"""Testa quantizacao apenas das entradas, min-max e treino/inferencia comuns."""

from __future__ import annotations

from dataclasses import fields, replace

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
    prever_rede,
)
from codigo_fonte.quantizacao_timesnet import (
    JanelasDiretasQuantizadas,
    aplicar_quantizacao,
    diagnosticar_quantizacao,
    normalizar_entradas,
    quantizar_entradas,
)


def _janelas(ano: int = 2020) -> JanelasDiretas:
    datas = pd.date_range(f"{ano}-01-31", periods=2, freq="ME")
    return JanelasDiretas(
        x_bruto=np.array([
            [8, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22],
            [80, 100, 110, 120, 130, 140, 150, 160, 170, 180, 200, 220],
        ], dtype=np.float32),
        y_bruto=np.array([[7.125], [224.375]], dtype=np.float32),
        localidade_id=np.array([0, 1], dtype=np.int64),
        localidade=np.array(["A", "B"], dtype=object),
        origem=datas,
        datas_alvo=datas.to_numpy().reshape(2, 1),
        seq_len=12,
        pred_len=1,
        particao="ajuste" if ano == 2020 else "validacao",
    )


def _escalas() -> pd.DataFrame:
    # Ordem deliberadamente inversa: a escala deve ser associada pelo ID.
    return pd.DataFrame({
        "localidade_id": [1, 0],
        "minimo_treino_wm2": [100.0, 10.0],
        "amplitude_escala_wm2": [100.0, 10.0],
    })


@pytest.mark.parametrize("niveis", [2, 4, 64, 128, 256, np.int64(64)])
def test_grade_tem_exatamente_n_niveis_e_extremos(niveis) -> None:
    grade = np.arange(niveis, dtype=np.float64) / (int(niveis) - 1)
    resultado = quantizar_entradas(grade, niveis)
    assert resultado.dtype == np.float32
    assert len(np.unique(resultado)) == niveis
    assert resultado[0] == 0.0
    assert resultado[-1] == 1.0
    np.testing.assert_array_equal(resultado, grade.astype(np.float32))


def test_empates_usam_inteiro_par_do_numpy_rint() -> None:
    entrada = np.array([0.0, 1 / 6, 0.5, 5 / 6, 1.0])
    esperado = np.array([0.0, 0.0, 2 / 3, 2 / 3, 1.0], dtype=np.float32)
    np.testing.assert_array_equal(quantizar_entradas(entrada, 4), esperado)


@pytest.mark.parametrize("niveis", [64, 128, 256])
def test_idempotencia_e_erro_maximo_dentro_da_faixa(niveis) -> None:
    valores = np.linspace(0.0, 1.0, 20001)
    quantizados = quantizar_entradas(valores, niveis)
    np.testing.assert_array_equal(quantizar_entradas(quantizados, niveis), quantizados)
    limite = 1 / (2 * (niveis - 1)) + np.finfo(np.float32).eps
    assert np.max(np.abs(valores - quantizados)) <= limite


def test_clip_e_forma_nao_alteram_array_fonte() -> None:
    entrada = np.array([[-3.0, 0.0, 0.1], [0.8, 1.0, 3.0]], dtype=np.float64)
    original = entrada.copy()
    entrada.setflags(write=False)
    resultado = quantizar_entradas(entrada, 64)
    assert resultado.shape == entrada.shape
    assert resultado[0, 0] == 0.0
    assert resultado[-1, -1] == 1.0
    assert not np.shares_memory(entrada, resultado)
    np.testing.assert_array_equal(entrada, original)


@pytest.mark.parametrize("dtype", [np.float32, np.float64, np.int64])
def test_none_preserva_exatamente_valores_dtype_sem_clip(dtype) -> None:
    entrada = np.array([-3, -0.0, 0.123456789, 2], dtype=dtype)
    original = entrada.tobytes()
    resultado = quantizar_entradas(entrada, None)
    assert resultado.dtype == entrada.dtype
    assert resultado.tobytes() == original
    assert entrada.tobytes() == original
    assert not np.shares_memory(entrada, resultado)


@pytest.mark.parametrize("niveis", [True, False, np.bool_(True), 0, 1, -4, 64.0, "64", np.nan, np.inf, 10**400])
def test_rejeita_niveis_invalidos(niveis) -> None:
    with pytest.raises(ValueError, match="niveis"):
        quantizar_entradas(np.array([0.5]), niveis)
    with pytest.raises(ValueError, match="niveis"):
        aplicar_quantizacao(_janelas(), niveis)


@pytest.mark.parametrize("niveis", [None, 64])
@pytest.mark.parametrize("entrada", [[np.nan], [np.inf], [-np.inf], [1 + 2j], [True], ["0.2"]])
def test_rejeita_entradas_nao_finitas_ou_nao_reais(entrada, niveis) -> None:
    with pytest.raises(ValueError, match="reais finitos"):
        quantizar_entradas(np.asarray(entrada), niveis)


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_adaptador_preserva_alvos_metadados_minmax_e_inversao(niveis) -> None:
    fonte = _janelas()
    escalas = _escalas()
    copia_escalas = escalas.copy(deep=True)
    x_original = fonte.x_bruto.copy()
    y_original = fonte.y_bruto.copy()
    x, y = fonte.normalizar(escalas)
    adaptadas = aplicar_quantizacao(fonte, niveis)
    assert isinstance(adaptadas, JanelasDiretasQuantizadas)
    assert isinstance(adaptadas, JanelasDiretas)
    assert adaptadas is not fonte
    for campo in fields(JanelasDiretas):
        assert getattr(adaptadas, campo.name) is getattr(fonte, campo.name)
    x_quantizado, y_continuo = adaptadas.normalizar(escalas)
    np.testing.assert_array_equal(x_quantizado, quantizar_entradas(x, niveis))
    np.testing.assert_array_equal(y_continuo, y)
    assert y_continuo[0, 0] < 0 and y_continuo[1, 0] > 1
    # Previsoes tambem permanecem continuas e nao sao limitadas/quantizadas.
    previsto = np.array([[-0.123456], [1.234567]])
    np.testing.assert_array_equal(adaptadas.inverter(previsto, escalas), fonte.inverter(previsto, escalas))
    assert treino.macro_mae_fisico(adaptadas, previsto, escalas) == treino.macro_mae_fisico(fonte, previsto, escalas)
    np.testing.assert_array_equal(fonte.x_bruto, x_original)
    np.testing.assert_array_equal(fonte.y_bruto, y_original)
    pd.testing.assert_frame_equal(escalas, copia_escalas)


def test_reaplicar_adaptador_nao_acumula_quantizacao() -> None:
    janelas = _janelas()
    direto = aplicar_quantizacao(janelas, 128)
    reaplicado = aplicar_quantizacao(aplicar_quantizacao(janelas, 64), 128)
    np.testing.assert_array_equal(direto.normalizar(_escalas())[0], reaplicado.normalizar(_escalas())[0])


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_inferencia_equivale_ao_treino_sem_consultar_alvo(niveis) -> None:
    janelas = _janelas()
    x_treino, _ = aplicar_quantizacao(janelas, niveis).normalizar(_escalas())
    x_inferencia = normalizar_entradas(janelas, _escalas(), niveis)
    np.testing.assert_array_equal(x_treino, x_inferencia)
    # Um alvo indisponivel nao deve participar nem mesmo da preparacao de x.
    janelas.y_bruto[:] = np.nan
    np.testing.assert_array_equal(normalizar_entradas(janelas, _escalas(), niveis), x_inferencia)


@pytest.mark.parametrize("problema", ["ausente", "duplicada", "coluna", "zero", "negativa", "nan", "inf"])
def test_inferencia_rejeita_escalas_invalidas(problema) -> None:
    escalas = _escalas()
    if problema == "ausente":
        escalas = escalas.iloc[:1]
    elif problema == "duplicada":
        escalas = pd.concat([escalas, escalas.iloc[:1]])
    elif problema == "coluna":
        escalas = escalas.drop(columns="minimo_treino_wm2")
    else:
        escalas.loc[0, "amplitude_escala_wm2"] = {"zero": 0, "negativa": -1, "nan": np.nan, "inf": np.inf}[problema]
    with pytest.raises(ValueError):
        normalizar_entradas(_janelas(), escalas, 64)


def test_diagnostico_distingue_arredondamento_saturacao_e_controle() -> None:
    entrada = np.array([-0.1, 0.0, 0.125, 0.5, 1.0, 1.1])
    dados = diagnosticar_quantizacao(entrada, 3)
    assert dados == {
        "niveis": 3, "total": 6, "alterados": 3, "fracao_alterados": 0.5,
        "abaixo_zero": 1, "acima_um": 1, "saturados": 2, "fracao_saturados": 2 / 6,
    }
    controle = diagnosticar_quantizacao(entrada, None)
    assert controle["alterados"] == controle["saturados"] == 0
    assert controle["abaixo_zero"] == controle["acima_um"] == 1
    assert diagnosticar_quantizacao(np.array([]), 64)["fracao_alterados"] == 0


class _RedeObservada(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.peso = nn.Parameter(torch.tensor(0.0))
        self.entradas_treino = []

    def forward(self, x, ids):
        if self.training:
            self.entradas_treino.append(x.detach().clone().numpy())
        return x.mean(dim=1, keepdim=True) + self.peso


@pytest.mark.parametrize("com_validacao", [False, True])
def test_treinador_recebe_x_quantizado_y_continuo_e_inferencia_independe_de_y(monkeypatch, com_validacao) -> None:
    alvos_da_perda = []

    class PerdaObservada(nn.MSELoss):
        def forward(self, previsto, alvo):
            alvos_da_perda.append(alvo.detach().clone().numpy())
            return super().forward(previsto, alvo)

    monkeypatch.setattr(treino, "criar_modelo_neural", lambda *args, **kwargs: _RedeObservada())
    monkeypatch.setattr(treino.nn, "MSELoss", PerdaObservada)
    fonte = _janelas()
    escalas = _escalas()
    quantizadas = aplicar_quantizacao(fonte, 64)
    config = ConfiguracaoMultirresolucao(max_epocas_mensal=1, paciencia_mensal=1)
    argumentos = {"validacao": aplicar_quantizacao(_janelas(2023), 64)} if com_validacao else {"epocas_fixas": 1}
    modelo, epocas, historico = treino.treinar_candidato(
        tarefa=TAREFAS_CANONICAS["monthly_1"], configuracao=config, semente=11,
        ajuste=quantizadas, escalas=escalas, **argumentos,
    )
    assert epocas == 1
    x_esperado, y_esperado = quantizadas.normalizar(escalas)
    np.testing.assert_array_equal(np.sort(np.concatenate(modelo.entradas_treino), axis=0), np.sort(x_esperado, axis=0))
    np.testing.assert_array_equal(np.sort(np.concatenate(alvos_da_perda), axis=0), np.sort(y_esperado, axis=0))
    assert np.isfinite(historico.perda_treino).all()
    if com_validacao:
        assert np.isfinite(historico.mae_validacao_wm2).all()
    x = normalizar_entradas(fonte, escalas, 64)
    antes = prever_rede(modelo, x, fonte.localidade_id, batch_size=32)
    outro_alvo = replace(fonte, y_bruto=fonte.y_bruto + 10000)
    depois = prever_rede(modelo, normalizar_entradas(outro_alvo, escalas, 64), outro_alvo.localidade_id, batch_size=32)
    np.testing.assert_array_equal(antes, depois)