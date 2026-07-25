"""Modelos tabulares e referencias do protocolo mensal global canonico."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

import joblib
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
from xgboost import XGBRegressor

from codigo_fonte.dados_mensais_globais import BaseMensalGlobal


@dataclass(frozen=True)
class ResultadoXGBoostGlobal:
    modelo: XGBRegressor
    n_estimators: int


def _parametros_xgboost(seed: int, n_estimators: int) -> dict[str, object]:
    return {
        "n_estimators": n_estimators,
        "max_depth": 3,
        "learning_rate": 0.03,
        "min_child_weight": 4,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "reg_alpha": 0.1,
        "reg_lambda": 10.0,
        "objective": "reg:squarederror",
        "eval_metric": "mae",
        "random_state": seed,
        "n_jobs": -1,
    }


def treinar_xgboost_global(
    treino: pd.DataFrame,
    colunas: tuple[str, ...],
    *,
    seed: int = 42,
    inicio_validacao: str = "2023-01-01",
    treino_refit: pd.DataFrame | None = None,
) -> ResultadoXGBoostGlobal:
    """Seleciona arvores temporalmente e reajusta em uma base final.

    ``treino`` deve ter sido transformado usando apenas o bloco anterior a
    ``inicio_validacao``. ``treino_refit`` pode usar a transformacao ajustada em
    todo o treino e e a unica base entregue ao modelo final. Essa separacao
    impede que extremos da validacao vazem para a escolha do numero de arvores.
    """

    obrigatorias = set(colunas) | {"data_alvo", "y_normalizado"}
    faltantes = sorted(obrigatorias - set(treino.columns))
    if faltantes:
        raise ValueError(f"Colunas ausentes no treino de selecao: {', '.join(faltantes)}")
    refit = treino if treino_refit is None else treino_refit
    faltantes_refit = sorted(obrigatorias - set(refit.columns))
    if faltantes_refit:
        raise ValueError(f"Colunas ausentes no treino final: {', '.join(faltantes_refit)}")
    for nome, frame in (("selecao", treino), ("final", refit)):
        valores = frame.loc[:, list(colunas) + ["y_normalizado"]].to_numpy(dtype=float)
        if frame.empty or not np.isfinite(valores).all():
            raise ValueError(f"O treino {nome} deve ser nao vazio e finito.")

    datas = pd.to_datetime(treino["data_alvo"])
    inicio = pd.Timestamp(inicio_validacao)
    if inicio.tz is not None:
        raise ValueError("inicio_validacao nao pode possuir fuso horario.")
    mascara_validacao = datas >= inicio
    if not mascara_validacao.any() or mascara_validacao.all():
        raise ValueError("A janela de validacao do XGBoost precisa dividir o treino.")
    X_ajuste = treino.loc[~mascara_validacao, list(colunas)]
    y_ajuste = treino.loc[~mascara_validacao, "y_normalizado"]
    X_validacao = treino.loc[mascara_validacao, list(colunas)]
    y_validacao = treino.loc[mascara_validacao, "y_normalizado"]
    seletor = XGBRegressor(
        **_parametros_xgboost(seed, 1000),
        early_stopping_rounds=40,
    )
    seletor.fit(
        X_ajuste,
        y_ajuste,
        eval_set=[(X_validacao, y_validacao)],
        verbose=False,
    )
    melhor_iteracao = getattr(seletor, "best_iteration", None)
    n_estimators = 1000 if melhor_iteracao is None else max(1, int(melhor_iteracao) + 1)
    modelo = XGBRegressor(**_parametros_xgboost(seed, n_estimators))
    modelo.fit(refit.loc[:, list(colunas)], refit["y_normalizado"])
    return ResultadoXGBoostGlobal(modelo=modelo, n_estimators=n_estimators)


def treinar_mlp_global(
    treino: pd.DataFrame,
    colunas: tuple[str, ...],
    *,
    seed: int,
):
    """Treina uma MLP regularizada sobre todas as localidades."""

    modelo = make_pipeline(
        StandardScaler(),
        MLPRegressor(
            hidden_layer_sizes=(64, 32),
            activation="relu",
            solver="lbfgs",
            alpha=0.05,
            max_iter=2000,
            random_state=seed,
        ),
    )
    modelo.fit(treino.loc[:, list(colunas)], treino["y_normalizado"])
    return modelo


def prever_baselines_mensais(
    base: BaseMensalGlobal,
) -> dict[str, np.ndarray]:
    """Calcula persistencia, sazonal ingenuo e climatologia em W/m2."""

    treino = base.treino
    teste = base.teste
    persistencia = np.empty(len(teste), dtype=float)
    sazonal = np.empty(len(teste), dtype=float)
    climatologia = np.empty(len(teste), dtype=float)

    medias = (
        treino.assign(mes=pd.to_datetime(treino["data_alvo"]).dt.month)
        .groupby(["localidade_id", "mes"])["y_wm2"]
        .mean()
    )
    for posicao, (_, linha) in enumerate(teste.iterrows()):
        serie = base.series[int(linha["localidade_id"])]
        alvo_idx = int(linha["indice_alvo"])
        # As referencias ingenuas usam as observacoes fisicas exatas. Elas nao
        # devem herdar o erro de discretizacao reservado aos modelos treinados.
        persistencia[posicao] = serie.ghi_wm2[alvo_idx - 1]
        sazonal[posicao] = serie.ghi_wm2[alvo_idx - 12]
        chave = (int(linha["localidade_id"]), pd.Timestamp(linha["data_alvo"]).month)
        climatologia[posicao] = float(medias.loc[chave])
    return {
        "Persistencia": persistencia,
        "SazonalIngenuo": sazonal,
        "Climatologia": climatologia,
    }


def salvar_modelo_joblib(modelo, caminho: str | Path) -> None:
    """Persiste um estimador por substituicao atomica no mesmo diretorio."""

    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{caminho.name}-",
        suffix=".tmp",
        dir=caminho.parent,
        delete=False,
    ) as arquivo:
        temporario = Path(arquivo.name)
    try:
        joblib.dump(modelo, temporario)
        temporario.replace(caminho)
    finally:
        temporario.unlink(missing_ok=True)


__all__ = [
    "ResultadoXGBoostGlobal",
    "prever_baselines_mensais",
    "salvar_modelo_joblib",
    "treinar_mlp_global",
    "treinar_xgboost_global",
]
