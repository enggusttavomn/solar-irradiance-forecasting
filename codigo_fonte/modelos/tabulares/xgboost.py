"""XGBoost global das dez localidades."""

from codigo_fonte.modelos_tabulares_globais import (
    ResultadoXGBoostGlobal,
    salvar_modelo_joblib,
    treinar_xgboost_global,
)


treinar = treinar_xgboost_global
salvar = salvar_modelo_joblib
ResultadoTreino = ResultadoXGBoostGlobal

__all__ = ["ResultadoTreino", "salvar", "treinar"]
