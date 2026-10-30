"""Persistencia do preprocessamento e integridade numerica da busca mensal."""
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from codigo_fonte.experimentos import otimizacao_timesnet_mensal as otim
from codigo_fonte.experimentos import experimento_multirresolucao as base


def series_mensais(tmp_path):
    datas = pd.date_range("2019-01-31", "2024-12-31", freq="ME")
    series = []
    for i in range(2):
        meses = np.arange(len(datas))
        valores = 140 + i * 30 + 40 * np.sin(2 * np.pi * meses / 12) + meses * 0.2
        fonte = tmp_path / f"serie{i}.csv"
        fonte.write_text("dados sinteticos", encoding="utf-8")
        series.append(base.SerieResolucao(f"Local {i}", i, "Teste", datas,
                                          valores.astype(np.float32), "ME", fonte))
    return tuple(series)


@pytest.mark.parametrize("alvo", ["bruto", "anomalia"])
@pytest.mark.parametrize("nome_tarefa", ["monthly_1", "monthly_6"])
def test_checkpoint_reproduz_previsao_sem_reajustar_transformacoes(tmp_path, monkeypatch, alvo, nome_tarefa):
    series = series_mensais(tmp_path)
    tarefa = base.TAREFAS_CANONICAS[nome_tarefa]
    config = base.ConfiguracaoMultirresolucao(sementes=(11,), max_epocas_mensal=1,
                                             timesnet_top_k=1, timesnet_kernels=1)
    candidato = otim.Candidato("teste", alvo=alvo, perda="mae")
    pasta = tmp_path / "resultado"
    otim.avaliar_vencedor(series=series, tarefa=tarefa, candidato=candidato,
                          configuracao=config, pasta=pasta, epocas={"11": 1})
    teste = otim._janelas(series, tarefa, "teste", config)
    with np.load(pasta / "refit/seed11.npz") as dados:
        esperado = dados["previsao"]

    def proibido(*args, **kwargs):
        raise AssertionError("Inferencia nao pode recalcular escalas/climatologia.")

    monkeypatch.setattr(otim, "climatologia_mensal", proibido)
    monkeypatch.setattr(base, "ajustar_escalas_pre_corte", proibido)
    # Nem os valores reais futuros sao necessarios para a inferencia.
    alvos_alterados = replace(teste, y_bruto=np.full_like(teste.y_bruto, 9999))
    checkpoint = pasta / "modelos/timesnet_seed11_refit.pt"
    observado = otim.prever_checkpoint(checkpoint, alvos_alterados)
    np.testing.assert_allclose(observado, esperado, rtol=0, atol=1e-5)
    with pytest.raises(ValueError, match="Identidade"):
        otim.prever_checkpoint(checkpoint, replace(teste, localidade=np.full_like(teste.localidade, "Outro")))
    assert (pasta / "preprocessamento_refit.json").is_file()


def test_macro_mae_recusa_infinito_negativo_antes_do_piso(tmp_path):
    series = series_mensais(tmp_path)
    config = base.ConfiguracaoMultirresolucao()
    janelas = otim._janelas(series, base.TAREFAS_CANONICAS["monthly_1"], "teste", config)
    with pytest.raises(ValueError, match="invalida"):
        otim.macro_mae(janelas, np.full_like(janelas.y_bruto, -np.inf))


def test_escalas_anomalia_rejeitam_janela_posterior_ao_corte(tmp_path):
    series = series_mensais(tmp_path)
    config = base.ConfiguracaoMultirresolucao()
    janelas = otim._janelas(series, base.TAREFAS_CANONICAS["monthly_1"], "teste", config)
    with pytest.raises(ValueError, match="corte"):
        otim.escalas_anomalia(janelas, "ajuste", "2024-01-01")
