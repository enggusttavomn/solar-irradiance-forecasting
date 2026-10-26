"""Ponto de entrada organizado para a busca mensal da TimesNet."""

from scripts._entrada import executar


def main() -> None:
    executar("scripts.otimizar_timesnet_mensal")


if __name__ == "__main__":
    main()
