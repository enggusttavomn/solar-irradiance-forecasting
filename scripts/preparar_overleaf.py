"""Export only the dependencies of the two official Overleaf documents.

The scanner handles literal LaTeX paths and compiles from the source root.
Distribution-provided classes, packages and bibliography styles are not copied.
No source files are changed and no destination files are removed or overwritten.
"""
from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINTS = ("main.tex", "supplementary_material.tex")
GRAPHICS_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg", ".eps")
COMMAND = re.compile(
    r"\\(includegraphics|graphicspath|bibliographystyle|bibliography|"
    r"documentclass|usepackage|RequirePackageWithOptions|RequirePackage|"
    r"LoadClassWithOptions|LoadClass|input|include)(?![A-Za-z@])\*?"
)


class ExportacaoOverleafError(ValueError):
    """The source closure or destination is unsuitable for a clean export."""


def _without_comments(text: str) -> str:
    lines = []
    for line in text.splitlines():
        for position, char in enumerate(line):
            if char != "%":
                continue
            backslashes = 0
            cursor = position - 1
            while cursor >= 0 and line[cursor] == "\\":
                backslashes += 1
                cursor -= 1
            if backslashes % 2 == 0:
                line = line[:position]
                break
        lines.append(line)
    return "\n".join(lines)


def _group(text: str, start: int, opening: str, closing: str) -> tuple[str, int]:
    if start >= len(text) or text[start] != opening:
        raise ExportacaoOverleafError("Expected a literal LaTeX argument.")
    depth = 1
    cursor = start + 1
    while cursor < len(text):
        char = text[cursor]
        if char == "\\":
            cursor += 2
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start + 1:cursor], cursor + 1
        cursor += 1
    raise ExportacaoOverleafError("Unclosed LaTeX dependency argument.")


def _commands(text: str):
    text = _without_comments(text)
    cursor = 0
    while match := COMMAND.search(text, cursor):
        command = match.group(1)
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "[":
            _, cursor = _group(text, cursor, "[", "]")
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
        if cursor < len(text) and text[cursor] == "{":
            argument, cursor = _group(text, cursor, "{", "}")
        elif command == "input":
            match_path = re.match(r"[^\s{}%]+", text[cursor:])
            if not match_path:
                raise ExportacaoOverleafError("Missing literal input path.")
            argument = match_path.group()
            cursor += len(argument)
        else:
            raise ExportacaoOverleafError(f"Nonliteral or missing argument for {command}.")
        yield command, argument.strip()


def _literal_path(value: str) -> Path:
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if (
        not value or windows.is_absolute() or windows.drive or posix.is_absolute()
        or ".." in posix.parts or ".." in windows.parts
        or any(char in value for char in "\\{}#$~\x00")
    ):
        raise ExportacaoOverleafError(f"Unsafe or nonliteral dependency path: {value!r}")
    return Path(*posix.parts)


class _Collector:
    def __init__(self, root: Path):
        self.root = root
        self.files: set[Path] = set()
        self.active: set[Path] = set()
        self.loaded_support: set[Path] = set()

    def _candidate(self, relative: Path) -> Path:
        path = self.root / relative
        resolved = path.resolve()
        if not resolved.is_relative_to(self.root):
            raise ExportacaoOverleafError(f"Dependency escapes source root: {relative}")
        return path

    def resolve(
        self, value: str, extensions: tuple[str, ...],
        search: Sequence[Path] = (Path("."),), optional: bool = False,
    ) -> Path | None:
        relative = _literal_path(value)
        names = [relative] if relative.suffix else [relative.with_suffix(e) for e in extensions]
        for directory in search:
            for name in names:
                candidate = self._candidate(directory / name)
                if candidate.is_file():
                    return candidate
        if optional and len(relative.parts) == 1:
            return None
        raise ExportacaoOverleafError(f"Missing dependency: {value}")

    def scan(self, path: Path, graphics: list[Path], *, support: bool = False) -> None:
        if support and path in self.loaded_support:
            return
        if path in self.active:
            raise ExportacaoOverleafError(f"Cyclic input/include dependency: {path}")
        if support:
            self.loaded_support.add(path)
        self.files.add(path)
        self.active.add(path)
        try:
            text = path.read_text(encoding="utf-8-sig")
            for command, argument in _commands(text):
                if command == "graphicspath":
                    directories = []
                    cursor = 0
                    while cursor < len(argument):
                        if argument[cursor].isspace():
                            cursor += 1
                            continue
                        value, cursor = _group(argument, cursor, "{", "}")
                        directory = _literal_path(value.strip())
                        self._candidate(directory)
                        directories.append(directory)
                    graphics[:] = directories
                elif command in {"input", "include"}:
                    dependency = self.resolve(argument, (".tex",))
                    assert dependency is not None
                    self.scan(dependency, graphics)
                elif command == "includegraphics":
                    dependency = self.resolve(argument, GRAPHICS_EXTENSIONS, [Path("."), *graphics])
                    assert dependency is not None
                    self.files.add(dependency)
                elif command == "bibliography":
                    for name in argument.split(","):
                        dependency = self.resolve(name.strip(), (".bib",))
                        assert dependency is not None
                        self.files.add(dependency)
                else:
                    suffix = ".bst" if command == "bibliographystyle" else (
                        ".cls" if command in {"documentclass", "LoadClass", "LoadClassWithOptions"}
                        else ".sty"
                    )
                    for name in argument.split(","):
                        dependency = self.resolve(name.strip(), (suffix,), optional=True)
                        if dependency is not None:
                            if suffix == ".bst":
                                self.files.add(dependency)
                            else:
                                self.scan(dependency, graphics, support=True)
        except UnicodeError as error:
            raise ExportacaoOverleafError(f"Source is not valid UTF-8: {path}") from error
        finally:
            self.active.remove(path)


def coletar_dependencias(origem: str | Path) -> list[Path]:
    """Return sorted source-relative paths needed by both official entrypoints."""
    root = Path(origem).resolve()
    if not root.is_dir():
        raise ExportacaoOverleafError(f"Source directory not found: {root}")
    collector = _Collector(root)
    for entrypoint in ENTRYPOINTS:
        path = collector.resolve(entrypoint, (".tex",))
        assert path is not None
        # Each document has its own package-loading and graphicspath state.
        collector.loaded_support.clear()
        collector.scan(path, [])
    return sorted((p.relative_to(root) for p in collector.files), key=lambda p: p.as_posix())


def preparar_overleaf(origem: str | Path, destino: str | Path) -> list[Path]:
    """Preflight all dependencies, then copy into a new or empty directory."""
    source = Path(origem).resolve()
    destination = Path(destino).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ExportacaoOverleafError(f"Destination must be new or empty: {destination}")
    if destination == source:
        raise ExportacaoOverleafError("Source and destination must differ.")
    files = coletar_dependencias(source)
    # Verify readability before creating any output; preserve source bytes exactly.
    contents = {relative: (source / relative).read_bytes() for relative in files}
    destination.mkdir(parents=True, exist_ok=True)
    if any(destination.iterdir()):
        raise ExportacaoOverleafError(f"Destination became occupied: {destination}")
    for relative, content in contents.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as output:
            output.write(content)
    return files


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origem", type=Path, default=REPOSITORY_ROOT / "artigos/revista_unificado")
    parser.add_argument("--destino", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        copied = preparar_overleaf(arguments.origem, arguments.destino)
    except (ExportacaoOverleafError, OSError) as error:
        parser.error(str(error))
    print(f"Exported {len(copied)} required files to {arguments.destino.resolve()}")
    print("Entrypoints: " + ", ".join(ENTRYPOINTS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
