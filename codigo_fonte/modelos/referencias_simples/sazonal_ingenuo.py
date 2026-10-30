"""Referencia que usa a GHI do mesmo mes do ano anterior."""

import numpy as np

from codigo_fonte.coleta_e_preparacao.base_mensal import BaseMensalGlobal
from codigo_fonte.modelos.tabulares.modelos_tabulares_globais import prever_baselines_mensais


def prever(base: BaseMensalGlobal) -> np.ndarray:
    """Preve cada alvo com a observacao de doze meses antes em W/m2."""

    return prever_baselines_mensais(base)["SazonalIngenuo"]


__all__ = ["prever"]
