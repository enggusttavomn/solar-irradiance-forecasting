"""Equivalencia do controle e isolamento da quantizacao horaria/diaria."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn
from torch.utils.data import TensorDataset

from codigo_fonte.experimentos import experimento_multirresolucao as base
from codigo_fonte.experimentos import treinamento_timesnet_resolucoes as original
from codigo_fonte.experimentos import treinamento_timesnet_quantizado_resolucoes as treino
from codigo_fonte.experimentos.experimento_horario_timesnet import JanelasHorarias
from codigo_fonte.experimentos.quantizacao_timesnet import quantizar_entradas


def _escalas():
    return pd.DataFrame({"localidade_id": [0, 1], "minimo_treino_wm2": [10., 100.],
                         "amplitude_escala_wm2": [10., 100.]})


def _tarefa(horaria):
    fonte = base.TAREFA_HORARIA_EXTENSAO if horaria else base.TAREFAS_CANONICAS["daily_30"]
    return replace(fonte, seq_len=12, pred_len=2, horizontes=(1, 2))


def _janelas(horaria, ano=2020):
    tarefa = _tarefa(horaria)
    ids = np.array([0, 0, 0, 1, 1], dtype=np.int64)
    minimo = np.where(ids == 0, 10., 100.).astype(np.float32)[:, None]
    amplitude = minimo.copy()
    # Valores fora da faixa verificam que somente a variante quantizada satura.
    x = np.linspace(-0.1, 1.2, len(ids) * tarefa.seq_len, dtype=np.float32).reshape(len(ids), -1)
    y = np.linspace(0.41329, 1.12137, len(ids) * tarefa.pred_len, dtype=np.float32).reshape(len(ids), -1)
    comum = dict(x_bruto=minimo + amplitude * x, y_bruto=minimo + amplitude * y,
                 localidade_id=ids, localidade=np.array([f"Local {i}" for i in ids]),
                 seq_len=tarefa.seq_len, pred_len=tarefa.pred_len, particao="ajuste")
    datas = pd.date_range(f"{ano}-01-01", periods=len(ids), freq="D")
    if horaria:
        return JanelasHorarias(**comum, origem_utc=datas.tz_localize("UTC"), origem_local=datas)
    alvos = datas.to_numpy()[:, None] + np.arange(tarefa.pred_len)[None, :] * np.timedelta64(1, "D")
    return base.JanelasDiretas(**comum, origem=datas, datas_alvo=alvos)


def _config(**kw):
    return replace(base.ConfiguracaoMultirresolucao(
        max_epocas_diario=3, paciencia_diario=2, batch_size_diario=3,
        timesnet_d_model=4, timesnet_d_ff=8, timesnet_top_k=1, timesnet_kernels=1,
        threads_torch=1,
    ), **kw)


@pytest.mark.parametrize("horaria", [False, True])
@pytest.mark.parametrize("selecao", [False, True])
@pytest.mark.parametrize("perda", ["mae", "mse", "huber"])
def test_none_reproduz_exatamente_treinador_original(horaria, selecao, perda):
    ajuste = _janelas(horaria)
    argumentos = dict(tarefa=_tarefa(horaria), config=_config(), semente=23,
                     ajuste=ajuste, escalas=_escalas(), perda=perda)
    if selecao:
        argumentos["validacao"] = _janelas(horaria, 2023)
        if horaria:
            argumentos["elevacao_validacao"] = np.tile([-5., 30.], (5, 1))
    else:
        argumentos["epocas_fixas"] = 2
    esperado, epocas, historico = original.treinar(**argumentos)
    rng_esperado = torch.random.get_rng_state().clone()
    obtido, epocas_quant, historico_quant = treino.treinar(**argumentos, niveis=None)
    torch.testing.assert_close(torch.random.get_rng_state(), rng_esperado, rtol=0, atol=0)
    assert epocas_quant == epocas
    pd.testing.assert_frame_equal(historico.drop(columns="segundos"), historico_quant.drop(columns="segundos"))
    for nome, tensor in esperado.state_dict().items():
        torch.testing.assert_close(tensor, obtido.state_dict()[nome], rtol=0, atol=0)
    np.testing.assert_array_equal(original.prever(esperado, ajuste, _escalas(), 2),
                                  treino.prever(obtido, ajuste, _escalas(), 2, niveis=None))
    assert not obtido.training and next(obtido.parameters()).device.type == "cpu"


class _Espia(nn.Module):
    def __init__(self, passos=2):
        super().__init__()
        self.peso = nn.Parameter(torch.tensor(0.31415927))
        self.passos = passos
        self.entradas = []

    def forward(self, x, ids):
        self.entradas.append((self.training, x.detach().cpu().numpy().copy(), ids.detach().cpu().numpy().copy()))
        # Saida deliberadamente continua, fora dos pontos de quantizacao.
        return self.peso.expand(len(x), self.passos)


@pytest.mark.parametrize("horaria", [False, True])
@pytest.mark.parametrize("niveis", [64, 128, 256])
def test_aplica_mesmos_niveis_no_treino_validacao_inferencia_sem_mudar_alvos(monkeypatch, horaria, niveis):
    ajuste, validacao, escalas = _janelas(horaria), _janelas(horaria, 2023), _escalas()
    originais = (ajuste.x_bruto.copy(), ajuste.y_bruto.copy(), validacao.x_bruto.copy(), validacao.y_bruto.copy())
    datasets = []

    def capturar_dataset(*tensores):
        datasets.append(tuple(t.detach().cpu().numpy().copy() for t in tensores))
        return TensorDataset(*tensores)

    espia = _Espia()
    monkeypatch.setattr(treino, "TensorDataset", capturar_dataset)
    monkeypatch.setattr(base, "criar_modelo_neural", lambda *a, **k: espia)
    argumentos = dict(tarefa=_tarefa(horaria), config=_config(max_epocas_diario=1), semente=11,
                     ajuste=ajuste, validacao=validacao, escalas=escalas, niveis=niveis)
    if horaria:
        argumentos["elevacao_validacao"] = np.tile([-5., 30.], (5, 1))
    modelo, epocas, historico = treino.treinar(**argumentos)
    assert epocas == len(historico) == 1
    x_esperado = quantizar_entradas(original._normalizar_contexto(ajuste, escalas), niveis)
    _, y_esperado = ajuste.normalizar(escalas)
    np.testing.assert_array_equal(datasets[0][0], x_esperado)
    np.testing.assert_array_equal(datasets[0][1], y_esperado)
    np.testing.assert_array_equal(datasets[0][2], ajuste.localidade_id)
    assert np.any(y_esperado != quantizar_entradas(y_esperado, niveis))
    assert x_esperado.min() == 0. and x_esperado.max() == 1.
    grade = (np.arange(niveis, dtype=np.float64) / (niveis - 1)).astype(np.float32)
    for _, contexto, _ in modelo.entradas:
        assert np.isin(contexto, grade).all()
    avaliadas = np.concatenate([x for treinando, x, _ in modelo.entradas if not treinando])
    np.testing.assert_array_equal(avaliadas, x_esperado)
    bruto = treino.prever(modelo, validacao, escalas, batch_size=2, niveis=niveis)
    tabela = escalas.set_index("localidade_id").loc[validacao.localidade_id]
    esperado = np.full((5, 2), float(modelo.peso.detach())) * tabela.amplitude_escala_wm2.to_numpy()[:, None]
    esperado += tabela.minimo_treino_wm2.to_numpy()[:, None]
    np.testing.assert_array_equal(bruto, esperado)
    assert not np.isin(float(modelo.peso.detach()), grade)
    for real, copiado in zip((ajuste.x_bruto, ajuste.y_bruto, validacao.x_bruto, validacao.y_bruto), originais):
        np.testing.assert_array_equal(real, copiado)


@pytest.mark.parametrize("horaria", [False, True])
@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_inferencia_independe_dos_alvos_inclusive_ausentes(horaria, niveis):
    fonte = _janelas(horaria)
    campos = {nome: getattr(fonte, nome) for nome in ("x_bruto", "localidade_id", "localidade", "seq_len", "pred_len")}
    sem_alvo = SimpleNamespace(**campos)
    alvo_invalido = SimpleNamespace(**campos, y_bruto=np.full((5, 2), np.nan))
    modelo = _Espia()
    esperado = treino.prever(modelo, fonte, _escalas(), 2, niveis=niveis)
    np.testing.assert_array_equal(esperado, treino.prever(modelo, sem_alvo, _escalas(), 2, niveis=niveis))
    np.testing.assert_array_equal(esperado, treino.prever(modelo, alvo_invalido, _escalas(), 2, niveis=niveis))


def test_macro_mae_preserva_piso_mascara_e_peso_por_localidade():
    janela = _janelas(True)
    previsto = np.array([[-10., 20.], [10., -10.], [30., 50.], [100., 200.], [200., -10.]])
    elevacao = np.tile([-2., 5.], (5, 1))
    esperado = np.maximum(previsto, 0.)
    esperado[elevacao <= 0.] = 0.
    maes = [np.abs(esperado[janela.localidade_id == i] - janela.y_bruto[janela.localidade_id == i]).mean()
            for i in (0, 1)]
    assert treino.macro_mae_fisico is original.macro_mae_fisico
    assert treino.macro_mae_fisico(janela, previsto, elevacao) == np.mean(maes)
    assert previsto[0, 0] == -10.


@pytest.mark.parametrize("niveis", [True, 1, 0, 64.0, "128"])
def test_niveis_invalidos_rejeitados_antes_de_criar_modelo(monkeypatch, niveis):
    def nao_criar(*args, **kwargs):
        pytest.fail("Nao deve criar o modelo antes de validar niveis.")

    monkeypatch.setattr(base, "criar_modelo_neural", nao_criar)
    with pytest.raises(ValueError, match="niveis"):
        treino.treinar(tarefa=_tarefa(False), config=_config(), semente=11, ajuste=_janelas(False),
                      escalas=_escalas(), niveis=niveis, epocas_fixas=1)


@pytest.mark.parametrize("horaria", [False, True])
def test_rejeita_identidade_e_forma_incompativeis(horaria):
    janela = _janelas(horaria)
    alterada = replace(janela, localidade=np.array(["A", "B", "A", "C", "C"]))
    with pytest.raises(ValueError, match="correspondencia unica"):
        treino.prever(_Espia(), alterada, _escalas(), niveis=64)
    with pytest.raises(ValueError, match="forma de saida"):
        treino.prever(_Espia(3), janela, _escalas(), niveis=64)


@pytest.mark.parametrize("horaria", [False, True])
def test_rejeita_sobreposicao_temporal_e_mantem_exigencia_de_mascara(horaria):
    janela = _janelas(horaria)
    argumentos = dict(tarefa=_tarefa(horaria), config=_config(), semente=11,
                     ajuste=janela, validacao=janela, escalas=_escalas(), niveis=128)
    if horaria:
        with pytest.raises(ValueError, match="exige elevacao"):
            treino.treinar(**argumentos)
        argumentos["elevacao_validacao"] = np.ones((5, 2))
    with pytest.raises(ValueError, match="anteceder"):
        treino.treinar(**argumentos)


@pytest.mark.parametrize("horaria", [False, True])
def test_none_preserva_valores_fora_da_faixa_e_dtype(horaria):
    janela = _janelas(horaria)
    esperado = original._normalizar_contexto(janela, _escalas())
    obtido = treino._normalizar_contexto(janela, _escalas())
    assert obtido.dtype == esperado.dtype == np.float32
    assert obtido.min() < 0. and obtido.max() > 1.
    np.testing.assert_array_equal(obtido, esperado)
