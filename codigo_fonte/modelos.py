"""Construcao, ajuste e persistencia dos modelos de previsao."""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
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


class KerasSequenceRegressor:
    """Adaptador simples para treinar RNN/LSTM com a interface ``fit/predict``.

    As features tabulares do pipeline sao reinterpretadas como uma sequencia curta
    de sete passos, com uma variavel por passo. Isso permite comparar modelos
    recorrentes usando exatamente o mesmo corte temporal e o mesmo alvo dos
    demais regressores.
    """

    def __init__(
        self,
        tipo: str,
        units: int = 32,
        dense_units: int = 16,
        epochs: int = 80,
        batch_size: int = 32,
        learning_rate: float = 0.001,
        validation_split: float = 0.15,
        random_state: int = 42,
        verbose: int = 0,
    ) -> None:
        self.tipo = tipo.upper()
        self.units = units
        self.dense_units = dense_units
        self.epochs = epochs
        self.batch_size = batch_size
        self.learning_rate = learning_rate
        self.validation_split = validation_split
        self.random_state = random_state
        self.verbose = verbose
        self.model_ = None
        self.n_features_in_: int | None = None

    @staticmethod
    def _tensorflow():
        try:
            import tensorflow as tf
        except ImportError as exc:
            raise ImportError(
                "TensorFlow nao esta instalado. Instale as dependencias com "
                "`pip install -r requirements.txt` para treinar RNN e LSTM."
            ) from exc
        return tf

    @staticmethod
    def _reshape(X: pd.DataFrame | np.ndarray) -> np.ndarray:
        valores = np.asarray(X, dtype=np.float32)
        if valores.ndim != 2:
            raise ValueError("A entrada dos modelos recorrentes deve ser uma matriz 2D.")
        return valores.reshape((valores.shape[0], valores.shape[1], 1))

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "KerasSequenceRegressor":
        tf = self._tensorflow()
        tf.keras.utils.set_random_seed(self.random_state)

        X_seq = self._reshape(X_train)
        y_array = np.asarray(y_train, dtype=np.float32)
        self.n_features_in_ = X_seq.shape[1]

        if self.tipo == "RNN":
            camada_recorrente = tf.keras.layers.SimpleRNN(self.units, activation="tanh")
        elif self.tipo == "LSTM":
            camada_recorrente = tf.keras.layers.LSTM(self.units, activation="tanh")
        else:
            raise ValueError("tipo deve ser 'RNN' ou 'LSTM'.")

        self.model_ = tf.keras.Sequential(
            [
                tf.keras.layers.Input(shape=(self.n_features_in_, 1)),
                camada_recorrente,
                tf.keras.layers.Dense(self.dense_units, activation="relu"),
                tf.keras.layers.Dense(1, activation="sigmoid"),
            ]
        )
        self.model_.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss="mse",
        )

        callbacks = []
        if len(X_seq) >= 50 and self.validation_split > 0:
            callbacks.append(
                tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=10,
                    restore_best_weights=True,
                )
            )

        self.model_.fit(
            X_seq,
            y_array,
            epochs=self.epochs,
            batch_size=self.batch_size,
            validation_split=self.validation_split if callbacks else 0.0,
            shuffle=False,
            callbacks=callbacks,
            verbose=self.verbose,
        )
        return self

    def predict(self, X_test: pd.DataFrame) -> np.ndarray:
        if self.model_ is None:
            raise RuntimeError("O modelo recorrente precisa ser treinado antes da previsao.")
        X_seq = self._reshape(X_test)
        return self.model_.predict(X_seq, verbose=0).ravel()

    def save(self, output_path: str | Path) -> None:
        if self.model_ is None:
            raise RuntimeError("Nao ha modelo recorrente treinado para salvar.")
        self.model_.save(str(output_path))


def treinar_rnn(X_train: pd.DataFrame, y_train: pd.Series) -> KerasSequenceRegressor:
    """Treina uma rede neural recorrente simples (SimpleRNN)."""
    return KerasSequenceRegressor("RNN").fit(X_train, y_train)


def treinar_lstm(X_train: pd.DataFrame, y_train: pd.Series) -> KerasSequenceRegressor:
    """Treina uma rede LSTM para regressao da GHI normalizada."""
    return KerasSequenceRegressor("LSTM").fit(X_train, y_train)


def salvar_modelo(model, output_path: str | Path) -> None:
    """Salva um modelo treinado em disco com joblib.

    Args:
        model: Modelo treinado.
        output_path: Caminho de destino do arquivo ``.joblib``.
    """
    # ``joblib`` preserva o objeto ajustado para uso posterior sem novo treino.
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix == ".keras" and hasattr(model, "save"):
        model.save(output_path)
    else:
        joblib.dump(model, output_path)
