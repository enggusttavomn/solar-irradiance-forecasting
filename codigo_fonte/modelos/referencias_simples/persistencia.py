"""Referencia que repete a GHI observada no mes imediatamente anterior."""

import numpy as np

from codigo_fonte.dados_mensais_globais import BaseMensalGlobal
from codigo_fonte.modelos_tabulares_globais import prever_baselines_mensais


def prever(base: BaseMensalGlobal) -> np.ndarray:
    """Preve cada alvo usando o ultimo mes disponivel em W/m2."""

    return prever_baselines_mensais(base)["Persistencia"]


__all__ = ["prever"]
