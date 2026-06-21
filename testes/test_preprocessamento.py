"""Testes das transformacoes e das regras de proveniencia dos dados.

Os testes usam bases pequenas e controladas para verificar o comportamento sem
depender da API. ``pytest`` descobre automaticamente funcoes iniciadas por
``test_`` e informa qual regra deixou de ser atendida.
"""

import pandas as pd
import pytest

from codigo_fonte.avaliacao import calcular_metricas, desnormalizar_ghi
from codigo_fonte.preprocessamento import (
    NSRDB_API_URL,
    NSRDB_DAILY_AGGREGATION,
    NSRDB_GHI_UNIT,
    NSRDB_PRODUCT,
    NSRDB_SOURCE,
    calcular_estatisticas_ghi_horario,
    carregar_serie_ghi,
    normalizar_minmax,
    preparar_serie_temporal,
    quantizar_ghi,
)
from codigo_fonte.features import criar_features_temporais
from codigo_fonte.localidades_ev import LOCALIDADES_EV
from treinar_todas_localidades import validar_csv_nrel_localidade


def criar_base_nsrdb_valida():
    """Monta um CSV oficial minimo que deve passar por todas as validacoes."""
    # Reutilizar o cadastro real evita repetir coordenadas e fontes nos testes.
    local = LOCALIDADES_EV[0]
    # A cobertura completa e uma exigencia do validador oficial.
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
    """Confirma o mapeamento dos extremos e do ponto medio para 0..127."""
    valores = pd.Series([0.0, 50.0, 100.0])

    quantizado = quantizar_ghi(valores, n_niveis=128)

    assert quantizado.tolist() == [0, 64, 127]


def test_normalizar_minmax_limita_entre_zero_e_um():
    """Confirma que a escala quantizada e convertida para o intervalo unitario."""
    valores = pd.Series([0, 64, 127])

    normalizado = normalizar_minmax(valores, minimo=0, maximo=127)

    assert normalizado.min() >= 0
    assert normalizado.max() <= 1


def test_desnormalizar_ghi_volta_para_escala_wm2():
    """Confirma a conversao aproximada da escala normalizada para W/m2."""
    valores = pd.Series([0.0, 0.5, 1.0])

    desnormalizado = desnormalizar_ghi(valores, {"min": 100.0, "max": 300.0})

    assert desnormalizado.tolist() == [100.0, 200.0, 300.0]


def test_calcular_metricas_inclui_nrmse():
    """Verifica a normalizacao do RMSE pela media real."""
    metricas = calcular_metricas(
        pd.Series([100.0, 200.0, 300.0]),
        pd.Series([100.0, 200.0, 240.0]),
        "Teste",
        sufixo="wm2",
    )

    assert metricas["RMSE_wm2"] == pytest.approx((3600 / 3) ** 0.5)
    assert metricas["nRMSE_wm2"] == pytest.approx(metricas["RMSE_wm2"] / 200.0)
    assert metricas["nRMSE_percentual_wm2"] == pytest.approx(metricas["nRMSE_wm2"] * 100)


def test_calcular_estatisticas_ghi_horario_retorna_cov():
    """Calcula sigma/media usando observacoes horarias antes da media diaria."""
    df = pd.DataFrame(
        {
            "data": pd.date_range("2024-01-01", periods=4, freq="h"),
            "ghi": [0.0, 100.0, 200.0, 300.0],
        }
    )

    estatisticas = calcular_estatisticas_ghi_horario(df)

    assert estatisticas["ghi_horario_media"] == pytest.approx(150.0)
    assert estatisticas["ghi_horario_sigma"] == pytest.approx(111.80339887498948)
    assert estatisticas["ghi_horario_cov"] == pytest.approx(0.7453559924999299)
    assert estatisticas["ghi_horario_fonte_estatistica"] == "horaria"


def test_preparar_serie_temporal_cria_features_sem_futuro():
    """Verifica a estrutura basica da base supervisionada produzida."""
    # Sessenta dias sao suficientes para uma janela completa de 30 dias.
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


def test_features_ficam_alinhadas_com_o_alvo_do_dia_seguinte():
    """Demonstra numericamente que as entradas terminam antes do alvo."""
    # Uma sequencia 0..9 torna cada deslocamento facil de conferir.
    datas = pd.date_range("2024-01-01", periods=10, freq="D")
    dados = pd.DataFrame(
        {
            "data": datas,
            "ghi": range(10),
            "ghi_quantizado": range(10),
            "ghi_normalizado": range(10),
        }
    )

    modelagem, _ = criar_features_temporais(
        dados,
        lags=(1, 2, 3),
        moving_windows=(3,),
    )
    # A primeira linha valida tem os dias 1, 2 e 3 como historico.
    primeira = modelagem.iloc[0]

    assert primeira["data"] == pd.Timestamp("2024-01-03")
    assert primeira["data_alvo"] == pd.Timestamp("2024-01-04")
    assert primeira["ghi_t-1"] == 2
    assert primeira["ghi_t-2"] == 1
    assert primeira["ghi_t-3"] == 0
    assert primeira["ghi_media_movel_3d"] == pytest.approx(1.0)
    assert primeira["ghi_alvo_original"] == 3


def test_validar_csv_nrel_rejeita_dado_sintetico(tmp_path):
    """Rejeita um arquivo sem metadados e com nome sintetico por coordenada."""
    # ``tmp_path`` e uma pasta temporaria isolada fornecida pelo pytest.
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
    """Confirma o caminho feliz com cobertura e proveniencia completas."""
    arquivo = tmp_path / "byd_camacari.csv"
    criar_base_nsrdb_valida().to_csv(arquivo, index=False)

    valido, motivo = validar_csv_nrel_localidade(
        arquivo,
        LOCALIDADES_EV[0],
    )

    assert valido
    assert motivo == "CSV validado como NLR/NSRDB"


def test_validar_csv_nrel_rejeita_ghi_fora_da_unidade_declarada(tmp_path):
    """Detecta valor diario incompativel com a faixa esperada em W/m2."""
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
    """Impede associar a fabrica a um ponto NSRDB geograficamente distante."""
    arquivo = tmp_path / "byd_camacari.csv"
    dados = criar_base_nsrdb_valida()
    dados["lat_grade_nsrdb"] = 0.0
    dados["lon_grade_nsrdb"] = 0.0
    dados.to_csv(arquivo, index=False)

    valido, motivo = validar_csv_nrel_localidade(arquivo, LOCALIDADES_EV[0])

    assert not valido
    assert "distante demais" in motivo


def test_carregar_serie_rejeita_csv_sintetico_em_localidades_ev(tmp_path):
    """Garante que ate o carregador simples proteja a pasta oficial."""
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

    # O contexto passa somente se a excecao e sua mensagem forem as esperadas.
    with pytest.raises(ValueError, match="proveniencia NLR/NSRDB"):
        carregar_serie_ghi(arquivo)
