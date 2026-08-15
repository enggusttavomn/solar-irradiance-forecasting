"""Perceptron multicamadas global aplicado aos atributos tabulares."""

from codigo_fonte.modelos_tabulares_globais import (
    salvar_modelo_joblib,
    treinar_mlp_global,
)


treinar = treinar_mlp_global
salvar = salvar_modelo_joblib

__all__ = ["salvar", "treinar"]
