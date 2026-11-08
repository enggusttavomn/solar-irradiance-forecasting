from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy
from datetime import datetime, timezone
from lxml import etree as E
import csv
import hashlib
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Revisado.docx'
OUTPUT = SOURCE.with_name('Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = {'w': W, 'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
q = lambda name: '{'+W+'}'+name
plain = lambda e: ''.join(e.xpath('.//w:t/text()', namespaces=NS))
sha = lambda b: hashlib.sha256(b).hexdigest()
inventory = json.loads((HERE / 'inventario_fonte.json').read_text(encoding='utf-8'))
assert sha(SOURCE.read_bytes()) == inventory['sha256'], 'A fonte retida mudou.'
with ZipFile(SOURCE) as z:
    infos = z.infolist()
    parts = {i.filename: z.read(i.filename) for i in infos}
root = E.fromstring(parts['word/document.xml'])
body = root.find('w:body', NS)
ps = root.xpath('//w:body//w:p', namespaces=NS)
assert len(ps) == 1334
tables = lambda r: [E.tostring(t) for t in r.xpath('//w:body/w:tbl', namespaces=NS)]
equations = lambda r: [E.tostring(t) for t in r.xpath('//m:oMath', namespaces=NS)]
before_tables = tables(root)
before_equations = equations(root)
changes = []

def set_text(p, text, reason):
    old = plain(p)
    if old == text:
        return
    assert not p.xpath('ancestor::w:tbl | .//w:drawing | .//m:oMath', namespaces=NS), old
    rpr = p.find('w:r/w:rPr', NS)
    rpr = deepcopy(rpr) if rpr is not None else None
    for child in list(p):
        if child.tag not in {q('pPr'), q('bookmarkStart'), q('bookmarkEnd')}:
            p.remove(child)
    run = E.Element(q('r'))
    if rpr is not None:
        run.append(rpr)
    E.SubElement(run, q('t')).text = text
    ends = p.findall('w:bookmarkEnd', NS)
    if ends:
        p.insert(p.index(ends[0]), run)
    else:
        p.append(run)
    changes.append({'source_id': ps.index(p) if p in ps else None, 'reason': reason, 'before': old, 'after': text})

all_replacements = {}
for filename in ['propostas_introducao.json', 'propostas_metodos.json', 'propostas_resultados.json']:
    for row in json.loads((HERE / filename).read_text(encoding='utf-8'))['replacements']:
        assert row['id'] not in all_replacements, f"Propostas duplicadas: {row['id']}"
        all_replacements[row['id']] = (row['text'], filename)
for row in json.loads((HERE / 'propostas_compactacao.json').read_text(encoding='utf-8'))['replacements']:
    all_replacements[row['id']] = (row['text'], 'compactacao_editorial')
for i, (text, reason) in sorted(all_replacements.items()):
    set_text(ps[i], text, reason)

# Explain the architectures and data before the auxiliary preprocessing question.
assert ps[80].getparent() is body and ps[82].getparent() is body
body.remove(ps[80])
body.insert(body.index(ps[82])+1, ps[80])

# Present model performance by horizon before the auxiliary quantization analysis.
start, end = body.index(ps[541]), body.index(ps[548])
horizon_block = list(body)[start:end]
for node in horizon_block:
    body.remove(node)
target = body.index(ps[440])
for offset, node in enumerate(horizon_block):
    body.insert(target+offset, node)
set_text(ps[541], '5.3 Comportamento nos horizontes cumulativos', 'ordem_resultados')
set_text(ps[440], '5.4 Quantização como análise de pré-processamento', 'ordem_resultados')

# Keep figure numbering in first-appearance order after moving the horizon section.
figure_map = {7: 8, 8: 7}
for p in root.xpath('//w:body//w:p', namespaces=NS):
    old = plain(p)
    new = re.sub(r'\bFigura ([78])\b', lambda m: 'Figura '+str(figure_map[int(m.group(1))]), old)
    if old != new:
        set_text(p, new, 'renumeracao_figuras')

# Renumber citations and reorder the same 16 references by their first appearance.
references = {}
for p in ps:
    match = re.match(r'^\[(\d+)\]\s+', plain(p))
    if match:
        references[int(match.group(1))] = p
assert set(references) == set(range(1, 17))
ref_nodes = set(references.values())
citation = re.compile(r'\[(\d+(?:\s*[,–-]\s*\d+)*)\]')

def parse_group(raw):
    values = []
    for part in raw.split(','):
        edges = re.split('[–-]', part.strip())
        if len(edges) == 1:
            values.append(int(edges[0]))
        elif len(edges) == 2:
            values.extend(range(int(edges[0]), int(edges[1])+1))
        else:
            return []
    return values if values and all(1 <= n <= 16 for n in values) else []

ordered = []
for p in root.xpath('//w:body//w:p', namespaces=NS):
    if p in ref_nodes:
        continue
    for match in citation.finditer(plain(p)):
        for n in parse_group(match.group(1)):
            if n not in ordered:
                ordered.append(n)
assert set(ordered) == set(range(1, 17)), ordered
citation_map = {old: new for new, old in enumerate(ordered, 1)}

def remap(match):
    values = parse_group(match.group(1))
    if not values:
        return match.group(0)
    return '['+','.join(map(str, sorted({citation_map[n] for n in values})))+']'

for p in root.xpath('//w:body//w:p', namespaces=NS):
    if p in ref_nodes:
        continue
    old = plain(p)
    new = citation.sub(remap, old)
    if old != new:
        set_text(p, new, 'renumeracao_citacoes')
for old, p in references.items():
    new = re.sub(r'^\[\d+\]', '['+str(citation_map[old])+']', plain(p))
    set_text(p, new, 'renumeracao_bibliografia')
for p in ref_nodes:
    body.remove(p)
ref_start = body.index(ps[640])+1
for offset, old in enumerate(ordered):
    body.insert(ref_start+offset, references[old])

# Preserve all numerical tables, equations and image payloads.
assert tables(root) == before_tables
assert equations(root) == before_equations
assert len(root.xpath('//w:body//w:p', namespaces=NS)) == 1334
assert len(root.xpath('//w:drawing', namespaces=NS)) == 9
assert [int(re.match(r'^Figura (\d+)', plain(p)).group(1)) for p in root.xpath('//w:body/w:p', namespaces=NS)
        if re.match(r'^Figura \d+', plain(p))] == list(range(1, 10))
assert len(before_tables) == 17 and len(before_equations) == 7
parts['word/document.xml'] = E.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)

core = E.fromstring(parts['docProps/core.xml'])
dc = 'http://purl.org/dc/elements/1.1/'
dcterms = 'http://purl.org/dc/terms/'
core.find('{'+dc+'}title').text = 'Previsão multirresolução de GHI com avaliação comparativa de Transformer, Informer e LSTM'
subject = core.find('{'+dc+'}subject')
if subject is not None:
    subject.text = 'Comparação de modelos na previsão de GHI; análises complementares de pré-processamento e histórico'
modified = core.find('{'+dcterms+'}modified')
if modified is not None:
    modified.text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
parts['docProps/core.xml'] = E.tostring(core, encoding='UTF-8', xml_declaration=True, standalone=True)
with ZipFile(OUTPUT, 'w') as z:
    for info in infos:
        z.writestr(info, parts[info.filename])
assert sha(SOURCE.read_bytes()) == inventory['sha256']
with ZipFile(OUTPUT) as z:
    changed_parts = [name for name, digest in inventory['parts'].items() if sha(z.read(name)) != digest]
assert set(changed_parts) <= {'word/document.xml', 'docProps/core.xml'}

# Cross-check the newly reported continuous values and rank stability from saved metrics.
metrics_path = ROOT / 'resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina/metricas_teste_modelos_disciplina.csv'
with metrics_path.open(encoding='utf-8-sig', newline='') as f:
    metrics = list(csv.DictReader(f))
rankings = []
for task, horizon in [('hourly_72_extension', 72), ('daily_30', 30), ('monthly_1', 1), ('monthly_6', 6)]:
    rows = [r for r in metrics if r['regime'] == 'atual' and r['tarefa'] == task and int(r['horizonte']) == horizon]
    control = sorted([r for r in rows if r['variante'] == 'sem_quantizacao'], key=lambda r: float(r['MAE_wm2']))
    selected = sorted([r for r in rows if r['selecionado'] == 'True'], key=lambda r: float(r['MAE_wm2']))
    assert len(control) == len(selected) == 3
    assert [r['modelo'] for r in control] == [r['modelo'] for r in selected]
    rankings.append({'task': task, 'horizon': horizon,
                     'continuous': [{k: r[k] for k in ['modelo','variante','MAE_wm2']} for r in control],
                     'selected': [{k: r[k] for k in ['modelo','variante','MAE_wm2']} for r in selected]})
audit = {'source': str(SOURCE), 'source_sha256': inventory['sha256'], 'output': str(OUTPUT),
         'source_unchanged': True, 'tables_unchanged': 17, 'equations_unchanged': 7,
         'figures_preserved': 9, 'references_preserved': 16, 'changed_parts': changed_parts,
         'citation_map': citation_map, 'changes': changes, 'rankings_verified': rankings,
         'metrics_source': str(metrics_path), 'metrics_sha256': sha(metrics_path.read_bytes()),
         'new_training': False, 'output_sha256': sha(OUTPUT.read_bytes())}
(HERE / 'alteracoes_e_verificacao.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
(HERE / 'texto_revisado.txt').write_text('\n'.join(plain(p) for p in root.xpath('//w:body/w:p', namespaces=NS)), encoding='utf-8')
print(json.dumps({k: audit[k] for k in ['output','source_unchanged','tables_unchanged','equations_unchanged','figures_preserved','references_preserved','new_training']}, ensure_ascii=False))
