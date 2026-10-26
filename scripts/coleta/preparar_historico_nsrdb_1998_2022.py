"""Ponto de entrada organizado para a preparação do histórico NSRDB."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.preparar_historico_nsrdb_1998_2022")


if __name__ == "__main__":
    main()
