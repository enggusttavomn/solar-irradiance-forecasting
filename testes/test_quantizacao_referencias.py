"""Causalidade e semantica da quantizacao nas referencias e no ARIMA."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from codigo_fonte import quantizacao_referencias as q
from codigo_fonte import experimento_multirresolucao as m
from codigo_fonte import experimento_horario_timesnet as h


def escala():
    return pd.DataFrame({"localidade_id": [0], "minimo_treino_wm2": [0.0],
                         "amplitude_escala_wm2": [100.0]})


def mensal():
    datas = pd.date_range("2019-01-31", "2024-12-31", freq="ME")
    serie = m.SerieResolucao("A", 0, "BR", datas,
                            (20 + np.arange(len(datas)) % 12 * 4.321).astype(np.float32),
                            "ME", Path("fixture.csv"))
    tarefa = m.TAREFAS_CANONICAS["monthly_1"]
    janelas = {p: m.construir_janelas([serie], seq_len=12, pred_len=1,
                                    intervalo=intervalo, particao=p)
               for p, intervalo in (("ajuste", tarefa.ajuste), ("validacao", tarefa.validacao),
                                    ("refit", tarefa.refit), ("teste", tarefa.teste))}
    return SimpleNamespace(tarefa=tarefa, series=(serie,), janelas=janelas,
                           escalas={"selecao": escala(), "refit": escala()})


def horario():
    datas = pd.date_range("2022-01-01", "2024-03-01", freq="h", tz="Etc/GMT+3")
    serie = h.SerieLocalidade("A", 0, datas.tz_convert("UTC"), datas,
                             (20 + datas.hour.to_numpy() + datas.day.to_numpy() * 0.123).astype(np.float32),
                             -3, -20, -40)
    origem = pd.DatetimeIndex([pd.Timestamp("2024-02-29", tz="Etc/GMT+3")])
    pos = datas.get_indexer(origem)[0]
    janelas = h.JanelasHorarias(serie.ghi[pos-24:pos][None, :], np.array([[909.0, 808.0]]),
                               np.array([0]), np.array(["A"]), origem.tz_convert("UTC"), origem, 24, 2, "teste")
    return SimpleNamespace(tarefa=m.TAREFA_HORARIA_EXTENSAO, series=(serie,),
                           janelas={"teste": janelas}, escalas={"refit": escala()})


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_transformacao_historica_nao_modifica_origem_e_preserva_escala(niveis):
    original = np.array([-10.0, 0.0, 12.3, 55.5, 100.0, 130.0])
    copia = original.copy()
    saida = q.quantizar_historico_bruto(original, escala(), 0, niveis)
    np.testing.assert_array_equal(original, copia)
    if niveis is None:
        np.testing.assert_array_equal(saida, copia)
    else:
        esperado = np.rint(np.clip(original.astype(np.float32) / 100, 0, 1).astype(float) * (niveis-1)) / (niveis-1)
        np.testing.assert_array_equal(saida, esperado.astype(np.float32).astype(float) * 100)
        assert saida.min() == 0 and saida.max() == 100


@pytest.mark.parametrize("niveis", [True, 1, 64.0, -5])
def test_rejeita_niveis_invalidos(niveis):
    with pytest.raises(ValueError):
        q.quantizar_historico_bruto([5], escala(), 0, niveis)


def test_controle_mensal_reproduz_referencias_originais_exatamente():
    ctx = mensal()
    atual = q.previsoes_referencias(ctx, "teste")
    original = m.previsoes_baselines(ctx.janelas["teste"], ctx.series, fim_ajuste_exclusivo="2024-01-01")
    for modelo in original:
        np.testing.assert_array_equal(atual[modelo], original[modelo])


def test_controle_horario_preserva_persistencia_24h_e_sazonal_anual():
    ctx = horario()
    atual = q.previsoes_referencias(ctx, "teste")
    np.testing.assert_array_equal(atual["Persistencia"], h.prever_persistencia_diaria(ctx.janelas["teste"]))
    np.testing.assert_array_equal(atual["Sazonal ingenuo"], h.prever_sazonal_ingenuo_anual(ctx.janelas["teste"], ctx.series))


@pytest.mark.parametrize("niveis", [64, 128, 256])
def test_referencias_mudam_historico_antes_media_e_nao_y(niveis):
    ctx = mensal()
    original_y = ctx.janelas["teste"].y_bruto.copy()
    resultado = q.previsoes_referencias(ctx, "teste", niveis)
    serie = ctx.series[0]
    esperado = q.quantizar_historico_bruto(serie.ghi[serie.datas < "2024-01-01"], escala(), 0, niveis)
    previsto_jan = esperado[::12].mean()
    assert resultado["Climatologia"][0, 0] == pytest.approx(previsto_jan, abs=1e-12)
    np.testing.assert_array_equal(ctx.janelas["teste"].y_bruto, original_y)
    assert not np.array_equal(resultado["Persistencia"], q.previsoes_referencias(ctx, "teste")["Persistencia"])


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_climatologia_horaria_nao_usa_futuro_e_fallback_fevereiro(niveis):
    ctx = horario()
    primeiro = q.previsoes_referencias(ctx, "teste", niveis)["Climatologia"]
    serie = ctx.series[0]
    alterados = serie.ghi.copy()
    alterados[serie.timestamp_local.tz_localize(None) >= pd.Timestamp("2024-01-01")] = 9999
    outro = SimpleNamespace(**{**vars(ctx), "series": (replace(serie, ghi=alterados),)})
    segundo = q.previsoes_referencias(outro, "teste", niveis)["Climatologia"]
    np.testing.assert_array_equal(primeiro, segundo)
    refs = (serie.timestamp_local.month == 2) & (serie.timestamp_local.day == 28)
    refs &= serie.timestamp_local.year < 2024
    valores = q.quantizar_historico_bruto(serie.ghi[refs], escala(), 0, niveis)
    assert primeiro[0, 0] == pytest.approx(valores[::24].mean())
    assert primeiro[0, 1] == pytest.approx(valores[1::24].mean())


@pytest.mark.parametrize("niveis", [None, 64])
def test_inferencia_referencias_independe_alvos(niveis):
    ctx = mensal()
    primeiro = q.previsoes_referencias(ctx, "teste", niveis)
    ctx.janelas["teste"].y_bruto[:] = np.nan
    segundo = q.previsoes_referencias(ctx, "teste", niveis)
    for nome in primeiro:
        np.testing.assert_array_equal(primeiro[nome], segundo[nome])


def test_climatologia_rejeita_corte_que_invade_teste():
    with pytest.raises(ValueError, match="ultrapassa"):
        q.previsoes_referencias(mensal(), "teste", 64, fim_ajuste_exclusivo="2024-02-01")


def test_corte_mensal_e_inicio_do_mes():
    assert q.corte_fase(mensal(), "selecao") == pd.Timestamp("2023-01-01")
    assert q.corte_fase(mensal(), "refit") == pd.Timestamp("2024-01-01")


def test_csv_le_apenas_ordens_selecionadas_e_rejeita_duplicadas(tmp_path):
    path = tmp_path / "ordens.csv"
    pd.DataFrame({"localidade": ["A", "A", "A"], "ordem": ["(1,0,0)", "(2,0,0)", "(2,0,0)"],
                  "fase": ["selecao", "selecao", "refit"], "selecionada": [False, True, None]}).to_csv(path, index=False)
    assert q.ordens_de_csv(path) == {"A": (2, 0, 0)}
    df = pd.read_csv(path)
    df.loc[0, "selecionada"] = True
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="duplicadas"):
        q.ordens_de_csv(path)


class FakeFit:
    def __init__(self, historia, ordem):
        self.historia = np.asarray(historia)
        self.ordem = ordem

    def apply(self, contexto, refit):
        assert refit is False
        return SimpleNamespace(forecast=lambda n: np.repeat(np.asarray(contexto).mean(), n))


def fake_ajuste(monkeypatch):
    historicos = []
    def ajustar(valores, ordem):
        historicos.append(np.asarray(valores).copy())
        return FakeFit(valores, ordem), [{"convergiu": True, "otimizador": "fixture"}]
    monkeypatch.setattr(q.arima, "ajustar", ajustar)
    # A serializacao real tem seus testes proprios; este dublê isola o protocolo.
    monkeypatch.setattr(q, "compactar_resultado", lambda modelo: modelo)
    return historicos


def test_arima_quantizado_exige_ordem_do_controle():
    with pytest.raises(ValueError, match="ordens fixadas"):
        q.selecionar_arima(mensal(), 64)


@pytest.mark.parametrize("niveis", [None, 64, 128, 256])
def test_arima_serie_endogena_e_contextos_quantizados_alvos_continuos(monkeypatch, niveis):
    ctx = mensal()
    historias = fake_ajuste(monkeypatch)
    antes = ctx.janelas["validacao"].y_bruto.copy()
    resultado = q.selecionar_arima(ctx, niveis, ordens_fixas={"A": [2, 0, 0]})
    esperado_hist = q.quantizar_entradas(q.e.serie_ajuste_arima(ctx, ctx.series[0], "selecao"), niveis)
    np.testing.assert_array_equal(historias[0], esperado_hist)
    x = q.normalizar_entradas(ctx.janelas["validacao"], escala(), niveis)
    np.testing.assert_allclose(resultado["previsao_bruta"], x.astype(float).mean(axis=1, keepdims=True) * 100)
    np.testing.assert_array_equal(antes, ctx.janelas["validacao"].y_bruto)
    assert resultado["ordens"] == {"A": [2, 0, 0]}


def test_arima_refit_nao_consulta_valores_reais_teste(monkeypatch, tmp_path):
    ctx = mensal()
    fake_ajuste(monkeypatch)
    selecao = q.selecionar_arima(ctx, 64, ordens_fixas={"A": [1, 0, 0]})
    primeiro = q.refit_arima(ctx, 64, None, selecao)
    ctx.janelas["teste"].y_bruto[:] = np.nan
    segundo = q.refit_arima(ctx, 64, tmp_path, selecao)
    np.testing.assert_array_equal(primeiro["previsao_bruta"], segundo["previsao_bruta"])
    import joblib
    checkpoint = joblib.load(tmp_path / "modelos/localidade0_refit.joblib")
    np.testing.assert_array_equal(q.prever_checkpoint_arima(checkpoint, ctx.janelas["teste"]), segundo["previsao_bruta"])


def test_arima_erro_se_refit_trocar_nivel(monkeypatch):
    ctx = mensal()
    fake_ajuste(monkeypatch)
    selecao = q.selecionar_arima(ctx, 64, ordens_fixas={"A": [1, 0, 0]})
    with pytest.raises(ValueError, match="Nivel diverge"):
        q.refit_arima(ctx, 128, None, selecao)


def test_arima_ordem_fixa_sem_convergencia_nao_e_substituida(monkeypatch):
    chamadas = []
    def falhar(valores, ordem):
        chamadas.append(ordem)
        raise RuntimeError("falha numerica")
    monkeypatch.setattr(q.arima, "ajustar", falhar)
    with pytest.raises(RuntimeError, match="sem ajuste valido"):
        q.selecionar_arima(mensal(), 64, ordens_fixas={"A": [2, 0, 0]})
    assert chamadas == [(2, 0, 0)]


def test_arima_sem_controle_seleciona_sem_necessitar_dados_teste(monkeypatch):
    ctx = mensal()
    fake_ajuste(monkeypatch)
    ctx.janelas.pop("teste")
    ctx.janelas.pop("refit")
    ctx.escalas.pop("refit")
    resultado = q.selecionar_arima(ctx)
    assert len(resultado["registros"]) == len(q.e.ORDENS_ARIMA)
    assert resultado["ordens"]["A"] == list(q.e.ORDENS_ARIMA[0])


def test_arima_usa_robusto_com_mesma_politica_numerica():
    assert q.protocolo_referencias()["arima_numerico"] == [["lbfgs", 200], ["powell", 2000]]
