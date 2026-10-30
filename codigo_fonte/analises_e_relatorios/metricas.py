"""Avaliacao dos modelos e persistencia dos resultados tabulares."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def desnormalizar_ghi(
    valores_normalizados,
    quantization_params: dict[str, float],
) -> pd.Series:
    """Inverte a escala min--max e retorna GHI em W/m2.

    ``quantization_params`` e mantido como nome de argumento por compatibilidade;
    no protocolo corrigido seus limites pertencem ao alvo continuo de treino.
    """
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
    if len(y_true_series) != len(y_pred_series) or len(y_true_series) == 0:
        raise ValueError("y_true e y_pred devem ter o mesmo tamanho nao vazio.")
    if not np.isfinite(y_true_series).all() or not np.isfinite(y_pred_series).all():
        raise ValueError("y_true e y_pred devem conter somente valores finitos.")

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
        f"R2{prefix}": (
            r2_score(y_true_series, y_pred_series)
            if len(y_true_series) >= 2
            else np.nan
        ),
        f"nRMSE{prefix}": nrmse,
        f"nRMSE_percentual{prefix}": nrmse * 100 if not np.isnan(nrmse) else np.nan,
    }


def crps_empirico(y_true, amostras) -> np.ndarray:
    """Calcula o CRPS de uma previsao representada por amostras.

    Para cada observacao, a identidade usada e

    ``E|X-y| - 0.5 E|X-X'|``, em que ``X`` e ``X'`` sao duas amostras
    independentes da distribuicao preditiva. A forma ordenada evita construir
    uma matriz quadratica de diferencas para cada previsao.
    """

    reais = np.asarray(y_true, dtype=float).reshape(-1)
    sims = np.asarray(amostras, dtype=float)
    if sims.ndim != 2 or sims.shape[0] != len(reais) or sims.shape[1] < 2:
        raise ValueError(
            "amostras deve ter forma (n_observacoes, n_amostras), com pelo menos duas amostras."
        )
    if not np.isfinite(reais).all() or not np.isfinite(sims).all():
        raise ValueError("y_true e amostras devem conter somente valores finitos.")

    ordenadas = np.sort(sims, axis=1)
    quantidade = sims.shape[1]
    pesos = 2 * np.arange(1, quantidade + 1) - quantidade - 1
    termo_observado = np.mean(np.abs(sims - reais[:, None]), axis=1)
    metade_diferenca_pares = np.sum(ordenadas * pesos, axis=1) / quantidade**2
    return termo_observado - metade_diferenca_pares


def calcular_metricas_probabilisticas(
    y_true,
    amostras,
    modelo: str,
    nivel_intervalo: float = 0.90,
) -> dict[str, float | str]:
    """Resume CRPS, cobertura e largura de um intervalo preditivo central."""

    if not 0 < nivel_intervalo < 1:
        raise ValueError("nivel_intervalo deve estar entre zero e um.")
    reais = np.asarray(y_true, dtype=float).reshape(-1)
    sims = np.asarray(amostras, dtype=float)
    crps = crps_empirico(reais, sims)
    alfa = 1.0 - nivel_intervalo
    inferior = np.quantile(sims, alfa / 2, axis=1)
    superior = np.quantile(sims, 1 - alfa / 2, axis=1)
    cobertura = np.mean((reais >= inferior) & (reais <= superior))
    return {
        "Modelo": modelo,
        "CRPS_wm2": float(np.mean(crps)),
        "Nivel_intervalo": float(nivel_intervalo),
        "PICP": float(cobertura),
        "PICP_percentual": float(cobertura * 100),
        "MPIW_wm2": float(np.mean(superior - inferior)),
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


def resumir_metricas_por_modelo(
    metricas: pd.DataFrame,
    coluna_metrica: str = "MAE_wm2",
    n_bootstrap: int = 20_000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Resume uma metrica entre localidades com IC bootstrap pareado por local."""
    obrigatorias = {"Localidade", "Modelo", coluna_metrica}
    faltantes = sorted(obrigatorias - set(metricas.columns))
    if faltantes:
        raise ValueError(f"Colunas ausentes: {', '.join(faltantes)}")
    if n_bootstrap < 1:
        raise ValueError("n_bootstrap deve ser positivo.")
    rng = np.random.default_rng(random_state)
    linhas = []
    for modelo, grupo in metricas.groupby("Modelo", sort=True):
        valores = grupo.groupby("Localidade")[coluna_metrica].mean().to_numpy(dtype=float)
        amostras = rng.choice(valores, size=(n_bootstrap, len(valores)), replace=True)
        medias = amostras.mean(axis=1)
        linhas.append(
            {
                "Modelo": modelo,
                "Metrica": coluna_metrica,
                "N_localidades": len(valores),
                "Media": float(valores.mean()),
                "Desvio_padrao_localidades": float(valores.std(ddof=1)) if len(valores) > 1 else np.nan,
                "IC95_inferior": float(np.quantile(medias, 0.025)),
                "IC95_superior": float(np.quantile(medias, 0.975)),
            }
        )
    return pd.DataFrame(linhas).sort_values("Media", ignore_index=True)


def _ajustar_holm(p_valores: list[float]) -> list[float]:
    """Ajuste de Holm sem dependencia adicional."""
    ordem = np.argsort(p_valores)
    ajustados_ordenados = []
    acumulado = 0.0
    quantidade = len(p_valores)
    for posicao, indice in enumerate(ordem):
        candidato = min(1.0, (quantidade - posicao) * float(p_valores[indice]))
        acumulado = max(acumulado, candidato)
        ajustados_ordenados.append(acumulado)
    resultado = [np.nan] * quantidade
    for indice, ajustado in zip(ordem, ajustados_ordenados, strict=True):
        resultado[int(indice)] = float(ajustado)
    return resultado


def comparar_mae_com_referencia(
    metricas: pd.DataFrame,
    referencia: str = "Climatologia",
    n_bootstrap: int = 20_000,
    random_state: int = 42,
) -> pd.DataFrame:
    """Compara MAE por localidade contra uma referencia predefinida.

    ``Diferenca_MAE_wm2`` e MAE(modelo) menos MAE(referencia): valores positivos
    favorecem a referencia. O bootstrap reamostra localidades inteiras, e o
    Wilcoxon usa as dez diferencas pareadas; Holm corrige os testes simultaneos.
    """
    obrigatorias = {"Localidade", "Modelo", "MAE_wm2"}
    faltantes = sorted(obrigatorias - set(metricas.columns))
    if faltantes:
        raise ValueError(f"Colunas ausentes: {', '.join(faltantes)}")
    tabela = metricas.pivot_table(
        index="Localidade",
        columns="Modelo",
        values="MAE_wm2",
        aggfunc="mean",
    )
    if referencia not in tabela.columns:
        raise ValueError(f"Referencia ausente: {referencia}")
    rng = np.random.default_rng(random_state)
    linhas = []
    for modelo in sorted(coluna for coluna in tabela.columns if coluna != referencia):
        pares = tabela[[modelo, referencia]].dropna()
        diferencas = (pares[modelo] - pares[referencia]).to_numpy(dtype=float)
        if len(diferencas) < 2:
            raise ValueError(f"Pares insuficientes para comparar {modelo}.")
        indices = rng.integers(0, len(diferencas), size=(n_bootstrap, len(diferencas)))
        medias_bootstrap = diferencas[indices].mean(axis=1)
        inferior, superior = np.quantile(medias_bootstrap, [0.025, 0.975])
        if np.allclose(diferencas, 0):
            p_valor = 1.0
        else:
            p_valor = float(
                wilcoxon(diferencas, alternative="two-sided", method="auto").pvalue
            )
        conclusao = "inconclusivo"
        if superior < 0:
            conclusao = "modelo_melhor"
        elif inferior > 0:
            conclusao = "referencia_melhor"
        linhas.append(
            {
                "Modelo": modelo,
                "Referencia": referencia,
                "N_localidades": len(diferencas),
                "Diferenca_MAE_wm2": float(diferencas.mean()),
                "Mediana_diferenca_MAE_wm2": float(np.median(diferencas)),
                "IC95_inferior": float(inferior),
                "IC95_superior": float(superior),
                "Wilcoxon_p": p_valor,
                "Conclusao_IC95": conclusao,
            }
        )
    p_ajustados = _ajustar_holm([linha["Wilcoxon_p"] for linha in linhas])
    for linha, p_ajustado in zip(linhas, p_ajustados, strict=True):
        linha["Wilcoxon_p_Holm"] = p_ajustado
    return pd.DataFrame(linhas).sort_values("Diferenca_MAE_wm2", ignore_index=True)
