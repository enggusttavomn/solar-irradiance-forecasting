"""Figuras publicaveis do protocolo mensal global canonico.

O modulo recebe tabelas consolidadas de uma execucao completa.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib-cache-tcc")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


COR_DEEPNPTS = "#177245"
COR_COMPARACAO = "#D89B00"
COR_REAL = "#181818"
COR_INTERVALO = "#8BC5A6"
ROTULOS_MESES = (
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
)


def _estilo() -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.size": 8.5,
            "axes.labelsize": 8.5,
            "axes.titlesize": 9,
            "legend.fontsize": 7.5,
            "xtick.labelsize": 7.5,
            "ytick.labelsize": 7.5,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )


def _salvar(fig: plt.Figure, destino: str | Path) -> tuple[Path, Path]:
    base = Path(destino)
    if base.suffix:
        base = base.with_suffix("")
    base.parent.mkdir(parents=True, exist_ok=True)
    png = base.with_suffix(".png")
    pdf = base.with_suffix(".pdf")
    fig.savefig(png, dpi=300, bbox_inches="tight", facecolor="white")
    fig.savefig(pdf, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return png, pdf


def figura_ranking_mae(
    resumo_modelos: pd.DataFrame,
    destino: str | Path,
) -> tuple[Path, Path]:
    """Gera barras do macro-MAE, com desvio entre sementes quando existente."""

    obrigatorias = {"Modelo", "MAE_media_wm2", "MAE_dp_sementes_wm2"}
    faltantes = obrigatorias - set(resumo_modelos)
    if faltantes:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(faltantes))}")
    dados = resumo_modelos.sort_values("MAE_media_wm2", ascending=True).copy()
    if dados.empty or dados["Modelo"].duplicated().any():
        raise ValueError("O resumo deve conter exatamente uma linha por modelo.")
    numericas = dados[["MAE_media_wm2", "MAE_dp_sementes_wm2"]].to_numpy(dtype=float)
    if not np.isfinite(numericas).all() or (numericas < 0).any():
        raise ValueError("MAE e desvio devem ser finitos e nao negativos.")
    _estilo()
    fig, ax = plt.subplots(figsize=(4.6, 3.1))
    cores = [COR_DEEPNPTS if nome == "DeepNPTS" else "#6F7D8C" for nome in dados["Modelo"]]
    ax.barh(
        dados["Modelo"],
        dados["MAE_media_wm2"],
        xerr=dados["MAE_dp_sementes_wm2"],
        color=cores,
        edgecolor="white",
        capsize=2,
    )
    ax.invert_yaxis()
    ax.set_xlabel(r"MAE médio entre localidades (W/m$^2$)")
    ax.grid(axis="x", color="#D8D8D8", linewidth=0.5, alpha=0.75)
    deslocamento = max(float(dados["MAE_media_wm2"].max()) * 0.012, 0.15)
    limites_direitos = []
    for posicao, (valor, desvio) in enumerate(
        zip(
            dados["MAE_media_wm2"],
            dados["MAE_dp_sementes_wm2"],
            strict=True,
        )
    ):
        limite_direito = float(valor + desvio)
        limites_direitos.append(limite_direito)
        ax.text(
            limite_direito + deslocamento,
            posicao,
            f"{valor:.2f}".replace(".", ","),
            va="center",
        )
    ax.set_xlim(0, max(limites_direitos) * 1.16)
    return _salvar(fig, destino)


def figura_deepnpts_vs_melhor_concorrente(
    metricas_localidade: pd.DataFrame,
    destino: str | Path,
) -> tuple[Path, Path]:
    """Compara DeepNPTS ao concorrente de menor MAE em cada localidade."""

    obrigatorias = {"Localidade", "Modelo", "MAE_wm2"}
    faltantes = obrigatorias - set(metricas_localidade)
    if faltantes:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(faltantes))}")
    if metricas_localidade.duplicated(["Localidade", "Modelo"]).any():
        raise ValueError("As metricas devem ter uma linha por localidade e modelo.")
    if metricas_localidade.empty or not np.isfinite(
        metricas_localidade["MAE_wm2"].to_numpy(dtype=float)
    ).all():
        raise ValueError("As metricas por localidade devem ser finitas e nao vazias.")
    deep = metricas_localidade.loc[
        metricas_localidade["Modelo"] == "DeepNPTS", ["Localidade", "MAE_wm2"]
    ].rename(columns={"MAE_wm2": "DeepNPTS"})
    concorrentes = (
        metricas_localidade.loc[metricas_localidade["Modelo"] != "DeepNPTS"]
        .sort_values(["Localidade", "MAE_wm2"])
        .groupby("Localidade", as_index=False)
        .first()[["Localidade", "Modelo", "MAE_wm2"]]
        .rename(columns={"Modelo": "Concorrente", "MAE_wm2": "Melhor concorrente"})
    )
    localidades_esperadas = set(metricas_localidade["Localidade"])
    if set(deep["Localidade"]) != localidades_esperadas:
        raise ValueError("DeepNPTS deve possuir metrica em todas as localidades.")
    if set(concorrentes["Localidade"]) != localidades_esperadas:
        raise ValueError("Cada localidade deve possuir ao menos um concorrente.")
    dados = deep.merge(concorrentes, on="Localidade", validate="one_to_one")
    dados = dados.sort_values("DeepNPTS", ascending=True).reset_index(drop=True)
    posicoes = np.arange(len(dados))
    altura = 0.38
    _estilo()
    fig, ax = plt.subplots(figsize=(6.9, 3.65))
    ax.barh(posicoes - altura / 2, dados["DeepNPTS"], altura, color=COR_DEEPNPTS, label="DeepNPTS")
    ax.barh(
        posicoes + altura / 2,
        dados["Melhor concorrente"],
        altura,
        color=COR_COMPARACAO,
        label="Melhor concorrente local",
    )
    rotulos = [
        f"{local}\n({modelo})"
        for local, modelo in zip(dados["Localidade"], dados["Concorrente"], strict=True)
    ]
    ax.set_yticks(posicoes, rotulos)
    ax.invert_yaxis()
    ax.set_xlabel(r"MAE (W/m$^2$)")
    ax.grid(axis="x", color="#D8D8D8", linewidth=0.5, alpha=0.75)
    ax.legend(
        frameon=False,
        ncol=2,
        loc="lower center",
        bbox_to_anchor=(0.5, 1.01),
    )
    return _salvar(fig, destino)


def figura_serie_previsoes(
    previsoes: pd.DataFrame,
    localidade: str,
    modelo_comparacao: str,
    destino: str | Path,
) -> tuple[Path, Path]:
    """Plota GHI real, DeepNPTS e uma comparacao na janela final."""

    obrigatorias = {"data_alvo", "Localidade", "y_wm2", "DeepNPTS", modelo_comparacao}
    faltantes = obrigatorias - set(previsoes)
    if faltantes:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(faltantes))}")
    dados = previsoes.loc[previsoes["Localidade"] == localidade].copy()
    if dados.empty:
        raise ValueError(f"Localidade ausente: {localidade}")
    dados["data_alvo"] = pd.to_datetime(dados["data_alvo"])
    dados = dados.sort_values("data_alvo")
    if dados["data_alvo"].duplicated().any():
        raise ValueError("Ha datas duplicadas na serie de previsoes.")
    valores = dados[["y_wm2", "DeepNPTS", modelo_comparacao]].to_numpy(dtype=float)
    if not np.isfinite(valores).all():
        raise ValueError("A serie de previsoes deve conter apenas valores finitos.")
    _estilo()
    fig, ax = plt.subplots(figsize=(6.9, 3.25))
    posicoes = np.arange(len(dados))
    ax.plot(posicoes, dados["y_wm2"], "-o", color=COR_REAL, linewidth=1.5, markersize=3.2, label="GHI de referência")
    ax.plot(posicoes, dados[modelo_comparacao], "--s", color=COR_COMPARACAO, linewidth=1.2, markersize=2.8, label=modelo_comparacao)
    ax.plot(posicoes, dados["DeepNPTS"], "-^", color=COR_DEEPNPTS, linewidth=1.3, markersize=3.0, label="DeepNPTS")
    ax.set_ylabel(r"GHI média mensal (W/m$^2$)")
    ax.set_xlabel("Mês-alvo (2024)")
    ax.set_xticks(posicoes)
    ax.set_xticklabels(
        [ROTULOS_MESES[data.month - 1] for data in dados["data_alvo"]]
    )
    ax.margins(x=0.03)
    ax.grid(color="#D8D8D8", linewidth=0.5, alpha=0.75)
    ax.legend(frameon=False, ncol=3, loc="best")
    return _salvar(fig, destino)


def figura_intervalo_deepnpts(
    previsoes: pd.DataFrame,
    amostras_deepnpts: np.ndarray,
    localidade: str,
    destino: str | Path,
    quantis: Sequence[float] = (0.05, 0.95),
) -> tuple[Path, Path]:
    """Plota mediana e intervalo central do DeepNPTS em uma localidade."""

    obrigatorias = {"data_alvo", "Localidade", "y_wm2"}
    faltantes = obrigatorias - set(previsoes)
    if faltantes:
        raise ValueError(f"Colunas ausentes: {', '.join(sorted(faltantes))}")
    if len(quantis) != 2 or not 0 <= quantis[0] < quantis[1] <= 1:
        raise ValueError("quantis deve conter dois níveis ordenados em [0,1].")
    amostras = np.asarray(amostras_deepnpts, dtype=float)
    if (
        amostras.ndim != 2
        or amostras.shape[0] != len(previsoes)
        or amostras.shape[1] < 2
        or not np.isfinite(amostras).all()
    ):
        raise ValueError("amostras deve ter forma (linhas de previsoes, amostras).")
    mascara = previsoes["Localidade"].to_numpy() == localidade
    if not mascara.any():
        raise ValueError(f"Localidade ausente: {localidade}")
    dados = previsoes.loc[mascara].copy()
    dados["data_alvo"] = pd.to_datetime(dados["data_alvo"])
    if dados["data_alvo"].duplicated().any():
        raise ValueError("Ha datas duplicadas na serie de previsoes.")
    if not np.isfinite(dados["y_wm2"].to_numpy(dtype=float)).all():
        raise ValueError("A GHI observada deve conter apenas valores finitos.")
    ordem = np.argsort(dados["data_alvo"].to_numpy())
    dados = dados.iloc[ordem]
    sims = amostras[mascara][ordem]
    inferior, mediana, superior = np.quantile(
        sims, [quantis[0], 0.5, quantis[1]], axis=1
    )
    _estilo()
    fig, ax = plt.subplots(figsize=(6.9, 3.25))
    posicoes = np.arange(len(dados))
    ax.fill_between(posicoes, inferior, superior, color=COR_INTERVALO, alpha=0.42, label="Intervalo preditivo de 90%")
    ax.plot(posicoes, mediana, color=COR_DEEPNPTS, linewidth=1.4, label="Mediana DeepNPTS")
    ax.plot(posicoes, dados["y_wm2"], "-o", color=COR_REAL, linewidth=1.35, markersize=3.0, label="GHI de referência")
    ax.set_ylabel(r"GHI média mensal (W/m$^2$)")
    ax.set_xlabel("Mês-alvo (2024)")
    ax.set_xticks(posicoes)
    ax.set_xticklabels(
        [ROTULOS_MESES[data.month - 1] for data in dados["data_alvo"]]
    )
    ax.margins(x=0.03)
    ax.grid(color="#D8D8D8", linewidth=0.5, alpha=0.75)
    ax.legend(frameon=False, ncol=3, loc="best")
    return _salvar(fig, destino)


__all__ = [
    "figura_deepnpts_vs_melhor_concorrente",
    "figura_intervalo_deepnpts",
    "figura_ranking_mae",
    "figura_serie_previsoes",
]
