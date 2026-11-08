from pathlib import Path
from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
from pypdf import PdfReader
import argparse,hashlib,json,os,shutil

parser=argparse.ArgumentParser();parser.add_argument('--publish',action='store_true');args=parser.parse_args()
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent/'compactacao'
NAME='Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado'
STAGING=HERE/(NAME+'.docx')
NEWPDF=HERE/'render-v3'/(NAME+'.pdf')
DEST=ROOT/'documentacao/relatorio_final_ea019'/(NAME+'.docx')
OUT=ROOT/'resultados/relatorios/revisao_final_20261028'
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
ns={'w':W,'m':M,'wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def parts(p):
    with ZipFile(p) as z:return {n:z.read(n) for n in z.namelist()}
old=parts(HERE/'antes_compactacao.docx');new=parts(STAGING)
x=E.fromstring(old['word/document.xml']);y=E.fromstring(new['word/document.xml'])
def prose(t):
    result=[]
    for p in t.findall('.//w:p',ns):
        if any(h.get('{'+W+'}anchor','').startswith('_Toc') for h in p.findall('.//w:hyperlink',ns)):continue
        text=''.join(p.itertext()).strip()
        if text:result.append(text)
    return result
def table_text(t):
    return [[[''.join(c.itertext()) for c in row.findall('w:tc',ns)] for row in table.findall('w:tr',ns)] for table in t.findall('.//w:body/w:tbl',ns)]
def tree_value(t):
    return (t.tag,tuple(sorted(t.attrib.items())),t.text or '',tuple(tree_value(c) for c in t))
assert prose(x)==prose(y),'Non-TOC text changed'
assert table_text(x)==table_text(y),'Table content changed'
assert [tree_value(q) for q in x.findall('.//m:oMath',ns)]==[tree_value(q) for q in y.findall('.//m:oMath',ns)],'Equation changed'
assert len(y.findall('.//w:body/w:tbl',ns))==15
assert len(y.findall('.//wp:inline',ns))==13
assert len(y.findall('.//m:oMath',ns))==7
assert set(old)==set(new)
changed=[k for k in old if old[k]!=new[k]]
assert set(changed)<= {'word/document.xml','word/styles.xml','docProps/app.xml'},changed
before_section=x.find('.//w:sectPr',ns);after_section=y.find('.//w:sectPr',ns)
assert [tree_value(q) for q in before_section]==[tree_value(q) for q in after_section]
assert {k:v for k,v in before_section.attrib.items() if 'rsid' not in k}=={k:v for k,v in after_section.attrib.items() if 'rsid' not in k}
assert [tree_value(q) for q in E.fromstring(old['word/styles.xml']).findall('.//w:rPr',ns)]==[tree_value(q) for q in E.fromstring(new['word/styles.xml']).findall('.//w:rPr',ns)]
toc=json.loads((HERE/'toc_final.json').read_text(encoding='utf-8'))
assert toc['pdf_pages']==36 and toc['toc_entries']==37 and toc['matched']==37 and not toc['mismatches']
assert len(PdfReader(NEWPDF).pages)==36
assert digest(DEST)==digest(HERE/'antes_compactacao.docx'),'Source DOCX changed while working'
assert digest(DEST.with_suffix('.pdf'))==digest(HERE/'antes_compactacao.pdf'),'Source PDF changed while working'

report={'verified':True,'published':False,'pages_before':37,'pages_after':36,'text_preserved':True,'nonempty_paragraphs_outside_toc':len(prose(y)),
    'tables':15,'figures':13,'native_equations':7,'all_table_content_preserved':True,'all_equations_preserved':True,
    'fonts_preserved':True,'page_geometry_preserved':True,'changed_package_parts':changed,'toc_entries_verified':37,
    'before_docx_sha256':digest(DEST),'before_pdf_sha256':digest(DEST.with_suffix('.pdf')),'staging_docx_sha256':digest(STAGING),'new_pdf_sha256':digest(NEWPDF)}
if args.publish:
    qa=[HERE/f'qa_paginas{a}_{b}.txt' for a,b in [(1,12),(13,24),(25,36)]]
    assert all(p.is_file() for p in qa),'Visual QA incomplete'
    # Metadata only: the rendered layout remains unchanged.
    app=E.fromstring(new['docProps/app.xml'])
    ep='http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
    app.find('{'+ep+'}Pages').text='36'
    new['docProps/app.xml']=E.tostring(app,encoding='UTF-8',xml_declaration=True,standalone=True)
    with ZipFile(STAGING,'w',ZIP_DEFLATED) as z:
        for n,b in new.items():z.writestr(n,b)
    backupdir=OUT/'antes_compactacao';backupdir.mkdir(exist_ok=True)
    for ext in ['.docx','.pdf']:
        backup=backupdir/(NAME+ext)
        if backup.exists():assert digest(backup)==digest(DEST.with_suffix(ext))
        else:shutil.copyfile(DEST.with_suffix(ext),backup)
    for source,destination in [(STAGING,DEST),(NEWPDF,DEST.with_suffix('.pdf'))]:
        assert ROOT in destination.resolve().parents
        swap=destination.with_name(destination.name+'.swap')
        shutil.copyfile(source,swap)
        os.replace(swap,destination)
    report.update(published=True,docx_sha256=digest(DEST),pdf_sha256=digest(DEST.with_suffix('.pdf')),
        visual_qa_pages=36,visual_qa_records=[p.name for p in qa],backup_directory=str(backupdir.relative_to(ROOT)),
        changed_package_parts=[k for k in old if old[k]!=new[k]])
    for p in qa:shutil.copyfile(p,OUT/p.name)
    shutil.copyfile(HERE/'toc_final.json',OUT/'sumario_apos_compactacao.json')
    (OUT/'compactacao_verificada.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'finalizacao.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
