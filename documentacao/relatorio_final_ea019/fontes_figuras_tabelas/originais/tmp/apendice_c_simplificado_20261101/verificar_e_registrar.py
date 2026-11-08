from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from pypdf import PdfReader
from PIL import Image
from html import escape
import hashlib,json,re,unicodedata,sys

sys.stdout.reconfigure(encoding='utf-8')
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
DOCX=HERE/(NAME+'.docx')
PDF=HERE/'render-v1'/(NAME+'.pdf')
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W=NS['w'];plain=lambda p:''.join(p.xpath('.//w:t/text()',namespaces=NS))
sha=lambda b:hashlib.sha256(b).hexdigest()
normal=lambda s:''.join(c for c in unicodedata.normalize('NFKC',s).casefold() if c.isalnum())
with ZipFile(HERE/'antes.docx') as z:old=E.fromstring(z.read('word/document.xml'));old_parts={n:sha(z.read(n)) for n in z.namelist()}
with ZipFile(DOCX) as z:
    new=E.fromstring(z.read('word/document.xml'))
    assert set(z.namelist())==set(old_parts)
    changed_parts=[n for n,h in old_parts.items() if sha(z.read(n))!=h]
assert changed_parts==['word/document.xml']

def prefix(root):
    out=[]
    for p in root.xpath('//w:body//w:p',namespaces=NS):
        st=p.find('w:pPr/w:pStyle',NS)
        sid=st.get('{'+W+'}val','') if st is not None else ''
        if sid=='Ttulo1' and plain(p).startswith('APÊNDICE C'):break
        if not sid.startswith('TOC'):out.append(plain(p))
    return out
assert prefix(old)==prefix(new)
table_text=lambda r:[[plain(c) for c in t.findall('.//w:tc',NS)] for t in r.xpath('//w:tbl',namespaces=NS)]
assert table_text(old)==table_text(new) and len(table_text(new))==17
assert [E.tostring(x) for x in old.xpath('//m:oMath',namespaces=NS)]==[E.tostring(x) for x in new.xpath('//m:oMath',namespaces=NS)]
assert len(new.xpath('//m:oMath',namespaces=NS))==7
assert len(new.xpath('//w:drawing',namespaces=NS))==9
old_reader=PdfReader(HERE/'antes.pdf');new_reader=PdfReader(PDF)
assert len(old_reader.pages)==36 and len(new_reader.pages)==35
old_pages=[p.extract_text() or '' for p in old_reader.pages]
new_pages=[p.extract_text() or '' for p in new_reader.pages]

def where(text,pages):
    needle=normal(text)[:120]
    candidates=[i+1 for i,p in enumerate(pages) if i>=3 and needle in normal(p)]
    return candidates[0] if candidates else None

changes=json.loads((HERE/'alteracoes_completas.json').read_text(encoding='utf-8'))
for c in changes['changes']:
    c['page_before']=where(c['before'],old_pages)
    c['page_after']=where(c['after'],new_pages) if c['after'] else None
assert all(c['page_before'] in [34,35,36] for c in changes['changes'])
assert all(c['page_after'] in [34,35] for c in changes['changes'] if c['after'])

toc=[]
for p in new.xpath('//w:body//w:p',namespaces=NS):
    st=p.find('w:pPr/w:pStyle',NS)
    if st is None or not st.get('{'+W+'}val','').startswith('TOC'):continue
    texts=p.xpath('.//w:t/text()',namespaces=NS)
    label=''.join(texts[:-1]).strip();n=int(texts[-1])
    assert normal(label) in normal(new_pages[n-1]),(label,n)
    toc.append({'heading':label,'page':n})
assert len(toc)==38

# The user has already reviewed the preceding pages: prove their raster identity.
old_render=ROOT/'tmp/compactacao_layout_20261101/render-v2'
identical=[]
for n in range(1,34):
    if n==3:continue
    with Image.open(HERE/'render-v1'/f'page-{n}.png') as a,Image.open(old_render/f'page-{n}.png') as b:
        assert a.size==b.size and sha(a.convert('RGB').tobytes())==sha(b.convert('RGB').tobytes()),f'Página {n} mudou antes do apêndice.'
    identical.append(n)
report={'pages_before':36,'pages_after':35,'appendix_pages_before':[34,35,36],'appendix_pages_after':[34,35],
        'text_before_appendix_identical_except_contents':True,'pixel_identical_pages':identical,
        'contents_page_updated':3,'tables_unchanged':17,'equations_unchanged':7,'figures_unchanged':9,
        'references_unchanged':16,'changed_parts':changed_parts,'toc_checks':toc,
        'paragraphs_replaced':7,'paragraphs_removed':31,'changes':changes['changes'],
        'docx_sha256':sha(DOCX.read_bytes()),'pdf_sha256':sha(PDF.read_bytes()),'new_training':False}
(HERE/'verificacao_e_mapa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

rows=[]
for c in report['changes']:
    if c['action']!='replace':continue
    rows.append('<tr><td>'+str(c['page_before'])+' → '+str(c['page_after'])+'</td><td>'+escape(c['before'])+'</td><td>'+escape(c['after'])+'</td></tr>')
removed=[]
for c in report['changes']:
    if c['action']=='remove':removed.append('<li><strong>Página '+str(c['page_before'])+'</strong><p>'+escape(c['before'])+'</p></li>')
html='''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>Alterações no Apêndice C</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:1200px;margin:40px auto;padding:0 24px;color:#202124}h1,h2{line-height:1.2}table{border-collapse:collapse;width:100%;font-size:15px}th,td{border:1px solid #cbd0d5;padding:12px;text-align:left;vertical-align:top}th{background:#edf0f3}td,li{overflow-wrap:anywhere}td:first-child{width:80px}details{margin:24px 0}li{padding:8px}p{max-width:100ch}</style>
<h1>Alterações no Apêndice C</h1>
<p>A edição ficou restrita ao apêndice, que passou das páginas 34–36 para 34–35. As páginas 1–33 permanecem idênticas, com exceção do sumário na página 3, atualizado para refletir os títulos e a paginação.</p>
<p>Foram feitas sete substituições de parágrafos e 31 remoções. As 17 tabelas, sete equações, nove figuras e 16 referências foram preservadas. A descrição técnica do decoder e da destilação, a fonte da Tabela 17 e a fórmula de contagem de parâmetros permaneceram iguais.</p>
<h2>Todas as substituições</h2><table><thead><tr><th>Páginas antes → depois</th><th>Antes</th><th>Depois</th></tr></thead><tbody>'''+''.join(rows)+'''</tbody></table>
<h2>Blocos removidos</h2><ul><li>Diretórios e nomes de arquivos de resultados.</li><li>Lista de sete arquivos de auditoria com seus hashes.</li><li>Seção detalhada de verificação e referências a CSVs e séries locais.</li><li>Parágrafo de ambiente incorporado ao resumo da nova seção C.2.</li><li>Antiga seção C.4, com URL, commit, contratos de execução, arquivo de preservação e quatro nomes de código com seus hashes.</li></ul>
<details><summary>Ver os 31 parágrafos removidos, na íntegra</summary><ol>'''+''.join(removed)+'''</ol></details>
<h2>Sumário</h2><p>O título do Apêndice C foi atualizado; a antiga C.2 passou a C.1 e a antiga C.3 passou a C.2. As entradas da antiga verificação C.1 e da seção C.4 foram retiradas. Não houve outra alteração de texto antes do apêndice.</p></html>'''
(HERE/'alteracoes_completas.html').write_text(html,encoding='utf-8')
print(json.dumps({k:report[k] for k in ['pages_before','pages_after','appendix_pages_after','text_before_appendix_identical_except_contents','paragraphs_replaced','paragraphs_removed']},ensure_ascii=False))
