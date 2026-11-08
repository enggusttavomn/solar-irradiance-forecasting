from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
from copy import deepcopy
from lxml import etree as E
import hashlib
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
SOURCE = HERE/'antes.docx'
TARGET = HERE/'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx'
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W=NS['w']; q=lambda n:'{'+W+'}'+n
plain=lambda e:''.join(e.xpath('.//w:t/text()',namespaces=NS))
sha=lambda b:hashlib.sha256(b).hexdigest()

def read(path):
    data=path.read_bytes()
    with ZipFile(BytesIO(data)) as z:
        parts={name:z.read(name) for name in z.namelist()}
    return data,parts,E.fromstring(parts['word/document.xml'])

old_bytes,old_parts,old=read(SOURCE)
new_bytes,new_parts,new=read(TARGET)
content=json.loads((HERE/'conteudo.json').read_text(encoding='utf-8'))
changes=json.loads((HERE/'alteracoes.json').read_text(encoding='utf-8'))

def style(p):
    el=p.find('w:pPr/w:pStyle',NS)
    return el.get(q('val'),'') if el is not None else ''

is_toc=lambda p:style(p).upper().startswith('TOC')
old_body=old.find('w:body',NS);new_body=new.find('w:body',NS)
expected_additions=['',content['dedicatoria'],'','Agradecimentos',*content['agradecimentos'],'']
added_nodes=list(new_body)[29:36]
actual_additions=list(map(plain,added_nodes))
clean=deepcopy(new)
clean_body=clean.find('w:body',NS)
for node in list(clean_body)[29:36]: clean_body.remove(node)

paragraph_texts=lambda root:[plain(p) for p in root.xpath('//w:body//w:p',namespaces=NS) if not is_toc(p)]
old_texts=paragraph_texts(old);clean_texts=paragraph_texts(clean)

def normalize(root):
    root=deepcopy(root)
    for p in list(root.xpath('//w:body//w:p',namespaces=NS)):
        if is_toc(p):p.getparent().remove(p)
    for el in root.iter():
        for attr in list(el.attrib):
            name=E.QName(attr).localname
            if name.startswith('rsid') or name in {'paraId','textId'}:del el.attrib[attr]
        if el.tag==q('bookmarkStart') and el.get(q('name'),'').startswith('_Toc'):
            el.set(q('name'),'_Toc')
    for el in list(root.xpath('//w:lastRenderedPageBreak',namespaces=NS)):el.getparent().remove(el)
    for el in list(root.xpath('//w:r[not(*)]',namespaces=NS)):el.getparent().remove(el)
    return root

old_norm,clean_norm=normalize(old),normalize(clean)
c14n=lambda nodes:[E.tostring(x,method='c14n') for x in nodes]
table_text=lambda root:[[[list(c.xpath('.//w:t/text()',namespaces=NS)) for c in row.findall('w:tc',NS)]
                        for row in t.findall('w:tr',NS)] for t in root.xpath('//w:body/w:tbl',namespaces=NS)]
old_tables,new_tables=table_text(old),table_text(new)
old_eq,new_eq=[r.xpath('//w:body//m:oMath',namespaces=NS) for r in [old,new]]
old_fig,new_fig=[r.xpath('//w:body//w:drawing',namespaces=NS) for r in [old,new]]
refs=lambda root:[plain(p) for p in root.xpath('//w:body//w:p',namespaces=NS) if re.match(r'^\[\d+\]\s',plain(p))]
old_refs,new_refs=refs(old),refs(new)

def toc(root):
    rows=[]
    for p in root.xpath('//w:body//w:p',namespaces=NS):
        if not is_toc(p):continue
        text=plain(p)
        match=re.match(r'^(.*?)(\d+)$',text)
        rows.append({'label':match.group(1).strip(),'page':int(match.group(2))} if match else {'unparsed':text})
    return rows

old_toc,new_toc=toc(old),toc(new)
toc_labels_same=len(old_toc)==len(new_toc)==38 and all(a.get('label')==b.get('label') for a,b in zip(old_toc,new_toc))
toc_pages_plus_two=toc_labels_same and all(b.get('page',-999)==a.get('page',0)+2 for a,b in zip(old_toc,new_toc))
media=[n for n in old_parts if n.startswith('word/media/')]
changed_parts=[n for n in sorted(set(old_parts)|set(new_parts)) if old_parts.get(n)!=new_parts.get(n)]
names=['Gustavo Fraidenraich','Thales Wulfert Cabral']
old_body_text=' '.join(old_texts)
name_verification={n:n in old_body_text and any(n in t for t in content['agradecimentos']) for n in names}
added_styles=[style(p) for p in added_nodes]
style_root=E.fromstring(new_parts['word/styles.xml'])
default_style_nodes=style_root.xpath('//w:style[@w:type="paragraph"][@w:default="1"]',namespaces=NS)
default_style=default_style_nodes[0].get(q('styleId')) if len(default_style_nodes)==1 else None
effective_added_styles=[s or default_style for s in added_styles]
page_breaks=[bool(p.xpath('.//w:br[@w:type="page"]',namespaces=NS)) for p in added_nodes]
spacer_spacing=added_nodes[0].find('w:pPr/w:spacing',NS)
dedication_spacing=added_nodes[1].find('w:pPr/w:spacing',NS)
spacer_exact_250pt=spacer_spacing is not None and spacer_spacing.get(q('line'))=='5000' and spacer_spacing.get(q('lineRule'))=='exact'
dedication_before_zero=dedication_spacing is not None and dedication_spacing.get(q('before'),'0')=='0'

checks={
    'source_hash_matches_change_record':sha(old_bytes)==changes['source_sha256'],
    'user_preference_brief_general_text_recorded':content['user_preference']=='Escrever um texto breve e geral',
    'exactly_7_expected_paragraphs_added_before_summary':len(added_nodes)==7 and actual_additions==expected_additions and plain(new_body[36])=='SUMÁRIO' and plain(old_body[29])=='SUMÁRIO',
    'only_2_added_page_breaks_in_expected_positions':page_breaks==[False,False,True,False,False,False,True],
    'dedication_spacer_empty_exact_250pt_and_dedication_before_zero':plain(added_nodes[0])=='' and spacer_exact_250pt and dedication_before_zero,
    'remaining_non_toc_text_identical_in_same_order_after_removing_only_7_added_paragraphs':old_texts==clean_texts,
    'remaining_document_structure_identical_except_toc_and_word_metadata':E.tostring(old_norm,method='c14n')==E.tostring(clean_norm,method='c14n'),
    'tables_17_text_and_numbers_identical':len(old_tables)==len(new_tables)==17 and old_tables==new_tables,
    'tables_structure_preserved_except_word_metadata':c14n(old_norm.xpath('//w:body/w:tbl',namespaces=NS))==c14n(clean_norm.xpath('//w:body/w:tbl',namespaces=NS)),
    'native_equations_7_xml_identical':len(old_eq)==len(new_eq)==7 and c14n(old_eq)==c14n(new_eq),
    'figures_9_xml_identical_in_same_order':len(old_fig)==len(new_fig)==9 and c14n(old_fig)==c14n(new_fig),
    'references_16_identical_in_same_order':len(old_refs)==len(new_refs)==16 and old_refs==new_refs,
    'all_image_payloads_preserved':all(old_parts[n]==new_parts.get(n) for n in media),
    'all_parts_outside_document_xml_identical':set(old_parts)==set(new_parts) and changed_parts==['word/document.xml'],
    'toc_38_labels_identical_in_same_order':toc_labels_same,
    'every_toc_page_number_increased_by_2':toc_pages_plus_two,
    'dedication_and_acknowledgments_not_in_toc':not any('Agradecimentos' in r.get('label','') or content['dedicatoria'] in r.get('label','') for r in new_toc),
    'added_styles_are_normal_and_frontheading_without_heading1_or_heading2':effective_added_styles==['Normal','Normal','Normal','FrontHeading','Normal','Normal','Normal'],
    'mentor_names_match_existing_report':all(name_verification.values())
}
report={'source':str(SOURCE),'target':str(TARGET),'source_sha256':sha(old_bytes),'target_sha256':sha(new_bytes),
        'passed':all(checks.values()),'checks':checks,
        'counts':{'source_total_paragraphs':len(old.xpath('//w:body//w:p',namespaces=NS)),
                  'target_total_paragraphs':len(new.xpath('//w:body//w:p',namespaces=NS)),
                  'source_non_toc_paragraphs':len(old_texts),'target_non_toc_after_removing_additions':len(clean_texts),
                  'tables':len(new_tables),'equations':len(new_eq),'figures':len(new_fig),
                  'references':len(new_refs),'image_parts':len(media),'toc_entries':len(new_toc)},
        'added_texts':actual_additions,'added_styles':added_styles,'effective_added_styles':effective_added_styles,
        'default_paragraph_style':default_style,'mentor_name_verification':name_verification,
        'toc_source':old_toc,'toc_target':new_toc,'changed_package_parts':changed_parts,
        'personal_content_review':'Textos breves e gerais. A dedicatória não atribui apoio a familiares, crenças ou fatos privados. Os agradecimentos citam orientador e coorientador identificados no relatório e a comunidade acadêmica da instituição; não acrescentam nomes ou episódios pessoais específicos.',
        'notes':['Auditoria independente somente leitura: nenhum DOCX foi editado ou renderizado.',
                 'A prova estrutural remove apenas os 7 parágrafos acrescentados, o sumário e metadados/caches voláteis gerados pelo Word. O restante é idêntico.']}
(HERE/'auditoria_independente.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':checks,'counts':report['counts'],'changed_package_parts':changed_parts},ensure_ascii=False))
