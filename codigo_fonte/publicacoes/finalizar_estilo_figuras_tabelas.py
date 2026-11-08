"""Completa o estilo monocromático do relatório, preservando o mapa colorido.

Entrada: revisão com as cinco figuras dos prints já alteradas. Saída em tmp,
para QA antes da publicação. Não executa treinamento ou builders históricos.
"""
from pathlib import Path
import hashlib
import io
import json
import re
import zipfile
import zlib

from lxml import etree
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject, NumberObject

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'documentacao/relatorio_final_ea019'
WORK = ROOT / 'tmp/estilo_monocromatico_completo_20261105'
FIGURES = ROOT / 'tmp/estilo_monocromatico_20261105/figuras'
STEM = 'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos'
SELECTED = (2, 4, 6)
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    WORK.mkdir(exist_ok=True)
    original_pdf, original_docx = BASE / (STEM + '.pdf'), BASE / (STEM + '.docx')
    output_pdf, output_docx = WORK / (STEM + '.pdf'), WORK / (STEM + '.docx')
    if output_pdf.exists() or output_docx.exists():
        raise FileExistsError('Já existe candidato; escolha outro diretório para nova edição.')
    expected = json.loads((BASE / 'Verificacao_Estilo_Figuras_20261105.json').read_text(encoding='utf-8'))
    assert sha(original_pdf.read_bytes()) == expected['pdf']['sha256']
    assert sha(original_docx.read_bytes()) == expected['docx']['sha256']
    inventory = json.loads((ROOT / 'tmp/proveniencia_elementos_relatorio/figuras_mapa.json').read_text(encoding='utf-8'))
    selected = [f for f in inventory['figures'] if f['number'] in SELECTED]
    replacements = {}
    for f in selected:
        raw = (FIGURES / f"figura_{f['number']:02d}.png").read_bytes()
        with Image.open(io.BytesIO(raw)) as im:
            assert list(im.size) == f['asset_dimensions_px']
            r, g, b = im.convert('RGB').split()
            assert r.tobytes() == g.tobytes() == b.tobytes()
        replacements[f['docx_media']] = raw
    with zipfile.ZipFile(original_docx) as src, zipfile.ZipFile(output_docx, 'w') as dst:
        xml = src.read('word/document.xml')
        assert xml.count(b'w:fill="E8ECEF"') == 101
        new_xml = xml.replace(b'w:fill="E8ECEF"', b'w:fill="ECECEC"')
        for entry in src.infolist():
            raw = src.read(entry.filename)
            if entry.filename == 'word/document.xml':
                raw = new_xml
            elif entry.filename in replacements:
                raw = replacements[entry.filename]
            dst.writestr(entry, raw)
    with zipfile.ZipFile(original_docx) as src, zipfile.ZipFile(output_docx) as dst:
        changed = [p for p in src.namelist() if src.read(p) != dst.read(p)]
        assert sorted(changed) == sorted(['word/document.xml', *replacements])
        assert dst.testzip() is None
        before, after = (etree.fromstring(z.read('word/document.xml')) for z in (src, dst))
        assert before.xpath('//w:t/text()', namespaces=NS) == after.xpath('//w:t/text()', namespaces=NS)
        before_tables = before.xpath('//w:tbl//w:tc', namespaces=NS)
        after_tables = after.xpath('//w:tbl//w:tc', namespaces=NS)
        assert len(before_tables) == len(after_tables) == 996
        assert [t.xpath('.//w:t/text()', namespaces=NS) for t in before_tables] == [t.xpath('.//w:t/text()', namespaces=NS) for t in after_tables]
        assert len(after.xpath('//w:tbl', namespaces=NS)) == 17
        assert set(after.xpath('//w:shd/@w:fill', namespaces=NS)) == {'ECECEC'}
        for f in inventory['figures']:
            if f['number'] == 1:
                assert src.read(f['docx_media']) == dst.read(f['docx_media'])
            else:
                with Image.open(io.BytesIO(dst.read(f['docx_media']))) as im:
                    r, g, b = im.convert('RGB').split()
                    assert r.tobytes() == g.tobytes() == b.tobytes(), f['number']

    source = PdfReader(original_pdf)
    writer = PdfWriter(clone_from=original_pdf)
    assert len(source.pages) == len(writer.pages) == 37
    for f in selected:
        page = writer.pages[f['page'] - 1]
        body = [ref.get_object() for ref in page['/Resources']['/XObject'].values()
                if ref.get_object().get('/Subtype') == '/Image' and int(ref.get_object().get('/Width', 0)) > 600]
        assert len(body) == 1
        obj = body[0]
        with Image.open(io.BytesIO(replacements[f['docx_media']])) as image:
            rgba = image.convert('RGBA')
            canvas = Image.new('RGBA', rgba.size, 'white')
            canvas.alpha_composite(rgba)
            gray = canvas.convert('L')
            for key in ('/DecodeParms', '/SMask', '/Mask', '/Matte', '/Decode'):
                obj.pop(NameObject(key), None)
            obj.update({NameObject('/Width'): NumberObject(gray.width),
                        NameObject('/Height'): NumberObject(gray.height),
                        NameObject('/ColorSpace'): NameObject('/DeviceGray'),
                        NameObject('/BitsPerComponent'): NumberObject(8),
                        NameObject('/Filter'): NameObject('/FlateDecode')})
            obj._data = zlib.compress(gray.tobytes(), level=9)
            obj.decoded_self = None
    tint = re.compile(rb'(?<![\d.])0\.91\s+0\.925\s+0\.937\s+rg\b')
    table_changes = []
    for n, page in enumerate(writer.pages, 1):
        data = page.get_contents().get_data()
        neutral, count = tint.subn(b'0.92549 0.92549 0.92549 rg', data)
        if count:
            new_stream = DecodedStreamObject()
            new_stream.set_data(neutral)
            page.replace_contents(new_stream)
            page.compress_content_streams()
            table_changes.append({'pagina': n, 'operadores_de_cor_neutralizados': count})
    assert table_changes
    writer.write(output_pdf)
    result = PdfReader(output_pdf)
    for p, q in zip(source.pages, result.pages):
        assert p.extract_text() == q.extract_text()
        assert p.mediabox == q.mediabox
        assert not tint.search(q.get_contents().get_data())
    assert source.pages[8].get_contents().get_data() == result.pages[8].get_contents().get_data()
    links = [a.get_object().get('/A', {}).get('/URI') for a in result.pages[0].get('/Annots', [])]
    assert 'https://youtu.be/XuWWDDLRIOg' in links
    qa = {'status': 'verificacao_estrutural_concluida_revisao_visual_pendente',
          'paginas': 37, 'figuras_monocromaticas': list(range(2, 10)), 'mapa_colorido_preservado': True,
          'tabelas_monocromaticas': 17, 'preenchimentos_docx_neutralizados': 101,
          'celulas_nativas_conferidas': 996, 'texto_pdf_docx_preservado': True,
          'partes_docx_alteradas_nesta_etapa': changed, 'cabecalhos_pdf': table_changes,
          'link_video_preservado': links, 'pdf': str(output_pdf), 'docx': str(output_docx),
          'originais_sha256': {'pdf': sha(original_pdf.read_bytes()), 'docx': sha(original_docx.read_bytes())}}
    (WORK / 'verificacao_estrutural.json').write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
