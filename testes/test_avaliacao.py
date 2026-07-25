"""Testes das metricas e dos artefatos tabulares de avaliacao."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.avaliacao import (
    calcular_metricas_probabilisticas,
    crps_empirico,
    comparar_mae_com_referencia,
    calcular_metricas,
    desnormalizar_ghi,
    resumir_metricas_por_modelo,
    salvar_metricas,
    salvar_previsoes,
)


def test_metricas_conferem_com_calculo_manual() -> None:
    metricas = calcular_metricas(
        [100.0, 200.0, 300.0],
        [100.0, 200.0, 240.0],
        "Modelo de teste",
        sufixo="wm2",
    )

    assert metricas["Modelo"] == "Modelo de teste"
    assert metricas["MAE_wm2"] == pytest.approx(20.0)
    assert metricas["MSE_wm2"] == pytest.approx(1200.0)
    assert metricas["RMSE_wm2"] == pytest.approx(np.sqrt(1200.0))
    assert metricas["R2_wm2"] == pytest.approx(0.82)
    assert metricas["nRMSE_wm2"] == pytest.approx(np.sqrt(1200.0) / 200.0)
    assert metricas["nRMSE_percentual_wm2"] == pytest.approx(
        100 * np.sqrt(1200.0) / 200.0
    )


def test_nrmse_e_indefinido_quando_media_real_e_zero() -> None:
    metricas = calcular_metricas([-1.0, 0.0, 1.0], [0.0, 0.0, 0.0], "zero")

    assert np.isnan(metricas["nRMSE"])
    assert np.isnan(metricas["nRMSE_percentual"])


def test_crps_empirico_e_zero_para_distribuicao_perfeita_degenerada() -> None:
    # Duas amostras iguais sao permitidas e representam uma previsao pontual.
    valores = crps_empirico([1.0, 2.0], [[1.0, 1.0], [2.0, 2.0]])

    assert valores.tolist() == pytest.approx([0.0, 0.0])


def test_metricas_probabilisticas_calculam_cobertura_e_largura() -> None:
    metricas = calcular_metricas_probabilisticas(
        [1.0, 5.0],
        [[0.0, 1.0, 2.0], [0.0, 1.0, 2.0]],
        "Probabilistico",
        nivel_intervalo=0.8,
    )

    assert metricas["CRPS_wm2"] >= 0
    assert metricas["PICP"] == pytest.approx(0.5)
    assert metricas["PICP_percentual"] == pytest.approx(50.0)
    assert metricas["MPIW_wm2"] == pytest.approx(1.6)


def test_desnormalizacao_limita_previsoes_a_faixa_de_ajuste() -> None:
    valores = desnormalizar_ghi([-0.2, 0.0, 0.5, 1.0, 1.2], {"min": 100, "max": 300})

    assert valores.tolist() == pytest.approx([100, 100, 200, 300, 300])


def test_salvar_metricas_cria_csv_recarregavel(tmp_path) -> None:
    caminho = tmp_path / "subpasta" / "metricas.csv"
    tabela = salvar_metricas(
        [calcular_metricas([1, 2, 3], [1, 2, 3], "Perfeito")], caminho
    )

    assert caminho.exists()
    pd.testing.assert_frame_equal(pd.read_csv(caminho), tabela)


def test_salvar_previsoes_alinha_por_posicao_e_mantem_unidades(tmp_path) -> None:
    datas = pd.Series(pd.date_range("2024-01-31", periods=3, freq="ME"), index=[10, 11, 12])
    reais = pd.Series([0.1, 0.2, 0.3], index=[10, 11, 12])
    reais_wm2 = pd.Series([100.0, 200.0, 300.0], index=[10, 11, 12])
    pred = pd.Series([0.11, 0.19, 0.31], index=[50, 51, 52])
    pred_wm2 = pd.Series([110.0, 190.0, 310.0], index=[50, 51, 52])

    tabela = salvar_previsoes(
        datas,
        reais,
        {"Modelo": pred},
        tmp_path,
        y_true_original=reais_wm2,
        predicoes_original={"Modelo": pred_wm2},
    )

    assert tabela["ghi_previsto_modelo_normalizado"].tolist() == pytest.approx(pred.tolist())
    assert tabela["ghi_previsto_modelo_wm2"].tolist() == pytest.approx(pred_wm2.tolist())
    assert (tmp_path / "previsoes_modelo.csv").exists()
    assert (tmp_path / "previsoes_modelos.csv").exists()


def _metricas_localidades() -> pd.DataFrame:
    linhas = []
    for indice in range(8):
        localidade = f"Local {indice + 1}"
        linhas.extend(
            [
                {"Localidade": localidade, "Modelo": "Climatologia", "MAE_wm2": 10.0},
                {"Localidade": localidade, "Modelo": "Melhor", "MAE_wm2": 5.0},
                {"Localidade": localidade, "Modelo": "Pior", "MAE_wm2": 15.0},
                {"Localidade": localidade, "Modelo": "Igual", "MAE_wm2": 10.0},
            ]
        )
    return pd.DataFrame(linhas)


def test_resumo_bootstrap_e_reprodutivel_e_ordenado() -> None:
    metricas = pd.DataFrame(
        {
            "Localidade": ["A", "B", "C", "A", "B", "C"],
            "Modelo": ["M1", "M1", "M1", "M2", "M2", "M2"],
            "MAE_wm2": [1.0, 2.0, 3.0, 3.0, 4.0, 5.0],
        }
    )

    primeiro = resumir_metricas_por_modelo(metricas, n_bootstrap=1000, random_state=7)
    segundo = resumir_metricas_por_modelo(metricas, n_bootstrap=1000, random_state=7)

    pd.testing.assert_frame_equal(primeiro, segundo)
    assert primeiro["Modelo"].tolist() == ["M1", "M2"]
    assert primeiro["Media"].tolist() == pytest.approx([2.0, 4.0])
    assert (primeiro["IC95_inferior"] <= primeiro["Media"]).all()
    assert (primeiro["Media"] <= primeiro["IC95_superior"]).all()


def test_comparacao_define_sinal_ic_e_holm_corretamente() -> None:
    resultado = comparar_mae_com_referencia(
        _metricas_localidades(),
        referencia="Climatologia",
        n_bootstrap=2000,
        random_state=42,
    ).set_index("Modelo")

    # Diferenca = MAE(modelo) - MAE(referencia): negativa favorece o modelo.
    assert resultado.loc["Melhor", "Diferenca_MAE_wm2"] == pytest.approx(-5.0)
    assert resultado.loc["Melhor", "IC95_superior"] < 0
    assert resultado.loc["Melhor", "Conclusao_IC95"] == "modelo_melhor"
    assert resultado.loc["Pior", "Diferenca_MAE_wm2"] == pytest.approx(5.0)
    assert resultado.loc["Pior", "IC95_inferior"] > 0
    assert resultado.loc["Pior", "Conclusao_IC95"] == "referencia_melhor"
    assert resultado.loc["Igual", "Conclusao_IC95"] == "inconclusivo"
    assert resultado.loc["Igual", "Wilcoxon_p"] == pytest.approx(1.0)

    assert resultado.loc["Melhor", "Wilcoxon_p"] == pytest.approx(0.0078125)
    assert resultado.loc["Pior", "Wilcoxon_p"] == pytest.approx(0.0078125)
    assert resultado.loc["Melhor", "Wilcoxon_p_Holm"] == pytest.approx(0.0234375)
    assert resultado.loc["Pior", "Wilcoxon_p_Holm"] == pytest.approx(0.0234375)
    assert (resultado["Wilcoxon_p_Holm"] >= resultado["Wilcoxon_p"]).all()


@pytest.mark.parametrize("funcao", [resumir_metricas_por_modelo, comparar_mae_com_referencia])
def test_estatisticas_rejeitam_esquema_incompleto(funcao) -> None:
    metricas = pd.DataFrame({"Localidade": ["A"], "Modelo": ["M"]})

    with pytest.raises(ValueError, match="Colunas ausentes.*MAE_wm2"):
        funcao(metricas, n_bootstrap=10)


def test_comparacao_rejeita_referencia_ausente_e_pares_insuficientes() -> None:
    metricas = pd.DataFrame(
        {
            "Localidade": ["A", "A"],
            "Modelo": ["Climatologia", "M"],
            "MAE_wm2": [10.0, 9.0],
        }
    )

    with pytest.raises(ValueError, match="Referencia ausente"):
        comparar_mae_com_referencia(metricas, referencia="Outra", n_bootstrap=10)
    with pytest.raises(ValueError, match="Pares insuficientes"):
        comparar_mae_com_referencia(metricas, n_bootstrap=10)


def test_resumo_rejeita_bootstrap_nao_positivo() -> None:
    with pytest.raises(ValueError, match="n_bootstrap deve ser positivo"):
        resumir_metricas_por_modelo(_metricas_localidades(), n_bootstrap=0)
