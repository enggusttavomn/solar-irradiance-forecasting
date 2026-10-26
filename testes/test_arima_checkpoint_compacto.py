"""Equivalencia literal do filtro e previsoes apos serializacao compacta."""
import io
import warnings

import joblib
import numpy as np
import pytest
from statsmodels.tsa.arima.model import ARIMA

from codigo_fonte.arima_checkpoint_compacto import compactar_resultado, hash_array
from codigo_fonte.quantizacao_timesnet import quantizar_entradas
from codigo_fonte.experimento_baselines_adicionais import ORDENS_ARIMA


def assert_bits(um, outro):
    um, outro = np.asarray(um), np.asarray(outro)
    assert um.dtype == outro.dtype
    assert um.shape == outro.shape
    assert um.tobytes() == outro.tobytes()


@pytest.mark.parametrize("ordem", ORDENS_ARIMA)
@pytest.mark.parametrize("nivel", [None, 64, 128, 256])
def test_ordens_niveis_estados_iniciais_e_previsoes_bit_a_bit(ordem, nivel):
    rng = np.random.default_rng(912)
    historia = quantizar_entradas(rng.uniform(0.2, 0.8, 96), nivel)
    contexto = quantizar_entradas(rng.uniform(0.2, 0.8, 24), nivel).astype(float)
    mod = ARIMA(historia, order=ordem)
    p, d, q = ordem
    params = ([0.5] if d == 0 else []) + [0.25, 0.1][:p] + [0.1, -0.05][:q] + [0.03]
    completo = mod.smooth(params, cov_type="none")
    compacto = compactar_resultado(completo)
    buffer = io.BytesIO()
    joblib.dump(compacto, buffer)
    buffer.seek(0)
    lido = joblib.load(buffer)
    anterior, novo = completo.apply(contexto, refit=False), lido.apply(contexto, refit=False)
    assert_bits(anterior.forecast(12), novo.forecast(12))
    assert_bits(anterior.filter_results.initial_state, novo.filter_results.initial_state)
    assert_bits(anterior.filter_results.initial_state_cov, novo.filter_results.initial_state_cov)
    assert_bits(anterior.predicted_state, novo.predicted_state)
    assert_bits(anterior.filtered_state, novo.filtered_state)
    assert_bits(completo.params, compacto.params)
    assert compacto.evidencia_fit["serie_endogena_sha256"] == hash_array(completo.model.endog)
    assert len(buffer.getvalue()) < 12000


@pytest.mark.parametrize("ordem,trend", [((1, 0, 0), "c"), ((1, 0, 1), "ct"), ((1, 1, 1), "n"), ((1, 1, 0), "t")])
def test_fit_real_tendencias_e_covariancia_preservados(ordem, trend):
    rng = np.random.default_rng(44)
    historia = 0.3 + 0.01 * np.arange(120) + rng.normal(0, 0.1, 120)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        completo = ARIMA(historia, order=ordem, trend=trend, trend_offset=5).fit(method_kwargs={"maxiter": 200})
    compacto = compactar_resultado(completo)
    contexto = historia[-30:]
    assert_bits(completo.apply(contexto, refit=False).forecast(12), compacto.apply(contexto, refit=False).forecast(12))
    assert_bits(completo.cov_params_default, compacto.cov_params_default)
    assert compacto.evidencia_fit["mle_retvals"]
    assert compacto.evidencia_fit["loglik"] == completo.llf


def test_compactacao_nao_modifica_objeto_original():
    historia = np.sin(np.arange(96) / 4) + 2
    completo = ARIMA(historia, order=(1, 0, 0)).smooth([2, 0.5, 0.1], cov_type="none")
    antes = completo.filtered_state.copy()
    compacto = compactar_resultado(completo)
    compacto.params[0] = -99
    assert completo.params[0] == 2
    assert_bits(antes, completo.filtered_state)
    assert completo.smoother_results is not None


def test_rejeita_reestimacao_copia_estado_e_exogenas():
    completo = ARIMA(np.arange(32) / 32, order=(1, 0, 0)).smooth([0.5, 0.1, 0.2], cov_type="none")
    compacto = compactar_resultado(completo)
    for kwargs in ({"refit": True}, {"copy_initialization": True}, {"exog": np.ones(12)}):
        with pytest.raises(ValueError):
            compacto.apply(np.ones(12), **kwargs)


def test_caminho_filter_sem_smoother_tambem_e_exato():
    completo = ARIMA(np.arange(32) / 32, order=(1, 1, 0)).filter([0.25, 0.2], cov_type="none")
    # Nesta versao filter ainda cria um objeto SmootherResults; exercitar
    # explicitamente o ramo oficial em que esse objeto nao e armazenado.
    completo._results.smoother_results = None
    compacto = compactar_resultado(completo)
    assert compacto.suavizar is False
    contexto = np.arange(16) / 16
    assert_bits(completo.apply(contexto).forecast(4), compacto.apply(contexto).forecast(4))
