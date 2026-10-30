"""Diagnostico somente leitura do controle ARIMA; nao ajusta modelos."""
from pathlib import Path
import ast
import json

import joblib
import numpy as np
import pandas as pd

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as run


def comparacao(a, b):
    a, b = np.asarray(a), np.asarray(b)
    igual = a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()
    return {"shape_a": list(a.shape), "shape_b": list(b.shape),
            "dtype_a": str(a.dtype), "dtype_b": str(b.dtype), "bit_a_bit": igual,
            "delta_maximo": float(np.max(np.abs(a-b))) if a.shape == b.shape else None,
            "diferentes": int(np.count_nonzero(a != b)) if a.shape == b.shape else None}


def main():
    tarefa = "hourly_72_extension"
    pasta = run.SAIDA / "atual" / tarefa / "arima"
    fonte = run.e.SAIDA / tarefa / "arima_robusto"
    destino = run.RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/diagnostico_arima_horario"
    destino.mkdir(parents=True, exist_ok=True)
    print("Preparando contexto novo e original, sem novos ajustes", flush=True)
    novo = run.motor.preparar_contexto(tarefa, "selecao")
    antigo = run.e.preparar_contexto(tarefa, "completa")
    jn, ja = novo.janelas["validacao"], antigo.janelas["validacao_2023"]
    xn = run.q.normalizar_entradas(jn, novo.escalas["selecao"], None)
    xa, ya = ja.normalizar(antigo.escalas["selecao"])
    dados = {"x_bruto": comparacao(jn.x_bruto, ja.x_bruto),
             "y_bruto": comparacao(jn.y_bruto, ja.y_bruto),
             "x_normalizado": comparacao(xn, xa),
             "ids": comparacao(jn.localidade_id, ja.localidade_id),
             "escalas": comparacao(novo.escalas["selecao"].select_dtypes("number").to_numpy(),
                                    antigo.escalas["selecao"].select_dtypes("number").to_numpy()),
             "origens_locais_iguais": jn.origem_local.equals(ja.origem_local)}
    with np.load(fonte / "cache/deterministica.npz", allow_pickle=False) as z:
        po = z["validacao_2023_bruta"].copy()
    with np.load(pasta / "sem_quantizacao/selecao/seed-1.npz", allow_pickle=False) as z:
        pn = z["previsao"].copy()
    csv = pd.read_csv(fonte / "selecao_arima.csv", float_precision="round_trip")
    registros = []
    por_id = {s.localidade_id: s for s in antigo.series}
    for serie in novo.series:
        ident = int(serie.localidade_id)
        uso = jn.localidade_id == ident
        cp = joblib.load(pasta / "sem_quantizacao/modelos" / f"localidade{ident}_selecao.joblib")
        yn = run.e.serie_ajuste_arima(novo, serie, "selecao")
        yo = run.e.serie_ajuste_arima(antigo, por_id[ident], "selecao")
        previa = csv[(csv.localidade == serie.localidade) & (csv.fase == "selecao") &
                     (csv.selecionada.astype(str).str.lower() == "true")].iloc[0]
        tentativas = json.loads(previa.tentativas)
        reg = {"localidade": serie.localidade, "localidade_id": ident,
               "historico_fit": comparacao(yn, yo),
               "historico_checkpoint": comparacao(yn, cp["serie_ajuste_quantizada"]),
               "previsoes_vs_original": comparacao(pn[uso], po[uso]),
               "ordem_nova": cp["ordem"], "ordem_original": list(ast.literal_eval(previa.ordem)),
               "params_novos": cp["modelo"].params.tolist(),
               "loglik_original": tentativas[-1].get("loglik"),
               "loglik_novo": cp["modelo"].evidencia_fit["loglik"],
               "mse_validacao_original": float(previa.mse_validacao_normalizado),
               "tentativas_originais": tentativas,
               "mle_retvals_novo": {k:(v.tolist() if isinstance(v, np.ndarray) else v)
                                     for k,v in cp["modelo"].evidencia_fit["mle_retvals"].items()}}
        registros.append(reg)
        print(serie.localidade, "historico", reg["historico_fit"]["bit_a_bit"],
              "pred_delta", reg["previsoes_vs_original"]["delta_maximo"], flush=True)
    posn = run.e.pos_processar(novo, "validacao", pn)
    poso = run.e.pos_processar(novo, "validacao", po)
    mae = lambda arr: float(np.mean([np.mean(np.abs(arr[jn.localidade_id == i]-jn.y_bruto[jn.localidade_id == i]))
                                   for i in np.unique(jn.localidade_id)]))
    resultado = {"sem_novos_ajustes": True, "dados": dados, "localidades": registros,
                 "comparacao_global": comparacao(pn, po),
                 "mae_macro_original": mae(poso), "mae_macro_novo": mae(posn),
                 "pacotes_atual": run.motor.ler_json(pasta / "contrato_execucao.json")["pacotes"],
                 "concluido_em_utc": run.motor.agora(),
                 "fontes": run.motor.hashes([Path(__file__), pasta / "contrato_execucao.json",
                     pasta / "sem_quantizacao/selecao/seed-1.npz", fonte / "cache/deterministica.npz",
                     fonte / "selecao_arima.csv", fonte / "contrato.json"])}
    run.m.salvar_json_atomico(resultado, destino / "diagnostico.json")
    print({"dados": dados, "mae_original": mae(poso), "mae_novo": mae(posn),
           "saida": str(destino / "diagnostico.json")}, flush=True)


if __name__ == "__main__":
    main()
