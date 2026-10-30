r"""DilatedRNN com conexoes recorrentes dilatadas reais.

Este modulo implementa o mecanismo central proposto por Chang et al.
(``Dilated Recurrent Neural Networks``, NeurIPS 2017). Para uma camada com
dilatacao :math:`s`, a recorrencia e

.. math::

   h_t = \phi(W_x x_t + W_h h_{t-s} + b).

Portanto, a camada consulta diretamente o estado de ``s`` instantes atras;
ela nao subamostra um vetor de atributos e nao interpreta covariaveis
heterogeneas como passos temporais. Um buffer de ``s`` estados implementa a
conexao recorrente de salto. As camadas sao empilhadas com dilatacoes
configuraveis, tipicamente ``(1, 2, 4, ...)``, formando a representacao em
multiplas resolucoes descrita no artigo.

A entrada temporal deve ser uma sequencia verdadeira com forma
``(amostras, passos, variaveis_temporais)``. Covariaveis auxiliares estaticas
ou derivadas (por exemplo, seno/cosseno do mes) sao recebidas separadamente e
concatenadas somente depois do codificador recorrente.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

try:
    import tensorflow as tf
except ImportError as exc:  # pragma: no cover - coberto pelo ambiente leve
    raise ImportError(
        "TensorFlow nao esta instalado. Instale as dependencias com "
        "`pip install -r requirements.txt` para usar a DilatedRNN."
    ) from exc


@tf.keras.utils.register_keras_serializable(package="TCC")
class DilatedSimpleRNNCell(tf.keras.layers.Layer):
    """Celula RNN vanilla cuja recorrencia aponta para ``h[t-dilation]``.

    O estado da celula e uma fila de ``dilation`` vetores. Antes de calcular
    ``h_t``, o primeiro vetor da fila e exatamente ``h_{t-dilation}``; depois
    do calculo, a fila avanca e recebe ``h_t``. Para os primeiros instantes,
    os estados inexistentes sao inicializados com zero pelo ``keras.layers.RNN``.

    Esta celula pode ser envolvida por :class:`tf.keras.layers.RNN` e segue a
    interface de celulas do Keras atual.
    """

    def __init__(
        self,
        units: int,
        dilation: int = 1,
        activation: str | Any = "tanh",
        kernel_initializer: str | Any = "glorot_uniform",
        recurrent_initializer: str | Any = "orthogonal",
        bias_initializer: str | Any = "zeros",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not isinstance(units, int) or units < 1:
            raise ValueError("units deve ser um inteiro positivo.")
        if not isinstance(dilation, int) or dilation < 1:
            raise ValueError("dilation deve ser um inteiro positivo.")

        self.units = units
        self.dilation = dilation
        self.activation = tf.keras.activations.get(activation)
        self.kernel_initializer = tf.keras.initializers.get(kernel_initializer)
        self.recurrent_initializer = tf.keras.initializers.get(
            recurrent_initializer
        )
        self.bias_initializer = tf.keras.initializers.get(bias_initializer)

        # O Keras cria um estado por entrada desta tupla. A fila contem
        # [h_{t-s}, ..., h_{t-1}] imediatamente antes de processar x_t.
        self.state_size = tuple(self.units for _ in range(self.dilation))
        self.output_size = self.units
        self.kernel = None
        self.recurrent_kernel = None
        self.bias = None

    def build(self, input_shape: tf.TensorShape) -> None:
        input_dim = input_shape[-1]
        if input_dim is None:
            raise ValueError("A dimensao das variaveis temporais deve ser conhecida.")

        self.kernel = self.add_weight(
            name="kernel",
            shape=(int(input_dim), self.units),
            initializer=self.kernel_initializer,
        )
        self.recurrent_kernel = self.add_weight(
            name="recurrent_kernel",
            shape=(self.units, self.units),
            initializer=self.recurrent_initializer,
        )
        self.bias = self.add_weight(
            name="bias",
            shape=(self.units,),
            initializer=self.bias_initializer,
        )
        super().build(input_shape)

    def call(
        self,
        inputs: tf.Tensor,
        states: Sequence[tf.Tensor],
        training: bool | None = None,
    ) -> tuple[tf.Tensor, tuple[tf.Tensor, ...]]:
        del training
        if len(states) != self.dilation:
            raise ValueError(
                f"Esperados {self.dilation} estados, recebidos {len(states)}."
            )

        estado_dilatado = states[0]
        pre_ativacao = (
            tf.linalg.matmul(inputs, self.kernel)
            + tf.linalg.matmul(estado_dilatado, self.recurrent_kernel)
            + self.bias
        )
        novo_estado = self.activation(pre_ativacao)
        nova_fila = tuple(states[1:]) + (novo_estado,)
        return novo_estado, nova_fila

    def get_config(self) -> dict[str, Any]:
        config = super().get_config()
        config.update(
            {
                "units": self.units,
                "dilation": self.dilation,
                "activation": tf.keras.activations.serialize(self.activation),
                "kernel_initializer": tf.keras.initializers.serialize(
                    self.kernel_initializer
                ),
                "recurrent_initializer": tf.keras.initializers.serialize(
                    self.recurrent_initializer
                ),
                "bias_initializer": tf.keras.initializers.serialize(
                    self.bias_initializer
                ),
            }
        )
        return config


def construir_dilated_rnn(
    sequence_length: int,
    n_sequence_features: int,
    *,
    n_aux_features: int = 0,
    dilations: Sequence[int] = (1, 2, 4),
    units: int | Sequence[int] = 16,
    dense_units: int = 8,
    output_activation: str = "linear",
    learning_rate: float = 0.001,
) -> tf.keras.Model:
    """Constroi uma DilatedRNN empilhada para regressao pontual.

    Args:
        sequence_length: Quantidade de instantes da janela temporal.
        n_sequence_features: Variaveis observadas em cada instante.
        n_aux_features: Covariaveis auxiliares por amostra. Elas nao entram na
            recorrencia e sao concatenadas depois do codificador temporal.
        dilations: Salto recorrente de cada camada empilhada.
        units: Numero de unidades comum ou uma sequencia, uma por camada.
        dense_units: Unidades da camada densa posterior ao codificador.
        output_activation: Ativacao da saida escalar (``linear`` por padrao).
        learning_rate: Taxa do otimizador Adam.

    Returns:
        Modelo Keras compilado. Quando ``n_aux_features > 0``, suas entradas
        sao um dicionario com as chaves ``sequence`` e ``auxiliary``.
    """
    if sequence_length < 1 or n_sequence_features < 1:
        raise ValueError("sequence_length e n_sequence_features devem ser positivos.")
    if n_aux_features < 0:
        raise ValueError("n_aux_features nao pode ser negativo.")
    if dense_units < 1:
        raise ValueError("dense_units deve ser positivo.")

    dilations = tuple(dilations)
    if not dilations or any(not isinstance(d, int) or d < 1 for d in dilations):
        raise ValueError("dilations deve conter inteiros positivos.")

    if isinstance(units, int):
        units_por_camada = (units,) * len(dilations)
    else:
        units_por_camada = tuple(units)
        if len(units_por_camada) != len(dilations):
            raise ValueError("units deve ter um valor para cada dilatacao.")
    if any(not isinstance(valor, int) or valor < 1 for valor in units_por_camada):
        raise ValueError("Todos os valores de units devem ser inteiros positivos.")

    entrada_sequencia = tf.keras.layers.Input(
        shape=(sequence_length, n_sequence_features), name="sequence"
    )
    representacao = entrada_sequencia
    for indice, (dilatacao, unidades) in enumerate(
        zip(dilations, units_por_camada, strict=True)
    ):
        ultima_camada = indice == len(dilations) - 1
        celula = DilatedSimpleRNNCell(
            units=unidades,
            dilation=dilatacao,
            name=f"dilated_cell_{indice + 1}",
        )
        representacao = tf.keras.layers.RNN(
            celula,
            return_sequences=not ultima_camada,
            name=f"dilated_rnn_s{dilatacao}_l{indice + 1}",
        )(representacao)

    entradas: tf.keras.KerasTensor | dict[str, tf.keras.KerasTensor]
    if n_aux_features:
        entrada_auxiliar = tf.keras.layers.Input(
            shape=(n_aux_features,), name="auxiliary"
        )
        representacao = tf.keras.layers.Concatenate(name="temporal_plus_auxiliary")(
            [representacao, entrada_auxiliar]
        )
        entradas = {"sequence": entrada_sequencia, "auxiliary": entrada_auxiliar}
    else:
        entradas = entrada_sequencia

    representacao = tf.keras.layers.Dense(
        dense_units, activation="relu", name="dense_representation"
    )(representacao)
    saida = tf.keras.layers.Dense(
        1, activation=output_activation, name="forecast"
    )(representacao)
    modelo = tf.keras.Model(inputs=entradas, outputs=saida, name="DilatedRNN")
    modelo.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=learning_rate),
        loss="mse",
    )
    return modelo


class DilatedRNNRegressor:
    """Adaptador ``fit/predict`` para a DilatedRNN de regressao.

    ``X_sequence`` deve manter a ordem passado -> presente. ``X_aux`` e
    opcional e deve conter apenas covariaveis por amostra, nunca novos passos
    artificiais da sequencia.
    """

    def __init__(
        self,
        *,
        dilations: Sequence[int] = (1, 2, 4),
        units: int | Sequence[int] = 16,
        dense_units: int = 8,
        output_activation: str = "linear",
        learning_rate: float = 0.001,
        epochs: int = 120,
        batch_size: int = 16,
        validation_split: float = 0.2,
        patience: int = 15,
        random_state: int = 42,
        verbose: int = 0,
    ) -> None:
        self.dilations = tuple(dilations)
        self.units = units
        self.dense_units = dense_units
        self.output_activation = output_activation
        self.learning_rate = learning_rate
        self.epochs = epochs
        self.batch_size = batch_size
        self.validation_split = validation_split
        self.patience = patience
        self.random_state = random_state
        self.verbose = verbose

        self.model_: tf.keras.Model | None = None
        self.history_: tf.keras.callbacks.History | None = None
        self.sequence_shape_: tuple[int, int] | None = None
        self.n_aux_features_: int = 0

    @staticmethod
    def _validar_sequencia(X_sequence: np.ndarray) -> np.ndarray:
        valores = np.asarray(X_sequence, dtype=np.float32)
        if valores.ndim != 3:
            raise ValueError(
                "X_sequence deve ter forma (amostras, passos, variaveis_temporais)."
            )
        if valores.shape[0] == 0 or valores.shape[1] == 0 or valores.shape[2] == 0:
            raise ValueError("X_sequence nao pode conter dimensoes vazias.")
        if not np.isfinite(valores).all():
            raise ValueError("X_sequence contem valores nao finitos.")
        return valores

    @staticmethod
    def _validar_auxiliar(
        X_aux: np.ndarray | None,
        n_amostras: int,
    ) -> np.ndarray | None:
        if X_aux is None:
            return None
        valores = np.asarray(X_aux, dtype=np.float32)
        if valores.ndim != 2 or valores.shape[0] != n_amostras:
            raise ValueError(
                "X_aux deve ter forma (amostras, covariaveis) e acompanhar X_sequence."
            )
        if valores.shape[1] == 0 or not np.isfinite(valores).all():
            raise ValueError("X_aux deve conter covariaveis finitas.")
        return valores

    @staticmethod
    def _entradas(
        X_sequence: np.ndarray,
        X_aux: np.ndarray | None,
    ) -> np.ndarray | dict[str, np.ndarray]:
        if X_aux is None:
            return X_sequence
        return {"sequence": X_sequence, "auxiliary": X_aux}

    def fit(
        self,
        X_sequence: np.ndarray,
        y: np.ndarray,
        X_aux: np.ndarray | None = None,
    ) -> "DilatedRNNRegressor":
        X_sequence = self._validar_sequencia(X_sequence)
        X_aux = self._validar_auxiliar(X_aux, len(X_sequence))
        y_array = np.asarray(y, dtype=np.float32).reshape(-1)
        if len(y_array) != len(X_sequence) or not np.isfinite(y_array).all():
            raise ValueError("y deve conter um alvo finito para cada amostra.")

        tf.keras.backend.clear_session()
        tf.keras.utils.set_random_seed(self.random_state)
        try:
            tf.config.experimental.enable_op_determinism()
        except (AttributeError, RuntimeError):
            pass

        self.sequence_shape_ = (X_sequence.shape[1], X_sequence.shape[2])
        self.n_aux_features_ = 0 if X_aux is None else X_aux.shape[1]
        self.model_ = construir_dilated_rnn(
            sequence_length=self.sequence_shape_[0],
            n_sequence_features=self.sequence_shape_[1],
            n_aux_features=self.n_aux_features_,
            dilations=self.dilations,
            units=self.units,
            dense_units=self.dense_units,
            output_activation=self.output_activation,
            learning_rate=self.learning_rate,
        )

        callbacks = []
        usar_validacao = len(X_sequence) >= 10 and self.validation_split > 0
        if usar_validacao and self.patience > 0:
            callbacks.append(
                tf.keras.callbacks.EarlyStopping(
                    monitor="val_loss",
                    patience=self.patience,
                    restore_best_weights=True,
                )
            )
        self.history_ = self.model_.fit(
            self._entradas(X_sequence, X_aux),
            y_array,
            epochs=self.epochs,
            batch_size=self.batch_size,
            validation_split=self.validation_split if usar_validacao else 0.0,
            shuffle=False,
            callbacks=callbacks,
            verbose=self.verbose,
        )
        return self

    def predict(
        self,
        X_sequence: np.ndarray,
        X_aux: np.ndarray | None = None,
    ) -> np.ndarray:
        if self.model_ is None or self.sequence_shape_ is None:
            raise RuntimeError("O regressor precisa ser treinado antes da previsao.")
        X_sequence = self._validar_sequencia(X_sequence)
        if X_sequence.shape[1:] != self.sequence_shape_:
            raise ValueError("A forma temporal da previsao difere da usada no treino.")
        X_aux = self._validar_auxiliar(X_aux, len(X_sequence))
        n_aux = 0 if X_aux is None else X_aux.shape[1]
        if n_aux != self.n_aux_features_:
            raise ValueError("As covariaveis auxiliares diferem das usadas no treino.")
        previsoes = self.model_.predict(
            self._entradas(X_sequence, X_aux), verbose=0
        )
        return np.asarray(previsoes, dtype=float).reshape(-1)


__all__ = [
    "DilatedSimpleRNNCell",
    "DilatedRNNRegressor",
    "construir_dilated_rnn",
]
