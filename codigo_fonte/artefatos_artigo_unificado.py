"""Geracao auditavel de tabelas e figuras para o artigo unificado.

Este modulo e deliberadamente estrito: ele so consome tarefas concluidas e
publicaveis, confere o contrato e todos os hashes declarados no manifesto e
recalcula os resumos a partir dos CSVs primarios. Resultados de ``smoke`` ou
pastas parciais nao sao convertidos em material de publicacao.

O contexto meteorologico da NASA POWER e usado exclusivamente depois da
previsao. A classificacao adversa depende de precipitacao e nebulosidade; GHI
observada ou prevista nunca e usada para chamar um dia de chuvoso/nublado.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import time
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator, Mapping, Sequence

import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


SEMENTES_CANONICAS = (11, 23, 42, 67, 89)
TAREFA_HORARIA = "hourly_72_extension"
MODELOS_APRENDIDOS = {"XGBoost", "LSTM", "TimesNet", "DilatedRNN"}
MODELOS_COMPARADOS = ("TimesNet", "DilatedRNN")
TOLERANCIA_EMPATE_WM2 = 1e-12
RAIZ_PROJETO = Path(__file__).resolve().parents[1]

ARQUIVOS_COMUNS_OBRIGATORIOS = {
    "status_execucao.json",
    "contrato_execucao.json",
    "metricas_macro.csv",
    "metricas_por_localidade.csv",
    "previsoes_validacao.csv.gz",
    "previsoes_teste.csv.gz",
    "comparacao_pareada_localidades.csv",
    "comparacao_pareada_resumo.csv",
    "epocas_selecionadas.csv",
    "historico_treinamento.csv",
    "escalas_minmax_pre_corte.csv",
    "protocolo_temporal.csv",
    "hiperparametros_e_metodo.json",
}

COLUNAS_METRICAS = {
    "tarefa",
    "resolucao",
    "particao",
    "modelo",
    "tipo_estimativa",
    "semente",
    "tipo_horizonte",
    "horizonte",
    "N_origens",
    "N_pontos",
    "MAE_wm2",
    "RMSE_wm2",
    "nRMSE",
    "R2",
}

COLUNAS_CONTEXTO = {
    "data_local",
    "localidade",
    "precipitacao_corrigida_mm_dia",
    "nebulosidade_percentual",
    "irradiacao_all_sky_kwh_m2_dia",
    "irradiacao_clear_sky_kwh_m2_dia",
    "indice_all_sky_clear_sky",
    "chuva_relevante",
    "muito_nublado",
    "condicao_adversa_independente",
    "fonte_contexto",
    "time_standard",
}


class ArtefatoNaoPublicavelError(ValueError):
    """Indica que uma entrada nao satisfaz o contrato de publicacao."""


def caminho_portatil(caminho: str | Path) -> str:
    """Representa arquivos do projeto sem incorporar o caminho da maquina."""

    resolvido = Path(caminho).resolve()
    try:
        return resolvido.relative_to(RAIZ_PROJETO).as_posix()
    except ValueError:
        return str(resolvido)


@dataclass(frozen=True)
class EntradaValidada:
    pasta: Path
    tarefa: str
    resolucao: str
    status: Mapping[str, object]
    manifesto: Mapping[str, object]

    @property
    def uma_semente(self) -> bool:
        return self.tarefa == TAREFA_HORARIA

    @property
    def limitacao_sementes(self) -> str:
        if self.uma_semente:
            return (
                "extensao_horaria_com_uma_semente_seed_42;"
                "sem_variabilidade_entre_sementes"
            )
        return "nenhuma;ensemble_de_cinco_sementes_para_modelos_aprendidos"


@dataclass(frozen=True)
class EsquemaPrevisoes:
    caminho: Path
    colunas_leitura: tuple[str, ...]
    particao: str
    localidade: str
    origem: str
    alvo_local: str
    passo: str
    real: str
    timesnet: str
    dilatedrnn: str
    elevacao: str | None = None
    periodo_diurno: str | None = None


def sha256_arquivo(caminho: str | Path, *, bloco: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(caminho).open("rb") as arquivo:
        while pedaco := arquivo.read(bloco):
            digest.update(pedaco)
    return digest.hexdigest()


def _carregar_json(caminho: Path) -> dict[str, object]:
    try:
        valor = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError as erro:
        raise ArtefatoNaoPublicavelError(f"Arquivo obrigatorio ausente: {caminho}") from erro
    except json.JSONDecodeError as erro:
        raise ArtefatoNaoPublicavelError(f"JSON invalido: {caminho}") from erro
    if not isinstance(valor, dict):
        raise ArtefatoNaoPublicavelError(f"JSON deve conter um objeto: {caminho}")
    return valor


def _json_canonico(valor: Mapping[str, object]) -> bytes:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _slug(valor: object) -> str:
    texto = unicodedata.normalize("NFKD", str(valor)).encode("ascii", "ignore").decode()
    return "_".join(texto.casefold().replace("-", " ").split())


def _validar_status(status: Mapping[str, object], pasta: Path) -> None:
    etapa = str(status.get("etapa", "")).casefold()
    if etapa not in {"concluida", "concluido"}:
        raise ArtefatoNaoPublicavelError(
            f"Execucao incompleta em {pasta}: etapa={status.get('etapa')!r}."
        )
    if status.get("modo_execucao") != "completa":
        raise ArtefatoNaoPublicavelError(
            f"Resultado smoke/nao completo recusado em {pasta}."
        )
    if status.get("resultado_smoke_nao_publicavel") is not False:
        raise ArtefatoNaoPublicavelError(
            f"Resultado smoke ou sem marcacao publica recusado em {pasta}."
        )
    if status.get("resultado_publicavel") is not True:
        raise ArtefatoNaoPublicavelError(
            f"Status nao declara resultado_publicavel=true em {pasta}."
        )
    tarefa = str(status.get("tarefa", ""))
    if not tarefa:
        raise ArtefatoNaoPublicavelError(f"Status sem identificador de tarefa em {pasta}.")
    if tarefa == TAREFA_HORARIA:
        if status.get("semente") != 42 or status.get("modelo_adicionado") != "DilatedRNN":
            raise ArtefatoNaoPublicavelError(
                "A extensao horaria deve declarar DilatedRNN e a unica semente 42."
            )
    else:
        sementes = tuple(int(x) for x in status.get("sementes_efetivas", []))
        if sementes != SEMENTES_CANONICAS:
            raise ArtefatoNaoPublicavelError(
                f"{tarefa} nao possui as cinco sementes canonicas {SEMENTES_CANONICAS}."
            )


def _validar_contrato(pasta: Path, status: Mapping[str, object]) -> None:
    contrato = _carregar_json(pasta / "contrato_execucao.json")
    declarado = contrato.get("sha256_contrato")
    if not isinstance(declarado, str) or len(declarado) != 64:
        raise ArtefatoNaoPublicavelError(f"Contrato sem SHA-256 valido em {pasta}.")
    base = dict(contrato)
    base.pop("sha256_contrato", None)
    calculado = hashlib.sha256(_json_canonico(base)).hexdigest()
    if calculado != declarado:
        raise ArtefatoNaoPublicavelError(f"Hash interno do contrato diverge em {pasta}.")
    if status.get("sha256_contrato") != declarado:
        raise ArtefatoNaoPublicavelError(f"Status e contrato divergem em {pasta}.")


def _caminho_manifestado(pasta: Path, relativo: object) -> Path:
    texto = str(relativo).replace("\\", "/")
    rel = Path(texto)
    if rel.is_absolute() or ".." in rel.parts:
        raise ArtefatoNaoPublicavelError(f"Caminho inseguro no manifesto: {texto!r}.")
    raiz = pasta.resolve()
    caminho = (pasta / rel).resolve()
    if caminho != raiz and raiz not in caminho.parents:
        raise ArtefatoNaoPublicavelError(f"Caminho fora da tarefa no manifesto: {texto!r}.")
    return caminho


def _validar_manifesto(pasta: Path, manifesto: Mapping[str, object]) -> None:
    itens = manifesto.get("arquivos")
    if not isinstance(itens, list):
        raise ArtefatoNaoPublicavelError(
            f"Manifesto de {pasta} nao usa a lista auditavel de arquivos."
        )
    if manifesto.get("N_arquivos") != len(itens):
        raise ArtefatoNaoPublicavelError(f"N_arquivos inconsistente em {pasta}.")
    declarados: set[str] = set()
    for item in itens:
        if not isinstance(item, dict):
            raise ArtefatoNaoPublicavelError(f"Entrada invalida no manifesto de {pasta}.")
        relativo = str(item.get("arquivo", "")).replace("\\", "/")
        if not relativo or relativo in declarados:
            raise ArtefatoNaoPublicavelError(
                f"Arquivo vazio ou duplicado no manifesto de {pasta}: {relativo!r}."
            )
        declarados.add(relativo)
        caminho = _caminho_manifestado(pasta, relativo)
        if not caminho.is_file():
            raise ArtefatoNaoPublicavelError(f"Arquivo manifestado ausente: {caminho}.")
        if item.get("bytes") != caminho.stat().st_size:
            raise ArtefatoNaoPublicavelError(f"Tamanho divergente: {caminho}.")
        esperado = item.get("sha256")
        if not isinstance(esperado, str) or len(esperado) != 64:
            raise ArtefatoNaoPublicavelError(f"SHA-256 invalido para {caminho}.")
        if sha256_arquivo(caminho) != esperado:
            raise ArtefatoNaoPublicavelError(f"SHA-256 divergente: {caminho}.")
    obrigatorios = set(ARQUIVOS_COMUNS_OBRIGATORIOS)
    if (pasta / "status_execucao.json").is_file():
        status = _carregar_json(pasta / "status_execucao.json")
        if status.get("tarefa") == TAREFA_HORARIA:
            obrigatorios.add("vinculo_artefatos_oficiais.json")
        else:
            obrigatorios |= {"variabilidade_sementes.csv", "auditoria_entradas.csv"}
    faltantes = obrigatorios - declarados
    if faltantes:
        raise ArtefatoNaoPublicavelError(
            f"Arquivos obrigatorios nao manifestados em {pasta}: {sorted(faltantes)}."
        )


def _validar_metricas_basicas(
    quadro: pd.DataFrame,
    *,
    entrada: EntradaValidada | None,
    caminho: Path,
    local: bool,
) -> tuple[str, str]:
    faltantes = COLUNAS_METRICAS - set(quadro.columns)
    if local:
        faltantes |= {"localidade"} - set(quadro.columns)
    else:
        faltantes |= {"N_localidades", "agregacao"} - set(quadro.columns)
    if faltantes:
        raise ArtefatoNaoPublicavelError(
            f"Colunas ausentes em {caminho}: {sorted(faltantes)}."
        )
    tarefas = quadro["tarefa"].dropna().astype(str).unique()
    resolucoes = quadro["resolucao"].dropna().astype(str).unique()
    if len(tarefas) != 1 or len(resolucoes) != 1:
        raise ArtefatoNaoPublicavelError(f"Tarefa/resolucao ambiguas em {caminho}.")
    if entrada is not None and tarefas[0] != entrada.tarefa:
        raise ArtefatoNaoPublicavelError(
            f"Status ({entrada.tarefa}) e metricas ({tarefas[0]}) divergem em {caminho}."
        )
    for coluna in ("MAE_wm2", "RMSE_wm2"):
        valores = pd.to_numeric(quadro[coluna], errors="coerce")
        if valores.isna().any() or (~np.isfinite(valores)).any() or (valores < 0).any():
            raise ArtefatoNaoPublicavelError(f"Valores invalidos em {caminho}:{coluna}.")
    for coluna in ("N_origens", "N_pontos", "horizonte"):
        valores = pd.to_numeric(quadro[coluna], errors="coerce")
        if valores.isna().any() or (valores < 1).any():
            raise ArtefatoNaoPublicavelError(f"Contagens invalidas em {caminho}:{coluna}.")
    return str(tarefas[0]), str(resolucoes[0])


def validar_pasta_tarefa(pasta: str | Path) -> EntradaValidada:
    raiz = Path(pasta)
    if not raiz.is_dir():
        raise ArtefatoNaoPublicavelError(f"Pasta de tarefa ausente: {raiz}.")
    status = _carregar_json(raiz / "status_execucao.json")
    _validar_status(status, raiz)
    _validar_contrato(raiz, status)
    manifesto = _carregar_json(raiz / "manifesto_artefatos.json")
    _validar_manifesto(raiz, manifesto)
    macro = pd.read_csv(raiz / "metricas_macro.csv")
    tarefa, resolucao = _validar_metricas_basicas(
        macro, entrada=None, caminho=raiz / "metricas_macro.csv", local=False
    )
    if tarefa != status.get("tarefa"):
        raise ArtefatoNaoPublicavelError(
            f"Status ({status.get('tarefa')}) e metricas ({tarefa}) divergem em {raiz}."
        )
    entrada = EntradaValidada(raiz, tarefa, resolucao, status, manifesto)
    local = pd.read_csv(raiz / "metricas_por_localidade.csv")
    _validar_metricas_basicas(
        local, entrada=entrada, caminho=raiz / "metricas_por_localidade.csv", local=True
    )
    return entrada


def descobrir_pastas_tarefa(caminhos: Iterable[str | Path]) -> list[Path]:
    encontrados: list[Path] = []
    for bruto in caminhos:
        caminho = Path(bruto)
        if (caminho / "status_execucao.json").is_file():
            encontrados.append(caminho)
            continue
        if caminho.is_dir():
            encontrados.extend(
                filho
                for filho in sorted(caminho.iterdir())
                if filho.is_dir()
                and (filho / "status_execucao.json").is_file()
                and (filho / "manifesto_artefatos.json").is_file()
            )
    unicos: dict[Path, Path] = {}
    for caminho in encontrados:
        unicos[caminho.resolve()] = caminho
    if not unicos:
        raise ArtefatoNaoPublicavelError("Nenhuma pasta de tarefa foi encontrada.")
    return [unicos[chave] for chave in sorted(unicos, key=str)]


def _selecionar_estimativas_publicacao(
    quadro: pd.DataFrame,
    entrada: EntradaValidada,
    *,
    local: bool,
) -> pd.DataFrame:
    base = quadro.loc[
        quadro["particao"] == "teste_2024"
    ].copy()
    if base.empty:
        raise ArtefatoNaoPublicavelError(
            f"{entrada.tarefa} nao contem metricas de teste_2024."
        )
    chaves = ["tarefa", "resolucao", "tipo_horizonte", "horizonte", "modelo"]
    if local:
        chaves.append("localidade")
    selecionadas: list[pd.DataFrame] = []
    for identificador, grupo in base.groupby(chaves, dropna=False, sort=True):
        modelo = str(identificador[4])
        ensemble = grupo.loc[grupo["tipo_estimativa"] == "ensemble"]
        deterministica = grupo.loc[grupo["tipo_estimativa"] == "deterministica"]
        sementes = grupo.loc[grupo["tipo_estimativa"] == "semente"]
        if not ensemble.empty:
            if len(ensemble) != 1:
                raise ArtefatoNaoPublicavelError(
                    f"Ensemble duplicado para {identificador} em {entrada.tarefa}."
                )
            efetivas = tuple(sorted(pd.to_numeric(sementes["semente"]).astype(int).unique()))
            if modelo in MODELOS_APRENDIDOS and efetivas != SEMENTES_CANONICAS:
                raise ArtefatoNaoPublicavelError(
                    f"Ensemble {modelo}/{entrada.tarefa} sem as cinco sementes canonicas."
                )
            escolhida = ensemble.copy()
            escolhida["N_sementes"] = len(efetivas)
        elif not deterministica.empty:
            if len(deterministica) != 1:
                raise ArtefatoNaoPublicavelError(
                    f"Estimativa deterministica duplicada para {identificador}."
                )
            escolhida = deterministica.copy()
            escolhida["N_sementes"] = pd.NA
        elif entrada.uma_semente and not sementes.empty:
            semente_esperada = int(entrada.status["semente"])
            escolhida = sementes.loc[
                pd.to_numeric(sementes["semente"]).astype(int) == semente_esperada
            ].copy()
            if len(escolhida) != 1:
                raise ArtefatoNaoPublicavelError(
                    f"Extensao horaria ambigua para {identificador}."
                )
            escolhida["N_sementes"] = 1
        else:
            raise ArtefatoNaoPublicavelError(
                f"Nao ha estimativa publicavel para {identificador}."
            )
        selecionadas.append(escolhida)
    resultado = pd.concat(selecionadas, ignore_index=True)
    return resultado


def construir_desempenho_macro(entradas: Sequence[EntradaValidada]) -> pd.DataFrame:
    tabelas: list[pd.DataFrame] = []
    for entrada in entradas:
        bruto = pd.read_csv(entrada.pasta / "metricas_macro.csv")
        _validar_metricas_basicas(
            bruto,
            entrada=entrada,
            caminho=entrada.pasta / "metricas_macro.csv",
            local=False,
        )
        tabela = _selecionar_estimativas_publicacao(bruto, entrada, local=False)
        tabela["carater_tarefa"] = (
            "exploratorio"
            if entrada.status.get("carater_exploratorio") is True
            else "principal"
        )
        tabela["limitacao_sementes"] = np.where(
            tabela["tipo_estimativa"] == "deterministica",
            "nao_aplicavel_modelo_deterministico",
            entrada.limitacao_sementes,
        )
        tabelas.append(tabela)
    desempenho = pd.concat(tabelas, ignore_index=True)
    desempenho["semente"] = pd.to_numeric(
        desempenho["semente"], errors="coerce"
    ).astype("Int64")
    desempenho["N_sementes"] = pd.to_numeric(
        desempenho["N_sementes"], errors="coerce"
    ).astype("Int64")
    desempenho["posicao_MAE"] = (
        desempenho.groupby(["tarefa", "tipo_horizonte", "horizonte"])["MAE_wm2"]
        .rank(method="min", ascending=True)
        .astype("Int64")
    )
    colunas = [
        "tarefa",
        "resolucao",
        "carater_tarefa",
        "tipo_horizonte",
        "horizonte",
        "posicao_MAE",
        "modelo",
        "tipo_estimativa",
        "semente",
        "N_sementes",
        "limitacao_sementes",
        "N_localidades",
        "N_origens",
        "N_pontos",
        "MAE_wm2",
        "RMSE_wm2",
        "nRMSE",
        "R2",
        "agregacao",
    ]
    return desempenho[colunas].sort_values(
        [
            "tarefa",
            "tipo_horizonte",
            "horizonte",
            "MAE_wm2",
            "RMSE_wm2",
            "modelo",
        ],
        kind="mergesort",
        ignore_index=True,
    )


def construir_comparacao_timesnet_dilatedrnn(
    entradas: Sequence[EntradaValidada],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    tabelas: list[pd.DataFrame] = []
    for entrada in entradas:
        bruto = pd.read_csv(entrada.pasta / "metricas_por_localidade.csv")
        _validar_metricas_basicas(
            bruto,
            entrada=entrada,
            caminho=entrada.pasta / "metricas_por_localidade.csv",
            local=True,
        )
        tabelas.append(_selecionar_estimativas_publicacao(bruto, entrada, local=True))
    base = pd.concat(tabelas, ignore_index=True)
    base = base.loc[base["modelo"].isin(MODELOS_COMPARADOS)].copy()
    chaves = ["tarefa", "resolucao", "tipo_horizonte", "horizonte", "localidade"]
    pivot = base.pivot(index=chaves, columns="modelo", values="MAE_wm2").reset_index()
    faltantes = set(MODELOS_COMPARADOS) - set(pivot.columns)
    if faltantes or pivot[list(MODELOS_COMPARADOS)].isna().any().any():
        raise ArtefatoNaoPublicavelError(
            f"Comparacao local incompleta; modelos ausentes: {sorted(faltantes)}."
        )
    pivot = pivot.rename(
        columns={
            "TimesNet": "MAE_timesnet_wm2",
            "DilatedRNN": "MAE_dilatedrnn_wm2",
        }
    )
    pivot["diferenca_MAE_timesnet_menos_dilatedrnn_wm2"] = (
        pivot["MAE_timesnet_wm2"] - pivot["MAE_dilatedrnn_wm2"]
    )
    diferenca = pivot["diferenca_MAE_timesnet_menos_dilatedrnn_wm2"]
    empate = np.isclose(diferenca, 0.0, rtol=0.0, atol=TOLERANCIA_EMPATE_WM2)
    pivot["vencedor_local_MAE"] = np.select(
        [empate, diferenca < 0], ["Empate", "TimesNet"], default="DilatedRNN"
    )
    pivot["unidade_pareamento"] = "localidade"
    pivot["janelas_alvo_sobrepostas"] = pivot["tarefa"] != "monthly_1"
    pivot["inferencia"] = np.where(
        pivot["janelas_alvo_sobrepostas"],
        "descritiva;janelas_alvo_sobrepostas_nao_tratadas_como_iid",
        "descritiva;origens_mensais_de_um_passo_sem_sobreposicao_de_alvos",
    )
    pivot = pivot.sort_values(chaves, ignore_index=True)

    linhas: list[dict[str, object]] = []
    agrupamento = ["tarefa", "resolucao", "tipo_horizonte", "horizonte"]
    for valores, grupo in pivot.groupby(agrupamento, sort=True):
        diferencas = grupo["diferenca_MAE_timesnet_menos_dilatedrnn_wm2"]
        linha = dict(zip(agrupamento, valores, strict=True))
        sobrepostas = str(linha["tarefa"]) != "monthly_1"
        linha.update(
            {
                "N_localidades": int(grupo["localidade"].nunique()),
                "diferenca_MAE_media_wm2": float(diferencas.mean()),
                "diferenca_MAE_mediana_wm2": float(diferencas.median()),
                "vitorias_locais_timesnet": int(
                    (grupo["vencedor_local_MAE"] == "TimesNet").sum()
                ),
                "vitorias_locais_dilatedrnn": int(
                    (grupo["vencedor_local_MAE"] == "DilatedRNN").sum()
                ),
                "empates_locais": int((grupo["vencedor_local_MAE"] == "Empate").sum()),
                "unidade_pareamento": "localidade",
                "janelas_alvo_sobrepostas": sobrepostas,
                "inferencia": (
                    "descritiva;janelas_alvo_sobrepostas_nao_tratadas_como_iid"
                    if sobrepostas
                    else "descritiva;origens_mensais_de_um_passo_sem_sobreposicao_de_alvos"
                ),
            }
        )
        linhas.append(linha)
    return pivot, pd.DataFrame(linhas).sort_values(
        ["tarefa", "horizonte"], ignore_index=True
    )


def construir_variabilidade_sementes(
    entradas: Sequence[EntradaValidada],
) -> pd.DataFrame:
    linhas: list[dict[str, object]] = []
    chaves = ["tarefa", "resolucao", "tipo_horizonte", "horizonte", "modelo"]
    for entrada in entradas:
        macro = pd.read_csv(entrada.pasta / "metricas_macro.csv")
        sementes = macro.loc[
            (macro["particao"] == "teste_2024")
            & (macro["tipo_estimativa"] == "semente")
        ].copy()
        for valores, grupo in sementes.groupby(chaves, sort=True):
            seeds = tuple(sorted(pd.to_numeric(grupo["semente"]).astype(int).unique()))
            esperado = (42,) if entrada.uma_semente else SEMENTES_CANONICAS
            if seeds != esperado:
                raise ArtefatoNaoPublicavelError(
                    f"Conjunto de sementes incompleto em {valores}: {seeds}."
                )
            linha = dict(zip(chaves, valores, strict=True))
            linha["N_sementes"] = len(seeds)
            linha["sementes"] = ";".join(map(str, seeds))
            linha["limitacao_sementes"] = entrada.limitacao_sementes
            for metrica in ("MAE_wm2", "RMSE_wm2", "nRMSE", "R2"):
                serie = pd.to_numeric(grupo[metrica], errors="coerce")
                linha[f"{metrica}_media"] = float(serie.mean())
                linha[f"{metrica}_desvio_padrao"] = (
                    float(serie.std(ddof=1)) if len(serie) > 1 else pd.NA
                )
                linha[f"{metrica}_minimo"] = float(serie.min())
                linha[f"{metrica}_maximo"] = float(serie.max())
            linhas.append(linha)
    if not linhas:
        raise ArtefatoNaoPublicavelError("Nenhuma estimativa por semente foi encontrada.")
    return pd.DataFrame(linhas).sort_values(
        ["tarefa", "horizonte", "modelo"], ignore_index=True
    )


def _coagir_booleano(serie: pd.Series, nome: str) -> pd.Series:
    mapa = {
        True: True,
        False: False,
        1: True,
        0: False,
        "true": True,
        "false": False,
        "1": True,
        "0": False,
    }
    convertido = serie.map(
        lambda x: mapa.get(x if isinstance(x, (bool, int)) else str(x).casefold())
    )
    if convertido.isna().any():
        raise ArtefatoNaoPublicavelError(f"Booleano invalido no contexto NASA: {nome}.")
    return convertido.astype(bool)


def _resolver_arquivo_proveniencia(texto: str, manifesto: Path) -> Path | None:
    caminho = Path(texto)
    if caminho.is_absolute():
        return caminho if caminho.is_file() else None
    candidatos = [Path.cwd() / caminho]
    candidatos.extend(ancestral / caminho for ancestral in manifesto.parent.parents)
    for candidato in candidatos:
        if candidato.is_file():
            return candidato
    return None


def validar_contexto_nasa(
    caminho_csv: str | Path,
    caminho_manifesto: str | Path,
) -> tuple[pd.DataFrame, dict[str, object]]:
    csv = Path(caminho_csv)
    manifesto_path = Path(caminho_manifesto)
    manifesto = _carregar_json(manifesto_path)
    if manifesto.get("sha256_csv") != sha256_arquivo(csv):
        raise ArtefatoNaoPublicavelError("SHA-256 do CSV NASA POWER diverge do manifesto.")
    parametros = set(manifesto.get("parametros", []))
    esperados = {
        "PRECTOTCORR",
        "CLOUD_AMT",
        "ALLSKY_SFC_SW_DWN",
        "CLRSKY_SFC_SW_DWN",
    }
    if parametros != esperados:
        raise ArtefatoNaoPublicavelError(
            f"Parametros NASA POWER divergentes: {sorted(parametros)}."
        )
    if manifesto.get("uso_no_modelo") is not False:
        raise ArtefatoNaoPublicavelError(
            "O contexto NASA deve ser declarado como pos-hoc e fora do modelo."
        )
    criterios = manifesto.get("criterios_predeclarados")
    if not isinstance(criterios, dict):
        raise ArtefatoNaoPublicavelError("Manifesto NASA sem criterios predeclarados.")
    limiar_chuva = float(criterios.get("chuva_relevante_mm_dia", math.nan))
    limiar_nuvens = float(criterios.get("muito_nublado_percentual", math.nan))
    if not math.isfinite(limiar_chuva) or not math.isfinite(limiar_nuvens):
        raise ArtefatoNaoPublicavelError("Limiares meteorologicos invalidos.")
    quadro = pd.read_csv(csv)
    faltantes = COLUNAS_CONTEXTO - set(quadro.columns)
    if faltantes:
        raise ArtefatoNaoPublicavelError(
            f"Colunas ausentes no contexto NASA: {sorted(faltantes)}."
        )
    if manifesto.get("linhas") != len(quadro):
        raise ArtefatoNaoPublicavelError("Quantidade de linhas NASA diverge do manifesto.")
    quadro["data_local"] = pd.to_datetime(quadro["data_local"], errors="coerce")
    if quadro["data_local"].isna().any():
        raise ArtefatoNaoPublicavelError("Datas invalidas no contexto NASA.")
    if not (quadro["time_standard"].astype(str) == "LST").all():
        raise ArtefatoNaoPublicavelError("Contexto NASA deve usar time_standard=LST.")
    for coluna in ("precipitacao_corrigida_mm_dia", "nebulosidade_percentual"):
        valores = pd.to_numeric(quadro[coluna], errors="coerce")
        if valores.isna().any() or (~np.isfinite(valores)).any():
            raise ArtefatoNaoPublicavelError(
                f"Contexto NASA sem medicao finita para classificar {coluna}."
            )
        quadro[coluna] = valores
    for coluna in ("chuva_relevante", "muito_nublado", "condicao_adversa_independente"):
        quadro[coluna] = _coagir_booleano(quadro[coluna], coluna)
    chuva = pd.to_numeric(
        quadro["precipitacao_corrigida_mm_dia"], errors="coerce"
    ) >= limiar_chuva
    nublado = pd.to_numeric(quadro["nebulosidade_percentual"], errors="coerce") >= limiar_nuvens
    if not chuva.equals(quadro["chuva_relevante"]):
        raise ArtefatoNaoPublicavelError("Indicador de chuva diverge de PRECTOTCORR.")
    if not nublado.equals(quadro["muito_nublado"]):
        raise ArtefatoNaoPublicavelError("Indicador de nuvens diverge de CLOUD_AMT.")
    if not (chuva | nublado).equals(quadro["condicao_adversa_independente"]):
        raise ArtefatoNaoPublicavelError("Indicador adverso NASA e inconsistente.")
    quadro["_local_key"] = quadro["localidade"].map(_slug)
    quadro["_data_key"] = quadro["data_local"].dt.strftime("%Y-%m-%d")
    if quadro.duplicated(["_local_key", "_data_key"]).any():
        raise ArtefatoNaoPublicavelError("Contexto NASA possui local/data duplicado.")
    for consulta in manifesto.get("consultas", []):
        if not isinstance(consulta, dict):
            raise ArtefatoNaoPublicavelError("Consulta invalida no manifesto NASA.")
        cache = _resolver_arquivo_proveniencia(
            str(consulta.get("arquivo_cache", "")), manifesto_path
        )
        if cache is None:
            raise ArtefatoNaoPublicavelError(
                f"Cache NASA manifestado nao encontrado: {consulta.get('arquivo_cache')}."
            )
        if sha256_arquivo(cache) != consulta.get("sha256"):
            raise ArtefatoNaoPublicavelError(f"SHA-256 divergente no cache NASA: {cache}.")
    return quadro, manifesto


def _esquema_previsoes(entrada: EntradaValidada) -> EsquemaPrevisoes:
    caminho = entrada.pasta / "previsoes_teste.csv.gz"
    colunas = set(pd.read_csv(caminho, nrows=0).columns)
    if entrada.uma_semente:
        mapa = {
            "particao": "particao",
            "localidade": "localidade",
            "origem": "origem_utc",
            "alvo_local": "timestamp_alvo_local_fixo",
            "passo": "passo_h",
            "real": "ghi_real_wm2",
            "timesnet": "previsao_pos_timesnet_wm2",
            "dilatedrnn": "previsao_pos_dilatedrnn_wm2",
        }
        elevacao = "elevacao_solar_graus" if "elevacao_solar_graus" in colunas else None
        diurno = "periodo_diurno" if "periodo_diurno" in colunas else None
    else:
        mapa = {
            "particao": "particao",
            "localidade": "localidade",
            "origem": "origem",
            "alvo_local": "data_alvo",
            "passo": "passo",
            "real": "ghi_real_wm2",
            "timesnet": "previsao_pos_timesnet_ensemble_wm2",
            "dilatedrnn": "previsao_pos_dilatedrnn_ensemble_wm2",
        }
        elevacao = None
        diurno = None
    faltantes = set(mapa.values()) - colunas
    if faltantes:
        raise ArtefatoNaoPublicavelError(
            f"Previsoes {entrada.tarefa} sem colunas publicaveis: {sorted(faltantes)}."
        )
    opcionais = tuple(x for x in (elevacao, diurno) if x is not None)
    return EsquemaPrevisoes(
        caminho=caminho,
        colunas_leitura=tuple(mapa.values()) + opcionais,
        elevacao=elevacao,
        periodo_diurno=diurno,
        **mapa,
    )


def _iterar_previsoes_normalizadas(
    entrada: EntradaValidada,
    *,
    chunksize: int,
) -> Iterator[pd.DataFrame]:
    esquema = _esquema_previsoes(entrada)
    for bruto in pd.read_csv(
        esquema.caminho,
        usecols=list(dict.fromkeys(esquema.colunas_leitura)),
        chunksize=chunksize,
    ):
        if not (bruto[esquema.particao].astype(str) == "teste_2024").all():
            raise ArtefatoNaoPublicavelError(
                f"Particao estranha em {esquema.caminho}; esperado teste_2024."
            )
        alvo = pd.to_datetime(bruto[esquema.alvo_local], errors="coerce")
        if alvo.isna().any():
            raise ArtefatoNaoPublicavelError(f"Alvos temporais invalidos em {esquema.caminho}.")
        numericas: dict[str, pd.Series] = {}
        for destino, origem in (
            ("passo", esquema.passo),
            ("ghi_real_wm2", esquema.real),
            ("previsao_timesnet_wm2", esquema.timesnet),
            ("previsao_dilatedrnn_wm2", esquema.dilatedrnn),
        ):
            numericas[destino] = pd.to_numeric(bruto[origem], errors="coerce")
        if any(serie.isna().any() or (~np.isfinite(serie)).any() for serie in numericas.values()):
            raise ArtefatoNaoPublicavelError(f"Previsoes nao finitas em {esquema.caminho}.")
        normalizado = pd.DataFrame(
            {
                "tarefa": entrada.tarefa,
                "resolucao": entrada.resolucao,
                "limitacao_sementes": entrada.limitacao_sementes,
                "localidade": bruto[esquema.localidade].astype(str),
                "origem": bruto[esquema.origem].astype(str),
                "data_hora_alvo_local": alvo.dt.strftime("%Y-%m-%d %H:%M:%S"),
                "data_local_nasa_power": alvo.dt.strftime("%Y-%m-%d"),
                **numericas,
            }
        )
        normalizado["passo"] = normalizado["passo"].astype(int)
        normalizado["_local_key"] = normalizado["localidade"].map(_slug)
        normalizado["_data_key"] = normalizado["data_local_nasa_power"]
        normalizado["arquivo_previsoes_entrada"] = caminho_portatil(esquema.caminho)
        if esquema.elevacao:
            normalizado["elevacao_solar_graus"] = pd.to_numeric(
                bruto[esquema.elevacao], errors="coerce"
            )
        if esquema.periodo_diurno:
            normalizado["periodo_diurno"] = _coagir_booleano(
                bruto[esquema.periodo_diurno], esquema.periodo_diurno
            )
        yield normalizado


def _horizontes_publicados(entrada: EntradaValidada) -> tuple[int, ...]:
    metricas = pd.read_csv(
        entrada.pasta / "metricas_macro.csv",
        usecols=["particao", "tipo_horizonte", "horizonte"],
    )
    valores = metricas.loc[
        (metricas["particao"] == "teste_2024")
        & (metricas["tipo_horizonte"] == "cumulativo"),
        "horizonte",
    ]
    horizontes = tuple(sorted(pd.to_numeric(valores).astype(int).unique()))
    if not horizontes:
        raise ArtefatoNaoPublicavelError(
            f"No cumulative test horizons were found for {entrada.tarefa}."
        )
    return horizontes


def _agregar_contrastes_por_origem(
    entrada: EntradaValidada,
    *,
    chunksize: int,
) -> tuple[pd.DataFrame, set[tuple[str, str]]]:
    """Aggregates absolute errors by site, forecast origin, and horizon."""

    parciais: list[pd.DataFrame] = []
    suporte_meteorologico: set[tuple[str, str]] = set()
    horizontes = _horizontes_publicados(entrada)
    for previsoes in _iterar_previsoes_normalizadas(entrada, chunksize=chunksize):
        if entrada.resolucao != "mensal":
            suporte_meteorologico.update(
                zip(previsoes["_local_key"], previsoes["_data_key"], strict=True)
            )
        previsoes = previsoes.assign(
            _erro_abs_timesnet=(
                previsoes["ghi_real_wm2"] - previsoes["previsao_timesnet_wm2"]
            ).abs(),
            _erro_abs_dilatedrnn=(
                previsoes["ghi_real_wm2"]
                - previsoes["previsao_dilatedrnn_wm2"]
            ).abs(),
        )
        chaves = [
            "tarefa",
            "resolucao",
            "limitacao_sementes",
            "localidade",
            "origem",
        ]
        for horizonte in horizontes:
            recorte = previsoes.loc[previsoes["passo"] <= horizonte]
            if recorte.empty:
                continue
            parcial = (
                recorte.groupby(chaves, as_index=False, sort=False)
                .agg(
                    soma_erro_abs_timesnet_wm2=("_erro_abs_timesnet", "sum"),
                    soma_erro_abs_dilatedrnn_wm2=("_erro_abs_dilatedrnn", "sum"),
                    N_pontos=("passo", "size"),
                    primeiro_alvo_local=("data_hora_alvo_local", "min"),
                    ultimo_alvo_local=("data_hora_alvo_local", "max"),
                )
            )
            parcial["horizonte"] = horizonte
            parciais.append(parcial)
    if not parciais:
        raise ArtefatoNaoPublicavelError(
            f"No forecast-origin contrasts could be computed for {entrada.tarefa}."
        )
    chaves_finais = [
        "tarefa",
        "resolucao",
        "limitacao_sementes",
        "localidade",
        "origem",
        "horizonte",
    ]
    agregado = (
        pd.concat(parciais, ignore_index=True)
        .groupby(chaves_finais, as_index=False, sort=False)
        .agg(
            soma_erro_abs_timesnet_wm2=("soma_erro_abs_timesnet_wm2", "sum"),
            soma_erro_abs_dilatedrnn_wm2=(
                "soma_erro_abs_dilatedrnn_wm2",
                "sum",
            ),
            N_pontos=("N_pontos", "sum"),
            primeiro_alvo_local=("primeiro_alvo_local", "min"),
            ultimo_alvo_local=("ultimo_alvo_local", "max"),
        )
    )
    agregado["MAE_timesnet_wm2"] = (
        agregado["soma_erro_abs_timesnet_wm2"] / agregado["N_pontos"]
    )
    agregado["MAE_dilatedrnn_wm2"] = (
        agregado["soma_erro_abs_dilatedrnn_wm2"] / agregado["N_pontos"]
    )
    agregado["ganho_timesnet_vs_dilatedrnn_wm2"] = (
        agregado["MAE_dilatedrnn_wm2"] - agregado["MAE_timesnet_wm2"]
    )
    return agregado.drop(
        columns=[
            "soma_erro_abs_timesnet_wm2",
            "soma_erro_abs_dilatedrnn_wm2",
        ]
    ), suporte_meteorologico


def _selecionar_extremo_global(
    contrastes: pd.DataFrame,
    *,
    maior: bool,
) -> dict[str, object]:
    coluna = "ganho_timesnet_vs_dilatedrnn_wm2"
    ordenado = contrastes.sort_values(
        [coluna, "tarefa", "localidade", "origem", "horizonte"],
        ascending=[not maior, True, True, True, True],
        kind="mergesort",
    )
    return ordenado.iloc[0].to_dict()


def _anexar_contexto_pos_hoc(
    caso: dict[str, object],
    *,
    entradas: Sequence[EntradaValidada],
    contexto: pd.DataFrame,
    chunksize: int,
) -> dict[str, object]:
    caso = dict(caso)
    caso["contexto_usado_na_selecao"] = False
    caso["alegacao_causal"] = False
    if caso["resolucao"] == "mensal":
        caso.update(
            {
                "contexto_meteorologico_disponivel": False,
                "motivo_contexto_indisponivel": (
                    "Daily weather is not assigned to a monthly irradiance target."
                ),
            }
        )
        return caso
    trajetoria = _trajetoria_caso(caso, entradas, chunksize=chunksize)
    trajetoria = trajetoria.loc[trajetoria["passo"] <= int(caso["horizonte"])]
    chaves = trajetoria[["_local_key", "_data_key"]].drop_duplicates()
    contexto_caso = chaves.merge(
        contexto,
        on=["_local_key", "_data_key"],
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    if not (contexto_caso["_merge"] == "both").all():
        raise ArtefatoNaoPublicavelError(
            "NASA POWER context is missing for a globally selected contrast case."
        )
    contexto_caso = contexto_caso.drop(columns="_merge")
    caso.update(
        {
            "contexto_meteorologico_disponivel": True,
            "N_dias_contexto": int(len(contexto_caso)),
            "datas_contexto_inicio": contexto_caso["_data_key"].min(),
            "datas_contexto_fim": contexto_caso["_data_key"].max(),
            "precipitacao_total_mm": float(
                contexto_caso["precipitacao_corrigida_mm_dia"].sum()
            ),
            "nebulosidade_media_percentual": float(
                contexto_caso["nebulosidade_percentual"].mean()
            ),
            "dias_com_chuva_relevante": int(
                contexto_caso["chuva_relevante"].sum()
            ),
            "dias_muito_nublados": int(contexto_caso["muito_nublado"].sum()),
            "dias_com_condicao_adversa": int(
                contexto_caso["condicao_adversa_independente"].sum()
            ),
            "condicao_adversa_independente": bool(
                contexto_caso["condicao_adversa_independente"].any()
            ),
            "fonte_contexto": "NASA POWER Daily API",
            "time_standard": "LST",
            "interpretacao_contexto": (
                "Post-hoc descriptive context only; no causal attribution."
            ),
        }
    )
    return caso


def _selecionar_caso_meteorologico_independente(
    contexto: pd.DataFrame,
    suporte: set[tuple[str, str]],
) -> dict[str, object] | None:
    if not suporte:
        return None
    chaves_suportadas = pd.DataFrame(
        sorted(suporte), columns=["_local_key", "_data_key"]
    )
    candidatos = contexto.merge(
        chaves_suportadas,
        on=["_local_key", "_data_key"],
        how="inner",
        validate="one_to_one",
    )
    candidatos = candidatos.loc[candidatos["condicao_adversa_independente"]]
    if candidatos.empty:
        return None
    escolhido = candidatos.sort_values(
        [
            "precipitacao_corrigida_mm_dia",
            "nebulosidade_percentual",
            "localidade",
            "data_local",
        ],
        ascending=[False, False, True, True],
        kind="mergesort",
    ).iloc[0]
    caso = escolhido.drop(labels=["_local_key", "_data_key"]).to_dict()
    caso.update(
        {
            "caso": "caso_meteorologico_independente",
            "data_local": pd.Timestamp(escolhido["data_local"]).strftime("%Y-%m-%d"),
            "regra_selecao": (
                "Among independently confirmed adverse dates with forecast support, "
                "maximize corrected precipitation; break ties by cloud amount, site, "
                "and date. Model errors are not consulted."
            ),
            "erros_modelos_usados_na_selecao": False,
            "alegacao_causal": False,
            "interpretacao_contexto": (
                "Descriptive meteorological example selected independently of errors."
            ),
        }
    )
    return caso


def selecionar_casos_contrastantes(
    entradas: Sequence[EntradaValidada],
    contexto: pd.DataFrame,
    manifesto_contexto: Mapping[str, object],
    *,
    chunksize: int = 200_000,
) -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    if chunksize < 1:
        raise ValueError("chunksize deve ser positivo.")
    tabelas: list[pd.DataFrame] = []
    suporte_meteorologico: set[tuple[str, str]] = set()
    for entrada in entradas:
        tabela, suporte = _agregar_contrastes_por_origem(
            entrada, chunksize=chunksize
        )
        tabelas.append(tabela)
        suporte_meteorologico |= suporte
    if not tabelas:
        raise ArtefatoNaoPublicavelError(
            "No forecast-origin contrasts are available for case selection."
        )
    contrastes = pd.concat(tabelas, ignore_index=True).sort_values(
        ["tarefa", "horizonte", "localidade", "origem"], ignore_index=True
    )
    ganho = _selecionar_extremo_global(contrastes, maior=True)
    deficit = _selecionar_extremo_global(contrastes, maior=False)
    ganho["caso"] = "maior_ganho_timesnet"
    deficit["caso"] = "maior_deficit_timesnet"
    regra_texto = (
        "For every site, forecast origin, and declared cumulative horizon, compute "
        "MAE(DilatedRNN)-MAE(TimesNet). Select the global maximum and minimum "
        "before joining weather context; break ties lexically by task, site, origin, "
        "and horizon."
    )
    for linha in (ganho, deficit):
        linha["universo_selecao"] = (
            "All available sites, forecast origins, and declared cumulative horizons; "
            "meteorology excluded from selection."
        )
        linha["regra_selecao"] = regra_texto
        valor = float(linha["ganho_timesnet_vs_dilatedrnn_wm2"])
        if linha["caso"] == "maior_ganho_timesnet":
            linha["interpretacao_extremo"] = (
                "Largest TimesNet gain" if valor >= 0 else "Smallest available deficit"
            )
        else:
            linha["interpretacao_extremo"] = (
                "Largest TimesNet deficit"
                if valor < 0
                else "Smallest available gain; no deficit was observed"
            )
    ganho = _anexar_contexto_pos_hoc(
        ganho, entradas=entradas, contexto=contexto, chunksize=chunksize
    )
    deficit = _anexar_contexto_pos_hoc(
        deficit, entradas=entradas, contexto=contexto, chunksize=chunksize
    )
    registros = [ganho, deficit]
    caso_meteorologico = _selecionar_caso_meteorologico_independente(
        contexto, suporte_meteorologico
    )
    if caso_meteorologico is not None:
        registros.append(caso_meteorologico)
    casos = pd.DataFrame(registros)
    colunas_frente = [
        "caso",
        "interpretacao_extremo",
        "universo_selecao",
        "regra_selecao",
        "tarefa",
        "resolucao",
        "limitacao_sementes",
        "localidade",
        "origem",
        "horizonte",
        "N_pontos",
        "primeiro_alvo_local",
        "ultimo_alvo_local",
        "MAE_timesnet_wm2",
        "MAE_dilatedrnn_wm2",
        "ganho_timesnet_vs_dilatedrnn_wm2",
    ]
    casos = casos[
        [c for c in colunas_frente if c in casos.columns]
        + [c for c in casos.columns if c not in colunas_frente]
    ]
    criterios = manifesto_contexto["criterios_predeclarados"]
    regra = {
        "versao": 2,
        "unidade_extremo": "site_forecast_origin_cumulative_horizon",
        "formula": "MAE(DilatedRNN)-MAE(TimesNet) within each origin/horizon",
        "maior_ganho": "global argmax before meteorological annotation",
        "maior_deficit": "global argmin before meteorological annotation",
        "desempate": "lexical order by task, site, origin, and horizon",
        "meteorologia_usada_na_selecao_dos_extremos": False,
        "ordem_operacoes": [
            "aggregate absolute errors by origin and cumulative horizon",
            "select global maximum and minimum model contrasts",
            "attach NASA POWER context post hoc when the temporal scale supports it",
        ],
        "adverso": criterios.get("adverso"),
        "limiar_chuva_mm_dia": criterios.get("chuva_relevante_mm_dia"),
        "limiar_muito_nublado_percentual": criterios.get(
            "muito_nublado_percentual"
        ),
        "parametros_contexto": manifesto_contexto.get("parametros"),
        "time_standard_contexto": "LST",
        "ghi_usado_para_classificar_chuva_ou_nuvens": False,
        "contexto_usado_no_modelo": False,
        "alegacao_causal": False,
        "caso_meteorologico_independente_disponivel": caso_meteorologico is not None,
        "regra_caso_meteorologico": (
            "maximize corrected precipitation among independently confirmed adverse "
            "NASA POWER dates with daily/hourly forecast support; model errors excluded"
        ),
        "observacao_mensal": (
            "Monthly contrasts remain eligible globally, but daily weather is not "
            "assigned to a selected monthly target."
        ),
        "N_origens_horizontes_avaliados": int(len(contrastes)),
    }
    return casos, regra, contrastes


def _hiperparametros_modelo(
    modelo: str,
    resolucao: str,
    documento: Mapping[str, object],
) -> dict[str, object]:
    configuracao = documento.get("configuracao", documento)
    if not isinstance(configuracao, Mapping):
        return {}
    prefixos = {
        "TimesNet": ("timesnet_",),
        "DilatedRNN": ("dilated_",),
        "LSTM": ("lstm_",),
        "XGBoost": ("xgb_",),
    }.get(modelo, ())
    comuns = {"taxa_aprendizado", "peso_decay"}
    if resolucao == "diaria":
        comuns |= {"batch_size_diario", "max_epocas_diario", "paciencia_diario"}
    elif resolucao == "mensal":
        comuns |= {"batch_size_mensal", "max_epocas_mensal", "paciencia_mensal"}
    elif resolucao == "horaria":
        comuns |= {"batch_size", "max_epocas", "paciencia"}
    selecionados = {
        str(chave): valor
        for chave, valor in configuracao.items()
        if str(chave) in comuns or any(str(chave).startswith(p) for p in prefixos)
    }
    if modelo == "DilatedRNN":
        for chave in (
            "dilatacoes",
            "unidades_por_camada",
            "unidades_densas",
            "embedding_localidade",
            "dropout",
            "batch_size",
            "max_epocas",
            "paciencia",
            "taxa_aprendizado",
        ):
            if chave in documento:
                selecionados[chave] = documento[chave]
    return selecionados


def construir_tabela_execucao(
    entradas: Sequence[EntradaValidada],
    desempenho: pd.DataFrame,
) -> pd.DataFrame:
    """Summarizes recorded training configuration without inventing measurements."""

    linhas: list[dict[str, object]] = []
    for entrada in entradas:
        epocas = pd.read_csv(entrada.pasta / "epocas_selecionadas.csv")
        metodo = _carregar_json(entrada.pasta / "hiperparametros_e_metodo.json")
        modelos = sorted(
            set(
                desempenho.loc[
                    desempenho["tarefa"] == entrada.tarefa, "modelo"
                ].unique()
            )
            & MODELOS_APRENDIDOS
        )
        for modelo in modelos:
            registros = (
                epocas.loc[epocas["modelo"].astype(str) == modelo].copy()
                if "modelo" in epocas.columns
                else pd.DataFrame()
            )
            if registros.empty:
                if modelo in MODELOS_APRENDIDOS and not entrada.uma_semente:
                    raise ArtefatoNaoPublicavelError(
                        f"Epocas/iteracoes ausentes para {modelo}/{entrada.tarefa}."
                    )
            parametros = _hiperparametros_modelo(modelo, entrada.resolucao, metodo)
            parametros_texto = (
                json.dumps(parametros, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                if parametros
                else "Not recorded in this task artifact"
            )
            coluna_epocas = next(
                (
                    nome
                    for nome in (
                        "epocas_selecionadas_em_2023",
                        "epocas_selecionadas",
                        "epocas",
                    )
                    if nome in registros.columns
                ),
                None,
            )
            valores_epocas = (
                pd.to_numeric(registros[coluna_epocas], errors="coerce").dropna()
                if coluna_epocas
                else pd.Series(dtype=float)
            )
            valores_epocas = valores_epocas.loc[valores_epocas > 0]
            if not valores_epocas.empty:
                resumo_epocas = (
                    f"min={int(valores_epocas.min())}; "
                    f"median={float(valores_epocas.median()):g}; "
                    f"max={int(valores_epocas.max())}"
                )
            elif modelo == "XGBoost":
                resumo_epocas = "Not applicable; tree count is a hyperparameter"
            else:
                resumo_epocas = "Not recorded in this task artifact"
            sementes = (
                sorted(pd.to_numeric(registros["semente"], errors="coerce").dropna().astype(int))
                if "semente" in registros.columns
                else []
            )
            linhas.append(
                {
                    "tarefa": entrada.tarefa,
                    "resolucao": entrada.resolucao,
                    "modelo": modelo,
                    "sementes_execucao": (
                        ";".join(map(str, sementes))
                        if sementes
                        else str(entrada.status.get("semente", "Not recorded"))
                    ),
                    "epocas_selecionadas_resumo": resumo_epocas,
                    "hiperparametros_declarados": parametros_texto,
                    "fonte_configuracao": (
                        "epocas_selecionadas.csv;hiperparametros_e_metodo.json"
                    ),
                    "limitacao_sementes": entrada.limitacao_sementes,
                }
            )
    return pd.DataFrame(linhas).sort_values(
        ["tarefa", "modelo"], ignore_index=True
    )


_CAMPOS_MEDICOES_COMPUTACIONAIS = {
    "trainable_parameter_count": (
        "N_parametros_treinaveis",
        "parametros_treinaveis",
        "numero_parametros",
    ),
    "training_runtime_seconds": (
        "tempo_treinamento_s",
        "duracao_treinamento_s",
    ),
    "inference_runtime_seconds": (
        "tempo_inferencia_s",
        "duracao_inferencia_s",
    ),
}


def detectar_medicoes_computacionais(
    entradas: Sequence[EntradaValidada],
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Returns only explicitly instrumented measurements and an audit declaration."""

    linhas: list[dict[str, object]] = []
    fontes_inspecionadas: list[str] = []
    disponibilidade: dict[str, dict[str, object]] = {}
    for metrica, candidatos in _CAMPOS_MEDICOES_COMPUTACIONAIS.items():
        disponibilidade[metrica] = {
            "available": False,
            "accepted_explicit_columns": list(candidatos),
            "policy": "not inferred from architecture, file size, epoch count, or timestamps",
        }
    for entrada in entradas:
        for nome_arquivo in ("epocas_selecionadas.csv", "historico_treinamento.csv"):
            caminho = entrada.pasta / nome_arquivo
            quadro = pd.read_csv(caminho)
            fontes_inspecionadas.append(caminho_portatil(caminho))
            for metrica, candidatos in _CAMPOS_MEDICOES_COMPUTACIONAIS.items():
                for coluna in candidatos:
                    if coluna not in quadro.columns:
                        continue
                    valores = pd.to_numeric(quadro[coluna], errors="coerce")
                    for indice in valores.loc[valores.notna()].index:
                        linhas.append(
                            {
                                "tarefa": entrada.tarefa,
                                "resolucao": entrada.resolucao,
                                "modelo": (
                                    quadro.at[indice, "modelo"]
                                    if "modelo" in quadro.columns
                                    else "Not recorded"
                                ),
                                "semente": (
                                    quadro.at[indice, "semente"]
                                    if "semente" in quadro.columns
                                    else pd.NA
                                ),
                                "medicao": metrica,
                                "valor": float(valores.at[indice]),
                                "unidade": (
                                    "count"
                                    if metrica == "trainable_parameter_count"
                                    else "s"
                                ),
                                "fonte": caminho_portatil(caminho),
                                "coluna_fonte": coluna,
                            }
                        )
                        disponibilidade[metrica]["available"] = True
    relatorio = {
        "versao": 1,
        "instrumentacao_computacional_disponivel": bool(linhas),
        "medicoes": disponibilidade,
        "fontes_inspecionadas": sorted(set(fontes_inspecionadas)),
        "declaracao": (
            "Runtime and trainable-parameter counts are omitted from article tables "
            "unless an explicit instrumented field is present."
        ),
    }
    return pd.DataFrame(linhas), relatorio


_CABECALHOS_ARTIGO = {
    "tarefa": "Task",
    "resolucao": "Resolution",
    "tipo_horizonte": "Horizon definition",
    "horizonte": "Horizon",
    "modelo": "Model",
    "posicao_MAE": "MAE rank",
    "N_sementes": "Seeds",
    "N_localidades": "Sites",
    "N_pontos": "Points",
    "MAE_wm2": "MAE (W/m2)",
    "RMSE_wm2": "RMSE (W/m2)",
    "nRMSE": "nRMSE",
    "R2": "R2",
    "MAE_timesnet_wm2": "TimesNet MAE (W/m2)",
    "MAE_dilatedrnn_wm2": "DilatedRNN MAE (W/m2)",
    "diferenca_MAE_timesnet_menos_dilatedrnn_wm2": (
        "MAE difference (W/m2)"
    ),
    "diferenca_MAE_media_wm2": "Mean MAE difference (W/m2)",
    "diferenca_MAE_mediana_wm2": "Median MAE difference (W/m2)",
    "vitorias_locais_timesnet": "TimesNet site wins",
    "vitorias_locais_dilatedrnn": "DilatedRNN site wins",
    "empates_locais": "Ties",
    "janelas_alvo_sobrepostas": "Overlapping targets",
    "localidade": "Site",
    "origem": "Forecast origin",
    "primeiro_alvo_local": "First target",
    "ultimo_alvo_local": "Last target",
    "ganho_timesnet_vs_dilatedrnn_wm2": "TimesNet gain (W/m2)",
    "interpretacao_extremo": "Contrast interpretation",
    "contexto_meteorologico_disponivel": "Weather context available",
    "precipitacao_total_mm": "Total precipitation (mm)",
    "nebulosidade_media_percentual": "Mean cloud amount (%)",
    "dias_com_condicao_adversa": "Adverse-context days",
    "data_local": "Local date",
    "precipitacao_corrigida_mm_dia": "Corrected precipitation (mm/day)",
    "nebulosidade_percentual": "Cloud amount (%)",
    "chuva_relevante": "Relevant precipitation",
    "muito_nublado": "Very cloudy",
    "condicao_adversa_independente": "Independent adverse condition",
    "interpretacao_contexto": "Interpretation",
    "sementes_execucao": "Execution seeds",
    "epocas_selecionadas_resumo": "Selected epochs",
    "hiperparametros_declarados": "Declared hyperparameters",
    "limitacao_sementes": "Seed limitation",
    "campo": "Field",
    "valor": "Value",
}

_VALORES_ARTIGO = {
    "horaria": "Hourly",
    "diaria": "Daily",
    "mensal": "Monthly",
    "cumulativo": "Cumulative",
    "lead_exato": "Exact lead",
    "Empate": "Tie",
    "maior_ganho_timesnet": "Largest TimesNet gain",
    "maior_deficit_timesnet": "Largest TimesNet deficit",
    "caso_meteorologico_independente": "Independent meteorological case",
}


def _tabela_desempenho_compacta(desempenho: pd.DataFrame) -> pd.DataFrame:
    base = desempenho.loc[desempenho["tipo_horizonte"] == "cumulativo"].copy()
    indice = ["tarefa", "resolucao", "horizonte"]
    tabela = base.pivot(index=indice, columns="modelo", values="MAE_wm2").reset_index()
    sementes = (
        base.loc[base["tipo_estimativa"] != "deterministica"]
        .groupby(indice, as_index=False)["N_sementes"]
        .max()
    )
    return tabela.merge(sementes, on=indice, how="left").sort_values(
        ["tarefa", "horizonte"], ignore_index=True
    )


def _tabela_variabilidade_compacta(variabilidade: pd.DataFrame) -> pd.DataFrame:
    base = variabilidade.loc[
        variabilidade["tipo_horizonte"] == "cumulativo"
    ].copy()

    def formatar(linha: pd.Series) -> str:
        media = float(linha["MAE_wm2_media"])
        desvio = pd.to_numeric(
            pd.Series([linha["MAE_wm2_desvio_padrao"]]), errors="coerce"
        ).iloc[0]
        if pd.isna(desvio):
            return f"{media:.2f} (one seed; SD unavailable)"
        return f"{media:.2f} (SD {float(desvio):.2f})"

    base["MAE_mean_SD"] = base.apply(formatar, axis=1)
    return (
        base.pivot(
            index=["tarefa", "resolucao", "horizonte"],
            columns="modelo",
            values="MAE_mean_SD",
        )
        .reset_index()
        .sort_values(["tarefa", "horizonte"], ignore_index=True)
    )


_LATEX = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}


def escapar_latex(valor: object) -> str:
    if pd.isna(valor):
        return "NA"
    if isinstance(valor, (float, np.floating)):
        if not math.isfinite(float(valor)):
            return "NA"
        return f"{float(valor):.4f}"
    if isinstance(valor, (int, np.integer)) and not isinstance(valor, bool):
        return str(int(valor))
    texto_original = str(valor)
    texto = _CABECALHOS_ARTIGO.get(
        texto_original, _VALORES_ARTIGO.get(texto_original, texto_original)
    )
    return "".join(_LATEX.get(caractere, caractere) for caractere in texto)


def _gravar_csv(quadro: pd.DataFrame, caminho: Path) -> None:
    quadro.to_csv(caminho, index=False, encoding="utf-8", na_rep="NA", lineterminator="\n")


def _gravar_latex(
    quadro: pd.DataFrame,
    caminho: Path,
    *,
    legenda: str,
    rotulo: str,
) -> None:
    alinhamento = "l" + "r" * max(0, len(quadro.columns) - 1)
    rotulo_seguro = rotulo.replace("_", "-")
    if not all(c.isalnum() or c in ":.-" for c in rotulo_seguro):
        raise ValueError(f"Rotulo LaTeX inseguro: {rotulo!r}.")
    linhas = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        f"\\caption{{{escapar_latex(legenda)}}}",
        f"\\label{{{rotulo_seguro}}}",
        r"\resizebox{\linewidth}{!}{%",
        f"\\begin{{tabular}}{{{alinhamento}}}",
        r"\toprule",
        " & ".join(escapar_latex(c) for c in quadro.columns) + r" \\",
        r"\midrule",
    ]
    for valores in quadro.itertuples(index=False, name=None):
        linhas.append(" & ".join(escapar_latex(v) for v in valores) + r" \\")
    linhas.extend(
        [r"\bottomrule", r"\end{tabular}%", r"}", r"\end{table}", ""]
    )
    caminho.write_text("\n".join(linhas), encoding="utf-8", newline="\n")


def _gravar_caso_latex(quadro: pd.DataFrame, caminho: Path, *, legenda: str, rotulo: str) -> None:
    registro = quadro.iloc[0]
    if registro.get("caso") == "caso_meteorologico_independente":
        preferidos = [
            "caso",
            "localidade",
            "data_local",
            "precipitacao_corrigida_mm_dia",
            "nebulosidade_percentual",
            "chuva_relevante",
            "muito_nublado",
            "condicao_adversa_independente",
            "interpretacao_contexto",
        ]
    else:
        preferidos = [
            "caso",
            "interpretacao_extremo",
            "tarefa",
            "resolucao",
            "localidade",
            "origem",
            "horizonte",
            "N_pontos",
            "MAE_timesnet_wm2",
            "MAE_dilatedrnn_wm2",
            "ganho_timesnet_vs_dilatedrnn_wm2",
            "contexto_meteorologico_disponivel",
            "precipitacao_total_mm",
            "nebulosidade_media_percentual",
            "dias_com_condicao_adversa",
            "interpretacao_contexto",
            "limitacao_sementes",
        ]
    campos = [
        campo
        for campo in preferidos
        if campo in quadro.columns and pd.notna(registro[campo])
    ]
    vertical = pd.DataFrame(
        {
            "campo": [_CABECALHOS_ARTIGO.get(campo, campo) for campo in campos],
            "valor": [registro[campo] for campo in campos],
        }
    )
    _gravar_latex(vertical, caminho, legenda=legenda, rotulo=rotulo)


def _salvar_figura(figura: plt.Figure, base: Path) -> None:
    figura.savefig(
        base.with_suffix(".png"),
        dpi=180,
        bbox_inches="tight",
        metadata={"Software": "artefatos_artigo_unificado.py"},
    )
    figura.savefig(
        base.with_suffix(".pdf"),
        bbox_inches="tight",
        metadata={
            "Creator": "artefatos_artigo_unificado.py",
            "CreationDate": None,
            "ModDate": None,
        },
    )
    plt.close(figura)


def _grafico_ranking(desempenho: pd.DataFrame, pasta: Path) -> None:
    desempenho = desempenho.loc[desempenho["tipo_horizonte"] == "cumulativo"].copy()
    tarefas = list(dict.fromkeys(desempenho["tarefa"].astype(str)))
    figura, eixos = plt.subplots(
        len(tarefas), 1, figsize=(9.0, max(3.2, 3.0 * len(tarefas))), squeeze=False
    )
    for eixo, tarefa in zip(eixos[:, 0], tarefas, strict=True):
        grupo = desempenho.loc[desempenho["tarefa"] == tarefa]
        for modelo, dados in grupo.groupby("modelo", sort=True):
            eixo.plot(
                dados["horizonte"],
                dados["posicao_MAE"],
                marker="o",
                linewidth=1.5,
                label=modelo,
            )
        limitacao = (
            " - single-seed extension"
            if "uma_semente" in " ".join(grupo["limitacao_sementes"])
            else ""
        )
        resolucao = _VALORES_ARTIGO.get(
            str(grupo["resolucao"].iloc[0]), str(grupo["resolucao"].iloc[0])
        )
        eixo.set_title(f"{tarefa} ({resolucao}){limitacao}")
        eixo.set_xlabel("Forecast horizon")
        eixo.set_ylabel("MAE rank (1 = best)")
        eixo.invert_yaxis()
        eixo.grid(True, alpha=0.25)
    eixos[0, 0].legend(ncol=4, fontsize=8, loc="best")
    figura.suptitle("Model ranking by task and cumulative forecast horizon")
    figura.tight_layout()
    _salvar_figura(figura, pasta / "ranking_por_tarefa")


def _grafico_variabilidade(variabilidade: pd.DataFrame, pasta: Path) -> None:
    variabilidade = variabilidade.loc[
        variabilidade["tipo_horizonte"] == "cumulativo"
    ].copy()
    tarefas = list(dict.fromkeys(variabilidade["tarefa"].astype(str)))
    figura, eixos = plt.subplots(
        len(tarefas), 1, figsize=(9.0, max(3.2, 3.0 * len(tarefas))), squeeze=False
    )
    for eixo, tarefa in zip(eixos[:, 0], tarefas, strict=True):
        grupo = variabilidade.loc[variabilidade["tarefa"] == tarefa]
        for modelo, dados in grupo.groupby("modelo", sort=True):
            y = pd.to_numeric(dados["MAE_wm2_media"])
            desvio = pd.to_numeric(dados["MAE_wm2_desvio_padrao"], errors="coerce")
            eixo.errorbar(
                dados["horizonte"],
                y,
                yerr=desvio.fillna(0.0),
                marker="o",
                capsize=3,
                linewidth=1.3,
                label=modelo,
            )
        if (grupo["N_sementes"] == 1).all():
            eixo.text(
                0.99,
                0.02,
                "Single seed: between-seed SD unavailable",
                transform=eixo.transAxes,
                ha="right",
                va="bottom",
                fontsize=8,
            )
        resolucao = _VALORES_ARTIGO.get(
            str(grupo["resolucao"].iloc[0]), str(grupo["resolucao"].iloc[0])
        )
        eixo.set_title(f"{tarefa} ({resolucao})")
        eixo.set_xlabel("Forecast horizon")
        eixo.set_ylabel("Macro MAE (W m$^{-2}$)")
        eixo.grid(True, alpha=0.25)
    eixos[0, 0].legend(ncol=4, fontsize=8, loc="best")
    figura.suptitle("Between-seed variability (mean and standard deviation)")
    figura.tight_layout()
    _salvar_figura(figura, pasta / "variabilidade_por_semente")


def _trajetoria_caso(
    caso: Mapping[str, object],
    entradas: Sequence[EntradaValidada],
    *,
    chunksize: int,
) -> pd.DataFrame:
    entrada = next(e for e in entradas if e.tarefa == caso["tarefa"])
    partes: list[pd.DataFrame] = []
    for quadro in _iterar_previsoes_normalizadas(entrada, chunksize=chunksize):
        recorte = quadro.loc[
            (quadro["localidade"] == caso["localidade"])
            & (quadro["origem"] == caso["origem"])
        ]
        if not recorte.empty:
            partes.append(recorte)
    if not partes:
        raise ArtefatoNaoPublicavelError("Nao foi possivel reconstruir a trajetoria do caso.")
    return pd.concat(partes, ignore_index=True).sort_values("passo", ignore_index=True)


def _grafico_casos(
    casos: pd.DataFrame,
    entradas: Sequence[EntradaValidada],
    pasta: Path,
    *,
    chunksize: int,
) -> None:
    casos = casos.loc[
        casos["caso"].isin(["maior_ganho_timesnet", "maior_deficit_timesnet"])
    ]
    if len(casos) != 2:
        raise ArtefatoNaoPublicavelError(
            "Exactly two globally selected model-contrast cases are required."
        )
    figura, eixos = plt.subplots(2, 1, figsize=(10.0, 7.0), squeeze=False)
    for eixo, (_, caso) in zip(eixos[:, 0], casos.iterrows(), strict=True):
        trajetoria = _trajetoria_caso(caso, entradas, chunksize=chunksize)
        trajetoria = trajetoria.loc[
            trajetoria["passo"] <= int(caso["horizonte"])
        ]
        x = pd.to_datetime(trajetoria["data_hora_alvo_local"])
        eixo.plot(x, trajetoria["ghi_real_wm2"], color="black", label="Observed")
        eixo.plot(x, trajetoria["previsao_timesnet_wm2"], label="TimesNet")
        eixo.plot(x, trajetoria["previsao_dilatedrnn_wm2"], label="DilatedRNN")
        if bool(caso.get("contexto_meteorologico_disponivel", False)):
            contexto = (
                "post-hoc adverse NASA POWER context"
                if bool(caso.get("condicao_adversa_independente", False))
                else "post-hoc non-adverse NASA POWER context"
            )
        else:
            contexto = "daily weather context not assigned"
        nome_caso = _VALORES_ARTIGO.get(str(caso["caso"]), str(caso["caso"]))
        eixo.set_title(
            f"{nome_caso}: {caso['localidade']}, "
            f"origin {caso['origem']}, horizon {int(caso['horizonte'])} - {contexto}"
        )
        eixo.set_ylabel("GHI (W m$^{-2}$)")
        eixo.grid(True, alpha=0.25)
    eixos[-1, 0].set_xlabel("Local target time")
    eixos[0, 0].legend(ncol=4, fontsize=8, loc="best")
    figura.tight_layout()
    _salvar_figura(figura, pasta / "previsoes_casos_contrastantes")


def _manifesto_saida(pasta: Path, gerado_em: str) -> dict[str, object]:
    arquivos = []
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file() or caminho.name == "manifesto_sha256.json":
            continue
        arquivos.append(
            {
                "arquivo": caminho.relative_to(pasta).as_posix(),
                "bytes": caminho.stat().st_size,
                "sha256": sha256_arquivo(caminho),
            }
        )
    return {
        "versao_esquema": 1,
        "gerado_em_utc": gerado_em,
        "algoritmo": "SHA-256",
        "N_arquivos": len(arquivos),
        "arquivos": arquivos,
        "observacao": "O manifesto nao inclui o proprio arquivo para evitar autorreferencia.",
    }


_ATRASOS_PROMOCAO_WINDOWS_S = (0.10, 0.25, 0.50, 1.00, 2.00)
_WINERRORS_BLOQUEIO_TRANSITORIO = {5, 32, 33}


def _promover_pasta_com_retry(temporaria: Path, destino: Path) -> None:
    """Promove uma pasta atomicamente, repetindo apenas bloqueios Windows conhecidos."""

    if destino.exists():
        raise FileExistsError(
            f"A pasta de saida ja existe e nao sera sobrescrita: {destino}."
        )
    for tentativa in range(len(_ATRASOS_PROMOCAO_WINDOWS_S) + 1):
        if destino.exists():
            raise FileExistsError(
                "A pasta de saida surgiu durante a promocao e nao sera "
                f"sobrescrita: {destino}."
            )
        try:
            os.replace(temporaria, destino)
            return
        except OSError as erro:
            winerror = getattr(erro, "winerror", None)
            esgotou = tentativa == len(_ATRASOS_PROMOCAO_WINDOWS_S)
            if winerror not in _WINERRORS_BLOQUEIO_TRANSITORIO or esgotou:
                raise
            time.sleep(_ATRASOS_PROMOCAO_WINDOWS_S[tentativa])


def gerar_artefatos_artigo_unificado(
    *,
    pastas_tarefas: Sequence[str | Path],
    caminho_contexto_nasa: str | Path,
    caminho_manifesto_contexto_nasa: str | Path,
    pasta_saida: str | Path,
    chunksize: int = 200_000,
) -> dict[str, object]:
    """Valida as entradas e gera todos os artefatos em uma pasta nova.

    A pasta final jamais e sobrescrita. A geracao ocorre numa pasta temporaria
    irma e so e promovida ao nome final depois do manifesto ser concluido.
    """

    if chunksize < 1:
        raise ValueError("chunksize deve ser positivo.")
    entradas = [validar_pasta_tarefa(p) for p in descobrir_pastas_tarefa(pastas_tarefas)]
    tarefas = [e.tarefa for e in entradas]
    if len(tarefas) != len(set(tarefas)):
        raise ArtefatoNaoPublicavelError(f"Tarefas duplicadas nas entradas: {tarefas}.")
    contexto, manifesto_contexto = validar_contexto_nasa(
        caminho_contexto_nasa, caminho_manifesto_contexto_nasa
    )
    desempenho = construir_desempenho_macro(entradas)
    comparacao_local, comparacao_resumo = construir_comparacao_timesnet_dilatedrnn(entradas)
    variabilidade = construir_variabilidade_sementes(entradas)
    casos, regra_casos, contrastes_origem = selecionar_casos_contrastantes(
        entradas, contexto, manifesto_contexto, chunksize=chunksize
    )
    configuracao_treinamento = construir_tabela_execucao(entradas, desempenho)
    medicoes_computacionais, disponibilidade_medicoes = (
        detectar_medicoes_computacionais(entradas)
    )

    destino = Path(pasta_saida)
    if destino.exists():
        raise FileExistsError(
            f"A pasta de saida ja existe e nao sera sobrescrita: {destino}."
        )
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporaria = destino.parent / f".{destino.name}.tmp-{uuid.uuid4().hex}"
    temporaria.mkdir()
    gerado_em = datetime.now(timezone.utc).isoformat()
    try:
        _gravar_csv(desempenho, temporaria / "desempenho_macro.csv")
        desempenho_tex = _tabela_desempenho_compacta(desempenho)
        _gravar_latex(
            desempenho_tex,
            temporaria / "desempenho_macro.tex",
            legenda=(
                "Macro test MAE by task and cumulative forecast horizon. "
                "Complete metrics and exact-lead results are provided in the CSV artifact."
            ),
            rotulo="tab:desempenho_macro_auditavel",
        )

        _gravar_csv(
            comparacao_local, temporaria / "comparacao_timesnet_dilatedrnn_por_localidade.csv"
        )
        _gravar_csv(
            comparacao_resumo, temporaria / "comparacao_timesnet_dilatedrnn_resumo.csv"
        )
        comparacao_resumo_tex = comparacao_resumo.loc[
            comparacao_resumo["tipo_horizonte"] == "cumulativo",
            [
                "tarefa",
                "resolucao",
                "horizonte",
                "N_localidades",
                "diferenca_MAE_media_wm2",
                "diferenca_MAE_mediana_wm2",
                "vitorias_locais_timesnet",
                "vitorias_locais_dilatedrnn",
                "empates_locais",
                "janelas_alvo_sobrepostas",
            ],
        ]
        _gravar_latex(
            comparacao_resumo_tex,
            temporaria / "comparacao_timesnet_dilatedrnn_resumo.tex",
            legenda=(
                "Descriptive paired comparison of TimesNet and DilatedRNN across sites. "
                "Overlapping target windows are not treated as independent observations."
            ),
            rotulo="tab:vitorias_timesnet_dilatedrnn",
        )

        _gravar_csv(variabilidade, temporaria / "variabilidade_sementes.csv")
        _gravar_latex(
            _tabela_variabilidade_compacta(variabilidade),
            temporaria / "variabilidade_sementes.tex",
            legenda=(
                "Macro test MAE across independent seeds (mean and standard deviation). "
                "Single-seed extensions are identified explicitly."
            ),
            rotulo="tab:variabilidade_sementes",
        )
        _gravar_csv(
            configuracao_treinamento,
            temporaria / "configuracao_treinamento.csv",
        )
        _gravar_latex(
            configuracao_treinamento[
                [
                    "tarefa",
                    "modelo",
                    "sementes_execucao",
                    "epocas_selecionadas_resumo",
                    "hiperparametros_declarados",
                ]
            ],
            temporaria / "configuracao_treinamento.tex",
            legenda=(
                "Recorded training configuration and selected epochs. Runtime and "
                "trainable-parameter counts are reported only when explicitly instrumented."
            ),
            rotulo="tab:configuracao_treinamento",
        )
        (temporaria / "disponibilidade_medicoes_computacionais.json").write_text(
            json.dumps(
                disponibilidade_medicoes,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if not medicoes_computacionais.empty:
            _gravar_csv(
                medicoes_computacionais,
                temporaria / "medicoes_computacionais.csv",
            )
            medicoes_resumo = (
                medicoes_computacionais.groupby(
                    ["tarefa", "resolucao", "modelo", "medicao", "unidade"],
                    as_index=False,
                    dropna=False,
                )["valor"]
                .agg(N_registros="size", minimo="min", mediana="median", maximo="max")
            )
            _gravar_latex(
                medicoes_resumo,
                temporaria / "medicoes_computacionais.tex",
                legenda=(
                    "Explicitly instrumented computational measurements. No values are "
                    "inferred from architecture, file size, epoch counts, or timestamps."
                ),
                rotulo="tab:medicoes_computacionais",
            )

        _gravar_csv(
            contrastes_origem,
            temporaria / "contrastes_por_origem_horizonte.csv",
        )

        for nome, legenda in (
            (
                "caso_maior_ganho_timesnet",
                "Largest global TimesNet gain relative to DilatedRNN",
            ),
            (
                "caso_maior_deficit_timesnet",
                "Largest global TimesNet deficit relative to DilatedRNN",
            ),
            (
                "caso_meteorologico_independente",
                "Meteorological case selected independently of model errors",
            ),
        ):
            caso = casos.loc[casos["caso"] == nome]
            if caso.empty:
                if nome == "caso_meteorologico_independente":
                    continue
                raise ArtefatoNaoPublicavelError(
                    f"Required model-contrast case is missing: {nome}."
                )
            _gravar_csv(caso, temporaria / f"{nome}.csv")
            _gravar_caso_latex(
                caso,
                temporaria / f"{nome}.tex",
                legenda=legenda,
                rotulo=f"tab:{nome}",
            )
        (temporaria / "regra_selecao_casos.json").write_text(
            json.dumps(regra_casos, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )

        _grafico_ranking(desempenho, temporaria)
        _grafico_variabilidade(variabilidade, temporaria)
        _grafico_casos(casos, entradas, temporaria, chunksize=chunksize)

        proveniencia = {
            "versao_esquema": 1,
            "gerado_em_utc": gerado_em,
            "gerador": {
                "arquivo": caminho_portatil(__file__),
                "sha256": sha256_arquivo(__file__),
            },
            "tarefas": [
                {
                    "tarefa": e.tarefa,
                    "resolucao": e.resolucao,
                    "pasta": caminho_portatil(e.pasta),
                    "sha256_status": sha256_arquivo(e.pasta / "status_execucao.json"),
                    "sha256_manifesto": sha256_arquivo(e.pasta / "manifesto_artefatos.json"),
                    "sha256_contrato": e.status["sha256_contrato"],
                    "limitacao_sementes": e.limitacao_sementes,
                }
                for e in entradas
            ],
            "contexto_nasa_power": {
                "csv": caminho_portatil(caminho_contexto_nasa),
                "sha256_csv": sha256_arquivo(caminho_contexto_nasa),
                "manifesto": caminho_portatil(caminho_manifesto_contexto_nasa),
                "sha256_manifesto": sha256_arquivo(caminho_manifesto_contexto_nasa),
                "uso": "pos_hoc;fora_do_modelo",
            },
            "ordenacao_desempenho": (
                "MAE crescente por tarefa/tipo_horizonte/horizonte; empate por RMSE/modelo"
            ),
            "inferencia_comparacao": "descritiva_pareada_por_localidade",
            "selecao_casos": {
                "unidade": regra_casos["unidade_extremo"],
                "meteorologia_usada_na_selecao_dos_extremos": False,
                "alegacao_causal": False,
            },
            "medicoes_computacionais": disponibilidade_medicoes["declaracao"],
        }
        (temporaria / "proveniencia_entradas.json").write_text(
            json.dumps(proveniencia, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        manifesto_saida = _manifesto_saida(temporaria, gerado_em)
        (temporaria / "manifesto_sha256.json").write_text(
            json.dumps(manifesto_saida, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        _promover_pasta_com_retry(temporaria, destino)
    except Exception:
        shutil.rmtree(temporaria, ignore_errors=True)
        raise
    return {
        "pasta_saida": str(destino),
        "tarefas": tarefas,
        "artefatos_manifestados": manifesto_saida["N_arquivos"],
        "limitacoes": [e.limitacao_sementes for e in entradas if e.uma_semente],
    }


__all__ = [
    "ArtefatoNaoPublicavelError",
    "EntradaValidada",
    "construir_comparacao_timesnet_dilatedrnn",
    "construir_desempenho_macro",
    "construir_tabela_execucao",
    "construir_variabilidade_sementes",
    "descobrir_pastas_tarefa",
    "escapar_latex",
    "gerar_artefatos_artigo_unificado",
    "selecionar_casos_contrastantes",
    "sha256_arquivo",
    "validar_contexto_nasa",
    "validar_pasta_tarefa",
]
