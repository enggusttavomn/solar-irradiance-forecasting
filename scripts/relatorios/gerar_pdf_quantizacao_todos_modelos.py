"""Ponto de entrada organizado para o relatório de todos os modelos."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.gerar_pdf_quantizacao_todos_modelos")


if __name__ == "__main__":
    main()
