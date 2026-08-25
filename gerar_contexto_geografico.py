"""Gera o contexto geográfico e climático auditável do artigo unificado."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from codigo_fonte.contexto_geografico import (
    CSV_CONTEXTO_PADRAO,
    DIRETORIO_KOPPEN_PADRAO,
    MAPA_PDF_PADRAO,
    MAPA_PNG_PADRAO,
    construir_contexto_geografico,
    gerar_mapa_contexto,
    salvar_contexto_csv,
)


def criar_parser() -> argparse.ArgumentParser:
    """Cria a interface de linha de comando do pipeline geográfico."""

    parser = argparse.ArgumentParser(
        description=(
            "Amostra Köppen–Geiger presente de 1 km nas localidades EV e "
            "gera CSV e mapa a partir dos GeoTIFFs locais."
        )
    )
    parser.add_argument(
        "--diretorio-koppen",
        type=Path,
        default=DIRETORIO_KOPPEN_PADRAO,
        help="Diretório local Beck_KG_V1 (nenhum download é realizado).",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_CONTEXTO_PADRAO,
        help="Destino do CSV auditável.",
    )
    parser.add_argument(
        "--mapa-png",
        type=Path,
        default=MAPA_PNG_PADRAO,
        help="Destino do mapa PNG.",
    )
    parser.add_argument(
        "--mapa-pdf",
        type=Path,
        default=MAPA_PDF_PADRAO,
        help="Destino do mapa PDF vetorial/rasterizado.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="Resolução do PNG; mínimo de 72 (padrão: 300).",
    )
    parser.add_argument(
        "--sem-mapa",
        action="store_true",
        help="Gera somente o CSV, sem renderizar PNG/PDF.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Executa o pipeline e apresenta um resumo reprodutível."""

    argumentos = criar_parser().parse_args(argv)
    tabela = construir_contexto_geografico(
        diretorio_koppen=argumentos.diretorio_koppen
    )
    caminho_csv = salvar_contexto_csv(tabela, argumentos.csv)

    classes = ", ".join(
        f"{codigo} ({quantidade})"
        for codigo, quantidade in tabela["classe_codigo"]
        .value_counts()
        .sort_index()
        .items()
    )
    print(f"CSV: {caminho_csv.resolve()}")
    print(f"Localidades: {len(tabela)}")
    print(f"Classes: {classes}")
    print(
        "Confiança Köppen–Geiger: "
        f"{tabela['confianca_pct'].min():.0f}%--"
        f"{tabela['confianca_pct'].max():.0f}%"
    )

    if argumentos.sem_mapa:
        print("Mapas: não gerados (--sem-mapa).")
        return 0

    caminho_png, caminho_pdf = gerar_mapa_contexto(
        tabela,
        diretorio_koppen=argumentos.diretorio_koppen,
        caminho_png=argumentos.mapa_png,
        caminho_pdf=argumentos.mapa_pdf,
        dpi=argumentos.dpi,
    )
    print(f"Mapa PNG: {caminho_png.resolve()}")
    print(f"Mapa PDF: {caminho_pdf.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
