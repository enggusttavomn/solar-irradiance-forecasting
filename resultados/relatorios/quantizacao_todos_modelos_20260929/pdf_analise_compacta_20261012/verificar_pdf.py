from pathlib import Path
from collections import Counter
import argparse
import json
import re

import pandas as pd
import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(ROOT))
from scripts.gerar_pdf_quantizacao_analise_compacta import AUDIT_DIRS, REGIMES, TAREFAS, MODELOS, VARIANTES, REL, fmt, condition, model_label, plain, digest

parser = argparse.ArgumentParser()
parser.add_argument('--pdf', required=True, type=Path)
parser.add_argument('--manifesto', required=True, type=Path)
args = parser.parse_args()
record = json.loads(args.manifesto.read_text(encoding='utf-8'))
assert digest(args.pdf) == record['pdf']['sha256']
frames, choices = {}, {}
for regime, folder in zip(REGIMES, AUDIT_DIRS, strict=True):
    audit = json.loads((REL / folder / 'auditoria.json').read_text(encoding='utf-8'))
    frame = pd.read_csv(audit['metricas']['path'])
    assert digest(audit['metricas']['path']) == audit['metricas']['sha256']
    frames[regime] = frame.loc[frame.particao == 'teste'].set_index(['tarefa', 'modelo', 'variante', 'horizonte'])
    choices[regime] = {(r['tarefa'], r['modelo']): r['vencedor_validacao'] for r in audit['resultados']}

coverage = set()
numeric_cells = 0
for cell in record['celulas_pdf']:
    key = cell['chave']
    if not key:
        continue
    if 'registro' in key:
        regime, task, model, variant, horizon = key['registro']
        metric = key['metrica']
        row = frames[regime].loc[(task, model, variant, horizon)]
        if metric == 'delta_quant_pct':
            base = frames[regime].loc[(task, model, 'sem_quantizacao', horizon), 'MAE_wm2']
            expected = fmt(100 * (row.MAE_wm2 - base) / base, 3, signed=True)
        else:
            expected = fmt(row[metric], 3 if metric == 'R2' else 4)
        if metric == 'MAE_wm2':
            coverage.add((regime, task, model, variant, horizon))
    else:
        task, model, variant = key['comparacao']
        horizon = max(TAREFAS[task])
        short = frames[REGIMES[2]].loc[(task, model, variant, horizon), 'MAE_wm2']
        long = frames[REGIMES[1]].loc[(task, model, variant, horizon), 'MAE_wm2']
        delta = long - short
        metric = key['metrica']
        value = {'MAE_curto': short, 'MAE_longo': long, 'delta': delta, 'delta_pct': 100 * delta / short}[metric]
        expected = fmt(value, 2 if metric == 'delta_pct' else 4, signed=metric in ('delta', 'delta_pct'))
        if metric in ('MAE_curto', 'MAE_longo'):
            regime = REGIMES[2] if metric == 'MAE_curto' else REGIMES[1]
            coverage.add((regime, task, model, variant, horizon))
    assert cell['texto'] == expected, (cell['pagina'], key, cell['texto'], expected)
    numeric_cells += 1

expected_coverage = {(r, t, m, v, max(hs)) for r in REGIMES for t, hs in TAREFAS.items() for m in MODELOS for v in VARIANTES}
assert coverage == expected_coverage and len(coverage) == 528

leaders = Counter()
rmse_changes = 0
def ranking(regime, task, horizon):
    frame = frames[regime].reset_index()
    selected = frame.loc[(frame.tarefa == task) & (frame.horizonte == horizon)]
    selected = selected.loc[[variant == choices[regime][task, model] for model, variant in selected[['modelo', 'variante']].itertuples(index=False, name=None)]]
    return selected.sort_values(['MAE_wm2', 'modelo'], kind='stable')
for regime in REGIMES:
    for task, hs in TAREFAS.items():
        rank = ranking(regime, task, max(hs))
        leaders[rank.iloc[0].modelo] += 1
        rmse_changes += int(rank.iloc[0].modelo != rank.sort_values(['RMSE_wm2', 'modelo']).iloc[0].modelo)
assert dict(leaders) == {'TimesNet': 6, 'Climatologia': 5, 'DilatedRNN': 1}
assert rmse_changes == 7

doc = pymupdf.open(args.pdf)
assert len(doc) == 10
assert len(doc.get_toc()) == 10
all_text = '\n'.join(page.get_text() for page in doc)
assert not re.search(r'\b(?:eu|nós|nosso|nossa|você|ChatGPT|assistente de IA)\b', all_text, flags=re.I)
normalize = lambda text: re.sub(r'\s+', '', text)
characters = []
for page in doc:
    chars = [char for block in page.get_text('rawdict')['blocks'] if block['type'] == 0
             for line in block['lines'] for span in line['spans'] for char in span['chars']]
    characters.append(chars)
    assert all(char['bbox'][0] >= 0 and char['bbox'][1] >= 0 and
               char['bbox'][2] <= page.rect.width + .1 and char['bbox'][3] <= page.rect.height + .1 for char in chars)

failures = []
for cell in record['celulas_pdf']:
    page_index = cell['pagina'] - 1
    x0, y0, x1, y1 = cell['rect']
    selected = [char['c'] for char in characters[page_index]
                if x0 < (char['bbox'][0] + char['bbox'][2]) / 2 < x1
                and y0 < (char['bbox'][1] + char['bbox'][3]) / 2 < y1]
    actual = ''.join(selected)
    if normalize(actual) != normalize(cell['texto']):
        failures.append({'pagina': cell['pagina'], 'esperado': cell['texto'], 'extraido': actual, 'rect': cell['rect']})

for index, page in enumerate(doc, 1):
    footer = page.get_text(clip=pymupdf.Rect(page.rect.width - 65, page.rect.height - 28, page.rect.width, page.rect.height))
    assert normalize(footer) == f'{index}/10'

horizon_cells = [cell for cell in record['celulas_pdf'] if cell['pagina'] == 10][4:]
assert len(horizon_cells) == 48
row_index = 0
for task, hs in TAREFAS.items():
    for horizon in hs:
        for col, regime in enumerate(REGIMES, 1):
            entries = [f'{pos}º {model_label(r.modelo)} ({condition(r.variante)}) | {fmt(r.MAE_wm2)}'
                       for pos, r in enumerate(ranking(regime, task, horizon).head(3).itertuples(), 1)]
            assert normalize(horizon_cells[row_index * 4 + col]['texto']) == normalize(' '.join(entries))
        row_index += 1

images_dir = args.pdf.parent / (args.pdf.stem + '_paginas')
images_dir.mkdir(exist_ok=True)
for index, page in enumerate(doc, 1):
    page.get_pixmap(matrix=pymupdf.Matrix(1.65, 1.65), alpha=False).save(images_dir / f'pagina_{index:02d}.png')
for start in range(1, 11, 2):
    sheet = Image.new('RGB', (1684, 596), '#CCD4DA')
    for offset in range(2):
        thumb = Image.open(images_dir / f'pagina_{start + offset:02d}.png').convert('RGB')
        thumb.thumbnail((842, 596))
        sheet.paste(thumb, (842 * offset, 0))
    sheet.save(images_dir / f'contato_{start:02d}_{start + 1:02d}.png')

report = {'pdf': str(args.pdf.resolve()), 'sha256': digest(args.pdf), 'paginas': len(doc),
          'celulas_verificadas': len(record['celulas_pdf']), 'celulas_numericas_conferidas_csv': numeric_cells,
          'MAEs_horizonte_completo_cobertos': len(coverage), 'rankings_horizontes_intermediarios': 36,
          'lideres': dict(leaders), 'mudancas_lider_por_RMSE': rmse_changes,
          'divergencias_extracao': failures, 'numeracao_correta': True, 'texto_impessoal': True,
          'fontes_preservadas': all(digest(path) == sha for path, sha in record['fontes_sha256'].items()),
          'originais_preservados': all(digest(path) == sha for path, sha in record['originais_sha256'].items()),
          'imagens': str(images_dir.resolve()), 'ok': not failures}
args.pdf.with_suffix('.verificacao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'divergencias_extracao'}, ensure_ascii=False), flush=True)
if failures:
    print(json.dumps(failures[:10], ensure_ascii=False), flush=True)
    raise SystemExit(1)
