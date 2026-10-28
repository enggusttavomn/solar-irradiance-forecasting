"""Contrato, congelamento e caches das referencias quantizadas."""
from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from codigo_fonte import experimento_quantizacao_estatisticos as run
from testes.test_quantizacao_referencias import mensal, fake_ajuste


def contexto(tmp_path, fase, regime="historico_1998_2022"):
    ctx = mensal()
    ctx.config = run.m.ConfiguracaoMultirresolucao(modo_execucao="smoke")
    ctx.fase = fase
    ctx.protocolo = {**run.motor.protocolo_padrao(), "regime": regime}
    fonte = tmp_path / "dados_fixture.csv"
    if not fonte.exists():
        fonte.write_text("dados_fixos", encoding="utf-8")
    ctx.entradas = [fonte]
    chaves = {"ajuste", "validacao"} if fase == "selecao" else {"refit", "teste"}
    ctx.janelas = {k:v for k,v in ctx.janelas.items() if k in chaves}
    ctx.escalas = {fase: ctx.escalas[fase]}
    return ctx


@pytest.mark.parametrize("modelo", run.q.MODELOS_REFERENCIA)
def test_referencia_selecao_freeze_refit_e_cache(tmp_path, modelo):
    saida = tmp_path / "resultados"
    ctx = contexto(tmp_path, "selecao")
    selecao = run.executar_fase(ctx, modelo, saida, "selecao")
    pasta = saida / "monthly_1" / run.slug_modelo(modelo)
    contrato, validada = run.validar_selecao(pasta)
    assert validada == selecao
    assert contrato["parametros"]["sem_epocas"] is True
    assert len(selecao["ranking"]) == 4
    assert {r["nome"] for r in selecao["ranking"]} == set(dict(run.VARIANTES))
    assert run.executar_fase(ctx, modelo, saida, "selecao") == selecao
    ctx_refit = contexto(tmp_path, "refit")
    run.executar_fase(ctx_refit, modelo, saida, "refit")
    run.executar_fase(ctx_refit, modelo, saida, "refit")
    run.validar_selecao(pasta)
    assert run.motor.ler_json(pasta / "status.json")["etapa"] == "concluida"
    for variante,_ in run.VARIANTES:
        assert (pasta / variante / "previsoes_teste.csv.gz").exists()
        assert (pasta / variante / "metricas_teste.csv").exists()


def test_arima_ordens_do_controle_compartilhadas_congeladas(tmp_path, monkeypatch):
    fake_ajuste(monkeypatch)
    ctx = contexto(tmp_path, "selecao")
    saida = tmp_path / "resultados"
    selecao = run.executar_fase(ctx, "ARIMA", saida, "selecao")
    assert selecao["ordens_arima_controle"] == {"A": list(run.e.ORDENS_ARIMA[0])}
    pasta = saida / "monthly_1/arima"
    for variante,_ in run.VARIANTES:
        detalhes = run.motor.ler_json(pasta / variante / "selecao/detalhes.json")
        assert detalhes["ordens"] == selecao["ordens_arima_controle"]
    run.executar_fase(contexto(tmp_path, "refit"), "ARIMA", saida, "refit")
    run.validar_selecao(pasta)


def test_refit_bloqueado_sem_selecao(tmp_path):
    with pytest.raises(FileNotFoundError):
        run.executar_fase(contexto(tmp_path, "refit"), "Persistencia", tmp_path / "resultados", "refit")


def test_hash_detecta_alteracao_dos_dados(tmp_path):
    ctx = contexto(tmp_path, "selecao")
    run.executar_fase(ctx, "Persistencia", tmp_path / "resultados", "selecao")
    ctx.entradas[0].write_text("dados_alterados", encoding="utf-8")
    with pytest.raises(ValueError, match="Arquivo alterado"):
        run.validar_selecao(tmp_path / "resultados/monthly_1/persistencia")


def test_hash_detecta_adulteracao_previsoes_selecao(tmp_path):
    run.executar_fase(contexto(tmp_path, "selecao"), "Persistencia", tmp_path / "resultados", "selecao")
    pasta = tmp_path / "resultados/monthly_1/persistencia"
    (pasta / "q64/previsoes_validacao.csv.gz").write_bytes(b"alterado")
    with pytest.raises(ValueError, match="Arquivo alterado"):
        run.validar_selecao(pasta)


def test_rejeita_ranking_com_nivel_faltante(tmp_path):
    run.executar_fase(contexto(tmp_path, "selecao"), "Persistencia", tmp_path / "resultados", "selecao")
    pasta = tmp_path / "resultados/monthly_1/persistencia"
    arquivo = pasta / "selecao_congelada.json"
    conteudo = run.motor.ler_json(arquivo)
    conteudo["ranking"].pop()
    arquivo.write_text(json.dumps(conteudo), encoding="utf-8")
    with pytest.raises(ValueError, match="quatro variantes"):
        run.validar_selecao(pasta)


def test_rejeita_ordens_arima_divergentes(tmp_path, monkeypatch):
    fake_ajuste(monkeypatch)
    run.executar_fase(contexto(tmp_path, "selecao"), "ARIMA", tmp_path / "resultados", "selecao")
    pasta = tmp_path / "resultados/monthly_1/arima"
    arquivo = pasta / "q64/selecao/detalhes.json"
    conteudo = run.motor.ler_json(arquivo)
    conteudo["ordens"]["A"] = [9, 9, 9]
    arquivo.write_text(json.dumps(conteudo), encoding="utf-8")
    with pytest.raises(ValueError, match="Ordem ARIMA mudou"):
        run.validar_selecao(pasta)


def test_rejeita_escrita_em_resultados_originais(tmp_path):
    ctx = contexto(tmp_path, "selecao")
    with pytest.raises(ValueError, match="historicos"):
        run.executar_fase(ctx, "Persistencia", run.e.FONTE, "selecao")


def test_nomes_modelos_possuem_slugs_estaveis():
    assert run.slug_modelo("Sazonal ingenuo") == "sazonal_ingenuo"
    assert run.slug_modelo("ARIMA") == "arima"
    with pytest.raises(ValueError):
        run.slug_modelo("modelo_desconhecido")
