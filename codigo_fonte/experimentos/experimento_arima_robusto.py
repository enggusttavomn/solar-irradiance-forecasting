"""Reexecucao ARIMA com contingencia numerica, sem alterar o runner congelado.

A tentativa inicial foi preservada: L-BFGS nao convergiu no refit mensal
de BMW San Luis Potosi. Politica uniforme desta revisao: tentar L-BFGS/200;
somente se nao convergir, Powell/2000, na MESMA ordem e MESMOS dados.
Nao se escolhe otimizador pela validacao ou pelo teste. Ordem continua
selecionada exclusivamente pelo MSE de 2023. Resultados: arima_robusto/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from codigo_fonte.experimentos import experimento_baselines_adicionais as e

OTIMIZADORES = (("lbfgs", 200), ("powell", 2000))


def ajustar(y, ordem):
    tentativas = []
    for metodo, limite in OTIMIZADORES:
        registro = {"otimizador": metodo, "limite": limite}
        try:
            with warnings.catch_warnings(record=True) as avisos:
                warnings.simplefilter("always")
                fit = ARIMA(y, order=ordem).fit(method_kwargs={"method": metodo, "maxiter": limite})
            convergiu = bool(fit.mle_retvals.get("converged", False)) and np.isfinite(fit.params).all()
            registro.update(convergiu=bool(convergiu), loglik=float(fit.llf),
                avisos=" | ".join(sorted({str(w.message) for w in avisos})))
            tentativas.append(registro)
            if convergiu:
                return fit, tentativas
        except (ValueError, RuntimeError, np.linalg.LinAlgError) as erro:
            registro.update(convergiu=False, erro=str(erro))
            tentativas.append(registro)
    raise RuntimeError(f"Ajuste ARIMA sem convergencia: {ordem}; {tentativas}")


def criar_contrato(ctx):
    contrato = e.contrato(ctx, "ARIMA")
    contrato["parametros"].update(arima_numerical_retry_policy=[list(x) for x in OTIMIZADORES],
        arima_optimizer_selection="first_converged_fit_no_validation_or_test_metric",
        arima_version="numerical_retry_v2_all_sites_and_tasks")
    contrato["arquivos_codigo"].append({"arquivo": str(Path(__file__).resolve()), "sha256": e.m.sha256_arquivo(__file__)})
    contrato.pop("sha256_contrato", None)
    contrato["sha256_contrato"] = hashlib.sha256(json.dumps(contrato, sort_keys=True).encode()).hexdigest()
    return contrato


def executar(ctx, saida):
    e.verificar_alinhamento(ctx)
    pasta = Path(saida).resolve() / ctx.tarefa.slug / "arima_robusto"
    if e.FONTE == pasta or e.FONTE in pasta.parents:
        raise ValueError("Proibido escrever na fonte canonica.")
    contrato = criar_contrato(ctx)
    if (pasta / "contrato.json").exists():
        if json.loads((pasta / "contrato.json").read_text(encoding="utf-8")) != contrato:
            raise RuntimeError("Contrato ARIMA divergente; nao reutilizar caches.")
    elif pasta.exists() and any(pasta.iterdir()):
        raise RuntimeError("Destino nao vazio sem contrato.")
    else:
        e.m.salvar_json_atomico(contrato, pasta / "contrato.json")
    status = {"etapa": "em_execucao", "modelo": "ARIMA", "tarefa": ctx.tarefa.slug,
        "modo": ctx.config.modo_execucao, "resultado_publicavel": False}
    e.m.salvar_json_atomico(status, pasta / "status.json")
    try:
        for p in ("validacao_2023", "teste_2024"):
            e.m.salvar_csv_atomico(e.tabela_chaves(ctx, p), pasta / f"chaves_{p}.csv.gz")
        e.m.salvar_csv_atomico(pd.concat(ctx.escalas.values(), ignore_index=True), pasta / "escalas.csv")
        treinar(ctx, pasta)
        status.update(etapa="concluida", resultado_publicavel=ctx.config.modo_execucao == "completa",
            atualizado_em_utc=datetime.now(timezone.utc).isoformat())
        e.m.salvar_json_atomico(status, pasta / "status.json")
        e.m.salvar_json_atomico(e.m.gerar_manifesto_artefatos(pasta), pasta / "manifesto_artefatos.json")
    except Exception as erro:
        status.update(etapa="falhou", erro=f"{type(erro).__name__}: {erro}")
        e.m.salvar_json_atomico(status, pasta / "status.json")
        raise


def treinar(ctx, pasta):
    cache = pasta / "cache/deterministica.npz"
    if cache.exists():
        with np.load(cache, allow_pickle=False) as z:
            for p in ("validacao_2023", "teste_2024"):
                e.pos_processar(ctx, p, z[f"{p}_bruta"])
        return
    inicio = time.perf_counter()
    v, t = ctx.janelas["validacao_2023"], ctx.janelas["teste_2024"]
    xv, yv = v.normalizar(ctx.escalas["selecao"])
    xt, _ = t.normalizar(ctx.escalas["refit"])
    pv, pt = np.empty_like(yv, dtype=float), np.empty_like(t.y_bruto, dtype=float)
    registros = []
    for serie in ctx.series:
        i = serie.localidade_id
        mv, mt = v.localidade_id == i, t.localidade_id == i
        cp = pasta / "cache_localidades" / f"localidade{i}.npz"
        if cp.exists():
            with np.load(cp, allow_pickle=False) as z:
                pv[mv], pt[mt] = z["val"], z["teste"]
                registros.extend(json.loads(str(z["registros"].item())))
            continue
        treino, refit = e.serie_ajuste_arima(ctx, serie, "selecao"), e.serie_ajuste_arima(ctx, serie, "refit")
        melhor, detalhes = None, []
        for ordem in e.ORDENS_ARIMA:
            reg = {"localidade": serie.localidade, "ordem": str(ordem), "fase": "selecao"}
            try:
                modelo, tentativas = ajustar(treino, ordem)
                previsto = e.previsoes_arima_fixos(modelo, xv[mv], ctx.tarefa.pred_len)
                mse = float(np.mean((previsto - yv[mv]) ** 2))
                reg.update(convergiu=True, mse_validacao_normalizado=mse, tentativas=json.dumps(tentativas))
                if melhor is None or mse < melhor[0]:
                    melhor = (mse, ordem, previsto)
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as erro:
                reg.update(convergiu=False, erro=str(erro))
            detalhes.append(reg)
            print(f"[{ctx.tarefa.slug}/ARIMA-v2/{i}] {ordem}: {reg.get('mse_validacao_normalizado', reg.get('erro'))}", flush=True)
        if melhor is None:
            raise RuntimeError(f"Nenhuma ordem valida: {serie.localidade}")
        _, ordem, pval = melhor
        final, tentativas = ajustar(refit, ordem)
        pteste = e.previsoes_arima_fixos(final, xt[mt], ctx.tarefa.pred_len)
        pv[mv], pt[mt] = pval, pteste
        for d in detalhes:
            d["selecionada"] = d["ordem"] == str(ordem)
        detalhes.append({"localidade": serie.localidade, "fase": "refit", "ordem": str(ordem),
            "parametros": json.dumps(final.params.tolist()), "n_treino": len(treino), "n_refit": len(refit),
            "tentativas": json.dumps(tentativas)})
        e.m.salvar_joblib_atomico(final, pasta / "modelos" / f"localidade{i}_refit.joblib")
        e.m.salvar_npz_atomico(cp, val=pval, teste=pteste, registros=np.asarray(json.dumps(detalhes)))
        registros.extend(detalhes)
        e.m.salvar_csv_atomico(pd.DataFrame(registros), pasta / "selecao_arima.csv")
    bv, bt = v.inverter(pv, ctx.escalas["selecao"]), t.inverter(pt, ctx.escalas["refit"])
    meta = {"segundos": time.perf_counter() - inicio, "n_localidades": len(ctx.series), "otimizadores": OTIMIZADORES}
    e.m.salvar_npz_atomico(cache, validacao_2023_bruta=bv, validacao_2023_pos=e.pos_processar(ctx, "validacao_2023", bv),
        teste_2024_bruta=bt, teste_2024_pos=e.pos_processar(ctx, "teste_2024", bt), metadados_json=np.asarray(json.dumps(meta)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=[*e.TAREFAS, "todas"], default="todas")
    ap.add_argument("--modo", choices=["smoke", "completa"], default="smoke")
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    saida = args.saida or (e.SAIDA if args.modo == "completa" else e.RAIZ / "tmp/revisao_literatura_20260912/arima_v2_smoke")
    for slug in (["monthly_1", "monthly_6", "daily_30", "hourly_72_extension"] if args.tarefa == "todas" else [args.tarefa]):
        executar(e.preparar_contexto(slug, args.modo), saida)
