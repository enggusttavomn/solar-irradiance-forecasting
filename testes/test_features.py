"""Testes do alinhamento causal das entradas, alvos e cortes temporais."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.features import (
    criar_features_temporais,
    dividir_treino_teste_temporal,
)
from codigo_fonte.preprocessamento import preparar_serie_temporal


def _serie_transformada(periodos: int = 15) -> pd.DataFrame:
    valores = np.arange(periodos, dtype=float)
    return pd.DataFrame(
        {
            "data": pd.date_range("2023-01-31", periods=periodos, freq="ME"),
            "ghi": valores * 10.0,
            "ghi_quantizado": valores.astype(int),
            "ghi_normalizado": valores,
        }
    )


def test_features_usam_apenas_historico_anterior_ao_alvo() -> None:
    modelagem, colunas = criar_features_temporais(
        _serie_transformada(),
        lags=(1, 2, 3),
        moving_windows=(3,),
        periodo_label="m",
    )

    primeira = modelagem.iloc[0]
    assert colunas[:3] == ["ghi_t-1", "ghi_t-2", "ghi_t-3"]
    assert primeira["data"] == pd.Timestamp("2023-03-31")
    assert primeira["data_alvo"] == pd.Timestamp("2023-04-30")
    assert primeira["ghi_t-1"] == pytest.approx(2.0)
    assert primeira["ghi_t-2"] == pytest.approx(1.0)
    assert primeira["ghi_t-3"] == pytest.approx(0.0)
    assert primeira["ghi_media_movel_3m"] == pytest.approx(1.0)
    assert primeira["ghi_alvo_original"] == pytest.approx(30.0)
    assert {"mes_alvo_sin", "mes_alvo_cos"}.issubset(colunas)
    assert primeira["mes_alvo_sin"] == pytest.approx(1.0)
    assert primeira["mes_alvo_cos"] == pytest.approx(0.0, abs=1e-12)


def test_alterar_futuro_nao_altera_features_do_passado() -> None:
    original = _serie_transformada()
    alterada = original.copy()
    alterada.loc[alterada.index[-3:], ["ghi", "ghi_quantizado", "ghi_normalizado"]] = 9999

    base_original, colunas = criar_features_temporais(
        original, lags=(1, 2, 3), moving_windows=(3,), periodo_label="m"
    )
    base_alterada, _ = criar_features_temporais(
        alterada, lags=(1, 2, 3), moving_windows=(3,), periodo_label="m"
    )

    limite = original.loc[original.index[-4], "data"]
    passado_original = base_original.loc[base_original["data"] <= limite, colunas]
    passado_alterado = base_alterada.loc[base_alterada["data"] <= limite, colunas]
    pd.testing.assert_frame_equal(passado_original, passado_alterado)


def test_divisao_temporal_nao_embaralha_nem_sobrepoe() -> None:
    dados, colunas = criar_features_temporais(
        _serie_transformada(20), lags=(1, 2), moving_windows=(2,), periodo_label="m"
    )

    X_treino, X_teste, y_treino, y_teste, treino, teste = dividir_treino_teste_temporal(
        dados, colunas, train_ratio=0.7
    )

    assert len(X_treino) == len(y_treino) == len(treino)
    assert len(X_teste) == len(y_teste) == len(teste)
    assert treino["data_alvo"].max() < teste["data_alvo"].min()
    assert X_treino.index.intersection(X_teste.index).empty
    pd.testing.assert_frame_equal(X_treino, treino[colunas])


def test_pipeline_mensal_preserva_alvo_no_mes_seguinte() -> None:
    datas = pd.date_range("2021-01-01", "2024-12-31", freq="D")
    dados = pd.DataFrame(
        {
            "data": datas,
            "ghi": 180.0 + 40.0 * np.sin(2 * np.pi * (datas.month - 1) / 12),
        }
    )

    resultado = preparar_serie_temporal(
        dados,
        lags=(1, 12),
        moving_windows=(3, 12),
        frequencia_modelagem="mensal",
        output_path=None,
    )

    base = resultado.dados_modelagem
    periodos_entrada = base["data"].dt.to_period("M")
    periodos_alvo = base["data_alvo"].dt.to_period("M")
    assert (periodos_alvo.astype(int) - periodos_entrada.astype(int) == 1).all()
    assert {"ghi_t-1", "ghi_t-12", "ghi_media_movel_12m"}.issubset(
        resultado.feature_columns
    )
