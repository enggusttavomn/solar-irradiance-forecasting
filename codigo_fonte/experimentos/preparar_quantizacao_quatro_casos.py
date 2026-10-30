"""Preserva os resultados anteriores e o PDF antes da complementacao autorizada."""
from pathlib import Path
import hashlib
import json
import shutil

RAIZ = Path(__file__).resolve().parents[2]
RELATORIO = RAIZ / "resultados/relatorios/quantizacao_timesnet_quatro_casos_20260927"


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def main():
    RELATORIO.mkdir(parents=True, exist_ok=True)
    destino = RELATORIO / "snapshot_anteriores.json"
    if destino.exists():
        fontes = json.loads(destino.read_text(encoding="utf-8"))
        for nome, esperado in fontes.items():
            if sha(Path(nome)) != esperado:
                raise ValueError(f"Fonte historica alterada: {nome}")
        print(f"Snapshot existente conferido: {len(fontes)} arquivos.")
        return
    arquivos = []
    for pasta in ("resultados/busca_timesnet_resolucoes_20260922", "resultados/busca_timesnet_mensal_20260920",
                  "resultados/quantizacao_timesnet_mensal_20260923", "resultados/relatorios/quantizacao_timesnet_20260923"):
        arquivos.extend(p for p in (RAIZ / pasta).rglob("*") if p.is_file())
    arquivos.extend(RAIZ / "codigo_fonte" / n for n in (
        "experimento_multirresolucao.py", "experimento_horario_timesnet.py", "experimento_baselines_adicionais.py",
        "otimizacao_timesnet_resolucoes.py", "treinamento_timesnet_resolucoes.py", "quantizacao_timesnet.py",
        "experimento_quantizacao_timesnet.py", "otimizacao_timesnet_mensal.py", "treinamento_timesnet_otimizacao.py"))
    pdf = RAIZ / "documentacao/tabela_resultados_ghi_2024.pdf"
    arquivos.append(pdf)
    fontes = {str(p.resolve()): sha(p) for p in sorted(set(arquivos), key=str)}
    backup = RELATORIO / "fonte_6_paginas.pdf"
    if backup.exists() and sha(backup) != sha(pdf):
        raise ValueError("Backup anterior diferente; nao sobrescrever.")
    if not backup.exists():
        shutil.copy2(pdf, backup)
    from pypdf import PdfReader
    if len(PdfReader(backup).pages) != 6:
        raise ValueError("Esperada a versao anterior com seis paginas.")
    destino.write_text(json.dumps(fontes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Snapshot salvo: {len(fontes)} arquivos; PDF6p SHA256={sha(backup)}")


if __name__ == "__main__":
    main()
