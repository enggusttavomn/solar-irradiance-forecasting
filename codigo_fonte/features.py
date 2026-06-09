"""Conversao da serie diaria em uma base supervisionada.

Uma serie temporal possui uma observacao por data. Modelos tabulares precisam
de colunas de entrada e uma coluna alvo; este modulo cria essa representacao
sem permitir que informacoes futuras aparecam nas entradas.
"""

from __future__ import annotations

import pandas as pd


def criar_features_temporais(
    dados: pd.DataFrame,
    lags: tuple[int, ...] = (1, 2, 3, 7),
    moving_windows: tuple[int, ...] = (3, 7, 30),
) -> tuple[pd.DataFrame, list[str]]:
    """Cria lags, medias moveis e alvo do dia seguinte sem vazamento de dados.

    Args:
        dados: DataFrame com colunas ``data``, ``ghi`` e ``ghi_normalizado``.
        lags: Defasagens usadas como entradas do modelo.
        moving_windows: Janelas das medias moveis.

    Returns:
        DataFrame com as features criadas e lista de colunas de entrada.

    Notes:
        A linha associada ao dia ``t`` preve o dia ``t+1``. Os nomes dos lags
        sao definidos em relacao ao alvo: ``ghi_t-1`` e o valor do proprio dia
        ``t``, exatamente um dia antes do alvo.
    """
    # A copia evita modificar silenciosamente o DataFrame recebido pelo chamador.
    dados = dados.copy()
    feature_columns: list[str] = []

    # A linha de data t preve t+1. Portanto, lag 1 e o valor observado em t,
    # exatamente um dia antes do alvo.
    for lag in lags:
        coluna = f"ghi_t-{lag}"
        dados[coluna] = dados["ghi_normalizado"].shift(lag - 1)
        feature_columns.append(coluna)

    # ``min_periods=janela`` exige uma janela completa. Por isso as primeiras
    # 29 linhas ficam vazias quando a maior janela possui 30 dias.
    for janela in moving_windows:
        coluna = f"ghi_media_movel_{janela}d"
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

    # Remove o inicio sem historico completo e a ultima linha, que nao possui
    # um dia seguinte dentro da serie. O indice e refeito para ficar continuo.
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
