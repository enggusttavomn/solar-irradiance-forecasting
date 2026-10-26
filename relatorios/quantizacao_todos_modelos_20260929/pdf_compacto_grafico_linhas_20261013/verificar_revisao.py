from pathlib import Path
import json
import sys

import pandas as pd
import pymupdf

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
PREVIOUS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_grafico_mae_20261012'
checker = (ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_analise_compacta_20261012/verificar_pdf.py').read_text(encoding='utf-8')
for before, after in [("if cell['pagina'] == 10", "if cell['pagina'] == 8"),
                      ('str(args.pdf.resolve())', 'str(args.pdf.absolute())')]:
    assert checker.count(before) == 1
    checker = checker.replace(before, after)
sys.argv = [str(__file__), '--pdf', str(WORK / 'revisao_v1.pdf'), '--manifesto', str(WORK / 'manifesto_v1.json')]
exec(compile(checker, str(__file__), 'exec'), {'__name__': '__main__', '__file__': str(__file__)})
sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import AUDIT_DIRS, REGIMES, TAREFAS, MODELOS, digest, model_label

record = json.loads((WORK / 'manifesto_v1.json').read_text(encoding='utf-8'))
old_record = json.loads((PREVIOUS / 'manifesto.json').read_text(encoding='utf-8'))
assert record['rankings_selecionados'] == old_record['rankings_selecionados']
graph = record['grafico_MAE']
assert graph['regime'] == 'atual'
assert graph['total_pontos'] == len(graph['pontos']) == 44
assert graph['total_series'] == len(graph['series']) == 11
assert len(graph['paineis']) == 1
panel = graph['paineis'][0]
assert panel['ordem_tarefas'] == list(TAREFAS)
assert panel['eixo_x_categorico'] and panel['eixo_y'][0] == 0
audit = json.loads((ROOT / 'relatorios/quantizacao_todos_modelos_20260929' / AUDIT_DIRS[0] / 'auditoria.json').read_text(encoding='utf-8'))
assert digest(audit['metricas']['path']) == audit['metricas']['sha256']
frame = pd.read_csv(audit['metricas']['path'])
frame = frame.loc[frame.particao == 'teste'].set_index(['tarefa', 'modelo', 'variante', 'horizonte'])
choices = {(r['tarefa'], r['modelo']): r['vencedor_validacao'] for r in audit['resultados']}
seen, minima = set(), 0
for point in graph['pontos']:
    task, model, level, horizon = point['tarefa'], point['modelo'], point['variante'], point['horizonte']
    assert point['regime'] == 'atual' and level == choices[task, model] and horizon == max(TAREFAS[task])
    expected = float(frame.loc[(task, model, level, horizon), 'MAE_wm2'])
    assert point['MAE_wm2'] == point['posicao_y'] == expected
    assert point['posicao_x'] == list(TAREFAS).index(task)
    assert panel['eixo_y'][0] <= expected <= panel['eixo_y'][1]
    task_values = [float(frame.loc[(task, m, choices[task, m], horizon), 'MAE_wm2']) for m in MODELOS]
    assert point['menor_MAE_conjunto'] == (expected == min(task_values))
    minima += int(point['menor_MAE_conjunto'])
    key = (task, model)
    assert key not in seen
    seen.add(key)
assert len(seen) == 44 and minima == 4
assert [s['modelo'] for s in graph['series']] == list(MODELOS)
for line in graph['series']:
    assert len(line['pontos']) == 4
    assert [p['tarefa'] for p in line['pontos']] == list(TAREFAS)
    assert all(p['modelo'] == line['modelo'] for p in line['pontos'])
    assert all(p in graph['pontos'] for p in line['pontos'])

old_pdf = ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
assert digest(old_pdf) == old_record['pdf']['sha256']
with pymupdf.open(old_pdf) as old_doc, pymupdf.open(WORK / 'revisao_v1.pdf') as doc:
    assert len(old_doc) == len(doc) == 10
    for index in range(9):
        assert doc[index].get_text() == old_doc[index].get_text(), index + 1
        assert doc[index].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).samples == old_doc[index].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).samples, index + 1
    text = doc[-1].get_text()
    for label in ('Desempenho dos modelos nas quatro tarefas', 'Base 2019-2024', 'Teste: 2024',
                  '72 h', '30 dias', '1 mês', '6 meses', 'resoluções horária, diária e mensal', 'exploratória'):
        assert label in text, label
    for model in MODELOS:
        assert model_label(model) in text, model
    for removed in ('Desempenho por tarefa.', 'Critério de classificação.', 'Quantização: escolha da validação versus controle do mesmo modelo', 'Escopo.', 'Limites.'):
        assert removed not in '\n'.join(page.get_text() for page in doc)
report_path = WORK / 'revisao_v1.verificacao.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
report.update(pontos_grafico_conferidos_csv=44, menores_MAE_conferidos=4, linhas_modelos_conferidas=11,
              primeira_nove_paginas_preservadas=True, escala_MAE_linear_inicio_zero=True,
              grafico_unico_vetorial=True, eixo_tarefas_categorico=True,
              trechos_removidos_continuam_ausentes=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pontos_grafico_conferidos': 44, 'modelos': 11, 'tarefas': 4, 'paginas_anteriores_preservadas': 9, 'ok': True}, ensure_ascii=False), flush=True)
