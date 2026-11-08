from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from copy import deepcopy
from io import BytesIO
import hashlib
import json
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
BEFORE = HERE / 'antes.docx'
AFTER = HERE / 'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.docx'
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
      'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math',
      'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
sha = lambda b: hashlib.sha256(b).hexdigest()
plain = lambda e: ''.join(e.xpath('.//w:t/text()', namespaces=NS))

def read(path):
    package_bytes = path.read_bytes()
    with ZipFile(BytesIO(package_bytes)) as z:
        parts = {name: z.read(name) for name in z.namelist()}
    return parts, E.fromstring(parts['word/document.xml']), package_bytes

old_parts, old, old_package_bytes = read(BEFORE)
new_parts, new, new_package_bytes = read(AFTER)

def style(p):
    el = p.find('w:pPr/w:pStyle', NS)
    return el.get('{'+NS['w']+'}val', '') if el is not None else ''

is_toc = lambda p: style(p).upper().startswith('TOC')
paragraphs = lambda root: [p for p in root.xpath('//w:body//w:p', namespaces=NS) if not is_toc(p)]
old_ps, new_ps = paragraphs(old), paragraphs(new)
old_text, new_text = list(map(plain, old_ps)), list(map(plain, new_ps))
text_differences = [{'index_excluding_toc': i, 'before': a, 'after': b}
                    for i, (a, b) in enumerate(zip(old_text, new_text)) if a != b]
if len(old_text) != len(new_text):
    text_differences.append({'paragraph_count_before': len(old_text), 'paragraph_count_after': len(new_text)})

FIGURE6_CAPTION = 'Figura 6 — Desempenho por localidade nas quatro tarefas'

def figure6_group(root):
    body = root.find('w:body', NS)
    captions = [p for p in body.findall('w:p', NS) if plain(p) == FIGURE6_CAPTION]
    headings = [p for p in body.findall('w:p', NS)
                if style(p) == 'Heading2' and plain(p) == '5.2 Heterogeneidade entre localidades']
    if len(captions) != 1 or len(headings) != 1:
        return None
    cap = captions[0]
    drawing = cap.getnext()
    source = drawing.getnext() if drawing is not None else None
    if drawing is None or source is None or not drawing.xpath('.//w:drawing', namespaces=NS):
        return None
    if not plain(source).startswith('Fonte: elaboração própria. Métricas locais de teste com seleção fixa pela validação.'):
        return None
    return {'body': body, 'heading': headings[0], 'caption': cap, 'drawing': drawing, 'source': source}

old_group, new_group = figure6_group(old), figure6_group(new)
figure6_texts = {plain(old_group['caption']), plain(old_group['source'])} if old_group else set()
old_prose = [t for t in old_text if t.strip() and t not in figure6_texts]
new_prose = [t for t in new_text if t.strip() and t not in figure6_texts]
figure6_position_valid = bool(new_group and
    new_group['heading'].getnext() is new_group['caption'] and
    plain(new_group['source'].getnext()).startswith('A média macro atribui o mesmo peso às dez localidades'))

def tables(root):
    return [[[list(cell.xpath('.//w:t/text()', namespaces=NS))
              for cell in row.findall('w:tc', NS)]
             for row in table.findall('w:tr', NS)]
            for table in root.xpath('//w:body/w:tbl', namespaces=NS)]

def equations(root):
    return [{'text': ''.join(eq.xpath('.//m:t/text()', namespaces=NS)),
             'xml': E.tostring(eq, method='c14n').decode('utf-8')}
            for eq in root.xpath('//w:body//m:oMath', namespaces=NS)]

def drawings(root):
    result = []
    for index, d in enumerate(root.xpath('//w:body//w:drawing', namespaces=NS), 1):
        extents = d.xpath('.//wp:extent | .//a:xfrm/a:ext', namespaces=NS)
        result.append({'index': index,
                       'embeds': d.xpath('.//a:blip/@r:embed', namespaces=NS),
                       'extents': [{'type': E.QName(e).localname,
                                    'cx': int(e.get('cx')), 'cy': int(e.get('cy'))}
                                   for e in extents]})
    return result

old_tables, new_tables = tables(old), tables(new)
old_eq, new_eq = equations(old), equations(new)
old_d, new_d = drawings(old), drawings(new)
refs = lambda root: [plain(p) for p in paragraphs(root) if re.match(r'^\[\d+\]\s', plain(p))]
old_refs, new_refs = refs(old), refs(new)

part_names_equal = set(old_parts) == set(new_parts)
changed_parts = [name for name in sorted(set(old_parts) | set(new_parts))
                 if old_parts.get(name) != new_parts.get(name)]
changed_outside = [name for name in changed_parts if name != 'word/document.xml']
media_names = sorted(name for name in old_parts if name.startswith('word/media/'))
media_equal = all(old_parts[name] == new_parts.get(name) for name in media_names)

extent_changes = []
extent_issues = []
for a, b in zip(old_d, new_d):
    index = a['index']
    if a['extents'] != b['extents']:
        expected = {4: 0.95, 6: 0.9, 7: 0.9}.get(index)
        entry = {'drawing': index, 'before': a['extents'], 'after': b['extents'], 'expected_scale': expected}
        extent_changes.append(entry)
        if expected is None or len(a['extents']) != len(b['extents']):
            extent_issues.append(entry)
        else:
            for e_old, e_new in zip(a['extents'], b['extents']):
                for dimension in ['cx', 'cy']:
                    if abs(e_new[dimension] - round(e_old[dimension] * expected)) > 1:
                        extent_issues.append({'drawing': index, 'dimension': dimension,
                                              'before': e_old[dimension], 'after': e_new[dimension],
                                              'expected_scale': expected})

def normalize_allowed_changes(root):
    root = deepcopy(root)
    for p in list(root.xpath('//w:body//w:p', namespaces=NS)):
        if is_toc(p):
            p.getparent().remove(p)
    for spacing in list(root.xpath('//w:spacing', namespaces=NS)):
        spacing.getparent().remove(spacing)
    group = figure6_group(root)
    if group:
        body = group['body']
        target = body.index(group['heading']) + 1
        for node in [group['caption'], group['drawing'], group['source']]:
            body.remove(node)
        for offset, node in enumerate([group['caption'], group['drawing'], group['source']]):
            body.insert(target + offset, node)
    for index, d in enumerate(root.xpath('//w:body//w:drawing', namespaces=NS), 1):
        if index in {4, 6, 7}:
            for extent in d.xpath('.//wp:extent | .//a:xfrm/a:ext', namespaces=NS):
                extent.set('cx', '0')
                extent.set('cy', '0')
    return E.tostring(root, method='c14n')

norm_old, norm_new = normalize_allowed_changes(old), normalize_allowed_changes(new)
structural_equal = norm_old == norm_new

def normalize_word_refresh_metadata(data):
    root = E.fromstring(data)
    removed_attributes = 0
    for el in root.iter():
        for attr in list(el.attrib):
            local = E.QName(attr).localname
            if local.startswith('rsid') or local in {'paraId', 'textId'}:
                del el.attrib[attr]
                removed_attributes += 1
        if E.QName(el).localname == 'bookmarkStart' and el.get('{'+NS['w']+'}name', '').startswith('_Toc'):
            el.set('{'+NS['w']+'}name', '_Toc')
    page_break_caches = root.xpath('//w:lastRenderedPageBreak', namespaces=NS)
    for el in page_break_caches:
        el.getparent().remove(el)
    empty_runs = root.xpath('//w:r[not(*)]', namespaces=NS)
    for el in empty_runs:
        el.getparent().remove(el)
    return E.tostring(root, method='c14n'), {'volatile_attributes': removed_attributes,
                                           'page_break_caches': len(page_break_caches),
                                           'empty_runs': len(empty_runs)}

metadata_old, metadata_old_stats = normalize_word_refresh_metadata(norm_old)
metadata_new, metadata_new_stats = normalize_word_refresh_metadata(norm_new)
structural_equal_after_word_metadata = metadata_old == metadata_new
old_toc = [plain(p) for p in old.xpath('//w:body//w:p', namespaces=NS) if is_toc(p)]
new_toc = [plain(p) for p in new.xpath('//w:body//w:p', namespaces=NS) if is_toc(p)]

checks = {
    'all_paragraph_text_outside_toc_identical_multiset': Counter(old_text) == Counter(new_text),
    'nonempty_prose_order_identical_excluding_only_figure6_caption_source_and_toc': old_prose == new_prose,
    'figure6_group_immediately_after_real_heading2_before_first_prose_paragraph': figure6_position_valid,
    'tables_17_identical_text_and_numbers': len(old_tables) == len(new_tables) == 17 and old_tables == new_tables,
    'native_equations_7_same_text': len(old_eq) == len(new_eq) == 7 and [x['text'] for x in old_eq] == [x['text'] for x in new_eq],
    'native_equations_xml_identical': old_eq == new_eq,
    'body_drawings_9_same_relationships': len(old_d) == len(new_d) == 9 and [x['embeds'] for x in old_d] == [x['embeds'] for x in new_d],
    'all_image_payloads_identical': media_equal,
    'references_16_intact_in_same_order': len(old_refs) == len(new_refs) == 16 and old_refs == new_refs,
    'package_part_names_identical': part_names_equal,
    'parts_outside_document_xml_identical': not changed_outside,
    'extent_changes_only_permitted_figures_and_scales': not extent_issues and {x['drawing'] for x in extent_changes} == {4, 6, 7},
    'document_xml_identical_except_spacing_allowed_extents_figure6_position_toc_and_word_refresh_metadata': structural_equal_after_word_metadata
}
report = {'before': str(BEFORE), 'after': str(AFTER),
          'sha256_before': sha(old_package_bytes), 'sha256_after': sha(new_package_bytes),
          'passed': all(checks.values()), 'checks': checks,
          'counts': {'paragraphs_excluding_toc': [len(old_ps), len(new_ps)],
                     'toc_paragraphs': [len(old_toc), len(new_toc)],
                     'tables': [len(old_tables), len(new_tables)],
                     'native_equations': [len(old_eq), len(new_eq)],
                     'body_drawings': [len(old_d), len(new_d)], 'image_parts': len(media_names),
                     'references': [len(old_refs), len(new_refs)]},
          'text_differences': text_differences, 'changed_parts': changed_parts,
          'text_order_notes': {'full_order_identical': old_text == new_text,
                               'allowed_repositioned_texts': sorted(figure6_texts),
                               'prose_paragraphs_excluding_repositioned_figure6_texts': [len(old_prose), len(new_prose)],
                               'unmatched_paragraph_text_before': list((Counter(old_text) - Counter(new_text)).elements()),
                               'unmatched_paragraph_text_after': list((Counter(new_text) - Counter(old_text)).elements())},
          'changed_parts_outside_document_xml': changed_outside,
          'extent_changes': extent_changes, 'extent_issues': extent_issues,
          'raw_xml_equal_after_only_requested_changes_normalized': structural_equal,
          'word_refresh_metadata': {'before': metadata_old_stats, 'after': metadata_new_stats,
                                    'normalizations': ['w:rsid*', 'w14:paraId', 'w14:textId',
                                                       'generated _Toc bookmark names',
                                                       'w:lastRenderedPageBreak cache',
                                                       'empty runs after removing cache'],
                                    'remaining_structural_differences': not structural_equal_after_word_metadata},
          'toc_before': old_toc, 'toc_after': new_toc,
          'notes': ['Auditoria independente somente leitura das duas versões; nenhum DOCX foi editado, treinado ou renderizado.',
                    'O reposicionamento autorizado do grupo da Figura 6 para depois do Heading2 real da Seção 5.2 é verificado separadamente. Seu conteúdo e o multiconjunto integral dos textos são preservados; a ordem restante da prosa é idêntica.',
                    'Além dos ajustes de diagramação autorizados, o Word renovou identificadores internos e caches de paginação. Esses metadados não mudam o conteúdo. A verificação estrutural normaliza somente essas alterações explícitas.']}
if not structural_equal:
    (HERE / 'auditoria_normalizada_antes.xml').write_bytes(norm_old)
    (HERE / 'auditoria_normalizada_depois.xml').write_bytes(norm_new)
(HERE / 'auditoria_texto_independente.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'checks': checks, 'counts': report['counts'],
                  'text_differences_count_due_to_repositioning': len(text_differences), 'changed_parts': changed_parts,
                  'extent_issues': extent_issues}, ensure_ascii=False))
