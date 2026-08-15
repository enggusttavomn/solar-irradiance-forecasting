"""Testes das redes recorrentes do protocolo global canonico."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("tensorflow")

from codigo_fonte.dados_mensais_globais import (
    carregar_base_mensal_global,
    matrizes_keras,
)
from codigo_fonte.modelos_neurais_globais import (
    construir_rede_global,
    prever_rede_global,
    salvar_rede_global,
    treinar_rede_global_com_validacao_temporal,
)


@pytest.mark.parametrize("tipo", ["RNN", "LSTM", "DilatedRNN"])
def test_rede_global_recebe_tempo_e_covariaveis_em_ramos_separados(tipo: str) -> None:
    base = carregar_base_mensal_global()
    sequencias, auxiliares, alvos = matrizes_keras(base.treino.head(32), base)
    modelo = construir_rede_global(
        tipo,
        contexto=base.contexto,
        n_auxiliares=auxiliares.shape[1],
        unidades=4,
        unidades_densas=4,
    )
    modelo.fit([sequencias, auxiliares], alvos, epochs=1, batch_size=16, verbose=0)
    previsoes = modelo.predict([sequencias[:3], auxiliares[:3]], verbose=0)

    assert modelo.inputs[0].shape[1:] == (12, 1)
    assert modelo.inputs[1].shape[1:] == (15,)
    assert modelo.get_layer("previsao").activation.__name__ == "linear"
    assert previsoes.shape == (3, 1)
    assert np.isfinite(previsoes).all()


def test_selecao_temporal_pode_refazer_modelo_na_escala_final(tmp_path) -> None:
    base_final = carregar_base_mensal_global()
    base_selecao = carregar_base_mensal_global(
        limite_ajuste_transformacao="2023-01-01"
    )
    ajuste = base_selecao.treino.loc[
        base_selecao.treino["data_alvo"] < "2023-01-01"
    ]
    validacao = base_selecao.treino.loc[
        base_selecao.treino["data_alvo"] >= "2023-01-01"
    ]
    seq_a, aux_a, y_a = matrizes_keras(ajuste, base_selecao)
    seq_v, aux_v, y_v = matrizes_keras(validacao, base_selecao)
    seq_r, aux_r, y_r = matrizes_keras(base_final.treino, base_final)

    resultado = treinar_rede_global_com_validacao_temporal(
        "RNN",
        seq_a,
        aux_a,
        y_a,
        seq_v,
        aux_v,
        y_v,
        seed=7,
        max_epocas=1,
        paciencia=1,
        lote=64,
        unidades=2,
        unidades_densas=2,
        sequencia_refit=seq_r,
        auxiliares_refit=aux_r,
        y_refit=y_r,
    )
    previsoes = prever_rede_global(resultado.modelo, seq_v[:2], aux_v[:2])
    destino = tmp_path / "rnn.keras"
    salvar_rede_global(resultado.modelo, destino)

    assert resultado.epocas == 1
    assert previsoes.shape == (2,)
    assert np.isfinite(previsoes).all()
    assert destino.is_file()


def test_refit_incompleto_e_rejeitado_antes_do_treino() -> None:
    base = carregar_base_mensal_global()
    seq, aux, y = matrizes_keras(base.treino.head(20), base)

    with pytest.raises(ValueError, match="conjuntamente"):
        treinar_rede_global_com_validacao_temporal(
            "RNN",
            seq[:10],
            aux[:10],
            y[:10],
            seq[10:],
            aux[10:],
            y[10:],
            seed=7,
            max_epocas=1,
            paciencia=1,
            sequencia_refit=seq,
        )
