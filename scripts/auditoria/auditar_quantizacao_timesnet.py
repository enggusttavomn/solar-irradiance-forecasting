"""Ponto de entrada organizado para auditar a quantização mensal."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.auditar_quantizacao_timesnet")


if __name__ == "__main__":
    main()
