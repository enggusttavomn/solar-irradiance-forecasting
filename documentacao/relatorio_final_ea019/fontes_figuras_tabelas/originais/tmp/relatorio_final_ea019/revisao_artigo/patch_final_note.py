from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree
import json,hashlib
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
F=ROOT/'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'
with ZipFile(F) as z:parts={n:z.read(n) for n in z.namelist()}
before={n:hashlib.sha256(b).hexdigest() for n,b in parts.items()}
old='Estrela indica escolha na validação quando a variante escolhida é quantizada.'
new='Estrela identifica a condição escolhida na validação; contorno destaca escolhas quantizadas.'
r=etree.fromstring(parts['word/document.xml'])
found=0
for el in r.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t'):
    if el.text and old in el.text:
        el.text=el.text.replace(old,new);found+=1
assert found==1
parts['word/document.xml']=etree.tostring(r,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(F,'w',ZIP_DEFLATED) as z:
    for n,b in parts.items():z.writestr(n,b)
changed=[n for n,b in parts.items() if before[n]!=hashlib.sha256(b).hexdigest()]
assert changed==['word/document.xml']
(HERE/'legend_patch.json').write_text(json.dumps({'old':old,'new':new,'changed_parts':changed},ensure_ascii=False,indent=2),encoding='utf-8')
