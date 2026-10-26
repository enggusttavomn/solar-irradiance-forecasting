"""Falhas de integridade e casos fisicos da auditoria de quantizacao."""
import json
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from scripts import auditar_quantizacao_resolucoes as audit


def salvar(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_rejeita_nan_adicionado_a_metrica_e_aceita_nan_legitimo():
    assert audit.perto([1., np.nan], [1., np.nan], "R2") == 0
    with pytest.raises(AssertionError, match="NaNs"):
        audit.perto([np.nan, np.nan], [1., np.nan], "R2")


def test_mascara_noturna_preserva_erro_real_e_media_antes_piso():
    bruto = np.mean([np.array([[-10., 30.]]), np.array([[6., 10.]])], axis=0)
    previsto = audit.pos_processar(bruto, np.array([[1., -1.]]))
    np.testing.assert_array_equal(previsto, [[0., 0.]])
    # Observacao noturna nao e descartada ou substituida pela mascara.
    assert audit.mae_macro([[1., 5.]], previsto, np.array([0])) == 3.


def test_quantizacao_audita_clipping_e_independencia_de_alvos():
    j = SimpleNamespace(x_bruto=np.array([[-1., .4372, 2.]], np.float32),
                        y_bruto=np.array([[.62345]], np.float32),
                        localidade_id=np.array([0]), localidade=np.array(["A"]),
                        seq_len=3, pred_len=1)
    escalas = pd.DataFrame({"localidade_id": [0], "minimo_treino_wm2": [0.],
                           "amplitude_escala_wm2": [1.]})
    diag = audit.exp.diagnosticos(j, escalas, 64)
    out = audit.conferir_quantizacao(j, escalas, 64, diag)
    assert out["inferencia_independe_de_y"] is True
    assert j.y_bruto[0, 0] == np.float32(.62345)
    diag["total"]["saturados"] = 0
    with pytest.raises(AssertionError, match="Diagnostico"):
        audit.conferir_quantizacao(j, escalas, 64, diag)


def test_snapshot_so_aceita_pdf_com_backup_e_entrega(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    pdf = tmp_path/"documentacao/tabela_resultados_ghi_2024.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"old-pdf")
    old_sha = audit.base.sha256_arquivo(pdf)
    snapshot = tmp_path/"relatorios/snapshot_anteriores.json"
    salvar(snapshot, {str(pdf): old_sha})
    pdf.write_bytes(b"new-pdf")
    with pytest.raises(AssertionError, match="Historico alterado"):
        audit.snapshot_historico(snapshot)
    backup = snapshot.parent/"fonte_6_paginas.pdf"
    backup.write_bytes(b"old-pdf")
    salvar(snapshot.parent/"entrega_pdf.json", {
        "pdf": {"path": str(pdf), "sha256": audit.base.sha256_arquivo(pdf)},
        "pdf_anterior": {"path": str(backup), "sha256": old_sha}})
    assert len(audit.snapshot_historico(snapshot)["alteracoes_autorizadas"]) == 1
    backup.write_bytes(b"tampered-backup")
    with pytest.raises(AssertionError, match="Backup"):
        audit.snapshot_historico(snapshot)


def test_snapshot_rejeita_resultado_historico_alterado(monkeypatch, tmp_path):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    original = tmp_path/"previsoes.csv"
    original.write_bytes(b"old")
    snapshot = tmp_path/"snapshot.json"
    salvar(snapshot, {str(original): audit.base.sha256_arquivo(original)})
    original.write_bytes(b"new")
    with pytest.raises(AssertionError, match="Historico alterado"):
        audit.snapshot_historico(snapshot)


def test_global_rejeita_congelamento_de_so_uma_tarefa(tmp_path):
    salvar(tmp_path/"selecao_global_congelada.json", {"tarefas": ["daily_30"]})
    with pytest.raises(AssertionError, match="ambas tarefas"):
        audit.congelamento_global(tmp_path)
