"""CLI para gerar tabelas, figuras e manifesto auditavel do artigo unificado."""

from __future__ import annotations


# Permite executar este arquivo diretamente a partir de ``executaveis/``,
# mantendo a raiz do repositorio disponivel para importar ``codigo_fonte``.
import sys as _sys
from pathlib import Path as _Path

_RAIZ_REPOSITORIO = _Path(__file__).resolve().parents[1]
if str(_RAIZ_REPOSITORIO) not in _sys.path:
    _sys.path.insert(0, str(_RAIZ_REPOSITORIO))

import argparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from codigo_fonte.artefatos_artigo_unificado import (
    gerar_artefatos_artigo_unificado,
)


PASTA_ENTRADA_PADRAO = Path("resultados/avaliacao_multirresolucao_corrigida_v2")


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
            f"Padrao: {PASTA_ENTRADA_PADRAO.as_posix()}."
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
        default=None,
        help=(
            "Pasta nova de destino; uma pasta existente nunca e sobrescrita. "
            "Padrao: resultados/artigo_revista_unificado/"
            "artefatos_resultados_corrigidos_<timestamp UTC>."
        ),
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
    entradas = argumentos.entrada or [PASTA_ENTRADA_PADRAO]
    saida = argumentos.saida
    if saida is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        saida = Path("resultados/artigo_revista_unificado") / (
            f"artefatos_resultados_corrigidos_{timestamp}"
        )
    resumo = gerar_artefatos_artigo_unificado(
        pastas_tarefas=entradas,
        caminho_contexto_nasa=argumentos.contexto_nasa,
        caminho_manifesto_contexto_nasa=argumentos.manifesto_contexto_nasa,
        pasta_saida=saida,
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
