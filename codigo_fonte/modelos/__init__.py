"""Compatibilidade dos modelos exploratorios e pacote dos modelos atuais.

A API historica deste arquivo foi preservada para os fluxos anteriores. Os
dez metodos do protocolo mensal atual ficam nos subpacotes
``referencias_simples``, ``tabulares``, ``recorrentes`` e
``probabilisticos``, com um arquivo publico por modelo.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import joblib
import numpy as np
import pandas as pd
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor


def _configuracao_xgboost(random_state: int, n_estimators: int) -> dict:
    """Configuracao regularizada adequada a amostras temporais pequenas."""
    return {
        "n_estimators": n_estimators,
        "max_depth": 2,
        "learning_rate": 0.03,
        "min_child_weight": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 10.0,
        "objective": "reg:squarederror",
        "eval_metric": "mae",
        "random_state": random_state,
        "n_jobs": -1,
    }


def treinar_xgboost(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = 42,
) -> XGBRegressor:
    """Treina um XGBoost para regressao sobre as features temporais.

    Args:
        X_train: Matriz de features de treino.
        y_train: Serie alvo de treino.

    Returns:
        Modelo XGBoost treinado.
    """
    # A quantidade de arvores e escolhida em um bloco cronologico final do
    # proprio treino. Em seguida, o estimador e reajustado em todo o treino;
    # o conjunto de teste nunca participa dessa escolha.
    n_estimators = 120
    if len(X_train) >= 30:
        corte_validacao = max(1, int(len(X_train) * 0.8))
        selector = XGBRegressor(
            **_configuracao_xgboost(random_state, n_estimators=600),
            early_stopping_rounds=30,
        )
        selector.fit(
            X_train.iloc[:corte_validacao],
            y_train.iloc[:corte_validacao],
            eval_set=[
                (X_train.iloc[corte_validacao:], y_train.iloc[corte_validacao:])
            ],
            verbose=False,
        )
        if getattr(selector, "best_iteration", None) is not None:
            n_estimators = max(1, int(selector.best_iteration) + 1)

    model = XGBRegressor(**_configuracao_xgboost(random_state, n_estimators))
    model.fit(X_train, y_train)
    return model


def treinar_mlp(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = 42,
) -> MLPRegressor:
    """Treina uma rede neural MLPRegressor usando as mesmas features do XGBoost.

    Args:
        X_train: Matriz de features de treino.
        y_train: Serie alvo de treino.

    Returns:
        Modelo MLP treinado.
    """
    model = MLPRegressor(
        # Uma camada pequena e L2 forte reduzem a variancia diante da amostra
        # mensal curta.
        hidden_layer_sizes=(8,),
        activation="relu",
        solver="lbfgs",
        alpha=0.05,
        max_iter=2000,
        random_state=random_state,
    )
    model.fit(X_train, y_train)
    return model


class VizinhosHistoricosPonderados:
    """Regressor deterministico de analogos historicos locais.

    Esta implementacao e um suavizador por vizinhos, nao DeepNPTS. As features
    sao padronizadas com estatisticas do treino, ``k`` cresce como raiz da
    amostra e a largura do nucleo e definida pelas distancias observadas. Assim,
    nao ha hiperparametro escolhido olhando o teste.
    """

    def __init__(self, k: int | None = None) -> None:
        self.k = k
        self.X_train_: np.ndarray | None = None
        self.y_train_: np.ndarray | None = None
        self.media_: np.ndarray | None = None
        self.escala_: np.ndarray | None = None
        self.feature_names_in_: list[str] | None = None

    def fit(
        self,
        X_train: pd.DataFrame | np.ndarray,
        y_train: pd.Series | np.ndarray,
    ) -> "VizinhosHistoricosPonderados":
        valores = np.asarray(X_train, dtype=float)
        alvos = np.asarray(y_train, dtype=float).ravel()
        if valores.ndim != 2 or len(valores) != len(alvos) or len(alvos) == 0:
            raise ValueError("X_train e y_train devem conter a mesma amostra nao vazia.")
        if self.k is not None and self.k < 1:
            raise ValueError("k deve ser positivo ou None.")
        self.feature_names_in_ = (
            list(map(str, X_train.columns)) if isinstance(X_train, pd.DataFrame) else None
        )
        self.media_ = valores.mean(axis=0)
        self.escala_ = valores.std(axis=0)
        self.escala_[np.isclose(self.escala_, 0.0)] = 1.0
        self.X_train_ = (valores - self.media_) / self.escala_
        self.y_train_ = alvos
        return self

    def predict(self, X_test: pd.DataFrame | np.ndarray) -> np.ndarray:
        if any(
            valor is None
            for valor in (self.X_train_, self.y_train_, self.media_, self.escala_)
        ):
            raise RuntimeError("O regressor precisa ser treinado antes da previsao.")
        if isinstance(X_test, pd.DataFrame) and self.feature_names_in_ is not None:
            faltantes = sorted(set(self.feature_names_in_) - set(map(str, X_test.columns)))
            if faltantes:
                raise ValueError(f"Features ausentes: {', '.join(faltantes)}")
            valores = X_test[self.feature_names_in_].to_numpy(dtype=float)
        else:
            valores = np.asarray(X_test, dtype=float)
        if valores.ndim != 2 or valores.shape[1] != self.X_train_.shape[1]:
            raise ValueError("X_test deve ter o mesmo numero de features do treino.")

        valores = (valores - self.media_) / self.escala_
        k = min(self.k or int(np.ceil(np.sqrt(len(self.y_train_)))), len(self.y_train_))
        previsoes = []
        for linha in valores:
            distancias = np.linalg.norm(self.X_train_ - linha, axis=1)
            indices = np.argsort(distancias, kind="stable")[:k]
            distancias_k = distancias[indices]
            if np.isclose(distancias_k[0], 0.0):
                iguais = indices[np.isclose(distancias_k, 0.0)]
                previsoes.append(float(np.mean(self.y_train_[iguais])))
                continue
            largura = max(float(np.median(distancias_k)), np.finfo(float).eps)
            pesos = np.exp(-0.5 * np.square(distancias_k / largura))
            previsoes.append(float(np.average(self.y_train_[indices], weights=pesos)))
        return np.asarray(previsoes)


def treinar_vizinhos_historicos(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = 42,
) -> VizinhosHistoricosPonderados:
    """Ajusta o baseline aprendido; ``random_state`` mantem API uniforme."""
    del random_state
    return VizinhosHistoricosPonderados().fit(X_train, y_train)


class KerasSequenceRegressor:
    """Adaptador simples para treinar RNN/LSTM com a interface ``fit/predict``.

    Somente as colunas de lag ``ghi_t-k`` formam a sequencia, ordenadas do
    instante mais antigo para o mais recente. Medias moveis e calendario nao sao
    reinterpretados como passos, pois nao constituem uma sequencia temporal.
    """

    def __init__(
        self,
        tipo: str,
        units: int = 4,
        dense_units: int = 4,
        epochs: int = 120,
        batch_size: int = 16,
        learning_rate: float = 0.001,
        validation_split: float = 0.2,
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
        self.sequence_columns_: list[str] | None = None

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
    def _ordenar_colunas_lag(colunas) -> list[str]:
        """Ordena ``t-12,...,t-1`` para apresentar passado -> presente."""
        pares = []
        for coluna in colunas:
            match = re.fullmatch(r"ghi_t-(\d+)", str(coluna))
            if match:
                pares.append((int(match.group(1)), str(coluna)))
        return [coluna for _, coluna in sorted(pares, reverse=True)]

    @staticmethod
    def _reshape(X: pd.DataFrame | np.ndarray) -> np.ndarray:
        if isinstance(X, pd.DataFrame):
            sequence_columns = KerasSequenceRegressor._ordenar_colunas_lag(X.columns)
            if not sequence_columns:
                raise ValueError("Nenhuma coluna de lag no formato ghi_t-k foi encontrada.")
            valores = X[sequence_columns].to_numpy(dtype=np.float32)
        else:
            valores = np.asarray(X, dtype=np.float32)
        if valores.ndim != 2:
            raise ValueError("A entrada dos modelos recorrentes deve ser uma matriz 2D.")
        return valores.reshape((valores.shape[0], valores.shape[1], 1))

    def _preparar_entrada(
        self,
        X: pd.DataFrame | np.ndarray,
        *,
        ajustar: bool = False,
    ) -> np.ndarray:
        if isinstance(X, pd.DataFrame):
            colunas = self._ordenar_colunas_lag(X.columns)
            if ajustar:
                self.sequence_columns_ = colunas
            elif self.sequence_columns_ is not None and colunas != self.sequence_columns_:
                raise ValueError("As colunas de lag da previsao diferem das usadas no treino.")
        return self._reshape(X)

    def fit(self, X_train: pd.DataFrame, y_train: pd.Series) -> "KerasSequenceRegressor":
        tf = self._tensorflow()
        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(self.random_state)
        try:
            tf.config.experimental.enable_op_determinism()
        except (AttributeError, RuntimeError):
            pass

        X_seq = self._preparar_entrada(X_train, ajustar=True)
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
        if len(X_seq) >= 24 and self.validation_split > 0:
            callbacks.append(
                tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=15,
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
        X_seq = self._preparar_entrada(X_test)
        return self.model_.predict(X_seq, verbose=0).ravel()

    def save(self, output_path: str | Path) -> None:
        if self.model_ is None:
            raise RuntimeError("Nao ha modelo recorrente treinado para salvar.")
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        self.model_.save(str(output_path))
        output_path.with_suffix(".metadata.json").write_text(
            json.dumps(
                {
                    "tipo": self.tipo,
                    "sequence_columns": self.sequence_columns_,
                    "units": self.units,
                    "dense_units": self.dense_units,
                    "random_state": self.random_state,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )


def treinar_rnn(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = 42,
) -> KerasSequenceRegressor:
    """Treina uma rede neural recorrente simples (SimpleRNN)."""
    return KerasSequenceRegressor("RNN", random_state=random_state).fit(X_train, y_train)


def treinar_lstm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    random_state: int = 42,
) -> KerasSequenceRegressor:
    """Treina uma rede LSTM para regressao da GHI normalizada."""
    return KerasSequenceRegressor("LSTM", random_state=random_state).fit(X_train, y_train)


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
