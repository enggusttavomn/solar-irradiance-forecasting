from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from docx import Document
from docx.shared import Pt,Cm,RGBColor
import json,shutil,hashlib

HERE=Path(__file__).resolve().parent
TMP=HERE.parent
ROOT=TMP.parents[1]
F=ROOT/'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'
PDF=F.with_suffix('.pdf')
for path in [F,PDF]:
    backup=HERE/('antes_ajuste'+path.suffix)
    if not backup.exists():shutil.copy2(path,backup)
with ZipFile(F) as z:before={n:z.read(n) for n in z.namelist()}
doc=Document(F)
titles=[p for p in doc.paragraphs if p.style.name=='Title']
subs=[p for p in doc.paragraphs if p.style.name=='Subtitle']
assert len(titles)==len(subs)==2
title='Previsão multirresolução de irradiância global horizontal em localidades associadas à fabricação de veículos elétricos'
subtitle='Transformer Informer e LSTM sob quantização das entradas'
for p in titles:
    assert not p._p.xpath('.//w:bookmarkStart')
    p.text=title
    p.paragraph_format.left_indent=Cm(1)
    p.paragraph_format.right_indent=Cm(1)
    p.paragraph_format.space_before=Pt(0)
    p.paragraph_format.space_after=Pt(10)
    p.paragraph_format.line_spacing=1.05
    p.paragraph_format.keep_with_next=True
    for run in p.runs:
        run.font.name='Times New Roman'
        run.font.size=Pt(16.5)
        run.font.bold=True
        run.font.color.rgb=RGBColor(0,0,0)
for p in subs:
    assert not p._p.xpath('.//w:bookmarkStart')
    p.text=subtitle
    p.paragraph_format.space_before=Pt(0)
    p.paragraph_format.space_after=Pt(8)
    for run in p.runs:
        run.font.name='Times New Roman'
        run.font.size=Pt(13)
        run.font.bold=False
        run.font.color.rgb=RGBColor(0,0,0)

ps=doc.paragraphs
title_indices=[i for i,p in enumerate(ps) if p.style.name=='Title']
assert ps[title_indices[0]-1].text==''
ps[title_indices[0]-1].paragraph_format.space_after=Cm(1.9)
video_index=next(i for i,p in enumerate(ps) if p.text.startswith('Link do vídeo:'))
assert ps[video_index+1].text==''
ps[video_index+1].paragraph_format.space_after=Cm(4.4)
sub2=next(i for i,p in enumerate(ps) if p._p is subs[1]._p)
assert ps[sub2+1].text==''
ps[sub2+1].paragraph_format.space_after=Cm(.8)

working=HERE/'authoring.docx'
doc.save(working)
with ZipFile(working) as z:authored={n:z.read(n) for n in z.namelist()}
# Only front-page text and paragraph properties are changed. The rest of the
# package, including all field caches, headers, images and styles, is preserved.
after=dict(before)
after['word/document.xml']=authored['word/document.xml']
with ZipFile(F,'w',ZIP_DEFLATED) as z:
    for n,b in after.items():z.writestr(n,b)
assert all(before[n]==after[n] for n in before if n!='word/document.xml')

# Keep the retained builder consistent with this presentation-only change.
prepare=TMP/'revisao_completa/prepare_complete.py'
source=prepare.read_text(encoding='utf-8')
old="title='PREVISÃO MULTIRRESOLUÇÃO DE\\\\nIRRADIÂNCIA GLOBAL HORIZONTAL\\\\nEM LOCALIDADES ASSOCIADAS À FABRICAÇÃO\\\\nDE VEÍCULOS ELÉTRICOS'"
new='title='+repr(title)
assert source.count(old)==1
source=source.replace(old,new)
old="subtitle='Transformer Informer e LSTM sob\\\\nquantização das entradas'"
assert source.count(old)==1
source=source.replace(old,'subtitle='+repr(subtitle))
old="p('RA 239679','Frente')\\nspacer(1.3)"
assert source.count(old)==1
source=source.replace(old,"p('RA 239679','Frente')\\nspacer(1.9)")
source=source.replace('change("spacer(4.6)","spacer(3.0)")','change("spacer(4.6)","spacer(4.4)")')
style_patch='''
change("configure('Title',18,True,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)","configure('Title',16.5,True,WD_ALIGN_PARAGRAPH.CENTER,0,10,0)\\nstyles['Title'].paragraph_format.left_indent=Cm(1)\\nstyles['Title'].paragraph_format.right_indent=Cm(1)\\nstyles['Title'].paragraph_format.line_spacing=1.05")
change("configure('Subtitle',14,False,WD_ALIGN_PARAGRAPH.CENTER,0,14,0)","configure('Subtitle',13,False,WD_ALIGN_PARAGRAPH.CENTER,0,8,0)")
change("spacer(1.2)\\nz=p('Relatório final", "spacer(.8)\\nz=p('Relatório final")
'''
anchor="# Link the existing figures to the reasoning without adding redundant sections."
assert source.count(anchor)==1
source=source.replace(anchor,style_patch+'\n'+anchor)
prepare.write_text(source,encoding='utf-8')
(HERE/'formatting_audit.json').write_text(json.dumps({'title':title,'subtitle':subtitle,'title_font_pt':16.5,'title_width_cm':15,'subtitle_font_pt':13,'manual_line_breaks_removed':True,'changed_parts':['word/document.xml'],'before_docx_sha256':hashlib.sha256((HERE/'antes_ajuste.docx').read_bytes()).hexdigest(),'after_docx_sha256':hashlib.sha256(F.read_bytes()).hexdigest()},ensure_ascii=False,indent=2),encoding='utf-8')
print('Capa e folha de rosto ajustadas; demais partes preservadas.')
