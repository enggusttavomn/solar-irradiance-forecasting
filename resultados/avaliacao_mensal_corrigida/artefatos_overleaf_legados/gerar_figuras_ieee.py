"""Gera as figuras do artigo IEEE a partir da avaliação mensal corrigida.

Não há números digitados manualmente: médias, intervalos de confiança e séries
de 2024 são lidos dos CSVs produzidos pelo protocolo reproduzível.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Evita depender de uma pasta de configuração gravável no diretório pessoal.
os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "matplotlib-figuras-ieee"),
)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RAIZ = Path(__file__).resolve().parents[2]
RESULTADOS = RAIZ / "resultados" / "avaliacao_mensal_corrigida"
PASTA_FIGURAS = RAIZ / "overlief" / "figuras"

COR_CLIMA = "#2666A8"
COR_VHP = "#A33D2B"
COR_MODELO = "#7C8793"
COR_REAL = "#202124"
COR_IC = "#515A64"

NOMES_MODELOS = {
    "Climatologia": "Climatologia",
    "MLP": "MLP",
    "XGBoost": "XGBoost",
    "VizinhosHistoricos": "VHP",
    "SazonalIngenuo": "Sazonal ingênuo",
    "Persistencia": "Persistência",
    "RNN": "RNN",
    "LSTM": "LSTM",
}


def configurar_estilo() -> None:
    """Configura dimensões e fontes compatíveis com uma coluna IEEE."""
    plt.rcParams.update(
        {
            "font.family": "DejaVu Serif",
            "font.size": 7.5,
            "axes.labelsize": 8,
            "xtick.labelsize": 7,
            "ytick.labelsize": 7,
            "legend.fontsize": 7,
            "axes.linewidth": 0.7,
            "figure.dpi": 150,
            "savefig.dpi": 300,
        }
    )


def decimal(valor: float, casas: int = 2) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def salvar(figura: plt.Figure, nome: str) -> None:
    PASTA_FIGURAS.mkdir(parents=True, exist_ok=True)
    figura.savefig(
        PASTA_FIGURAS / nome,
        bbox_inches="tight",
        pad_inches=0.03,
        facecolor="white",
    )
    plt.close(figura)


def gerar_mae_medio() -> None:
    """Plota MAE médio e IC95% bootstrap entre as dez localidades."""
    resumo = pd.read_csv(RESULTADOS / "resumo_modelos_mae.csv")
    resumo = resumo.loc[resumo["Metrica"] == "MAE_wm2"].copy()
    resumo = resumo.sort_values("Media").reset_index(drop=True)
    resumo["rotulo"] = resumo["Modelo"].map(NOMES_MODELOS)

    posicoes = np.arange(len(resumo))
    erros = np.vstack(
        [
            resumo["Media"] - resumo["IC95_inferior"],
            resumo["IC95_superior"] - resumo["Media"],
        ]
    )
    cores = [
        COR_CLIMA if modelo == "Climatologia" else COR_VHP if modelo == "VizinhosHistoricos" else COR_MODELO
        for modelo in resumo["Modelo"]
    ]

    figura, eixo = plt.subplots(figsize=(3.45, 2.75))
    eixo.barh(posicoes, resumo["Media"], color=cores, height=0.60, alpha=0.92)
    eixo.errorbar(
        resumo["Media"],
        posicoes,
        xerr=erros,
        fmt="none",
        ecolor=COR_IC,
        elinewidth=0.8,
        capsize=2.0,
        capthick=0.8,
    )
    eixo.set_yticks(posicoes, resumo["rotulo"])
    eixo.invert_yaxis()
    eixo.set_xlabel(r"MAE médio (W/m$^2$)")
    eixo.set_xlim(0, float(resumo["IC95_superior"].max()) * 1.08)
    eixo.grid(axis="x", color="#D9D9D9", linewidth=0.5)
    eixo.set_axisbelow(True)
    eixo.spines[["top", "right"]].set_visible(False)
    for y, valor, limite_superior in zip(
        posicoes,
        resumo["Media"],
        resumo["IC95_superior"],
        strict=True,
    ):
        # Coloca o valor depois da barra de incerteza para preservar legibilidade.
        eixo.text(
            float(limite_superior) + 0.8,
            y,
            decimal(float(valor)),
            va="center",
            fontsize=6.7,
        )
    figura.tight_layout(pad=0.35)
    salvar(figura, "mae_medio_modelos_ieee.png")


def gerar_delta_climatologia() -> None:
    """Plota diferenças pareadas de MAE contra a climatologia e IC95%."""
    dados = pd.read_csv(RESULTADOS / "comparacao_climatologia.csv")
    dados = dados.sort_values("Diferenca_MAE_wm2").reset_index(drop=True)
    dados["rotulo"] = dados["Modelo"].map(NOMES_MODELOS)
    posicoes = np.arange(len(dados))
    erros = np.vstack(
        [
            dados["Diferenca_MAE_wm2"] - dados["IC95_inferior"],
            dados["IC95_superior"] - dados["Diferenca_MAE_wm2"],
        ]
    )
    cores = [COR_VHP if modelo == "VizinhosHistoricos" else COR_MODELO for modelo in dados["Modelo"]]

    figura, eixo = plt.subplots(figsize=(3.45, 2.55))
    eixo.axvline(0, color="#202124", linewidth=0.8, linestyle="--")
    eixo.errorbar(
        dados["Diferenca_MAE_wm2"],
        posicoes,
        xerr=erros,
        fmt="none",
        ecolor=COR_IC,
        elinewidth=1.0,
        capsize=2.3,
    )
    eixo.scatter(dados["Diferenca_MAE_wm2"], posicoes, c=cores, s=24, zorder=3)
    eixo.set_yticks(posicoes, dados["rotulo"])
    eixo.invert_yaxis()
    eixo.set_xlabel(r"$\Delta$MAE vs. climatologia (W/m$^2$)")
    eixo.grid(axis="x", color="#D9D9D9", linewidth=0.5)
    eixo.set_axisbelow(True)
    eixo.spines[["top", "right"]].set_visible(False)
    figura.tight_layout(pad=0.35)
    salvar(figura, "delta_mae_climatologia_ieee.png")


def gerar_previsao_camacari() -> None:
    """Compara a referência NSRDB, climatologia e VHP em Camaçari."""
    pasta = RESULTADOS / "previsoes" / "byd_camacari"
    clima = pd.read_csv(pasta / "previsoes_climatologia.csv", parse_dates=["data"])
    vhp = pd.read_csv(pasta / "previsoes_vizinhoshistoricos.csv", parse_dates=["data"])
    dados = clima.merge(vhp, on="data", suffixes=("_clima", "_vhp"))

    meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    x = np.arange(len(dados))
    figura, eixo = plt.subplots(figsize=(3.45, 2.35))
    eixo.plot(
        x,
        dados["ghi_real_wm2_clima"],
        color=COR_REAL,
        marker="o",
        markersize=3.7,
        linewidth=1.6,
        label="Referência NSRDB",
    )
    eixo.plot(
        x,
        dados["ghi_previsto_climatologia_wm2"],
        color=COR_CLIMA,
        marker="s",
        markersize=3.7,
        linewidth=1.3,
        linestyle="--",
        label="Climatologia",
    )
    eixo.plot(
        x,
        dados["ghi_previsto_vizinhoshistoricos_wm2"],
        color=COR_VHP,
        marker="^",
        markersize=4.0,
        linewidth=1.3,
        linestyle="-.",
        label="VHP",
    )
    eixo.set_xticks(x, meses, rotation=45, ha="right")
    eixo.set_xlabel("Mês de 2024")
    eixo.set_ylabel(r"GHI média mensal (W/m$^2$)")
    eixo.grid(color="#D9D9D9", linewidth=0.5)
    eixo.set_axisbelow(True)
    eixo.spines[["top", "right"]].set_visible(False)
    eixo.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3, frameon=False)
    figura.tight_layout(pad=0.35)
    salvar(figura, "previsao_mensal_byd_camacari_ieee.png")


def main() -> None:
    configurar_estilo()
    gerar_mae_medio()
    gerar_delta_climatologia()
    gerar_previsao_camacari()


if __name__ == "__main__":
    main()
