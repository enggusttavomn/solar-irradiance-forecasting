"""Apply the approved subtitle and verify cover-page layout and export."""
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
base = Path(__file__).resolve().parent
audit = base / 'ajuste_subtitulo'
target = base.parents[2] / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx'
old = 'Transformer, Informer e LSTM sob quantização das entradas'
new = 'Avaliação comparativa de Transformer, Informer e LSTM sob quantização das entradas'
lines = ['Avaliação comparativa de Transformer, Informer e LSTM', 'sob quantização das entradas']
sha = lambda data: hashlib.sha256(data).hexdigest()

if sys.argv[1] == 'edit':
    from docx import Document
    audit.mkdir(exist_ok=True)
    assert not (audit / 'antes.docx').exists()
    original = target.read_bytes()
    before = Document(BytesIO(original))
    assert [p.text for p in before.paragraphs if p.style.name == 'Subtitle'] == [old, old]
    with ZipFile(BytesIO(original)) as z:
        xml = z.read('word/document.xml')
        needle = ('<w:t>' + old + '</w:t>').encode()
        replacement = ('<w:t>' + lines[0] + '</w:t><w:br/><w:t>' + lines[1] + '</w:t>').encode()
        assert xml.count(needle) == 2
        updated_xml = xml.replace(needle, replacement)
        output = BytesIO()
        with ZipFile(output, 'w') as out:
            for item in z.infolist():
                out.writestr(item, updated_xml if item.filename == 'word/document.xml' else z.read(item.filename))
        updated = output.getvalue()
    after = Document(BytesIO(updated))
    assert [' '.join(p.text.split()) for p in after.paragraphs if p.style.name == 'Subtitle'] == [new, new]
    assert [p.text for p in before.paragraphs if p.style.name != 'Subtitle'] == [p.text for p in after.paragraphs if p.style.name != 'Subtitle']
    assert 'orientado pelo Prof. Dr. Gustavo Fraidenraich.' in '\n'.join(p.text for p in after.paragraphs)
    with ZipFile(BytesIO(original)) as a, ZipFile(BytesIO(updated)) as b:
        differences = [name for name in a.namelist() if a.read(name) != b.read(name)]
    assert differences == ['word/document.xml']
    (audit / 'antes.docx').write_bytes(original)
    (audit / 'antes.pdf').write_bytes(target.with_suffix('.pdf').read_bytes())
    target.write_bytes(updated)
    report = {'old': old, 'new': new, 'occurrences_updated': 2, 'line_break_before': 'sob quantização das entradas',
              'changed_package_parts': differences, 'before_docx_sha256': sha(original), 'after_docx_sha256': sha(updated)}
    (audit / 'edicao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

elif sys.argv[1] == 'publish':
    from pypdf import PdfReader, PdfWriter
    from PIL import Image, ImageChops
    from pdf2image import convert_from_path
    from docx import Document

    render = base / 'render-v7'
    source = render / target.with_suffix('.pdf').name
    reader = PdfReader(source)
    prior = PdfReader(audit / 'antes.pdf')
    assert len(reader.pages) == len(prior.pages) == 39
    changed_text = [i for i, (a, b) in enumerate(zip(prior.pages, reader.pages), 1)
                    if a.extract_text() != b.extract_text()]
    assert changed_text == [1, 2], changed_text
    assert all(new in ' '.join(reader.pages[i].extract_text().split()) for i in (0, 1))
    changed_visual = []
    for i in range(1, 40):
        with Image.open(base / 'render-v6' / f'page-{i}.png') as a, Image.open(render / f'page-{i}.png') as b:
            if a.size != b.size or ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox():
                changed_visual.append(i)
    assert changed_visual == [1, 2], changed_visual
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_metadata({key: prior.metadata[key] for key in ('/Title', '/Author', '/Subject', '/Keywords') if key in prior.metadata})
    pdf = target.with_suffix('.pdf')
    with pdf.open('wb') as f:
        writer.write(f)
    poppler = 'C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
    pages = convert_from_path(pdf, dpi=171, first_page=1, last_page=2, poppler_path=poppler)
    for i, actual in enumerate(pages, 1):
        with Image.open(render / f'page-{i}.png') as expected:
            assert actual.size == expected.size
            assert ImageChops.difference(actual.convert('RGB'), expected.convert('RGB')).getbbox() is None
    final = PdfReader(pdf)
    assert final.metadata.title == Document(target).core_properties.title
    report = {'pages': 39, 'text_changed_pages': changed_text, 'visually_changed_pages': changed_visual,
              'final_pdf_changed_pages_match_docx_render': True, 'docx_sha256': sha(target.read_bytes()), 'pdf_sha256': sha(pdf.read_bytes())}
    (audit / 'verificacao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
