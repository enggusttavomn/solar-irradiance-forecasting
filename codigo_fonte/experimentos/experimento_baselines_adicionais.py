"""Extensao isolada dos resultados canonicos, sem regravar previsoes antigas.

Executar: python -m codigo_fonte.experimentos.experimento_baselines_adicionais
  --tarefa monthly_1 --modelo GRU --modo completa
Cada par tarefa/modelo tem contrato, status, checkpoints e caches atomicos.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch

from codigo_fonte.experimentos import experimento_multirresolucao as m
from codigo_fonte.modelos import modelos_baselines_adicionais as redes

RAIZ = Path(__file__).resolve().parents[2]
FONTE = RAIZ / "resultados/avaliacao_multirresolucao_corrigida_v2"
SAIDA = RAIZ / "resultados/avaliacao_baselines_revisao_20260912"
MODELOS = ("GRU", "Transformer", "Informer", "ARIMA")
TAREFAS = {**m.TAREFAS_CANONICAS, "hourly_72_extension": m.TAREFA_HORARIA_EXTENSAO}
ORDENS_ARIMA = ((1, 0, 0), (2, 0, 0), (2, 0, 2), (1, 1, 0), (0, 1, 1), (1, 1, 1), (2, 1, 2))


@dataclass
class Contexto:
    tarefa: Any
    config: Any
    series: Any
    janelas: dict
    escalas: dict
    elevacoes: dict
    entradas: list[Path]


def preparar_contexto(slug: str, modo: str) -> Contexto:
    t = TAREFAS[slug]
    c = m.ConfiguracaoMultirresolucao(modo_execucao=modo)
    limite = c.limite_origens_smoke if modo == "smoke" else None
    if t.resolucao == "horaria":
        from codigo_fonte.coleta_e_preparacao.dados_horarios_nsrdb import PASTA_HORARIA_PADRAO, carregar_dados_horarios
        from codigo_fonte.experimentos import experimento_horario_timesnet as h

        ch = h.ConfiguracaoExperimentoHorario(modo_execucao=modo, semente=42)
        series = h.preparar_series_localidades(carregar_dados_horarios(PASTA_HORARIA_PADRAO), ch)
        if modo == "smoke":
            series = series[:c.limite_localidades_smoke]
        anos = {"ajuste": (2019, 2020, 2021, 2022), "validacao_2023": (2023,),
                "refit": (2019, 2020, 2021, 2022, 2023), "teste_2024": (2024,)}
        janelas = {p: h.construir_janelas_diarias(series, anos_origem=a, seq_len=t.seq_len,
                    pred_len=t.pred_len, particao=p, limite_origens_por_localidade=limite)
                   for p, a in anos.items()}
        escalas = {p: h.ajustar_escalas_pre_corte(series, primeiro_ano=2019,
                    fim_local_exclusivo=corte, nome_ajuste=p)
                   for p, corte in (("selecao", "2023-01-01"), ("refit", "2024-01-01"))}
        elevacoes = {p: h.calcular_elevacao_solar(janelas[p], series, minutos_centro_intervalo=30)
                    for p in ("validacao_2023", "teste_2024")}
        entradas = [Path(PASTA_HORARIA_PADRAO) / f"nsrdb_ghi_horaria_{ano}.csv.gz" for ano in range(2019, 2025)]
    else:
        diarias, _ = m.carregar_series_diarias()
        series = diarias if t.resolucao == "diaria" else m.agregar_series_mensais(diarias)
        if modo == "smoke":
            series = series[:c.limite_localidades_smoke]
        intervalos = {"ajuste": t.ajuste, "validacao_2023": t.validacao, "refit": t.refit, "teste_2024": t.teste}
        janelas = {p: m.construir_janelas(series, seq_len=t.seq_len, pred_len=t.pred_len,
                    intervalo=i, particao=p, limite_origens_por_localidade=limite)
                   for p, i in intervalos.items()}
        escalas = {p: m.ajustar_escalas_pre_corte(series, fim_exclusivo=corte, nome_ajuste=p)
                   for p, corte in (("selecao", "2023-01-01"), ("refit", "2024-01-01"))}
        elevacoes = {}
        entradas = sorted({Path(s.caminho_fonte) for s in diarias}, key=str)
    return Contexto(t, c, series, janelas, escalas, elevacoes, entradas)


def pos_processar(ctx: Contexto, particao: str, bruto: np.ndarray) -> np.ndarray:
    bruto = np.asarray(bruto, dtype=float)
    if bruto.shape != ctx.janelas[particao].y_bruto.shape or not np.isfinite(bruto).all():
        raise ValueError("Previsao adicional invalida ou nao finita.")
    if ctx.tarefa.resolucao == "horaria":
        from codigo_fonte.experimentos.experimento_horario_timesnet import aplicar_pos_processamento_fisico
        return aplicar_pos_processamento_fisico(bruto, ctx.elevacoes[particao])
    return np.maximum(bruto, 0.0)


def tabela_chaves(ctx: Contexto, particao: str) -> pd.DataFrame:
    j = ctx.janelas[particao]
    if ctx.tarefa.resolucao == "horaria":
        from codigo_fonte.experimentos.experimento_horario_timesnet import timestamps_alvo
        utc, _ = timestamps_alvo(j)
        return pd.DataFrame({"localidade": np.repeat(j.localidade, j.pred_len),
            "origem_utc": np.repeat(j.origem_utc, j.pred_len), "timestamp_alvo_utc": utc,
            "passo_h": np.tile(np.arange(1, j.pred_len + 1), len(j.x_bruto)),
            "ghi_real_wm2": j.y_bruto.reshape(-1).astype(float)})
    return pd.DataFrame({"tarefa": ctx.tarefa.slug, "particao": particao,
        "localidade": np.repeat(j.localidade, j.pred_len),
        "localidade_id": np.repeat(j.localidade_id, j.pred_len),
        "origem": np.repeat(j.origem.to_numpy(), j.pred_len),
        "data_alvo": j.datas_alvo.reshape(-1),
        "passo": np.tile(np.arange(1, j.pred_len + 1), len(j.x_bruto)),
        "ghi_real_wm2": j.y_bruto.reshape(-1).astype(float)})


def verificar_alinhamento(ctx: Contexto) -> None:
    """Antes de treinar, exige mesmas chaves e alvos das previsoes oficiais."""
    for p, arquivo in (("validacao_2023", "previsoes_validacao.csv.gz"), ("teste_2024", "previsoes_teste.csv.gz")):
        novo = tabela_chaves(ctx, p)
        antigo = pd.read_csv(FONTE / ctx.tarefa.slug / arquivo)
        if ctx.tarefa.resolucao == "horaria":
            datas, chaves = ("origem_utc", "timestamp_alvo_utc"), ["localidade", "origem_utc", "timestamp_alvo_utc", "passo_h"]
        else:
            datas, chaves = ("origem", "data_alvo"), ["localidade", "origem", "data_alvo", "passo"]
        for col in datas:
            novo[col] = pd.to_datetime(novo[col], utc=True)
            antigo[col] = pd.to_datetime(antigo[col], utc=True)
        if novo.duplicated(chaves).any() or antigo.duplicated(chaves).any():
            raise ValueError("Chaves duplicadas.")
        junto = novo.merge(antigo[chaves + ["ghi_real_wm2"]], on=chaves, how="left", validate="one_to_one", suffixes=("_novo", "_antigo"))
        if ctx.config.modo_execucao == "completa" and len(novo) != len(antigo):
            raise ValueError("Quantidade de previsoes diverge da fonte canonica.")
        if not np.allclose(junto.ghi_real_wm2_novo, junto.ghi_real_wm2_antigo, rtol=0, atol=1e-6):
            raise ValueError("Alvos diferem da fonte canonica ou ha linhas ausentes.")


def parametros(ctx: Contexto, modelo: str) -> dict:
    mensal = ctx.tarefa.resolucao == "mensal"
    return {"modelo": modelo, "modo": ctx.config.modo_execucao,
        "batch_size": 32 if mensal else 128, "lr": ctx.config.taxa_aprendizado, "weight_decay": ctx.config.peso_decay,
        "max_epocas": 1 if ctx.config.modo_execucao == "smoke" else (300 if mensal else 30),
        "paciencia": 30 if mensal else 5, "loss_selecao_neural": "MSE_normalizado_2023",
        "refit": "reinitialization_same_seed_fixed_selected_epochs",
        "sementes": [42] if ctx.tarefa.resolucao == "horaria" else list(ctx.config.sementes_efetivas),
        "gru_hidden": 32, "gru_layers": 1, "embedding_localidade": 8,
        "d_model": 16, "d_ff": 32, "heads": 2, "encoder_layers": 2, "decoder_layers": 1,
        "label_len": max(1, ctx.tarefa.seq_len // 2), "dropout": 0.1, "activation": "relu",
        "posicao": "sinusoidal_relativa_sem_calendario", "informer_factor": 5,
        "informer_eval_sampling_seed": 0, "informer_distill": True, "informer_mix": False,
        "decoder_future": "zeros_no_teacher_forcing",
        "arima_orders": [list(o) for o in ORDENS_ARIMA], "arima_maxiter": 200,
        "arima_selection": "per_site_validation_MSE_normalized_before_postprocessing",
        "arima_context": "apply_fixed_parameters_to_same_bounded_input_window",
        "arima_parameter_period": "union_of_training_target_dates_before_partition_cut",
        "arima_refit": "selected_order_fit_training_and_validation_targets_only",
        "threads_torch": 1, "publication_warning": "compact_configurations_not_SOTA_reproduction"}


def contrato(ctx: Contexto, modelo: str) -> dict:
    extras = [FONTE / ctx.tarefa.slug / f for f in ("contrato_execucao.json", "previsoes_validacao.csv.gz", "previsoes_teste.csv.gz")]
    # Algumas versoes canonicas usam contrato_experimento.json.
    extras = [p if p.exists() else p.with_name("contrato_experimento.json") for p in extras]
    codigos = [Path(__file__), Path(redes.__file__), Path(m.__file__),
        RAIZ / "codigo_fonte/experimentos/experimento_horario_timesnet.py", RAIZ / "codigo_fonte/coleta_e_preparacao/dados_horarios_nsrdb.py"]
    hashes = lambda ps: [{"arquivo": str(p.resolve()), "sha256": m.sha256_arquivo(p)} for p in ps]
    r = {"schema": 1, "tarefa": asdict(ctx.tarefa), "parametros": parametros(ctx, modelo),
        "configuracao_canonica": asdict(ctx.config), "arquivos_entrada": hashes(ctx.entradas + extras),
        "arquivos_codigo": hashes(codigos), "python": platform.python_version(),
        "pacotes": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "torch", "statsmodels", "scipy")}}
    r["sha256_contrato"] = hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()
    return json.loads(json.dumps(r))


def preparar_destino(ctx: Contexto, modelo: str, saida: Path) -> Path:
    destino = saida.resolve() / ctx.tarefa.slug / modelo.lower()
    if FONTE == destino or FONTE in destino.parents:
        raise ValueError("Proibido escrever na fonte canonica.")
    c = contrato(ctx, modelo)
    arquivo = destino / "contrato.json"
    if arquivo.exists():
        anterior = json.loads(arquivo.read_text(encoding="utf-8"))
        if anterior != c:
            raise RuntimeError(f"Contrato alterado: {arquivo}. Use outro diretorio, nao reutilize caches incompatíveis.")
    elif destino.exists() and any(destino.iterdir()):
        raise RuntimeError("Destino nao vazio sem contrato.")
    else:
        m.salvar_json_atomico(c, arquivo)
    return destino


def treinar_seed(ctx: Contexto, modelo: str, seed: int, destino: Path) -> dict:
    cache = destino / "cache" / f"seed{seed}.npz"
    if cache.exists():
        with np.load(cache, allow_pickle=False) as z:
            for p in ("validacao_2023", "teste_2024"):
                pos_processar(ctx, p, z[f"{p}_bruta"])
        print(f"[{ctx.tarefa.slug}/{modelo}/{seed}] cache verificado", flush=True)
        return {"semente": seed, "cache": str(cache), "retomado": True}
    inicio = time.perf_counter()
    j, s, par = ctx.janelas, ctx.escalas, parametros(ctx, modelo)
    x, y = j["ajuste"].normalizar(s["selecao"])
    xv, yv = j["validacao_2023"].normalizar(s["selecao"])
    xr, yr = j["refit"].normalizar(s["refit"])
    xt, _ = j["teste_2024"].normalizar(s["refit"])

    def nova_rede():
        m.fixar_semente(seed, 1)
        return redes.criar_baseline(modelo, ctx.tarefa.seq_len, ctx.tarefa.pred_len, len(ctx.series))

    comum = {"batch_size": par["batch_size"], "taxa_aprendizado": par["lr"],
        "peso_decay": par["weight_decay"], "semente": seed, "threads_torch": 1, "paciencia": par["paciencia"]}
    print(f"[{ctx.tarefa.slug}/{modelo}/{seed}] selecao ate {par['max_epocas']} epocas", flush=True)
    rede, epocas, hs = m.treinar_rede(nova_rede(), x_treino=x, y_treino=y, ids_treino=j["ajuste"].localidade_id,
        x_validacao=xv, y_validacao=yv, ids_validacao=j["validacao_2023"].localidade_id,
        max_epocas=par["max_epocas"], **comum)
    nparam = sum(p.numel() for p in rede.parameters())
    bv = j["validacao_2023"].inverter(m.prever_rede(rede, xv, j["validacao_2023"].localidade_id,
        batch_size=par["batch_size"]), s["selecao"])
    m.salvar_torch_atomico({"state_dict": rede.state_dict(), "seed": seed, "epocas": epocas,
        "parametros": par}, destino / "modelos" / f"seed{seed}_selecao.pt")
    del rede
    gc.collect()
    print(f"[{ctx.tarefa.slug}/{modelo}/{seed}] refit {epocas} epocas", flush=True)
    rede, _, hr = m.treinar_rede(nova_rede(), x_treino=xr, y_treino=yr, ids_treino=j["refit"].localidade_id,
        max_epocas=epocas, epocas_fixas=epocas, **comum)
    bt = j["teste_2024"].inverter(m.prever_rede(rede, xt, j["teste_2024"].localidade_id,
        batch_size=par["batch_size"]), s["refit"])
    m.salvar_torch_atomico({"state_dict": rede.state_dict(), "seed": seed, "epocas": epocas,
        "parametros": par}, destino / "modelos" / f"seed{seed}_refit.pt")
    pv, pt = pos_processar(ctx, "validacao_2023", bv), pos_processar(ctx, "teste_2024", bt)
    hist = [{"fase": "selecao", **r} for r in hs] + [{"fase": "refit", **r} for r in hr]
    m.salvar_csv_atomico(pd.DataFrame(hist), destino / "historicos" / f"seed{seed}.csv")
    meta = {"seed": seed, "epocas": epocas, "n_parametros": nparam, "segundos": time.perf_counter() - inicio}
    m.salvar_npz_atomico(cache, validacao_2023_bruta=bv, validacao_2023_pos=pv,
        teste_2024_bruta=bt, teste_2024_pos=pt, metadados_json=np.asarray(json.dumps(meta)))
    print(f"[{ctx.tarefa.slug}/{modelo}/{seed}] concluido em {meta['segundos']:.1f}s", flush=True)
    return meta


def serie_ajuste_arima(ctx: Contexto, serie: Any, fase: str) -> np.ndarray:
    """Datas alvo unicas, nao janelas sobrepostas repetidas; sem alvo futuro."""
    j = ctx.janelas["ajuste" if fase == "selecao" else "refit"]
    datas = serie.timestamp_local.tz_localize(None) if ctx.tarefa.resolucao == "horaria" else serie.datas
    if ctx.tarefa.resolucao == "horaria":
        datas_j = j.origem_local.tz_localize(None)
        delta = pd.Timedelta(hours=ctx.tarefa.pred_len - 1)
        inicio, fim = datas_j.min(), datas_j.max() + delta
    else:
        inicio, fim = pd.Timestamp(j.datas_alvo.min()), pd.Timestamp(j.datas_alvo.max())
    valores = np.asarray(serie.ghi[(datas >= inicio) & (datas <= fim)], dtype=float)
    escala = ctx.escalas[fase].set_index("localidade_id").loc[serie.localidade_id]
    return (valores - escala.minimo_treino_wm2) / escala.amplitude_escala_wm2


def previsoes_arima_fixos(ajustado: Any, contextos: np.ndarray, horizonte: int) -> np.ndarray:
    # apply nao retreina: filtra SOMENTE a mesma janela passada aos modelos.
    previstos = [np.asarray(ajustado.apply(np.asarray(x, dtype=float), refit=False).forecast(horizonte)) for x in contextos]
    resultado = np.asarray(previstos, dtype=float)
    if not np.isfinite(resultado).all():
        raise ValueError("ARIMA produziu previsao nao finita.")
    return resultado


def treinar_arima(ctx: Contexto, destino: Path) -> dict:
    from statsmodels.tsa.arima.model import ARIMA
    cache = destino / "cache" / "deterministica.npz"
    if cache.exists():
        with np.load(cache, allow_pickle=False) as z:
            for p in ("validacao_2023", "teste_2024"):
                pos_processar(ctx, p, z[f"{p}_bruta"])
        return {"retomado": True}
    inicio = time.perf_counter()
    v, t = ctx.janelas["validacao_2023"], ctx.janelas["teste_2024"]
    xv, yv = v.normalizar(ctx.escalas["selecao"])
    xt, _ = t.normalizar(ctx.escalas["refit"])
    pv, pt = np.empty_like(yv, dtype=float), np.empty_like(t.y_bruto, dtype=float)
    registros = []
    for serie in ctx.series:
        i = serie.localidade_id
        checkpoint = destino / "cache_localidades" / f"localidade{i}.npz"
        mv, mt = v.localidade_id == i, t.localidade_id == i
        if checkpoint.exists():
            with np.load(checkpoint, allow_pickle=False) as z:
                pv[mv], pt[mt] = z["val"], z["teste"]
                registros.extend(json.loads(str(z["registros"].item())))
            continue
        treino = serie_ajuste_arima(ctx, serie, "selecao")
        refit = serie_ajuste_arima(ctx, serie, "refit")
        melhor, detalhes = None, []
        for ordem in ORDENS_ARIMA:
            registro = {"localidade": serie.localidade, "ordem": str(ordem)}
            try:
                with warnings.catch_warnings(record=True) as avisos:
                    warnings.simplefilter("always")
                    modelo = ARIMA(treino, order=ordem).fit(method_kwargs={"maxiter": 200})
                    convergiu = bool(modelo.mle_retvals.get("converged", False))
                    if not convergiu:
                        raise RuntimeError("Ajuste nao convergiu no limite declarado.")
                    previsto = previsoes_arima_fixos(modelo, xv[mv], ctx.tarefa.pred_len)
                mse = float(np.mean((previsto - yv[mv]) ** 2))
                registro.update(mse_validacao_normalizado=mse, convergiu=True,
                    avisos=" | ".join(sorted({str(w.message) for w in avisos})))
                if melhor is None or mse < melhor[0]:
                    melhor = (mse, ordem, previsto)
            except (ValueError, RuntimeError, np.linalg.LinAlgError) as erro:
                registro.update(convergiu=False, erro=str(erro))
            detalhes.append(registro)
            print(f"[{ctx.tarefa.slug}/ARIMA/{i}] ordem {ordem}: {registro.get('mse_validacao_normalizado', registro.get('erro'))}", flush=True)
        if melhor is None:
            m.salvar_csv_atomico(pd.DataFrame(registros + detalhes), destino / "selecao_arima.csv")
            raise RuntimeError(f"Nenhuma ordem ARIMA valida em {serie.localidade}; sem substituicao silenciosa.")
        _, ordem, pval = melhor
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter("always")
            final = ARIMA(refit, order=ordem).fit(method_kwargs={"maxiter": 200})
            if not final.mle_retvals.get("converged", False):
                raise RuntimeError(f"Refit ARIMA nao convergiu: {serie.localidade}/{ordem}")
            pteste = previsoes_arima_fixos(final, xt[mt], ctx.tarefa.pred_len)
        pv[mv], pt[mt] = pval, pteste
        for d in detalhes:
            d["selecionada"] = d["ordem"] == str(ordem)
        detalhes.append({"localidade": serie.localidade, "fase": "refit", "ordem": str(ordem),
            "parametros": json.dumps(final.params.tolist()), "n_treino": len(treino), "n_refit": len(refit),
            "avisos": " | ".join(sorted({str(w.message) for w in avisos}))})
        m.salvar_joblib_atomico(final, destino / "modelos" / f"localidade{i}_refit.joblib")
        m.salvar_npz_atomico(checkpoint, val=pval, teste=pteste, registros=np.asarray(json.dumps(detalhes)))
        registros.extend(detalhes)
        m.salvar_csv_atomico(pd.DataFrame(registros), destino / "selecao_arima.csv")
    bv, bt = v.inverter(pv, ctx.escalas["selecao"]), t.inverter(pt, ctx.escalas["refit"])
    meta = {"segundos": time.perf_counter() - inicio, "n_localidades": len(ctx.series), "criterio": "MSE_validacao_2023"}
    m.salvar_npz_atomico(cache, validacao_2023_bruta=bv, validacao_2023_pos=pos_processar(ctx, "validacao_2023", bv),
        teste_2024_bruta=bt, teste_2024_pos=pos_processar(ctx, "teste_2024", bt), metadados_json=np.asarray(json.dumps(meta)))
    return meta


def executar(ctx: Contexto, modelo: str, saida: Path) -> None:
    verificar_alinhamento(ctx)
    destino = preparar_destino(ctx, modelo, saida)
    status = {"tarefa": ctx.tarefa.slug, "modelo": modelo, "modo": ctx.config.modo_execucao,
        "pid": os.getpid(), "resultado_publicavel": False, "etapa": "em_execucao"}
    m.salvar_json_atomico(status, destino / "status.json")
    try:
        for p in ("validacao_2023", "teste_2024"):
            m.salvar_csv_atomico(tabela_chaves(ctx, p), destino / f"chaves_{p}.csv.gz")
        m.salvar_csv_atomico(pd.concat(ctx.escalas.values(), ignore_index=True), destino / "escalas.csv")
        if modelo == "ARIMA":
            status["execucoes"] = [treinar_arima(ctx, destino)]
        else:
            status["execucoes"] = []
            for seed in parametros(ctx, modelo)["sementes"]:
                status["execucoes"].append(treinar_seed(ctx, modelo, seed, destino))
                m.salvar_json_atomico(status, destino / "status.json")
        status.update(etapa="concluida", resultado_publicavel=ctx.config.modo_execucao == "completa",
            atualizado_em_utc=datetime.now(timezone.utc).isoformat())
        m.salvar_json_atomico(status, destino / "status.json")
        m.salvar_json_atomico(m.gerar_manifesto_artefatos(destino), destino / "manifesto_artefatos.json")
    except Exception as erro:
        status.update(etapa="falhou", erro=f"{type(erro).__name__}: {erro}")
        m.salvar_json_atomico(status, destino / "status.json")
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=[*TAREFAS, "todas"], default="todas")
    ap.add_argument("--modelo", choices=[*MODELOS, "todos"], default="todos")
    ap.add_argument("--modo", choices=["smoke", "completa"], default="smoke")
    ap.add_argument("--saida", type=Path)
    args = ap.parse_args()
    saida = args.saida or (SAIDA if args.modo == "completa" else RAIZ / "tmp/revisao_literatura_20260912/smoke_baselines")
    for tarefa in (["monthly_1", "monthly_6", "daily_30", "hourly_72_extension"] if args.tarefa == "todas" else [args.tarefa]):
        ctx = preparar_contexto(tarefa, args.modo)
        for modelo in (MODELOS if args.modelo == "todos" else [args.modelo]):
            executar(ctx, modelo, saida)


if __name__ == "__main__":
    main()
