"""Testes dos adaptadores de modelos recorrentes."""

import importlib.util

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.modelos import KerasSequenceRegressor, treinar_rnn


def test_keras_sequence_regressor_reinterpreta_features_como_sequencia():
    """Confirma o formato esperado por RNN/LSTM: amostras, passos, canais."""
    X = pd.DataFrame(
        {
            "ghi_t-1": [0.1, 0.2],
            "ghi_t-2": [0.3, 0.4],
            "ghi_media_movel_3d": [0.5, 0.6],
        }
    )

    sequencia = KerasSequenceRegressor._reshape(X)

    assert sequencia.shape == (2, 3, 1)
    assert sequencia.dtype == np.float32
    assert sequencia[0, :, 0].tolist() == pytest.approx([0.1, 0.3, 0.5])


def test_treinar_rnn_orienta_instalar_tensorflow_quando_dependencia_ausente():
    """Mantem uma falha clara quando TensorFlow ainda nao foi instalado."""
    if importlib.util.find_spec("tensorflow"):
        pytest.skip("TensorFlow instalado; este teste cobre apenas ambiente sem a dependencia.")

    X = pd.DataFrame({"ghi_t-1": [0.1, 0.2, 0.3]})
    y = pd.Series([0.2, 0.3, 0.4])

    with pytest.raises(ImportError, match="TensorFlow nao esta instalado"):
        treinar_rnn(X, y)
