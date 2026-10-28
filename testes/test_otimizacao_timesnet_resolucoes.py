"""Busca diaria/horaria: causalidade, alinhamento e selecao independente do teste."""

from __future__ import annotations

import json
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn

from codigo_fonte import otimizacao_timesnet_resolucoes as otim
from codigo_fonte.experimento_horario_timesnet import JanelasHorarias


def _contexto(horario=False):
    tarefa = otim.m.TAREFA_HORARIA_EXTENSAO if horario else otim.m.TAREFAS_CANONICAS["daily_30"]
    tarefa = replace(tarefa, seq_len=6, pred_len=2, horizontes=(1, 2))
    ids = np.asarray([0, 1, 0, 1], dtype=np.int64)
    nomes = np.asarray([f"Local {i}" for i in ids], dtype=object)
    janelas = {}
    for fase, ano in (("ajuste", 2022), ("validacao_2023", 2023), ("refit", 2023), ("teste_2024", 2024)):
        origem = pd.date_range(f"{ano}-06-01", periods=4, freq="D")
        kwargs = dict(x_bruto=np.arange(24, dtype=np.float32).reshape(4, 6),
                      y_bruto=np.arange(8, dtype=np.float32).reshape(4, 2) + 100,
                      localidade_id=ids, localidade=nomes, seq_len=6, pred_len=2, particao=fase)
        if horario:
            janelas[fase] = JanelasHorarias(**kwargs, origem_local=origem,
                                           origem_utc=origem.tz_localize("UTC") + pd.Timedelta(hours=3))
        else:
            datas = np.stack([(origem + pd.Timedelta(days=i)).to_numpy() for i in range(2)], axis=1)
            janelas[fase] = otim.m.JanelasDiretas(**kwargs, origem=origem, datas_alvo=datas)
    escalas = pd.DataFrame({"localidade_id": [0, 1], "localidade": ["Local 0", "Local 1"],
                           "minimo_treino_wm2": [0., 0.], "amplitude_escala_wm2": [200., 300.]})
    elevacoes = {p: np.full((4, 2), 30.) for p in ("validacao_2023", "teste_2024")} if horario else {}
    return otim.e.Contexto(tarefa, otim.m.ConfiguracaoMultirresolucao(sementes=(11, 23)),
                           (), janelas, {"selecao": escalas, "refit": escalas.copy()}, elevacoes, [])


@pytest.mark.parametrize("horario", [False, True])
def test_recorte_preserva_ultimos_valores_passados_alvos_e_origens(horario):
    original = _contexto(horario).janelas["validacao_2023"]
    menor = otim.recortar(original, 4)
    np.testing.assert_array_equal(menor.x_bruto, original.x_bruto[:, -4:])
    assert not np.shares_memory(menor.x_bruto, original.x_bruto)
    assert menor.y_bruto is original.y_bruto
    assert menor.localidade_id is original.localidade_id
    assert menor.pred_len == original.pred_len
    assert menor.particao == original.particao
    assert menor.seq_len == 4
    assert (menor.origem_utc is original.origem_utc if horario else menor.origem is original.origem)
    menor.x_bruto[0, 0] = -900
    assert original.x_bruto[0, -4] >= 0


@pytest.mark.parametrize("contexto", [True, False, 1, 0, -1, 7, 4.0])
def test_recorte_recusa_contexto_invalido(contexto):
    with pytest.raises(ValueError):
        otim.recortar(_contexto().janelas["ajuste"], contexto)


@pytest.mark.parametrize("horario,comprimento,curto", [(False, 365, 182), (True, 336, 168)])
def test_grade_preserva_protocolo_e_muda_contexto_capacidade_taxa(horario, comprimento, curto):
    ctx = _contexto(horario)
    ctx.tarefa = replace(ctx.tarefa, seq_len=comprimento)
    candidatos = otim.grade(ctx)
    assert len({c.nome for c in candidatos}) == len(candidatos)
    assert {c.contexto for c in candidatos} == {comprimento, curto}
    assert {c.perda for c in candidatos} == {"mae", "huber"}
    original = ctx.config
    for candidato in candidatos:
        config = candidato.configurar(ctx)
        assert config.sementes == original.sementes
        assert config.timesnet_d_model == candidato.dimensao
        assert config.timesnet_d_ff == candidato.dimensao * 2
        assert config.taxa_aprendizado == candidato.taxa
        assert config.max_epocas_diario == original.max_epocas_diario
    assert ctx.config is original


def _salvar_referencia(monkeypatch, tmp_path, ctx, alteracao=None):
    fonte = tmp_path / "fonte"
    pasta = fonte / ctx.tarefa.slug
    pasta.mkdir(parents=True)
    tabela = otim.e.tabela_chaves(ctx, "validacao_2023")
    coluna = ("previsao_bruta_timesnet_wm2" if ctx.tarefa.resolucao == "horaria"
              else "previsao_bruta_timesnet_ensemble_wm2")
    previstos = ctx.janelas["validacao_2023"].y_bruto.astype(float) + np.arange(8).reshape(4, 2)
    tabela[coluna] = previstos.reshape(-1)
    if alteracao is not None:
        tabela = alteracao(tabela, coluna)
    tabela.iloc[::-1].to_csv(pasta / "previsoes_validacao.csv.gz", index=False)
    monkeypatch.setattr(otim.e, "FONTE", fonte)
    return previstos


@pytest.mark.parametrize("horario", [False, True])
def test_referencia_alinha_por_chaves_mesmo_com_ordem_invertida(monkeypatch, tmp_path, horario):
    ctx = _contexto(horario)
    previstos = _salvar_referencia(monkeypatch, tmp_path, ctx)
    np.testing.assert_array_equal(otim.previsao_original(ctx, "validacao_2023"), previstos)


@pytest.mark.parametrize("problema", ["alvo", "ausente", "duplicada", "nao_finita"])
def test_referencia_rejeita_tabela_inconsistente(monkeypatch, tmp_path, problema):
    ctx = _contexto()

    def alterar(tabela, coluna):
        if problema == "alvo":
            tabela.loc[0, "ghi_real_wm2"] += 20
        elif problema == "ausente":
            tabela = tabela.iloc[1:]
        elif problema == "duplicada":
            tabela = pd.concat([tabela, tabela.iloc[:1]], ignore_index=True)
        else:
            tabela.loc[0, coluna] = np.inf
        return tabela

    _salvar_referencia(monkeypatch, tmp_path, ctx, alterar)
    with pytest.raises((ValueError, pd.errors.MergeError)):
        otim.previsao_original(ctx, "validacao_2023")


class _Rede(nn.Module):
    def __init__(self, deslocamento):
        super().__init__()
        self.peso = nn.Parameter(torch.tensor(float(deslocamento)))
        self.deslocamento = deslocamento


def _busca_falsa(monkeypatch, tmp_path, *, referencia=4., horario=False):
    ctx = _contexto(horario)
    saida = tmp_path / "saida"
    congelado = saida / ctx.tarefa.slug / "selecao_congelada.json"
    registros = []
    referencias = []
    candidatos = (otim.Candidato("mae", 6), otim.Candidato("huber", 4, perda="huber"))
    monkeypatch.setattr(otim, "preparar", lambda slug, modo: ctx)
    monkeypatch.setattr(otim, "grade", lambda ctx: candidatos)
    monkeypatch.setattr(otim, "contrato", lambda *args: {
        "sha256_contrato": "contrato-deterministico-do-teste", "criterio": "MAE_validacao", "limitacoes": []})

    def original(contexto, particao):
        if particao == "teste_2024":
            assert congelado.is_file(), "Referencia de teste consultada antes da selecao."
        referencias.append(particao)
        return contexto.janelas[particao].y_bruto.astype(float) + referencia

    def treinar(**kwargs):
        refit = kwargs.get("epocas_fixas") is not None
        if refit:
            assert congelado.is_file(), "Refit antes de congelar a escolha."
            assert "validacao" not in kwargs
            assert kwargs["ajuste"].particao == "refit"
            deslocamento = 50.
        else:
            assert not congelado.exists()
            assert kwargs["ajuste"].particao == "ajuste"
            assert kwargs["validacao"].particao == "validacao_2023"
            # MAE do ensemble (3) vence Huber (5), embora a media de MAEs
            # individuais (6) seja pior. Evita selecionar pela media errada.
            deslocamento = ({11: 9., 23: -3., 42: 3.}[kwargs["semente"]]
                            if kwargs["perda"] == "mae" else 5.)
        registros.append(kwargs)
        epocas = 2 if kwargs["semente"] in (11, 42) else 3
        hist = pd.DataFrame({"epoca": [1], "mae_validacao_wm2": [abs(deslocamento)]})
        return _Rede(deslocamento), epocas, hist

    monkeypatch.setattr(otim, "previsao_original", original)
    monkeypatch.setattr(otim.treino, "treinar", treinar)
    monkeypatch.setattr(otim.treino, "prever", lambda rede, j, escala, **k:
                        j.y_bruto.astype(float) + rede.deslocamento)
    return ctx, saida, registros, referencias


@pytest.mark.parametrize("horario", [False, True])
def test_selecao_usa_ensemble_validacao_e_refit_so_epocas_escolhidas(monkeypatch, tmp_path, horario):
    ctx, saida, registros, referencias = _busca_falsa(monkeypatch, tmp_path, horario=horario)
    status = otim.executar(ctx.tarefa.slug, saida, max_epocas=8, paciencia=2)
    assert status["candidato"] == "mae"
    assert status["MAE_validacao_wm2"] == pytest.approx(3.)
    assert status["MAE_teste_wm2"] == pytest.approx(50.)
    refits = [r for r in registros if r.get("epocas_fixas") is not None]
    assert [(r["semente"], r["epocas_fixas"]) for r in refits] == ([(42, 2)] if horario else [(11, 2), (23, 3)])
    assert all(r["config"].max_epocas_diario == 8 for r in registros)
    assert referencias == ["validacao_2023"]
    assert not (saida / f".{ctx.tarefa.slug}.lock").exists()
    destino = saida / ctx.tarefa.slug
    selecao = json.loads((destino / "selecao_congelada.json").read_text(encoding="utf-8"))
    assert selecao["selecao_concluida_antes_do_teste"] is True
    tabela = pd.read_csv(destino / "previsoes_teste.csv.gz")
    np.testing.assert_array_equal(tabela.previsao_bruta_timesnet_otimizada_wm2,
                                  ctx.janelas["teste_2024"].y_bruto.reshape(-1) + 50.)
    quantidade = len(registros)
    otim.executar(ctx.tarefa.slug, saida, max_epocas=8, paciencia=2)
    assert len(registros) == quantidade, "Retomada treinou novamente apesar dos caches completos."


@pytest.mark.parametrize("referencia", [1., 3.])
def test_referencia_original_pode_vencer_e_tem_preferencia_no_empate(monkeypatch, tmp_path, referencia):
    ctx, saida, registros, referencias = _busca_falsa(monkeypatch, tmp_path, referencia=referencia)
    status = otim.executar(ctx.tarefa.slug, saida)
    assert status["candidato"] == "referencia_original"
    assert status["MAE_teste_wm2"] == pytest.approx(referencia)
    assert all(r.get("epocas_fixas") is None for r in registros)
    assert referencias == ["validacao_2023", "teste_2024", "validacao_2023"]


def test_falha_treino_libera_lock_sem_congelar_selecao(monkeypatch, tmp_path):
    ctx, saida, _, _ = _busca_falsa(monkeypatch, tmp_path)

    def falhar(**kwargs):
        raise RuntimeError("falha de treinamento simulada")

    monkeypatch.setattr(otim.treino, "treinar", falhar)
    with pytest.raises(RuntimeError, match="simulada"):
        otim.executar(ctx.tarefa.slug, saida)
    assert not (saida / f".{ctx.tarefa.slug}.lock").exists()
    assert not (saida / ctx.tarefa.slug / "selecao_congelada.json").exists()
