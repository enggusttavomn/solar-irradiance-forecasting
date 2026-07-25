"""Testes dos modelos tabulares do protocolo global canonico."""

from __future__ import annotations

import numpy as np
import joblib

from codigo_fonte.dados_mensais_globais import carregar_base_mensal_global
from codigo_fonte.modelos_tabulares_globais import (
    prever_baselines_mensais,
    salvar_modelo_joblib,
    treinar_mlp_global,
    treinar_xgboost_global,
)


def test_baselines_globais_sao_finitos_e_tem_um_valor_por_alvo() -> None:
    base = carregar_base_mensal_global()
    previsoes = prever_baselines_mensais(base)

    assert set(previsoes) == {"Persistencia", "SazonalIngenuo", "Climatologia"}
    assert all(valores.shape == (120,) for valores in previsoes.values())
    assert all(np.isfinite(valores).all() for valores in previsoes.values())


def test_xgboost_global_seleciona_arvores_sem_tocar_no_teste() -> None:
    base = carregar_base_mensal_global()
    base_selecao = carregar_base_mensal_global(
        limite_ajuste_transformacao="2023-01-01"
    )
    resultado = treinar_xgboost_global(
        base_selecao.treino,
        base.colunas_tabulares,
        seed=7,
        treino_refit=base.treino,
    )
    previsoes = resultado.modelo.predict(base.teste.loc[:, base.colunas_tabulares])

    assert resultado.n_estimators >= 1
    assert previsoes.shape == (120,)
    assert np.isfinite(previsoes).all()


def test_mlp_global_usa_todas_as_localidades_e_produz_previsoes() -> None:
    base = carregar_base_mensal_global()
    modelo = treinar_mlp_global(base.treino, base.colunas_tabulares, seed=7)
    previsoes = modelo.predict(base.teste.loc[:, base.colunas_tabulares])

    assert previsoes.shape == (120,)
    assert np.isfinite(previsoes).all()


def test_persistencia_joblib_e_atomica_e_recarregavel(tmp_path) -> None:
    base = carregar_base_mensal_global()
    modelo = treinar_mlp_global(base.treino, base.colunas_tabulares, seed=7)
    destino = tmp_path / "modelo.joblib"

    salvar_modelo_joblib(modelo, destino)
    restaurado = joblib.load(destino)

    esperado = modelo.predict(base.teste.loc[:, base.colunas_tabulares])
    observado = restaurado.predict(base.teste.loc[:, base.colunas_tabulares])
    assert np.allclose(observado, esperado)
    assert not list(tmp_path.glob("*.tmp"))
