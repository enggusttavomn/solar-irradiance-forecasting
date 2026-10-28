"""Ponto de entrada organizado para o painel local de treinamentos."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.painel_progresso_quantizacao")


if __name__ == "__main__":
    main()
