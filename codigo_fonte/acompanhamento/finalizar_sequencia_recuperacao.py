"""Espera recuperacoes verificadas e prepara os PDFs para revisao visual."""
from __future__ import annotations

from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
import ctypes
import os
import subprocess
import sys
import time

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from codigo_fonte.acompanhamento.coordenacao_quantizacao import ler, agora
from codigo_fonte.utilitarios.json_atomico import salvar_json
from codigo_fonte.acompanhamento.processos_quantizacao import TravaDiretorio, ExecucaoOcupada, ProcessoProprio, identidade, mesma_instancia, processos_da_fila_ativos
from codigo_fonte.acompanhamento.metricas_quantizacao_todos import sha256
from codigo_fonte.experimentos.rodar_quantizacao_todos_modelos import TAREFAS, MODELOS, slug

REL = RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929'
DESTINO = REL / 'finalizacao_20261001'
SAIDA = RAIZ / 'resultados/quantizacao_todos_modelos_20260929'
FILAS_RECUPERACAO = {
    'RNN': REL / 'recuperacao_20261001/runner.json',
    'XGBoost': REL / 'recuperacao_xgboost_20261001/runner.json',
}
PARES_RNN = {(t, m) for t in ('daily_30', 'hourly_72_extension')
             for m in ('GRU', 'LSTM', 'DilatedRNN')}


def pendencias_refit(saida=SAIDA):
    """Os 44 caminhos sao obrigatorios; glob nao detecta arquivos ausentes."""
    pendentes = []
    for tarefa in TAREFAS:
        for modelo in MODELOS:
            pasta = Path(saida) / 'atual' / tarefa / slug(modelo)
            path = pasta / 'status.json'
            try:
                status = ler(path)
            except FileNotFoundError:
                pendentes.append({'par': f'{tarefa}/{modelo}', 'motivo': 'status ausente'})
                continue
            if status.get('modo') != 'completa':
                raise ValueError(f'Modo invalido para o refit completo: {path}')
            if status.get('etapa') != 'concluida':
                pendentes.append({'par': f'{tarefa}/{modelo}',
                                  'motivo': status.get('etapa', 'etapa ausente')})
    return pendentes


def conferir_fila(estado, nome, *, instante=None, checar=mesma_instancia,
                  arvore=processos_da_fila_ativos, max_heartbeat_s=600):
    """Inspeciona fila existente; nunca encerra processos de outro executor."""
    if estado.get('regime') != 'atual' or estado.get('modo') != 'completa':
        raise ValueError(f'Fila {nome} nao corresponde ao regime atual completo.')
    etapa = estado.get('etapa')
    if etapa in ('erro', 'interrompida') or estado.get('falhas'):
        raise RuntimeError(f'Recuperacao {nome} falhou ou foi interrompida; preservar e investigar.')
    ativos = arvore(estado)
    if etapa == 'concluida' and not ativos:
        return {'etapa': etapa, 'pronta': True, 'processos_ativos': ativos}
    registro = estado.get('identidade_runner')
    if not registro or not checar(registro):
        raise RuntimeError(f'Recuperacao {nome} parou sem concluir sua arvore de processos.')
    instante = instante or datetime.now(timezone.utc)
    try:
        atualizado = datetime.fromisoformat(estado['atualizado_em_utc'])
        atraso = (instante - atualizado).total_seconds()
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError(f'Recuperacao {nome} tem heartbeat invalido.') from exc
    if atraso > max_heartbeat_s:
        raise RuntimeError(f'Recuperacao {nome} sem atualizacao por dez minutos; inspecao obrigatoria.')
    return {'etapa': etapa, 'pronta': False, 'processos_ativos': ativos}


def conferir_escopo_rnn(rel=REL):
    path = Path(rel) / 'recuperacao_20261001/escopo.json'
    escopo = ler(path)
    pares = escopo.get('pares', [])
    if (not isinstance(pares, list) or len(pares) != len(PARES_RNN)
            or any(not isinstance(p, list) or len(p) != 2
                   or not all(isinstance(v, str) for v in p) for p in pares)
            or {tuple(p) for p in pares} != PARES_RNN):
        raise ValueError('Escopo da recuperacao RNN diverge dos seis pares autorizados.')
    origem_logica = Path(rel) / 'fila_integral_atual/atual/completa/runner.json'
    origem_preservada = (Path(rel) / 'recuperacao_20261001/estados_anteriores'
                        / 'fila_integral_atual/atual/completa/runner.json')
    fontes = (
        ('origem preservada', origem_preservada, 'origem_sha256'),
        ('politica', Path(rel) / 'politica_migracao_cpu_cuda/proposta_politica_v2.json', 'politica_sha256'),
        ('revisao', Path(rel) / 'politica_migracao_cpu_cuda/revisao_root_v2.json', 'revisao_sha256'),
    )
    if Path(escopo.get('origem', '')).resolve() != origem_logica.resolve():
        raise ValueError('Origem da recuperacao RNN nao corresponde a fila preservada.')
    for nome, fonte, chave in fontes:
        if escopo.get(chave) != sha256(fonte):
            raise ValueError(f'Fonte da recuperacao RNN alterada: {nome}')
    return sha256(path)


def conferir_sem_filas_ativas(rel=REL, *, arvore=processos_da_fila_ativos):
    caminhos = (
        'coordenacao_atual/status.json', 'coordenacao_historica/status.json',
        'fila_integral_atual/atual/completa/runner.json',
        'fila_aprendidos/atual/completa/runner.json',
        'fila_atencao/atual/completa/runner.json',
        'fila_estatisticos/atual/completa/runner.json',
        'fila_historica/historico_1998_2022/completa/runner.json',
        'fila_historica/historico_curto_pareado/completa/runner.json',
    )
    for caminho in caminhos:
        path = Path(rel) / caminho
        if path.exists() and arvore(ler(path)):
            raise RuntimeError(f'Coordenacao ou fila anterior ainda ativa: {path}')


def main():
    DESTINO.mkdir(parents=True, exist_ok=True)
    with TravaDiretorio(DESTINO):
        st = {'iniciado_em_utc': agora(), 'pid': os.getpid(),
              'identidade_coordenador': identidade(os.getpid()),
              'codigo_sha256': sha256(Path(__file__)),
              'publicado': False, 'revisao_visual_pendente': True,
              'processos_historico': []}
        filho = None
        travas_recuperacao = None

        def registrar(etapa, **campos):
            st.update(etapa=etapa, atualizado_em_utc=agora(), **campos)
            salvar_json(st, DESTINO / 'status.json')

        def executar(cmd, nome):
            nonlocal filho
            path = DESTINO / f'{nome}.log'
            with path.open('a', encoding='utf-8') as stream:
                stream.write(f'\nInicio {agora()}\n')
                stream.flush()
                filho = ProcessoProprio(cmd, cwd=RAIZ, stdout=stream, stderr=subprocess.STDOUT)
                st['processos_historico'].append(filho.registro)
                while filho.poll() is None:
                    registrar(nome, processo_filho=filho.registro, log=str(path))
                    time.sleep(10)
                retorno = filho.returncode
                filho.fechar()
                filho = None
                registrar(nome + '_concluida', processo_filho=None, retorno=retorno)
                if retorno:
                    raise RuntimeError(f'Falha {nome}: {path}')

        suspensao = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001))
        if not suspensao:
            raise OSError('Falha ao manter computador ativo.')
        try:
            escopo_sha = conferir_escopo_rnn(REL)
            while True:
                filas = {nome: conferir_fila(ler(path), nome)
                         for nome, path in FILAS_RECUPERACAO.items()}
                faltam = pendencias_refit(SAIDA)
                registrar('aguardando_recuperacoes', filas_recuperacao=filas,
                          pares_refit_pendentes=faltam, escopo_rnn_sha256=escopo_sha)
                if all(f['pronta'] for f in filas.values()):
                    if faltam:
                        raise RuntimeError('Recuperacoes encerradas, mas os 44 refits completos nao foram confirmados.')
                    travas = ExitStack()
                    try:
                        for path in sorted(FILAS_RECUPERACAO.values()):
                            travas.enter_context(TravaDiretorio(path.parent))
                        # Relendo dentro das travas: nenhuma recuperacao pode reiniciar.
                        finais = {nome: conferir_fila(ler(path), nome)
                                  for nome, path in FILAS_RECUPERACAO.items()}
                        if not all(f['pronta'] for f in finais.values()):
                            travas.close()
                        elif conferir_escopo_rnn(REL) != escopo_sha:
                            raise ValueError('Escopo da recuperacao mudou durante a espera.')
                        elif pendencias_refit(SAIDA):
                            raise RuntimeError('Refits completos mudaram durante a aquisicao das travas.')
                        else:
                            travas_recuperacao = travas
                            break
                    except ExecucaoOcupada:
                        travas.close()
                    except BaseException:
                        travas.close()
                        raise
                time.sleep(15)
            xgb = SAIDA / 'atual/hourly_72_extension/xgboost'
            from codigo_fonte.experimentos import experimento_xgboost_horario_controle_auditado_v1 as adaptador
            adaptador.validar_controle_adaptado(xgb)
            conferir_sem_filas_ativas(REL)
            py = [sys.executable, '-X', 'utf8', '-m']
            executar(py + ['codigo_fonte.acompanhamento.coordenar_quantizacao_atual', '--politica',
                str(REL / 'politica_migracao_cpu_cuda/proposta_politica_v2.json'),
                '--revisao', str(REL / 'politica_migracao_cpu_cuda/revisao_root_v2.json'),
                '--fila-estatisticos', str(REL / 'fila_atencao/atual/completa/runner.json')],
                'coordenacao_atual')
            if ler(REL / 'coordenacao_atual/status.json')['etapa'] != 'pronto_para_revisao_visual':
                raise RuntimeError('Coordenador atual nao preparou artefatos auditados.')
            travas_recuperacao.close()
            travas_recuperacao = None
            executar(py + ['codigo_fonte.acompanhamento.coordenar_quantizacao_historica', '--cpu-workers', '2',
                          '--gpu-workers', '2'], 'coordenacao_historica')
            if ler(REL / 'coordenacao_historica/status.json')['etapa'] != 'pronto_para_revisao_visual':
                raise RuntimeError('Coordenador historico nao preparou artefatos auditados.')
            registrar('pronto_para_revisao_visual', processo_filho=None,
                      observacao='Ambos PDFs preparados. Revisao visual, entrega e feedback final continuam pendentes.')
        except BaseException as exc:
            registrar('erro', erro=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            try:
                if filho is not None:
                    filho.encerrar()
            finally:
                if travas_recuperacao is not None:
                    travas_recuperacao.close()
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == '__main__':
    main()
