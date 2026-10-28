"""Verifica isolamento temporal, congelamento e reproducao do novo experimento."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from codigo_fonte import experimento_multirresolucao as base
from codigo_fonte import experimento_quantizacao_timesnet as exp
from codigo_fonte import otimizacao_timesnet_mensal as mensal


@pytest.fixture
def series(tmp_path):
    datas = pd.date_range("2019-01-31", "2024-12-31", freq="ME")
    caminho = tmp_path / "entrada.csv"
    caminho.write_text("dados sinteticos", encoding="utf-8")
    return tuple(base.SerieResolucao(
        localidade_id=i, localidade=f"Local {i}", pais="BR", datas=datas,
        ghi=(100 + i * 30 + 20*np.sin(np.arange(len(datas))*.7)
             + np.arange(len(datas))*.2).astype(np.float32),
        frequencia="ME", caminho_fonte=caminho) for i in range(2))


def config():
    return base.ConfiguracaoMultirresolucao(
        sementes=(11, 23), max_epocas_mensal=2, paciencia_mensal=1,
        timesnet_d_model=4, timesnet_d_ff=8, timesnet_top_k=1,
        timesnet_kernels=1)


@pytest.mark.parametrize("slug,perda,dim,taxa", [
    ("monthly_1", "mae", 16, .0003), ("monthly_6", "huber", 8, .001)])
def test_contexto_preserva_configuracao_pura_escolhida(monkeypatch, series, slug, perda, dim, taxa):
    monkeypatch.setattr(base, "carregar_series_diarias", lambda: (series, None))
    monkeypatch.setattr(base, "agregar_series_mensais", lambda s: s)
    _, tarefa, candidato, cfg = exp.preparar_contexto(slug)
    assert (candidato.alvo, candidato.perda, candidato.d_model, candidato.taxa_aprendizado) == (
        "bruto", perda, dim, taxa)
    assert tarefa.seq_len == 12
    assert tuple(cfg.sementes_efetivas) == (11, 23, 42, 67, 89)
    assert (cfg.batch_size_mensal, cfg.max_epocas_mensal, cfg.paciencia_mensal,
            cfg.threads_torch, cfg.timesnet_blocos, cfg.timesnet_dropout) == (32, 300, 30, 1, 1, .1)
    assert exp.VARIANTES == (("sem_quantizacao", None), ("q64", 64), ("q128", 128), ("q256", 256))


def test_selecao_nao_recebe_2024_e_independe_dos_seus_valores(monkeypatch, tmp_path, series):
    chamadas = []
    construir = mensal._janelas

    def janelas(s, tarefa, particao, cfg):
        assert all(serie.datas.max() < pd.Timestamp("2024-01-01") for serie in s)
        assert particao in {"ajuste", "validacao"}
        return construir(s, tarefa, particao, cfg)

    def sementes(executor, **kw):
        chamadas.append((kw["nome"], kw["niveis"]))
        assert kw["treino"].datas_alvo.max() < np.datetime64("2023-01-01")
        assert kw["avaliacao"].datas_alvo.max() < np.datetime64("2024-01-01")
        erro = {None: 4., 64: 3., 128: 1., 256: 2.}[kw["niveis"]]
        return [{"semente": s, "previsao": kw["avaliacao"].y_bruto.astype(float)+erro,
                 "epocas": s % 3 + 1} for s in kw["config"].sementes_efetivas]

    monkeypatch.setattr(mensal, "_janelas", janelas)
    monkeypatch.setattr(exp, "rodar_sementes", sementes)
    tarefa = base.TAREFAS_CANONICAS["monthly_6"]
    contrato = {"sha256_contrato": "teste", "criterio": "mae"}
    args = (tarefa, mensal.Candidato("fixo"), config())
    a = exp.selecionar(series, *args, tmp_path/"a", contrato, None)
    alteradas = tuple(replace(s, ghi=np.where(s.datas.year == 2024, s.ghi*100, s.ghi)) for s in series)
    b = exp.selecionar(alteradas, *args, tmp_path/"b", contrato, None)
    assert a["ranking"] == b["ranking"]
    assert a["vencedor"]["nome"] == "q128"
    assert chamadas == list(exp.VARIANTES)*2
    assert not list(tmp_path.rglob("previsoes_teste.csv"))


def test_refit_sem_congelamento_falha_antes_de_criar_janelas(monkeypatch, tmp_path):
    def proibido(*a, **kw):
        pytest.fail("Nao deve construir janelas antes de validar congelamento global")
    monkeypatch.setattr(mensal, "_janelas", proibido)
    with pytest.raises(ValueError, match="Congele"):
        exp.refazer_teste(None, None, None, None, tmp_path/"monthly_1", None, None, None)


def _selecao_falsa(pasta, slug):
    contrato = {"sha256_contrato": "abc", "configuracao": {"sementes": [11]}}
    selecao = {"contrato_sha256": "abc", "selecao_concluida_antes_do_teste": True,
               "modo": "completa", "fontes_selecao_sha256": {}, "ranking": [
                   {"nome": nome, "epocas": {"11": 1}} for nome, _ in exp.VARIANTES]}
    base.salvar_json_atomico(contrato, pasta/slug/"contrato_execucao.json")
    base.salvar_json_atomico(selecao, pasta/slug/"selecao_congelada.json")
    base.salvar_csv_atomico(pd.DataFrame({"exemplo": [1]}), pasta/slug/"escalas_selecao.csv")


def test_congelamento_exige_duas_tarefas_e_detecta_mutacao(tmp_path):
    _selecao_falsa(tmp_path, "monthly_1")
    with pytest.raises((FileNotFoundError, ValueError)):
        exp.congelar_global(tmp_path)
    assert not (tmp_path/"selecao_global_congelada.json").exists()
    _selecao_falsa(tmp_path, "monthly_6")
    exp.congelar_global(tmp_path)
    exp.validar_congelamento_global(tmp_path)
    path = tmp_path/"monthly_1"/"selecao_congelada.json"
    path.write_text(path.read_text(encoding="utf-8")+" ", encoding="utf-8")
    with pytest.raises(ValueError, match="mudou|alterada"):
        exp.validar_congelamento_global(tmp_path)


def test_checkpoint_reproduz_previsao_sem_depender_de_alvos_e_cache_confere_hashes(tmp_path, series):
    cfg = replace(config(), sementes=(11,))
    tarefa = base.TAREFAS_CANONICAS["monthly_1"]
    treino = mensal._janelas(series, tarefa, "ajuste", cfg)
    val = mensal._janelas(series, tarefa, "validacao", cfg)
    escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo="2023-01-01", nome_ajuste="selecao")
    args = (str(tmp_path), tarefa, mensal.Candidato("fixo"), cfg, 11, treino, val,
            escalas, "q64", 64, "hash_contrato", "selecao")
    resultado = exp._seed_job(*args)
    cp = tmp_path/"modelos"/"timesnet_seed11_selecao.pt"
    previsto = exp.prever_checkpoint(cp, val)
    np.testing.assert_allclose(previsto, resultado["previsao"], rtol=0, atol=1e-7)
    alterado = replace(val, y_bruto=val.y_bruto+12345)
    np.testing.assert_array_equal(exp.prever_checkpoint(cp, alterado), previsto)
    retomado = exp._seed_job(*args)
    assert retomado["cache"] is True
    np.testing.assert_array_equal(retomado["previsao"], previsto)
    historico = tmp_path/"selecao"/"seed11.csv"
    historico.write_text(historico.read_text(encoding="utf-8")+" ", encoding="utf-8")
    with pytest.raises(ValueError, match="Cache alterado"):
        exp._seed_job(*args)


def test_retomada_recusa_outro_contrato(tmp_path):
    base.validar_ou_criar_contrato(tmp_path, {"sha256_contrato": "a"}, retomar=True)
    base.validar_ou_criar_contrato(tmp_path, {"sha256_contrato": "a"}, retomar=True)
    with pytest.raises(RuntimeError, match="outro contrato"):
        base.validar_ou_criar_contrato(tmp_path, {"sha256_contrato": "b"}, retomar=True)


def test_ensemble_aplica_piso_apos_media():
    estimativas, media = exp._estimar([np.array([[-10.]]), np.array([[6.]])], (11, 23))
    assert media.item() == -2.
    assert estimativas[-1].previsao_pos.item() == 0.


@pytest.fixture
def snapshot_pdf(tmp_path, monkeypatch):
    from scripts import auditar_quantizacao_timesnet as auditor
    monkeypatch.setattr(exp, "RAIZ", tmp_path)
    pdf = tmp_path/"documentacao/tabela_resultados_ghi_2024.pdf"
    pdf.parent.mkdir()
    pdf.write_bytes(b"PDF anterior")
    backup = tmp_path/"backup.pdf"
    backup.write_bytes(pdf.read_bytes())
    outro = tmp_path/"dados.csv"
    outro.write_bytes(b"dados originais")
    fontes = {str(p): base.sha256_arquivo(p) for p in (pdf, outro)}
    entrega = tmp_path/"relatorios/quantizacao_timesnet_20260923/entrega_pdf.json"
    def registrar():
        base.salvar_json_atomico({
            "pdf": {"path": str(pdf), "sha256": base.sha256_arquivo(pdf)},
            "pdf_anterior": {"path": str(backup), "sha256": fontes[str(pdf)]}}, entrega)
    return auditor, pdf, backup, outro, fontes, entrega, registrar


def test_snapshot_preserva_todos_antes_da_entrega(snapshot_pdf):
    auditor, pdf, backup, outro, fontes, entrega, registrar = snapshot_pdf
    r = auditor.conferir_snapshot_historico(fontes)
    assert r == {"arquivos_verificados": 2, "arquivos_preservados": 2, "alteracoes_autorizadas": []}
    assert not entrega.exists()


def test_snapshot_aceita_somente_pdf_novo_com_backup_e_entrega_verificados(snapshot_pdf):
    auditor, pdf, backup, outro, fontes, entrega, registrar = snapshot_pdf
    pdf.write_bytes(b"PDF atualizado com quantizacao")
    registrar()
    r = auditor.conferir_snapshot_historico(fontes)
    assert r["arquivos_preservados"] == 1
    assert r["arquivos_verificados"] == 2
    assert len(r["alteracoes_autorizadas"]) == 1
    alteracao = r["alteracoes_autorizadas"][0]
    assert alteracao["backup_sha256"] == fontes[str(pdf)]
    assert alteracao["sha256_atual"] == base.sha256_arquivo(pdf)
    assert alteracao["entrega_sha256"] == base.sha256_arquivo(entrega)


@pytest.mark.parametrize("problema", ["sem_entrega", "backup_modificado", "pdf_modificado_apos_entrega",
                                     "outro_arquivo_modificado", "caminho_final_diferente"])
def test_snapshot_recusa_alteracoes_sem_evidencia_exata(snapshot_pdf, problema):
    auditor, pdf, backup, outro, fontes, entrega, registrar = snapshot_pdf
    pdf.write_bytes(b"PDF novo")
    if problema != "sem_entrega":
        registrar()
    if problema == "backup_modificado":
        backup.write_bytes(b"backup diferente")
    elif problema == "pdf_modificado_apos_entrega":
        pdf.write_bytes(b"PDF diferente do entregue")
    elif problema == "outro_arquivo_modificado":
        outro.write_bytes(b"dados modificados")
    elif problema == "caminho_final_diferente":
        manifesto = exp.ler_json(entrega)
        manifesto["pdf"]["path"] = str(backup)
        base.salvar_json_atomico(manifesto, entrega)
    with pytest.raises(AssertionError):
        auditor.conferir_snapshot_historico(fontes)
