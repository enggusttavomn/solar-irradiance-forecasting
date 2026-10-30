import numpy as np
import pytest
from types import SimpleNamespace

pytest.importorskip("torch")
pytest.importorskip("statsmodels")

from codigo_fonte.experimentos import experimento_arima_robusto as ar


@pytest.mark.parametrize("primeiro_converge,esperados", [(True, ["lbfgs"]), (False, ["lbfgs", "powell"])])
def test_contingencia_so_por_convergencia(monkeypatch, primeiro_converge, esperados):
    chamadas = []
    class Fake:
        def __init__(self, y, order):
            np.testing.assert_equal(y, [1, 2, 3])
            assert order == (2, 0, 2)
        def fit(self, method_kwargs):
            metodo = method_kwargs["method"]
            chamadas.append(metodo)
            return SimpleNamespace(mle_retvals={"converged": primeiro_converge or metodo == "powell"}, params=np.ones(3), llf=-1.)
    monkeypatch.setattr(ar, "ARIMA", Fake)
    _, tentativas = ar.ajustar(np.array([1, 2, 3]), (2, 0, 2))
    assert chamadas == esperados
    assert len(tentativas) == len(esperados)


def test_erro_se_ambos_nao_convergem(monkeypatch):
    class Fake:
        def __init__(self, *args, **kwargs):
            pass
        def fit(self, method_kwargs):
            return SimpleNamespace(mle_retvals={"converged": False}, params=np.ones(3), llf=-1.)
    monkeypatch.setattr(ar, "ARIMA", Fake)
    with pytest.raises(RuntimeError, match="sem convergencia"):
        ar.ajustar(np.arange(20), (1, 0, 0))
