from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import hashlib,json,shutil,sys

sys.stdout.reconfigure(encoding='utf-8')
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
SOURCE=ROOT/'documentacao/relatorio_final_ea019'/(NAME+'.docx')
for ext in ['.docx','.pdf']:
    backup=HERE/('antes'+ext)
    if not backup.exists():shutil.copy2(SOURCE.with_suffix(ext),backup)
NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
with ZipFile(HERE/'antes.docx') as z:
    root=E.fromstring(z.read('word/document.xml'))
    inventory={'sha256':hashlib.sha256((HERE/'antes.docx').read_bytes()).hexdigest(),
               'parts':{n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()},
               'paragraphs':[''.join(p.xpath('.//w:t/text()',namespaces=NS)) for p in root.xpath('//w:body//w:p',namespaces=NS)]}
(HERE/'inventario_fonte.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'backup':str(HERE/'antes.docx'),'sha256':inventory['sha256'],'paragraphs':len(inventory['paragraphs'])}))
