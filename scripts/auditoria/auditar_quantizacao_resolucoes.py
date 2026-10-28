"""Ponto de entrada organizado para auditar a quantização horária e diária."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.auditar_quantizacao_resolucoes")


if __name__ == "__main__":
    main()
