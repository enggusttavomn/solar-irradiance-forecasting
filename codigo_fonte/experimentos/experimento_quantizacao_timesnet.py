"""Experimento mensal controlado: min-max + quantizacao apenas das entradas.

Configuracao TimesNet congelada da busca pura. Epocas/niveis escolhidos em
2023; as duas tarefas devem ter selecao global congelada antes de acessar 2024.
Todas as quatro variantes sao avaliadas apos congelamento, sem escolher por teste.
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
import time

import numpy as np
import pandas as pd
import torch

from codigo_fonte.experimentos import experimento_multirresolucao as base
from codigo_fonte.experimentos import otimizacao_timesnet_mensal as mensal
from codigo_fonte.experimentos import quantizacao_timesnet as quant
from codigo_fonte.experimentos.treinamento_timesnet_otimizacao import treinar_candidato

RAIZ = Path(__file__).resolve().parents[2]
FONTE = RAIZ / "resultados/busca_timesnet_mensal_20260920"
SAIDA = RAIZ / "resultados/quantizacao_timesnet_mensal_20260923"
TAREFAS = ("monthly_1", "monthly_6")
VARIANTES = (("sem_quantizacao", None), ("q64", 64), ("q128", 128), ("q256", 256))


def ler_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def agora():
    return datetime.now(timezone.utc).isoformat()


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")).hexdigest()


def preparar_contexto(tarefa_nome, smoke=False):
    if tarefa_nome not in TAREFAS:
        raise ValueError("Somente as duas tarefas mensais sao permitidas.")
    selecao = ler_json(FONTE / tarefa_nome / "selecao_congelada.json")
    origem = ler_json(FONTE / tarefa_nome / "contrato_execucao.json")
    vencedor = selecao["vencedor"]
    candidato = mensal.Candidato(**{f.name: vencedor[f.name] for f in fields(mensal.Candidato)
                                    if f.name in vencedor})
    if candidato.alvo != "bruto":
        raise ValueError("A configuracao de origem deve ser TimesNet pura.")
    config = candidato.configurar(base.ConfiguracaoMultirresolucao(**origem["configuracao"]))
    if smoke:
        config = replace(config, modo_execucao="smoke")
    diarias, _ = base.carregar_series_diarias()
    series = base.agregar_series_mensais(diarias)
    if smoke:
        series = series[:config.limite_localidades_smoke]
    tarefa = mensal.adaptar_tarefa(base.TAREFAS_CANONICAS[tarefa_nome], series, candidato.seq_len)
    return series, tarefa, candidato, config


def construir_contrato(series, tarefa, candidato, config, workers):
    contrato = base.construir_contrato(
        tarefa=tarefa, configuracao=config,
        arquivos_entrada=[s.caminho_fonte for s in series],
        arquivos_codigo_extras=[Path(__file__), Path(quant.__file__), Path(mensal.__file__),
                                Path(__file__).parents[2] / 'codigo_fonte/experimentos/treinamento_timesnet_otimizacao.py'])
    contrato.pop("sha256_contrato", None)
    contrato.update(
        experimento="minmax_quantizacao_entrada_mensal_v1", candidato_base=asdict(candidato),
        variantes=[{"nome": n, "niveis": k} for n, k in VARIANTES],
        minmax=True, quantizacao={"onde": "somente_entradas", "niveis": [64, 128, 256],
            "formula": "rint(clip(x_minmax,0,1)*(N-1))/(N-1)",
            "empates": "arredondamento_para_inteiro_par_np_rint", "intervalo": [0, 1],
            "alvos_quantizados": False, "pesos_quantizados": False,
            "controle": "sem_quantizacao_e_sem_clip"},
        criterio="menor_macro_MAE_fisico_ensemble_validacao_2023_horizonte_completo",
        ordem_desempate=[n for n, _ in VARIANTES], workers=workers, dispositivo="cpu",
        escala_selecao_pre_corte="2023-01-01", escala_refit_pre_corte="2024-01-01",
        avaliacao_teste="todas_variantes_predefinidas_apos_congelamento_global_sem_reselecao",
        fontes_configuracao={str(p.resolve()): base.sha256_arquivo(p) for p in
            [FONTE / tarefa.slug / "contrato_execucao.json", FONTE / tarefa.slug / "selecao_congelada.json"]},
        limitacoes=["2024 ja observado; analise retrospectiva requer confirmacao futura.",
                    "Quantizacao tambem satura entradas fora de [0,1]; controle nao satura.",
                    "Mesma validacao seleciona epocas e niveis; nao e teste prospectivo.",
                    "Quantizacao de dados; arquitetura, pesos e saidas continuam float32."])
    contrato["sha256_contrato"] = hash_obj(contrato)
    return contrato


def _prever(modelo, janelas, escalas, config, niveis):
    x = quant.normalizar_entradas(janelas, escalas, niveis)
    normalizada = base.prever_rede(modelo, x, janelas.localidade_id,
                                  batch_size=config.batch_size_mensal)
    return janelas.inverter(normalizada, escalas)


def diagnosticos(janelas, escalas, niveis):
    x = quant.normalizar_entradas(janelas, escalas, None)
    q = quant.quantizar_entradas(x, niveis)
    recortes = {"total": np.ones(len(x), dtype=bool)}
    recortes.update({str(int(i)): janelas.localidade_id == i for i in np.unique(janelas.localidade_id)})
    resultado = {}
    for nome, mascara in recortes.items():
        z, w = x[mascara], q[mascara]
        r = quant.diagnosticar_quantizacao(z, niveis)
        r["erro_medio_quantizacao_normalizado"] = float(np.abs(z.astype(float)-w).mean())
        r["erro_medio_somente_clip_normalizado"] = float(np.abs(z.astype(float)-np.clip(z, 0, 1)).mean()) if niveis else 0.0
        r["contagem_refere_a"] = "posicoes_das_janelas_sobrepostas_nao_meses_unicos"
        resultado[nome] = r
    return resultado


def _estimar(brutas, sementes):
    estimativas = [base.Estimativa("TimesNet", "semente", int(s), p, np.maximum(p, 0))
                   for s, p in zip(sementes, brutas, strict=True)]
    media = np.mean(brutas, axis=0)
    estimativas.append(base.Estimativa("TimesNet", "ensemble", None, media, np.maximum(media, 0)))
    return estimativas, media


def salvar_avaliacao(pasta, tarefa, janelas, brutas, sementes, nome_particao):
    estimativas, media = _estimar(brutas, sementes)
    local, macro = base.calcular_metricas_estimativas(
        tarefa=tarefa, particao=nome_particao, janelas=janelas, estimativas=estimativas)
    sufixo = "" if nome_particao == "teste_2024" else "_validacao"
    base.salvar_csv_atomico(local, pasta / f"metricas_por_localidade{sufixo}.csv")
    base.salvar_csv_atomico(macro, pasta / f"metricas_macro{sufixo}.csv")
    base.salvar_csv_atomico(base.montar_tabela_previsoes(tarefa=tarefa, janelas=janelas,
        estimativas=estimativas), pasta / ("previsoes_teste.csv" if not sufixo else "previsoes_validacao.csv"))
    base.salvar_csv_atomico(base.resumir_variabilidade_sementes(macro),
                            pasta / f"variabilidade_sementes{sufixo}.csv")
    return mensal.macro_mae(janelas, media)


def _seed_job(pasta_str, tarefa, candidato, config, semente, treino, avaliacao, escalas,
              nome_variante, niveis, contrato_hash, fase, epocas_fixas=None):
    pasta = Path(pasta_str)
    cache = pasta / fase / f"seed{semente}.npz"
    registro = cache.with_suffix(".json")
    checkpoint = pasta / "modelos" / f"timesnet_seed{semente}_{fase}.pt"
    if cache.exists() and registro.exists():
        meta = ler_json(registro)
        if meta["contrato_sha256"] != contrato_hash or meta["niveis"] != niveis:
            raise ValueError("Cache de outra configuracao.")
        for caminho, digest in meta["arquivos_sha256"].items():
            if base.sha256_arquivo(caminho) != digest:
                raise ValueError(f"Cache alterado: {caminho}")
        with np.load(cache, allow_pickle=False) as z:
            pred, epocas = z["previsao"], int(z["epocas"].item())
        mensal.macro_mae(avaliacao, pred)
        return {"semente": semente, "previsao": pred, "epocas": epocas,
                "duracao_s": meta["duracao_s"], "cache": True}
    inicio = time.perf_counter()
    print(f"[{tarefa.slug}] {fase} {nome_variante} seed={semente} inicio", flush=True)
    modelo, epocas, historico = treinar_candidato(
        tarefa=tarefa, configuracao=config, semente=int(semente),
        ajuste=quant.aplicar_quantizacao(treino, niveis), escalas=escalas,
        validacao=quant.aplicar_quantizacao(avaliacao, niveis) if fase == "selecao" else None,
        perda=candidato.perda, epocas_fixas=epocas_fixas)
    pred = _prever(modelo, avaliacao, escalas, config, niveis)
    mensal.macro_mae(avaliacao, pred)
    prep = {"versao": 1, "minmax": True, "niveis": niveis, "onde": "somente_entradas",
            "escala_fim_exclusivo": "2023-01-01" if fase == "selecao" else "2024-01-01",
            "escalas": escalas.to_dict(orient="records"),
            "localidades": {str(int(i)): str(n) for i, n in zip(treino.localidade_id, treino.localidade)},
            "formula": "rint(clip(x,0,1)*(N-1))/(N-1); None sem clip nem arredondamento",
            "dispositivo": "cpu", "batch_size": config.batch_size_mensal}
    base.salvar_torch_atomico({"state_dict": modelo.state_dict(), "tarefa": asdict(tarefa),
        "configuracao": asdict(config), "candidato": asdict(candidato), "semente": int(semente),
        "epocas": int(epocas), "fase": fase, "variante": nome_variante,
        "contrato_sha256": contrato_hash, "preprocessamento": prep,
        "selecao_global_sha256": (base.sha256_arquivo(pasta.parents[2] / "selecao_global_congelada.json") if fase == "refit" else None),
        "selecao_tarefa_sha256": (base.sha256_arquivo(pasta.parents[1] / "selecao_congelada.json") if fase == "refit" else None)}, checkpoint)
    base.salvar_csv_atomico(historico, cache.with_suffix(".csv"))
    base.salvar_npz_atomico(cache, previsao=pred, epocas=np.asarray(epocas))
    segundos = time.perf_counter() - inicio
    base.salvar_json_atomico({"contrato_sha256": contrato_hash, "niveis": niveis,
        "semente": int(semente), "epocas": int(epocas), "duracao_s": segundos, "concluido_em_utc": agora(),
        "arquivos_sha256": {str(p.resolve()): base.sha256_arquivo(p) for p in
                             [cache, cache.with_suffix(".csv"), checkpoint]}}, registro)
    print(f"[{tarefa.slug}] {fase} {nome_variante} seed={semente} fim epocas={epocas} segundos={segundos:.1f}", flush=True)
    return {"semente": semente, "previsao": pred, "epocas": epocas, "duracao_s": segundos, "cache": False}


def rodar_sementes(executor, *, pasta, tarefa, candidato, config, treino, avaliacao, escalas,
                    nome, niveis, contrato_hash, fase, epocas=None):
    argumentos = [(str(pasta), tarefa, candidato, config, s, treino, avaliacao, escalas,
                   nome, niveis, contrato_hash, fase, None if epocas is None else int(epocas[str(s)]))
                  for s in config.sementes_efetivas]
    if executor is None:
        resultados = [_seed_job(*args) for args in argumentos]
    else:
        futuros = [executor.submit(_seed_job, *args) for args in argumentos]
        resultados = [f.result() for f in as_completed(futuros)]
    por_semente = {int(r["semente"]): r for r in resultados}
    return [por_semente[int(s)] for s in config.sementes_efetivas]


def selecionar(series, tarefa, candidato, config, pasta, contrato, executor):
    caminho = pasta / "selecao_congelada.json"
    if caminho.exists():
        selecao = ler_json(caminho)
        if selecao["contrato_sha256"] != contrato["sha256_contrato"]:
            raise ValueError("Selecao congelada de outro contrato.")
        for arquivo, digest in selecao["fontes_selecao_sha256"].items():
            if base.sha256_arquivo(arquivo) != digest:
                raise ValueError("Fonte da selecao foi alterada.")
        return selecao
    series = tuple(replace(s, datas=s.datas[s.datas < "2024-01-01"],
                            ghi=s.ghi[s.datas < "2024-01-01"]) for s in series)
    ajuste = mensal._janelas(series, tarefa, "ajuste", config)
    validacao = mensal._janelas(series, tarefa, "validacao", config)
    escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo="2023-01-01", nome_ajuste="selecao")
    base.salvar_csv_atomico(escalas, pasta / "escalas_selecao.csv")
    ranking = []
    for nome, niveis in VARIANTES:
        variante = pasta / "variantes" / nome
        resultados = rodar_sementes(executor, pasta=variante, tarefa=tarefa, candidato=candidato,
            config=config, treino=ajuste, avaliacao=validacao, escalas=escalas, nome=nome, niveis=niveis,
            contrato_hash=contrato["sha256_contrato"], fase="selecao")
        brutas = [r["previsao"] for r in resultados]
        mae = salvar_avaliacao(variante, tarefa, validacao, brutas, config.sementes_efetivas, "validacao_2023")
        base.salvar_json_atomico({"ajuste": diagnosticos(ajuste, escalas, niveis),
            "validacao": diagnosticos(validacao, escalas, niveis)}, variante / "diagnostico_selecao.json")
        linha = {"nome": nome, "niveis": niveis, "MAE_validacao_wm2": mae,
            "epocas": {str(r["semente"]): r["epocas"] for r in resultados},
            "MAE_validacao_sementes": {str(r["semente"]): mensal.macro_mae(validacao, r["previsao"]) for r in resultados}}
        ranking.append(linha)
        base.salvar_json_atomico({"etapa": "selecionando", "variante_concluida": nome,
            "MAE_validacao_wm2": mae, "atualizado_em_utc": agora()}, pasta / "status_execucao.json")
    ordem = {n: i for i, (n, _) in enumerate(VARIANTES)}
    ranking.sort(key=lambda r: (r["MAE_validacao_wm2"], ordem[r["nome"]]))
    selecao = {"tarefa": tarefa.slug, "contrato_sha256": contrato["sha256_contrato"],
        "selecao_concluida_antes_do_teste": True, "criado_em_utc": agora(),
        "criterio": contrato["criterio"], "vencedor": ranking[0], "ranking": ranking,
        "modo": config.modo_execucao,
        "fontes_selecao_sha256": {str(p.resolve()): base.sha256_arquivo(p)
            for p in (pasta / "variantes").rglob("*") if p.is_file()}}
    base.salvar_json_atomico(selecao, caminho)
    base.salvar_csv_atomico(pd.DataFrame(ranking).drop(columns=["epocas", "MAE_validacao_sementes"]),
                            pasta / "ranking_validacao.csv")
    return selecao


def congelar_global(pasta_saida):
    pasta_saida = Path(pasta_saida)
    destino = pasta_saida / "selecao_global_congelada.json"
    fontes = {}
    for tarefa in TAREFAS:
        selecao_path = pasta_saida / tarefa / "selecao_congelada.json"
        s = ler_json(selecao_path)
        c = ler_json(pasta_saida / tarefa / "contrato_execucao.json")
        if not s["selecao_concluida_antes_do_teste"] or s["contrato_sha256"] != c["sha256_contrato"]:
            raise ValueError("Selecao incompleta/incoerente.")
        if {r["nome"] for r in s["ranking"]} != {n for n, _ in VARIANTES}:
            raise ValueError("E necessario concluir as quatro variantes antes do teste.")
        for row in s["ranking"]:
            if set(row["epocas"]) != {str(x) for x in (c["configuracao"]["sementes"][:1] if s["modo"] == "smoke" else c["configuracao"]["sementes"])}:
                raise ValueError("Sementes incompletas na selecao.")
        for arquivo, digest in s["fontes_selecao_sha256"].items():
            if base.sha256_arquivo(arquivo) != digest:
                raise ValueError("Fonte de selecao alterada antes do congelamento global.")
        fontes[str(selecao_path.resolve())] = base.sha256_arquivo(selecao_path)
        for extra in ("contrato_execucao.json", "escalas_selecao.csv"):
            path_extra = pasta_saida / tarefa / extra
            fontes[str(path_extra.resolve())] = base.sha256_arquivo(path_extra)
        for p in (pasta_saida / tarefa / "variantes").rglob("*"):
            if p.is_file() and p.suffix in {".npz", ".csv", ".json", ".pt"}:
                fontes[str(p.resolve())] = base.sha256_arquivo(p)
    if destino.exists():
        anterior = ler_json(destino)
        # Nao inclui artefatos de refit novos na reconferencia das selecoes.
        for p, digest in anterior["fontes_selecao_sha256"].items():
            if base.sha256_arquivo(p) != digest:
                raise ValueError("Selecao alterada depois do congelamento global.")
        return anterior
    if any((pasta_saida / t / "variantes" / n / "refit").exists() for t in TAREFAS for n, _ in VARIANTES):
        raise ValueError("Ha refit anterior ao congelamento global.")
    r = {"congelado_em_utc": agora(), "fontes_selecao_sha256": fontes,
         "tarefas": list(TAREFAS), "criterio": "nunca escolher por 2024"}
    base.salvar_json_atomico(r, destino)
    return r


def validar_congelamento_global(pasta_saida):
    path = Path(pasta_saida) / "selecao_global_congelada.json"
    if not path.is_file():
        raise ValueError("Congele as duas selecoes antes de construir janelas de teste.")
    congelado = ler_json(path)
    fontes = congelado["fontes_selecao_sha256"]
    esperadas = {str((Path(pasta_saida) / t / "selecao_congelada.json").resolve()) for t in TAREFAS}
    if set(congelado["tarefas"]) != set(TAREFAS) or not esperadas.issubset(fontes):
        raise ValueError("Congelamento global incompleto.")
    for p, digest in fontes.items():
        if base.sha256_arquivo(p) != digest:
            raise ValueError("Fonte de selecao mudou apos congelamento.")


def refazer_teste(series, tarefa, candidato, config, pasta, contrato, selecao, executor):
    validar_congelamento_global(pasta.parent)
    refit = mensal._janelas(series, tarefa, "refit", config)
    teste = mensal._janelas(series, tarefa, "teste", config)
    escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo="2024-01-01", nome_ajuste="refit")
    base.salvar_csv_atomico(escalas, pasta / "escalas_refit.csv")
    por_nome = {r["nome"]: r for r in selecao["ranking"]}
    linhas = []
    for nome, niveis in VARIANTES:
        variante = pasta / "variantes" / nome
        resultados = rodar_sementes(executor, pasta=variante, tarefa=tarefa, candidato=candidato,
            config=config, treino=refit, avaliacao=teste, escalas=escalas, nome=nome, niveis=niveis,
            contrato_hash=contrato["sha256_contrato"], fase="refit", epocas=por_nome[nome]["epocas"])
        mae = salvar_avaliacao(variante, tarefa, teste, [r["previsao"] for r in resultados],
                               config.sementes_efetivas, "teste_2024")
        base.salvar_json_atomico({"refit": diagnosticos(refit, escalas, niveis),
            "teste": diagnosticos(teste, escalas, niveis)}, variante / "diagnostico_refit.json")
        linha = {"tarefa": tarefa.slug, "nome": nome, "niveis": niveis,
            "MAE_validacao_wm2": por_nome[nome]["MAE_validacao_wm2"], "MAE_teste_wm2": mae,
            "selecionada": nome == selecao["vencedor"]["nome"]}
        linhas.append(linha)
        base.salvar_json_atomico({"etapa": "concluida", "modo": config.modo_execucao,
                                 **linha}, variante / "status_execucao.json")
        base.salvar_json_atomico({"etapa": "avaliando", "variante_concluida": nome,
            "MAE_teste_wm2": mae, "atualizado_em_utc": agora()}, pasta / "status_execucao.json")
    base.salvar_csv_atomico(pd.DataFrame(linhas), pasta / "comparacao.csv")
    return linhas


def prever_checkpoint(caminho, janelas):
    cp = torch.load(caminho, map_location="cpu", weights_only=True)
    t = dict(cp["tarefa"])
    for key in ("ajuste", "validacao", "refit", "teste"):
        t[key] = base.IntervaloParticao(**t[key])
    tarefa = base.EspecificacaoTarefa(**t)
    if (janelas.seq_len, janelas.pred_len) != (tarefa.seq_len, tarefa.pred_len):
        raise ValueError("Janelas nao correspondem ao checkpoint.")
    cfg = base.ConfiguracaoMultirresolucao(**cp["configuracao"])
    prep = cp["preprocessamento"]
    if prep["versao"] != 1 or prep["onde"] != "somente_entradas" or not prep["minmax"]:
        raise ValueError("Preprocessamento invalido.")
    for i, n in zip(janelas.localidade_id, janelas.localidade):
        if prep["localidades"].get(str(int(i))) != str(n):
            raise ValueError("Localidade diferente do checkpoint.")
    base.fixar_semente(int(cp["semente"]), cfg.threads_torch)
    modelo = base.criar_modelo_neural("TimesNet", tarefa=tarefa, configuracao=cfg,
        num_localidades=max(int(i) for i in prep["localidades"]) + 1, semente=int(cp["semente"]))
    modelo.load_state_dict(cp["state_dict"])
    return _prever(modelo, janelas, pd.DataFrame(prep["escalas"]), cfg, prep["niveis"])


def executar(tarefa_nome, pasta_saida=SAIDA, fase="selecao", workers=2, smoke=False):
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers deve ser inteiro positivo.")
    if fase not in {"selecao", "refit"}:
        raise ValueError("Fase invalida.")
    raiz = Path(pasta_saida).resolve()
    if raiz == FONTE.resolve() or FONTE.resolve() in raiz.parents:
        raise ValueError("Nao substituir a busca de referencia.")
    series, tarefa, candidato, config = preparar_contexto(tarefa_nome, smoke)
    pasta = raiz / tarefa_nome
    raiz.mkdir(parents=True, exist_ok=True)
    lock = raiz / f".{tarefa_nome}.lock"
    try:
        with lock.open("x") as f:
            f.write(str(os.getpid()))
    except FileExistsError as e:
        raise RuntimeError(f"Execucao concorrente: {lock}") from e
    try:
        contrato = construir_contrato(series, tarefa, candidato, config, workers)
        base.validar_ou_criar_contrato(pasta, contrato, retomar=True)
        with ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn")) if workers > 1 else _SemExecutor() as executor:
            selecao = selecionar(series, tarefa, candidato, config, pasta, contrato, executor)
            linhas = refazer_teste(series, tarefa, candidato, config, pasta, contrato, selecao, executor) if fase == "refit" else None
        status = {"etapa": "concluida" if fase == "refit" else "selecao_concluida",
                  "tarefa": tarefa_nome, "modo": config.modo_execucao,
                  "teste_avaliado": fase == "refit", "vencedor": selecao["vencedor"],
                  "atualizado_em_utc": agora()}
        base.salvar_json_atomico(status, pasta / "status_execucao.json")
        if fase == "refit":
            base.salvar_json_atomico(base.gerar_manifesto_artefatos(pasta), pasta / "manifesto_artefatos.json")
        return linhas or selecao
    except Exception as erro:
        if pasta.exists():
            base.salvar_json_atomico({"etapa": "falhou", "erro": str(erro), "atualizado_em_utc": agora()},
                                    pasta / "status_execucao.json")
        raise
    finally:
        lock.unlink()


class _SemExecutor:
    def __enter__(self):
        return None
    def __exit__(self, *args):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tarefa", choices=TAREFAS)
    parser.add_argument("--fase", choices=["selecao", "congelar", "refit"], default="selecao")
    parser.add_argument("--saida", type=Path, default=SAIDA)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.fase == "congelar":
        congelar_global(args.saida)
    else:
        if not args.tarefa:
            parser.error("--tarefa obrigatoria na selecao e refit")
        executar(args.tarefa, args.saida, args.fase, args.workers, args.smoke)
    print("Fase concluida.", flush=True)


if __name__ == "__main__":
    main()