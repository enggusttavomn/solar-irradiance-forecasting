"""Referencias temporais obrigatorias para avaliar previsoes de GHI."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _mapa_observacoes(dados: pd.DataFrame) -> dict[pd.Timestamp, float]:
    datas = pd.to_datetime(dados["data"]).dt.normalize()
    valores = pd.to_numeric(dados["ghi"], errors="raise").astype(float)
    return dict(zip(datas, valores, strict=True))


def _data_ano_anterior(data: pd.Timestamp) -> pd.Timestamp:
    """Retorna a mesma data no ano anterior, tratando 29 de fevereiro."""
    try:
        return data.replace(year=data.year - 1)
    except ValueError:
        return data.replace(year=data.year - 1, day=28)


def prever_baselines(
    dados_treino: pd.DataFrame,
    dados_teste: pd.DataFrame,
    frequencia: str,
) -> dict[str, pd.Series]:
    """Gera persistencia, sazonal ingenuo e climatologia sem usar o teste.

    A climatologia e ajustada apenas nos alvos de treino. A referencia sazonal
    consulta a observacao do mesmo periodo do ano anterior, que ja estaria
    disponivel no instante de cada previsao walk-forward.
    """
    if frequencia not in {"diaria", "mensal"}:
        raise ValueError("frequencia deve ser 'diaria' ou 'mensal'.")
    obrigatorias = {"data", "data_alvo", "ghi", "ghi_alvo_original"}
    for nome, frame in (("treino", dados_treino), ("teste", dados_teste)):
        faltantes = sorted(obrigatorias - set(frame.columns))
        if faltantes:
            raise ValueError(f"Colunas ausentes em {nome}: {', '.join(faltantes)}")

    indice_saida = dados_teste.index
    persistencia = pd.Series(
        dados_teste["ghi"].to_numpy(dtype=float),
        index=indice_saida,
        dtype=float,
    )

    historico = pd.concat([dados_treino, dados_teste], axis=0)
    observacoes = _mapa_observacoes(historico)
    datas_alvo = pd.to_datetime(dados_teste["data_alvo"]).dt.normalize()
    sazonal = []
    for data in datas_alvo:
        anterior = _data_ano_anterior(data)
        if frequencia == "mensal":
            # As datas mensais ficam no fim do mes; DateOffset preserva essa
            # semantica melhor do que subtrair 365 dias.
            anterior = data - pd.offsets.DateOffset(years=1)
            anterior = anterior + pd.offsets.MonthEnd(0)
        if anterior not in observacoes:
            raise ValueError(f"Historico sazonal indisponivel para {data.date()}.")
        sazonal.append(observacoes[anterior])

    alvos_treino = pd.DataFrame(
        {
            "data": pd.to_datetime(dados_treino["data_alvo"]),
            "ghi": dados_treino["ghi_alvo_original"].to_numpy(dtype=float),
        }
    )
    if frequencia == "mensal":
        chave_treino = alvos_treino["data"].dt.month
        chave_teste = datas_alvo.dt.month
    else:
        chave_treino = alvos_treino["data"].dt.strftime("%m-%d")
        chave_teste = datas_alvo.dt.strftime("%m-%d")
    medias = alvos_treino.groupby(chave_treino)["ghi"].mean()
    climatologia = pd.Series(chave_teste.map(medias).to_numpy(), index=indice_saida, dtype=float)
    if climatologia.isna().any():
        # So pode ocorrer em 29/02 quando esse dia nao existiu no treino.
        climatologia = climatologia.fillna(float(alvos_treino["ghi"].mean()))

    return {
        "Persistencia": persistencia,
        "SazonalIngenuo": pd.Series(sazonal, index=indice_saida, dtype=float),
        "Climatologia": climatologia,
    }


def normalizar_previsoes_fisicas(
    previsoes: dict[str, pd.Series],
    parametros: dict[str, float],
) -> dict[str, pd.Series]:
    """Leva referencias em W/m2 para a escala de treino continua."""
    minimo = float(parametros["min"])
    maximo = float(parametros["max"])
    amplitude = maximo - minimo
    if np.isclose(amplitude, 0.0):
        return {nome: pd.Series(np.zeros(len(valores))) for nome, valores in previsoes.items()}
    return {
        nome: ((pd.Series(valores).reset_index(drop=True) - minimo) / amplitude).clip(0, 1)
        for nome, valores in previsoes.items()
    }
