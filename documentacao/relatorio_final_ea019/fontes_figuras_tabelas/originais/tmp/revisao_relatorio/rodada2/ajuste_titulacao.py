"""Correct the title-page advisor degree and verify the exported pair."""
from pathlib import Path
from zipfile import ZipFile
from io import BytesIO
import hashlib
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
base = Path(__file__).resolve().parent
audit = base / 'ajuste_titulacao'
audit.mkdir(exist_ok=True)
target = base.parents[2] / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx'
sha = lambda value: hashlib.sha256(value).hexdigest()
old = 'orientado pelo Prof. Gustavo Fraidenraich.'
new = 'orientado pelo Prof. Dr. Gustavo Fraidenraich.'

if sys.argv[1] == 'edit':
    original = target.read_bytes()
    with ZipFile(BytesIO(original)) as z:
        xml = z.read('word/document.xml')
        assert xml.count(old.encode()) == 1
        changed = xml.replace(old.encode(), new.encode())
        output = BytesIO()
        with ZipFile(output, 'w') as out:
            for item in z.infolist():
                out.writestr(item, changed if item.filename == 'word/document.xml' else z.read(item.filename))
        updated = output.getvalue()
    with ZipFile(BytesIO(original)) as a, ZipFile(BytesIO(updated)) as b:
        differences = [name for name in a.namelist() if a.read(name) != b.read(name)]
        assert differences == ['word/document.xml'], differences
    assert not (audit / 'antes.docx').exists()
    (audit / 'antes.docx').write_bytes(original)
    (audit / 'antes.pdf').write_bytes(target.with_suffix('.pdf').read_bytes())
    target.write_bytes(updated)
    report = {'before_docx_sha256': sha(original), 'after_docx_sha256': sha(updated),
              'changed_package_parts': differences, 'old': old, 'new': new}
    (audit / 'edicao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))

elif sys.argv[1] == 'publish':
    from pypdf import PdfReader, PdfWriter
    from PIL import Image, ImageChops
    from pdf2image import convert_from_path
    from docx import Document

    render = base / 'render-v6'
    source = render / target.with_suffix('.pdf').name
    reader = PdfReader(source)
    prior = PdfReader(audit / 'antes.pdf')
    assert len(reader.pages) == len(prior.pages) == 39
    changed_text = [i for i, (a, b) in enumerate(zip(prior.pages, reader.pages), 1)
                    if a.extract_text() != b.extract_text()]
    assert changed_text == [2], changed_text
    assert new in ' '.join(reader.pages[1].extract_text().split())
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    writer.add_metadata({key: prior.metadata[key] for key in ('/Title', '/Author', '/Subject', '/Keywords') if key in prior.metadata})
    pdf = target.with_suffix('.pdf')
    with pdf.open('wb') as f:
        writer.write(f)
    changed_visual = []
    for i in range(1, 40):
        with Image.open(base / 'render-v5' / f'page-{i}.png') as a, Image.open(render / f'page-{i}.png') as b:
            if a.size != b.size or ImageChops.difference(a.convert('RGB'), b.convert('RGB')).getbbox():
                changed_visual.append(i)
    assert changed_visual == [2], changed_visual
    poppler = 'C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
    rendered = convert_from_path(pdf, dpi=171, first_page=2, last_page=2, poppler_path=poppler)[0]
    with Image.open(render / 'page-2.png') as expected:
        assert rendered.size == expected.size
        assert ImageChops.difference(rendered.convert('RGB'), expected.convert('RGB')).getbbox() is None
    final = PdfReader(pdf)
    assert final.metadata.title == Document(target).core_properties.title
    report = {'pages': 39, 'text_changed_pages': changed_text, 'visually_changed_pages': changed_visual,
              'final_pdf_page_2_matches_docx_render': True, 'docx_sha256': sha(target.read_bytes()), 'pdf_sha256': sha(pdf.read_bytes())}
    (audit / 'verificacao.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
