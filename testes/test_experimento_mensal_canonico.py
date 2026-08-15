"""Testes leves do orquestrador mensal global canonico."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.dados_mensais_globais import carregar_base_mensal_global
from codigo_fonte.experimento_mensal_canonico import (
    ConfiguracaoExperimento,
    _contrato_retomada,
    _inverter_por_linha,
    _mapear_amostras_gluonts,
    _parser,
    _resumo_modelos,
    _salvar_status,
    _series_gluonts,
    executar_experimento,
)
from codigo_fonte.modelos_globais_gluonts import PrevisaoProbabilistica


def test_configuracao_rejeita_sementes_repetidas() -> None:
    with pytest.raises(ValueError, match="unicos"):
        ConfiguracaoExperimento(sementes=(42, 42))


def test_parser_expoe_retomada_explicita() -> None:
    argumentos = _parser().parse_args(["--retomar"])

    assert argumentos.retomar is True


def test_status_concluido_pode_marcar_fonte_canonica(tmp_path) -> None:
    _salvar_status(
        tmp_path,
        "concluido",
        {"fonte_artigos_atuais": True, "modo_execucao": "completa"},
    )

    status = json.loads((tmp_path / "status_execucao.json").read_text())
    assert status["detalhes"]["protocolo_canonico"] is True
    assert status["detalhes"]["fonte_artigos_atuais"] is True


def test_contrato_retomada_detecta_mutacao_de_entrada(tmp_path) -> None:
    entrada = tmp_path / "entrada.csv"
    entrada.write_text("a,b\n1,2\n", encoding="utf-8")
    configuracao = {"sementes": [11], "contexto": 12}

    primeiro = _contrato_retomada(configuracao, [entrada])
    repetido = _contrato_retomada(configuracao, [entrada])
    entrada.write_text("a,b\n1,3\n", encoding="utf-8")
    alterado = _contrato_retomada(configuracao, [entrada])

    assert primeiro == repetido
    assert primeiro["sha256_entradas"] != alterado["sha256_entradas"]


def test_retomada_rejeita_configuracao_diferente_antes_do_treino(tmp_path) -> None:
    pasta = tmp_path / "execucao"
    pasta.mkdir()
    (pasta / "configuracao_execucao.json").write_text(
        json.dumps({"contexto": 999}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="configuracao da retomada difere"):
        executar_experimento(
            pasta,
            ConfiguracaoExperimento(sementes=(11,), modo_execucao="smoke"),
            retomar=True,
        )


@pytest.mark.parametrize(
    "parametro,valor,mensagem",
    [
        ("modo_execucao", "artigo", "modo_execucao"),
        ("contexto", 11, "contexto"),
        ("amostras_probabilisticas_por_semente", 0, "inteiro positivo"),
        ("nivel_intervalo", 1.0, "entre zero e um"),
    ],
)
def test_configuracao_rejeita_protocolo_invalido(parametro, valor, mensagem) -> None:
    with pytest.raises(ValueError, match=mensagem):
        ConfiguracaoExperimento(**{parametro: valor})


def test_series_gluonts_usam_treino_ate_2023_e_origens_rolling_2024() -> None:
    base = carregar_base_mensal_global()
    treino, historico, origens = _series_gluonts(base)

    assert len(treino) == len(historico) == len(origens) == 10
    assert all(len(serie) == 60 for serie in treino.values())
    assert all(len(serie) == 72 for serie in historico.values())
    assert all(periodos[0] == pd.Period("2023-12", freq="M") for periodos in origens.values())
    assert all(periodos[-1] == pd.Period("2024-11", freq="M") for periodos in origens.values())


def test_inversao_por_linha_respeita_escala_de_cada_localidade() -> None:
    base = carregar_base_mensal_global()
    teste = base.teste.reset_index(drop=True)
    valores = _inverter_por_linha(teste, np.zeros(len(teste)))

    assert np.allclose(valores, teste["minimo_treino"])

    extrapolados = _inverter_por_linha(teste, np.full(len(teste), 1.5))
    assert np.all(extrapolados > teste["maximo_treino"].to_numpy(dtype=float))


def test_resumo_macro_calcula_media_e_desvio_entre_sementes() -> None:
    metricas = pd.DataFrame(
        {
            "Localidade": ["A", "B", "A", "B"],
            "Modelo": ["M", "M", "M", "M"],
            "seed": [1, 1, 2, 2],
            "MAE_wm2": [1.0, 3.0, 2.0, 4.0],
            "MSE_wm4": [1.0, 9.0, 4.0, 16.0],
            "RMSE_wm2": [1.0, 3.0, 2.0, 4.0],
            "R2": [0.9, 0.8, 0.85, 0.75],
            "nRMSE_percentual": [1.0, 3.0, 2.0, 4.0],
        }
    )
    resumo = _resumo_modelos(metricas)

    assert resumo.loc[0, "MAE_media_wm2"] == pytest.approx(2.5)
    assert resumo.loc[0, "MAE_dp_sementes_wm2"] == pytest.approx(np.sqrt(0.5))


def test_resumo_usa_metricas_recalculadas_no_ensemble() -> None:
    por_seed = pd.DataFrame(
        {
            "Localidade": ["A", "A"],
            "Modelo": ["M", "M"],
            "seed": [1, 2],
            "MAE_wm2": [10.0, 14.0],
            "MSE_wm4": [100.0, 196.0],
            "RMSE_wm2": [10.0, 14.0],
            "R2": [0.0, -1.0],
            "nRMSE_percentual": [10.0, 14.0],
        }
    )
    principal = pd.DataFrame(
        {
            "Localidade": ["A"],
            "Modelo": ["M"],
            "MAE_wm2": [2.0],
            "MSE_wm4": [4.0],
            "RMSE_wm2": [2.0],
            "R2": [0.9],
            "nRMSE_percentual": [2.0],
        }
    )

    resumo = _resumo_modelos(por_seed, principal)

    assert resumo.loc[0, "MAE_media_wm2"] == pytest.approx(2.0)
    assert resumo.loc[0, "MAE_dp_sementes_wm2"] == pytest.approx(np.sqrt(8.0))


def test_mapeamento_gluonts_rejeita_previsao_duplicada() -> None:
    base = carregar_base_mensal_global()
    primeira = base.teste.iloc[0]
    serie = base.series[int(primeira["localidade_id"])]
    alvo = pd.Period(primeira["data_alvo"], freq="M")
    previsao = PrevisaoProbabilistica(
        localidade=serie.localidade,
        origem=alvo - 1,
        inicio_previsao=alvo,
        amostras=np.ones((5, 1)),
        seed=42,
    )

    with pytest.raises(ValueError, match="duplicada"):
        _mapear_amostras_gluonts(base, [previsao, previsao])
