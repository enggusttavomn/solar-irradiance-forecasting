"""Retoma, em etapas curtas, a execução horária interrompida por limite de sessão.

O script não altera o protocolo. Ele reutiliza a validação, o XGBoost final e
a LSTM final já persistidos pela execução canônica e divide apenas o restante
do TimesNet em três comandos menores que o limite operacional do ambiente.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

import codigo_fonte.experimento_horario_timesnet as exp
from codigo_fonte.dados_horarios_nsrdb import (
    PASTA_HORARIA_PADRAO,
    carregar_dados_horarios,
)


def _carregar_configuracao(saida: Path) -> exp.ConfiguracaoExperimentoHorario:
    conteudo = json.loads((saida / "configuracao_execucao.json").read_text())
    for chave in ("horizontes", "anos_treino"):
        conteudo[chave] = tuple(conteudo[chave])
    return exp.ConfiguracaoExperimentoHorario(**conteudo)


def _preparar(
    saida: Path,
) -> tuple[
    exp.ConfiguracaoExperimentoHorario,
    tuple[exp.SerieLocalidade, ...],
    pd.DataFrame,
]:
    configuracao = _carregar_configuracao(saida)
    dados = carregar_dados_horarios(
        PASTA_HORARIA_PADRAO,
        anos=range(configuracao.anos_treino[0], configuracao.ano_teste + 1),
    )
    series = exp.preparar_series_localidades(dados, configuracao)
    escalas = pd.read_csv(saida / "escalas_minmax_pre_corte.csv")
    return configuracao, series, escalas


def selecionar_timesnet(saida: Path) -> None:
    """Repete deterministicamente só a seleção do TimesNet e confere a previsão."""

    configuracao, series, escalas = _preparar(saida)
    treino = exp.construir_janelas_diarias(
        series,
        anos_origem=configuracao.anos_treino,
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="validacao_treino",
    )
    validacao = exp.construir_janelas_diarias(
        series,
        anos_origem=(configuracao.ano_validacao,),
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="validacao_2023",
    )
    escala = escalas.loc[escalas["ajuste"] == "treino_para_validacao"]
    x_treino, y_treino = treino.normalizar(escala)
    x_validacao, y_validacao = validacao.normalizar(escala)
    modelo = exp.criar_timesnet(configuracao, len(series))
    modelo, epocas, historico = exp.treinar_rede_direta(
        modelo,
        x_treino=x_treino,
        y_treino=y_treino,
        ids_treino=treino.localidade_id,
        configuracao=configuracao,
        x_validacao=x_validacao,
        y_validacao=y_validacao,
        ids_validacao=validacao.localidade_id,
    )
    previsao = validacao.inverter(
        exp.prever_rede_direta(
            modelo,
            x_validacao,
            validacao.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escala,
    ).reshape(-1)

    existente = pd.read_csv(
        saida / "previsoes_validacao.csv.gz",
        usecols=["previsao_bruta_timesnet_wm2"],
    )["previsao_bruta_timesnet_wm2"].to_numpy(dtype=float)
    erro_maximo = float(np.max(np.abs(previsao - existente)))
    if not np.allclose(previsao, existente, rtol=1e-5, atol=1e-5):
        raise RuntimeError(
            "A retomada não reproduziu a previsão TimesNet já persistida; "
            f"erro máximo={erro_maximo:.8g}."
        )

    pasta = saida / "retomada"
    pasta.mkdir(parents=True, exist_ok=True)
    exp._salvar_json(
        pasta / "epocas_timesnet.json",
        {
            "epocas_selecionadas": int(epocas),
            "erro_maximo_reproducao_validacao_wm2": erro_maximo,
            "previsao_validacao_reproduzida": True,
        },
    )
    exp._salvar_csv(
        pd.DataFrame(
            {"fase": "selecao_epocas", "Modelo": "TimesNet", **linha}
            for linha in historico
        ),
        pasta / "historico_timesnet_selecao.csv",
    )
    print(f"TimesNet selecionado em {epocas} épocas; erro máximo={erro_maximo:.3g}.")


def refit_timesnet(saida: Path) -> None:
    """Reajusta somente o TimesNet em 2019--2023 e persiste seu checkpoint."""

    configuracao, series, escalas = _preparar(saida)
    epocas = int(
        json.loads(
            (saida / "retomada" / "epocas_timesnet.json").read_text()
        )["epocas_selecionadas"]
    )
    refit = exp.construir_janelas_diarias(
        series,
        anos_origem=(*configuracao.anos_treino, configuracao.ano_validacao),
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="refit_2019_2023",
    )
    escala = escalas.loc[escalas["ajuste"] == "refit_para_teste"]
    x_refit, y_refit = refit.normalizar(escala)
    modelo = exp.criar_timesnet(configuracao, len(series))
    modelo, _, historico = exp.treinar_rede_direta(
        modelo,
        x_treino=x_refit,
        y_treino=y_refit,
        ids_treino=refit.localidade_id,
        configuracao=configuracao,
        epocas_fixas=epocas,
    )
    destino = saida / "modelos" / "timesnet_refit.pt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": modelo.state_dict(),
            "classe": "TimesNetHorario",
            "epocas_refit": epocas,
            "configuracao": asdict(configuracao),
        },
        destino,
    )
    exp._salvar_csv(
        pd.DataFrame(
            {"fase": "refit_epocas_fixas", "Modelo": "TimesNet", **linha}
            for linha in historico
        ),
        saida / "retomada" / "historico_timesnet_refit.csv",
    )
    print(f"TimesNet reajustado por {epocas} épocas e salvo em {destino}.")


def _carregar_epocas(saida: Path) -> dict[str, int]:
    lstm = torch.load(
        saida / "modelos" / "lstm_encoder_direto_refit.pt",
        map_location="cpu",
        weights_only=False,
    )
    timesnet = torch.load(
        saida / "modelos" / "timesnet_refit.pt",
        map_location="cpu",
        weights_only=False,
    )
    return {
        "LSTM": int(lstm["epocas_refit"]),
        "TimesNet": int(timesnet["epocas_refit"]),
    }


def consolidar(saida: Path) -> None:
    """Carrega os três modelos finais, infere 2024 e conclui os artefatos."""

    configuracao, series, escalas = _preparar(saida)
    teste = exp.construir_janelas_diarias(
        series,
        anos_origem=(configuracao.ano_teste,),
        seq_len=configuracao.seq_len,
        pred_len=configuracao.pred_len,
        particao="teste_2024",
    )
    escala = escalas.loc[escalas["ajuste"] == "refit_para_teste"]
    x_teste, _ = teste.normalizar(escala)
    previsoes = exp._previsoes_baselines(teste, series)

    xgb = joblib.load(saida / "modelos" / "xgboost_multioutput_refit.joblib")
    previsto = xgb.predict(
        exp._matriz_xgboost(x_teste, teste.localidade_id, len(series))
    )
    previsoes["XGBoost"] = teste.inverter(
        np.asarray(previsto).reshape(len(teste.x_bruto), configuracao.pred_len),
        escala,
    )

    checkpoint_lstm = torch.load(
        saida / "modelos" / "lstm_encoder_direto_refit.pt",
        map_location="cpu",
        weights_only=False,
    )
    lstm = exp.criar_lstm(configuracao, len(series))
    lstm.load_state_dict(checkpoint_lstm["state_dict"])
    previsoes["LSTM"] = teste.inverter(
        exp.prever_rede_direta(
            lstm,
            x_teste,
            teste.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escala,
    )

    checkpoint_timesnet = torch.load(
        saida / "modelos" / "timesnet_refit.pt",
        map_location="cpu",
        weights_only=False,
    )
    timesnet = exp.criar_timesnet(configuracao, len(series))
    timesnet.load_state_dict(checkpoint_timesnet["state_dict"])
    previsoes["TimesNet"] = teste.inverter(
        exp.prever_rede_direta(
            timesnet,
            x_teste,
            teste.localidade_id,
            batch_size=configuracao.batch_size,
        ),
        escala,
    )

    tabela_teste = exp.montar_tabela_previsoes(
        teste, previsoes, series, configuracao
    )
    metricas_teste, macro_teste = exp.calcular_metricas_horarias(
        tabela_teste, configuracao.horizontes
    )
    exp._salvar_csv(tabela_teste, saida / "previsoes_teste.csv.gz")

    tabela_validacao = pd.read_csv(saida / "previsoes_validacao.csv.gz")
    metricas_val, macro_val = exp.calcular_metricas_horarias(
        tabela_validacao, configuracao.horizontes
    )
    metricas = pd.concat((metricas_val, metricas_teste), ignore_index=True)
    macro = pd.concat((macro_val, macro_teste), ignore_index=True)
    exp._salvar_csv(metricas, saida / "metricas_por_localidade.csv")
    exp._salvar_csv(macro, saida / "metricas_macro.csv")

    historicos = []
    for nome in (
        "historico_timesnet_selecao.csv",
        "historico_timesnet_refit.csv",
    ):
        historicos.append(pd.read_csv(saida / "retomada" / nome))
    exp._salvar_csv(
        pd.concat(historicos, ignore_index=True),
        saida / "historico_treinamento.csv",
    )
    figura = saida / "figuras" / "previsao_horaria_timesnet_72h.png"
    exp.gerar_figura_timesnet_horaria(
        tabela_teste, series, configuracao, figura
    )

    epocas = _carregar_epocas(saida)
    resumo = macro.loc[
        (macro["particao"] == "teste_2024")
        & (macro["escopo"] == "todas_horas")
        & (macro["versao_previsao"] == "pos_processada")
    ]
    exp._salvar_json(
        saida / "resumo_execucao.json",
        {
            "modo_execucao": "completa",
            "resultado_smoke_nao_publicavel": False,
            "semente": int(configuracao.semente),
            "modelos": list(exp.MODELOS),
            "epocas_redes_escolhidas_em_2023": epocas,
            "retomada_por_limite_de_sessao": True,
            "metricas_macro_teste_pos_processadas": resumo.to_dict(
                orient="records"
            ),
        },
    )
    exp._salvar_json(
        saida / "status_execucao.json",
        {
            "etapa": "concluida",
            "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
            "modo_execucao": "completa",
            "resultado_smoke_nao_publicavel": False,
            "retomada_por_limite_de_sessao": True,
        },
    )
    exp._salvar_json(
        saida / "manifesto_artefatos.json",
        exp._manifesto(saida, configuracao, epocas),
    )
    print(f"Consolidação concluída em {saida}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--etapa",
        required=True,
        choices=("selecionar-timesnet", "refit-timesnet", "consolidar"),
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("resultados/avaliacao_horaria_timesnet"),
    )
    argumentos = parser.parse_args()
    if argumentos.etapa == "selecionar-timesnet":
        selecionar_timesnet(argumentos.saida)
    elif argumentos.etapa == "refit-timesnet":
        refit_timesnet(argumentos.saida)
    else:
        consolidar(argumentos.saida)


if __name__ == "__main__":
    main()
