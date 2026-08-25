"""CLI para gerar tabelas, figuras e manifesto auditavel do artigo unificado."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from codigo_fonte.artefatos_artigo_unificado import (
    gerar_artefatos_artigo_unificado,
)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Valida execucoes multirresolucao completas e produz, em uma pasta nova, "
            "tabelas CSV/LaTeX, figuras PNG/PDF e manifesto SHA-256."
        )
    )
    parser.add_argument(
        "--entrada",
        action="append",
        default=None,
        help=(
            "Pasta de uma tarefa ou raiz que contenha tarefas. Pode ser repetida. "
            "Padrao: resultados/avaliacao_multirresolucao."
        ),
    )
    parser.add_argument(
        "--contexto-nasa",
        type=Path,
        default=Path("resultados/artigo_revista_unificado/contexto_meteorologico_2024.csv"),
        help="CSV diario independente da NASA POWER em LST.",
    )
    parser.add_argument(
        "--manifesto-contexto-nasa",
        type=Path,
        default=Path(
            "resultados/artigo_revista_unificado/contexto_meteorologico_2024_manifesto.json"
        ),
        help="Manifesto do CSV/contexto NASA POWER.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("resultados/artigo_revista_unificado/artefatos_resultados"),
        help="Pasta nova de destino; uma pasta existente nunca e sobrescrita.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=200_000,
        help="Numero de linhas por bloco ao auditar previsoes largas (padrao: 200000).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    argumentos = construir_parser().parse_args(argv)
    entradas = argumentos.entrada or ["resultados/avaliacao_multirresolucao"]
    resumo = gerar_artefatos_artigo_unificado(
        pastas_tarefas=entradas,
        caminho_contexto_nasa=argumentos.contexto_nasa,
        caminho_manifesto_contexto_nasa=argumentos.manifesto_contexto_nasa,
        pasta_saida=argumentos.saida,
        chunksize=argumentos.chunksize,
    )
    print(f"Artefatos gerados em: {resumo['pasta_saida']}")
    print(f"Tarefas: {', '.join(resumo['tarefas'])}")
    print(f"Arquivos manifestados: {resumo['artefatos_manifestados']}")
    for limitacao in resumo["limitacoes"]:
        print(f"Limitacao declarada: {limitacao}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
