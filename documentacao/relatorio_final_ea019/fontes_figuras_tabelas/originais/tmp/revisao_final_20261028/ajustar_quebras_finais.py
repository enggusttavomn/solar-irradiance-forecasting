from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
import json

HERE=Path(__file__).resolve().parent/'compactacao'
P=HERE/'Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ns={'w':W}
with ZipFile(P) as z:
    info=z.infolist();parts={n:z.read(n) for n in z.namelist()}
root=E.fromstring(parts['word/document.xml']);body=root.find('w:body',ns)
changes=[]
for p in body.findall('w:p',ns):
    text=''.join(p.itertext()).strip()
    if text.startswith('Tabela 1 — Localidades'):
        props=p.find('w:pPr',ns)
        if props.find('w:pageBreakBefore',ns) is None:
            E.SubElement(props,'{'+W+'}pageBreakBefore')
        changes.append('Tabela 1 volta a iniciar na página seguinte, evitando uma única linha isolada abaixo do mapa.')
for i,t in enumerate(body.findall('w:tbl',ns),1):
    if i==10:
        margins=t.find('w:tblPr/w:tblCellMar',ns)
        for side in ['top','bottom']:
            margins.find('w:'+side,ns).set('{'+W+'}w','50')
        changes.append('Tabela 10: padding vertical de 70 para 50 twips para acomodar a fonte na mesma página.')
    last=t.findall('w:tr',ns)[-1]
    for p in last.findall('.//w:p',ns):
        props=p.find('w:pPr',ns)
        if props is None:props=E.SubElement(p,'{'+W+'}pPr')
        keep=props.find('w:keepNext',ns)
        if keep is None:keep=E.SubElement(props,'{'+W+'}keepNext')
        keep.set('{'+W+'}val','1')
changes.append('Última linha de cada tabela vinculada à nota de fonte seguinte, preservando cabeçalho repetido e linhas indivisíveis.')
parts['word/document.xml']=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(P,'w',ZIP_DEFLATED) as z:
    for member in info:z.writestr(member,parts[member.filename])
(HERE/'ajustes_v3.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(changes,ensure_ascii=False))
