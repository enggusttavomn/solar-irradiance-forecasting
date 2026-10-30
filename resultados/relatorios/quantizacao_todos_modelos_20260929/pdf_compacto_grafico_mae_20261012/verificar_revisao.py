from pathlib import Path
import json
import sys

import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
ORIGINAL_CHECKER = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_analise_compacta_20261012/verificar_pdf.py'
PREVIOUS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_sem_abertura_20261012'
checker = ORIGINAL_CHECKER.read_text(encoding='utf-8')
for before, after in [("if cell['pagina'] == 10", "if cell['pagina'] == 8"),
                      ('str(args.pdf.resolve())', 'str(args.pdf.absolute())')]:
    assert checker.count(before) == 1
    checker = checker.replace(before, after)
sys.argv = [str(__file__), '--pdf', str(WORK / 'revisao_v1.pdf'), '--manifesto', str(WORK / 'manifesto_v1.json')]
exec(compile(checker, str(__file__), 'exec'), {'__name__': '__main__', '__file__': str(__file__)})
sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import AUDIT_DIRS, REGIMES, TAREFAS, MODELOS, digest

record = json.loads((WORK / 'manifesto_v1.json').read_text(encoding='utf-8'))
old_record = json.loads((PREVIOUS / 'manifesto.json').read_text(encoding='utf-8'))
assert record['rankings_selecionados'] == old_record['rankings_selecionados']
graph = record['grafico_MAE']
assert graph['total_pontos'] == len(graph['pontos']) == 132
seen, minima = set(), 0
for regime, folder in zip(REGIMES, AUDIT_DIRS, strict=True):
    audit = json.loads((ROOT / 'relatorios/quantizacao_todos_modelos_20260929' / folder / 'auditoria.json').read_text(encoding='utf-8'))
    frame = pd.read_csv(audit['metricas']['path'])
    assert digest(audit['metricas']['path']) == audit['metricas']['sha256']
    frame = frame.loc[frame.particao == 'teste'].set_index(['tarefa', 'modelo', 'variante', 'horizonte'])
    choices = {(r['tarefa'], r['modelo']): r['vencedor_validacao'] for r in audit['resultados']}
    for point in [p for p in graph['pontos'] if p['regime'] == regime]:
        task, model, level, horizon = point['tarefa'], point['modelo'], point['variante'], point['horizonte']
        assert level == choices[task, model] and horizon == max(TAREFAS[task])
        expected = float(frame.loc[(task, model, level, horizon), 'MAE_wm2'])
        assert point['MAE_wm2'] == expected
        task_values = [float(frame.loc[(task, m, choices[task, m], horizon), 'MAE_wm2']) for m in MODELOS]
        assert point['menor_MAE_conjunto'] == (expected == min(task_values))
        minima += int(point['menor_MAE_conjunto'])
        key = (regime, task, model)
        assert key not in seen
        seen.add(key)
assert len(seen) == 132 and minima == 12
assert all(panel['eixo_x'][0] == 0 and panel['escala'] == 'linear, inicio em zero' for panel in graph['paineis'])
assert len({tuple(panel['modelos']) for panel in graph['paineis']}) == 1

old_pdf = ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
old_doc, doc = pymupdf.open(old_pdf), pymupdf.open(WORK / 'revisao_v1.pdf')
assert len(old_doc) == 9 and len(doc) == 10
for index in range(9):
    body = pymupdf.Rect(0, 0, doc[index].rect.width, doc[index].rect.height - 25)
    assert doc[index].get_text(clip=body) == old_doc[index].get_text(clip=body), index + 1
    assert doc[index].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), clip=body, alpha=False).samples == old_doc[index].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), clip=body, alpha=False).samples, index + 1
text = doc[-1].get_text()
assert 'Desempenho dos modelos pelo MAE' in text
for model in MODELOS:
    label = {'Persistencia': 'Persistência', 'Sazonal ingenuo': 'Sazonal ingênuo'}.get(model, model)
    assert text.count(label) >= 4, label
for removed in ('Desempenho por tarefa.', 'Critério de classificação.', 'Quantização: escolha da validação versus controle do mesmo modelo', 'Escopo.', 'Limites.'):
    assert removed not in '\n'.join(page.get_text() for page in doc)
report_path = WORK / 'revisao_v1.verificacao.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
report.update(pontos_grafico_conferidos_csv=132, menores_MAE_destacados_conferidos=12,
              primeira_nove_paginas_preservadas=True, eixos_lineares_inicio_zero=True,
              grafico_vetorial=True, trechos_removidos_continuam_ausentes=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pontos_grafico_conferidos': 132, 'destaques_conferidos': 12, 'paginas_anteriores_preservadas': 9, 'ok': True}, ensure_ascii=False), flush=True)
