"""Invariantes das arquiteturas adicionais e da consolidacao sem vazamento."""
import inspect
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

torch = pytest.importorskip("torch")
from torch.nn import functional as F

from codigo_fonte.modelos import modelos_baselines_adicionais as r
from codigo_fonte.experimentos import experimento_baselines_adicionais as e
from codigo_fonte.analises_e_relatorios import consolidar_baselines_adicionais as c


@pytest.mark.parametrize("modelo", ["GRU", "Transformer", "Informer"])
@pytest.mark.parametrize("seq,pred", [(12, 1), (12, 6), (365, 30), (336, 72)])
def test_shapes_gradientes_e_determinismo(modelo, seq, pred):
    torch.set_num_threads(1)
    torch.manual_seed(42)
    rede = r.criar_baseline(modelo, seq, pred, 2)
    x, ids = torch.randn(2, seq), torch.tensor([0, 1])
    y = rede(x, ids)
    assert y.shape == (2, pred)
    assert torch.isfinite(y).all()
    y.square().mean().backward()
    assert all(torch.isfinite(p.grad).all() for p in rede.parameters() if p.grad is not None)
    rede.eval()
    with torch.no_grad():
        lote = rede(x, ids)
        estado_rng = torch.get_rng_state().clone()
        outra = rede(x, ids)
        assert torch.equal(estado_rng, torch.get_rng_state())
        separadas = torch.cat([rede(x[i:i+1], ids[i:i+1]) for i in range(2)])
    torch.testing.assert_close(lote, outra, atol=1e-6, rtol=1e-6)
    torch.testing.assert_close(lote, separadas, atol=2e-6, rtol=2e-6)


@pytest.mark.parametrize("causal", [False, True])
def test_probesparse_equivale_completa_quando_todas_queries_selecionadas(causal):
    torch.manual_seed(1)
    a = r.AtencaoProjetada(esparsa=True, causal=causal, fator=100, dropout=0).eval()
    q, k, v = (torch.randn(2, 2, 12, 8) for _ in range(3))
    esperado = F.scaled_dot_product_attention(q, k, v, is_causal=causal)
    torch.testing.assert_close(a._probsparse(q, k, v), esperado, atol=1e-6, rtol=1e-6)


def test_informer_tem_probesparse_distilacao_e_decoder_sem_alvos():
    rede = r.TransformerDireto(12, 6, 2, informer=True)
    assert isinstance(rede.distilacao, r.Distilacao)
    assert rede.encoders[0].atencao.esparsa
    assert rede.decoder.autoatencao.esparsa
    assert rede.decoder.autoatencao.causal
    assert not rede.decoder.cruzada.esparsa
    assert list(inspect.signature(rede.forward).parameters) == ["x", "ids"]
    x = torch.arange(24, dtype=torch.float32).reshape(2, 12)
    dec = rede.entrada_decoder(x)
    torch.testing.assert_close(dec[:, :6, 0], x[:, -6:])
    assert dec[:, -6:, :].count_nonzero() == 0
    assert rede.distilacao(torch.randn(2, 12, 16)).shape == (2, 6, 16)


def test_transformer_nao_usa_probesparse_ou_distilacao():
    rede = r.TransformerDireto(12, 6, 2)
    assert isinstance(rede.distilacao, torch.nn.Identity)
    assert not rede.encoders[0].atencao.esparsa
    assert not rede.decoder.autoatencao.esparsa


def test_metricas_mse_e_denominadores_indefinidos():
    met = c.metricas_vetor(np.array([1, 3]), np.array([2, 1]))
    assert met["MAE_wm2"] == 1.5
    assert met["MSE_w2m4"] == 2.5
    assert met["RMSE_wm2"] == pytest.approx(np.sqrt(2.5))
    zero = c.metricas_vetor(np.zeros(2), np.zeros(2))
    assert zero["MSE_w2m4"] == 0
    assert np.isnan(zero["R2"]) and np.isnan(zero["nRMSE"])
    with pytest.raises(ValueError):
        c.metricas_vetor(np.array([np.nan]), np.array([0]))


def test_macro_mse_nao_e_quadrado_macro_rmse():
    tabela = pd.DataFrame({"localidade": ["A", "A", "B", "B"], "origem": [1, 2, 1, 2],
        "passo": [1, 1, 1, 1], "ghi_real_wm2": [1., 1., 2., 2.],
        "previsao_pos_gru_seed42_wm2": [2., 2., 5., 5.]})
    tarefa = SimpleNamespace(resolucao="mensal", horizontes=[1], slug="sintetica")
    _, macro = c.avaliar(tabela, tarefa, "teste_2024")
    assert macro.iloc[0].MSE_w2m4 == 5.0
    assert macro.iloc[0].RMSE_wm2 ** 2 == 4.0


def test_alinhamento_exige_chaves_alvos_e_sem_sobrescrita():
    a = pd.DataFrame({"localidade": ["A", "A"], "origem": ["2024-01-01"] * 2,
        "data_alvo": ["2024-01-01", "2024-01-02"], "passo": [1, 2], "ghi_real_wm2": [1., 2.]})
    b = a.iloc[::-1].copy()
    b["previsao_pos_gru_seed42_wm2"] = [10., 20.]
    junto = c.alinhar(a, b, False)
    assert junto.previsao_pos_gru_seed42_wm2.tolist() == [20., 10.]
    with pytest.raises(ValueError):
        c.alinhar(a, b.iloc[:1], False)
    with pytest.raises(ValueError):
        c.alinhar(junto, b, False)
    b.loc[b.index[0], "ghi_real_wm2"] = 100.
    with pytest.raises(ValueError):
        c.alinhar(a, b, False)


def test_arima_aplica_so_contexto_fixo_sem_refit():
    class Ajustado:
        def __init__(self):
            self.contextos = []
        def apply(self, x, refit):
            assert refit is False
            self.contextos.append(x.copy())
            return SimpleNamespace(forecast=lambda n: np.repeat(x[-1], n))
    ajuste = Ajustado()
    x = np.array([[1., 2., 3.], [4., 5., 6.]])
    np.testing.assert_equal(e.previsoes_arima_fixos(ajuste, x, 2), [[3, 3], [6, 6]])
    np.testing.assert_equal(ajuste.contextos, x)


def test_retoma_contrato_e_recusa_mudanca(tmp_path, monkeypatch):
    ctx = SimpleNamespace(tarefa=SimpleNamespace(slug="sintetica"))
    monkeypatch.setattr(e, "contrato", lambda ctx, modelo: {"valor": 1})
    destino = e.preparar_destino(ctx, "GRU", tmp_path)
    assert e.preparar_destino(ctx, "GRU", tmp_path) == destino
    monkeypatch.setattr(e, "contrato", lambda ctx, modelo: {"valor": 2})
    with pytest.raises(RuntimeError):
        e.preparar_destino(ctx, "GRU", tmp_path)


def test_fonte_canonica_nunca_e_destino():
    ctx = SimpleNamespace(tarefa=SimpleNamespace(slug="monthly_1"))
    with pytest.raises(ValueError):
        e.preparar_destino(ctx, "GRU", e.FONTE)
