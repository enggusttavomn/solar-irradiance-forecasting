"""Protecoes do relatorio contra resultados parciais ou selecao por teste."""
from copy import deepcopy
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_timesnet import SEMENTES, VARIANTES, validar_metadados, validar_previsoes, validar_diagnostico


def assinar(contrato, selecao):
    corpo = {k: v for k, v in contrato.items() if k != "sha256_contrato"}
    contrato["sha256_contrato"] = hashlib.sha256(json.dumps(corpo, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    selecao["contrato_sha256"] = contrato["sha256_contrato"]


@pytest.fixture
def metadados():
    contrato = {"tarefa": {"slug": "monthly_1"}, "minmax": True, "regressao": "continua",
        "quantizacao": {"onde": "somente_entradas", "alvos_quantizados": False,
                        "pesos_quantizados": False, "controle": "sem_quantizacao_e_sem_clip",
                        "intervalo": [0, 1], "niveis": [64, 128, 256]},
        "configuracao": {"sementes": SEMENTES, "modo_execucao": "completa",
                         "max_epocas_mensal": 300, "paciencia_mensal": 30},
        "candidato_base": {"alvo": "bruto"}, "dispositivo": "cpu",
        "variantes": [{"nome": n, "niveis": k} for n, k in VARIANTES.items()]}
    ranking = [{"nome": n, "niveis": k, "MAE_validacao_wm2": float(10 + i),
                "epocas": {str(s): 10 for s in SEMENTES}}
               for i, (n, k) in enumerate(VARIANTES.items())]
    selecao = {"tarefa": "monthly_1", "selecao_concluida_antes_do_teste": True,
               "modo": "completa", "ranking": ranking, "vencedor": ranking[0]}
    status = {"tarefa": "monthly_1", "etapa": "concluida", "modo": "completa",
              "teste_avaliado": True, "vencedor": ranking[0]}
    assinar(contrato, selecao)
    return contrato, selecao, status


def test_aceita_quatro_variantes_completas(metadados):
    validar_metadados("monthly_1", *metadados)


@pytest.mark.parametrize("campo,valor", [("etapa", "avaliando"), ("modo", "smoke"), ("teste_avaliado", False)])
def test_recusa_execucao_parcial(metadados, campo, valor):
    contrato, selecao, status = metadados
    status[campo] = valor
    with pytest.raises(ValueError, match="incompleto ou smoke"):
        validar_metadados("monthly_1", contrato, selecao, status)


@pytest.mark.parametrize("campo", ["alvos_quantizados", "pesos_quantizados"])
def test_recusa_quantizacao_fora_da_entrada(metadados, campo):
    contrato, selecao, status = metadados
    contrato["quantizacao"][campo] = True
    assinar(contrato, selecao)
    with pytest.raises(ValueError, match="alvo continuo"):
        validar_metadados("monthly_1", contrato, selecao, status)


def test_recusa_nivel_ausente(metadados):
    contrato, selecao, status = metadados
    selecao["ranking"].pop()
    with pytest.raises(ValueError, match="quatro niveis"):
        validar_metadados("monthly_1", contrato, selecao, status)


def test_recusa_vencedor_diferente_do_menor_mae_validacao(metadados):
    contrato, selecao, status = metadados
    selecao["vencedor"] = selecao["ranking"][2]
    status["vencedor"] = selecao["vencedor"]
    with pytest.raises(ValueError, match="MAE de validacao"):
        validar_metadados("monthly_1", contrato, selecao, status)


def test_recusa_selecao_com_quatro_sementes(metadados):
    contrato, selecao, status = metadados
    selecao["ranking"][0]["epocas"].pop("89")
    with pytest.raises(ValueError, match="sementes/epocas"):
        validar_metadados("monthly_1", contrato, selecao, status)


def test_recusa_contrato_adulterado(metadados):
    contrato, selecao, status = metadados
    contrato["candidato_base"]["perda"] = "mae"
    with pytest.raises(ValueError, match="Hash do contrato"):
        validar_metadados("monthly_1", contrato, selecao, status)


def previsoes():
    linhas = []
    for local in range(10):
        for mes in range(1, 13):
            row = {"localidade": str(local), "origem": f"2024-{mes:02d}-01",
                   "data_alvo": f"2024-{mes:02d}-01", "passo": 1, "ghi_real_wm2": 30.0}
            for i, s in enumerate(SEMENTES):
                row[f"previsao_bruta_timesnet_seed{s}_wm2"] = float(i + mes)
                row[f"previsao_pos_timesnet_seed{s}_wm2"] = float(i + mes)
            row["previsao_bruta_timesnet_ensemble_wm2"] = float(mes + 2)
            row["previsao_pos_timesnet_ensemble_wm2"] = float(mes + 2)
            linhas.append(row)
    return pd.DataFrame(linhas)


def test_ensemble_calculado_de_cinco_sementes_em_escala_fisica():
    df = previsoes()
    assert len(validar_previsoes(df, "monthly_1", 2024)) == 120
    df.loc[0, "previsao_bruta_timesnet_seed89_wm2"] += 5
    with pytest.raises(ValueError, match="Ensemble"):
        validar_previsoes(df, "monthly_1", 2024)


def test_recusa_periodo_errado_e_amostra_parcial():
    df = previsoes()
    with pytest.raises(ValueError, match="Amostra/periodo"):
        validar_previsoes(df.iloc[:-1], "monthly_1", 2024)
    df.loc[0, "data_alvo"] = "2023-01-01"
    with pytest.raises(ValueError, match="Amostra/periodo"):
        validar_previsoes(df, "monthly_1", 2024)


def test_clipping_separa_controle_sem_clipping_dos_niveis_quantizados():
    locais = {str(i): {"total": 100, "abaixo_zero": 1, "acima_um": 2, "saturados": 3} for i in range(10)}
    diag = {**locais, "total": {"niveis": 64, "total": 1000, "abaixo_zero": 10,
                              "acima_um": 20, "saturados": 30, "fracao_saturados": .03}}
    assert validar_diagnostico(diag, 64, 1000)["saturados"] == 30
    diag["total"].update(niveis=None, saturados=0, fracao_saturados=0.)
    for local in locais:
        diag[local]["saturados"] = 0
    assert validar_diagnostico(diag, None, 1000)["saturados"] == 0
    diag["total"]["saturados"] = 30
    with pytest.raises(ValueError, match="clipping"):
        validar_diagnostico(diag, None, 1000)