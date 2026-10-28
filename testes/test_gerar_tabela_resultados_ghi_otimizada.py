"""Protecoes da tabela contra agregacao incorreta e comparacoes desalinhadas."""

import numpy as np
import pandas as pd
import pytest

from scripts.gerar_tabela_resultados_ghi_otimizada import (
    calcular_macro,
    conferir_observacoes,
    nota_teto_epocas,
    normalizar_chaves,
    validar_mensal_pura,
)


def previsoes(locais=2):
    linhas = []
    for local in range(locais):
        for passo, real in enumerate((10.0, 20.0), 1):
            linhas.append({"localidade": f"local_{local}", "origem": "2024-01-01",
                           "data_alvo": f"2024-01-0{passo}", "passo": passo,
                           "ghi_real_wm2": real, "previsto": real + (1 if local == 0 else 3)})
    return pd.DataFrame(linhas)


def test_macro_mse_nao_e_quadrado_do_macro_rmse():
    result = calcular_macro(previsoes(), "previsto", (1, 2)).set_index("horizonte")
    # Erros locais constantes de 1 e 3: macro-MSE = (1+9)/2 = 5,
    # macro-RMSE = (1+3)/2 = 2. Portanto, macro-RMSE^2 = 4 esta errado.
    assert result.loc[2, "MSE_w2m4"] == pytest.approx(5)
    assert result.loc[2, "RMSE_wm2"] == pytest.approx(2)
    assert result.loc[2, "MAE_wm2"] == pytest.approx(2)
    assert result.loc[2, "nRMSE"] == pytest.approx(2 / 15)
    assert result.loc[2, "R2"] == pytest.approx(0.8)
    assert result.loc[2, "N_origens"] == 2
    assert result.loc[2, "N_pontos"] == 4


def test_horizonte_e_cumulativo():
    dados = previsoes(1)
    dados.loc[1, "previsto"] = 25
    result = calcular_macro(dados, "previsto", (1, 2)).set_index("horizonte")
    assert result.loc[1, "MAE_wm2"] == pytest.approx(1)
    assert result.loc[2, "MAE_wm2"] == pytest.approx(3)
    assert result.loc[2, "MSE_w2m4"] == pytest.approx(13)


def test_chaves_horarias_e_fusos_equivalentes():
    original = previsoes(10)
    outras = original.rename(columns={"origem": "origem_utc", "data_alvo": "timestamp_alvo_utc", "passo": "passo_h"})
    outras["origem_utc"] = "2024-01-01 00:00:00+00:00"
    conferir_observacoes(original, outras.iloc[::-1])


def test_rejeita_observacao_diferente():
    dados = previsoes(10)
    outras = dados.copy()
    outras.loc[0, "ghi_real_wm2"] += 1
    with pytest.raises(ValueError, match="observacoes"):
        conferir_observacoes(dados, outras)


def test_rejeita_origem_diferente_e_amostra_incompleta():
    dados = previsoes(10)
    outras = dados.copy()
    outras.loc[0, "origem"] = "2023-12-31"
    with pytest.raises(ValueError, match="origens/alvos"):
        conferir_observacoes(dados, outras)
    with pytest.raises(ValueError, match="origens/alvos"):
        conferir_observacoes(dados.iloc[:-1], dados)


def test_rejeita_duplicatas_e_nan():
    dados = previsoes()
    with pytest.raises(ValueError, match="duplicadas"):
        normalizar_chaves(pd.concat([dados, dados]))
    dados.loc[0, "previsto"] = np.nan
    with pytest.raises(ValueError, match="nao finitas"):
        calcular_macro(dados, "previsto", (1, 2))


def test_nota_teto_le_limite_do_contrato():
    selecao = {"vencedor": {"epocas": {"42": 45}}}
    contrato = {"configuracao": {"max_epocas_diario": 45}}
    nota = nota_teto_epocas("hourly_72_extension", selecao, contrato)
    assert "45 épocas" in nota
    assert "semente 42" in nota
    assert "pode não ter convergido" in nota


def test_nota_teto_conta_apenas_sementes_que_alcancaram_limite():
    selecao = {"vencedor": {"epocas": {"11": 30, "23": 25, "42": 30, "67": 22, "89": 27}}}
    contrato = {"configuracao": {"max_epocas_diario": 30}}
    assert "2/5 sementes" in nota_teto_epocas("daily_30", selecao, contrato)


@pytest.mark.parametrize("tarefa,epocas", [
    ("daily_30", {"11": 29, "23": 20}),
    ("hourly_72_extension", {}),
    ("monthly_1", {"42": 30}),
])
def test_nota_teto_nao_presume_convergencia_ou_epocas_ausentes(tarefa, epocas):
    selecao = {"vencedor": {"epocas": epocas}}
    contrato = {"configuracao": {"max_epocas_diario": 30}}
    assert nota_teto_epocas(tarefa, selecao, contrato) == ""


@pytest.fixture
def mensal_pura():
    candidato = {"nome": "mae", "perda": "mae", "seq_len": 12, "d_model": 8,
                 "d_ff": 16, "blocos": 1, "dropout": 0.1, "taxa_aprendizado": 0.001}
    contrato = {"tarefa": "monthly_1", "quantizacao": False, "candidatos": [candidato],
                "configuracao": {"sementes": [11, 23, 42, 67, 89]}}
    selecao = {"tarefa": {"slug": "monthly_1"},
               "vencedor": {**candidato, "epocas": {str(s): 10 for s in (11, 23, 42, 67, 89)}}}
    return selecao, contrato


@pytest.mark.parametrize("alvo_explicito", [False, True])
def test_mensal_pura_aceita_legado_e_alvo_bruto(mensal_pura, alvo_explicito):
    selecao, contrato = mensal_pura
    if alvo_explicito:
        contrato["candidatos"][0]["alvo"] = "bruto"
        selecao["vencedor"]["alvo"] = "bruto"
    validar_mensal_pura("monthly_1", selecao, contrato)


@pytest.mark.parametrize("alvo", ["anomalia", "climatologia", None])
def test_mensal_pura_rejeita_candidato_hibrido_mesmo_com_vencedor_bruto(mensal_pura, alvo):
    selecao, contrato = mensal_pura
    contrato["candidatos"].append({"nome": "outro", "alvo": alvo})
    with pytest.raises(ValueError, match="todos os candidatos com alvo bruto"):
        validar_mensal_pura("monthly_1", selecao, contrato)


def test_mensal_pura_rejeita_vencedor_por_anomalia(mensal_pura):
    selecao, contrato = mensal_pura
    selecao["vencedor"]["alvo"] = "anomalia"
    with pytest.raises(ValueError, match="alvo bruto"):
        validar_mensal_pura("monthly_1", selecao, contrato)


def test_mensal_pura_rejeita_contrato_com_climatologia(mensal_pura):
    selecao, contrato = mensal_pura
    contrato["climatologia_anomalia"] = "media_por_mes_civil"
    with pytest.raises(ValueError, match="hibrido com climatologia"):
        validar_mensal_pura("monthly_1", selecao, contrato)


@pytest.mark.parametrize("campo,valor", [("nome", "nao_declarado"), ("d_model", 16), ("seq_len", 24)])
def test_mensal_pura_rejeita_vencedor_incoerente(mensal_pura, campo, valor):
    selecao, contrato = mensal_pura
    selecao["vencedor"][campo] = valor
    with pytest.raises(ValueError, match="incoerente"):
        validar_mensal_pura("monthly_1", selecao, contrato)


def test_mensal_pura_rejeita_quantizacao_e_ensemble_incompleto(mensal_pura):
    selecao, contrato = mensal_pura
    contrato["quantizacao"] = True
    with pytest.raises(ValueError, match="sem quantizacao"):
        validar_mensal_pura("monthly_1", selecao, contrato)
    contrato["quantizacao"] = False
    del selecao["vencedor"]["epocas"]["89"]
    with pytest.raises(ValueError, match="cinco sementes"):
        validar_mensal_pura("monthly_1", selecao, contrato)
