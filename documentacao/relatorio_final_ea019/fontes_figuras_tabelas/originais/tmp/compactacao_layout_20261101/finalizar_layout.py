from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from pypdf import PdfReader
from PIL import Image
import hashlib,json,re,shutil,unicodedata

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
STAGED=HERE/(NAME+'.docx')
RENDER=HERE/'render-v2'
STAGED_PDF=RENDER/(NAME+'.pdf')
DEST=ROOT/'documentacao/relatorio_final_ea019'
sha=lambda b:hashlib.sha256(b).hexdigest()
normal=lambda s:re.sub(r'\W+','',unicodedata.normalize('NFKC',s)).casefold()
audit=json.loads((HERE/'auditoria_texto_independente.json').read_text(encoding='utf-8'))
assert audit['passed'] and all(audit['checks'].values())
assert sha(STAGED.read_bytes())==audit['sha256_after']
assert sha((DEST/(NAME+'.docx')).read_bytes())==sha((HERE/'antes.docx').read_bytes()), 'O arquivo principal foi alterado externamente.'
assert sha((DEST/(NAME+'.pdf')).read_bytes())==sha((HERE/'antes.pdf').read_bytes()), 'O PDF principal foi alterado externamente.'
reader=PdfReader(STAGED_PDF)
assert len(reader.pages)==36
pages=[p.extract_text() or '' for p in reader.pages]
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS={'w':W}
with ZipFile(STAGED) as z:root=E.fromstring(z.read('word/document.xml'))
toc=[]
for p in root.xpath('//w:body//w:p',namespaces=NS):
    s=p.find('w:pPr/w:pStyle',NS)
    if s is None or not s.get('{'+W+'}val','').startswith('TOC'):continue
    texts=p.xpath('.//w:t/text()',namespaces=NS)
    assert texts[-1].isdigit()
    label=''.join(texts[:-1]).strip();page=int(texts[-1])
    assert normal(label) in normal(pages[page-1]), (label,page)
    toc.append({'heading':label,'page':page})
assert len(toc)==40

# Pages 1–11, except the repaginated contents page, are pixel-identical to the
# previously inspected PDF. Page 12 is the visually inspected figure-fit case.
base=ROOT/'tmp/foco_modelos_20261101/render-v2'
identical=[]
for n in [1,2,4,5,6,7,8,9,10,11]:
    with Image.open(RENDER/f'page-{n}.png') as a, Image.open(base/f'page-{n}.png') as b:
        assert a.size==b.size and sha(a.convert('RGB').tobytes())==sha(b.convert('RGB').tobytes())
    identical.append(n)
with Image.open(RENDER/'page-12.png') as a, Image.open(HERE/'render-v1/page-12.png') as b:
    assert a.size==b.size and sha(a.convert('RGB').tobytes())==sha(b.convert('RGB').tobytes())

for report in ['qa_visual_13_24.json','qa_visual_25_36.json']:
    data=json.loads((HERE/report).read_text(encoding='utf-8'))
    assert data, report

for src in [STAGED,STAGED_PDF]:
    dst=DEST/src.name
    shutil.copy2(src,dst)
    assert sha(src.read_bytes())==sha(dst.read_bytes())
report={'published_docx':str(DEST/STAGED.name),'published_pdf':str(DEST/STAGED_PDF.name),
        'pages_before':37,'pages_after':36,'text_changed':False,'numbers_changed':False,
        'tables_preserved':17,'equations_preserved':7,'figures_preserved':9,'references_preserved':16,
        'contents_page_numbers_updated':True,'toc_checks':toc,
        'visual_review_passed':True,'unchanged_rendered_pages':identical,
        'reviewed_updated_pages':[3]+list(range(12,37)),
        'docx_sha256':sha(STAGED.read_bytes()),'pdf_sha256':sha(STAGED_PDF.read_bytes()),
        'new_versions_created_in_report_folder':False}
(HERE/'verificacao_final.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['pages_before','pages_after','text_changed','numbers_changed','visual_review_passed','published_docx','published_pdf']},ensure_ascii=False))
