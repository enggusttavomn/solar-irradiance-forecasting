'''Guardas compartilhadas pelos coordenadores; nao alteram a ciencia dos experimentos.'''
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time

from codigo_fonte.utilitarios.json_atomico import salvar_json
from codigo_fonte.acompanhamento.processos_quantizacao import ProcessoProprio, TravaDiretorio, ExecucaoOcupada, processos_da_fila_ativos

TERMINAIS = {'selecao_concluida', 'concluida', 'erro', 'interrompida'}
PARES_GPU = {(t, m) for t in ('daily_30', 'hourly_72_extension') for m in ('GRU', 'LSTM', 'DilatedRNN')}


def ler(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def agora():
    return datetime.now(timezone.utc).isoformat()


def auditoria_publicavel(a, regime):
    return (a.get('ok') is True and a.get('publicavel') is True
            and a.get('modo') == 'completa' and a.get('regime') == regime
            and a.get('escopo_completo') is True and a.get('replay_novo_executado') is True
            and a.get('pares_verificados') == 44)


def controles_solicitados(fila, saida, *, permitir_resolvidos=False):
    '''Toda falha deve ser exatamente a solicitacao prevista, nunca um erro tecnico.'''
    if fila.get('etapa') != 'erro':
        if fila.get('etapa') in {'selecao_concluida', 'concluida'} and not fila.get('falhas'):
            return []
        raise ValueError('Fila nao terminou corretamente ou foi interrompida.')
    falhas = fila.get('falhas', [])
    jobs = [f for f in falhas if 'modelo' in f]
    if not jobs:
        raise ValueError('Fila falhou sem solicitacao explicita de controle.')
    for f in falhas:
        if 'modelo' not in f and not (f.get('tipo') == 'RuntimeError' and f.get('mensagem', '').startswith(
                f'{len(jobs)} execucoes falharam; outras selecoes foram preservadas. Consulte ')):
            raise ValueError('Erro geral da fila exige inspecao antes de retomar.')
    pendentes = []
    for f in jobs:
        if (f.get('tarefa'), f.get('modelo')) not in PARES_GPU or f.get('fase') not in ('selecao', 'refit'):
            raise ValueError('Falha fora da politica de migracao CPU/CUDA.')
        if not f.get('returncode'):
            raise ValueError('Falha sem codigo de saida nao zero.')
        part = 'validacao' if f['fase'] == 'selecao' else 'teste'
        pasta = Path(saida).resolve() / 'atual' / f['tarefa'] / f['modelo'].lower()
        divergencia = pasta / f'controle_{part}_divergencia.json'
        aceite = pasta / f'aceite_controle_gpu_{part}.json'
        ultima = Path(f['log']).read_text(encoding='utf-8').strip().splitlines()[-1]
        esperado = f'ValueError: Controle GPU exige auditoria independente registrada em {aceite}'
        if ultima != esperado or not divergencia.is_file():
            raise ValueError('Falha tecnica ou mensagem diferente da solicitacao de controle prevista.')
        d = ler(divergencia)
        if not (d.get('novo_controle_por_dispositivo') is True and d.get('dispositivo') == 'cuda'
                and d.get('dispositivo_original') == 'cpu' and d.get('alvos_primarios_bitexatos') is True):
            raise ValueError('Divergencia nao representa a migracao CPU/CUDA autorizada.')
        if aceite.exists():
            if not permitir_resolvidos:
                raise ValueError('Falha reapareceu apesar de aceite existente; inspecao obrigatoria.')
            # A mesma validacao do motor confere fonte, contrato e todas as evidencias.
            from codigo_fonte.experimentos.experimento_quantizacao_concorrentes import validar_aceite_gpu
            from codigo_fonte.acompanhamento.metricas_quantizacao_todos import sha256
            validar_aceite_gpu(aceite, d['contrato_sha256'], d['sha256'], sha256(divergencia))
        else:
            pendentes.append((pasta, part))
    return sorted(set(pendentes), key=lambda p: (str(p[0]), p[1]))


def aguardar_filas(paths, registrar, *, intervalo=15):
    '''Retorna locks mantidos pelo chamador; filas antigas sao somente inspecionadas.'''
    paths = [Path(p) for p in paths]
    while True:
        estados = []
        for path in paths:
            f = ler(path)
            if f.get('regime') != 'atual' or f.get('modo') != 'completa':
                raise ValueError('Fila inicial de outro regime/modo.')
            ativos = processos_da_fila_ativos(f)
            estados.append((path, f, ativos))
            if f.get('etapa') not in TERMINAIS and not ativos:
                raise RuntimeError('Fila sem processo ativo nem estado terminal; inspecao obrigatoria.')
            if f.get('etapa') not in TERMINAIS:
                idade = (datetime.now(timezone.utc) - datetime.fromisoformat(f['atualizado_em_utc'])).total_seconds()
                if idade > 600:
                    raise RuntimeError('Fila sem atualizacao por dez minutos; nao retomar automaticamente.')
        registrar('aguardando_filas_iniciais', filas=[{'path': str(p), 'etapa': f['etapa'],
                  'processos_ativos': ativos} for p, f, ativos in estados])
        if all(f.get('etapa') in TERMINAIS and not ativos for _, f, ativos in estados):
            locks = ExitStack()
            try:
                for path in sorted(paths):
                    locks.enter_context(TravaDiretorio(path.parent))
                novos = [(p, ler(p)) for p in paths]
                if all(f.get('etapa') in TERMINAIS and not processos_da_fila_ativos(f) for _, f in novos):
                    return locks, novos
            except ExecucaoOcupada:
                pass
            except BaseException:
                locks.close()
                raise
            locks.close()
        time.sleep(intervalo)


class ExecutadorCoordenacao:
    def __init__(self, raiz, rel, status):
        self.raiz, self.rel, self.status = Path(raiz), Path(rel), status
        self.filho = None

    def registrar(self, etapa, **campos):
        self.status.update(etapa=etapa, atualizado_em_utc=agora(), **campos)
        salvar_json(self.status, self.rel / 'status.json')

    def executar(self, cmd, nome, exigir_sucesso=True):
        log = self.rel / f'{nome}.log'
        with log.open('a', encoding='utf-8') as stream:
            stream.write(f'\nInicio {agora()}\n')
            stream.flush()
            self.filho = ProcessoProprio(cmd, cwd=self.raiz, stdout=stream, stderr=subprocess.STDOUT)
            self.status.setdefault('processos_historico', []).append(self.filho.registro)
            print(f'{nome}: iniciado pid={self.filho.pid}', flush=True)
            while self.filho.poll() is None:
                self.registrar(nome, processo_filho=self.filho.registro, log=str(log))
                time.sleep(10)
            retorno = self.filho.returncode
            self.filho.fechar()
            self.filho = None
        self.status.setdefault('eventos', []).append({'etapa': nome, 'retorno': retorno,
                                                      'fim_utc': agora(), 'log': str(log)})
        self.registrar(nome + '_concluida', processo_filho=None)
        if exigir_sucesso and retorno:
            raise RuntimeError(f'Falha {nome}; consultar {log}')
        return retorno

    def fechar(self):
        if self.filho is not None:
            self.filho.encerrar()
            self.filho = None


def renderizar_pdf(pdf):
    import pymupdf
    pasta = Path(pdf).parent / 'paginas'
    pasta.mkdir(exist_ok=True)
    imagens = []
    with pymupdf.open(pdf) as doc:
        for i, pagina in enumerate(doc, 1):
            imagem = pasta / f'pagina_{i:03d}.png'
            pagina.get_pixmap(matrix=pymupdf.Matrix(1.8, 1.8), alpha=False).save(imagem)
            imagens.append(str(imagem))
    return imagens
