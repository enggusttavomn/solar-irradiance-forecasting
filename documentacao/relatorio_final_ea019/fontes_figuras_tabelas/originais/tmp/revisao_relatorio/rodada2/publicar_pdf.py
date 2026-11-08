"""Set final PDF properties and prove equivalence to the reviewed rendering."""
from pathlib import Path
from pypdf import PdfReader, PdfWriter
from pdf2image import convert_from_path
from PIL import Image, ImageChops
from docx import Document
import json
import hashlib
import sys

sys.stdout.reconfigure(encoding='utf-8')
h = Path(__file__).resolve().parent
target = h.parents[2] / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.pdf'
source = h / 'render-v5' / target.name
reader = PdfReader(source)
writer = PdfWriter()
writer.clone_document_from_reader(reader)
doc = Document(target.with_suffix('.docx'))
writer.add_metadata({'/Title': doc.core_properties.title, '/Author': doc.core_properties.author,
                     '/Subject': 'TCC de Engenharia Elétrica — previsão multirresolução de GHI com Transformer, Informer e LSTM',
                     '/Keywords': 'GHI, NSRDB, Transformer, Informer, LSTM, quantização de entradas'})
with target.open('wb') as f:
    writer.write(f)
final = PdfReader(target)
assert final.metadata.title == doc.core_properties.title and final.metadata.author == doc.core_properties.author
assert len(final.pages) == len(reader.pages)
out = h / 'pdf-final-render'
out.mkdir(exist_ok=True)
poppler = 'C:/Users/gusta/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin'
images = convert_from_path(target, dpi=171, fmt='png', output_folder=str(out), paths_only=True, poppler_path=poppler, thread_count=2)
different = []
for i, image in enumerate(images, 1):
    with Image.open(image) as actual, Image.open(h / 'render-v5' / f'page-{i}.png') as expected:
        if actual.size != expected.size or ImageChops.difference(actual.convert('RGB'), expected.convert('RGB')).getbbox() is not None:
            different.append(i)
assert not different, different
report = {'pdf': str(target), 'pages': len(final.pages), 'title': final.metadata.title, 'author': final.metadata.author,
          'all_pages_pixel_identical_to_docx_render': True, 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
(h / 'metadados_pdf_e_equivalencia.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False))
