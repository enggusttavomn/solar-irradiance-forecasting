"""Entrada para a busca mensal isolada da TimesNet."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from codigo_fonte.otimizacao_timesnet_mensal import main


if __name__ == "__main__":
    raise SystemExit(main())
