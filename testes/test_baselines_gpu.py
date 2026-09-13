"""Execucao GPU: mesma rede e mesmo laco, contrato distinto do da CPU."""
from pathlib import Path

import pytest

torch = pytest.importorskip("torch")

from codigo_fonte import modelos_baselines_adicionais as r
from codigo_fonte import experimento_baselines_gpu as g

DISPOSITIVOS = ["cpu", pytest.param("cuda", marks=pytest.mark.skipif(
    not torch.cuda.is_available(), reason="sem CUDA"))]


@pytest.mark.parametrize("dispositivo", DISPOSITIVOS)
@pytest.mark.parametrize("modelo", ["Transformer", "Informer"])
def test_rede_no_dispositivo_devolve_saida_na_cpu(modelo, dispositivo):
    torch.manual_seed(42)
    referencia = r.criar_baseline(modelo, 365, 30, 2).eval()
    rede = r.criar_baseline(modelo, 365, 30, 2)
    rede.load_state_dict(referencia.state_dict())
    rede = g.no_dispositivo(rede, torch.device(dispositivo)).eval()
    x, ids = torch.randn(4, 365), torch.tensor([0, 1, 0, 1])
    with torch.no_grad():
        saida = rede(x, ids)
        esperado = referencia(x, ids)
        assert torch.equal(rede(x, ids), saida)
    assert saida.device.type == "cpu"
    assert all(p.device.type == dispositivo for p in rede.parameters())
    # O Informer sorteia chaves com o gerador do proprio dispositivo; CPU e CUDA
    # geram sequencias diferentes, entao so o Transformer iguala entre eles.
    if modelo == "Transformer" or dispositivo == "cpu":
        torch.testing.assert_close(saida, esperado, atol=1e-4, rtol=1e-4)
    assert torch.isfinite(saida).all()
    rede.train()
    rede(x, ids).square().mean().backward()
    assert all(torch.isfinite(p.grad).all() for p in rede.parameters() if p.grad is not None)


def test_contrato_gpu_registra_dispositivo_e_codigo(monkeypatch):
    cpu = {"parametros": {"threads_torch": 1}, "arquivos_codigo": [], "sha256_contrato": "cpu"}
    monkeypatch.setattr(g, "_contrato_cpu", lambda ctx, modelo: {**cpu, "arquivos_codigo": []})
    monkeypatch.setattr(torch.cuda, "get_device_name", lambda _: "GPU teste")
    c = g.contrato_gpu(None, "Transformer")
    assert c["execucao"]["dispositivo"] == "cuda" and c["execucao"]["gpu"] == "GPU teste"
    assert [Path(a["arquivo"]).name for a in c["arquivos_codigo"]] == ["experimento_baselines_gpu.py"]
    assert c["sha256_contrato"] != cpu["sha256_contrato"]
    assert c["parametros"] == cpu["parametros"]


def test_recusa_sem_cuda(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError):
        g.ativar_gpu()
