"""Modelos que recebem uma matriz tabular de atributos."""

from codigo_fonte.modelos.tabulares.mlp import treinar as treinar_mlp
from codigo_fonte.modelos.tabulares.xgboost import treinar as treinar_xgboost

__all__ = ["treinar_mlp", "treinar_xgboost"]
