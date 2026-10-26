"""Ponto de entrada organizado para reconstruir as figuras oficiais."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.gerar_figuras")


if __name__ == "__main__":
    main()
