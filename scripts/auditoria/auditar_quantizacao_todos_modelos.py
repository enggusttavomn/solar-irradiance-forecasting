"""Ponto de entrada organizado para auditar a comparação dos modelos."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.auditar_quantizacao_todos_modelos")


if __name__ == "__main__":
    main()
