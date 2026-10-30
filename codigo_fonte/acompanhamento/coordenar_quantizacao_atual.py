'''Conclui a base atual e prepara o PDF, sem publicacao nem aprovacao visual automatica.'''
from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import sys

from codigo_fonte.acompanhamento.metricas_quantizacao_todos import sha256
from codigo_fonte.utilitarios.json_atomico import salvar_json
from codigo_fonte.acompanhamento.processos_quantizacao import TravaDiretorio, identidade
from codigo_fonte.acompanhamento.coordenacao_quantizacao import ler, agora, ExecutadorCoordenacao, aguardar_filas, controles_solicitados, auditoria_publicavel, renderizar_pdf

RAIZ = Path(__file__).resolve().parents[2]
REL = RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929'
SAIDA = RAIZ / 'resultados/quantizacao_todos_modelos_20260929'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--politica', type=Path, required=True)
    ap.add_argument('--revisao', type=Path, required=True)
    ap.add_argument('--fila-aprendidos', type=Path, default=REL / 'fila_aprendidos/atual/completa/runner.json')
    ap.add_argument('--fila-estatisticos', type=Path, default=REL / 'fila_estatisticos/atual/completa/runner.json')
    ap.add_argument('--somente-planejar', action='store_true')
    args = ap.parse_args()
    print('Plano: aguardar filas e arvores; verificar controles; concluir selecao/refit; auditar; preparar PDF.', flush=True)
    if args.somente_planejar:
        return
    rel = REL / 'coordenacao_atual'
    with TravaDiretorio(rel):
        coordenar(args, rel)


def coordenar(args, rel):
    review = ler(args.revisao)
    verifier = RAIZ / 'codigo_fonte/analises_e_relatorios/verificar_migracao_controles_gpu.py'
    if not (review.get('aprovado') is True and review.get('politica_sha256') == sha256(args.politica)
            and review.get('verificador_sha256') == sha256(verifier)):
        raise ValueError('Politica/verificador nao correspondem a revisao explicita.')
    status = {'iniciado_em_utc': agora(), 'pid': os.getpid(), 'identidade_coordenador': identidade(os.getpid()),
              'publicado': False, 'historico_iniciado': False, 'codigo_sha256': sha256(Path(__file__)),
              'politica': {'path': str(args.politica.resolve()), 'sha256': sha256(args.politica)},
              'revisao': {'path': str(args.revisao.resolve()), 'sha256': sha256(args.revisao)}}
    exe = ExecutadorCoordenacao(RAIZ, rel, status)
    py = [sys.executable, '-X', 'utf8', '-m']
    locks_iniciais = None
    suspensao = bool(ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)) if os.name == 'nt' else False

    def validar(pendentes):
        for pasta, part in pendentes:
            exe.executar(py + ['codigo_fonte.analises_e_relatorios.verificar_migracao_controles_gpu', '--pasta', str(pasta),
                '--particao', part, '--politica', str(args.politica.resolve()),
                '--revisao', str(args.revisao.resolve()), '--emitir'], f'controle_{pasta.parent.name}_{pasta.name}_{part}')
            if not (pasta / f'aceite_controle_gpu_{part}.json').is_file():
                raise RuntimeError('Verificador nao gerou o registro exigido.')

    try:
        locks_iniciais, filas = aguardar_filas((args.fila_aprendidos, args.fila_estatisticos), exe.registrar)
        pendentes = []
        # Examina TODAS as falhas antes de emitir qualquer aceite ou relancar fila.
        for _, fila in filas:
            pendentes.extend(controles_solicitados(fila, SAIDA, permitir_resolvidos=True))
        validar(sorted(set(pendentes), key=lambda p: (str(p[0]), p[1])))
        fila_final = REL / 'fila_integral_atual'
        cmd = py + ['codigo_fonte.experimentos.rodar_quantizacao_todos_modelos', '--regime', 'atual',
                    '--relatorios', str(fila_final), '--cpu-workers', '2', '--gpu-workers', '1']
        for tentativa in range(1, 4):
            retorno = exe.executar(cmd, f'fila_integral_{tentativa}', exigir_sucesso=False)
            if retorno == 0:
                break
            fila = ler(fila_final / 'atual/completa/runner.json')
            pendentes = controles_solicitados(fila, SAIDA)
            if tentativa == 3 or not pendentes:
                raise RuntimeError('Falha sem novo controle elegivel; preservar execucao para inspecao.')
            validar(pendentes)
        auditoria = REL / 'auditoria_final_atual/auditoria.json'
        exe.executar(py + ['codigo_fonte.analises_e_relatorios.auditar_quantizacao_todos_modelos', '--regime', 'atual', '--replay',
                          '--relatorio', str(auditoria)], 'auditoria_completa')
        if not auditoria_publicavel(ler(auditoria), 'atual'):
            raise RuntimeError('Auditoria nao aprovou os 44 pares completos com replay.')
        marker_record = REL / 'marcador_operacao_pdf.json'
        if not marker_record.exists():
            marker = Path('C:/Users/gm.nascimento/.codex/plugins/cache/openai-primary-runtime/pdf/26.923.10815/skills/pdf/container_tools/mark_artifact_operation_started.mjs')
            exe.executar(['node', str(marker), '--operation-kind', 'edit', '--expected-output-count', '2',
                          '--output-format', 'pdf'], 'marcador_pdf')
            salvar_json({'executado_em_utc': agora(), 'operacao': 'edit', 'pdfs_previstos': 2}, marker_record)
        pdf, manifesto = REL / 'pdf_atual/tabela_resultados_ghi_2024.pdf', REL / 'pdf_atual/manifesto.json'
        exe.executar(py + ['codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos', '--auditorias', str(auditoria),
                          '--saida', str(pdf), '--manifesto', str(manifesto)], 'preparar_pdf')
        exe.executar(py + ['codigo_fonte.analises_e_relatorios.resumir_quantizacao_todos_modelos', '--auditoria', str(auditoria),
                          '--saida', str(REL / 'feedback_resultados_atual.md')], 'preparar_feedback')
        exe.registrar('pronto_para_revisao_visual', pdf=str(pdf), manifesto=str(manifesto),
                      auditoria=str(auditoria), auditoria_sha256=sha256(auditoria), imagens=renderizar_pdf(pdf),
                      observacao='PDF original preservado; revisao visual e publicacao permanecem pendentes.')
    except BaseException as exc:
        exe.registrar('erro', erro=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        try:
            exe.fechar()
        finally:
            if locks_iniciais is not None:
                locks_iniciais.close()
            if suspensao:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)


if __name__ == '__main__':
    main()
