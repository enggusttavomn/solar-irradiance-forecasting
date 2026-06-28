"""Geracao dos graficos usados para avaliar visualmente as previsoes."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def gerar_grafico_temporal(
    datas: pd.Series,
    y_true: pd.Series,
    predicoes: dict[str, pd.Series],
    caminho_saida: str | Path,
    y_label: str = "GHI quantizado normalizado",
    titulo_sufixo: str = "",
) -> None:
    """Gera grafico temporal comparando valores reais e previstos no teste."""
    # A funcao cria a pasta de destino para poder ser chamada isoladamente.
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    # A linha preta e a referencia real; as demais sao as previsoes.
    plt.figure(figsize=(12, 4.5))
    plt.plot(datas, y_true, label="Real", linewidth=2.2, color="black")
    for nome_modelo, y_pred in predicoes.items():
        plt.plot(datas, y_pred, label=nome_modelo, linewidth=1.8, alpha=0.85)

    plt.title(f"Serie temporal no conjunto de teste{titulo_sufixo}")
    plt.xlabel("Data")
    plt.ylabel(y_label)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    # ``tight_layout`` evita cortes nos rotulos; 300 dpi atende uso em relatorio.
    plt.savefig(caminho_saida, dpi=300)
    # Fechar libera memoria, importante ao gerar dezenas de figuras em lote.
    plt.close()


def gerar_grafico_real_vs_previsto(
    datas: pd.Series,
    y_true: pd.Series,
    y_pred: pd.Series,
    modelo: str,
    caminho_saida: str | Path,
    y_label: str = "GHI quantizado normalizado",
    titulo_sufixo: str = "",
) -> None:
    """Gera grafico temporal para um modelo especifico."""
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    # Este grafico isola um modelo para facilitar a leitura de atrasos e picos.
    plt.figure(figsize=(11, 4))
    plt.plot(datas, y_true, label="Real", linewidth=2)
    plt.plot(datas, y_pred, label=f"Previsto - {modelo}", linewidth=2, alpha=0.85)
    plt.title(f"Valores reais vs previstos - {modelo}{titulo_sufixo}")
    plt.xlabel("Data")
    plt.ylabel(y_label)
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
    eixo_label: str = "GHI",
    titulo_sufixo: str = "",
) -> None:
    """Gera grafico de dispersao real vs previsto para um modelo."""
    caminho_saida = Path(caminho_saida)
    caminho_saida.parent.mkdir(parents=True, exist_ok=True)

    # Os limites comuns permitem desenhar a diagonal ideal y_previsto = y_real.
    min_value = min(float(pd.Series(y_true).min()), float(pd.Series(y_pred).min()))
    max_value = max(float(pd.Series(y_true).max()), float(pd.Series(y_pred).max()))

    plt.figure(figsize=(5, 5))
    # Quanto mais perto um ponto estiver da diagonal, menor e o erro da amostra.
    plt.scatter(y_true, y_pred, alpha=0.65)
    plt.plot([min_value, max_value], [min_value, max_value], color="black", linestyle="--")
    plt.title(f"Dispersao real vs previsto - {modelo}{titulo_sufixo}")
    plt.xlabel(f"{eixo_label} real")
    plt.ylabel(f"{eixo_label} previsto")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=300)
    plt.close()


def salvar_graficos(
    datas: pd.Series,
    y_true: pd.Series,
    predicoes: dict[str, pd.Series],
    pasta_saida: str | Path,
    y_label: str = "GHI quantizado normalizado",
    titulo_sufixo: str = "",
) -> None:
    """Salva todos os graficos obrigatorios da avaliacao dos modelos."""
    pasta_saida = Path(pasta_saida)
    pasta_saida.mkdir(parents=True, exist_ok=True)

    # Primeiro salva a visao conjunta dos dois modelos.
    gerar_grafico_temporal(
        datas,
        y_true,
        predicoes,
        pasta_saida / "serie_temporal_teste_real_xgboost_mlp.png",
        y_label=y_label,
        titulo_sufixo=titulo_sufixo,
    )

    # Depois cria duas figuras especificas para cada modelo.
    for nome_modelo, y_pred in predicoes.items():
        nome_seguro = nome_modelo.lower()
        gerar_grafico_real_vs_previsto(
            datas,
            y_true,
            y_pred,
            nome_modelo,
            pasta_saida / f"{nome_seguro}_real_vs_previsto.png",
            y_label=y_label,
            titulo_sufixo=titulo_sufixo,
        )
        gerar_grafico_dispersao(
            y_true,
            y_pred,
            nome_modelo,
            pasta_saida / f"{nome_seguro}_dispersao_real_vs_previsto.png",
            eixo_label=y_label,
            titulo_sufixo=titulo_sufixo,
        )
