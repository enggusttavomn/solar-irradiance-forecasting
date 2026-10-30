"""Repete ajuste isolado para auditar variacao numerica, sem mudar resultados."""
from pathlib import Path
import time

import joblib
import numpy as np

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as run
from codigo_fonte.modelos.referencias_simples.arima_checkpoint_compacto import compactar_resultado
from codigo_fonte.analises_e_relatorios.diagnosticar_controle_arima_horario import comparacao


def main():
    tarefa, ident = "hourly_72_extension", 2
    pasta = run.SAIDA / "atual" / tarefa / "arima"
    fonte = run.e.SAIDA / tarefa / "arima_robusto"
    destino = run.RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/diagnostico_arima_horario"
    anterior = run.motor.ler_json(destino / "diagnostico.json")
    for comparado in ("x_bruto", "y_bruto", "x_normalizado", "escalas", "ids"):
        assert anterior["dados"][comparado]["bit_a_bit"]
    for s in anterior["localidades"]:
        assert s["historico_fit"]["bit_a_bit"]
    cp = joblib.load(pasta / "sem_quantizacao/modelos/localidade2_selecao.joblib")
    ctx = run.motor.preparar_contexto(tarefa, "selecao")
    j = ctx.janelas["validacao"]
    uso = j.localidade_id == ident
    x = run.q.normalizar_entradas(j, ctx.escalas["selecao"], None)[uso]
    with np.load(fonte / "cache/deterministica.npz", allow_pickle=False) as z:
        original = z["validacao_2023_bruta"][uso].copy()
    with np.load(pasta / "sem_quantizacao/selecao/seed-1.npz", allow_pickle=False) as z:
        atual = z["previsao"][uso].copy()
    replay = run.q.prever_checkpoint_arima(cp, j)
    comparar_replay = comparacao(replay, atual)
    assert comparar_replay["bit_a_bit"]
    escala = ctx.escalas["selecao"].set_index("localidade_id").loc[ident]
    registros = []
    for repeticao in (1, 2):
        print(f"Repeticao isolada Ford {repeticao}: ajuste original, ordem fixa {cp['ordem']}", flush=True)
        inicio = time.perf_counter()
        fit, tentativas = run.q.arima.ajustar(cp["serie_ajuste_quantizada"], tuple(cp["ordem"]))
        pred = run.e.previsoes_arima_fixos(fit, x, ctx.tarefa.pred_len)
        bruto = pred.astype(float) * float(escala.amplitude_escala_wm2) + float(escala.minimo_treino_wm2)
        pequeno = compactar_resultado(fit)
        arquivo = destino / f"ford_repeticao{repeticao}.joblib"
        run.m.salvar_joblib_atomico({**cp, "modelo": pequeno}, arquivo)
        reg = {"repeticao": repeticao, "duracao_s": time.perf_counter()-inicio,
               "params": fit.params.tolist(), "tentativas": tentativas,
               "vs_params_checkpoint": comparacao(fit.params, cp["modelo"].params),
               "vs_previsoes_checkpoint": comparacao(bruto, atual),
               "vs_previsoes_historicas": comparacao(bruto, original),
               "loglik": float(fit.llf), "checkpoint": str(arquivo),
               "sha256_checkpoint": run.m.sha256_arquivo(arquivo)}
        registros.append(reg)
        print(reg, flush=True)
        run.m.salvar_json_atomico({"ok": False, "registros": registros,
                                  "replay_checkpoint": comparar_replay}, destino / "repeticoes.json")
    resultado = {"ok": True, "registros": registros, "replay_checkpoint": comparar_replay,
                 "selecao_ou_resultados_nao_alterados": True,
                 "mesma_politica_numerica": run.q.protocolo_referencias()["arima_numerico"],
                 "fontes": run.motor.hashes([Path(__file__), Path(run.q.arima.__file__),
                     destino / "diagnostico.json", pasta / "sem_quantizacao/modelos/localidade2_selecao.joblib"])}
    run.m.salvar_json_atomico(resultado, destino / "repeticoes.json")


if __name__ == "__main__":
    main()
