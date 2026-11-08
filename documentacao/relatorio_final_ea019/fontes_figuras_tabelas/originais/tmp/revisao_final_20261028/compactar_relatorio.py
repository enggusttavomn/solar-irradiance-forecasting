from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORK=HERE/'compactacao'
WORK.mkdir(exist_ok=True)
SOURCE=ROOT/'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'
BACKUP=WORK/'antes_compactacao.docx'
if not BACKUP.exists():
    shutil.copyfile(SOURCE,BACKUP)
    shutil.copyfile(SOURCE.with_suffix('.pdf'),WORK/'antes_compactacao.pdf')
OUT=WORK/SOURCE.name
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
ns={'w':W}
with ZipFile(BACKUP) as z:
    info=z.infolist()
    parts={n:z.read(n) for n in z.namelist()}
x=E.fromstring(parts['word/document.xml'])
styles=E.fromstring(parts['word/styles.xml'])
body=x.find('w:body',ns)
changes=[]
for index,p in enumerate(list(body)):
    if p.tag!='{'+W+'}p':continue
    text=''.join(p.itertext()).strip()
    props=p.find('w:pPr',ns)
    style=None if props is None else props.find('w:pStyle',ns)
    style_id='' if style is None else style.get('{'+W+'}val')
    if style_id=='Heading2' and props.find('w:pageBreakBefore',ns) is not None:
        props.remove(props.find('w:pageBreakBefore',ns))
        changes.append({'kind':'remove_subsection_page_break','body_index':index,'text':text})
    brs=[b for b in p.findall('.//w:br',ns) if b.get('{'+W+'}type')=='page']
    if index>97 and brs and not text and p.find('.//w:drawing',ns) is None and p.find('.//w:fldChar',ns) is None:
        body.remove(p)
        changes.append({'kind':'remove_internal_manual_page_break','body_index':index})
for table_index,t in enumerate(body.findall('w:tbl',ns),1):
    margins=t.find('w:tblPr/w:tblCellMar',ns)
    if margins is not None:
        for side in ['top','bottom']:
            e=margins.find('w:'+side,ns)
            if e is not None and int(e.get('{'+W+'}w','0'))>70:
                before=e.get('{'+W+'}w')
                e.set('{'+W+'}w','70')
                changes.append({'kind':'table_vertical_padding','table':table_index,'side':side,'before_twips':before,'after_twips':70})
for style in styles.findall('w:style',ns):
    name=style.find('w:name',ns)
    display='' if name is None else name.get('{'+W+'}val')
    if display not in ['Fonte','caption','Caption','Legenda']:continue
    spacing=style.find('w:pPr/w:spacing',ns)
    if spacing is None:continue
    new={'after':100} if display=='Fonte' else {'before':80,'after':60}
    for key,val in new.items():
        old=spacing.get('{'+W+'}'+key)
        if old is not None and int(old)>val:
            spacing.set('{'+W+'}'+key,str(val))
            changes.append({'kind':'caption_or_source_spacing','style':display,'property':key,'before_twips':old,'after_twips':val})
parts['word/document.xml']=E.tostring(x,encoding='UTF-8',xml_declaration=True,standalone=True)
parts['word/styles.xml']=E.tostring(styles,encoding='UTF-8',xml_declaration=True,standalone=True)
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
    for member in info:z.writestr(member,parts[member.filename])
(WORK/'ajustes_v1.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'output':str(OUT),'layout_changes':len(changes),'source_backup_sha256':hashlib.sha256(BACKUP.read_bytes()).hexdigest(),'removed_page_breaks':sum('page_break' in c['kind'] for c in changes)},ensure_ascii=False))
