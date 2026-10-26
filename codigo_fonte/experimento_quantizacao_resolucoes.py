"""Quantizacao X-only da TimesNet horaria/diaria com selecao temporal congelada.

Preserva os hiperparametros, sementes, dispositivo e amostras da busca pura.
As duas selecoes terminam antes da construcao das novas janelas de teste.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, fields, replace
from datetime import datetime, timezone
import hashlib
import json
import multiprocessing as mp
import os
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd
import torch

from codigo_fonte import experimento_multirresolucao as base
from codigo_fonte import experimento_baselines_adicionais as dados
from codigo_fonte import experimento_horario_timesnet as horario
from codigo_fonte import otimizacao_timesnet_resolucoes as origem
from codigo_fonte import quantizacao_timesnet as quant
from codigo_fonte import treinamento_timesnet_quantizado_resolucoes as treino

RAIZ = Path(__file__).resolve().parents[1]
FONTE = RAIZ / "resultados/busca_timesnet_resolucoes_20260922"
SAIDA = RAIZ / "resultados/quantizacao_timesnet_resolucoes_20260927"
TAREFAS = ("hourly_72_extension", "daily_30")
VARIANTES = (("sem_quantizacao", None), ("q64", 64), ("q128", 128), ("q256", 256))


def ler_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def agora():
    return datetime.now(timezone.utc).isoformat()


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def conferir_hashes(fontes):
    for path, digest in fontes.items():
        if base.sha256_arquivo(path) != digest:
            raise ValueError(f"Fonte alterada: {path}")


def validar_selecao(pasta):
    """Confere contrato, fontes, variantes e escolha anterior ao teste."""
    pasta = Path(pasta)
    c = ler_json(pasta / "contrato_execucao.json")
    s = ler_json(pasta / "selecao_congelada.json")
    conteudo = {k: v for k, v in c.items() if k != "sha256_contrato"}
    if c.get("sha256_contrato") != hash_obj(conteudo):
        raise ValueError("Hash do contrato invalido.")
    for grupo in ("codigo", "entradas", "fontes_configuracao"):
        conferir_hashes(c[grupo])
    if (s.get("selecao_concluida_antes_do_teste") is not True
            or s.get("contrato_sha256") != c["sha256_contrato"]
            or s.get("tarefa") != c["tarefa"]["slug"]
            or s.get("modo") != c["modo"]):
        raise ValueError("Selecao incompativel/incompleta.")
    ranking = s.get("ranking", [])
    esperados = dict(VARIANTES)
    if len(ranking) != len(VARIANTES) or {r["nome"] for r in ranking} != set(esperados):
        raise ValueError("Quatro variantes unicas obrigatorias.")
    seeds = c["sementes"]
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("Sementes invalidas no contrato.")
    conf = c["configuracao"]
    maximo = conf["epocas_smoke"] if c["modo"] == "smoke" else conf["max_epocas_diario"]
    for r in ranking:
        if r.get("niveis") != esperados[r["nome"]]:
            raise ValueError("Niveis da variante inconsistentes.")
        epocas = r.get("epocas", {})
        if set(epocas) != {str(x) for x in seeds}:
            raise ValueError("Sementes incompletas.")
        if any(isinstance(e, bool) or not isinstance(e, int) or not 1 <= e <= maximo for e in epocas.values()):
            raise ValueError("Epocas selecionadas invalidas.")
        mae = r.get("MAE_validacao_wm2")
        if isinstance(mae, bool) or not isinstance(mae, (int, float)) or not np.isfinite(mae) or mae < 0:
            raise ValueError("MAE de validacao invalido.")
    ordem = {n: i for i, (n, _) in enumerate(VARIANTES)}
    ordenado = sorted(ranking, key=lambda r: (r["MAE_validacao_wm2"], ordem[r["nome"]]))
    if ranking != ordenado or s.get("vencedor") != ordenado[0]:
        raise ValueError("Ranking/vencedor diverge da validacao.")
    conferir_hashes(s["fontes_selecao_sha256"])
    return c, s


def parametros(slug, smoke=False):
    if slug not in TAREFAS:
        raise ValueError("Somente diario e horario.")
    contrato = ler_json(FONTE / slug / "contrato_execucao.json")
    selecao = ler_json(FONTE / slug / "selecao_congelada.json")
    conferir_hashes(contrato["codigo"])
    conferir_hashes(contrato["entradas"])
    vencedor = selecao["vencedor"]
    candidato = origem.Candidato(**{f.name: vencedor[f.name] for f in fields(origem.Candidato)})
    conf = base.ConfiguracaoMultirresolucao(**contrato["configuracao"])
    conf = replace(conf, taxa_aprendizado=candidato.taxa, timesnet_d_model=candidato.dimensao,
                   timesnet_d_ff=2 * candidato.dimensao, batch_size_diario=candidato.lote)
    if smoke:
        conf = replace(conf, modo_execucao="smoke", epocas_smoke=1)
    tarefa = replace(dados.TAREFAS[slug], seq_len=candidato.contexto)
    seeds = contrato["sementes"][:1] if smoke else contrato["sementes"]
    return tarefa, candidato, conf, seeds, contrato["dispositivo"]


def preparar_contexto(slug, fase, pasta_saida=SAIDA, smoke=False):
    """Nao constroi refit/teste antes de conferir o congelamento global."""
    if fase not in {"selecao", "refit"}:
        raise ValueError("Fase invalida.")
    if fase == "refit":
        validar_congelamento_global(pasta_saida)
    tarefa, candidato, conf, seeds, device = parametros(slug, smoke)
    limite = conf.limite_origens_smoke if smoke else None
    if tarefa.resolucao == "horaria":
        from codigo_fonte.dados_horarios_nsrdb import PASTA_HORARIA_PADRAO, carregar_dados_horarios
        hc = horario.ConfiguracaoExperimentoHorario(modo_execucao=conf.modo_execucao, semente=42)
        series = horario.preparar_series_localidades(carregar_dados_horarios(PASTA_HORARIA_PADRAO), hc)
        if smoke:
            series = series[:conf.limite_localidades_smoke]
        if fase == "selecao":
            series = tuple(replace(s, timestamp_utc=s.timestamp_utc[s.timestamp_local < "2024-01-01"],
                timestamp_local=s.timestamp_local[s.timestamp_local < "2024-01-01"],
                ghi=s.ghi[s.timestamp_local < "2024-01-01"]) for s in series)
        anos = ({"ajuste": (2019, 2020, 2021, 2022), "validacao_2023": (2023,)} if fase == "selecao"
                else {"refit": (2019, 2020, 2021, 2022, 2023), "teste_2024": (2024,)})
        janelas = {p: horario.construir_janelas_diarias(series, anos_origem=a, seq_len=tarefa.seq_len,
            pred_len=tarefa.pred_len, particao=p, limite_origens_por_localidade=limite) for p, a in anos.items()}
        corte = "2023-01-01" if fase == "selecao" else "2024-01-01"
        escalas = {fase: horario.ajustar_escalas_pre_corte(series, primeiro_ano=2019,
                    fim_local_exclusivo=corte, nome_ajuste=fase)}
        avaliacao = "validacao_2023" if fase == "selecao" else "teste_2024"
        elevacoes = {avaliacao: horario.calcular_elevacao_solar(janelas[avaliacao], series,
                                                              minutos_centro_intervalo=30)}
        entradas = [Path(PASTA_HORARIA_PADRAO) / f"nsrdb_ghi_horaria_{ano}.csv.gz" for ano in range(2019, 2025)]
    else:
        series, _ = base.carregar_series_diarias()
        entradas = sorted({Path(s.caminho_fonte) for s in series}, key=str)
        if smoke:
            series = series[:conf.limite_localidades_smoke]
        if fase == "selecao":
            series = tuple(replace(s, datas=s.datas[s.datas < "2024-01-01"],
                                   ghi=s.ghi[s.datas < "2024-01-01"]) for s in series)
        intervalos = ({"ajuste": tarefa.ajuste, "validacao_2023": tarefa.validacao} if fase == "selecao"
                      else {"refit": tarefa.refit, "teste_2024": tarefa.teste})
        janelas = {p: base.construir_janelas(series, seq_len=tarefa.seq_len, pred_len=tarefa.pred_len,
            intervalo=i, particao=p, limite_origens_por_localidade=limite) for p, i in intervalos.items()}
        corte = "2023-01-01" if fase == "selecao" else "2024-01-01"
        escalas = {fase: base.ajustar_escalas_pre_corte(series, fim_exclusivo=corte, nome_ajuste=fase)}
        elevacoes = {}
    ctx = dados.Contexto(tarefa, conf, series, janelas, escalas, elevacoes, entradas)
    conferir_alinhamento(ctx, "validacao_2023" if fase == "selecao" else "teste_2024")
    return ctx, candidato, seeds, device


def conferir_alinhamento(ctx, particao):
    nome = "validacao" if particao == "validacao_2023" else "teste"
    novo = dados.tabela_chaves(ctx, particao)
    antigo = pd.read_csv(FONTE / ctx.tarefa.slug / f"previsoes_{nome}.csv.gz")
    chaves, datas_col = chaves_previsoes(ctx.tarefa.resolucao)
    for col in datas_col:
        novo[col] = pd.to_datetime(novo[col], utc=True)
        antigo[col] = pd.to_datetime(antigo[col], utc=True)
    if novo.duplicated(chaves).any() or antigo.duplicated(chaves).any():
        raise ValueError("Chaves duplicadas.")
    junto = novo.merge(antigo[chaves + ["ghi_real_wm2"]], on=chaves, how="left", validate="one_to_one",
                       suffixes=("", "_anterior"), sort=False)
    if ctx.config.modo_execucao == "completa" and len(novo) != len(antigo):
        raise ValueError("Amostra diferente do controle original.")
    if not np.allclose(junto.ghi_real_wm2, junto.ghi_real_wm2_anterior, atol=1e-6, rtol=0):
        raise ValueError("Alvos/datas diferentes do controle original.")


def chaves_previsoes(resolucao):
    datas_col = ["origem_utc", "timestamp_alvo_utc"] if resolucao == "horaria" else ["origem", "data_alvo"]
    return ["localidade", *datas_col, "passo_h" if resolucao == "horaria" else "passo"], datas_col


def construir_contrato(ctx, candidato, seeds, device, workers):
    modules = [__file__, treino.__file__, quant.__file__, origem.__file__, base.__file__, dados.__file__,
               horario.__file__, Path(__file__).with_name("treinamento_timesnet_resolucoes.py"),
               Path(__file__).with_name("treinamento_timesnet_otimizacao.py"),
               Path(__file__).with_name("timesnet_horario.py"),
               Path(__file__).with_name("consolidar_baselines_adicionais.py")]
    fontes = [FONTE / ctx.tarefa.slug / n for n in
              ("contrato_execucao.json", "selecao_congelada.json", "manifesto_artefatos.json")]
    c = {"versao": 1, "experimento": "minmax_quantizacao_entrada_resolucoes_v1",
         "tarefa": asdict(ctx.tarefa), "configuracao": asdict(ctx.config),
         "candidato_base": asdict(candidato), "sementes": list(seeds), "dispositivo": device,
         "modo": ctx.config.modo_execucao, "workers": workers, "n_localidades": len(ctx.series),
         "minmax": True, "variantes": [{"nome": n, "niveis": k} for n, k in VARIANTES],
         "quantizacao": {"onde": "somente_entradas", "niveis": [64, 128, 256], "intervalo": [0, 1],
            "formula": "rint(clip(x_minmax,0,1)*(N-1))/(N-1)", "alvos_quantizados": False,
            "pesos_quantizados": False, "controle": "sem_quantizacao_e_sem_clip"},
         "criterio": "macro_MAE_fisico_ensemble_validacao_2023_horizonte_completo",
         "ordem_desempate": [n for n, _ in VARIANTES],
         "python": platform.python_version(), "torch": str(torch.__version__),
         "numpy": np.__version__, "pandas": pd.__version__,
         "codigo": {str(Path(p).resolve()): base.sha256_arquivo(p) for p in modules},
         "entradas": {str(p.resolve()): base.sha256_arquivo(p) for p in ctx.entradas},
         "fontes_configuracao": {str(p.resolve()): base.sha256_arquivo(p) for p in fontes},
         "limitacoes": ["Dados 2019-2024; historico nao ampliado.",
             "2024 previamente observado; avaliacao retrospectiva.",
             "Horaria conserva uma semente; diaria conserva cinco.",
             "Quantizacao combina arredondamento e saturacao; controle nao satura.",
             "Hiperparametros fixados da busca anterior; selecao nova apenas de epocas e niveis."]}
    c["sha256_contrato"] = hash_obj(c)
    return c


def diagnosticos(janelas, escalas, niveis):
    x = treino._normalizar_contexto(janelas, escalas, niveis=None)
    q = quant.quantizar_entradas(x, niveis)
    recortes = {"total": np.ones(len(x), dtype=bool),
                **{str(int(i)): janelas.localidade_id == i for i in np.unique(janelas.localidade_id)}}
    resultado = {}
    for nome, mascara in recortes.items():
        z, w = x[mascara], q[mascara]
        d = quant.diagnosticar_quantizacao(z, niveis)
        d["erro_medio_quantizacao_normalizado"] = float(np.abs(z.astype(float) - w).mean())
        d["erro_medio_somente_clip_normalizado"] = float(np.abs(z.astype(float) - np.clip(z, 0, 1)).mean()) if niveis else 0.
        d["contagem_refere_a"] = "posicoes_em_janelas_sobrepostas"
        resultado[nome] = d
    return resultado


def _seed_job(pasta_str, tarefa, candidato, config, seed, ajuste, avaliacao, escalas,
              elevacao, nome, niveis, contrato_hash, fase, device, epocas_fixas=None):
    pasta = Path(pasta_str)
    cache = pasta / fase / f"seed{seed}.npz"
    registro = cache.with_suffix(".json")
    cp_path = pasta / "modelos" / f"timesnet_seed{seed}_{fase}.pt"
    if cache.exists() and registro.exists():
        meta = ler_json(registro)
        if (meta["contrato_sha256"] != contrato_hash or meta["niveis"] != niveis
                or meta.get("semente") != seed or meta.get("fase") != fase
                or meta.get("variante") != nome or meta.get("epocas_fixas") != epocas_fixas):
            raise ValueError("Cache incompativel.")
        conferir_hashes(meta["arquivos_sha256"])
        with np.load(cache, allow_pickle=False) as z:
            epocas = int(z["epocas"].item())
            previsao = z["previsao"]
            if (epocas != meta["epocas"] or epocas < 1
                    or epocas_fixas is not None and epocas != epocas_fixas
                    or previsao.shape != (len(avaliacao.localidade_id), avaliacao.pred_len)
                    or not np.isfinite(previsao).all()):
                raise ValueError("Conteudo do cache incompativel.")
            return {"semente": seed, "previsao": previsao, "epocas": epocas}
    inicio = time.perf_counter()
    print(f"[{tarefa.slug}] {fase} {nome} seed={seed} inicio", flush=True)
    modelo, epocas, hist = treino.treinar(tarefa=tarefa, config=config, semente=seed,
        ajuste=ajuste, escalas=escalas, validacao=avaliacao if fase == "selecao" else None,
        elevacao_validacao=elevacao if fase == "selecao" else None,
        perda=candidato.perda, epocas_fixas=epocas_fixas, dispositivo=device, niveis=niveis)
    bruto = treino.prever(modelo, avaliacao, escalas, batch_size=config.batch_size_diario,
                         dispositivo=device, niveis=niveis)
    treino.macro_mae_fisico(avaliacao, bruto, elevacao)
    prep = {"versao": 1, "minmax": True, "niveis": niveis, "onde": "somente_entradas",
        "escalas": escalas.to_dict(orient="records"), "dispositivo": device,
        "batch_size": config.batch_size_diario,
        "escala_fim_exclusivo": "2023-01-01" if fase == "selecao" else "2024-01-01",
        "localidades": {str(int(i)): str(n) for i, n in zip(ajuste.localidade_id, ajuste.localidade)},
        "pos_processamento": "piso_zero_e_mascara_solar" if tarefa.resolucao == "horaria" else "piso_zero"}
    cp = {"state_dict": {k: v.cpu() for k, v in modelo.state_dict().items()},
          "tarefa": asdict(tarefa), "configuracao": asdict(config), "candidato": asdict(candidato),
          "semente": seed, "epocas": epocas, "fase": fase, "variante": nome,
          "contrato_sha256": contrato_hash, "preprocessamento": prep}
    if fase == "refit":
        cp["selecao_global_sha256"] = base.sha256_arquivo(pasta.parents[2] / "selecao_global_congelada.json")
        cp["selecao_tarefa_sha256"] = base.sha256_arquivo(pasta.parents[1] / "selecao_congelada.json")
    base.salvar_torch_atomico(cp, cp_path)
    base.salvar_csv_atomico(hist, cache.with_suffix(".csv"))
    base.salvar_npz_atomico(cache, previsao=bruto, epocas=np.asarray(epocas))
    base.salvar_json_atomico({"contrato_sha256": contrato_hash, "niveis": niveis, "semente": seed,
        "fase": fase, "variante": nome, "epocas_fixas": epocas_fixas,
        "epocas": epocas, "duracao_s": time.perf_counter() - inicio, "concluido_em_utc": agora(),
        "arquivos_sha256": {str(p.resolve()): base.sha256_arquivo(p) for p in
            (cache, cache.with_suffix(".csv"), cp_path)}}, registro)
    del modelo
    if device == "cuda":
        torch.cuda.empty_cache()
    print(f"[{tarefa.slug}] {fase} {nome} seed={seed} fim epocas={epocas}", flush=True)
    return {"semente": seed, "previsao": bruto, "epocas": epocas}


def salvar_avaliacao(ctx, variante, resultados, particao):
    brutas = [r["previsao"] for r in resultados]
    media = np.mean(brutas, axis=0)
    tabela, locais, macro = origem.avaliar_metricas(ctx, particao, media)
    tabela = tabela.rename(columns={"previsao_bruta_timesnet_otimizada_wm2": "previsao_bruta_timesnet_ensemble_wm2",
                                   "previsao_pos_timesnet_otimizada_wm2": "previsao_pos_timesnet_ensemble_wm2"})
    if particao in ctx.elevacoes:
        tabela["elevacao_solar_graus"] = ctx.elevacoes[particao].reshape(-1)
    for r in resultados:
        tabela[f"previsao_bruta_timesnet_seed{r['semente']}_wm2"] = r["previsao"].reshape(-1)
        tabela[f"previsao_pos_timesnet_seed{r['semente']}_wm2"] = dados.pos_processar(ctx, particao, r["previsao"]).reshape(-1)
    sufixo = "validacao" if particao == "validacao_2023" else "teste"
    base.salvar_csv_atomico(tabela, variante / f"previsoes_{sufixo}.csv.gz")
    base.salvar_csv_atomico(locais, variante / f"metricas_{sufixo}_por_localidade.csv")
    base.salvar_csv_atomico(macro, variante / f"metricas_{sufixo}_macro.csv")
    return treino.macro_mae_fisico(ctx.janelas[particao], media, ctx.elevacoes.get(particao))


def conferir_controle(ctx, variante, fase):
    if ctx.config.modo_execucao == "smoke":
        return
    sufixo = "validacao" if fase == "selecao" else "teste"
    novo = pd.read_csv(variante / f"previsoes_{sufixo}.csv.gz")
    antigo = pd.read_csv(FONTE / ctx.tarefa.slug / f"previsoes_{sufixo}.csv.gz")
    keys, _ = chaves_previsoes(ctx.tarefa.resolucao)
    novo, antigo = novo.sort_values(keys), antigo.sort_values(keys)
    if not novo[keys].reset_index(drop=True).equals(antigo[keys].reset_index(drop=True)):
        raise ValueError("Controle mudou ordem/chaves da amostra.")
    delta = float(np.max(np.abs(novo.previsao_bruta_timesnet_ensemble_wm2.to_numpy() -
                               antigo.previsao_bruta_timesnet_otimizada_wm2.to_numpy())))
    base.salvar_json_atomico({"fase": fase, "diferenca_maxima_wm2": delta, "tolerancia_wm2": 1e-6,
        "fonte": str((FONTE / ctx.tarefa.slug / f"previsoes_{sufixo}.csv.gz").resolve()),
        "aprovado": delta <= 1e-6}, variante / f"reproducao_controle_{fase}.json")
    if delta > 1e-6:
        raise ValueError(f"Controle nao reproduziu fonte; max delta {delta}. Investigar antes de prosseguir.")


def rodar_fase(ctx, candidato, seeds, device, pasta, contrato, fase, executor, selecao=None):
    ajuste_nome, avaliacao_nome = ("ajuste", "validacao_2023") if fase == "selecao" else ("refit", "teste_2024")
    escalas = ctx.escalas[fase]
    base.salvar_csv_atomico(escalas, pasta / f"escalas_{fase}.csv")
    anteriores = {r["nome"]: r for r in selecao["ranking"]} if selecao else {}
    linhas = []
    for nome, niveis in VARIANTES:
        variante = pasta / "variantes" / nome
        argumentos = [(str(variante), ctx.tarefa, candidato, ctx.config, seed, ctx.janelas[ajuste_nome],
            ctx.janelas[avaliacao_nome], escalas, ctx.elevacoes.get(avaliacao_nome), nome, niveis,
            contrato["sha256_contrato"], fase, device,
            int(anteriores[nome]["epocas"][str(seed)]) if selecao else None) for seed in seeds]
        if executor is None:
            resultados = [_seed_job(*args) for args in argumentos]
        else:
            futures = [executor.submit(_seed_job, *args) for args in argumentos]
            resultados = [f.result() for f in as_completed(futures)]
        resultados.sort(key=lambda r: seeds.index(r["semente"]))
        mae = salvar_avaliacao(ctx, variante, resultados, avaliacao_nome)
        if nome == "sem_quantizacao":
            conferir_controle(ctx, variante, fase)
        base.salvar_json_atomico({ajuste_nome: diagnosticos(ctx.janelas[ajuste_nome], escalas, niveis),
            "validacao" if fase == "selecao" else "teste": diagnosticos(ctx.janelas[avaliacao_nome], escalas, niveis)},
            variante / f"diagnostico_{fase}.json")
        row = {"nome": nome, "niveis": niveis, "epocas": {str(r["semente"]): int(r["epocas"]) for r in resultados}}
        if fase == "selecao":
            row["MAE_validacao_wm2"] = mae
        else:
            row.update(MAE_validacao_wm2=anteriores[nome]["MAE_validacao_wm2"], MAE_teste_wm2=mae,
                       selecionada=nome == selecao["vencedor"]["nome"])
            base.salvar_json_atomico({"etapa": "concluida", "modo": ctx.config.modo_execucao, **row},
                                    variante / "status_execucao.json")
        linhas.append(row)
        base.salvar_json_atomico({"etapa": fase, "variante_concluida": nome, "MAE": mae,
            "atualizado_em_utc": agora()}, pasta / "status_execucao.json")
    return linhas


def congelar_global(pasta_saida=SAIDA):
    pasta_saida = Path(pasta_saida)
    path = pasta_saida / "selecao_global_congelada.json"
    if path.exists():
        validar_congelamento_global(pasta_saida)
        return ler_json(path)
    fontes = {}
    for t in TAREFAS:
        pasta = pasta_saida / t
        c, s = validar_selecao(pasta)
        if not s["selecao_concluida_antes_do_teste"] or s["contrato_sha256"] != c["sha256_contrato"]:
            raise ValueError("Selecao incompativel/incompleta.")
        if {r["nome"] for r in s["ranking"]} != {n for n, _ in VARIANTES}:
            raise ValueError("Quatro variantes obrigatorias.")
        for r in s["ranking"]:
            if set(r["epocas"]) != {str(x) for x in c["sementes"]}:
                raise ValueError("Sementes incompletas.")
        conferir_hashes(s["fontes_selecao_sha256"])
        fontes.update(s["fontes_selecao_sha256"])
        for nome in ("contrato_execucao.json", "selecao_congelada.json", "escalas_selecao.csv"):
            p = pasta / nome
            fontes[str(p.resolve())] = base.sha256_arquivo(p)
        if any((pasta / "variantes" / n / "refit").exists() for n, _ in VARIANTES):
            raise ValueError("Refit anterior ao congelamento.")
    r = {"congelado_em_utc": agora(), "tarefas": list(TAREFAS),
         "fontes_selecao_sha256": fontes, "criterio": "nunca escolher por 2024"}
    base.salvar_json_atomico(r, path)
    return r


def validar_congelamento_global(pasta_saida):
    path = Path(pasta_saida) / "selecao_global_congelada.json"
    if not path.is_file():
        raise ValueError("Congele ambas as tarefas antes de construir o teste.")
    c = ler_json(path)
    expected = {str((Path(pasta_saida) / t / "selecao_congelada.json").resolve()) for t in TAREFAS}
    if set(c["tarefas"]) != set(TAREFAS) or not expected.issubset(c["fontes_selecao_sha256"]):
        raise ValueError("Congelamento global incompleto.")
    conferir_hashes(c["fontes_selecao_sha256"])
    for tarefa in TAREFAS:
        validar_selecao(Path(pasta_saida) / tarefa)


def prever_checkpoint(path, janelas):
    cp = torch.load(path, map_location="cpu", weights_only=True)
    t = dict(cp["tarefa"])
    for k in ("ajuste", "validacao", "refit", "teste"):
        t[k] = base.IntervaloParticao(**t[k])
    tarefa = base.EspecificacaoTarefa(**t)
    config = base.ConfiguracaoMultirresolucao(**cp["configuracao"])
    p = cp["preprocessamento"]
    if p["versao"] != 1 or not p["minmax"] or p["onde"] != "somente_entradas":
        raise ValueError("Pre-processamento desconhecido.")
    if (janelas.seq_len, janelas.pred_len) != (tarefa.seq_len, tarefa.pred_len):
        raise ValueError("Janela incompativel.")
    for i, n in zip(janelas.localidade_id, janelas.localidade):
        if p["localidades"].get(str(int(i))) != str(n):
            raise ValueError("Identidade de localidade divergente.")
    base.fixar_semente(cp["semente"], config.threads_torch)
    model = base.criar_modelo_neural("TimesNet", tarefa=tarefa, configuracao=config,
        num_localidades=max(int(i) for i in p["localidades"]) + 1, semente=cp["semente"])
    model.load_state_dict(cp["state_dict"])
    return treino.prever(model, janelas, pd.DataFrame(p["escalas"]),
                         batch_size=p["batch_size"], dispositivo=p["dispositivo"], niveis=p["niveis"])


def executar(slug, fase="selecao", pasta_saida=SAIDA, workers=1, smoke=False):
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers deve ser inteiro positivo.")
    if fase not in {"selecao", "refit"}:
        raise ValueError("Fase invalida.")
    root = Path(pasta_saida).resolve()
    if root == FONTE.resolve() or FONTE.resolve() in root.parents:
        raise ValueError("Nao gravar sobre resultados fonte.")
    root.mkdir(parents=True, exist_ok=True)
    pasta = root / slug
    lock = root / f".{slug}.lock"
    with lock.open("x", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    try:
        ctx, candidato, seeds, device = preparar_contexto(slug, fase, root, smoke)
        c = construir_contrato(ctx, candidato, seeds, device, workers)
        base.validar_ou_criar_contrato(pasta, c, retomar=True)
        escolha = pasta / "selecao_congelada.json"
        if fase == "selecao" and escolha.exists():
            _, s = validar_selecao(pasta)
            return s
        s = validar_selecao(pasta)[1] if fase == "refit" else None
        if s is not None and s["contrato_sha256"] != c["sha256_contrato"]:
            raise ValueError("Selecao de contrato diferente.")
        executor = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) if workers > 1 else None
        try:
            linhas = rodar_fase(ctx, candidato, seeds, device, pasta, c, fase, executor, s)
        finally:
            if executor is not None:
                executor.shutdown(wait=True, cancel_futures=True)
        if fase == "selecao":
            order = {n: i for i, (n, _) in enumerate(VARIANTES)}
            ranking = sorted(linhas, key=lambda r: (r["MAE_validacao_wm2"], order[r["nome"]]))
            s = {"tarefa": slug, "modo": ctx.config.modo_execucao, "contrato_sha256": c["sha256_contrato"],
                "selecao_concluida_antes_do_teste": True, "criado_em_utc": agora(),
                "criterio": c["criterio"], "ranking": ranking, "vencedor": ranking[0],
                "fontes_selecao_sha256": {str(p.resolve()): base.sha256_arquivo(p)
                    for p in (pasta / "variantes").rglob("*") if p.is_file()}}
            base.salvar_json_atomico(s, escolha)
            base.salvar_csv_atomico(pd.DataFrame(ranking).drop(columns="epocas"), pasta / "ranking_validacao.csv")
        else:
            base.salvar_csv_atomico(pd.DataFrame(linhas).drop(columns="epocas"), pasta / "comparacao.csv")
        status = {"etapa": "selecao_concluida" if fase == "selecao" else "concluida",
            "tarefa": slug, "modo": ctx.config.modo_execucao, "teste_avaliado": fase == "refit",
            "vencedor": s["vencedor"], "concluido_em_utc": agora()}
        base.salvar_json_atomico(status, pasta / "status_execucao.json")
        if fase == "refit":
            base.salvar_json_atomico(base.gerar_manifesto_artefatos(pasta), pasta / "manifesto_artefatos.json")
        return status
    except Exception as exc:
        if pasta.exists():
            base.salvar_json_atomico({"etapa": "erro", "tipo": type(exc).__name__, "mensagem": str(exc),
                "atualizado_em_utc": agora()}, pasta / "status_execucao.json")
        raise
    finally:
        lock.unlink()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=TAREFAS)
    ap.add_argument("--fase", choices=["selecao", "congelar", "refit"], default="selecao")
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    if args.fase == "congelar":
        congelar_global(args.saida)
    else:
        if args.tarefa is None:
            ap.error("--tarefa obrigatoria")
        executar(args.tarefa, args.fase, args.saida, args.workers, args.smoke)
    print("Fase concluida.", flush=True)


if __name__ == "__main__":
    main()
