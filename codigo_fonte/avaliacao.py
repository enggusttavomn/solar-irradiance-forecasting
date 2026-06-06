"""Metricas e salvamento das previsoes dos modelos de GHI."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def calcular_metricas(y_true, y_pred, modelo: str) -> dict[str, float | str]:
    """Calcula MAE, MSE, RMSE e R2 para um modelo.

    Args:
        y_true: Valores reais do conjunto de teste.
        y_pred: Valores previstos pelo modelo.
        modelo: Nome do modelo avaliado.

    Returns:
        Dicionario com as metricas no formato da tabela comparativa final.
    """
    mse = mean_squared_error(y_true, y_pred)
    return {
        "Modelo": modelo,
        "MAE": mean_absolute_error(y_true, y_pred),
        "MSE": mse,
        "RMSE": mse**0.5,
        "R2": r2_score(y_true, y_pred),
    }


def salvar_metricas(metricas: list[dict[str, float | str]], output_path: str | Path) -> pd.DataFrame:
    """Salva a tabela comparativa de metricas dos modelos.

    Args:
        metricas: Lista de dicionarios produzidos por ``calcular_metricas``.
        output_path: Caminho do CSV de metricas.

    Returns:
        DataFrame com a tabela comparativa final.
    """
    df_metricas = pd.DataFrame(metricas, columns=["Modelo", "MAE", "MSE", "RMSE", "R2"])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_metricas.to_csv(output_path, index=False)
    return df_metricas


def salvar_previsoes(
    datas: pd.Series,
    y_true: pd.Series,
    predicoes: dict[str, pd.Series],
    output_dir: str | Path,
) -> pd.DataFrame:
    """Salva as previsoes de cada modelo e uma tabela comparativa completa.

    Args:
        datas: Datas do alvo no conjunto de teste.
        y_true: Valores reais normalizados.
        predicoes: Dicionario ``nome_modelo -> previsoes``.
        output_dir: Pasta de saida dos CSVs.

    Returns:
        DataFrame com valores reais e previsoes de todos os modelos.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    resultados = pd.DataFrame({"data": datas.values, "ghi_real": y_true.values})
    for nome_modelo, y_pred in predicoes.items():
        nome_seguro = nome_modelo.lower()
        coluna = f"ghi_previsto_{nome_seguro}"
        resultados[coluna] = y_pred
        resultados[["data", "ghi_real", coluna]].to_csv(
            output_dir / f"previsoes_{nome_seguro}.csv",
            index=False,
        )

    resultados.to_csv(output_dir / "previsoes_modelos.csv", index=False)
    return resultados
