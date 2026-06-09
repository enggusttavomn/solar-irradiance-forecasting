"""Construcao, ajuste e persistencia dos modelos de previsao."""

from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor


def treinar_xgboost(X_train: pd.DataFrame, y_train: pd.Series) -> XGBRegressor:
    """Treina um XGBoost para regressao sobre as features temporais.

    Args:
        X_train: Matriz de features de treino.
        y_train: Serie alvo de treino.

    Returns:
        Modelo XGBoost treinado.
    """
    model = XGBRegressor(
        n_estimators=300,  # Quantidade de arvores adicionadas ao conjunto.
        max_depth=3,  # Limita a complexidade de cada arvore.
        learning_rate=0.05,  # Faz cada arvore corrigir o modelo gradualmente.
        subsample=0.9,  # Usa 90% das linhas em cada arvore para regularizar.
        colsample_bytree=0.9,  # Usa 90% das features em cada arvore.
        objective="reg:squarederror",
        random_state=42,  # Torna a aleatoriedade reproduzivel.
        n_jobs=-1,  # Permite usar todos os nucleos disponiveis.
    )
    # ``fit`` ajusta as arvores usando somente o conjunto de treinamento.
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
        # Duas camadas ocultas: a primeira com 64 e a segunda com 32 neuronios.
        hidden_layer_sizes=(64, 32),
        activation="relu",
        solver="adam",
        max_iter=1000,
        random_state=42,
        learning_rate_init=0.001,
    )
    # A MLP recebe as mesmas sete features e o mesmo alvo do XGBoost.
    model.fit(X_train, y_train)
    return model


def salvar_modelo(model, output_path: str | Path) -> None:
    """Salva um modelo treinado em disco com joblib.

    Args:
        model: Modelo treinado.
        output_path: Caminho de destino do arquivo ``.joblib``.
    """
    # ``joblib`` preserva o objeto ajustado para uso posterior sem novo treino.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output_path)
