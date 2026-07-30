"""Linha de comando para recuperar as séries horárias públicas da NSRDB."""

from __future__ import annotations

import argparse

from codigo_fonte.dados_horarios_nsrdb import (
    PASTA_HORARIA_PADRAO,
    coletar_periodo_horario,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inicio", type=int, default=2019)
    parser.add_argument("--fim", type=int, default=2024)
    parser.add_argument("--saida", default=str(PASTA_HORARIA_PADRAO))
    parser.add_argument("--sobrescrever", action="store_true")
    args = parser.parse_args()
    if args.fim < args.inicio:
        parser.error("--fim deve ser maior ou igual a --inicio.")

    caminhos = coletar_periodo_horario(
        range(args.inicio, args.fim + 1),
        pasta_saida=args.saida,
        sobrescrever=args.sobrescrever,
    )
    for caminho in caminhos:
        print(caminho)


if __name__ == "__main__":
    main()
