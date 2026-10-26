"""Ponto de entrada organizado para a correção de imagens dos slides."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.corrigir_apresentacao_imagens")


if __name__ == "__main__":
    main()
