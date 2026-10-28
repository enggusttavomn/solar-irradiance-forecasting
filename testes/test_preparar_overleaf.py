from pathlib import Path

import pytest

from scripts.preparar_overleaf import ExportacaoOverleafError, preparar_overleaf


def write(root: Path, relative: str, text: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def source(tmp_path: Path, main: str = "") -> Path:
    root = tmp_path / "source"
    write(root, "main.tex", main)
    write(root, "supplementary_material.tex", r"\documentclass{article}")
    return root


def test_exports_transitive_dependencies_and_excludes_unused_files(tmp_path: Path) -> None:
    root = source(tmp_path, r"""\documentclass{localclass}
\usepackage{localstyle,amsmath}
\graphicspath{{figures/}}
\input{sections/first}
\bibliography{references}
\bibliographystyle{localbib}
% \input{missing_comment}
""")
    write(root, "sections/first.tex", r"\include{sections/second}")
    write(root, "sections/second.tex", r"\includegraphics[width=\linewidth]{chart.png}")
    write(root, "figures/chart.png", "PNG fixture")
    write(root, "references.bib", "@article{example, title={Example}}")
    write(root, "localclass.cls", r"\LoadClass{article}")
    write(root, "localstyle.sty", r"\RequirePackage{nested}")
    write(root, "nested.sty", "")
    write(root, "localbib.bst", "ENTRY{}{}{}")
    ignored = ["README.md", ".gitignore", "notes/review.md", "main_ieee.tex",
               "figures/chart.svg", "tables/unused.tex", "sections/04_algorithms.tex"]
    for relative in ignored:
        write(root, relative, "not an official dependency")
    target = tmp_path / "export"
    files = preparar_overleaf(root, target)
    expected = {"main.tex", "supplementary_material.tex", "sections/first.tex",
                "sections/second.tex", "figures/chart.png", "references.bib",
                "localclass.cls", "localstyle.sty", "nested.sty", "localbib.bst"}
    assert {p.as_posix() for p in files} == expected
    assert {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()} == expected
    assert all((target / p).read_bytes() == (root / p).read_bytes() for p in files)
    assert all(not (target / p).exists() for p in ignored)


def test_missing_transitive_file_fails_before_creating_destination(tmp_path: Path) -> None:
    root = source(tmp_path, r"\input{sections/present}")
    write(root, "sections/present.tex", r"\includegraphics{missing.png}")
    target = tmp_path / "export"
    with pytest.raises(ExportacaoOverleafError, match="Missing dependency"):
        preparar_overleaf(root, target)
    assert not target.exists()


@pytest.mark.parametrize("command", [
    r"\input{../outside}", r"\includegraphics{../outside.png}",
    r"\graphicspath{{../outside/}}", r"\bibliography{../outside}",
    r"\usepackage{../outside}", r"\input{C:/outside.tex}",
])
def test_rejects_paths_outside_source_before_copying(tmp_path: Path, command: str) -> None:
    root = source(tmp_path, command)
    target = tmp_path / "export"
    with pytest.raises(ExportacaoOverleafError, match="Unsafe|escapes"):
        preparar_overleaf(root, target)
    assert not target.exists()


def test_rejects_occupied_destination_and_preserves_it(tmp_path: Path) -> None:
    root = source(tmp_path)
    target = tmp_path / "export"
    existing = write(target, "old/asset.txt", "preserve this")
    with pytest.raises(ExportacaoOverleafError, match="new or empty"):
        preparar_overleaf(root, target)
    assert existing.read_text() == "preserve this"
    assert not (target / "main.tex").exists()


def test_supports_existing_empty_destination_and_both_document_graphicspaths(tmp_path: Path) -> None:
    root = source(tmp_path, r"\graphicspath{{first/}}\input{shared}")
    write(root, "supplementary_material.tex", r"\graphicspath{{second/}}\input{shared}")
    write(root, "shared.tex", r"\includegraphics{chart}")
    write(root, "first/chart.png", "first chart")
    write(root, "second/chart.png", "second chart")
    target = tmp_path / "export"
    target.mkdir()
    files = preparar_overleaf(root, target)
    assert Path("first/chart.png") in files
    assert Path("second/chart.png") in files


def test_rejects_cyclic_input_without_copying(tmp_path: Path) -> None:
    root = source(tmp_path, r"\input{loop}")
    write(root, "loop.tex", r"\input{loop}")
    target = tmp_path / "export"
    with pytest.raises(ExportacaoOverleafError, match="Cyclic"):
        preparar_overleaf(root, target)
    assert not target.exists()
