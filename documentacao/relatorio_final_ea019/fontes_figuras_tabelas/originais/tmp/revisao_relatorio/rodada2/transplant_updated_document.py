"""Validate Word field refresh and transplant only document.xml into authored DOCX."""
from collections import Counter
from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import json
import os
import posixpath
import urllib.parse
import unicodedata
from lxml import etree as ET

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
NS = {'w': W}
WORKSPACE = Path('C:/Users/gusta/Downloads/1) EA019 - TCC').resolve()
TEMPLATE = Path('C:/Users/gusta/Downloads/Modelo Relatório Final - EA019.EA006.docx').resolve()


def relationship_map(package):
    result = {}
    for rel in ET.fromstring(package.read('word/_rels/document.xml.rels')):
        mode = rel.get('TargetMode', 'Internal')
        target = rel.attrib['Target']
        if mode != 'External':
            target = urllib.parse.unquote(target).replace('\\', '/')
            target = posixpath.normpath(target.lstrip('/') if target.startswith('/')
                                       else posixpath.join('word', target))
        result[rel.attrib['Id']] = (rel.attrib['Type'], mode, target)
    return result


def references(root, relationships):
    records = []
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.startswith('{' + R + '}'):
                if value not in relationships:
                    raise ValueError('Unresolved document relationship: ' + value)
                records.append((element.tag, key, value, relationships[value]))
    return records


def furniture(root, relationships):
    sections = []
    for section in root.findall('.//w:sectPr', NS):
        refs = []
        for child in section:
            if child.tag in ('{' + W + '}headerReference', '{' + W + '}footerReference'):
                rel_id = child.attrib['{' + R + '}id']
                refs.append((child.tag, child.get('{' + W + '}type', 'default'), relationships[rel_id]))
        sections.append(sorted(refs))
    return sections


def section_geometry(root):
    result = []
    for section in root.findall('.//w:sectPr', NS):
        size = section.find('w:pgSz', NS)
        margins = section.find('w:pgMar', NS)
        first = section.find('w:titlePg', NS)
        first_enabled = first is not None and first.get('{' + W + '}val', '1') not in ('0', 'false', 'off')
        result.append({'page_size': {key: size.get('{' + W + '}' + key, 'portrait' if key == 'orient' else '')
                                     for key in ('w', 'h', 'orient')},
                       'margins': {key: margins.get('{' + W + '}' + key, '0')
                                   for key in ('top', 'right', 'bottom', 'left', 'header', 'footer', 'gutter')},
                       'different_first_page': first_enabled})
    return result


def digest(data):
    return hashlib.sha256(data).hexdigest()


def remap_relationships(root, authored_package, refreshed_package, original_rels, updated_rels):
    mapping = {}
    for element in root.iter():
        for key, rel_id in list(element.attrib.items()):
            if not key.startswith('{' + R + '}'):
                continue
            target = updated_rels[rel_id]
            if target[0].rsplit('/', 1)[-1] == 'image' and target[1] != 'External':
                content_sha = digest(refreshed_package.read(target[2]))
                candidates = [old_id for old_id, old in original_rels.items()
                              if old[:2] == target[:2] and digest(authored_package.read(old[2])) == content_sha]
            else:
                candidates = [old_id for old_id, old in original_rels.items() if old == target]
            if len(candidates) != 1:
                raise ValueError('A refreshed relationship has no unambiguous authored equivalent: ' + rel_id)
            mapping[rel_id] = candidates[0]
            element.set(key, candidates[0])
    return mapping


def remap_styles(original_root, updated_root, authored_package, refreshed_package):
    def style_data(package):
        rows = {}
        for item in ET.fromstring(package.read('word/styles.xml')).findall('w:style', NS):
            name = item.find('w:name', NS)
            rows[item.get('{' + W + '}styleId')] = (item.get('{' + W + '}type'),
                                                   name.get('{' + W + '}val') if name is not None else '', item)
        return rows

    def normalized(value):
        value = unicodedata.normalize('NFKD', value).casefold()
        return ''.join(c for c in value if not unicodedata.combining(c) and not c.isspace())

    original_styles, refreshed_styles = style_data(authored_package), style_data(refreshed_package)
    paragraph_evidence = {}
    for paragraph in original_root.findall('.//w:p', NS):
        style = paragraph.find('w:pPr/w:pStyle', NS)
        text = ''.join(t.text or '' for t in paragraph.iter('{'+W+'}t'))
        if text and style is not None:
            paragraph_evidence.setdefault(text, set()).add(style.get('{' + W + '}val'))
    references_to_update = [e for tag in ('pStyle', 'rStyle', 'tblStyle')
                            for e in updated_root.findall('.//w:' + tag, NS)]
    needed = {e.get('{' + W + '}val') for e in references_to_update}
    mapping = {}
    for style_id in needed - set(original_styles):
        kind, name, definition = refreshed_styles[style_id]
        candidates = [sid for sid, (old_kind, old_name, _) in original_styles.items()
                      if old_kind == kind and normalized(old_name) == normalized(name)]
        method = 'normalized_display_name'
        support = 0
        if not candidates and kind == 'paragraph':
            votes = set()
            for paragraph in updated_root.findall('.//w:p', NS):
                style = paragraph.find('w:pPr/w:pStyle', NS)
                if style is None or style.get('{' + W + '}val') != style_id:
                    continue
                text = ''.join(t.text or '' for t in paragraph.iter('{'+W+'}t'))
                evidence = paragraph_evidence.get(text, set())
                if len(evidence) == 1:
                    votes.update(evidence)
                    support += 1
            candidates = list(votes)
            method = 'identical_paragraph_text_style_consensus'
        if len(candidates) != 1:
            raise ValueError('No unambiguous authored style equivalent for: ' + style_id)
        old_id = candidates[0]
        if original_styles[old_id][0] != kind:
            raise ValueError('Style type changed during Word refresh: ' + style_id)
        old_outline = original_styles[old_id][2].find('w:pPr/w:outlineLvl', NS)
        new_outline = definition.find('w:pPr/w:outlineLvl', NS)
        if old_outline is not None and new_outline is not None and old_outline.get('{' + W + '}val') != new_outline.get('{' + W + '}val'):
            raise ValueError('Heading outline level changed during Word refresh: ' + style_id)
        mapping[style_id] = {'authored_style': old_id, 'evidence': method, 'supporting_paragraphs': support}
    for element in references_to_update:
        style_id = element.get('{' + W + '}val')
        if style_id in mapping:
            element.set('{' + W + '}val', mapping[style_id]['authored_style'])
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--authored', required=True)
    parser.add_argument('--refreshed', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--audit', required=True)
    args = parser.parse_args()
    authored, refreshed, output, audit = [Path(p).resolve() for p in
                                         (args.authored, args.refreshed, args.output, args.audit)]
    if output == TEMPLATE or not output.is_relative_to(WORKSPACE) or output.suffix.lower() != '.docx':
        raise ValueError('Output must be a task DOCX inside the workspace, never the retained template.')
    report = {'authored': str(authored), 'refreshed': str(refreshed), 'output': str(output)}
    with ZipFile(authored) as before, ZipFile(refreshed) as after:
        original_xml, raw_updated_xml = before.read('word/document.xml'), after.read('word/document.xml')
        original_root, updated_root = ET.fromstring(original_xml), ET.fromstring(raw_updated_xml)
        original_rels, updated_rels = relationship_map(before), relationship_map(after)
        relationship_remap = remap_relationships(updated_root, before, after, original_rels, updated_rels)
        style_remap = remap_styles(original_root, updated_root, before, after)
        updated_xml = ET.tostring(updated_root, encoding='UTF-8', xml_declaration=True, standalone=True)
        before_refs, after_refs = references(original_root, original_rels), references(updated_root, original_rels)
        for _, _, rel_id, semantic_target in after_refs:
            if original_rels.get(rel_id) != semantic_target:
                raise ValueError('Word changed a relationship ID or target: ' + rel_id)
            if semantic_target[1] != 'External' and semantic_target[2] not in before.namelist():
                raise ValueError('Word references an unavailable authored package part: ' + semantic_target[2])
        semantic = lambda rows: Counter((tag, key, target) for tag, key, _, target in rows)
        if semantic(before_refs) != semantic(after_refs):
            raise ValueError('Relationship-backed document content changed during field refresh.')
        if furniture(original_root, original_rels) != furniture(updated_root, original_rels):
            raise ValueError('Header/footer relationships or section count changed during field refresh.')
        if section_geometry(original_root) != section_geometry(updated_root):
            raise ValueError('Page geometry or first-page header behavior changed during field refresh.')
        styles = ET.fromstring(before.read('word/styles.xml'))
        style_ids = {s.get('{' + W + '}styleId') for s in styles.findall('w:style', NS)}
        required_styles = {e.get('{' + W + '}val') for tag in ('pStyle', 'rStyle', 'tblStyle')
                           for e in updated_root.findall('.//w:' + tag, NS)}
        missing_styles = sorted(required_styles - style_ids)
        if missing_styles:
            raise ValueError('Predeclare these Word-generated styles before refreshing: ' + ', '.join(missing_styles))
        numbering = ET.fromstring(before.read('word/numbering.xml')) if 'word/numbering.xml' in before.namelist() else None
        num_ids = {'0'} | ({e.get('{' + W + '}numId') for e in numbering.findall('w:num', NS)}
                           if numbering is not None else set())
        required_nums = {e.get('{' + W + '}val') for e in updated_root.findall('.//w:numPr/w:numId', NS)}
        if required_nums - num_ids:
            raise ValueError('Word introduced numbering IDs absent from the authored package.')
        starts = Counter(e.get('{' + W + '}id') for e in updated_root.findall('.//w:bookmarkStart', NS))
        ends = Counter(e.get('{' + W + '}id') for e in updated_root.findall('.//w:bookmarkEnd', NS))
        if starts != ends:
            raise ValueError('Word field refresh produced unmatched bookmark boundaries.')
        original_parts = {i.filename: before.read(i.filename) for i in before.infolist()}
        changed_by_word = sorted(name for name, content in original_parts.items()
                                 if name not in after.namelist() or after.read(name) != content)
        temporary = output.with_suffix('.docx.fields.tmp')
        with ZipFile(temporary, 'w') as result:
            result.comment = before.comment
            for entry in before.infolist():
                result.writestr(entry, updated_xml if entry.filename == 'word/document.xml'
                                else original_parts[entry.filename])
    with ZipFile(temporary) as result:
        preserved = [name for name in original_parts if name != 'word/document.xml']
        if any(result.read(name) != original_parts[name] for name in preserved):
            raise ValueError('Preserve-only package content was changed during transplantation.')
        if set(result.namelist()) != set(original_parts):
            raise ValueError('Package inventory changed during transplantation.')
    os.replace(temporary, output)
    report.update(validated=True, transplanted_parts=['word/document.xml'],
                  preserved_parts=len(preserved), native_word_changed_parts=changed_by_word,
                  main_document_sha256_before=digest(original_xml),
                  main_document_sha256_after=digest(updated_xml),
                  word_generated_document_sha256=digest(raw_updated_xml),
                  output_sha256=digest(output.read_bytes()), section_count=len(furniture(updated_root, original_rels)),
                  relationship_references=len(after_refs), relationship_id_remap=relationship_remap,
                  style_id_remap=style_remap, referenced_style_ids=sorted(required_styles),
                  page_geometry=section_geometry(updated_root))
    audit.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'validated': True, 'preserved_parts': len(preserved), 'audit': str(audit)}, ensure_ascii=True))


if __name__ == '__main__':
    main()
