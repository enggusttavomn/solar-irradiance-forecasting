"""Keep a model's horizons together and left-align long source identifiers."""
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
import json
import os

h = Path(__file__).resolve().parent
path = h.parents[2] / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx'
with ZipFile(path) as z:
    infos = z.infolist()
    parts = {i.filename: z.read(i.filename) for i in infos}
ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
w = '{' + ns['w'] + '}'
r = E.fromstring(parts['word/document.xml'])
before = r.xpath('//w:t/text()', namespaces=ns)
changed = []
for p in r.findall('.//w:body/w:p', ns):
    text = ''.join(p.xpath('.//w:t/text()', namespaces=ns))
    if text.startswith(('O retrato consultado do repositório', 'As quatro fontes abaixo foram conferidas')):
        pr = p.find('w:pPr', ns)
        if pr is None:
            pr = E.Element(w + 'pPr'); p.insert(0, pr)
        jc = pr.find('w:jc', ns)
        if jc is None:
            jc = E.SubElement(pr, w + 'jc')
        jc.set(w + 'val', 'left')
        changed.append(text[:70])
table = r.findall('.//w:tbl', ns)[9]
lstm_rows = [row for row in table.findall('w:tr', ns) if ''.join(row.find('w:tc', ns).xpath('.//w:t/text()', namespaces=ns)) == 'LSTM']
assert len(lstm_rows) == 5
for row in lstm_rows[:-1]:
    for p in row.findall('.//w:p', ns):
        pr = p.find('w:pPr', ns)
        if pr is None:
            pr = E.Element(w + 'pPr'); p.insert(0, pr)
        keep = pr.find('w:keepNext', ns)
        if keep is None:
            keep = E.SubElement(pr, w + 'keepNext')
        keep.set(w + 'val', 'true')
assert before == r.xpath('//w:t/text()', namespaces=ns)
updated = E.tostring(r, encoding='UTF-8', xml_declaration=True, standalone=True)
temp = path.with_suffix('.layout.tmp')
with ZipFile(temp, 'w') as z:
    for info in infos:
        z.writestr(info, updated if info.filename == 'word/document.xml' else parts[info.filename])
os.replace(temp, path)
(h / 'acabamento_visual.json').write_text(json.dumps({'all_text_unchanged': True, 'left_aligned': changed, 'lstm_daily_horizons_grouped': 5}, ensure_ascii=False, indent=2), encoding='utf-8')
print('Acabamento aplicado, com todo o texto e os valores preservados.')
