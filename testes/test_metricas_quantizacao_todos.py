import numpy as np
import pandas as pd
import pytest

from codigo_fonte.acompanhamento.metricas_quantizacao_todos import calcular_metricas, comparar_amostras, comparar_metricas, validar_previsoes


def amostra():
    return pd.DataFrame({"localidade": ["A", "A", "B", "B"],
                         "origem": ["2024-01-31", "2024-02-29"] * 2,
                         "data_alvo": ["2024-01-31", "2024-02-29"] * 2,
                         "passo": [1] * 4, "ghi_real_wm2": [1., 3., 10., 20.],
                         "TimesNet_bruta_wm2": [2., 4., 12., 24.],
                         "TimesNet_wm2": [2., 4., 12., 24.]})


def test_macro_mse_independente_de_rmse():
    m = calcular_metricas(amostra(), "monthly_1", "TimesNet").iloc[0]
    assert m.MAE_wm2 == 2
    assert m.MSE_w2m4 == 5.5
    assert m.RMSE_wm2 == pytest.approx((1 + np.sqrt(10)) / 2)
    assert m.MSE_w2m4 != pytest.approx(m.RMSE_wm2 ** 2)
    assert m.N_localidades == 2 and m.N_pontos == 4


def test_ordem_das_linhas_nao_altera_amostra():
    comparar_amostras(amostra(), amostra().iloc[::-1])


@pytest.mark.parametrize("col,valor", [("ghi_real_wm2", 40.), ("data_alvo", "2024-03-31")])
def test_recusa_observacao_ou_data_diferente(col, valor):
    b = amostra()
    b.loc[0, col] = valor
    with pytest.raises(ValueError):
        comparar_amostras(amostra(), b)


def test_recusa_duplicata():
    a = amostra()
    with pytest.raises(ValueError):
        comparar_amostras(pd.concat([a, a.iloc[:1]]), a)


def test_validacao_fisica():
    validar_previsoes(amostra(), "monthly_1", "TimesNet", 2)
    a = amostra()
    a.loc[0, "TimesNet_wm2"] = -1
    with pytest.raises(ValueError, match="Pos-processamento"):
        validar_previsoes(a, "monthly_1", "TimesNet", 2)


def test_recusa_metrica_alterada():
    a = calcular_metricas(amostra(), "monthly_1", "TimesNet")
    b = a.copy()
    b.loc[0, "MSE_w2m4"] += 1
    with pytest.raises(ValueError):
        comparar_metricas(a, b)


def test_recusa_horizonte_incompleto():
    with pytest.raises(ValueError, match="horizontes"):
        validar_previsoes(amostra(), "monthly_6", "TimesNet", 2)
