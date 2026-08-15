"""Testes rápidos do protocolo horário TimesNet."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.experimento_horario_timesnet import (
    ConfiguracaoExperimentoHorario,
    JanelasHorarias,
    MODELOS,
    SerieLocalidade,
    ajustar_escalas_pre_corte,
    aplicar_pos_processamento_fisico,
    calcular_elevacao_solar,
    construir_janelas_diarias,
    executar_experimento,
    preparar_series_localidades,
    prever_persistencia_diaria,
    prever_sazonal_ingenuo_anual,
)


def _dados_sinteticos(
    inicio: str,
    fim: str,
    *,
    localidade: str = "Local de teste",
    offset: float = -3.0,
    latitude: float = -12.67,
    longitude: float = -38.30,
) -> pd.DataFrame:
    utc = pd.date_range(inicio, fim, freq="1h", tz="UTC")
    local = utc + pd.to_timedelta(offset, unit="h")
    hora = local.hour.to_numpy()
    ciclo_diario = np.maximum(0.0, np.sin(np.pi * (hora - 6) / 12))
    ciclo_anual = 0.85 + 0.15 * np.cos(
        2 * np.pi * (local.dayofyear.to_numpy() - 20) / 365.25
    )
    return pd.DataFrame(
        {
            "timestamp_utc": utc,
            "localidade": localidade,
            "ghi": 800.0 * ciclo_diario * ciclo_anual,
            "timezone_nsrdb": offset,
            "lat_grade_nsrdb": latitude,
            "lon_grade_nsrdb": longitude,
        }
    )


def _janela_manual(
    *,
    x: np.ndarray,
    y: np.ndarray,
    origem_utc: str,
    origem_local: str | None = None,
    particao: str = "teste",
) -> JanelasHorarias:
    x = np.asarray(x, dtype=np.float32).reshape(1, -1)
    y = np.asarray(y, dtype=np.float32).reshape(1, -1)
    utc = pd.DatetimeIndex([pd.Timestamp(origem_utc)])
    if utc.tz is None:
        utc = utc.tz_localize("UTC")
    local = pd.DatetimeIndex(
        [pd.Timestamp(origem_local or origem_utc).tz_localize(None)]
    )
    return JanelasHorarias(
        x_bruto=x,
        y_bruto=y,
        localidade_id=np.array([0]),
        localidade=np.array(["Local"], dtype=object),
        origem_utc=utc,
        origem_local=local,
        seq_len=x.shape[1],
        pred_len=y.shape[1],
        particao=particao,
    )


def test_configuracao_padrao_codifica_protocolo_canonico() -> None:
    configuracao = ConfiguracaoExperimentoHorario()

    assert configuracao.seq_len == 336
    assert configuracao.pred_len == 72
    assert configuracao.horizontes == (24, 48, 72)
    assert configuracao.anos_treino == (2019, 2020, 2021, 2022)
    assert configuracao.ano_validacao == 2023
    assert configuracao.ano_teste == 2024
    assert configuracao.semente == 42
    assert configuracao.timesnet_d_model == 8
    assert configuracao.batch_size == 128


def test_origens_sao_meia_noite_local_e_alvo_nao_cruza_borda() -> None:
    dados = _dados_sinteticos("2023-12-20", "2024-01-10")
    configuracao = ConfiguracaoExperimentoHorario(modo_execucao="smoke")
    series = preparar_series_localidades(dados, configuracao)

    janelas = construir_janelas_diarias(
        series,
        anos_origem=(2024,),
        seq_len=24,
        pred_len=72,
        particao="teste_2024",
    )

    assert (janelas.origem_local.hour == 0).all()
    # UTC 03:00 corresponde a 00:00 no offset fixo -03 da NSRDB.
    assert (janelas.origem_utc.hour == 3).all()
    assert (
        janelas.origem_local + pd.Timedelta(hours=72)
        <= pd.Timestamp("2025-01-01")
    ).all()
    assert janelas.origem_utc.max() == pd.Timestamp(
        "2024-01-06 03:00:00+00:00"
    )


def test_minmax_usa_somente_observacoes_anteriores_ao_corte() -> None:
    dados = _dados_sinteticos("2022-12-20", "2023-01-10")
    dados.loc[dados["timestamp_utc"] >= "2023-01-02", "ghi"] = 100_000.0
    configuracao = ConfiguracaoExperimentoHorario(modo_execucao="smoke")
    series = preparar_series_localidades(dados, configuracao)

    escalas = ajustar_escalas_pre_corte(
        series,
        primeiro_ano=2022,
        fim_local_exclusivo="2023-01-01",
        nome_ajuste="teste",
    )

    assert escalas.loc[0, "maximo_treino_wm2"] < 1_000.0
    assert escalas.loc[0, "fim_local_exclusivo"] == "2023-01-01T00:00:00"


def test_persistencia_repete_exatamente_as_ultimas_24_horas() -> None:
    janela = _janela_manual(
        x=np.arange(336),
        y=np.zeros(72),
        origem_utc="2024-01-01T00:00:00Z",
    )

    previsto = prever_persistencia_diaria(janela)

    esperado = np.tile(np.arange(312, 336), 3)
    assert previsto.shape == (1, 72)
    assert np.array_equal(previsto[0], esperado)


def test_sazonal_anual_mapeia_29_de_fevereiro_para_28() -> None:
    utc = pd.date_range("2023-02-20", "2024-03-03", freq="1h", tz="UTC")
    local = utc.tz_localize(None)
    ghi = np.arange(len(utc), dtype=np.float32)
    serie = SerieLocalidade(
        localidade="Local",
        localidade_id=0,
        timestamp_utc=utc,
        timestamp_local=local,
        ghi=ghi,
        offset_horas=0,
        latitude=0,
        longitude=0,
    )
    origem = pd.Timestamp("2024-02-29")
    posicao = int(local.get_indexer([origem])[0])
    janela = JanelasHorarias(
        x_bruto=ghi[posicao - 24 : posicao][None, :],
        y_bruto=ghi[posicao : posicao + 24][None, :],
        localidade_id=np.array([0]),
        localidade=np.array(["Local"], dtype=object),
        origem_utc=pd.DatetimeIndex([origem.tz_localize("UTC")]),
        origem_local=pd.DatetimeIndex([origem]),
        seq_len=24,
        pred_len=24,
        particao="teste",
    )

    previsto = prever_sazonal_ingenuo_anual(janela, (serie,))

    referencia = int(local.get_indexer([pd.Timestamp("2023-02-28")])[0])
    assert previsto[0, 0] == ghi[referencia]
    assert previsto[0, 23] == ghi[referencia + 23]


def test_pos_processamento_trunca_negativos_e_aplica_mascara_noturna() -> None:
    bruto = np.array([[-5.0, 25.0, 30.0]])
    elevacao = np.array([[15.0, -2.0, 20.0]])

    resultado = aplicar_pos_processamento_fisico(bruto, elevacao)

    assert np.array_equal(resultado, [[0.0, 0.0, 30.0]])


def test_pvlib_identifica_noite_e_dia_no_equador() -> None:
    janela = _janela_manual(
        x=np.zeros(24),
        y=np.zeros(24),
        origem_utc="2024-03-20T00:00:00Z",
    )
    serie = SerieLocalidade(
        localidade="Local",
        localidade_id=0,
        timestamp_utc=pd.date_range(
            "2024-03-19", periods=72, freq="1h", tz="UTC"
        ),
        timestamp_local=pd.date_range(
            "2024-03-19", periods=72, freq="1h"
        ),
        ghi=np.zeros(72, dtype=np.float32),
        offset_horas=0,
        latitude=0,
        longitude=0,
    )

    elevacao = calcular_elevacao_solar(
        janela, (serie,), minutos_centro_intervalo=30
    )

    assert elevacao[0, 0] < 0
    assert elevacao[0, 12] > 0


def test_smoke_executa_cinco_modelos_e_gera_artefatos(tmp_path: Path) -> None:
    dados = _dados_sinteticos("2018-12-15", "2024-01-10")
    configuracao = ConfiguracaoExperimentoHorario(
        modo_execucao="smoke",
        seq_len=24,
        pred_len=24,
        horizontes=(24,),
        batch_size=2,
        lstm_ocultos=4,
        embedding_localidade_lstm=2,
        timesnet_d_model=2,
        timesnet_d_ff=4,
        timesnet_blocos=1,
        timesnet_top_k=1,
        timesnet_kernels=1,
        timesnet_dropout=0.0,
        limite_localidades_smoke=1,
        limite_origens_smoke=1,
        epocas_smoke=1,
        xgb_estimadores_smoke=1,
    )

    artefatos = executar_experimento(
        tmp_path / "saida",
        configuracao,
        dados=dados,
    )

    assert all(caminho.exists() for caminho in artefatos.values())
    previsoes = pd.read_csv(artefatos["previsoes_teste"])
    for modelo in MODELOS:
        slug = {
            "Persistência": "persistencia",
            "Sazonal Ingênuo": "sazonal_ingenuo",
            "XGBoost": "xgboost",
            "LSTM": "lstm",
            "TimesNet": "timesnet",
        }[modelo]
        assert f"previsao_bruta_{slug}_wm2" in previsoes
        assert f"previsao_pos_{slug}_wm2" in previsoes
    assert (previsoes.filter(like="previsao_pos_") >= 0).all().all()
    manifesto = json.loads(artefatos["manifesto"].read_text(encoding="utf-8"))
    assert manifesto["resultado_smoke_nao_publicavel"] is True
    assert manifesto["xgboost_multi_strategy"] == "multi_output_tree"
    assert (
        artefatos["figura_timesnet"].name
        == "previsao_horaria_timesnet_72h.png"
    )
    assert (
        artefatos["figura_comparacao_rmse"].name
        == "comparacao_rmse_modelos.png"
    )
