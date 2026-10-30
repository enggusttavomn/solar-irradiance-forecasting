'''Aguarda a base atual auditada e executa os dois historicos; PDF fica em revisao visual.'''
from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import sys
import time

from codigo_fonte.acompanhamento.metricas_quantizacao_todos import sha256
from codigo_fonte.acompanhamento.processos_quantizacao import TravaDiretorio, ExecucaoOcupada, identidade, processos_da_fila_ativos
from codigo_fonte.acompanhamento.coordenacao_quantizacao import ler, agora, ExecutadorCoordenacao, auditoria_publicavel, renderizar_pdf

RAIZ = Path(__file__).resolve().parents[2]
REL = RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929'
SAIDA = RAIZ / 'resultados/quantizacao_todos_modelos_20260929'
REGIMES = ('historico_1998_2022', 'historico_curto_pareado')
HASH_PROTOCOL = {
    'historico_1998_2022': 'edb58147b05c5fb6a767f7a80eaaedd57c0fdab768ac37c6683066f81308faf6',
    'historico_curto_pareado': '3fa36401531985272142165c7ae1837197c55dfc8a7c0fc9d573a0e1e8f6e09f',
}
HASH_AUDITORIA_DADOS = '52d4e4ffb2f6005749755ab18444954cd09ebc410c5ad1d748a3146453e9d96f'


def preflight_historico(protocolos, auditoria_dados, *, raiz=RAIZ):
    '''Confere coleta e protocolos sem exigir contratos de modelos ainda nao treinados.'''
    from codigo_fonte.analises_e_relatorios.auditar_pareamento_historicos import caminho, conferir_hash_interno, registrar_fonte, QUANTIDADES_FONTES
    fontes = {}
    registrar_fonte(fontes, auditoria_dados, HASH_AUDITORIA_DADOS)
    audit = ler(auditoria_dados)
    if audit.get('ok') is not True or audit.get('aprovado') is not True:
        raise ValueError('Auditoria estrutural dos dados historicos nao aprovada.')
    c = audit['contrato']
    contrato_path = caminho(c['arquivo'], raiz)
    registrar_fonte(fontes, contrato_path, c['sha256_arquivo'])
    contrato = ler(contrato_path)
    conferir_hash_interno(contrato, contrato_path)
    if (contrato.get('ok') is not True or contrato.get('aprovado') is not True
            or contrato['sha256_contrato'] != c['sha256_contrato']):
        raise ValueError('Contrato de coleta nao corresponde a auditoria aprovada.')
    for regime in REGIMES:
        path = protocolos[regime]
        registrar_fonte(fontes, path, HASH_PROTOCOL[regime])
        p = ler(path)
        if (p.get('regime') != regime or p.get('carregador_historico') is not True
                or caminho(p['contrato_preparacao_dados'], raiz) != contrato_path
                or p.get('sha256_arquivo_contrato_preparacao') != c['sha256_arquivo']
                or p.get('sha256_contrato_preparacao') != c['sha256_contrato']):
            raise ValueError('Protocolo diverge da coleta aprovada.')
    entradas = contrato.get('entradas', {})
    if set(entradas) != set(QUANTIDADES_FONTES):
        raise ValueError('Grupos da coleta incompletos.')
    arquivos = set()
    for grupo, quantidade in QUANTIDADES_FONTES.items():
        itens = entradas[grupo]
        if len(itens) != quantidade:
            raise ValueError(f'Quantidade invalida de fontes: {grupo}')
        for item in itens:
            path = caminho(item['arquivo'], raiz)
            if path in arquivos or path.stat().st_size != item['bytes']:
                raise ValueError('Fonte duplicada ou tamanho divergente na coleta.')
            registrar_fonte(fontes, path, item['sha256'])
            arquivos.add(path)
    if len(arquivos) != 70:
        raise ValueError('A coleta deve conter 70 arquivos distintos.')
    for item in [contrato['manifesto_horario'], *contrato['auditorias'].values()]:
        registrar_fonte(fontes, caminho(item['arquivo'], raiz), item['sha256'])
    registrar_fonte(fontes, Path(raiz) / 'codigo_fonte/experimentos/experimento_quantizacao_concorrentes.py', audit['motor_sha256'])
    return {'ok': True, 'aprovado': True, 'arquivos_coleta_verificados': len(arquivos),
            'verificado_em_utc': agora(), 'fontes_sha256': fontes}


def conferir_porta_atual(status, auditoria, auditoria_path):
    if status.get('etapa') != 'pronto_para_revisao_visual':
        raise ValueError('Resultados atuais ainda nao estao preparados para revisao visual.')
    if not auditoria_publicavel(auditoria, 'atual'):
        raise ValueError('Auditoria atual completa/publicavel obrigatoria antes do historico.')
    if status.get('auditoria_sha256') != sha256(auditoria_path):
        raise ValueError('Auditoria atual nao corresponde ao status do coordenador.')
    metricas = auditoria.get('metricas', {})
    if not metricas.get('path') or metricas.get('sha256') != sha256(Path(metricas['path'])):
        raise ValueError('Metricas atuais auditadas foram alteradas.')


def aguardar_atual(status_path, auditoria_path, registrar, *, intervalo=15):
    '''A trava da coordenacao atual fica retida durante o historico, impedindo relancamento.'''
    while True:
        if not status_path.exists():
            registrar('aguardando_coordenacao_atual', motivo='Status ainda nao foi criado.')
            time.sleep(intervalo)
            continue
        status = ler(status_path)
        if status.get('etapa') in ('erro', 'interrompida'):
            raise RuntimeError('Coordenacao atual falhou; historico nao sera iniciado.')
        ativos = processos_da_fila_ativos(status)
        registrar('aguardando_coordenacao_atual', etapa_atual=status.get('etapa'), processos_ativos=ativos)
        if status.get('etapa') == 'pronto_para_revisao_visual' and not ativos:
            trava = TravaDiretorio(status_path.parent)
            try:
                trava.__enter__()
            except ExecucaoOcupada:
                time.sleep(intervalo)
                continue
            try:
                novo = ler(status_path)
                if novo.get('etapa') == 'pronto_para_revisao_visual' and not processos_da_fila_ativos(novo):
                    conferir_porta_atual(novo, ler(auditoria_path), auditoria_path)
                    return trava
            except BaseException:
                trava.__exit__(None, None, None)
                raise
            trava.__exit__(None, None, None)
        elif not ativos:
            raise RuntimeError('Coordenacao atual parou sem concluir; requer inspecao.')
        time.sleep(intervalo)


def comando_fila_historica(args, regime, protocolo):
    cmd = [sys.executable, '-X', 'utf8', '-m', 'codigo_fonte.experimentos.rodar_quantizacao_todos_modelos',
           '--regime', regime, '--saida', str(SAIDA), '--relatorios', str(REL / 'fila_historica'),
           '--protocolo', str(protocolo.resolve()), '--cpu-workers', str(args.cpu_workers),
           '--gpu-workers', str(args.gpu_workers)]
    global_path = SAIDA / regime / 'selecao_global_congelada.json'
    if global_path.exists():
        # Arquivo presente mas invalido deve bloquear, nunca escolher de novo.
        from codigo_fonte.experimentos.rodar_quantizacao_todos_modelos import congelar, TAREFAS, MODELOS
        gate = argparse.Namespace(regime=regime, saida=SAIDA, smoke=False, somente_refit=True)
        congelar(gate, [(t, m) for t in TAREFAS for m in MODELOS])
        cmd.append('--somente-refit')
    return cmd


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--status-atual', type=Path, default=REL / 'coordenacao_atual/status.json')
    ap.add_argument('--auditoria-atual', type=Path, default=REL / 'auditoria_final_atual/auditoria.json')
    ap.add_argument('--protocolo-longo', type=Path, default=REL / 'historico/protocolo_historico_1998_2022.json')
    ap.add_argument('--protocolo-curto', type=Path, default=REL / 'historico/protocolo_historico_curto_pareado.json')
    ap.add_argument('--auditoria-dados', type=Path, default=REL / 'historico/auditoria_contextos_historicos_aprovada.json')
    ap.add_argument('--cpu-workers', type=int, default=2)
    ap.add_argument('--gpu-workers', type=int, default=1)
    ap.add_argument('--somente-planejar', action='store_true')
    args = ap.parse_args()
    if min(args.cpu_workers, args.gpu_workers) < 1:
        ap.error('Numero de workers deve ser positivo.')
    print('Plano: aguardar atual auditado; historico longo; auditoria; curto pareado; auditoria; pareamento; PDF separado.', flush=True)
    if args.somente_planejar:
        return
    with TravaDiretorio(REL / 'coordenacao_historica'):
        coordenar(args)


def coordenar(args):
    rel = REL / 'coordenacao_historica'
    status = {'iniciado_em_utc': agora(), 'pid': os.getpid(), 'identidade_coordenador': identidade(os.getpid()),
              'publicado': False, 'revisao_visual_pendente': True, 'codigo_sha256': sha256(Path(__file__))}
    exe = ExecutadorCoordenacao(RAIZ, rel, status)
    trava_atual = None
    suspensao = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)) if os.name == 'nt' else False
    py = [sys.executable, '-X', 'utf8', '-m']
    try:
        protocolos = dict(zip(REGIMES, (args.protocolo_longo, args.protocolo_curto), strict=True))
        for regime, path in protocolos.items():
            if sha256(path) != HASH_PROTOCOL[regime] or ler(path).get('regime') != regime:
                raise ValueError(f'Protocolo historico nao corresponde ao revisado: {regime}')
        a_dados = ler(args.auditoria_dados)
        if (sha256(args.auditoria_dados) != HASH_AUDITORIA_DADOS
                or a_dados.get('ok') is not True or a_dados.get('aprovado') is not True):
            raise ValueError('Auditoria estrutural dos dados historicos nao aprovada.')
        trava_atual = aguardar_atual(args.status_atual, args.auditoria_atual, exe.registrar)
        status['auditoria_atual_sha256'] = sha256(args.auditoria_atual)
        auditorias = {}
        for regime in REGIMES:
            exe.registrar('verificando_coleta_' + regime)
            preflight = preflight_historico(protocolos, args.auditoria_dados)
            from codigo_fonte.utilitarios.json_atomico import salvar_json
            salvar_json(preflight, rel / ('preflight_' + regime + '.json'))
            exe.executar(comando_fila_historica(args, regime, protocolos[regime]), 'fila_' + regime)
            auditoria = REL / ('auditoria_' + regime) / 'auditoria.json'
            exe.executar(py + ['codigo_fonte.analises_e_relatorios.auditar_quantizacao_todos_modelos', '--regime', regime,
                '--saida', str(SAIDA), '--replay', '--relatorio', str(auditoria)], 'auditoria_' + regime)
            if not auditoria_publicavel(ler(auditoria), regime):
                raise RuntimeError(f'Auditoria historica incompleta: {regime}')
            auditorias[regime] = auditoria
        pareamento = REL / 'auditoria_pareamento_historico/pareamento.json'
        exe.executar(py + ['codigo_fonte.analises_e_relatorios.auditar_pareamento_historicos', '--saida-experimentos', str(SAIDA),
            '--auditoria-longo', str(auditorias[REGIMES[0]]), '--auditoria-curto', str(auditorias[REGIMES[1]]),
            '--auditoria-dados', str(args.auditoria_dados.resolve()), '--protocolo-longo', str(args.protocolo_longo.resolve()),
            '--protocolo-curto', str(args.protocolo_curto.resolve()), '--relatorio', str(pareamento)], 'auditoria_pareamento')
        p = ler(pareamento)
        if p.get('ok') is not True or p.get('publicavel') is not True:
            raise RuntimeError('Pareamento historico nao aprovado.')
        if not (REL / 'marcador_operacao_pdf.json').exists():
            raise RuntimeError('Marcador da operacao PDF atual/historica ausente.')
        pdf = REL / 'pdf_historico/tabela_quantizacao_historico_1998_2022.pdf'
        manifesto = pdf.parent / 'manifesto.json'
        exe.executar(py + ['codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos', '--auditorias',
            str(auditorias[REGIMES[0]]), str(auditorias[REGIMES[1]]), '--pareamento', str(pareamento),
            '--saida', str(pdf), '--manifesto', str(manifesto)], 'preparar_pdf_historico')
        exe.executar(py + ['codigo_fonte.analises_e_relatorios.resumir_historicos_quantizacao', '--longo', str(auditorias[REGIMES[0]]),
            '--curto', str(auditorias[REGIMES[1]]), '--pareamento', str(pareamento),
            '--saida', str(REL / 'feedback_resultados_historicos.md')], 'preparar_feedback_historico')
        exe.registrar('pronto_para_revisao_visual', pdf=str(pdf), manifesto=str(manifesto),
            imagens=renderizar_pdf(pdf), pareamento=str(pareamento), pareamento_sha256=sha256(pareamento),
            observacao='Arquivo separado; revisao visual e publicacao nao executadas.')
    except BaseException as exc:
        exe.registrar('erro', erro=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        try:
            exe.fechar()
        finally:
            if trava_atual is not None:
                trava_atual.__exit__(None, None, None)
            if suspensao:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == '__main__':
    main()
