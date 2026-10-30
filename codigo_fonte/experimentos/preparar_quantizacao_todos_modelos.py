"""Preserva as fontes e o PDF antes da extensao de quantizacao aos concorrentes."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

RAIZ = Path(__file__).resolve().parents[2]
REL = RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    REL.mkdir(parents=True, exist_ok=True)
    destino = REL / "snapshot_anteriores.json"
    if destino.exists():
        print("Snapshot anterior preservado; nenhuma fonte sobrescrita.")
        return
    paths = set()
    anterior = RAIZ / "resultados/relatorios/quantizacao_timesnet_quatro_casos_20260927/snapshot_anteriores.json"
    if anterior.exists():
        paths.update(Path(p) for p in json.loads(anterior.read_text(encoding="utf-8")))
    for pasta in (
        "codigo_fonte", "executaveis", "testes", "scripts",
        "resultados/quantizacao_timesnet_resolucoes_20260927",
        "resultados/quantizacao_timesnet_mensal_20260923",
        "resultados/avaliacao_baselines_revisao_20260912",
    ):
        paths.update(p for p in (RAIZ / pasta).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts
                     and p.suffix not in {".log", ".lock", ".pyc"})
    pdf = RAIZ / "documentacao/tabela_resultados_ghi_2024.pdf"
    paths.add(pdf)
    paths.update((RAIZ / "documentacao").glob("*QUANTIZACAO*.md"))
    faltantes = sorted(str(p) for p in paths if not p.is_file())
    if faltantes:
        raise FileNotFoundError(f"Fonte historica ausente: {faltantes[:5]}")
    hashes = {str(p.resolve()): sha256(p) for p in sorted(paths)}
    backup = REL / "tabela_resultados_ghi_2024_anterior.pdf"
    if backup.exists() and sha256(backup) != hashes[str(pdf.resolve())]:
        raise ValueError("Backup existente diverge; nao sobrescrito.")
    if not backup.exists():
        shutil.copyfile(pdf, backup)
    if sha256(backup) != hashes[str(pdf.resolve())]:
        raise ValueError("Backup PDF nao reproduziu os bytes logicos autorizados.")
    payload = {"criado_em_utc": datetime.now(timezone.utc).isoformat(),
               "escopo_hash": "conteudo logico lido pelo Python autorizado; PDF permanece protegido",
               "arquivos": hashes, "backup_pdf": str(backup.resolve())}
    destino.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"arquivos_preservados": len(hashes), "snapshot": str(destino),
                      "pdf_sha256": hashes[str(pdf.resolve())]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
