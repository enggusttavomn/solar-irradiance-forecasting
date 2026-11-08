"""Empacota a extensao local do EA019, sem baixar dependencias."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
from xml.etree import ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile


def build(source: Path, destination: Path) -> Path:
    package = json.loads((source / "package.json").read_text(encoding="utf-8"))
    ns = "http://schemas.microsoft.com/developer/vsx-schema/2011"
    ET.register_namespace("", ns)
    def element(name, **attributes):
        return ET.Element(f"{{{ns}}}{name}", attributes)
    manifest = element("PackageManifest", Version="2.0.0")
    metadata = ET.SubElement(manifest, f"{{{ns}}}Metadata")
    metadata.append(element("Identity", Language="en-US", Id=package["name"],
                            Version=package["version"], Publisher=package["publisher"]))
    for name, value in (("DisplayName", package["displayName"]),
                        ("Description", package["description"]), ("Categories", "Other")):
        node = element(name)
        node.text = value
        metadata.append(node)
    properties = ET.SubElement(metadata, f"{{{ns}}}Properties")
    for key, value in (("Microsoft.VisualStudio.Code.Engine", package["engines"]["vscode"]),
                       ("Microsoft.VisualStudio.Code.ExtensionKind", "workspace")):
        properties.append(element("Property", Id=key, Value=value))
    installation = ET.SubElement(manifest, f"{{{ns}}}Installation")
    installation.append(element("InstallationTarget", Id="Microsoft.VisualStudio.Code"))
    manifest.append(element("Dependencies"))
    assets = ET.SubElement(manifest, f"{{{ns}}}Assets")
    assets.append(element("Asset", Type="Microsoft.VisualStudio.Code.Manifest",
                          Path="extension/package.json", Addressable="true"))
    assets.append(element("Asset", Type="Microsoft.VisualStudio.Services.Content.Details",
                          Path="extension/README.md", Addressable="true"))
    content_types = b'<?xml version="1.0" encoding="utf-8"?>\n<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="json" ContentType="application/json"/><Default Extension="js" ContentType="application/javascript"/><Default Extension="md" ContentType="text/markdown"/><Default Extension="vsixmanifest" ContentType="text/xml"/></Types>'
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / f'{package["publisher"]}.{package["name"]}-{package["version"]}.vsix'
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("extension.vsixmanifest", ET.tostring(manifest, encoding="utf-8", xml_declaration=True))
        for name in ("package.json", "extension.js", "README.md"):
            archive.write(source / name, f"extension/{name}")
    return output


def main():
    default_source = Path(__file__).resolve().parent / "vscode_github_sync"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=default_source)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        result = subprocess.run(["git", "-C", str(args.source), "rev-parse", "--absolute-git-dir"],
                                check=True, capture_output=True, text=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        args.output = Path(result.stdout.strip()) / "auto-sync" / "vscode"
    print(build(args.source.resolve(), args.output.resolve()))


if __name__ == "__main__":
    main()
