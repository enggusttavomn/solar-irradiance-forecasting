"""Entrega somente PDF auditado e revisado, preservando os resultados anteriores."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import time

from scripts.metricas_quantizacao_todos import sha256

RAIZ = Path(__file__).resolve().parents[1]
REL = RAIZ / "relatorios/quantizacao_todos_modelos_20260929"
NOMES_ENTREGA = {'tabela_resultados_ghi_2024.pdf', 'tabela_resultados_ghi_1998_2022.pdf'}


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exigir(ok, mensagem):
    if not ok:
        raise ValueError(mensagem)


def caminho_pdf_logico(path):
    """Preserva a extensao documental e o acesso autorizado pelo provedor local."""
    path = Path(path)
    exigir(path.suffix.casefold() == '.pdf', 'O PDF deve usar seu caminho logico com extensao .pdf.')
    return path.parent.resolve() / path.name


def validar_destino(path):
    destino = caminho_pdf_logico(path)
    # RAIZ ja e canonico. Resolver somente o pai impede que o provedor substitua
    # o nome documental por um temporario .nsc e ainda rejeita pais fora daqui.
    exigir(destino.parent == RAIZ / 'documentacao' and destino.name in NOMES_ENTREGA,
           'Destino fora das duas entregas previstas.')
    return destino


def substituir_pdf_com_espera(temporario, destino):
    """Espera no maximo dez segundos por compartilhamento/bloqueio do Windows."""
    limite = time.monotonic() + 10.0
    while True:
        try:
            return temporario.replace(destino)
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (32, 33):
                raise
            restante = limite - time.monotonic()
            if restante <= 0:
                raise
            time.sleep(min(0.25, restante))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifesto", type=Path, required=True)
    ap.add_argument("--visual", type=Path, required=True)
    ap.add_argument("--destino", type=Path, required=True)
    ap.add_argument("--registro", type=Path, required=True)
    args = ap.parse_args()
    destino = validar_destino(args.destino)
    manifesto, visual = ler(args.manifesto), ler(args.visual)
    origem = caminho_pdf_logico(manifesto["pdf"]["path"])
    digest = manifesto["pdf"]["sha256"]
    exigir(sha256(origem) == digest, "PDF mudou depois da geracao.")
    exigir(visual["aprovado"] is True and visual["pdf_sha256"] == digest, "Revisao visual nao aprovada.")
    exigir(visual["paginas_verificadas"] == list(range(1, manifesto["pdf"]["paginas"] + 1)), "Faltam paginas na revisao.")
    for fonte in manifesto["fontes"]:
        exigir(sha256(Path(fonte["path"])) == fonte["sha256"], f"Fonte alterada: {fonte['path']}")
    snapshot = ler(REL / "snapshot_anteriores.json")
    original = validar_destino(RAIZ / "documentacao/tabela_resultados_ghi_2024.pdf")
    chave_original = str(original)
    exigir(chave_original in snapshot['arquivos'], 'Snapshot sem a chave logica do PDF original.')
    digest_original = snapshot['arquivos'][chave_original]
    backup = caminho_pdf_logico(snapshot["backup_pdf"])
    exigir(sha256(backup) == digest_original, "Copia anterior diverge.")
    anterior = None
    if destino.exists():
        anterior = sha256(destino)
        if destino == original:
            exigir(anterior in {digest_original, digest}, "PDF atual modificado fora desta entrega.")
        else:
            exigir(anterior == digest, "PDF historico ja existente tem outro conteudo.")
    if anterior != digest:
        # A extensao final precisa permanecer .pdf para o formato documental local.
        temporario = destino.with_name(destino.stem + ".novo.pdf")
        shutil.copyfile(origem, temporario)
        exigir(sha256(temporario) == digest, "Copia de entrega divergente.")
        substituir_pdf_com_espera(temporario, destino)
    exigir(sha256(destino) == digest, "Arquivo final divergente.")
    args.registro.parent.mkdir(parents=True, exist_ok=True)
    args.registro.write_text(json.dumps({"entregue_em_utc": datetime.now(timezone.utc).isoformat(),
        "pdf": {"path": str(destino), "sha256": digest, "paginas": manifesto["pdf"]["paginas"]},
        "pdf_anterior_sha256": anterior, "backup_pdf_2024": str(backup),
        "evidencias": {str(args.manifesto.resolve()): sha256(args.manifesto),
                       str(args.visual.resolve()): sha256(args.visual)}},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"PDF conferido entregue: {destino}")


if __name__ == "__main__":
    main()
