import numpy as np
import pytest
import torch

from codigo_fonte.dilated_rnn_direta import (
    CamadaRNNDilatada,
    DilatedRNNDireta,
)


def test_camada_dilatada_equivale_a_recorrencia_manual():
    camada = CamadaRNNDilatada(1, 1, dilatacao=2)
    with torch.no_grad():
        camada.rnn.weight_ih_l0.fill_(0.7)
        camada.rnn.weight_hh_l0.fill_(0.4)
        camada.rnn.bias_ih_l0.fill_(0.1)
        camada.rnn.bias_hh_l0.fill_(-0.05)

    x = torch.tensor([[[0.2], [0.4], [0.6], [0.8], [1.0]]])
    obtido = camada(x)[0, :, 0]
    esperado = []
    estados = [torch.tensor(0.0), torch.tensor(0.0)]
    for indice, valor in enumerate(x[0, :, 0]):
        anterior = estados[indice % 2]
        atual = torch.tanh(0.7 * valor + 0.4 * anterior + 0.1 - 0.05)
        estados[indice % 2] = atual
        esperado.append(atual)
    assert torch.allclose(obtido, torch.stack(esperado), atol=1e-6)


def test_dilated_rnn_direta_produz_todo_o_horizonte_e_gradientes():
    torch.manual_seed(7)
    modelo = DilatedRNNDireta(
        seq_len=24,
        pred_len=7,
        dilatacoes=(1, 2, 4),
        unidades=(8, 6, 4),
        unidades_densas=5,
        num_localidades=3,
        dimensao_embedding_localidade=2,
        dropout=0.0,
    )
    x = torch.randn(9, 24)
    ids = torch.tensor([0, 1, 2] * 3)
    saida = modelo(x, ids)
    assert saida.shape == (9, 7)
    perda = saida.square().mean()
    perda.backward()
    assert all(
        parametro.grad is not None
        for parametro in modelo.parameters()
        if parametro.requires_grad
    )


def test_dilated_rnn_direta_e_deterministica_sem_dropout():
    torch.manual_seed(11)
    modelo = DilatedRNNDireta(
        seq_len=12,
        pred_len=1,
        num_localidades=2,
        dropout=0.0,
    ).eval()
    x = torch.as_tensor(np.arange(24).reshape(2, 12), dtype=torch.float32)
    ids = torch.tensor([0, 1])
    primeira = modelo(x, ids)
    segunda = modelo(x, ids)
    assert torch.equal(primeira, segunda)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seq_len": 0, "pred_len": 1, "num_localidades": 1},
        {"seq_len": 12, "pred_len": 0, "num_localidades": 1},
        {"seq_len": 12, "pred_len": 1, "num_localidades": 0},
        {
            "seq_len": 3,
            "pred_len": 1,
            "num_localidades": 1,
            "dilatacoes": (1, 4),
        },
    ],
)
def test_dilated_rnn_direta_rejeita_configuracoes_invalidas(kwargs):
    with pytest.raises(ValueError):
        DilatedRNNDireta(**kwargs)


def test_dilated_rnn_direta_rejeita_ids_fora_do_intervalo():
    modelo = DilatedRNNDireta(seq_len=12, pred_len=2, num_localidades=2)
    with pytest.raises(ValueError, match="fora do intervalo"):
        modelo(torch.zeros(1, 12), torch.tensor([2]))
