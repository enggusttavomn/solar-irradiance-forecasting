"""Verificação independente do TCC revisado, sem modificar os documentos.

Uso (no runtime Python autorizado):
  verificar_independente.py [--pdf ARQUIVO.pdf] [--pdf-text TEXTO_PDF.txt]

O texto opcional deve preservar as páginas com form feed (pdftotext -layout).
Se pypdf estiver disponível, --pdf permite conferir o sumário contra o PDF.
O relatório JSON e o código de saída permitem usar este script como gate de QA.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"w": W, "m": M, "r": R, "a": A}
VOLATILE = {"rsidR", "rsidRPr", "rsidDel", "rsidRDefault", "rsidP", "rsidSect"}
EXPECTED_RETAINED_FIGURES = [1, 2, 5, 6, 7, 9, 10, 11, 13]


def normal(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).split())


def visible_text(node: ET.Element) -> str:
    """Somente texto visível; mantém separadores necessários ao sumário."""
    parts = []
    for el in node.iter():
        if el.tag in {f"{{{W}}}t", f"{{{M}}}t"}:
            parts.append(el.text or "")
        elif el.tag == f"{{{W}}}tab":
            parts.append("\t")
        elif el.tag in {f"{{{W}}}br", f"{{{W}}}cr"}:
            parts.append("\n")
    return "".join(parts)


def math_signature(node: ET.Element):
    """Preserva conteúdo e estrutura; ignora apenas IDs voláteis de revisão."""
    attrs = sorted((k, v) for k, v in node.attrib.items() if k.rsplit("}", 1)[-1] not in VOLATILE)
    # Espaçamento XML entre elementos não pertence à fórmula; m:t é preservado.
    text = node.text or ""
    if node.tag not in {f"{{{M}}}t", f"{{{W}}}t"} and not text.strip():
        text = ""
    return [node.tag, attrs, text, [math_signature(child) for child in node]]


def digest(value) -> str:
    if not isinstance(value, bytes):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def field_instructions(root: ET.Element) -> list[str]:
    fields, stack = [], []
    for el in root.iter():
        if el.tag == f"{{{W}}}fldChar":
            kind = el.get(f"{{{W}}}fldCharType")
            if kind == "begin":
                stack.append([])
            elif kind == "end" and stack:
                fields.append("".join(stack.pop()))
        elif el.tag == f"{{{W}}}instrText" and stack:
            stack[-1].append(el.text or "")
        elif el.tag == f"{{{W}}}fldSimple":
            fields.append(el.get(f"{{{W}}}instr", ""))
    return fields


class Document:
    def __init__(self, path: Path):
        self.path = path
        with zipfile.ZipFile(path) as z:
            self.parts = set(z.namelist())
            self.root = ET.fromstring(z.read("word/document.xml"))
            self.styles = ET.fromstring(z.read("word/styles.xml"))
            relroot = ET.fromstring(z.read("word/_rels/document.xml.rels"))
            self.rels = {el.get("Id"): dict(el.attrib) for el in relroot}
            self.images = {}
            for rid, rel in self.rels.items():
                if rel.get("Type", "").endswith("/image") and rel.get("TargetMode") != "External":
                    target = self.resolve_part(rel.get("Target", ""))
                    if target in self.parts:
                        self.images[rid] = digest(z.read(target))
        self.paragraphs = list(self.root.findall(".//w:p", NS))
        self.texts = [visible_text(p) for p in self.paragraphs]
        self.style_by_paragraph = [self.par_style(p) for p in self.paragraphs]
        self.heading_styles = {"Ttulo1", "Heading1", "Heading2", "Ttulo2"}
        for st in self.styles.findall("w:style", NS):
            lvl = st.find("w:pPr/w:outlineLvl", NS)
            if lvl is not None and lvl.get(f"{{{W}}}val") in {"0", "1"}:
                self.heading_styles.add(st.get(f"{{{W}}}styleId"))

    @staticmethod
    def resolve_part(target: str) -> str:
        import posixpath
        return posixpath.normpath(target.lstrip("/") if target.startswith("/") else "word/" + target)

    @staticmethod
    def par_style(p: ET.Element) -> str:
        st = p.find("w:pPr/w:pStyle", NS)
        return st.get(f"{{{W}}}val", "") if st is not None else ""

    def tables(self):
        return [
            [[normal("\n".join(visible_text(p) for p in c.findall("w:p", NS))) for c in row.findall("w:tc", NS)]
             for row in table.findall("w:tr", NS)]
            for table in self.root.findall(".//w:tbl", NS)
        ]

    def equations(self):
        return [math_signature(eq) for eq in self.root.findall(".//m:oMath", NS)]

    def captions(self, label: str):
        out = []
        for index, (text, style) in enumerate(zip(self.texts, self.style_by_paragraph)):
            if style.upper().startswith("TOC"):
                continue
            match = re.match(rf"^{label}\s+(\d+)\s*[—–-]\s*(.+)$", normal(text))
            if match:
                out.append({"number": int(match[1]), "title": match[2], "paragraph": index})
        return out

    def figure_images(self):
        figures = []
        ps = list(self.root.find("w:body", NS))
        for i, p in enumerate(ps):
            text = normal(visible_text(p))
            match = re.match(r"^Figura\s+(\d+)\s*[—–-]", text)
            if not match:
                continue
            hashes = []
            # Neste documento, a imagem vem logo após a legenda superior.
            for other in ps[i + 1:i + 5]:
                if re.match(r"^(Figura|Tabela)\s+\d+\s*[—–-]", normal(visible_text(other))):
                    break
                for blip in other.findall(".//a:blip", NS):
                    rid = blip.get(f"{{{R}}}embed")
                    hashes.append(self.images.get(rid, f"MISSING:{rid}"))
                if hashes:
                    break
            figures.append({"number": int(match[1]), "hashes": hashes})
        return figures

    def headings(self):
        return [normal(text) for text, st in zip(self.texts, self.style_by_paragraph)
                if st in self.heading_styles and normal(text)]

    def toc(self):
        out = []
        for p, text, style in zip(self.paragraphs, self.texts, self.style_by_paragraph):
            if not style.upper().startswith("TOC"):
                continue
            title, sep, page = text.rpartition("\t")
            if not sep:
                match = re.match(r"^(.*?)(\d+)\s*$", text)
                title, page = (match[1], match[2]) if match else (text, "")
            links = [el.get(f"{{{W}}}anchor") for el in p.findall(".//w:hyperlink", NS)]
            out.append({"title": normal(title), "page": page.strip(), "anchors": [a for a in links if a]})
        return out


def numbered_mentions(text: str, label: str) -> list[int]:
    nums = []
    for match in re.finditer(rf"\b{label}s?\s+(\d+)((?:\s*(?:,|e|a|–|-)\s*\d+)*)", text, re.I):
        first = int(match[1])
        nums.append(first)
        suffix = match[2]
        others = [int(n) for n in re.findall(r"\d+", suffix)]
        if others and re.search(r"\s(?:a|–|-)\s", suffix):
            nums.extend(range(first + 1, others[-1] + 1))
        else:
            nums.extend(others)
    return nums


def inspect(source: Document, revised: Document):
    checks, warnings = [], []

    def check(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), **detail})

    before, after = source.tables(), revised.tables()
    check("tables_count_17", len(before) == len(after) == 17, source=len(before), revised=len(after))
    changed = []
    for i in range(max(len(before), len(after))):
        old = before[i] if i < len(before) else None
        new = after[i] if i < len(after) else None
        if old != new:
            changed.append({"table": i + 1, "source": old, "revised": new})
    check("all_table_texts_unchanged", not changed, differences=changed,
          source_sha256=digest(before), revised_sha256=digest(after))

    before, after = source.equations(), revised.equations()
    check("equations_count_7", len(before) == len(after) == 7, source=len(before), revised=len(after))
    changed_eqs = [i + 1 for i in range(min(len(before), len(after))) if before[i] != after[i]]
    check("all_equations_unchanged", len(before) == len(after) and not changed_eqs,
          changed_equations=changed_eqs, source_sha256=digest(before), revised_sha256=digest(after))

    figure_caps, table_caps = revised.captions("Figura"), revised.captions("Tabela")
    fnums, tnums = [x["number"] for x in figure_caps], [x["number"] for x in table_caps]
    check("figure_captions_1_to_9", fnums == list(range(1, 10)), numbers=fnums)
    check("table_captions_1_to_17", tnums == list(range(1, 18)), numbers=tnums)
    drawings = revised.root.findall(".//w:drawing", NS)
    check("figure_drawings_count_9", len(drawings) == 9, drawings=len(drawings))
    old_images = {x["number"]: x["hashes"] for x in source.figure_images()}
    expected = [old_images.get(n) for n in EXPECTED_RETAINED_FIGURES]
    actual = [x["hashes"] for x in revised.figure_images()]
    check("retained_figures_in_expected_order", actual == expected and all(expected),
          source_figure_numbers=EXPECTED_RETAINED_FIGURES, expected_hashes=expected, revised_hashes=actual)

    ordinary_texts = [text for text, st in zip(revised.texts, revised.style_by_paragraph)
                      if not st.upper().startswith("TOC")]
    alltext = "\n".join(ordinary_texts)
    fig_mentions = numbered_mentions(alltext, "Figura")
    tab_mentions = numbered_mentions(alltext, "Tabela")
    check("figure_references_resolve", set(fig_mentions) <= set(fnums),
          invalid_numbers=sorted(set(fig_mentions) - set(fnums)))
    check("table_references_resolve", set(tab_mentions) <= set(tnums),
          invalid_numbers=sorted(set(tab_mentions) - set(tnums)))
    body_only = "\n".join(text for text in ordinary_texts
                          if not re.match(r"^(Figura|Tabela)\s+\d+\s*[—–-]", normal(text)))
    uncited_figs = sorted(set(fnums) - set(numbered_mentions(body_only, "Figura")))
    if uncited_figs:
        warnings.append({"name": "figures_without_body_mentions", "numbers": uncited_figs})

    refs = []
    content = []
    for text in ordinary_texts:
        ref = re.match(r"^\[(\d+)\]\s+\S", text.strip())
        if ref:
            refs.append(int(ref[1]))
        else:
            content.append(text)
    expected_refs = sorted(set(refs))
    check("bibliography_numbering", refs == list(range(1, 18)), numbers=refs)
    cited = []
    for match in re.finditer(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]", "\n".join(content)):
        tokens = [int(n) for n in re.findall(r"\d+", match[1])]
        if 0 in tokens:  # intervalo [0,1], não referência bibliográfica
            continue
        if re.search(r"[–-]", match[1]) and len(tokens) == 2:
            cited.extend(range(tokens[0], tokens[1] + 1))
        else:
            cited.extend(tokens)
    check("citations_resolve_to_bibliography", set(cited) <= set(expected_refs),
          invalid_numbers=sorted(set(cited) - set(expected_refs)))
    check("all_bibliography_items_cited", set(refs) <= set(cited),
          uncited_numbers=sorted(set(refs) - set(cited)))
    first_seen = list(dict.fromkeys(cited))
    check("citation_numbering_follows_first_appearance", first_seen == list(range(1, 18)),
          first_appearance_order=first_seen)

    bookmarks = revised.root.findall(".//w:bookmarkStart", NS)
    names = [b.get(f"{{{W}}}name", "") for b in bookmarks]
    duplicate_names = sorted(k for k, v in Counter(names).items() if k and v > 1)
    check("bookmark_names_unique", not duplicate_names, duplicates=duplicate_names)
    broken_links, broken_rids, external = [], [], []
    for link in revised.root.findall(".//w:hyperlink", NS):
        anchor = link.get(f"{{{W}}}anchor")
        rid = link.get(f"{{{R}}}id")
        if anchor and anchor not in names:
            broken_links.append({"anchor": anchor, "text": visible_text(link)})
        if rid:
            rel = revised.rels.get(rid)
            if not rel or not rel.get("Target"):
                broken_rids.append(rid)
            else:
                external.append(rel.get("Target"))
    check("internal_hyperlinks_resolve", not broken_links, broken_links=broken_links)
    check("hyperlink_relationships_exist", not broken_rids, broken_relationships=broken_rids,
          external_links=external)
    missing_field_targets = []
    for code in field_instructions(revised.root):
        for match in re.finditer(r'\b(?:PAGEREF|REF|NOTEREF)\s+(?:"([^"]+)"|([^\s\\]+))', code, re.I):
            name = match[1] or match[2]
            if name not in names:
                missing_field_targets.append({"target": name, "field": code})
    check("reference_fields_resolve", not missing_field_targets, invalid_fields=missing_field_targets)
    missing_images = []
    for blip in revised.root.findall(".//a:blip", NS):
        rid = blip.get(f"{{{R}}}embed")
        if rid and rid not in revised.images:
            missing_images.append(rid)
    check("embedded_images_resolve", not missing_images, missing_relationships=missing_images)
    field_errors = [text for text in ordinary_texts if re.search(r"\b(?:Erro|Error)!", text, re.I)]
    check("no_visible_field_errors", not field_errors, errors=field_errors)

    toc, headings = revised.toc(), revised.headings()
    check("toc_titles_match_headings", [x["title"] for x in toc] == headings,
          toc_titles=[x["title"] for x in toc], body_headings=headings)
    bad_page_numbers = [x for x in toc if not re.fullmatch(r"\d+", x["page"])]
    check("toc_cached_page_numbers_exist", bool(toc) and not bad_page_numbers,
          invalid_entries=bad_page_numbers)
    bookmark_paragraphs = {}
    for p in revised.paragraphs:
        for b in p.findall(".//w:bookmarkStart", NS):
            bookmark_paragraphs[b.get(f"{{{W}}}name")] = normal(visible_text(p))
    toc_target_mismatches = []
    for entry in toc:
        if entry["anchors"] and all(bookmark_paragraphs.get(a) != entry["title"] for a in entry["anchors"]):
            toc_target_mismatches.append({**entry, "targets": [bookmark_paragraphs.get(a) for a in entry["anchors"]]})
    check("toc_links_target_correct_headings", not toc_target_mismatches, mismatches=toc_target_mismatches)
    return checks, warnings


def pdf_pages(pdf: Path | None, text_file: Path | None):
    if text_file:
        pages = text_file.read_text(encoding="utf-8-sig").split("\f")
        if pages and not pages[-1].strip():
            pages.pop()
        return pages, "text_with_form_feed"
    if pdf:
        try:
            from pypdf import PdfReader
        except ImportError:
            return None, "pypdf indisponível; forneça --pdf-text obtido com pdftotext -layout"
        return [(p.extract_text() or "") for p in PdfReader(str(pdf)).pages], "pypdf"
    return None, "PDF não fornecido"


def check_toc_pdf(doc: Document, pages: list[str]):
    normalized = [normal(page) for page in pages]
    toc_pages = [i for i, txt in enumerate(normalized) if re.search(r"\bSUMÁRIO\b", txt)]
    # Resumo vem depois do sumário e antes dos capítulos; exclui as páginas do sumário.
    first_toc = min(toc_pages) if toc_pages else -1
    resumo = next((i for i, txt in enumerate(normalized) if i > first_toc and re.search(r"\bRESUMO\b", txt)), first_toc)
    mismatches, verified, unavailable = [], [], []
    for entry in doc.toc():
        # Alinha quebras de linha e variações de espaços da extração PDF.
        title = entry["title"]
        candidates = [i for i, txt in enumerate(normalized) if i > resumo and title in txt]
        if not candidates:
            unavailable.append({"heading": title, "reason": "título não localizado na extração PDF"})
            continue
        found = candidates[0]
        last_lines = [line.strip() for line in pages[found].splitlines() if line.strip()][-4:]
        footer = next((int(line) for line in reversed(last_lines) if re.fullmatch(r"\d+", line)), None)
        # Neste documento, os números arábicos coincidem com as páginas físicas.
        actual = footer if footer is not None else found + 1
        row = {"heading": title, "toc_page": entry["page"], "pdf_physical_page": found + 1,
               "pdf_displayed_page": footer, "compared_page": actual,
               "page_source": "footer" if footer is not None else "physical_page_fallback"}
        verified.append(row)
        if not entry["page"].isdigit() or int(entry["page"]) != actual:
            mismatches.append(row)
    return {"name": "toc_pages_match_pdf_headings", "passed": not mismatches and not unavailable,
            "pdf_pages": len(pages), "mismatches": mismatches, "unavailable": unavailable, "verified": verified}


def main():
    root = Path(__file__).resolve().parents[2]
    folder = root / "documentacao/relatorio_final_ea019"
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=folder / "Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Corrigido.docx")
    ap.add_argument("--revised", type=Path, default=folder / "Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC_Revisado.docx")
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--pdf-text", type=Path)
    ap.add_argument("--output", type=Path, default=Path(__file__).with_name("verificacao_independente.json"))
    args = ap.parse_args()
    if not args.source.exists() or not args.revised.exists():
        ap.error("A fonte e a revisão precisam existir antes da execução; nenhum documento foi alterado.")
    source, revised = Document(args.source), Document(args.revised)
    checks, warnings = inspect(source, revised)
    pages, method = pdf_pages(args.pdf, args.pdf_text)
    if pages is not None:
        checks.append(check_toc_pdf(revised, pages))
    else:
        warnings.append({"name": "pdf_toc_not_checked", "reason": method})
    report = {"passed": all(item["passed"] for item in checks), "source": str(args.source.resolve()),
              "revised": str(args.revised.resolve()), "source_sha256": digest(args.source.read_bytes()),
              "revised_sha256": digest(args.revised.read_bytes()), "pdf_method": method,
              "pdf": str(args.pdf.resolve()) if args.pdf else None,
              "pdf_sha256": digest(args.pdf.read_bytes()) if args.pdf else None,
              "pdf_text": str(args.pdf_text.resolve()) if args.pdf_text else None,
              "checks": checks, "warnings": warnings,
              "limits": "Verificação estrutural e textual. Não substitui inspeção visual do PDF nem valida acessibilidade remota de links externos."}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item["name"] for item in checks if not item["passed"]]
    print(json.dumps({"passed": report["passed"], "checks": len(checks), "failed": failed,
                      "warnings": len(warnings), "report": str(args.output.resolve())}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
