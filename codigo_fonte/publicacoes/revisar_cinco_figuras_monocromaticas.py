"""Substitui somente as cinco figuras indicadas nos prints do usuário.

Mantém texto, tabelas, mapa, logotipos, paginação, fluxos PDF e links.
Use os marcadores de autoria PDF/DOCX antes de executar este script.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile
import zlib

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "tmp/estilo_monocromatico_20261105"
BASE = ROOT / "documentacao/relatorio_final_ea019"
STEM = "Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos"
SELECTED = (3, 5, 7, 8, 9)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--revision', default='')
    args = parser.parse_args()
    suffix = ('_' + args.revision) if args.revision else ''
    figures = json.loads((ROOT / "tmp/proveniencia_elementos_relatorio/figuras_mapa.json").read_text(encoding="utf-8"))["figures"]
    selected = [f for f in figures if f["number"] in SELECTED]
    source_pdf, source_docx = BASE / (STEM + ".pdf"), BASE / (STEM + ".docx")
    target_pdf = WORK / (STEM + "_Monocromatico" + suffix + ".pdf")
    target_docx = target_pdf.with_suffix(".docx")
    if target_pdf.exists() or target_docx.exists():
        raise FileExistsError("Use novos destinos para uma segunda revisão.")
    original_hashes = {p.name: digest(p.read_bytes()) for p in (source_pdf, source_docx)}
    replacement = {}
    edits = []
    for f in selected:
        final_nine = WORK / 'figuras/figura_09_final.png'
        png = final_nine if f['number'] == 9 and final_nine.is_file() else WORK / "figuras" / f"figura_{f['number']:02d}.png"
        raw = png.read_bytes()
        with Image.open(io.BytesIO(raw)) as image:
            assert list(image.size) == f["asset_dimensions_px"]
            rgb = image.convert("RGB")
            red, green, blue = rgb.split()
            assert red.tobytes() == green.tobytes() == blue.tobytes()
        replacement[f["docx_media"]] = raw
        edits.append({"figura": f["number"], "pagina": f["page"], "titulo": f["title"],
                      "png": str(png.relative_to(ROOT)), "png_sha256": digest(raw),
                      "docx_media": f["docx_media"]})
    with zipfile.ZipFile(source_docx) as src, zipfile.ZipFile(target_docx, "w") as dst:
        for item in src.infolist():
            raw = src.read(item.filename)
            if item.filename in replacement:
                assert digest(raw) == next(f["asset_sha256"] for f in selected if f["docx_media"] == item.filename)
                raw = replacement[item.filename]
            dst.writestr(item, raw)
    with zipfile.ZipFile(source_docx) as src, zipfile.ZipFile(target_docx) as dst:
        changed = [name for name in src.namelist() if src.read(name) != dst.read(name)]
        assert sorted(changed) == sorted(replacement)
        assert dst.testzip() is None

    source = PdfReader(source_pdf)
    writer = PdfWriter(clone_from=source_pdf)
    assert len(source.pages) == len(writer.pages) == 37
    for f, edit in zip(selected, edits):
        page = writer.pages[f["page"] - 1]
        # Cada uma destas páginas tem uma única imagem de corpo e dois logos.
        body = []
        for key, ref in page["/Resources"]["/XObject"].items():
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Image" and int(obj.get("/Width", 0)) > 600:
                body.append((key, ref, obj))
        assert len(body) == 1, (f["number"], body)
        key, ref, obj = body[0]
        with Image.open(io.BytesIO(replacement[f["docx_media"]])) as image:
            # Flatten explícito conserva o fundo branco dos diagramas.
            rgba = image.convert("RGBA")
            white = Image.new("RGBA", rgba.size, "white")
            white.alpha_composite(rgba)
            gray = white.convert("L")
            compressed = zlib.compress(gray.tobytes(), level=9)
            for name in ("/DecodeParms", "/SMask", "/Mask", "/Matte", "/Decode"):
                obj.pop(NameObject(name), None)
            obj[NameObject("/Width")] = NumberObject(gray.width)
            obj[NameObject("/Height")] = NumberObject(gray.height)
            obj[NameObject("/ColorSpace")] = NameObject("/DeviceGray")
            obj[NameObject("/BitsPerComponent")] = NumberObject(8)
            obj[NameObject("/Filter")] = NameObject("/FlateDecode")
            obj._data = compressed
            obj.decoded_self = None
            edit["pdf_resource"] = key
            edit["pdf_pixels"] = list(gray.size)
    writer.write(target_pdf)
    result = PdfReader(target_pdf)
    assert len(result.pages) == 37
    pages = []
    for index, (before, after) in enumerate(zip(source.pages, result.pages), 1):
        text_equal = before.extract_text() == after.extract_text()
        content_equal = before.get_contents().get_data() == after.get_contents().get_data()
        geometry_equal = before.mediabox == after.mediabox
        assert text_equal and content_equal and geometry_equal, index
        pages.append({"pagina": index, "texto_identico": text_equal,
                      "fluxo_de_pagina_identico": content_equal, "geometria_identica": geometry_equal})
    links = [a.get_object().get("/A", {}).get("/URI") for a in result.pages[0].get("/Annots", [])]
    assert "https://youtu.be/XuWWDDLRIOg" in links
    assert original_hashes == {p.name: digest(p.read_bytes()) for p in (source_pdf, source_docx)}
    qa = {"status": "verificacao_estrutural_concluida_revisao_visual_pendente", "figuras_alteradas": edits,
          "mapa_preservado": True, "outras_figuras_preservadas": [1, 2, 4, 6],
          "tabelas_nativas_preservadas": 17, "docx_partes_alteradas": changed,
          "paginas": pages, "youtube_capa_preservado": links,
          "originais_sha256": original_hashes,
          "candidato_pdf": str(target_pdf), "candidato_docx": str(target_docx)}
    (WORK / ("verificacao_estrutural" + suffix + ".json")).write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pdf": str(target_pdf), "docx": str(target_docx), "figuras": list(SELECTED),
                      "paginas": len(result.pages), "conteudo_textual_identico": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
