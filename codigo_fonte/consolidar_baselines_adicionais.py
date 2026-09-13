"""Alinha novos baselines a previsoes imutaveis e reavalia todas as metricas.

MSE em W^2/m^4; macro-MSE e media de MSEs locais (nao macro-RMSE^2).
Nao treina modelos. Recusa tabelas publicaveis incompletas e contratos alterados.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from codigo_fonte import experimento_multirresolucao as m
from codigo_fonte.experimento_baselines_adicionais import FONTE, SAIDA, MODELOS, TAREFAS

METRICAS = ("MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2")
NOMES = {**{v: k for k, v in m.SLUG_MODELO.items()}, "gru": "GRU", "transformer": "Transformer", "informer": "Informer", "arima": "ARIMA"}


def pasta_modelo(saida, slug, modelo):
    return saida / slug / ("arima_robusto" if modelo == "ARIMA" else modelo.lower())


def metricas_vetor(real, previsto):
    real, previsto = np.asarray(real, dtype=float), np.asarray(previsto, dtype=float)
    if real.shape != previsto.shape or not np.isfinite(real).all() or not np.isfinite(previsto).all():
        raise ValueError("Metricas exigem vetores alinhados e finitos.")
    return {**m._metricas_vetor(real, previsto), "MSE_w2m4": float(np.mean((real - previsto) ** 2))}


def metadados_coluna(coluna: str, horario: bool) -> tuple:
    slug = coluna.removeprefix("previsao_pos_").removesuffix("_wm2")
    seed = re.fullmatch(r"(.+)_seed(\d+)", slug)
    if seed:
        return NOMES[seed[1]], "semente", int(seed[2])
    for tipo in ("ensemble", "deterministica"):
        if slug.endswith("_" + tipo):
            return NOMES[slug.removesuffix("_" + tipo)], tipo, None
    modelo = NOMES[slug]
    if not horario:
        raise ValueError(f"Coluna sem tipo de estimativa: {coluna}")
    return (modelo, "deterministica", None) if modelo in m.MODELOS_DETERMINISTICOS else (modelo, "semente", 42)


def avaliar(tabela: pd.DataFrame, tarefa, particao: str):
    horario = tarefa.resolucao == "horaria"
    passo, origem = ("passo_h", "origem_utc") if horario else ("passo", "origem")
    registros = []
    for col in [c for c in tabela if c.startswith("previsao_pos_")]:
        modelo, tipo, seed = metadados_coluna(col, horario)
        for localidade, grupo in tabela.groupby("localidade", sort=True):
            for h in tarefa.horizontes:
                for recorte, mascara in (("cumulativo", grupo[passo] <= h), ("lead_exato", grupo[passo] == h)):
                    g = grupo.loc[mascara]
                    registros.append({"tarefa": tarefa.slug, "resolucao": tarefa.resolucao,
                        "particao": particao, "modelo": modelo, "tipo_estimativa": tipo,
                        "semente": seed, "localidade": localidade, "tipo_horizonte": recorte,
                        "horizonte": h, "N_origens": int(g[origem].nunique()), "N_pontos": len(g),
                        **metricas_vetor(g.ghi_real_wm2.to_numpy(), g[col].to_numpy())})
    local = pd.DataFrame(registros)
    chaves = ["tarefa", "resolucao", "particao", "modelo", "tipo_estimativa", "semente", "tipo_horizonte", "horizonte"]
    macro = local.groupby(chaves, dropna=False, as_index=False).agg(
        N_localidades=("localidade", "nunique"), N_origens=("N_origens", "sum"),
        N_pontos=("N_pontos", "sum"), **{met: (met, "mean") for met in METRICAS})
    macro["agregacao"] = "media_aritmetica_das_metricas_por_localidade"
    return local, macro


def alinhar(fonte: pd.DataFrame, novo: pd.DataFrame, horario: bool) -> pd.DataFrame:
    datas, chaves = (("origem_utc", "timestamp_alvo_utc"), ["localidade", "origem_utc", "timestamp_alvo_utc", "passo_h"]) if horario else (
        ("origem", "data_alvo"), ["localidade", "origem", "data_alvo", "passo"])
    fonte, novo = fonte.copy(), novo.copy()
    for col in datas:
        fonte[col], novo[col] = pd.to_datetime(fonte[col], utc=True), pd.to_datetime(novo[col], utc=True)
    novas = [c for c in novo if c.startswith("previsao_")]
    if set(novas) & set(fonte):
        raise ValueError("Baseline duplicado: seria sobrescrita.")
    if len(fonte) != len(novo) or fonte.duplicated(chaves).any() or novo.duplicated(chaves).any():
        raise ValueError("Matriz incompleta ou chaves duplicadas.")
    junto = fonte.merge(novo[chaves + ["ghi_real_wm2"] + novas], on=chaves, how="left", validate="one_to_one", suffixes=("", "_novo"))
    if not np.allclose(junto.ghi_real_wm2, junto.ghi_real_wm2_novo, atol=1e-6, rtol=0):
        raise ValueError("Alvos divergentes.")
    if not np.isfinite(junto[novas].to_numpy()).all():
        raise ValueError("Previsoes novas ausentes ou nao finitas.")
    return junto.drop(columns="ghi_real_wm2_novo")


def verificar_artefatos(pasta: Path):
    status = json.loads((pasta / "status.json").read_text(encoding="utf-8"))
    if status["etapa"] != "concluida" or not status["resultado_publicavel"]:
        raise ValueError(f"Baseline nao concluido/publicavel: {pasta}")
    c = json.loads((pasta / "contrato.json").read_text(encoding="utf-8"))
    for r in c["arquivos_entrada"] + c["arquivos_codigo"]:
        if m.sha256_arquivo(r["arquivo"]) != r["sha256"]:
            raise ValueError(f"Fonte/codigo alterado desde o contrato: {r['arquivo']}")
    manifesto = json.loads((pasta / "manifesto_artefatos.json").read_text(encoding="utf-8"))
    for r in manifesto["arquivos"]:
        if m.sha256_arquivo(pasta / r["arquivo"]) != r["sha256"]:
            raise ValueError(f"Artefato alterado: {pasta / r['arquivo']}")


def tabela_nova(pasta: Path, tarefa, modelo: str, particao: str) -> pd.DataFrame:
    tabela = pd.read_csv(pasta / f"chaves_{particao}.csv.gz")
    seeds = [42] if tarefa.resolucao == "horaria" else list(m.SEMENTES_CANONICAS)
    arquivos = [("deterministica", pasta / "cache/deterministica.npz")] if modelo == "ARIMA" else [
        (f"seed{s}", pasta / "cache" / f"seed{s}.npz") for s in seeds]
    previsoes = []
    for tipo, arquivo in arquivos:
        with np.load(arquivo, allow_pickle=False) as z:
            bruto, pos = z[f"{particao}_bruta"], z[f"{particao}_pos"]
            if bruto.size != len(tabela) or bruto.shape != pos.shape:
                raise ValueError("Cache incompleto.")
            for versao, array in (("bruta", bruto), ("pos", pos)):
                tabela[f"previsao_{versao}_{modelo.lower()}_{tipo}_wm2"] = array.reshape(-1)
            previsoes.append(bruto)
    if len(previsoes) > 1:
        bruto = np.mean(np.stack(previsoes), axis=0).reshape(-1)
        tabela[f"previsao_bruta_{modelo.lower()}_ensemble_wm2"] = bruto
        tabela[f"previsao_pos_{modelo.lower()}_ensemble_wm2"] = np.maximum(bruto, 0.0)
    return tabela


def conferir_legado(novas: pd.DataFrame, antigas: pd.DataFrame):
    chaves = ["tarefa", "particao", "modelo", "tipo_estimativa", "semente", "tipo_horizonte", "horizonte"]
    if "localidade" in antigas:
        chaves.append("localidade")
    comparacao = antigas.merge(novas, on=chaves, how="left", validate="one_to_one", suffixes=("_antiga", "_nova"))
    for met in ("MAE_wm2", "RMSE_wm2", "nRMSE", "R2"):
        if not np.allclose(comparacao[f"{met}_antiga"], comparacao[f"{met}_nova"], atol=1e-8, rtol=1e-10, equal_nan=True):
            raise ValueError(f"A consolidacao alteraria a metrica canonica {met}.")


def consolidar(saida: Path, *, somente_legado=False):
    destino = saida / ("consolidado_legado" if somente_legado else "consolidado")
    todos_locais, todos_macro, hashes = [], [], []
    for slug, tarefa in TAREFAS.items():
        locais, macros = [], []
        if not somente_legado:
            for modelo in MODELOS:
                verificar_artefatos(pasta_modelo(saida, slug, modelo))
        for p, arq in (("validacao_2023", "previsoes_validacao.csv.gz"), ("teste_2024", "previsoes_teste.csv.gz")):
            caminho = FONTE / slug / arq
            hashes.append({"arquivo": str(caminho), "sha256": m.sha256_arquivo(caminho)})
            tabela = pd.read_csv(caminho)
            if not somente_legado:
                for modelo in MODELOS:
                    tabela = alinhar(tabela, tabela_nova(pasta_modelo(saida, slug, modelo), tarefa, modelo, p), tarefa.resolucao == "horaria")
            local, macro = avaliar(tabela, tarefa, p)
            locais.append(local)
            macros.append(macro)
            m.salvar_csv_atomico(tabela, destino / slug / arq)
        local, macro = pd.concat(locais, ignore_index=True), pd.concat(macros, ignore_index=True)
        conferir_legado(local, pd.read_csv(FONTE / slug / "metricas_por_localidade.csv"))
        conferir_legado(macro, pd.read_csv(FONTE / slug / "metricas_macro.csv"))
        m.salvar_csv_atomico(local, destino / slug / "metricas_por_localidade.csv")
        m.salvar_csv_atomico(macro, destino / slug / "metricas_macro.csv")
        todos_locais.append(local)
        todos_macro.append(macro)
    local, macro = pd.concat(todos_locais, ignore_index=True), pd.concat(todos_macro, ignore_index=True)
    sementes = macro.loc[macro.tipo_estimativa == "semente"]
    chaves = ["tarefa", "resolucao", "particao", "modelo", "tipo_horizonte", "horizonte"]
    variabilidade = sementes.groupby(chaves, as_index=False).agg(N_sementes=("semente", "nunique"),
        **{f"{met}_{nome}": (met, func) for met in METRICAS for nome, func in (("media", "mean"), ("desvio_padrao", "std"))})
    for nome, quadro in (("metricas_por_localidade", local), ("metricas_macro", macro), ("variabilidade_sementes", variabilidade)):
        m.salvar_csv_atomico(quadro, destino / f"{nome}.csv")
    m.salvar_json_atomico({"etapa": "concluida", "inclui_todos_novos_baselines": not somente_legado,
        "fonte_inalterada": hashes, "MSE_unidade": "W^2/m^4", "agregacao": "metricas_locais_depois_media_macro",
        "hash_codigo_avaliacao": m.sha256_arquivo(__file__)}, destino / "auditoria_consolidacao.json")
    print(f"Consolidacao verificada: {destino}; {len(local)} metricas locais, {len(macro)} macro.", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--somente-legado", action="store_true")
    a = ap.parse_args()
    consolidar(a.saida, somente_legado=a.somente_legado)
