"""Referencia baseada na media historica de cada mes e localidade."""

import numpy as np

from codigo_fonte.dados_mensais_globais import BaseMensalGlobal
from codigo_fonte.modelos_tabulares_globais import prever_baselines_mensais


def prever(base: BaseMensalGlobal) -> np.ndarray:
    """Preve pela climatologia mensal calculada apenas nos alvos de treino."""

    return prever_baselines_mensais(base)["Climatologia"]


__all__ = ["prever"]
