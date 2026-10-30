"""Regressoes para treino/predicao TimesNet com metrica fisica e isolamento."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn

from codigo_fonte.experimentos import experimento_multirresolucao as base
from codigo_fonte.experimentos.experimento_horario_timesnet import JanelasHorarias
from codigo_fonte.experimentos import treinamento_timesnet_resolucoes as treino


def _escalas():
    return pd.DataFrame({"localidade_id": [0, 1], "minimo_treino_wm2": [10., 100.],
                         "amplitude_escala_wm2": [10., 100.]})


def _tarefa(horaria=False):
    origem = base.TAREFA_HORARIA_EXTENSAO if horaria else base.TAREFAS_CANONICAS["monthly_1"]
    return replace(origem, seq_len=12, pred_len=2 if horaria else 1, horizontes=(2,) if horaria else (1,))


def _janelas(horaria=False, ano=2020, ids=(0, 0, 0, 1)):
    tarefa = _tarefa(horaria)
    ids = np.asarray(ids, dtype=np.int64)
    n = len(ids)
    valores = np.where(ids == 0, 20., 200.).astype(np.float32)[:, None]
    metadados = dict(x_bruto=np.repeat(valores, tarefa.seq_len, axis=1),
                    y_bruto=np.repeat(valores, tarefa.pred_len, axis=1),
                    localidade_id=ids, localidade=np.array([f"Local {i}" for i in ids]),
                    seq_len=tarefa.seq_len, pred_len=tarefa.pred_len, particao="ajuste")
    if horaria:
        datas = pd.date_range(f"{ano}-01-01", periods=n, freq="D", tz="UTC")
        return JanelasHorarias(**metadados, origem_utc=datas, origem_local=datas.tz_localize(None))
    datas = pd.date_range(f"{ano}-01-31", periods=n, freq="ME")
    return base.JanelasDiretas(**metadados, origem=datas, datas_alvo=datas.to_numpy()[:, None])


def _config(**kw):
    return replace(base.ConfiguracaoMultirresolucao(
        max_epocas_diario=2, paciencia_diario=1, max_epocas_mensal=3, paciencia_mensal=1,
        timesnet_d_model=4, timesnet_d_ff=8, timesnet_top_k=1, timesnet_kernels=1,
    ), **kw)


def test_macro_mae_da_peso_igual_a_localidades_e_aplica_piso():
    janelas = _janelas()
    assert treino.macro_mae_fisico(janelas, np.array([[19.], [19.], [19.], [210.]])) == 5.5
    assert treino.macro_mae_fisico(janelas, np.full((4, 1), -10.)) == 110.


def test_mascara_solar_zera_noite_sem_descartar_alvo():
    janelas = _janelas(True, ids=(0, 1))
    elevacao = np.array([[-1., 0.], [0., 1.]])
    previsto = np.array([[100., -20.], [200., 210.]])
    # Local 0: (20+20)/2=20. Local 1: (200+10)/2=105. Macro=62.5.
    assert treino.macro_mae_fisico(janelas, previsto, elevacao) == 62.5
    np.testing.assert_array_equal(previsto, [[100., -20.], [200., 210.]])


@pytest.mark.parametrize("elevacao", [np.zeros((2,)), np.full((2, 2), np.nan)])
def test_mascara_invalida_e_rejeitada(elevacao):
    with pytest.raises(ValueError, match="Elevacao"):
        treino.macro_mae_fisico(_janelas(True, ids=(0, 1)), np.zeros((2, 2)), elevacao)


class _Constante(nn.Module):
    def __init__(self, passos=1):
        super().__init__()
        self.peso = nn.Parameter(torch.tensor(0.))
        self.passos = passos

    def forward(self, x, ids):
        return self.peso.expand(len(x), self.passos)


def test_prever_nao_acessa_alvos_e_retorna_ghi_bruto():
    fonte = _janelas(ids=(0, 1))
    # Este objeto deliberadamente nem possui y_bruto ou normalizar/inverter.
    entrada = SimpleNamespace(**{nome: getattr(fonte, nome) for nome in
        ("x_bruto", "localidade_id", "localidade", "seq_len", "pred_len")})
    bruto = treino.prever(_Constante(), entrada, _escalas(), batch_size=1)
    np.testing.assert_array_equal(bruto, [[10.], [100.]])


def test_selecao_restaura_estado_de_menor_mae_fisico(monkeypatch):
    estados = []
    erros = (np.array([[8.], [1.]]), np.array([[1.], [10.]]))

    def prever(modelo, janelas, *args):
        estados.append(modelo.peso.detach().clone())
        return janelas.y_bruto + erros[len(estados) - 1]

    monkeypatch.setattr(base, "criar_modelo_neural", lambda *a, **k: _Constante())
    monkeypatch.setattr(treino, "prever", prever)
    modelo, epocas, historico = treino.treinar(
        tarefa=_tarefa(), config=_config(), semente=42,
        ajuste=_janelas(ids=(0, 1)), validacao=_janelas(ano=2023, ids=(0, 1)), escalas=_escalas())
    assert epocas == 1
    np.testing.assert_allclose(historico.mae_validacao_wm2, [4.5, 5.5])
    torch.testing.assert_close(modelo.peso, estados[0])
    assert not torch.equal(estados[0], estados[1])
    assert (historico.segundos >= 0).all()


@pytest.mark.parametrize("horaria", [False, True])
@pytest.mark.parametrize("perda", ["mse", "mae", "huber"])
def test_refit_fresco_deterministico_e_checkpoint_reproduz_previsoes(tmp_path, horaria, perda):
    tarefa, config, janelas = _tarefa(horaria), _config(), _janelas(horaria)
    argumentos = dict(tarefa=tarefa, config=config, semente=42,
                     ajuste=janelas, escalas=_escalas(), epocas_fixas=2, perda=perda)
    modelo, epocas, historico = treino.treinar(**argumentos)
    outro, _, segundo_historico = treino.treinar(**argumentos)
    assert modelo is not outro and epocas == 2
    assert not modelo.training and next(modelo.parameters()).device.type == "cpu"
    assert historico.mae_validacao_wm2.isna().all()
    pd.testing.assert_frame_equal(historico.drop(columns="segundos"), segundo_historico.drop(columns="segundos"))
    for chave, tensor in modelo.state_dict().items():
        torch.testing.assert_close(tensor, outro.state_dict()[chave], rtol=0, atol=0)
    checkpoint = tmp_path / "rede.pt"
    torch.save(modelo.state_dict(), checkpoint)
    restaurado = base.criar_modelo_neural("TimesNet", tarefa=tarefa, configuracao=config, num_localidades=2, semente=9)
    restaurado.load_state_dict(torch.load(checkpoint, weights_only=True))
    previsto = treino.prever(modelo, janelas, _escalas(), 2)
    assert previsto.shape == (len(janelas.x_bruto), tarefa.pred_len)
    np.testing.assert_array_equal(previsto, treino.prever(restaurado, janelas, _escalas(), 2))


def test_horaria_usa_limites_diarios_e_exige_elevacao(monkeypatch):
    monkeypatch.setattr(base, "criar_modelo_neural", lambda *a, **k: _Constante(2))
    argumentos = dict(tarefa=_tarefa(True), config=_config(max_epocas_diario=1), semente=1,
                     ajuste=_janelas(True), validacao=_janelas(True, ano=2023), escalas=_escalas())
    with pytest.raises(ValueError, match="exige elevacao"):
        treino.treinar(**argumentos)
    _, epocas, historico = treino.treinar(**argumentos, elevacao_validacao=np.ones((4, 2)))
    assert epocas == len(historico) == 1


@pytest.mark.parametrize("horaria", [False, True])
def test_rejeita_sobreposicao_dos_alvos(horaria):
    janelas = _janelas(horaria)
    argumentos = dict(tarefa=_tarefa(horaria), config=_config(), semente=1,
                     ajuste=janelas, validacao=janelas, escalas=_escalas())
    if horaria:
        argumentos["elevacao_validacao"] = np.ones_like(janelas.y_bruto)
    with pytest.raises(ValueError, match="anteceder"):
        treino.treinar(**argumentos)


def test_rejeita_horizonte_horario_que_atravessa_validacao():
    ajuste = _janelas(True, ids=(0,))
    validacao = replace(ajuste, origem_utc=ajuste.origem_utc + pd.Timedelta(hours=1),
                       origem_local=ajuste.origem_local + pd.Timedelta(hours=1))
    with pytest.raises(ValueError, match="anteceder"):
        treino.treinar(tarefa=_tarefa(True), config=_config(), semente=1, ajuste=ajuste,
                      validacao=validacao, escalas=_escalas(), elevacao_validacao=np.ones((1, 2)))


@pytest.mark.parametrize("alteracoes", [{"perda": "incorreta"}, {"semente": True},
    {"epocas_fixas": 0}, {"epocas_fixas": None}, {"validacao": _janelas(ano=2023)},
    {"elevacao_validacao": np.ones((4, 1))}])
def test_argumentos_ambiguos_ou_invalidos(alteracoes):
    argumentos = dict(tarefa=_tarefa(), config=_config(), semente=1,
                     ajuste=_janelas(), escalas=_escalas(), epocas_fixas=1)
    argumentos.update(alteracoes)
    with pytest.raises(ValueError):
        treino.treinar(**argumentos)


def test_rejeita_saida_nao_finita(monkeypatch):
    class Invalida(_Constante):
        def forward(self, x, ids):
            return super().forward(x, ids) * float("nan")

    monkeypatch.setattr(base, "criar_modelo_neural", lambda *a, **k: Invalida())
    with pytest.raises(ValueError, match="Perda de treino nao finita"):
        treino.treinar(tarefa=_tarefa(), config=_config(), semente=1,
                      ajuste=_janelas(), escalas=_escalas(), epocas_fixas=1)
    with pytest.raises(ValueError, match="Previsao fisica"):
        treino.prever(Invalida(), _janelas(), _escalas())


def test_cortes_horarios_respeitam_fuso_de_cada_localidade(monkeypatch):
    monkeypatch.setattr(base, "criar_modelo_neural", lambda *a, **k: _Constante(2))
    fonte = _janelas(True, ids=(0, 1))
    # 22h locais em fusos +10 e -5: ultimos alvos de ajuste sao 23h locais.
    ajuste = replace(fonte,
        origem_utc=pd.DatetimeIndex(["2022-12-31T12:00Z", "2023-01-01T03:00Z"]),
        origem_local=pd.DatetimeIndex(["2022-12-31T22:00", "2022-12-31T22:00"]))
    validacao = replace(fonte,
        origem_utc=pd.DatetimeIndex(["2022-12-31T14:00Z", "2023-01-01T05:00Z"]),
        origem_local=pd.DatetimeIndex(["2023-01-01T00:00", "2023-01-01T00:00"]))
    # O maximo UTC global do ajuste ultrapassa o minimo global da validacao.
    # Mesmo assim, cada serie individual possui separacao temporal correta.
    _, epocas, historico = treino.treinar(
        tarefa=_tarefa(True), config=_config(max_epocas_diario=1), semente=1,
        ajuste=ajuste, validacao=validacao, escalas=_escalas(),
        elevacao_validacao=np.ones((2, 2)))
    assert epocas == len(historico) == 1
