"""Import only Word-computed document statistics; preserve every visual part."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import json
import os

h = Path(__file__).resolve().parent
p = h.parents[1] / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC.docx'
refreshed = h / 'fields-v4/word-refreshed.docx'
with ZipFile(p) as z:
    infos = z.infolist()
    old = {i.filename: z.read(i.filename) for i in infos}
with ZipFile(refreshed) as z:
    word_app = E.fromstring(z.read('docProps/app.xml'))
app = E.fromstring(old['docProps/app.xml'])
ns = 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'
stats = {}
for name in ('Pages', 'Words', 'Characters', 'CharactersWithSpaces', 'Lines', 'Paragraphs'):
    value = word_app.find('{' + ns + '}' + name)
    if value is None:
        continue
    target = app.find('{' + ns + '}' + name)
    if target is None:
        target = E.SubElement(app, '{' + ns + '}' + name)
    target.text = value.text
    stats[name] = value.text
new_app = E.tostring(app, encoding='UTF-8', xml_declaration=True, standalone=True)
temp = p.with_suffix('.metadata.tmp')
with ZipFile(temp, 'w') as z:
    for info in infos:
        z.writestr(info, new_app if info.filename == 'docProps/app.xml' else old[info.filename])
with ZipFile(temp) as z:
    assert all(z.read(n) == data for n, data in old.items() if n != 'docProps/app.xml')
os.replace(temp, p)
(h / 'auditoria_metadados.json').write_text(json.dumps({'stats_from_word': stats, 'visual_parts_unchanged': True}, indent=2), encoding='utf-8')
print(json.dumps(stats))
