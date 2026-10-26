"""Integridade dos dados destinados aos apendices horario e diario."""
import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from scripts import gerar_pdf_quantizacao_quatro_casos as pdf


def assinar(contrato, selecao):
    corpo = {k: v for k, v in contrato.items() if k != "sha256_contrato"}
    contrato["sha256_contrato"] = hashlib.sha256(json.dumps(
        corpo, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    selecao["contrato_sha256"] = contrato["sha256_contrato"]


def metadados(tarefa="daily_30"):
    contexto = 336 if tarefa == "hourly_72_extension" else 365
    contrato = {"tarefa": {"slug": tarefa, "seq_len": contexto, "horizontes": pdf.TAREFAS[tarefa]},
        "minmax": True, "sementes": pdf.SEMENTES[tarefa], "dispositivo": "cuda",
        "n_localidades": 10, "modo": "completa",
        "quantizacao": {"onde": "somente_entradas", "alvos_quantizados": False,
                        "pesos_quantizados": False, "controle": "sem_quantizacao_e_sem_clip",
                        "intervalo": [0, 1], "niveis": [64, 128, 256]},
        "configuracao": {"modo_execucao": "completa", "max_epocas_diario": 30, "paciencia_diario": 5},
        "candidato_base": {"contexto": contexto, "perda": "mae"},
        "variantes": [{"nome": n, "niveis": k} for n, k in pdf.VARIANTES.items()]}
    ranking = [{"nome": n, "niveis": k, "MAE_validacao_wm2": float(10 + i),
                "epocas": {str(s): 10 for s in pdf.SEMENTES[tarefa]}}
               for i, (n, k) in enumerate(pdf.VARIANTES.items())]
    selecao = {"tarefa": tarefa, "selecao_concluida_antes_do_teste": True,
               "modo": "completa", "ranking": ranking, "vencedor": ranking[0]}
    status = {"tarefa": tarefa, "etapa": "concluida", "modo": "completa",
              "teste_avaliado": True, "vencedor": ranking[0]}
    assinar(contrato, selecao)
    return contrato, selecao, status


@pytest.mark.parametrize("tarefa", pdf.TAREFAS)
def test_aceita_sementes_corretas_de_cada_resolucao(tarefa):
    pdf.validar_metadados(tarefa, *metadados(tarefa))


@pytest.mark.parametrize("campo,valor", [("etapa", "avaliando"), ("modo", "smoke"), ("teste_avaliado", False)])
def test_recusa_execucao_parcial(campo, valor):
    contrato, selecao, status = metadados()
    status[campo] = valor
    with pytest.raises(ValueError, match="incompleto ou smoke"):
        pdf.validar_metadados("daily_30", contrato, selecao, status)


def test_recusa_troca_de_sementes_entre_resolucoes():
    contrato, selecao, status = metadados("hourly_72_extension")
    contrato["sementes"] = [11, 23, 42, 67, 89]
    assinar(contrato, selecao)
    with pytest.raises(ValueError, match="sementes"):
        pdf.validar_metadados("hourly_72_extension", contrato, selecao, status)


@pytest.mark.parametrize("campo", ["alvos_quantizados", "pesos_quantizados"])
def test_recusa_quantizacao_fora_da_entrada(campo):
    contrato, selecao, status = metadados()
    contrato["quantizacao"][campo] = True
    assinar(contrato, selecao)
    with pytest.raises(ValueError, match="quantizacao incoerente"):
        pdf.validar_metadados("daily_30", contrato, selecao, status)


def test_recusa_vencedor_escolhido_fora_do_ranking_validacao():
    contrato, selecao, status = metadados()
    selecao["vencedor"] = selecao["ranking"][2]
    status["vencedor"] = selecao["vencedor"]
    with pytest.raises(ValueError, match="MAE de validacao"):
        pdf.validar_metadados("daily_30", contrato, selecao, status)


def test_recusa_epoca_acima_do_teto():
    contrato, selecao, status = metadados()
    selecao["ranking"][0]["epocas"]["11"] = 31
    with pytest.raises(ValueError, match="epocas"):
        pdf.validar_metadados("daily_30", contrato, selecao, status)


def test_recusa_adulteracao_do_contrato():
    contrato, selecao, status = metadados()
    contrato["candidato_base"]["perda"] = "mse"
    with pytest.raises(ValueError, match="Hash do contrato"):
        pdf.validar_metadados("daily_30", contrato, selecao, status)


def previsoes(tarefa, ano=2024):
    n, pred = pdf.ORIGENS[tarefa][ano], max(pdf.TAREFAS[tarefa])
    origens = pd.date_range(f"{ano}-01-01", periods=n, freq="D")
    passo = np.tile(np.arange(1, pred + 1), 10 * n)
    origem = np.tile(np.repeat(origens.values, pred), 10)
    alvo = origem + pd.to_timedelta(passo - 1, unit="h" if tarefa == "hourly_72_extension" else "D")
    df = pd.DataFrame({"localidade": np.repeat([f"local{i}" for i in range(10)], n * pred),
                       "origem": origem, "data_alvo": alvo, "passo": passo,
                       "ghi_real_wm2": 100.0 + passo})
    if tarefa == "hourly_72_extension":
        df["elevacao_solar_graus"] = np.where(passo % 24 < 12, -10.0, 30.0)
    brutas = []
    for i, s in enumerate(pdf.SEMENTES[tarefa]):
        bruto = passo.astype(float) + i
        pos = np.maximum(bruto, 0)
        if tarefa == "hourly_72_extension":
            pos[df.elevacao_solar_graus <= 0] = 0
        df[f"previsao_bruta_timesnet_seed{s}_wm2"] = bruto
        df[f"previsao_pos_timesnet_seed{s}_wm2"] = pos
        brutas.append(bruto)
    media = np.mean(brutas, axis=0)
    df["previsao_bruta_timesnet_ensemble_wm2"] = media
    if tarefa == "hourly_72_extension":
        media[df.elevacao_solar_graus <= 0] = 0
    df[pdf.COLUNA_PREVISAO] = media
    return df


@pytest.mark.parametrize("tarefa", pdf.TAREFAS)
def test_previsoes_completas_com_protocolo_de_cada_resolucao(tarefa):
    df = previsoes(tarefa)
    assert len(pdf.validar_previsoes(df, tarefa, 2024)) == len(df)


def test_recusa_mascara_noturna_incoerente():
    df = previsoes("hourly_72_extension")
    df.loc[0, pdf.COLUNA_PREVISAO] = 1
    with pytest.raises(ValueError, match="pos-processamento"):
        pdf.validar_previsoes(df, "hourly_72_extension", 2024)


def test_recusa_media_das_previsoes_positivas_no_lugar_da_media_bruta():
    df = previsoes("daily_30")
    df.loc[0, "previsao_bruta_timesnet_seed11_wm2"] = -100
    df.loc[0, "previsao_pos_timesnet_seed11_wm2"] = 0
    brutas = [f"previsao_bruta_timesnet_seed{s}_wm2" for s in pdf.SEMENTES["daily_30"]]
    df.loc[0, "previsao_bruta_timesnet_ensemble_wm2"] = df.loc[0, brutas].mean()
    with pytest.raises(ValueError, match="Ensemble"):
        pdf.validar_previsoes(df, "daily_30", 2024)


def test_recusa_dados_parciais():
    df = previsoes("daily_30")
    with pytest.raises(ValueError, match="Amostra/periodo"):
        pdf.validar_previsoes(df.iloc[:-1], "daily_30", 2024)


def test_mse_macro_conferido_separadamente():
    valores = {k: float(i + 1) for i, k in enumerate(pdf.METRICAS)}
    calculadas = pd.DataFrame([{"horizonte": h, **valores} for h in pdf.TAREFAS["daily_30"]])
    salvas = calculadas.assign(tarefa="daily_30", particao="teste_2024", tipo_horizonte="cumulativo")
    pdf.conferir_macro(salvas, calculadas, "daily_30", "teste_2024")
    salvas.loc[0, "MSE_w2m4"] += 1
    with pytest.raises(ValueError, match="MSE_w2m4"):
        pdf.conferir_macro(salvas, calculadas, "daily_30", "teste_2024")
