"""Ponto de entrada organizado para a coleta horária NSRDB."""

from scripts._entrada import executar


def main() -> None:
    executar("executaveis.coletar_dados_horarios_nsrdb")


if __name__ == "__main__":
    main()
