import pandas as pd
import pytest

from codigo_fonte.preprocessamento import (
    NSRDB_API_URL,
    NSRDB_DAILY_AGGREGATION,
    NSRDB_GHI_UNIT,
    NSRDB_PRODUCT,
    NSRDB_SOURCE,
    carregar_serie_ghi,
    normalizar_minmax,
    preparar_serie_temporal,
    quantizar_ghi,
)
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from treinar_todas_localidades import validar_csv_nrel_localidade


def criar_base_nsrdb_valida():
    local = LOCALIDADES_EV[0]
    datas = pd.date_range("2019-01-01", "2024-12-31", freq="D")
    return pd.DataFrame(
        {
            "data": datas,
            "ghi": 220.0,
            "localidade": "BYD Camacari",
            "pais": "Brasil",
            "lat": local["lat"],
            "lon": local["lon"],
            "endereco_localidade": local["endereco"],
            "fonte_localidade": local["fonte_localidade"],
            "fonte_coordenadas": local["fonte_coordenadas"],
            "metodo_coordenadas": local["metodo_coordenadas"],
            "osm_elemento": local["osm_elemento"],
            "ano": datas.year,
            "fonte_dados": NSRDB_SOURCE,
            "produto_dados": NSRDB_PRODUCT,
            "versao_dados": "4.1.2",
            "endpoint_api": NSRDB_API_URL,
            "intervalo_minutos": 60,
            "agregacao": NSRDB_DAILY_AGGREGATION,
            "unidade_ghi": NSRDB_GHI_UNIT,
            "lat_grade_nsrdb": -12.67,
            "lon_grade_nsrdb": -38.29,
            "site_id_nsrdb": 123,
            "source_nsrdb": "NSRDB",
            "timezone_nsrdb": -3,
            "elevacao_grade_m": 10,
            "ghi_unidade_api": "w/m2",
            "data_coleta_utc": "2026-06-06T00:00:00+00:00",
        }
    )


def test_quantizar_ghi_cria_128_niveis_possiveis():
    valores = pd.Series([0.0, 50.0, 100.0])

    quantizado = quantizar_ghi(valores, n_niveis=128)

    assert quantizado.tolist() == [0, 64, 127]


def test_normalizar_minmax_limita_entre_zero_e_um():
    valores = pd.Series([0, 64, 127])

    normalizado = normalizar_minmax(valores, minimo=0, maximo=127)

    assert normalizado.min() >= 0
    assert normalizado.max() <= 1


def test_preparar_serie_temporal_cria_features_sem_futuro():
    df = pd.DataFrame(
        {
            "data": pd.date_range("2024-01-01", periods=60, freq="D"),
            "ghi": range(60),
        }
    )

    result = preparar_serie_temporal(df, output_path=None)

    assert "ghi_t-1" in result.feature_columns
    assert "ghi_t-7" in result.feature_columns
    assert "ghi_media_movel_30d" in result.feature_columns
    assert result.train_size > 0
    assert result.train_size < len(result.dados_modelagem)


def test_validar_csv_nrel_rejeita_dado_sintetico(tmp_path):
    arquivo = tmp_path / "byd_camacari.csv"
    pd.DataFrame(
        {
            "data": ["2019-01-01"],
            "ghi": [6009],
            "localidade": ["lat_-12.70_lon_-38.32"],
            "lat": [-12.6977],
            "lon": [-38.3240],
            "ano": [2019],
        }
    ).to_csv(arquivo, index=False)

    valido, motivo = validar_csv_nrel_localidade(
        arquivo,
        LOCALIDADES_EV[0],
    )

    assert not valido
    assert "ausentes" in motivo


def test_validar_csv_nrel_aceita_metadados_oficiais(tmp_path):
    arquivo = tmp_path / "byd_camacari.csv"
    criar_base_nsrdb_valida().to_csv(arquivo, index=False)

    valido, motivo = validar_csv_nrel_localidade(
        arquivo,
        LOCALIDADES_EV[0],
    )

    assert valido
    assert motivo == "CSV validado como NLR/NSRDB"


def test_validar_csv_nrel_rejeita_ghi_fora_da_unidade_declarada(tmp_path):
    arquivo = tmp_path / "byd_camacari.csv"
    dados = criar_base_nsrdb_valida()
    dados["ghi"] = 6009
    dados.to_csv(arquivo, index=False)

    valido, motivo = validar_csv_nrel_localidade(
        arquivo,
        LOCALIDADES_EV[0],
    )

    assert not valido
    assert "entre 0 e 500" in motivo


def test_validar_csv_nrel_rejeita_grade_distante_da_fabrica(tmp_path):
    arquivo = tmp_path / "byd_camacari.csv"
    dados = criar_base_nsrdb_valida()
    dados["lat_grade_nsrdb"] = 0.0
    dados["lon_grade_nsrdb"] = 0.0
    dados.to_csv(arquivo, index=False)

    valido, motivo = validar_csv_nrel_localidade(arquivo, LOCALIDADES_EV[0])

    assert not valido
    assert "distante demais" in motivo


def test_carregar_serie_rejeita_csv_sintetico_em_localidades_ev(tmp_path):
    pasta = tmp_path / "dados" / "brutos" / "localidades_ev"
    pasta.mkdir(parents=True)
    arquivo = pasta / "byd_camacari.csv"
    pd.DataFrame(
        {
            "data": ["2019-01-01"],
            "ghi": [6009],
            "localidade": ["lat_-12.70_lon_-38.32"],
            "lat": [-12.6977],
            "lon": [-38.3240],
            "ano": [2019],
        }
    ).to_csv(arquivo, index=False)

    with pytest.raises(ValueError, match="proveniencia NLR/NSRDB"):
        carregar_serie_ghi(arquivo)
