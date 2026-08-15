"""Testes da DilatedRNN com conexoes recorrentes de salto."""

from __future__ import annotations

import numpy as np
import pytest

tf = pytest.importorskip("tensorflow")

from codigo_fonte.dilated_rnn import (  # noqa: E402
    DilatedRNNRegressor,
    DilatedSimpleRNNCell,
    construir_dilated_rnn,
)


def test_modelo_aceita_sequencia_real_e_covariaveis_auxiliares() -> None:
    modelo = construir_dilated_rnn(
        sequence_length=12,
        n_sequence_features=2,
        n_aux_features=3,
        dilations=(1, 2, 4),
        units=(4, 5, 6),
        dense_units=4,
    )

    formas_entrada = {
        tensor.name.split(":", maxsplit=1)[0]: tuple(tensor.shape)
        for tensor in modelo.inputs
    }
    assert formas_entrada == {
        "sequence": (None, 12, 2),
        "auxiliary": (None, 3),
    }
    assert modelo.output_shape == (None, 1)
    assert [
        modelo.get_layer(nome).cell.dilation
        for nome in ("dilated_rnn_s1_l1", "dilated_rnn_s2_l2", "dilated_rnn_s4_l3")
    ] == [1, 2, 4]


def test_celula_conecta_exatamente_ao_estado_t_menos_dilatacao() -> None:
    # Com ativacao linear e pesos unitarios, para s=2 vale h_t=x_t+h_{t-2}.
    celula = DilatedSimpleRNNCell(
        units=1,
        dilation=2,
        activation="linear",
        kernel_initializer="ones",
        recurrent_initializer="ones",
        bias_initializer="zeros",
    )
    camada = tf.keras.layers.RNN(celula, return_sequences=True)
    entrada = tf.constant([[[1.0], [2.0], [3.0], [4.0], [5.0]]])

    saida = camada(entrada).numpy()[0, :, 0]

    # h0=1, h1=2, h2=3+h0=4, h3=4+h1=6, h4=5+h2=9.
    assert saida.tolist() == pytest.approx([1.0, 2.0, 4.0, 6.0, 9.0])
    assert celula.state_size == (1, 1)


def test_regressor_executa_treino_minimo_e_prediz_com_forma_correta() -> None:
    gerador = np.random.default_rng(123)
    sequencias = gerador.normal(size=(16, 6, 1)).astype(np.float32)
    auxiliares = gerador.normal(size=(16, 2)).astype(np.float32)
    alvos = (0.4 * sequencias[:, -1, 0] + 0.2 * auxiliares[:, 0]).astype(
        np.float32
    )
    regressor = DilatedRNNRegressor(
        dilations=(1, 2),
        units=3,
        dense_units=3,
        epochs=2,
        batch_size=4,
        validation_split=0.0,
        random_state=7,
    )

    regressor.fit(sequencias, alvos, auxiliares)
    previsoes = regressor.predict(sequencias[:3], auxiliares[:3])

    assert previsoes.shape == (3,)
    assert np.isfinite(previsoes).all()
    assert regressor.history_ is not None
    assert len(regressor.history_.history["loss"]) == 2


def test_regressor_rejeita_vetor_tabular_como_sequencia() -> None:
    regressor = DilatedRNNRegressor(epochs=1, validation_split=0.0)

    with pytest.raises(ValueError, match="amostras, passos, variaveis_temporais"):
        regressor.fit(np.zeros((4, 6)), np.zeros(4))
