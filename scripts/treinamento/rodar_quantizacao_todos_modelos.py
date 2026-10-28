"""Ponto de entrada organizado para a quantização de todos os modelos."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.rodar_quantizacao_todos_modelos")


if __name__ == "__main__":
    main()
