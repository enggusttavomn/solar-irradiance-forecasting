"""Integração da ETA com contagens e filas; fixtures pequenas, sem treinos."""
from datetime import datetime, timezone
import json
from codigo_fonte.acompanhamento import painel_progresso_quantizacao as p

AGORA = datetime(2026, 9, 30, 17, tzinfo=timezone.utc)


def foco(feito=40):
    return {"regime": "atual", "titulo": "Escolha das configurações",
            "feito": feito, "total": 44}


def fila(pares, medidos, minimo, maximo):
    return {"estimativa": {"pares": pares, "medidos": medidos,
                          "pendentes": len(pares), "min_s": minimo, "max_s": maximo}}


def test_duas_filas_paralelas_nao_somam_tempo():
    a = fila([["daily_30", "GRU"], ["daily_30", "LSTM"]], 2, 100, 200)
    b = fila([["daily_30", "Transformer"], ["daily_30", "Informer"]], 2, 300, 500)
    e = p.resumir_estimativa(foco(), [a, b], [], False)
    assert e["status"] == "estimado"
    assert (e["min_s"], e["max_s"]) == (300, 500)
    assert e["medidos"] == e["pendentes"] == 4


def test_modelo_sem_medicao_nao_vira_estimativa_total():
    f = fila([["daily_30", "GRU"], ["daily_30", "LSTM"]], 1, 100, 200)
    e = p.resumir_estimativa(foco(42), [f], [], False)
    assert e["status"] == "parcial"
    assert (e["medidos"], e["pendentes"]) == (1, 2)


def test_fila_ausente_impede_previsao_completa():
    f = fila([["daily_30", "GRU"]], 1, 100, 200)
    assert p.resumir_estimativa(foco(42), [f], [], False)["status"] == "parcial"


def test_aviso_suspende_previsao():
    f = fila([["daily_30", "GRU"]], 1, 100, 200)
    e = p.resumir_estimativa(foco(43), [f], ["fila parada"], False)
    assert e["status"] == "suspensa"
    assert e["min_s"] is e["max_s"] is None


def test_nao_transfere_tempo_da_selecao_para_historico_ou_refit():
    for regime, titulo in [("historico_1998_2022", "Escolha das configurações"),
                            ("atual", "Treinamento final")]:
        f = {**foco(), "regime": regime, "titulo": titulo}
        assert p.resumir_estimativa(f, [], [], False)["status"] == "sem_base"


def test_metadado_de_outro_contrato_ou_fase_nao_alimenta_eta(tmp_path):
    pasta = tmp_path / "par"
    pasta.mkdir()
    contrato = {"modo": "completa", "sha256_contrato": "novo",
                "parametros": {"sementes": [42]}}
    (pasta / "contrato_execucao.json").write_text(json.dumps(contrato), encoding="utf-8")
    dest = pasta / "q64/selecao"
    dest.mkdir(parents=True)
    (dest / "seed42.npz").write_bytes(b"fixture")
    meta = {"concluido_em_utc": AGORA.isoformat(), "fase": "selecao",
            "seed": 42, "variante": "q64", "contrato_sha256": "antigo", "duracao_s": 10}
    (dest / "seed42.json").write_text(json.dumps(meta), encoding="utf-8")
    total, dados = p.registros_sementes(pasta, "selecao", p.Leitor())
    assert total == 4 and dados == []
    meta.update(contrato_sha256="novo", fase="refit")
    (dest / "seed42.json").write_text(json.dumps(meta), encoding="utf-8")
    assert p.registros_sementes(pasta, "selecao", p.Leitor())[1] == []
    meta["fase"] = "selecao"
    (dest / "seed42.json").write_text(json.dumps(meta), encoding="utf-8")
    assert len(p.registros_sementes(pasta, "selecao", p.Leitor())[1]) == 1
