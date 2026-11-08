"""Refresh document statistics from Word without changing visual parts."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import json
import os

h = Path(__file__).resolve().parent
path = h.parents[2] / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx'
with ZipFile(path) as z:
    infos = z.infolist()
    original = {i.filename: z.read(i.filename) for i in infos}
with ZipFile(h / 'fields-v3/word-refreshed.docx') as z:
    word = E.fromstring(z.read('docProps/app.xml'))
app = E.fromstring(original['docProps/app.xml'])
namespace = 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
statistics = {}
for key in ('Pages', 'Words', 'Characters', 'CharactersWithSpaces', 'Lines', 'Paragraphs'):
    value = word.find('{' + namespace + '}' + key)
    if value is None:
        continue
    target = app.find('{' + namespace + '}' + key)
    if target is None:
        target = E.SubElement(app, '{' + namespace + '}' + key)
    target.text = value.text
    statistics[key] = value.text
updated = E.tostring(app, encoding='UTF-8', xml_declaration=True, standalone=True)
temp = path.with_suffix('.stats.tmp')
with ZipFile(temp, 'w') as z:
    for info in infos:
        z.writestr(info, updated if info.filename == 'docProps/app.xml' else original[info.filename])
with ZipFile(temp) as z:
    assert all(z.read(name) == data for name, data in original.items() if name != 'docProps/app.xml')
os.replace(temp, path)
(h / 'metadados_docx.json').write_text(json.dumps({'word_statistics': statistics, 'visual_parts_unchanged': True}, indent=2), encoding='utf-8')
print(json.dumps(statistics))
