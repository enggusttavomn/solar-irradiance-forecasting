"""Confere a revisão com quatro rankings dos cinco menores MAEs."""
from collections import Counter
from math import isfinite
from pathlib import Path
import json
import re
import sys

import pandas as pd
import pymupdf


ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
PREVIOUS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_grafico_linhas_20261013'

checker = (ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_analise_compacta_20261012/verificar_pdf.py').read_text(encoding='utf-8')
for before, after in [("if cell['pagina'] == 10", "if cell['pagina'] == 8"),
                      ('str(args.pdf.resolve())', 'str(args.pdf.absolute())')]:
    assert checker.count(before) == 1
    checker = checker.replace(before, after)
sys.argv = [str(__file__), '--pdf', str(WORK / 'revisao_v1.pdf'),
            '--manifesto', str(WORK / 'manifesto_v1.json')]
exec(compile(checker, str(__file__), 'exec'), {'__name__': '__main__', '__file__': str(__file__)})

sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import AUDIT_DIRS, TAREFAS, MODELOS, digest, fmt, model_label


record = json.loads((WORK / 'manifesto_v1.json').read_text(encoding='utf-8'))
old_record = json.loads((PREVIOUS / 'manifesto.json').read_text(encoding='utf-8'))
assert len(record['celulas_pdf']) == 2104
assert record['rankings_selecionados'] == old_record['rankings_selecionados']

graph = record['grafico_MAE']
assert graph['regime'] == 'atual'
assert graph['total_pontos'] == len(graph['pontos']) == 20
assert graph['menores_MAE_destacados'] == 4
assert len(graph['paineis']) == 4
assert [panel['tarefa'] for panel in graph['paineis']] == list(TAREFAS)
assert [point['tarefa'] for point in graph['pontos']] == [task for task in TAREFAS for _ in range(5)]

audit = json.loads((ROOT / 'relatorios/quantizacao_todos_modelos_20260929' / AUDIT_DIRS[0] / 'auditoria.json').read_text(encoding='utf-8'))
assert digest(audit['metricas']['path']) == audit['metricas']['sha256']
frame = pd.read_csv(audit['metricas']['path'])
frame = frame.loc[frame.particao == 'teste'].set_index(['tarefa', 'modelo', 'variante', 'horizonte'])
assert frame.index.is_unique
choices = {(row['tarefa'], row['modelo']): row['vencedor_validacao'] for row in audit['resultados']}
assert set(choices) == {(task, model) for task in TAREFAS for model in MODELOS}

seen, minima = set(), 0
for task, panel in zip(TAREFAS, graph['paineis'], strict=True):
    horizon = max(TAREFAS[task])
    selected = [(float(frame.loc[(task, model, choices[task, model], horizon), 'MAE_wm2']), model)
                for model in MODELOS]
    selected.sort(key=lambda row: (row[0], row[1]))
    expected_top_five = selected[:5]
    points = [point for point in graph['pontos'] if point['tarefa'] == task]
    assert len(points) == 5
    assert panel['horizonte'] == horizon
    assert panel['modelos'] == [model for _, model in expected_top_five]
    assert panel['escala_x'] == 'linear; intervalo próprio'
    assert panel['ordem_mae_crescente'] is True
    assert len(panel['eixo_x']) == 2
    lower, upper = panel['eixo_x']
    assert isfinite(lower) and isfinite(upper) and 0 <= lower < upper
    assert lower <= expected_top_five[0][0] <= expected_top_five[-1][0] <= upper

    for position, (point, (expected_mae, expected_model)) in enumerate(zip(points, expected_top_five, strict=True), 1):
        assert point['regime'] == 'atual'
        assert point['modelo'] == expected_model
        assert point['modelo_exibido'] == model_label(expected_model)
        assert point['variante'] == choices[task, expected_model]
        assert point['horizonte'] == horizon
        assert point['MAE_wm2'] == point['posicao_x'] == expected_mae
        assert point['posicao'] == position
        assert point['posicao_y'] == position - 1
        assert lower <= expected_mae <= upper
        assert point['menor_MAE_conjunto'] is (expected_mae == selected[0][0])
        minima += int(point['menor_MAE_conjunto'])
        key = (task, expected_model)
        assert key not in seen
        seen.add(key)
assert len(seen) == 20 and minima == 4

old_pdf = ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
assert digest(old_pdf) == old_record['pdf']['sha256']
with pymupdf.open(old_pdf) as old_doc, pymupdf.open(WORK / 'revisao_v1.pdf') as doc:
    assert len(old_doc) == len(doc) == 10
    for index in range(9):
        assert doc[index].get_text() == old_doc[index].get_text(), index + 1
        assert doc[index].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).samples == old_doc[index].get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), alpha=False).samples, index + 1
    text = doc[-1].get_text()
    for label in ('Cinco menores MAEs por tarefa', 'Base 2019-2024', 'Teste: 2024',
                  '72 h', '30 dias', '1 mês', '6 meses'):
        assert label in text, label
    for label in ('escalas próprias', 'exploratória'):
        assert label in text.casefold(), label
    model_counts = Counter(model_label(point['modelo']) for point in graph['pontos'])
    for label, count in model_counts.items():
        assert text.count(label) >= count, (label, count)
    mae_counts = Counter(fmt(point['MAE_wm2'], 4) for point in graph['pontos'])
    for value, count in mae_counts.items():
        extracted = re.findall(r'(?<![\d,])' + re.escape(value) + r'(?![\d,])', text)
        assert len(extracted) >= count, (value, count)
    assert not doc[-1].get_images()
    all_text = '\n'.join(page.get_text() for page in doc)
    for removed in ('Desempenho por tarefa.', 'Critério de classificação.',
                    'Quantização: escolha da validação versus controle do mesmo modelo', 'Escopo.', 'Limites.'):
        assert removed not in all_text, removed

report_path = WORK / 'revisao_v1.verificacao.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
assert report['ok'] is True and report['celulas_verificadas'] == 2104
assert report['fontes_preservadas'] is True and report['originais_preservados'] is True
report.update(pontos_grafico_conferidos_csv=20, menores_MAE_conferidos=4,
              paineis_rankings_conferidos=4, primeira_nove_paginas_preservadas=True,
              escalas_MAE_lineares_proprias=True, rankings_top_cinco_conferidos_csv=True,
              nomes_e_MAEs_grafico_extraidos=True, grafico_rankings_vetorial=True,
              trechos_removidos_continuam_ausentes=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pontos_grafico_conferidos_csv': 20, 'menores_MAE_conferidos': 4,
                  'paineis_rankings_conferidos': 4, 'primeira_nove_paginas_preservadas': True,
                  'ok': True}, ensure_ascii=False), flush=True)
