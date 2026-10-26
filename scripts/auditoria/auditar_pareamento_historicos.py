"""Ponto de entrada organizado para auditar o pareamento histórico."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.auditar_pareamento_historicos")


if __name__ == "__main__":
    main()
