"""Geracao e salvamento dos graficos de avaliacao."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def gerar_grafico_temporal(
    datas: pd.Series,
    y_true: pd.Series,
    predicoes: dict[str, pd.Series],
    caminho_saida: str | Path,
) -> None:
    """Gera grafico temporal comparando valores reais e previstos no teste."""
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(12, 4.5))
    plt.plot(datas, y_true, label="Real", linewidth=2.2, color="black")
    for nome_modelo, y_pred in predicoes.items():
        plt.plot(datas, y_pred, label=nome_modelo, linewidth=1.8, alpha=0.85)

    plt.title("Serie temporal no conjunto de teste")
    plt.xlabel("Data")
    plt.ylabel("GHI quantizado normalizado")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=300)
    plt.close()


def gerar_grafico_real_vs_previsto(
    datas: pd.Series,
    y_true: pd.Series,
    y_pred: pd.Series,
    modelo: str,
    caminho_saida: str | Path,
) -> None:
    """Gera grafico temporal para um modelo especifico."""
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(11, 4))
    plt.plot(datas, y_true, label="Real", linewidth=2)
    plt.plot(datas, y_pred, label=f"Previsto - {modelo}", linewidth=2, alpha=0.85)
    plt.title(f"Valores reais vs previstos - {modelo}")
    plt.xlabel("Data")
    plt.ylabel("GHI quantizado normalizado")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=300)
    plt.close()


def gerar_grafico_dispersao(
    y_true: pd.Series,
    y_pred: pd.Series,
    modelo: str,
    caminho_saida: str | Path,
) -> None:
    """Gera grafico de dispersao real vs previsto para um modelo."""
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    min_value = min(float(pd.Series(y_true).min()), float(pd.Series(y_pred).min()))
    max_value = max(float(pd.Series(y_true).max()), float(pd.Series(y_pred).max()))

    plt.figure(figsize=(5, 5))
    plt.scatter(y_true, y_pred, alpha=0.65)
    plt.plot([min_value, max_value], [min_value, max_value], color="black", linestyle="--")
    plt.title(f"Dispersao real vs previsto - {modelo}")
    plt.xlabel("GHI real")
    plt.ylabel("GHI previsto")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=300)
    plt.close()


def salvar_graficos(
    datas: pd.Series,
    y_true: pd.Series,
    predicoes: dict[str, pd.Series],
    pasta_saida: str | Path,
) -> None:
    """Salva todos os graficos obrigatorios da avaliacao dos modelos."""
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    gerar_grafico_temporal(
        datas,
        y_true,
        predicoes,
        pasta_saida / "serie_temporal_teste_real_xgboost_mlp.png",
    )

    for nome_modelo, y_pred in predicoes.items():
        nome_seguro = nome_modelo.lower()
        gerar_grafico_real_vs_previsto(
            datas,
            y_true,
            y_pred,
            nome_modelo,
            pasta_saida / f"{nome_seguro}_real_vs_previsto.png",
        )
        gerar_grafico_dispersao(
            y_true,
            y_pred,
            nome_modelo,
            pasta_saida / f"{nome_seguro}_dispersao_real_vs_previsto.png",
        )
