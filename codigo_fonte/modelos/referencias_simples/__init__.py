"""Persistencia, sazonal ingenuo e climatologia mensal."""

from codigo_fonte.modelos.referencias_simples.climatologia import prever as prever_climatologia
from codigo_fonte.modelos.referencias_simples.persistencia import prever as prever_persistencia
from codigo_fonte.modelos.referencias_simples.sazonal_ingenuo import prever as prever_sazonal
from codigo_fonte.modelos_tabulares_globais import prever_baselines_mensais as prever_todas

__all__ = [
    "prever_climatologia",
    "prever_persistencia",
    "prever_sazonal",
    "prever_todas",
]
