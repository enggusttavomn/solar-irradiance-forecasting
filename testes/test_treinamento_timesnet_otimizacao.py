"""Verifica selecao fisica, refit e validacao do treino TimesNet separado."""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn

import codigo_fonte.treinamento_timesnet_otimizacao as treino
from codigo_fonte.experimento_multirresolucao import (
    ConfiguracaoMultirresolucao,
    JanelasDiretas,
    TAREFAS_CANONICAS,
)


def _janelas(ids=(0, 0, 0, 1), ano=2020) -> JanelasDiretas:
    ids = np.asarray(ids, dtype=np.int64)
    n = len(ids)
    y = np.where(ids == 0, 20.0, 200.0).astype(np.float32).reshape(n, 1)
    datas = pd.date_range(f"{ano}-01-31", periods=n, freq="ME")
    return JanelasDiretas(
        x_bruto=np.repeat(y, 12, axis=1),
        y_bruto=y,
        localidade_id=ids,
        localidade=np.asarray([f"Local {i}" for i in ids], dtype=object),
        origem=datas,
        datas_alvo=datas.to_numpy().reshape(n, 1),
        seq_len=12,
        pred_len=1,
        particao="ajuste" if ano == 2020 else "validacao",
    )


def _escalas() -> pd.DataFrame:
    return pd.DataFrame(
        {"localidade_id": [0, 1], "minimo_treino_wm2": [10.0, 100.0], "amplitude_escala_wm2": [10.0, 100.0]}
    )


def _config(**alteracoes) -> ConfiguracaoMultirresolucao:
    return replace(
        ConfiguracaoMultirresolucao(
            max_epocas_mensal=3,
            paciencia_mensal=1,
            timesnet_d_model=4,
            timesnet_d_ff=8,
            timesnet_top_k=1,
            timesnet_kernels=1,
        ),
        **alteracoes,
    )


def test_macro_mae_inverte_escala_e_da_peso_igual_a_localidades() -> None:
    janelas = _janelas()
    previsto = np.array([[0.9], [0.9], [0.9], [1.1]])
    # Erros fisicos: [1, 1, 1, 10]. Macro=5.5; media dos pontos seria 3.25.
    assert treino.macro_mae_fisico(janelas, previsto, _escalas()) == pytest.approx(5.5)


def test_macro_mae_aplica_piso_zero_apos_inverter() -> None:
    janelas = _janelas(ids=(0, 1))
    previsto = np.full((2, 1), -20.0)
    assert treino.macro_mae_fisico(janelas, previsto, _escalas()) == pytest.approx(110.0)


def test_macro_mae_com_deslocamento_aplica_o_piso_sobre_o_ghi() -> None:
    """Com alvo de anomalia, o piso zero tem de valer para GHI, nao para o desvio."""
    janelas = _janelas(ids=(0, 1))
    previsto = np.array([[-4.0], [0.0]])  # apos inverter: -30 e 100 W/m2 de desvio
    deslocamento = np.array([[25.0], [50.0]])  # climatologia dos alvos
    # GHI previsto: max(-5, 0)=0 e 150; GHI real: 45 e 250. Erros 45 e 100.
    assert treino.macro_mae_fisico(janelas, previsto, _escalas(), deslocamento) == pytest.approx(72.5)


def test_macro_mae_sem_deslocamento_mantem_o_comportamento_anterior() -> None:
    janelas = _janelas(ids=(0, 1))
    previsto = np.array([[0.9], [1.1]])
    sem = treino.macro_mae_fisico(janelas, previsto, _escalas())
    zerado = treino.macro_mae_fisico(janelas, previsto, _escalas(), np.zeros((2, 1)))
    assert sem == pytest.approx(zerado)


@pytest.mark.parametrize("deslocamento", [np.zeros((2, 2)), np.full((2, 1), np.nan)])
def test_macro_mae_rejeita_deslocamento_incompativel(deslocamento) -> None:
    with pytest.raises(ValueError, match="Deslocamento"):
        treino.macro_mae_fisico(_janelas(ids=(0, 1)), np.zeros((2, 1)), _escalas(), deslocamento)


def test_treino_rejeita_deslocamento_sem_validacao() -> None:
    with pytest.raises(ValueError, match="deslocamento_validacao"):
        treino.treinar_candidato(
            tarefa=TAREFAS_CANONICAS["monthly_1"], configuracao=_config(), semente=42,
            ajuste=_janelas(), escalas=_escalas(), epocas_fixas=1,
            deslocamento_validacao=np.zeros((4, 1)),
        )


@pytest.mark.parametrize("previsto", [np.zeros((4,)), np.full((4, 1), np.nan), np.full((4, 1), np.inf)])
def test_macro_mae_rejeita_forma_e_valores_invalidos(previsto) -> None:
    with pytest.raises(ValueError):
        treino.macro_mae_fisico(_janelas(), previsto, _escalas())


@pytest.mark.parametrize("problema", ["duplicada", "zero", "negativa", "infinita", "ausente"])
def test_macro_mae_rejeita_escalas_invalidas(problema) -> None:
    escalas = _escalas()
    if problema == "duplicada":
        escalas = pd.concat([escalas, escalas.iloc[:1]])
    elif problema == "ausente":
        escalas = escalas.iloc[:1]
    else:
        escalas.loc[0, "amplitude_escala_wm2"] = {"zero": 0.0, "negativa": -1.0, "infinita": np.inf}[problema]
    with pytest.raises(ValueError):
        treino.macro_mae_fisico(_janelas(), np.zeros((4, 1)), escalas)


class _RedeConstante(nn.Module):
    def __init__(self):
        super().__init__()
        self.peso = nn.Parameter(torch.tensor(0.0))

    def forward(self, x, ids):
        return self.peso.expand(len(x), 1)


def test_selecao_usa_mae_fisico_e_restaura_melhor_estado(monkeypatch) -> None:
    estados = []
    erros_normalizados = (np.array([[0.8], [0.01]]), np.array([[0.1], [0.1]]))

    def prever(modelo, x, ids, *, batch_size):
        estados.append(modelo.peso.detach().clone())
        return 1.0 + erros_normalizados[len(estados) - 1]

    monkeypatch.setattr(treino, "criar_modelo_neural", lambda *a, **k: _RedeConstante())
    monkeypatch.setattr(treino, "prever_rede", prever)
    modelo, epoca, historico = treino.treinar_candidato(
        tarefa=TAREFAS_CANONICAS["monthly_1"],
        configuracao=_config(),
        semente=42,
        ajuste=_janelas(ids=(0, 1)),
        validacao=_janelas(ids=(0, 1), ano=2023),
        escalas=_escalas(),
    )
    # MSE normalizado favoreceria epoca 2; MAE fisico favorece epoca 1.
    assert np.mean(erros_normalizados[1] ** 2) < np.mean(erros_normalizados[0] ** 2)
    assert epoca == 1
    assert list(historico.epoca) == [1, 2]
    np.testing.assert_allclose(historico.mae_validacao_wm2, [4.5, 5.5])
    assert not torch.equal(estados[0], estados[1])
    torch.testing.assert_close(modelo.peso, estados[0])
    assert not modelo.training


@pytest.mark.parametrize("perda", ["mse", "mae", "huber"])
def test_refit_cria_modelo_novo_deterministico_e_executa_epocas_fixas(perda) -> None:
    argumentos = dict(
        tarefa=TAREFAS_CANONICAS["monthly_1"],
        configuracao=_config(),
        semente=42,
        ajuste=_janelas(),
        escalas=_escalas(),
        perda=perda,
        epocas_fixas=2,
    )
    modelo_a, epoca, historico = treino.treinar_candidato(**argumentos)
    modelo_b, _, historico_b = treino.treinar_candidato(**argumentos)
    assert modelo_a is not modelo_b
    assert epoca == 2
    assert list(historico.columns) == ["epoca", "perda_treino", "mae_validacao_wm2"]
    assert historico.mae_validacao_wm2.isna().all()
    assert np.isfinite(historico.perda_treino).all()
    pd.testing.assert_frame_equal(historico, historico_b)
    for chave, tensor in modelo_a.state_dict().items():
        torch.testing.assert_close(tensor, modelo_b.state_dict()[chave], rtol=0, atol=0)


@pytest.mark.parametrize(
    "alteracao",
    [
        {"perda": "outra"},
        {"semente": -1},
        {"semente": True},
        {"epocas_fixas": 0},
        {"epocas_fixas": 1.5},
        {"epocas_fixas": None},
        {"validacao": _janelas(ano=2023)},
    ],
)
def test_treino_rejeita_configuracao_ambigua_ou_invalida(alteracao) -> None:
    argumentos = dict(
        tarefa=TAREFAS_CANONICAS["monthly_1"],
        configuracao=_config(),
        semente=42,
        ajuste=_janelas(),
        escalas=_escalas(),
        epocas_fixas=1,
    )
    argumentos.update(alteracao)
    with pytest.raises(ValueError):
        treino.treinar_candidato(**argumentos)


def test_treino_rejeita_alvos_de_validacao_sobrepostos() -> None:
    with pytest.raises(ValueError, match="anteceder"):
        treino.treinar_candidato(
            tarefa=TAREFAS_CANONICAS["monthly_1"], configuracao=_config(), semente=42,
            ajuste=_janelas(), validacao=_janelas(), escalas=_escalas(),
        )


def test_treino_rejeita_perda_nao_finita(monkeypatch) -> None:
    class RedeInvalida(_RedeConstante):
        def forward(self, x, ids):
            return super().forward(x, ids) * math_nan

    math_nan = float("nan")
    monkeypatch.setattr(treino, "criar_modelo_neural", lambda *a, **k: RedeInvalida())
    with pytest.raises(ValueError, match="Perda de treino nao finita"):
        treino.treinar_candidato(
            tarefa=TAREFAS_CANONICAS["monthly_1"], configuracao=_config(), semente=42,
            ajuste=_janelas(), escalas=_escalas(), epocas_fixas=1,
        )


def test_ids_nao_contiguos_dimensionam_embedding_pelo_maior_id(monkeypatch) -> None:
    capturado = {}

    def criar(*args, **kwargs):
        capturado.update(kwargs)
        return _RedeConstante()

    monkeypatch.setattr(treino, "criar_modelo_neural", criar)
    escalas = _escalas()
    escalas["localidade_id"] = [2, 5]
    treino.treinar_candidato(
        tarefa=TAREFAS_CANONICAS["monthly_1"], configuracao=_config(), semente=42,
        ajuste=_janelas(ids=(2, 5)), escalas=escalas, epocas_fixas=1,
    )
    assert capturado["num_localidades"] == 6
