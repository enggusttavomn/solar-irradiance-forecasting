"""Regressao: leitura CSV deve preservar exatamente os alvos float32 originais."""
from dataclasses import replace

import numpy as np
import pytest

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as run
from testes.test_experimento_quantizacao_estatisticos import contexto


def preparar(tmp_path, monkeypatch):
    ctx = contexto(tmp_path, "selecao", regime="atual")
    ctx.config = replace(ctx.config, modo_execucao="completa")
    ctx.janelas["validacao"].y_bruto[:] = np.float32(0.12345678)
    tab = run.e.tabela_chaves(ctx, "validacao")
    pred = np.full(ctx.janelas["validacao"].y_bruto.shape, 307.9171447753906)
    tab["previsao_bruta_persistencia_deterministica_wm2"] = pred.reshape(-1)
    origem = tmp_path / "originais"
    monkeypatch.setattr(run.e, "FONTE", origem)
    arquivo = origem / "monthly_1/previsoes_validacao.csv.gz"
    arquivo.parent.mkdir(parents=True)
    return ctx, pred, tab, arquivo


def test_round_trip_preserva_alvos_sem_relaxar_tolerancia(tmp_path, monkeypatch):
    ctx, pred, tab, arquivo = preparar(tmp_path, monkeypatch)
    tab.to_csv(arquivo, index=False)
    resultado = run.conferir_controle(ctx, "Persistencia", "validacao", pred, tmp_path / "relatorio")
    assert resultado["aprovado"] is True
    assert resultado["diferenca_maxima"] == 0


def test_mudanca_real_em_alvos_continua_rejeitada(tmp_path, monkeypatch):
    ctx, pred, tab, arquivo = preparar(tmp_path, monkeypatch)
    tab.loc[0, "ghi_real_wm2"] += 0.0001
    tab.to_csv(arquivo, index=False)
    with pytest.raises(ValueError, match="Alvos do controle divergem"):
        run.conferir_controle(ctx, "Persistencia", "validacao", pred, tmp_path / "relatorio")
