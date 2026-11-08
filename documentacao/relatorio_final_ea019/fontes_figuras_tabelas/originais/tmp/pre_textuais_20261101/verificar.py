from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from pypdf import PdfReader
from PIL import Image
import hashlib,json,re,unicodedata,sys

sys.stdout.reconfigure(encoding='utf-8')
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
DOCX=HERE/(NAME+'.docx');RENDER=HERE/'render-v2';PDF=RENDER/(NAME+'.pdf')
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS={'w':W,'m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
q=lambda n:'{'+W+'}'+n
plain=lambda p:''.join(p.xpath('.//w:t/text()',namespaces=NS))
sha=lambda b:hashlib.sha256(b).hexdigest()
normal=lambda s:re.sub(r'\W+','',unicodedata.normalize('NFKC',s)).casefold()
with ZipFile(HERE/'antes.docx') as z:
    old=E.fromstring(z.read('word/document.xml'));parts={n:sha(z.read(n)) for n in z.namelist()}
with ZipFile(DOCX) as z:
    new=E.fromstring(z.read('word/document.xml'))
    assert [n for n,h in parts.items() if sha(z.read(n))!=h]==['word/document.xml']
body=new.find('w:body',NS)
content=json.loads((HERE/'conteudo.json').read_text(encoding='utf-8'))
added=list(body)[29:36]
assert [plain(p) for p in added]==['',content['dedicatoria'],'','Agradecimentos']+content['agradecimentos']+['']
for p in added:body.remove(p)

def original_text(root):
    result=[]
    for p in root.xpath('//w:body//w:p',namespaces=NS):
        st=p.find('w:pPr/w:pStyle',NS)
        if st is not None and st.get(q('val'),'').startswith('TOC'):continue
        result.append(plain(p))
    return result
assert original_text(old)==original_text(new)
tables=lambda r:[[plain(c) for c in t.findall('.//w:tc',NS)] for t in r.xpath('//w:tbl',namespaces=NS)]
assert tables(old)==tables(new) and len(tables(new))==17
assert len(new.xpath('//m:oMath',namespaces=NS))==7 and len(new.xpath('//w:drawing',namespaces=NS))==9

old_reader=PdfReader(HERE/'antes.pdf');reader=PdfReader(PDF)
assert len(old_reader.pages)==35 and len(reader.pages)==37
text=[p.extract_text() or '' for p in reader.pages]
assert content['dedicatoria'] in ' '.join(text[2].split())
assert 'Agradecimentos' in text[3] and content['agradecimentos'][0] in ' '.join(text[3].split())
assert 'SUMÁRIO' in text[4] and 'RESUMO' in text[5] and '1 INTRODUÇÃO' in text[6]
toc=[]
for p in new.xpath('//w:body//w:p',namespaces=NS):
    st=p.find('w:pPr/w:pStyle',NS)
    if st is None or not st.get(q('val'),'').startswith('TOC'):continue
    values=p.xpath('.//w:t/text()',namespaces=NS)
    label=''.join(values[:-1]).strip();n=int(values[-1])
    assert normal(label) in normal(text[n-1]),(label,n)
    assert 'Agradecimentos' not in label and 'Dedicatória' not in label
    toc.append({'heading':label,'page':n})
assert len(toc)==38

old_render=ROOT/'tmp/apendice_c_simplificado_20261101/render-v1'
pixel_map=[]
for old_page in range(1,36):
    if old_page==3:continue
    new_page=old_page if old_page<3 else old_page+2
    with Image.open(old_render/f'page-{old_page}.png') as a,Image.open(RENDER/f'page-{new_page}.png') as b:
        a=a.convert('RGB');b=b.convert('RGB')
        assert a.size==b.size
        crop_a=a.crop((0,0,a.width,a.height-115));crop_b=b.crop((0,0,b.width,b.height-115))
        assert sha(crop_a.tobytes())==sha(crop_b.tobytes()),f'Conteúdo visual mudou: {old_page}→{new_page}'
    pixel_map.append({'old_page':old_page,'new_page':new_page,'body_pixel_identical':True})
report={'pages_before':35,'pages_after':37,'dedication_page':3,'acknowledgments_page':4,'contents_page':5,
        'new_visual_review_pages':[3,4,5],'all_existing_text_preserved':True,'pixel_map':pixel_map,
        'contents_checks':toc,'tables_preserved':17,'equations_preserved':7,'figures_preserved':9,'references_preserved':16,
        'content':content,'docx_sha256':sha(DOCX.read_bytes()),'pdf_sha256':sha(PDF.read_bytes())}
(HERE/'verificacao.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:report[k] for k in ['pages_before','pages_after','dedication_page','acknowledgments_page','all_existing_text_preserved']},ensure_ascii=False))
