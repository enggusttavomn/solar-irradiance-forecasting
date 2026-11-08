from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import hashlib,json,sys

sys.stdout.reconfigure(encoding='utf-8')
HERE=Path(__file__).resolve().parent
SOURCE=HERE/'antes.docx'
OUTPUT=HERE/'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS={'w':W,'m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
q=lambda n:'{'+W+'}'+n
plain=lambda p:''.join(p.xpath('.//w:t/text()',namespaces=NS))
sha=lambda b:hashlib.sha256(b).hexdigest()
inventory=json.loads((HERE/'inventario_fonte.json').read_text(encoding='utf-8'))
assert sha(SOURCE.read_bytes())==inventory['sha256']
content=json.loads((HERE/'conteudo.json').read_text(encoding='utf-8'))
assert content['user_preference']=='Escrever um texto breve e geral'
with ZipFile(SOURCE) as z:
    infos=z.infolist();parts={i.filename:z.read(i.filename) for i in infos}
root=E.fromstring(parts['word/document.xml'])
body=root.find('w:body',NS)
old_children=list(body)
old_xml=[E.tostring(x) for x in old_children]
toc_title=next(p for p in body.findall('w:p',NS) if plain(p)=='SUMÁRIO')
assert body.index(toc_title)==29
assert body[28].xpath('.//w:br[@w:type="page"]',namespaces=NS)

def paragraph(text,style='Normal',spacing=None,indent=None,align=None,size=None,keep=False):
    p=E.Element(q('p'));pp=E.SubElement(p,q('pPr'))
    E.SubElement(pp,q('pStyle')).set(q('val'),style)
    if keep:E.SubElement(pp,q('keepLines'))
    if spacing:
        node=E.SubElement(pp,q('spacing'))
        for k,v in spacing.items():node.set(q(k),str(v))
    if indent:
        node=E.SubElement(pp,q('ind'))
        for k,v in indent.items():node.set(q(k),str(v))
    if align:E.SubElement(pp,q('jc')).set(q('val'),align)
    if text:
        run=E.SubElement(p,q('r'))
        if size:
            rpr=E.SubElement(run,q('rPr'));E.SubElement(rpr,q('sz')).set(q('val'),str(size))
        E.SubElement(run,q('t')).text=text
    return p

def page_break():
    p=paragraph('',spacing={'before':0,'after':0,'line':240,'lineRule':'auto'},indent={'left':0,'right':0,'firstLine':0})
    E.SubElement(E.SubElement(p,q('r')),q('br')).set(q('type'),'page')
    return p

dedication_spacer=paragraph('',spacing={'before':0,'after':0,'line':5000,'lineRule':'exact'},
                            indent={'left':0,'right':0,'firstLine':0})
dedication=paragraph(content['dedicatoria'],spacing={'before':0,'after':0,'line':240,'lineRule':'auto'},
                     indent={'left':4522,'right':0,'firstLine':0},align='right',size=22,keep=True)
thanks_title=paragraph('Agradecimentos',style='FrontHeading')
new_nodes=[dedication_spacer,dedication,page_break(),thanks_title]
for text in content['agradecimentos']:
    new_nodes.append(paragraph(text,spacing={'before':0,'after':240,'line':360,'lineRule':'auto'},keep=True))
new_nodes.append(page_break())
start=body.index(toc_title)
for offset,p in enumerate(new_nodes):body.insert(start+offset,p)

# Existing elements are untouched; the added front matter is the only change.
assert [E.tostring(x) for x in old_children]==old_xml
assert len(root.xpath('//w:tbl',namespaces=NS))==17
assert len(root.xpath('//m:oMath',namespaces=NS))==7
assert len(root.xpath('//w:drawing',namespaces=NS))==9
parts['word/document.xml']=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUTPUT,'w') as z:
    for info in infos:z.writestr(info,parts[info.filename])
audit={'source_sha256':inventory['sha256'],'output':str(OUTPUT),'existing_elements_unchanged':True,
       'inserted_before':'SUMÁRIO','added_paragraphs':len(new_nodes),'added_pages_expected':2,
       'added_text':[content['dedicatoria'],'Agradecimentos']+content['agradecimentos'],
       'dedication_format':{'title':False,'font':'Times New Roman','size_pt':11,'left_indent_cm':7.98,'alignment':'right'},
       'acknowledgments_format':{'title_size_pt':14,'body_size_pt':12,'body_line_spacing':1.5},
       'body_text_changed':False,'tables_preserved':17,'equations_preserved':7,'figures_preserved':9,
       'output_sha256':sha(OUTPUT.read_bytes())}
(HERE/'alteracoes.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:audit[k] for k in ['output','existing_elements_unchanged','added_paragraphs','added_pages_expected','body_text_changed']},ensure_ascii=False))
