"""Testes do pre-processamento e das transformacoes aprendidas no treino."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.preprocessamento import (
    limpar_serie_ghi,
    normalizar_minmax,
    preparar_serie_temporal,
    quantizar_ghi,
)


def test_limpeza_ordena_remove_invalidos_e_consolida_dias() -> None:
    bruto = pd.DataFrame(
        {
            "timestamp": [
                "2024-01-02 12:00:00",
                "invalida",
                "2024-01-01 00:00:00",
                "2024-01-02 00:00:00",
                "2024-01-03 00:00:00",
            ],
            "GHI": [200.0, 10.0, 100.0, 0.0, -1.0],
        }
    )

    limpo = limpar_serie_ghi(bruto)

    assert limpo["data"].tolist() == [
        pd.Timestamp("2024-01-01"),
        pd.Timestamp("2024-01-02"),
    ]
    assert limpo["ghi"].tolist() == pytest.approx([100.0, 100.0])


def test_quantizacao_usa_faixa_informada_e_faz_clipping() -> None:
    quantizado, parametros = quantizar_ghi(
        pd.Series([-50.0, 0.0, 50.0, 100.0, 150.0]),
        n_niveis=128,
        minimo=0.0,
        maximo=100.0,
        return_params=True,
    )

    assert quantizado.tolist() == [0, 0, 64, 127, 127]
    assert parametros == {"min": 0.0, "max": 100.0, "n_niveis": 128.0}


def test_normalizacao_faz_clipping_e_preserva_indice() -> None:
    valores = pd.Series([-1.0, 0.0, 5.0, 10.0, 11.0], index=list("abcde"))

    normalizado = normalizar_minmax(valores, minimo=0.0, maximo=10.0)

    assert normalizado.index.tolist() == list("abcde")
    assert normalizado.tolist() == pytest.approx([0.0, 0.0, 0.5, 1.0, 1.0])


def test_transformacao_e_ajustada_somente_no_treino() -> None:
    # Os extremos artificiais aparecem exclusivamente depois do corte temporal.
    datas = pd.date_range("2024-01-01", periods=40, freq="D")
    ghi = np.concatenate([np.arange(30, dtype=float), np.arange(1000, 1010, dtype=float)])

    resultado = preparar_serie_temporal(
        pd.DataFrame({"data": datas, "ghi": ghi}),
        lags=(1,),
        moving_windows=(1,),
        train_ratio=0.75,
        output_path=None,
    )

    assert resultado.quantization_params["min"] == pytest.approx(0.0)
    assert resultado.quantization_params["max"] == pytest.approx(29.0)
    assert resultado.quantization_params["max"] < 1000.0
    assert resultado.dados_modelagem.loc[
        resultado.train_size :, "ghi_normalizado"
    ].between(0.0, 1.0).all()


def test_regressao_continua_e_padrao_sem_degraus_de_quantizacao() -> None:
    datas = pd.date_range("2024-01-01", periods=45, freq="D")
    ghi = pd.Series(np.linspace(100.13, 200.87, len(datas)))

    resultado = preparar_serie_temporal(
        pd.DataFrame({"data": datas, "ghi": ghi}),
        lags=(1,),
        moving_windows=(1,),
        output_path=None,
    )
    base = resultado.dados_modelagem
    minimo = resultado.normalization_params["min"]
    maximo = resultado.normalization_params["max"]
    esperado = ((base["ghi"] - minimo) / (maximo - minimo)).clip(0.0, 1.0)

    assert resultado.target_transform == "continuo_minmax"
    assert base["ghi_normalizado"].to_numpy() == pytest.approx(esperado.to_numpy())
    assert not np.allclose(
        base["ghi_normalizado"].to_numpy(),
        base["ghi_quantizado"].to_numpy() / 127.0,
    )


def test_serie_com_periodo_ausente_e_rejeitada() -> None:
    datas = pd.date_range("2024-01-01", periods=45, freq="D").delete(20)
    dados = pd.DataFrame({"data": datas, "ghi": np.arange(len(datas), dtype=float)})

    with pytest.raises(ValueError, match="periodos ausentes"):
        preparar_serie_temporal(
            dados,
            lags=(1,),
            moving_windows=(1,),
            output_path=None,
        )


def test_preparacao_rejeita_configuracoes_invalidas() -> None:
    dados = pd.DataFrame(
        {
            "data": pd.date_range("2024-01-01", periods=10, freq="D"),
            "ghi": np.arange(10, dtype=float),
        }
    )

    with pytest.raises(ValueError, match="train_ratio"):
        preparar_serie_temporal(dados, train_ratio=1.0, output_path=None)
    with pytest.raises(ValueError, match="lags"):
        preparar_serie_temporal(dados, lags=(0,), output_path=None)
    with pytest.raises(ValueError, match="frequencia_modelagem"):
        preparar_serie_temporal(dados, frequencia_modelagem="horaria", output_path=None)
