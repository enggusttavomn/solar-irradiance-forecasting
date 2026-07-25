"""Testes da representacao mensal do protocolo global canonico."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import codigo_fonte.dados_mensais_globais as dados_globais
from codigo_fonte.dados_mensais_globais import (
    auditar_arquivos_diarios,
    carregar_base_mensal_global,
    matrizes_keras,
)
from codigo_fonte.modelos_tabulares_globais import prever_baselines_mensais


def test_base_global_tem_48_alvos_de_treino_e_12_de_teste_por_localidade() -> None:
    base = carregar_base_mensal_global()

    contagem = base.janelas.groupby(["Localidade", "particao"]).size().unstack()

    assert len(base.series) == 10
    assert (contagem["treino"] == 48).all()
    assert (contagem["teste"] == 12).all()
    assert base.treino["data_alvo"].max().year == 2023
    assert base.teste["data_alvo"].min().year == 2024


def test_auditoria_confirma_cobertura_diaria_e_metadados_dos_dez_csvs() -> None:
    auditoria = auditar_arquivos_diarios()

    assert len(auditoria) == 10
    assert (auditoria["linhas_brutas"] == 2192).all()
    assert (
        auditoria[
            [
                "datas_invalidas",
                "ghi_invalidas",
                "ghi_negativas",
                "datas_duplicadas",
                "dias_ausentes",
            ]
        ]
        == 0
    ).all().all()
    assert (auditoria["produto_dados"] == "GOES Aggregated PSM v4").all()
    assert (auditoria["intervalo_minutos"] == "60").all()


def test_transformacao_e_ajustada_somente_ate_o_ultimo_alvo_de_treino() -> None:
    base = carregar_base_mensal_global()

    for serie in base.series:
        treino_bruto = serie.ghi_wm2[: serie.indice_corte_alvo]
        assert serie.minimo_treino == float(treino_bruto.min())
        assert serie.maximo_treino == float(treino_bruto.max())
        niveis = serie.ghi_modelo * (base.niveis_quantizacao - 1)
        assert np.allclose(niveis, np.rint(niveis))
        assert np.logical_and(serie.ghi_modelo >= 0, serie.ghi_modelo <= 1).all()


def test_base_de_selecao_ajusta_transformacao_antes_da_validacao() -> None:
    base = carregar_base_mensal_global(
        limite_ajuste_transformacao="2023-01-01"
    )

    assert base.limite_ajuste_transformacao == pd.Timestamp("2023-01-01")
    for serie in base.series:
        assert serie.indice_corte_transformacao == 48
        assert serie.indice_corte_alvo == 60
        trecho = serie.ghi_wm2[:48]
        assert serie.minimo_treino == pytest.approx(trecho.min())
        assert serie.maximo_treino == pytest.approx(trecho.max())


def test_transformacao_de_selecao_termina_antes_da_validacao() -> None:
    base = carregar_base_mensal_global(
        limite_ajuste_transformacao="2023-01-01"
    )

    for serie in base.series:
        assert serie.indice_corte_transformacao == 48
        anterior_validacao = serie.ghi_wm2[:48]
        assert serie.minimo_treino == float(anterior_validacao.min())
        assert serie.maximo_treino == float(anterior_validacao.max())


def test_inversao_nao_trunca_previsoes_no_maximo_do_treino() -> None:
    serie = carregar_base_mensal_global().series[0]
    valores = serie.inverter(np.array([-10.0, 0.0, 1.5]))

    assert valores[0] == 0.0
    assert valores[1] == serie.minimo_treino
    assert valores[2] > serie.maximo_treino


def test_janelas_sao_causais_e_matrizes_recorrentes_tem_tempo_real() -> None:
    base = carregar_base_mensal_global()
    primeira = base.janelas.iloc[0]
    serie = base.series[int(primeira["localidade_id"])]
    alvo_idx = serie.datas.get_loc(primeira["data_alvo"])

    esperado = serie.ghi_modelo[alvo_idx - base.contexto : alvo_idx]
    observado = primeira.loc[list(base.colunas_lag)].to_numpy(dtype=float)
    assert np.allclose(observado, esperado)
    assert primeira["y_normalizado"] == serie.ghi_modelo[alvo_idx]

    sequencias, auxiliares, alvos = matrizes_keras(base.treino, base)
    assert sequencias.shape == (480, 12, 1)
    assert auxiliares.shape == (480, 15)
    assert alvos.shape == (480,)


def test_baselines_inguenuos_usam_ghi_fisica_sem_erro_de_quantizacao() -> None:
    base = carregar_base_mensal_global()
    previsoes = prever_baselines_mensais(base)

    primeira = base.teste.iloc[0]
    serie = base.series[int(primeira["localidade_id"])]
    alvo_idx = int(primeira["indice_alvo"])

    assert previsoes["Persistencia"][0] == serie.ghi_wm2[alvo_idx - 1]
    assert previsoes["SazonalIngenuo"][0] == serie.ghi_wm2[alvo_idx - 12]


def test_carregamento_mensal_rejeita_lacuna_e_dia_duplicado(tmp_path) -> None:
    caminho = tmp_path / "diario.csv"
    frame = pd.DataFrame(
        {
            "data": ["2024-01-01", "2024-01-01", "2024-01-03"],
            "ghi": [100.0, 101.0, 103.0],
        }
    )
    frame.to_csv(caminho, index=False)
    with pytest.raises(ValueError, match="duplicados"):
        dados_globais._carregar_mensal(caminho)

    frame = frame.drop(index=1)
    frame.to_csv(caminho, index=False)
    with pytest.raises(ValueError, match="ausentes"):
        dados_globais._carregar_mensal(caminho)


def test_contexto_menor_que_um_ano_e_rejeitado() -> None:
    with pytest.raises(ValueError, match="pelo menos 12"):
        carregar_base_mensal_global(contexto=11)
