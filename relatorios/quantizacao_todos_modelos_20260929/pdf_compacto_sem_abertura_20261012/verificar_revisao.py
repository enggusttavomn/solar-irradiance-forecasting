from pathlib import Path
import json
import sys

import pymupdf

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(__file__).resolve().parent
PREVIOUS = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_analise_compacta_20261012'
checker = (PREVIOUS / 'verificar_pdf.py').read_text(encoding='utf-8')
changes = [
    ('assert len(doc) == 10', 'assert len(doc) == 9'),
    ('assert len(doc.get_toc()) == 10', 'assert len(doc.get_toc()) == 9'),
    ("f'{index}/10'", "f'{index}/9'"),
    ("if cell['pagina'] == 10", "if cell['pagina'] == 8"),
    ('for start in range(1, 11, 2):', 'for start in range(1, 10, 2):'),
    ('for offset in range(2):', 'for offset in range(min(2, len(doc) - start + 1)):'),
    ('str(args.pdf.resolve())', 'str(args.pdf.absolute())'),
]
for before, after in changes:
    assert checker.count(before) == 1, before
    checker = checker.replace(before, after)
sys.argv = [str(__file__), '--pdf', str(WORK / 'revisao.pdf'), '--manifesto', str(WORK / 'manifesto.json')]
exec(compile(checker, str(__file__), 'exec'), {'__name__': '__main__', '__file__': str(__file__)})

old_record = json.loads((PREVIOUS / 'manifesto.json').read_text(encoding='utf-8'))
new_record = json.loads((WORK / 'manifesto.json').read_text(encoding='utf-8'))
assert new_record['rankings_selecionados'] == old_record['rankings_selecionados']
archived_previous = ROOT / 'relatorios/quantizacao_todos_modelos_20260929/pdf_compacto_sem_abertura_20261012/compacto_anterior_10_paginas.pdf'
old_pdf = archived_previous if archived_previous.exists() else ROOT / 'output/pdf/quantizacao_ghi_unificado_compacto_20261009.pdf'
old_doc = pymupdf.open(old_pdf)
new_doc = pymupdf.open(WORK / 'revisao.pdf')
assert len(old_doc) == 10 and len(new_doc) == 9
for index in range(8):
    page, old_page = new_doc[index], old_doc[index + 2]
    body = pymupdf.Rect(0, 0, page.rect.width, page.rect.height - 25)
    assert page.get_text(clip=body) == old_page.get_text(clip=body), index + 1
    assert page.get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), clip=body, alpha=False).samples == old_page.get_pixmap(matrix=pymupdf.Matrix(1.2, 1.2), clip=body, alpha=False).samples, index + 1
old_period_cells = [dict(c, pagina=9) for c in old_record['celulas_pdf'] if c['pagina'] == 2][:20]
new_period_cells = [c for c in new_record['celulas_pdf'] if c['pagina'] == 9]
assert old_period_cells == new_period_cells
all_text = '\n'.join(page.get_text() for page in new_doc)
for removed in ('Comparação dos modelos de previsão de GHI', 'Desempenho por tarefa.', 'Critério de classificação.',
                'MAE e RMSE.', 'Interpretação.', 'Quantização: escolha da validação versus controle do mesmo modelo',
                'As contagens abrangem 44', 'Condições de entrada.', 'Métricas.', 'Escopo.', 'Limites.'):
    assert removed not in all_text, removed
assert new_doc[0].get_text().startswith('1. Base 2019-2024 - classificação dos modelos')
assert new_doc[-1].get_text().startswith('Períodos de treino, validação e teste')
report_path = WORK / 'revisao.verificacao.json'
report = json.loads(report_path.read_text(encoding='utf-8'))
report.update(trechos_destacados_removidos=True, corpos_das_oito_paginas_de_resultados_identicos=True,
              cronologia_preservada_ao_final=True, classificacoes_preservadas=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'remocoes_conferidas': True, 'paginas_resultados_preservadas': 8, 'paginas': 9}, ensure_ascii=False), flush=True)
