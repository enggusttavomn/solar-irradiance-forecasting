"""Avaliacao dos modelos e persistencia dos resultados tabulares."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def desnormalizar_ghi(
    valores_normalizados,
    quantization_params: dict[str, float],
) -> pd.Series:
    """Converte GHI normalizado de volta para uma aproximacao em W/m2."""
    valores = pd.Series(valores_normalizados, copy=True).astype(float)
    minimo = float(quantization_params["min"])
    maximo = float(quantization_params["max"])
    return valores.clip(0, 1) * (maximo - minimo) + minimo


def calcular_metricas(y_true, y_pred, modelo: str, sufixo: str = "") -> dict[str, float | str]:
    """Calcula MAE, MSE, RMSE, R2 e nRMSE para um modelo.

    Args:
        y_true: Valores reais do conjunto de teste.
        y_pred: Valores previstos pelo modelo.
        modelo: Nome do modelo avaliado.
        sufixo: Texto opcional anexado ao nome das metricas.

    Returns:
        Dicionario com as metricas no formato da tabela comparativa final.
    """
    y_true_series = pd.Series(y_true, copy=True).astype(float)
    y_pred_series = pd.Series(y_pred, copy=True).astype(float)

    # O MSE e calculado uma vez e reaproveitado para obter a raiz (RMSE).
    mse = mean_squared_error(y_true_series, y_pred_series)
    rmse = mse**0.5
    media_real = float(y_true_series.mean())
    nrmse = np.nan if np.isclose(media_real, 0.0) else rmse / media_real
    prefix = f"_{sufixo}" if sufixo else ""
    return {
        "Modelo": modelo,
        f"MAE{prefix}": mean_absolute_error(y_true_series, y_pred_series),
        f"MSE{prefix}": mse,
        f"RMSE{prefix}": rmse,
        f"R2{prefix}": r2_score(y_true_series, y_pred_series),
        f"nRMSE{prefix}": nrmse,
        f"nRMSE_percentual{prefix}": nrmse * 100 if not np.isnan(nrmse) else np.nan,
    }


def salvar_metricas(metricas: list[dict[str, float | str]], output_path: str | Path) -> pd.DataFrame:
    """Salva a tabela comparativa de metricas dos modelos.

    Args:
        metricas: Lista de dicionarios produzidos por ``calcular_metricas``.
        output_path: Caminho do CSV de metricas.

    Returns:
        DataFrame com a tabela comparativa final.
    """
    df_metricas = pd.DataFrame(metricas)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df_metricas.to_csv(output_path, index=False)
    return df_metricas


def salvar_previsoes(
    datas: pd.Series,
    y_true: pd.Series,
    predicoes: dict[str, pd.Series],
    output_dir: str | Path,
    y_true_original: pd.Series | None = None,
    predicoes_original: dict[str, pd.Series] | None = None,
) -> pd.DataFrame:
    """Salva as previsoes de cada modelo e uma tabela comparativa completa.

    Args:
        datas: Datas do alvo no conjunto de teste.
        y_true: Valores reais normalizados.
        predicoes: Dicionario ``nome_modelo -> previsoes``.
        output_dir: Pasta de saida dos CSVs.
        y_true_original: Valores reais em W/m2.
        predicoes_original: Previsoes em W/m2 por modelo.

    Returns:
        DataFrame com valores reais e previsoes de todos os modelos.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # ``.values`` ignora indices antigos e alinha tudo pela ordem das amostras.
    resultados = pd.DataFrame(
        {
            "data": datas.values,
            "ghi_real": y_true.values,
            "ghi_real_normalizado": y_true.values,
        }
    )
    if y_true_original is not None:
        resultados["ghi_real_wm2"] = pd.Series(y_true_original).reset_index(drop=True).values

    for nome_modelo, y_pred in predicoes.items():
        # Alem do CSV consolidado, cria um arquivo simples para cada modelo.
        nome_seguro = nome_modelo.lower()
        coluna_normalizada = f"ghi_previsto_{nome_seguro}_normalizado"
        resultados[coluna_normalizada] = pd.Series(y_pred).reset_index(drop=True).values
        colunas_modelo = ["data", "ghi_real_normalizado", coluna_normalizada]

        if y_true_original is not None and predicoes_original is not None:
            coluna_original = f"ghi_previsto_{nome_seguro}_wm2"
            resultados[coluna_original] = (
                pd.Series(predicoes_original[nome_modelo]).reset_index(drop=True).values
            )
            colunas_modelo.extend(["ghi_real_wm2", coluna_original])

        resultados[colunas_modelo].to_csv(
            output_dir / f"previsoes_{nome_seguro}.csv",
            index=False,
        )

    # O arquivo consolidado facilita comparar os modelos linha a linha.
    resultados.to_csv(output_dir / "previsoes_modelos.csv", index=False)
    return resultados
