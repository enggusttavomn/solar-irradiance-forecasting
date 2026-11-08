from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from copy import deepcopy
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
with ZipFile(SOURCE) as z:
    infos=z.infolist();parts={i.filename:z.read(i.filename) for i in infos}
root=E.fromstring(parts['word/document.xml'])
ps=root.xpath('//w:body//w:p',namespaces=NS)
assert len(ps)==1334 and plain(ps[1235]).startswith('APÊNDICE C')
body=root.find('w:body',NS)
start=body.index(ps[1235])
before_prefix=[E.tostring(n) for n in list(body)[:start]]
before_tables=[E.tostring(t) for t in root.xpath('//w:tbl',namespaces=NS)]
before_equations=[E.tostring(t) for t in root.xpath('//m:oMath',namespaces=NS)]
proposal=json.loads((HERE/'proposta.json').read_text(encoding='utf-8'))
replacements={r['id']:r['text'] for r in proposal['replacements'] if r['id']!=1295}
replacements[1236]='Este apêndice resume as configurações das três implementações e o ambiente das execuções. Os resultados foram consolidados de experimentos já realizados, mantendo as escolhas na validação e o pareamento dos históricos.'
removals=set(proposal['remove_ids'])
assert min(set(replacements)|removals)>=1235
changes=[]

def set_text(p,text):
    assert not p.xpath('ancestor::w:tbl | .//w:drawing | .//m:oMath',namespaces=NS)
    rpr=p.find('w:r/w:rPr',NS)
    rpr=deepcopy(rpr) if rpr is not None else None
    for c in list(p):
        if c.tag not in {q('pPr'),q('bookmarkStart'),q('bookmarkEnd')}:p.remove(c)
    run=E.Element(q('r'))
    if rpr is not None:run.append(rpr)
    E.SubElement(run,q('t')).text=text
    ends=p.findall('w:bookmarkEnd',NS)
    if ends:p.insert(p.index(ends[0]),run)
    else:p.append(run)

for i,text in sorted(replacements.items()):
    old=plain(ps[i]);set_text(ps[i],text)
    changes.append({'source_id':i,'action':'replace','before':old,'after':text})
for i in sorted(removals):
    p=ps[i]
    assert p.getparent() is body and not p.xpath('.//w:drawing | .//m:oMath',namespaces=NS)
    changes.append({'source_id':i,'action':'remove','before':plain(p),'after':''})
    body.remove(p)

assert [E.tostring(n) for n in list(body)[:start]]==before_prefix
assert [E.tostring(t) for t in root.xpath('//w:tbl',namespaces=NS)]==before_tables
assert [E.tostring(t) for t in root.xpath('//m:oMath',namespaces=NS)]==before_equations
assert len(root.xpath('//w:drawing',namespaces=NS))==9
appendix_text=' '.join(plain(p) for p in list(body)[start:] if p.tag==q('p'))
for forbidden in ['SHA256','contrato_execucao.json','resultados/','codigo_fonte/','3abe546','fontes_antes_reorganizacao']:
    assert forbidden not in appendix_text
parts['word/document.xml']=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUTPUT,'w') as z:
    for info in infos:z.writestr(info,parts[info.filename])
result={'source':str(SOURCE),'output':str(OUTPUT),'source_sha256':sha(SOURCE.read_bytes()),
        'before_appendix_unchanged':True,'tables_unchanged':17,'equations_unchanged':7,
        'figures_preserved':9,'references_preserved':16,
        'paragraphs_replaced':len(replacements),'paragraphs_removed':len(removals),
        'changes':changes,'preserved_technical_paragraph_ids':[1295,1317,1318],
        'new_training':False,'output_sha256':sha(OUTPUT.read_bytes())}
(HERE/'alteracoes_completas.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'apendice_c_depois.txt').write_text('\n\n'.join(plain(p) for p in list(body)[start:] if p.tag==q('p')),encoding='utf-8')
print(json.dumps({k:result[k] for k in ['output','before_appendix_unchanged','paragraphs_replaced','paragraphs_removed','tables_unchanged']},ensure_ascii=False))
