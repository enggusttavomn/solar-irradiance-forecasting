"""Resumo pareado com fixtures sinteticas; nunca produz feedback real."""
from copy import deepcopy
import json

import pandas as pd
import pytest

from codigo_fonte.analises_e_relatorios import resumir_historicos_quantizacao as r


def salvar(obj, path):
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def cenario(tmp_path, monkeypatch):
    registros = [{"tarefa": t, "modelo": m, "ok": True} for t in r.TAREFAS for m in r.MODELOS]
    curto, longo = [], []
    for indice, item in enumerate(registros):
        t, modelo = item["tarefa"], item["modelo"]
        delta = -2.0 if indice < 10 else 3.0 if indice < 25 else (5e-8 if indice % 2 else -5e-8)
        base = {"tarefa": t, "modelo": modelo, "horizonte": max(r.TAREFAS[t]),
                "particao": "teste", "variante": "sem_quantizacao", "MAE_wm2": 10.0,
                "N_localidades": 10, "N_origens": 120, "N_pontos": 120 * max(r.TAREFAS[t])}
        curto.append(base)
        longo.append({**base, "MAE_wm2": base["MAE_wm2"] + delta})
    # Linhas extras de validacao, quantizacao e horizontes parciais nao entram nas 44 comparacoes.
    for destino in (curto, longo):
        destino.append({**destino[0], "particao": "validacao", "MAE_wm2": 900.0})
        destino.append({**destino[0], "variante": "q64", "MAE_wm2": 800.0})
        destino.append({**destino[0], "horizonte": 24, "MAE_wm2": 700.0})
    paths = {nome: tmp_path / f"fixture_{nome}.json" for nome in ("longo", "curto", "pareamento")}
    docs = {
        "longo": {"regime": "historico_1998_2022", "resultados": deepcopy(registros)},
        "curto": {"regime": "historico_curto_pareado", "resultados": deepcopy(registros)},
    }
    for key, doc in docs.items():
        salvar(doc, paths[key])
    par = {"ok": True, "publicavel": True,
           "resultados": [{"tarefa": t, "particao": p, "observacoes_e_datas_iguais": True}
                          for t in r.TAREFAS for p in ("validacao", "teste")],
           "fontes_sha256": {str(paths[k].resolve()): r.sha256(paths[k]) for k in ("longo", "curto")}}
    salvar(par, paths["pareamento"])
    frames = {"longo": pd.DataFrame(longo).sample(frac=1, random_state=2),
              "curto": pd.DataFrame(curto).sample(frac=1, random_state=17)}
    def carregar(path):
        key = next(k for k in ("longo", "curto") if paths[k] == path)
        return docs[key], frames[key].copy()
    monkeypatch.setattr(r, "carregar_auditoria", carregar)
    saida = tmp_path / "apenas_fixture_sintetica.md"
    return paths, docs, frames, par, saida


def executar(cenario):
    paths, _, _, _, saida = cenario
    r.resumir(paths["longo"], paths["curto"], paths["pareamento"], saida)
    return saida


def test_juncao_por_chaves_44_controles_e_contagens(cenario):
    saida = executar(cenario)
    texto = saida.read_text(encoding="utf-8")
    meta = json.loads(saida.with_suffix(".json").read_text(encoding="utf-8"))
    assert meta["pares"] == 44
    assert (meta["menor_MAE_longo"], meta["maior_MAE_longo"], meta["empates_numericos"]) == (10, 15, 19)
    assert meta["tolerancia_empate_wm2"] == 1e-7
    assert len([linha for linha in texto.splitlines() if linha.startswith("| ")]) == 45
    for trecho in ("de 1998–2022", "abril de 2014", "em 10 das 44", "maior em 15", "nula em 19"):
        assert trecho in texto


def test_auditorias_invertidas_nao_geram_saida(cenario):
    paths, _, _, _, saida = cenario
    with pytest.raises(ValueError, match="invertidos"):
        r.resumir(paths["curto"], paths["longo"], paths["pareamento"], saida)
    assert not saida.exists()


@pytest.mark.parametrize("erro", ["auditoria_incompleta", "auditoria_duplicada", "auditoria_reprovada",
                                   "controle_ausente", "amostras_diferentes", "pareamento_incompleto",
                                   "pareamento_duplicado", "pareamento_reprovado", "hash_alterado"])
def test_recusa_incompletude_duplicacao_e_fonte_alterada(cenario, erro):
    paths, docs, frames, par, saida = cenario
    if erro == "auditoria_incompleta": docs["longo"]["resultados"].pop()
    if erro == "auditoria_duplicada": docs["longo"]["resultados"][-1] = docs["longo"]["resultados"][0]
    if erro == "auditoria_reprovada": docs["longo"]["resultados"][0]["ok"] = False
    if erro == "controle_ausente":
        f = frames["longo"]
        frames["longo"] = f[~((f.tarefa == "monthly_1") & (f.modelo == "ARIMA"))]
    if erro == "amostras_diferentes": frames["longo"].loc[:, "N_origens"] = 119
    if erro == "pareamento_incompleto": par["resultados"].pop()
    if erro == "pareamento_duplicado": par["resultados"][-1] = par["resultados"][0]
    if erro == "pareamento_reprovado": par["resultados"][0]["observacoes_e_datas_iguais"] = False
    if erro == "hash_alterado": paths["longo"].write_text("fonte alterada", encoding="utf-8")
    salvar(par, paths["pareamento"])
    with pytest.raises(ValueError):
        executar(cenario)
    assert not saida.exists()
    assert not saida.with_suffix(".json").exists()


@pytest.mark.parametrize("campo,valor", [("ok", False), ("publicavel", False), ("escopo_completo", False),
                                        ("modo", "smoke"), ("replay_novo_executado", False)])
def test_loader_real_rejeita_auditoria_incompleta_antes_de_ler_metricas(tmp_path, campo, valor):
    from codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos import carregar_auditoria
    documento = {"ok": True, "publicavel": True, "escopo_completo": True,
                 "modo": "completa", "replay_novo_executado": True}
    documento[campo] = valor
    path = tmp_path / "auditoria_incompleta_fixture.json"
    salvar(documento, path)
    with pytest.raises(ValueError, match="incompleta"):
        carregar_auditoria(path)
