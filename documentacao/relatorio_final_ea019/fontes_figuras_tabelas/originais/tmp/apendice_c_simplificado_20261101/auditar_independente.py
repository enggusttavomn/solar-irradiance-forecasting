from pathlib import Path
from io import BytesIO
from zipfile import ZipFile
from copy import deepcopy
from collections import Counter
from lxml import etree as E
import hashlib
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'antes.docx'
TARGET = HERE / 'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx'
NS = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W = NS['w']
q = lambda n: '{'+W+'}'+n
plain = lambda e: ''.join(e.xpath('.//w:t/text()', namespaces=NS))
sha = lambda b: hashlib.sha256(b).hexdigest()

def read(path):
    data = path.read_bytes()
    with ZipFile(BytesIO(data)) as z:
        parts = {name:z.read(name) for name in z.namelist()}
    return data, parts, E.fromstring(parts['word/document.xml'])

old_bytes, old_parts, old = read(SOURCE)
new_bytes, new_parts, new = read(TARGET)
log = json.loads((HERE/'alteracoes_completas.json').read_text(encoding='utf-8'))
old_ps = old.xpath('//w:body//w:p', namespaces=NS)
new_ps = new.xpath('//w:body//w:p', namespaces=NS)

def style(p):
    e = p.find('w:pPr/w:pStyle', NS)
    return e.get(q('val'), '') if e is not None else ''

is_toc = lambda p: style(p).upper().startswith('TOC')
def appendix_index(paragraphs):
    return next(i for i,p in enumerate(paragraphs)
                if plain(p).startswith('APÊNDICE C') and not is_toc(p))

old_start, new_start = appendix_index(old_ps), appendix_index(new_ps)
old_prefix = [plain(p) for p in old_ps[:old_start] if not is_toc(p)]
new_prefix = [plain(p) for p in new_ps[:new_start] if not is_toc(p)]
changes = log['changes']
replacement_map = {c['source_id']:c['after'] for c in changes if c['action']=='replace'}
removed_ids = {c['source_id'] for c in changes if c['action']=='remove'}
expected_sequence = [replacement_map.get(i,plain(p)) for i,p in enumerate(old_ps)
                     if i not in removed_ids and not is_toc(p)]
actual_sequence = [plain(p) for p in new_ps if not is_toc(p)]
manifest_before_matches = all(plain(old_ps[c['source_id']]) == c['before'] for c in changes)

def normalize(root):
    root = deepcopy(root)
    for p in list(root.xpath('//w:body//w:p', namespaces=NS)):
        if is_toc(p): p.getparent().remove(p)
    for el in root.iter():
        for attr in list(el.attrib):
            local = E.QName(attr).localname
            if local.startswith('rsid') or local in {'paraId','textId'}:
                del el.attrib[attr]
        if el.tag==q('bookmarkStart') and el.get(q('name'),'').startswith('_Toc'):
            el.set(q('name'),'_Toc')
    for el in list(root.xpath('//w:lastRenderedPageBreak', namespaces=NS)):
        el.getparent().remove(el)
    for el in list(root.xpath('//w:r[not(*)]', namespaces=NS)):
        el.getparent().remove(el)
    return root

old_norm, new_norm = normalize(old), normalize(new)
def prefix_xml(root):
    body = root.find('w:body',NS)
    result = []
    for node in body:
        if node.tag==q('p') and plain(node).startswith('APÊNDICE C'): break
        result.append(E.tostring(node,method='c14n'))
    return result

def table_cells(root):
    return [[[list(c.xpath('.//w:t/text()',namespaces=NS)) for c in row.findall('w:tc',NS)]
             for row in t.findall('w:tr',NS)]
            for t in root.xpath('//w:body/w:tbl',namespaces=NS)]

old_tables, new_tables = table_cells(old), table_cells(new)
old_eq = old.xpath('//w:body//m:oMath',namespaces=NS)
new_eq = new.xpath('//w:body//m:oMath',namespaces=NS)
equation_xml = lambda seq:[E.tostring(e,method='c14n') for e in seq]
drawings = lambda root:root.xpath('//w:body//w:drawing',namespaces=NS)
old_draw, new_draw = drawings(old), drawings(new)
refs = lambda seq:[plain(p) for p in seq if re.match(r'^\[\d+\]\s',plain(p))]
old_refs,new_refs = refs(old_ps),refs(new_ps)
changed_parts = [n for n in sorted(set(old_parts)|set(new_parts)) if old_parts.get(n)!=new_parts.get(n)]
media = [n for n in old_parts if n.startswith('word/media/')]
appendix_old_text = '\n'.join(plain(p) for p in old_ps[old_start:])
appendix_new_text = '\n'.join(plain(p) for p in new_ps[new_start:])
numbers = lambda s:set(re.findall(r'\d+(?:[.,]\d+)*',s))
footnote = next(c for c in changes if c['source_id']==1294)
footnote_tail_same = footnote['before'].split('. ',1)[1] == footnote['after'].split('. ',1)[1]
footnote_before_mentions_files = 'fontes executadas identificadas neste apêndice' in footnote['before']
footnote_after_removes_file_dependency = 'fontes executadas identificadas neste apêndice' not in footnote['after']
preserved = {str(i):{'text':plain(old_ps[i]),
                      'count_source':Counter(plain(p) for p in old_ps)[plain(old_ps[i])],
                      'count_target':Counter(plain(p) for p in new_ps)[plain(old_ps[i])]}
             for i in [1295,1317,1318]}
env_new = replacement_map[1320]
env_checks = {phrase:phrase in env_new for phrase in ['NumPy 2.4.4','pandas 3.0.3','PyTorch 2.12.0+cu126',
    'CUDA 12.6','mensais, CPU','NVIDIA GeForce GTX 1650 with Max-Q Design','cuDNN 91002',
    'Na LSTM, consta CUDA sem identificação da GPU','O modelo da CPU e a versão de Python não foram registrados',
    'sementes e regras de determinismo']}

checks = {
    'source_hash_matches_change_log':sha(old_bytes)==log['source_sha256'],
    'change_manifest_before_text_matches_source':manifest_before_matches,
    'exactly_7_replacements_31_removals_all_in_appendix_c':len(replacement_map)==7 and len(removed_ids)==31 and min(set(replacement_map)|removed_ids)>=old_start==1235,
    'text_before_appendix_c_identical_in_same_order_except_toc':old_prefix==new_prefix,
    'structure_before_appendix_c_identical_except_word_metadata_toc_and_page_caches':prefix_xml(old_norm)==prefix_xml(new_norm),
    'all_text_matches_exactly_approved_replacements_and_removals':expected_sequence==actual_sequence,
    'tables_17_all_text_and_numbers_identical':len(old_tables)==len(new_tables)==17 and old_tables==new_tables,
    'tables_17_structure_identical_except_word_metadata_and_page_caches':equation_xml(old_norm.xpath('//w:body/w:tbl',namespaces=NS))==equation_xml(new_norm.xpath('//w:body/w:tbl',namespaces=NS)),
    'native_equations_7_xml_and_text_identical':len(old_eq)==len(new_eq)==7 and equation_xml(old_eq)==equation_xml(new_eq),
    'figures_9_xml_identical_in_same_order':len(old_draw)==len(new_draw)==9 and equation_xml(old_draw)==equation_xml(new_draw),
    'all_image_payloads_identical':all(old_parts[n]==new_parts.get(n) for n in media),
    'references_16_identical_in_same_order':len(old_refs)==len(new_refs)==16 and old_refs==new_refs,
    'parts_outside_document_xml_identical':set(old_parts)==set(new_parts) and changed_parts==['word/document.xml'],
    'technical_paragraphs_1295_1317_1318_preserved':all(p['count_source']==p['count_target']==1 for p in preserved.values()),
    'table16_source_removes_file_list_dependency_preserves_all_caveats':footnote_before_mentions_files and footnote_after_removes_file_dependency and footnote_tail_same,
    'environment_retains_recorded_versions_devices_unknowns_and_reproduction_caveat':all(env_checks.values()),
    'no_new_numeric_values_in_appendix_c':numbers(appendix_new_text)<=numbers(appendix_old_text),
    'change_log_declares_no_new_training':log.get('new_training') is False
}
differences = [{'index_excluding_toc':i,'expected':a,'actual':b}
               for i,(a,b) in enumerate(zip(expected_sequence,actual_sequence)) if a!=b]
report = {'source':str(SOURCE),'target':str(TARGET),'source_sha256':sha(old_bytes),'target_sha256':sha(new_bytes),
          'passed':all(checks.values()),'checks':checks,
          'counts':{'source_paragraphs':len(old_ps),'target_paragraphs':len(new_ps),
                    'source_non_toc':len(expected_sequence)+len(removed_ids),'target_non_toc':len(actual_sequence),
                    'source_toc':sum(is_toc(p) for p in old_ps),'target_toc':sum(is_toc(p) for p in new_ps),
                    'tables':len(new_tables),'native_equations':len(new_eq),'figures':len(new_draw),
                    'image_parts':len(media),'references':len(new_refs)},
          'changed_package_parts':changed_parts,'unexpected_text_differences':differences,
          'preserved_technical_paragraphs':preserved,'environment_preservation_checks':env_checks,
          'table16_source_change':footnote,
          'new_numeric_values_in_appendix':sorted(numbers(appendix_new_text)-numbers(appendix_old_text)),
          'notes':['Auditoria independente somente leitura: nenhum DOCX foi editado ou renderizado.',
                   'Texto fora do Apêndice C comparado integralmente e em ordem, excluindo apenas o sumário atualizado.',
                   'Na análise estrutural são normalizados somente sumário e identificadores/caches voláteis do Word.']}
(HERE/'auditoria_independente.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'passed':report['passed'],'checks':checks,'counts':report['counts'],
                  'unexpected_text_differences':differences,'changed_package_parts':changed_parts},ensure_ascii=False))
