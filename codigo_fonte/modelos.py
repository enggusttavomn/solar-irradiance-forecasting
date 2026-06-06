"""Treinamento e salvamento dos modelos de previsao de GHI."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor


def treinar_xgboost(X_train: pd.DataFrame, y_train: pd.Series) -> XGBRegressor:
    """Treina um modelo XGBRegressor com hiperparametros iniciais simples.

    Args:
        X_train: Matriz de features de treino.
        y_train: Serie alvo de treino.

    Returns:
        Modelo XGBoost treinado.
    """
    model = XGBRegressor(
        n_estimators=300,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.9,
        objective="reg:squarederror",
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    return model


def treinar_mlp(X_train: pd.DataFrame, y_train: pd.Series) -> MLPRegressor:
    """Treina uma rede neural MLPRegressor usando as mesmas features do XGBoost.

    Args:
        X_train: Matriz de features de treino.
        y_train: Serie alvo de treino.

    Returns:
        Modelo MLP treinado.
    """
    model = MLPRegressor(
        hidden_layer_sizes=(64, 32),
        activation="relu",
        solver="adam",
        max_iter=1000,
        random_state=42,
        learning_rate_init=0.001,
    )
    model.fit(X_train, y_train)
    return model


def salvar_modelo(model, output_path: str | Path) -> None:
    """Salva um modelo treinado em disco com joblib.

    Args:
        model: Modelo treinado.
        output_path: Caminho de destino do arquivo ``.joblib``.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
