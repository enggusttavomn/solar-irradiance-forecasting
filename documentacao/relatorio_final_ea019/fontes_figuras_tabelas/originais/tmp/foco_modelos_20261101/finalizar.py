from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from pypdf import PdfReader
from PIL import Image
import hashlib
import json
import re
import shutil
import sys
import unicodedata

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FOLDER = ROOT / 'documentacao/relatorio_final_ea019'
SOURCE = FOLDER / 'Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Revisado.docx'
DOCX = FOLDER / 'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx'
RENDER = HERE / 'render-v2'
RENDERED_PDF = RENDER / DOCX.with_suffix('.pdf').name
PDF = DOCX.with_suffix('.pdf')
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
plain = lambda e: ''.join(e.xpath('.//w:t/text()', namespaces=NS))
sha = lambda b: hashlib.sha256(b).hexdigest()
normal = lambda s: re.sub(r'\W+', '', unicodedata.normalize('NFKC', s)).casefold()
inventory = json.loads((HERE / 'inventario_fonte.json').read_text(encoding='utf-8'))
assert sha(SOURCE.read_bytes()) == inventory['sha256']
with ZipFile(SOURCE) as z:
    source_root = E.fromstring(z.read('word/document.xml'))
with ZipFile(DOCX) as z:
    final_root = E.fromstring(z.read('word/document.xml'))
    changed_parts = [name for name, digest in inventory['parts'].items() if sha(z.read(name)) != digest]
    assert set(changed_parts) <= {'word/document.xml', 'docProps/core.xml'}
tables = lambda r: [[plain(c) for c in t.findall('.//w:tc', NS)] for t in r.xpath('//w:body/w:tbl', namespaces=NS)]
math = lambda r: [''.join(e.xpath('.//m:t/text()', namespaces=NS)) for e in r.xpath('//m:oMath', namespaces=NS)]
assert tables(source_root) == tables(final_root) and len(tables(final_root)) == 17
assert math(source_root) == math(final_root) and len(math(final_root)) == 7
assert len(final_root.xpath('//w:drawing', namespaces=NS)) == 9
paragraphs = final_root.xpath('//w:body//w:p', namespaces=NS)
figures = [int(re.match(r'^Figura (\d+)', plain(p)).group(1)) for p in paragraphs if re.match(r'^Figura \d+', plain(p))]
references = [int(re.match(r'^\[(\d+)\]', plain(p)).group(1)) for p in paragraphs if re.match(r'^\[\d+\]', plain(p))]
assert figures == list(range(1,10))
assert references == list(range(1,17))
reader = PdfReader(RENDERED_PDF)
pages_text = [p.extract_text() or '' for p in reader.pages]
toc_checks = []
for p in paragraphs:
    style = p.find('w:pPr/w:pStyle', NS)
    if style is None or not (style.get('{'+NS['w']+'}val') or '').startswith('TOC'):
        continue
    texts = p.xpath('.//w:t/text()', namespaces=NS)
    if not texts or not texts[-1].isdigit():
        continue
    label = ''.join(texts[:-1]).strip()
    number = int(texts[-1])
    assert 1 <= number <= len(reader.pages)
    present = normal(label) in normal(pages_text[number-1])
    toc_checks.append({'heading': label, 'page': number, 'present_on_page': present})
assert toc_checks and all(r['present_on_page'] for r in toc_checks), toc_checks
assert 'sob quantização das entradas' not in ' '.join(plain(p) for p in paragraphs[:30])
assert 'O problema central é comparar o desempenho' in ' '.join(plain(p) for p in paragraphs)
assert 'As escolhas permanecem no teste e horizontes menores' not in ' '.join(plain(p) for p in paragraphs)

# Map the final rendered pages to pages already inspected, ignoring the footer number.
old_dir = HERE / 'render-v1'
old_pages = {}
for path in old_dir.glob('page-*.png'):
    with Image.open(path) as im:
        rgb = im.convert('RGB')
        crop = rgb.crop((0,0,rgb.width,rgb.height-115))
        old_pages[int(path.stem.split('-')[-1])] = (crop.size, sha(crop.tobytes()))
page_map = []
for page in range(1,len(reader.pages)+1):
    path = RENDER / f'page-{page}.png'
    with Image.open(path) as im:
        rgb = im.convert('RGB')
        crop = rgb.crop((0,0,rgb.width,rgb.height-115))
        signature = (crop.size, sha(crop.tobytes()))
        matches = [n for n, old in old_pages.items() if old == signature]
        page_map.append({'page': page, 'matches_previous_body': matches, 'requires_new_visual_review': not bool(matches)})
shutil.copy2(RENDERED_PDF, PDF)
assert sha(PDF.read_bytes()) == sha(RENDERED_PDF.read_bytes())
audit = {'docx': str(DOCX), 'pdf': str(PDF), 'pages': len(reader.pages),
         'source_unchanged': True, 'tables_unchanged': 17, 'equations_unchanged': 7,
         'figures_preserved': 9, 'references_preserved': 16, 'changed_parts': changed_parts,
         'toc_checks': toc_checks, 'render_body_page_map': page_map,
         'new_visual_review_pages': [r['page'] for r in page_map if r['requires_new_visual_review']],
         'new_training': False, 'docx_sha256': sha(DOCX.read_bytes()), 'pdf_sha256': sha(PDF.read_bytes()),
         'pdf_identical_to_reviewed_render': True}
(HERE / 'verificacao_final.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: audit[k] for k in ['pages','source_unchanged','tables_unchanged','equations_unchanged','new_training','new_visual_review_pages','docx','pdf']}, ensure_ascii=False))
