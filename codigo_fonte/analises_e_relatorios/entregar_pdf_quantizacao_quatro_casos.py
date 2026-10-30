"""Entrega o PDF conferido e registra a preservacao da versao anterior."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
REL = ROOT / "resultados/relatorios/quantizacao_timesnet_quatro_casos_20260927"


def ler(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    manifesto = ler(REL / "manifesto_pdf.json")
    auditoria = ler(REL / "auditoria_quantizacao_resolucoes.json")
    visual = ler(REL / "verificacao_visual_pdf.json")
    assert auditoria["ok"] is True and auditoria["checkpoints_verificados"] == 48
    assert auditoria["smoke"] is False and auditoria["reproduz_checkpoints"] is True
    assert manifesto["verificacao_pdf"]["aprovado"] is True
    origem = Path(manifesto["pdf"]["path"])
    backup = Path(manifesto["pdf_original"]["path"])
    final = ROOT / "documentacao/tabela_resultados_ghi_2024.pdf"
    digest = sha(origem)
    assert digest == manifesto["pdf"]["sha256"]
    assert visual["aprovado"] is True and visual["paginas_verificadas"] == list(range(1, 9))
    assert visual["pdf_sha256"] == digest
    anterior = sha(backup)
    assert anterior == manifesto["pdf_original"]["sha256"]
    snapshot = ler(REL / "snapshot_anteriores.json")
    assert snapshot[str(final.resolve())] == anterior
    for path, expected in snapshot.items():
        atual = sha(Path(path))
        assert atual == expected or (Path(path).resolve() == final.resolve() and atual == digest), path
    destino_tmp = final.with_name(final.stem + ".novo.pdf")
    shutil.copyfile(origem, destino_tmp)
    assert sha(destino_tmp) == digest
    destino_tmp.replace(final)
    registro = {
        "entregue_em_utc": datetime.now(timezone.utc).isoformat(),
        "pdf": {"path": str(final.resolve()), "sha256": sha(final), "paginas": 8},
        "pdf_anterior": {"path": str(backup.resolve()), "sha256": anterior, "paginas": 6},
        "conferencias": {str((REL / name).resolve()): sha(REL / name) for name in
            ("manifesto_pdf.json", "auditoria_quantizacao_resolucoes.json", "verificacao_visual_pdf.json")},
    }
    (REL / "entrega_pdf.json").write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(registro["pdf"], ensure_ascii=False))


if __name__ == "__main__":
    main()
