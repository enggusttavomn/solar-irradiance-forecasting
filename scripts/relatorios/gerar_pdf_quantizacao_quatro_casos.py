"""Ponto de entrada organizado para o relatório das quatro tarefas."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.gerar_pdf_quantizacao_quatro_casos")


if __name__ == "__main__":
    main()
