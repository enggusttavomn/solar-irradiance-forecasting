import json
from pathlib import Path

import pandas as pd
import pytest

from scripts.gerar_pdf_quantizacao_todos_modelos import carregar_auditoria, numero, validar_pareamento
from scripts.metricas_quantizacao_todos import MODELOS, TAREFAS, VARIANTES, sha256


def criar_fonte(tmp_path):
    linhas = []
    for tarefa, horizontes in TAREFAS.items():
        for modelo in MODELOS:
            for variante in VARIANTES:
                for particao in ("validacao", "teste"):
                    for horizonte in horizontes:
                        linhas.append({"regime": "atual", "tarefa": tarefa, "modelo": modelo,
                                       "variante": variante, "particao": particao, "horizonte": horizonte,
                                       "N_localidades": 10, "MAE_wm2": 1., "MSE_w2m4": 2.,
                                       "RMSE_wm2": 1.4, "nRMSE": .1, "R2": .8})
    metricas = tmp_path / "metricas.csv"
    pd.DataFrame(linhas).to_csv(metricas, index=False)
    rel = tmp_path / "auditoria.json"
    payload = {"ok": True, "publicavel": True, "escopo_completo": True, "modo": "completa",
               "replay_novo_executado": True, "regime": "atual",
               "metricas": {"path": str(metricas), "sha256": sha256(metricas)},
               "resultados": [{"tarefa": t, "modelo": m, "ok": True,
                               "vencedor_validacao": "sem_quantizacao"} for t in TAREFAS for m in MODELOS]}
    rel.write_text(json.dumps(payload), encoding="utf-8")
    return rel, metricas, payload


def test_grade_completa_aceita(tmp_path):
    rel, _, _ = criar_fonte(tmp_path)
    _, df = carregar_auditoria(rel)
    assert len(df) == 1056


@pytest.mark.parametrize("campo,valor", [("publicavel", False), ("escopo_completo", False),
                                         ("modo", "smoke"), ("replay_novo_executado", False), ("ok", False)])
def test_recusa_publicacao_incompleta(tmp_path, campo, valor):
    rel, _, payload = criar_fonte(tmp_path)
    payload[campo] = valor
    rel.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Auditoria incompleta"):
        carregar_auditoria(rel)


def test_recusa_metrica_alterada_apos_auditoria(tmp_path):
    rel, metricas, _ = criar_fonte(tmp_path)
    metricas.write_text(metricas.read_text(encoding="utf-8").replace("1.0", "9.0", 1), encoding="utf-8")
    with pytest.raises(ValueError, match="alteradas"):
        carregar_auditoria(rel)


def test_recusa_modelo_faltante_mesmo_com_hash_atualizado(tmp_path):
    rel, metricas, payload = criar_fonte(tmp_path)
    df = pd.read_csv(metricas)
    df[df.modelo != "ARIMA"].to_csv(metricas, index=False)
    payload["metricas"]["sha256"] = sha256(metricas)
    rel.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="Grade"):
        carregar_auditoria(rel)


def test_recusa_duplicatas(tmp_path):
    rel, metricas, payload = criar_fonte(tmp_path)
    df = pd.read_csv(metricas)
    pd.concat([df, df.iloc[:1]]).to_csv(metricas, index=False)
    payload["metricas"]["sha256"] = sha256(metricas)
    rel.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicadas"):
        carregar_auditoria(rel)


def test_numero_em_portugues():
    assert numero(47.9044258) == "47,9044"
    assert numero(float("nan")) == "-"


@pytest.mark.parametrize("falha", ["ausente", "duplicado", "tarefa", "modelo", "reprovado",
                                  "sem_aprovacao", "vencedor", "sem_vencedor"])
def test_recusa_registros_de_auditoria_invalidos(tmp_path, falha):
    rel, _, payload = criar_fonte(tmp_path)
    registros = payload["resultados"]
    if falha == "ausente": registros.pop()
    elif falha == "duplicado": registros[-1] = registros[0].copy()
    elif falha == "tarefa": registros[-1]["tarefa"] = "caso_inexistente"
    elif falha == "modelo": registros[-1]["modelo"] = "modelo_inexistente"
    elif falha == "reprovado": registros[-1]["ok"] = False
    elif falha == "sem_aprovacao": registros[-1].pop("ok")
    elif falha == "vencedor": registros[-1]["vencedor_validacao"] = "q512"
    elif falha == "sem_vencedor": registros[-1].pop("vencedor_validacao")
    rel.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="pares tarefa/modelo|Escolha da validacao"):
        carregar_auditoria(rel)


def criar_pareamento(tmp_path):
    auditorias = [tmp_path / "fixture_longo.json", tmp_path / "fixture_curto.json"]
    for path in auditorias:
        path.write_text('{"fixture": true}', encoding="utf-8")
    payload = {"ok": True, "publicavel": True,
               "resultados": [{"tarefa": t, "particao": p, "observacoes_e_datas_iguais": True}
                              for t in TAREFAS for p in ("validacao", "teste")],
               "fontes_sha256": {str(p.resolve()): sha256(p) for p in auditorias}}
    path = tmp_path / "fixture_pareamento.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, auditorias, payload


def test_pareamento_completo_aceita_sem_gerar_pdf(tmp_path):
    path, auditorias, payload = criar_pareamento(tmp_path)
    assert validar_pareamento(path, auditorias) == payload
    assert not list(tmp_path.glob("*.pdf"))


@pytest.mark.parametrize("falha", ["ausente", "duplicado", "tarefa", "particao",
                                  "amostras_diferentes", "sem_confirmacao", "reprovado",
                                  "nao_publicavel", "fonte_alterada", "outra_auditoria"])
def test_recusa_pareamento_invalido_sem_gerar_pdf(tmp_path, falha):
    path, auditorias, payload = criar_pareamento(tmp_path)
    registros = payload["resultados"]
    if falha == "ausente": registros.pop()
    elif falha == "duplicado": registros[-1] = registros[0].copy()
    elif falha == "tarefa": registros[-1]["tarefa"] = "caso_inexistente"
    elif falha == "particao": registros[-1]["particao"] = "ajuste"
    elif falha == "amostras_diferentes": registros[-1]["observacoes_e_datas_iguais"] = False
    elif falha == "sem_confirmacao": registros[-1].pop("observacoes_e_datas_iguais")
    elif falha == "reprovado": payload["ok"] = False
    elif falha == "nao_publicavel": payload["publicavel"] = False
    elif falha == "fonte_alterada": auditorias[0].write_text("alterado", encoding="utf-8")
    elif falha == "outra_auditoria": auditorias[0] = tmp_path / "outra_auditoria.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="pareada|pareamento|Pareamento"):
        validar_pareamento(path, auditorias)
    assert not list(tmp_path.glob("*.pdf"))
