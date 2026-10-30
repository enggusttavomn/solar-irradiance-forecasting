"""Equivalencia numerica e escopo do cache de estatisticas climatologicas."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.experimentos import experimento_multirresolucao as original
from codigo_fonte.experimentos import quantizacao_referencias as q
from codigo_fonte.modelos.referencias_simples.climatologia_cache_localidade import prever_climatologia


def fixture(frequencia, niveis, fallback):
    datas = pd.date_range("2021-01-01", "2024-12-31", freq=frequencia)
    if fallback:
        # Ausencia de uma chave comum exercita a media global.
        uso = (datas.month != 7) if frequencia == "ME" else ~((datas.month == 7) & (datas.day == 15))
        datas = datas[uso]
    escalas = pd.DataFrame({"localidade_id": [0, 1], "minimo_treino_wm2": [-10.0, 0.0],
                           "amplitude_escala_wm2": [110.0, 150.0]})
    rng = np.random.default_rng(151)
    series = []
    for ident in (0, 1):
        valores = (rng.normal(50.0, 25.0, len(datas)) + ident * 7).astype(np.float32)
        series.append(SimpleNamespace(localidade_id=ident, datas=datas,
            ghi=q.quantizar_historico_bruto(valores, escalas, ident, niveis), frequencia=frequencia))
    alvos = pd.to_datetime(["2024-01-01", "2024-02-28", "2024-02-29", "2024-03-01", "2024-07-15", "2024-12-31"])
    j = SimpleNamespace(localidade_id=np.array([1, 0, 1, 0, 0]),
                        datas_alvo=np.repeat(alvos.to_numpy()[None, :], 5, axis=0),
                        y_bruto=np.full((5, len(alvos)), np.nan))
    return j, tuple(series)


@pytest.mark.parametrize("frequencia", ["D", "ME"])
@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
@pytest.mark.parametrize("fallback", [False, True])
def test_equivalencia_bit_a_bit_com_bissexto_global_e_localidades(frequencia, niveis, fallback):
    j, series = fixture(frequencia, niveis, fallback)
    corte = "2024-01-01"
    antes = [s.ghi.copy() for s in series]
    esperado = original.prever_climatologia(j, series, fim_ajuste_exclusivo=corte)
    atual = prever_climatologia(j, series, fim_ajuste_exclusivo=corte)
    assert atual.dtype == esperado.dtype
    assert atual.shape == esperado.shape
    assert atual.tobytes() == esperado.tobytes()
    for s, copia in zip(series, antes, strict=True):
        np.testing.assert_array_equal(s.ghi, copia)
    assert np.isnan(j.y_bruto).all()


def test_groupby_uma_vez_por_localidade_e_por_chamada(monkeypatch):
    j, series = fixture("D", 64, False)
    chamadas = []
    original_groupby = pd.Series.groupby
    def contar(self, *args, **kwargs):
        chamadas.append(len(self))
        return original_groupby(self, *args, **kwargs)
    monkeypatch.setattr(pd.Series, "groupby", contar)
    primeiro = prever_climatologia(j, series, fim_ajuste_exclusivo="2024-01-01")
    assert len(chamadas) == 2
    for s in series:
        s.ghi = s.ghi + 10
    segundo = prever_climatologia(j, series, fim_ajuste_exclusivo="2024-01-01")
    assert len(chamadas) == 4
    assert not np.array_equal(primeiro, segundo)


def test_fim_ajuste_nao_e_incluido():
    j, series = fixture("D", None, False)
    primeiro = prever_climatologia(j, series, fim_ajuste_exclusivo="2024-01-01")
    for s in series:
        s.ghi[s.datas >= "2024-01-01"] = 987654
    segundo = prever_climatologia(j, series, fim_ajuste_exclusivo="2024-01-01")
    assert primeiro.tobytes() == segundo.tobytes()
