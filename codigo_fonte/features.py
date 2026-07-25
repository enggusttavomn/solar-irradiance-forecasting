"""Conversao da serie temporal em uma base supervisionada.

Uma serie temporal possui uma observacao por periodo. Modelos tabulares
precisam de colunas de entrada e uma coluna alvo; este modulo cria essa
representacao sem permitir que informacoes futuras aparecam nas entradas.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def criar_features_temporais(
    dados: pd.DataFrame,
    lags: tuple[int, ...] = (1, 2, 3, 7),
    moving_windows: tuple[int, ...] = (3, 7, 30),
    periodo_label: str = "d",
    incluir_calendario: bool = True,
) -> tuple[pd.DataFrame, list[str]]:
    """Cria lags, medias moveis e alvo seguinte sem vazamento de dados.

    Args:
        dados: DataFrame com colunas ``data``, ``ghi`` e ``ghi_normalizado``.
        lags: Defasagens usadas como entradas do modelo.
        moving_windows: Janelas das medias moveis.
        periodo_label: Sufixo textual das janelas, como ``d`` ou ``m``.
        incluir_calendario: Inclui seno/cosseno do periodo do alvo. Essas
            variaveis sao conhecidas antes da previsao e nao causam vazamento.

    Returns:
        DataFrame com as features criadas e lista de colunas de entrada.

    Notes:
        A linha associada ao periodo ``t`` preve o periodo ``t+1``. Os nomes
        dos lags sao definidos em relacao ao alvo: ``ghi_t-1`` e o valor do
        proprio periodo ``t``, exatamente um periodo antes do alvo.
    """
    colunas_obrigatorias = {"data", "ghi", "ghi_normalizado", "ghi_quantizado"}
    faltantes = sorted(colunas_obrigatorias - set(dados.columns))
    if faltantes:
        raise ValueError(f"Colunas obrigatorias ausentes: {', '.join(faltantes)}")
    if periodo_label not in {"d", "m"}:
        raise ValueError("periodo_label deve ser 'd' ou 'm'.")
    if len(set(lags)) != len(lags) or len(set(moving_windows)) != len(moving_windows):
        raise ValueError("Lags e janelas moveis nao podem conter duplicatas.")

    # A copia evita modificar silenciosamente o DataFrame recebido pelo chamador.
    dados = dados.copy()
    dados["data"] = pd.to_datetime(dados["data"])
    feature_columns: list[str] = []

    # A linha de data t preve t+1. Portanto, lag 1 e o valor observado em t,
    # exatamente um dia antes do alvo.
    for lag in lags:
        coluna = f"ghi_t-{lag}"
        dados[coluna] = dados["ghi_normalizado"].shift(lag - 1)
        feature_columns.append(coluna)

    # ``min_periods=janela`` exige uma janela completa. Por isso as primeiras
    # linhas ficam vazias ate que exista historico suficiente.
    for janela in moving_windows:
        coluna = f"ghi_media_movel_{janela}{periodo_label}"
        dados[coluna] = dados["ghi_normalizado"].rolling(
            window=janela,
            min_periods=janela,
        ).mean()
        feature_columns.append(coluna)

    # ``shift(-1)`` traz o valor da proxima linha para a linha atual.
    # As tres versoes do alvo servem a finalidades diferentes:
    # normalizada para treinar, quantizada e original para auditoria.
    dados["data_alvo"] = dados["data"].shift(-1)
    dados["ghi_alvo"] = dados["ghi_normalizado"].shift(-1)
    dados["ghi_alvo_quantizado"] = dados["ghi_quantizado"].shift(-1)
    dados["ghi_alvo_original"] = dados["ghi"].shift(-1)

    # O calendario do periodo previsto esta disponivel no instante da previsao.
    # A codificacao circular evita a descontinuidade artificial dezembro/janeiro.
    if incluir_calendario:
        if periodo_label == "m":
            fase = 2 * np.pi * (dados["data_alvo"].dt.month - 1) / 12
            nomes = ("mes_alvo_sin", "mes_alvo_cos")
        else:
            fase = 2 * np.pi * (dados["data_alvo"].dt.dayofyear - 1) / 365.2425
            nomes = ("dia_ano_alvo_sin", "dia_ano_alvo_cos")
        dados[nomes[0]] = np.sin(fase)
        dados[nomes[1]] = np.cos(fase)
        feature_columns.extend(nomes)

    # Remove o inicio sem historico completo e a ultima linha, que nao possui
    # um periodo seguinte dentro da serie. O indice e refeito para ficar continuo.
    dados = dados.dropna(subset=feature_columns + ["ghi_alvo"]).reset_index(drop=True)
    return dados, feature_columns


def dividir_treino_teste_temporal(
    dados: pd.DataFrame,
    feature_columns: list[str],
    target_column: str = "ghi_alvo",
    train_ratio: float = 0.8,
):
    """Divide a base em treino e teste mantendo a ordem temporal.

    Args:
        dados: Base supervisionada ja ordenada cronologicamente.
        feature_columns: Colunas usadas como entradas.
        target_column: Coluna alvo.
        train_ratio: Proporcao inicial da serie usada no treino.

    Returns:
        Tupla ``X_train, X_test, y_train, y_test, dados_treino, dados_teste``.

    Notes:
        Nao existe embaralhamento. Os primeiros registros formam o treino e os
        registros cronologicamente mais novos formam o teste.
    """
    if not 0 < train_ratio < 1:
        raise ValueError("train_ratio deve estar entre 0 e 1.")

    # ``int`` arredonda para baixo, garantindo um ponto de corte inteiro.
    train_size = int(len(dados) * train_ratio)
    if train_size == 0 or train_size == len(dados):
        raise ValueError("A serie nao tem observacoes suficientes para treino e teste.")

    # ``iloc`` divide por posicao sem alterar a ordem temporal.
    dados_treino = dados.iloc[:train_size].copy()
    dados_teste = dados.iloc[train_size:].copy()

    # X contem somente entradas; y contem somente a variavel que sera prevista.
    X_train = dados_treino[feature_columns]
    X_test = dados_teste[feature_columns]
    y_train = dados_treino[target_column]
    y_test = dados_teste[target_column]

    return X_train, X_test, y_train, y_test, dados_treino, dados_teste
