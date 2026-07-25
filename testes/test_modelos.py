"""Testes leves dos adaptadores de modelos, sem treinar redes pesadas."""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

import codigo_fonte.modelos as modelos


class _EstimadorFalso:
    def __init__(self, **parametros) -> None:
        self.parametros = parametros
        self.ajustado = False

    def fit(self, X, y):
        self.X = X.copy()
        self.y = y.copy()
        self.ajustado = True
        return self


@pytest.mark.parametrize(
    ("funcao", "atributo"),
    [("treinar_mlp", "MLPRegressor"), ("treinar_xgboost", "XGBRegressor")],
)
def test_treinadores_tabulares_ajustam_somente_dados_recebidos(
    monkeypatch, funcao: str, atributo: str
) -> None:
    monkeypatch.setattr(modelos, atributo, _EstimadorFalso)
    X = pd.DataFrame({"ghi_t-1": [0.1, 0.2, 0.3], "mes_sin": [0.0, 0.5, 1.0]})
    y = pd.Series([0.2, 0.3, 0.4])

    modelo = getattr(modelos, funcao)(X, y)

    assert modelo.ajustado
    pd.testing.assert_frame_equal(modelo.X, X)
    pd.testing.assert_series_equal(modelo.y, y)
    assert "random_state" in modelo.parametros


def test_recorrente_usa_somente_lags_em_ordem_cronologica() -> None:
    X = pd.DataFrame(
        {
            "ghi_t-1": [0.3, 0.4],
            "ghi_media_movel_3m": [0.8, 0.9],
            "ghi_t-3": [0.1, 0.2],
            "mes_cos": [1.0, 0.5],
            "ghi_t-2": [0.2, 0.3],
        }
    )

    sequencia = modelos.KerasSequenceRegressor._reshape(X)

    assert sequencia.shape == (2, 3, 1)
    assert sequencia.dtype == np.float32
    assert sequencia[0, :, 0].tolist() == pytest.approx([0.1, 0.2, 0.3])


def test_reshape_recorrente_rejeita_matriz_com_dimensao_invalida() -> None:
    with pytest.raises(ValueError, match="matriz 2D"):
        modelos.KerasSequenceRegressor._reshape(np.zeros((2, 3, 1)))


def test_predict_exige_modelo_ajustado() -> None:
    regressor = modelos.KerasSequenceRegressor("RNN")

    with pytest.raises(RuntimeError, match="treinado"):
        regressor.predict(pd.DataFrame({"ghi_t-1": [0.1]}))


def test_treino_recorrente_orienta_instalacao_quando_tensorflow_ausente() -> None:
    if importlib.util.find_spec("tensorflow"):
        pytest.skip("TensorFlow instalado; o teste cobre a mensagem do ambiente leve.")

    X = pd.DataFrame({"ghi_t-2": [0.1, 0.2, 0.3], "ghi_t-1": [0.2, 0.3, 0.4]})
    y = pd.Series([0.3, 0.4, 0.5])

    with pytest.raises(ImportError, match="TensorFlow nao esta instalado"):
        modelos.treinar_rnn(X, y)


def test_vizinhos_historicos_reproduz_correspondencia_exata_e_media_empates() -> None:
    X = pd.DataFrame(
        {"lag": [0.0, 0.0, 10.0], "calendario": [1.0, 1.0, -1.0]}
    )
    y = pd.Series([1.0, 3.0, 9.0])
    regressor = modelos.VizinhosHistoricosPonderados(k=3).fit(X, y)

    previsao = regressor.predict(
        pd.DataFrame({"calendario": [1.0], "lag": [0.0]})
    )

    assert previsao.tolist() == pytest.approx([2.0])


def test_vizinhos_historicos_com_k_um_escolhe_analogo_mais_proximo() -> None:
    X = pd.DataFrame({"x": [0.0, 5.0, 10.0]})
    y = pd.Series([10.0, 50.0, 100.0])
    regressor = modelos.VizinhosHistoricosPonderados(k=1).fit(X, y)

    assert regressor.predict(pd.DataFrame({"x": [4.0, 9.0]})).tolist() == pytest.approx(
        [50.0, 100.0]
    )


def test_vizinhos_historicos_valida_ajuste_e_esquema_de_previsao() -> None:
    X = pd.DataFrame({"a": [0.0, 1.0], "b": [1.0, 2.0]})
    y = pd.Series([1.0, 2.0])

    with pytest.raises(RuntimeError, match="treinado"):
        modelos.VizinhosHistoricosPonderados().predict(X)
    with pytest.raises(ValueError, match="k deve ser positivo"):
        modelos.VizinhosHistoricosPonderados(k=0).fit(X, y)
    with pytest.raises(ValueError, match="mesma amostra nao vazia"):
        modelos.VizinhosHistoricosPonderados().fit(X, y.iloc[:1])

    regressor = modelos.VizinhosHistoricosPonderados().fit(X, y)
    with pytest.raises(ValueError, match="Features ausentes: b"):
        regressor.predict(pd.DataFrame({"a": [0.5]}))
    with pytest.raises(ValueError, match="mesmo numero de features"):
        regressor.predict(np.array([[0.5, 1.5, 2.5]]))
