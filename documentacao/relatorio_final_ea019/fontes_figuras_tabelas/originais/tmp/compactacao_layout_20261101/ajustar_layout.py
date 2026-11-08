from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import hashlib,json,re,sys

sys.stdout.reconfigure(encoding='utf-8')
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'antes.docx'
OUT=HERE/'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx'
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','a':'http://schemas.openxmlformats.org/drawingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W=NS['w']
q=lambda n:'{'+W+'}'+n
plain=lambda p:''.join(p.xpath('.//w:t/text()',namespaces=NS))
sha=lambda b:hashlib.sha256(b).hexdigest()
with ZipFile(SOURCE) as z:
    infos=z.infolist();parts={i.filename:z.read(i.filename) for i in infos}
root=E.fromstring(parts['word/document.xml'])
before_text=root.xpath('//w:t/text()',namespaces=NS)
before_paragraph_text=[(p,plain(p)) for p in root.xpath('//w:body//w:p',namespaces=NS)]
before_tables=[E.tostring(t) for t in root.xpath('//w:tbl',namespaces=NS)]
before_math=[E.tostring(t) for t in root.xpath('//m:oMath',namespaces=NS)]
ps=root.xpath('//w:body/w:p',namespaces=NS)
changes=[]

def spacing(p,values,figure,role):
    pp=p.find('w:pPr',NS)
    if pp is None: pp=E.Element(q('pPr'));p.insert(0,pp)
    sp=pp.find('w:spacing',NS)
    if sp is None:sp=E.SubElement(pp,q('spacing'))
    old={k:sp.get(q(k)) for k in values}
    for k,v in values.items():sp.set(q(k),str(v))
    changes.append({'figure':figure,'role':role,'kind':'spacing','before':old,'after':values})

for number,scale in {4:0.95,6:0.90,7:0.90}.items():
    caption=next(p for p in ps if re.match(r'^Figura '+str(number)+r'\b',plain(p)))
    i=ps.index(caption)
    picture,source=ps[i+1:i+3]
    assert picture.xpath('.//w:drawing',namespaces=NS) and plain(source).startswith('Fonte:')
    spacing(caption,{'before':0,'after':20},number,'caption')
    spacing(picture,{'after':0},number,'picture')
    spacing(source,{'before':0,'after':60},number,'source')
    for extent in picture.xpath('.//wp:extent | .//a:xfrm/a:ext',namespaces=NS):
        old={k:int(extent.get(k)) for k in ['cx','cy']}
        new={k:round(v*scale) for k,v in old.items()}
        for k,v in new.items():extent.set(k,str(v))
        changes.append({'figure':number,'kind':'proportional_extent','node':E.QName(extent).localname,'scale':scale,'before':old,'after':new})

# Place the local comparison figure immediately after its section title.
# Prose paragraphs keep their original order, and every paragraph keeps its text.
body=root.find('w:body',NS)
section=next(p for p in ps if plain(p).startswith('5.2 Heterogeneidade')
             and p.find('w:pPr/w:pStyle',NS) is not None
             and p.find('w:pPr/w:pStyle',NS).get(q('val'))=='Heading2')
caption=next(p for p in ps if plain(p).startswith('Figura 6 '))
i=ps.index(caption)
assert i-ps.index(section)==2, 'A posição da seção deve ser o título real, não o sumário.'
group=ps[i:i+3]
assert all(p.getparent() is body for p in group)
for p in group:body.remove(p)
target=body.index(section)+1
for offset,p in enumerate(group):body.insert(target+offset,p)
changes.append({'figure':6,'kind':'position','after':'5.2 Heterogeneidade entre localidades','before':'A média macro atribui o mesmo peso às dez localidades'})

assert all(plain(p)==text for p,text in before_paragraph_text), 'Ajuste de layout alterou texto.'
assert sorted(root.xpath('//w:t/text()',namespaces=NS))==sorted(before_text)
assert [E.tostring(t) for t in root.xpath('//w:tbl',namespaces=NS)]==before_tables
assert [E.tostring(t) for t in root.xpath('//m:oMath',namespaces=NS)]==before_math
parts['word/document.xml']=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUT,'w') as z:
    for info in infos:z.writestr(info,parts[info.filename])
audit={'source_sha256':sha(SOURCE.read_bytes()),'output':str(OUT),'text_identical_before_field_update':True,
       'tables_unchanged':17,'equations_unchanged':7,'image_payloads_unchanged':True,'changes':changes}
(HERE/'ajustes_layout.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUT),'text_unchanged':True,'layout_changes':len(changes)},ensure_ascii=False))
