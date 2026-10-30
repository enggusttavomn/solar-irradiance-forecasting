"""Verifica exclusao de escritores e preservacao da avaliacao na retomada."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import codigo_fonte.experimentos.otimizacao_timesnet_mensal as otim


@pytest.fixture
def argumentos(tmp_path, monkeypatch):
    monkeypatch.setattr(otim.base, "carregar_series_diarias",
                        lambda pasta=None: ((), pd.DataFrame({"origem": ["sintetica"]})))
    monkeypatch.setattr(otim.base, "agregar_series_mensais", lambda series: ())
    monkeypatch.setattr(otim, "_contrato", lambda *args: {"sha256_contrato": "contrato-fixo"})
    monkeypatch.setattr(otim, "selecionar", lambda **kwargs: {
        "vencedor": {"nome": "mae", "MAE_validacao_ensemble_wm2": 1.0,
                     "epocas": {"11": 2}}})
    return {
        "pasta_saida": tmp_path / "busca", "tarefas": ("monthly_1",),
        "candidatos": (otim.Candidato("mae", perda="mae"),),
        "configuracao": otim.base.ConfiguracaoMultirresolucao(sementes=(11,)),
    }


@pytest.mark.parametrize("legado", [False, True])
def test_concorrente_nao_limpa_temporario_nem_altera_status(argumentos, monkeypatch, legado):
    saida = argumentos["pasta_saida"]
    pasta = saida / "monthly_1"
    pasta.mkdir(parents=True)
    lock = pasta / "execucao.lock" if legado else saida / ".monthly_1.execucao.lock"
    lock.write_text("4242", encoding="utf-8")
    temporario = pasta / (".arquivo." + "a" * 32 + ".tmp")
    temporario.write_bytes(b"escrita ainda ativa")
    status = pasta / "status_execucao.json"
    status.write_bytes(b'{"etapa": "em_execucao"}')
    antes = {p.relative_to(saida): p.read_bytes() for p in saida.rglob("*") if p.is_file()}

    def contrato_proibido(*args, **kwargs):
        raise AssertionError("Contrato/limpeza nao podem ocorrer antes de adquirir o lock.")

    monkeypatch.setattr(otim.base, "validar_ou_criar_contrato", contrato_proibido)
    with pytest.raises(RuntimeError, match="apague o arquivo"):
        otim.executar(**argumentos)
    depois = {p.relative_to(saida): p.read_bytes() for p in saida.rglob("*") if p.is_file()}
    assert depois == antes


def test_contrato_e_manifesto_sao_processados_sob_o_mesmo_lock(argumentos, monkeypatch):
    saida = argumentos["pasta_saida"]
    lock = saida / ".monthly_1.execucao.lock"
    validar_original = otim.base.validar_ou_criar_contrato
    manifesto_original = otim.base.gerar_manifesto_artefatos
    salvar_original = otim.base.salvar_json_atomico
    etapas = []

    def validar(*args, **kwargs):
        assert lock.is_file()
        etapas.append("contrato")
        return validar_original(*args, **kwargs)

    def manifesto(*args, **kwargs):
        assert lock.is_file()
        etapas.append("hashes")
        resultado = manifesto_original(*args, **kwargs)
        assert not any("execucao.lock" in item["arquivo"] for item in resultado["arquivos"])
        return resultado

    def salvar(conteudo, destino):
        if Path(destino).name == "manifesto_artefatos.json":
            assert lock.is_file()
            etapas.append("manifesto_salvo")
        return salvar_original(conteudo, destino)

    monkeypatch.setattr(otim.base, "validar_ou_criar_contrato", validar)
    monkeypatch.setattr(otim.base, "gerar_manifesto_artefatos", manifesto)
    monkeypatch.setattr(otim.base, "salvar_json_atomico", salvar)
    otim.executar(**argumentos)
    assert etapas == ["contrato", "hashes", "manifesto_salvo"]
    assert not lock.exists()


def test_falha_de_contrato_libera_lock_sem_alterar_status(argumentos, monkeypatch):
    saida = argumentos["pasta_saida"]
    pasta = saida / "monthly_1"
    pasta.mkdir(parents=True)
    status = pasta / "status_execucao.json"
    status.write_bytes(b'{"etapa": "concluida"}')

    def falhar(*args, **kwargs):
        assert (saida / ".monthly_1.execucao.lock").is_file()
        raise RuntimeError("outro contrato")

    monkeypatch.setattr(otim.base, "validar_ou_criar_contrato", falhar)
    with pytest.raises(RuntimeError, match="outro contrato"):
        otim.executar(**argumentos)
    assert not (saida / ".monthly_1.execucao.lock").exists()
    assert status.read_bytes() == b'{"etapa": "concluida"}'


def test_falha_de_manifesto_libera_lock_e_registra_falha(argumentos, monkeypatch):
    saida = argumentos["pasta_saida"]

    def falhar(*args, **kwargs):
        assert (saida / ".monthly_1.execucao.lock").is_file()
        raise RuntimeError("falha de manifesto")

    monkeypatch.setattr(otim.base, "gerar_manifesto_artefatos", falhar)
    with pytest.raises(RuntimeError, match="falha de manifesto"):
        otim.executar(**argumentos)
    assert not (saida / ".monthly_1.execucao.lock").exists()
    status = json.loads((saida / "monthly_1" / "status_execucao.json").read_text(encoding="utf-8"))
    assert status["etapa"] == "falhou"


@pytest.mark.parametrize("artefato_ausente", [False, True])
def test_retomada_preserva_teste_concluido_apenas_com_artefatos(argumentos, monkeypatch, artefato_ausente):
    avaliacoes = []

    def avaliar(**kwargs):
        avaliacoes.append(kwargs["candidato"].nome)
        for nome in ("metricas_macro.csv", "metricas_por_localidade.csv",
                     "variabilidade_sementes.csv", "previsoes_teste.csv"):
            (kwargs["pasta"] / nome).write_text("valor\n1\n", encoding="utf-8")
        return 12.5

    monkeypatch.setattr(otim, "avaliar_vencedor", avaliar)
    otim.executar(**argumentos, avaliar_teste=True)
    pasta = argumentos["pasta_saida"] / "monthly_1"
    if artefato_ausente:
        (pasta / "previsoes_teste.csv").unlink()
    retomado = otim.executar(**argumentos)
    assert avaliacoes == ["mae"]  # retomar nao dispara nova avaliacao
    assert retomado[0]["teste_avaliado"] is (not artefato_ausente)
    status = json.loads((pasta / "status_execucao.json").read_text(encoding="utf-8"))
    assert status["teste_avaliado"] is (not artefato_ausente)
    resumo = pd.read_csv(argumentos["pasta_saida"] / "resumo.csv")
    assert bool(resumo.loc[0, "teste_avaliado"]) is (not artefato_ausente)
    if not artefato_ausente:
        assert retomado[0]["MAE_teste_wm2"] == status["MAE_teste_wm2"] == 12.5
    else:
        assert "MAE_teste_wm2" not in retomado[0]
