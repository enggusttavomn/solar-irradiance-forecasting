"""Guardas do novo controle restrito, sem flexibilizar o algoritmo congelado."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from codigo_fonte import experimento_arima_horario_controle_auditado_v1 as a


def contexto():
    return SimpleNamespace(tarefa=SimpleNamespace(slug="hourly_72_extension"),
        protocolo=a.base.motor.protocolo_padrao(), config=SimpleNamespace(modo_execucao="completa"))


def evidencia():
    return {"schema": 1, "id": "arima_horario_novo_controle_v1", "ok": True,
            "escopo": deepcopy(a.ESCOPO), "controle_historico_reproduzido": False,
            "tolerancia_replay": 1e-6, "origem_arquivada": str(a.ARQUIVO),
            "comparacao_historica": {"delta_maximo": 4.490431751946744e-05},
            "replays": [{"localidade_id": i, "bit_a_bit": True, "delta_maximo": 0.0} for i in range(10)],
            "fontes_sha256": {}, "hash_contrato_anterior": "arquivo-original"}


@pytest.mark.parametrize("campo", ["modelo", "tarefa", "regime", "modo", "protocolo"])
def test_rejeita_outros_casos_e_protocolos(campo):
    ctx = contexto()
    modelo = "ARIMA"
    if campo == "modelo": modelo = "Climatologia"
    if campo == "tarefa": ctx.tarefa.slug = "daily_30"
    if campo == "regime": ctx.protocolo["regime"] = "historico_1998_2022"
    if campo == "modo": ctx.config.modo_execucao = "smoke"
    if campo == "protocolo": ctx.protocolo["inicio_dados"] = "2020-01-01"
    with pytest.raises(ValueError):
        a.validar_escopo(ctx, modelo)


@pytest.mark.parametrize("campo", ["escopo", "delta", "replay", "hash"])
def test_evidencia_rejeita_desvios_de_escopo_delta_replay_ou_hash(monkeypatch, campo):
    ev = evidencia()
    if campo == "escopo": ev["escopo"]["fase"] = "refit"
    if campo == "delta": ev["comparacao_historica"]["delta_maximo"] = 0.0001
    if campo == "replay": ev["replays"][0]["bit_a_bit"] = False
    monkeypatch.setattr(a.base.motor, "ler_json", lambda _: ev)
    def conferir(_):
        if campo == "hash": raise ValueError("arquivo alterado")
    monkeypatch.setattr(a.base.motor, "conferir_hashes", conferir)
    with pytest.raises(ValueError):
        a.ler_evidencia()


def test_refit_preserva_verificacao_estrita_original(monkeypatch, tmp_path):
    def original(*args): raise ValueError("Controle ARIMA nao reproduzido: 0.00001")
    monkeypatch.setattr(a, "CONFERIR_ORIGINAL", original)
    with pytest.raises(ValueError, match="0.00001"):
        a.conferir_controle(contexto(), "ARIMA", "teste", np.zeros((1, 1)), tmp_path)


def preparar_cache(monkeypatch, tmp_path):
    arquivo = tmp_path / "arquivo"
    pasta = arquivo / "sem_quantizacao/selecao"
    pasta.mkdir(parents=True)
    valores = np.array([[1.0, 2.0]], dtype=float)
    np.savez(pasta / "seed-1.npz", previsao=valores)
    evpath = tmp_path / "evidencia.json"
    evpath.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(a, "ARQUIVO", arquivo)
    monkeypatch.setattr(a, "EVIDENCIA", evpath)
    monkeypatch.setattr(a, "ler_evidencia", evidencia)
    return valores


def test_somente_divergencia_historica_literal_e_cache_exato_sao_aceitos(monkeypatch, tmp_path):
    valores = preparar_cache(monkeypatch, tmp_path)
    def original(*args):
        raise ValueError("Controle ARIMA nao reproduzido: 4.490431751946744e-05")
    monkeypatch.setattr(a, "CONFERIR_ORIGINAL", original)
    registro = a.conferir_controle(contexto(), "ARIMA", "validacao", valores, tmp_path)
    assert registro["aprovado"]
    assert registro["novo_controle_reexecutado_auditado"]
    assert registro["comparacao_historica"]["aprovado"] is False
    assert registro["comparacao_historica"]["tolerancia"] == 1e-6
    alterado = valores.copy()
    alterado[0, 0] = np.nextafter(alterado[0, 0], np.inf)
    with pytest.raises(ValueError, match="cache exato"):
        a.conferir_controle(contexto(), "ARIMA", "validacao", alterado, tmp_path)


def test_divergencia_de_alvos_nao_e_aceita(monkeypatch, tmp_path):
    valores = preparar_cache(monkeypatch, tmp_path)
    def original(*args): raise ValueError("Alvos do controle divergem.")
    monkeypatch.setattr(a, "CONFERIR_ORIGINAL", original)
    with pytest.raises(ValueError, match="Alvos"):
        a.conferir_controle(contexto(), "ARIMA", "validacao", valores, tmp_path)


def test_validador_congelado_aceita_contrato_estendido_com_hashes(monkeypatch, tmp_path):
    evpath = tmp_path / "evidencia.json"
    evpath.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(a, "EVIDENCIA", evpath)
    monkeypatch.setattr(a, "ler_evidencia", evidencia)
    original = {"schema": 1, "modelo": "ARIMA", "codigo": {}, "entradas": {},
                "parametros": {"fontes_configuracao": {}}, "sha256_contrato": "anterior"}
    monkeypatch.setattr(a, "CONSTRUIR_ORIGINAL", lambda *args: deepcopy(original))
    contrato = a.construir_contrato(contexto(), "ARIMA")
    a.base.m.salvar_json_atomico(contrato, tmp_path / "contrato_execucao.json")
    ordens = {"A": [2, 0, 2]}
    arquivos, ranking = [], []
    for indice, (variante, niveis) in enumerate(a.base.VARIANTES):
        detalhe = tmp_path / variante / "selecao/detalhes.json"
        a.base.m.salvar_json_atomico({"ordens": ordens}, detalhe)
        arquivos.append(detalhe)
        ranking.append({"nome": variante, "niveis": niveis, "MAE_validacao_wm2": float(indice), "epocas": {"-1": 0}})
    selecao = {"contrato_sha256": contrato["sha256_contrato"], "ranking": ranking,
               "vencedor": ranking[0], "selecao_concluida_antes_refit": True,
               "ordens_arima_controle": ordens, "arquivos_selecao": a.base.motor.hashes(arquivos)}
    a.base.m.salvar_json_atomico(selecao, tmp_path / "selecao_congelada.json")
    recebido, _ = a.base.validar_selecao(tmp_path)
    assert recebido["controle_reexecutado_auditado"]["historico_reproduzido"] is False
    assert str(a.EVIDENCIA) in recebido["parametros"]["fontes_configuracao"]


def test_ativacao_restaura_funcoes_congeladas():
    originais = a.base.construir_contrato, a.base.conferir_controle, a.base.executar_fase
    with a.ativar_adaptador():
        assert a.base.construir_contrato is a.construir_contrato
        assert a.base.conferir_controle is a.conferir_controle
    assert (a.base.construir_contrato, a.base.conferir_controle, a.base.executar_fase) == originais
