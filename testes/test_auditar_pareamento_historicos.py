"""Integridade entre coleta, protocolos, contratos e evidencias de treinamento."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys

import pytest

from codigo_fonte.analises_e_relatorios import auditar_pareamento_historicos as a


def salvar(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def assinar(obj):
    obj.pop("sha256_contrato", None)
    obj["sha256_contrato"] = a.hash_obj(obj)
    return obj


@pytest.fixture(scope="module")
def caso_base(tmp_path_factory):
    raiz = tmp_path_factory.mktemp("integridade_historica")
    rel = raiz / "historico"
    coleta_path = rel / "contrato.json"
    saida = raiz / "resultados"
    grupos = {}
    for grupo, n in a.QUANTIDADES_FONTES.items():
        grupos[grupo] = []
        for i in range(n):
            p = raiz / "dados" / grupo / f"{i}.csv"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(f"{grupo},{i}\n".encode())
            item = {"arquivo": p.relative_to(raiz).as_posix(), "sha256": a.sha256(p),
                    "bytes": p.stat().st_size}
            if grupo in ("horario", "amostras_30min"):
                item["ano"] = 1998 + i
            grupos[grupo].append(item)
    manifesto = rel / "manifesto.json"
    salvar(manifesto, {"ok": True})
    audit_path = rel / "auditoria_coleta.json"
    salvar(audit_path, {"ok": True})
    coleta = assinar({"ok": True, "aprovado": True, "entradas": grupos,
        "manifesto_horario": {"arquivo": manifesto.relative_to(raiz).as_posix(), "sha256": a.sha256(manifesto)},
        "auditorias": {"independente": {"arquivo": audit_path.relative_to(raiz).as_posix(), "sha256": a.sha256(audit_path)}}})
    salvar(coleta_path, coleta)
    carregador = raiz / "codigo_fonte/coleta_e_preparacao/historico_nsrdb_expandido.py"
    carregador.parent.mkdir(parents=True)
    carregador.write_text("# carregador fixture\n", encoding="utf-8")
    protos, auds, cts = {}, {}, {}
    adaptador = raiz / 'codigo_fonte/experimentos/experimento_atencao_deterministica_v1.py'
    adaptador.parent.mkdir(parents=True, exist_ok=True)
    adaptador.write_text('# adaptador fixture', encoding='utf-8')
    for regime in a.REGIMES:
        proto = {"regime": regime, "carregador_historico": True,
            "contrato_preparacao_dados": str(coleta_path),
            "sha256_contrato_preparacao": coleta["sha256_contrato"],
            "sha256_arquivo_contrato_preparacao": a.sha256(coleta_path),
            "pasta_diaria": str(raiz / "dados/diario"),
            "arquivos_historicos": [str(raiz / e["arquivo"]) for e in grupos["horario"]]
                + [str(coleta_path), str(manifesto), str(audit_path)]}
        protos[regime] = rel / f"protocolo_{regime}.json"
        salvar(protos[regime], proto)
        auds[regime] = {"ok": True, "publicavel": True, "regime": regime, "resultados": []}
        for tarefa in a.TAREFAS:
            for modelo in a.MODELOS:
                pasta = saida / regime / tarefa / modelo.lower().replace(" ", "_")
                fontes = ([Path(p) for p in proto["arquivos_historicos"]] + [carregador]
                          if tarefa == "hourly_72_extension" else [raiz / e["arquivo"] for e in grupos["diario"]])
                ct = assinar({"modelo": modelo, "tarefa": {"slug": tarefa}, "modo": "completa",
                              "protocolo": proto, "entradas": {str(p): a.sha256(p) for p in fontes}})
                cp = pasta / "contrato_execucao.json"
                if tarefa in ('daily_30', 'hourly_72_extension') and modelo in ('Transformer', 'Informer'):
                    ct['execucao_numerica'] = {'id':'atencao_cuda_deterministica_v1',
                        'algoritmos_deterministicos':True, 'warn_only':False, 'sdpa':'automatico'}
                    ct['codigo'] = {str(adaptador):a.sha256(adaptador)}
                    assinar(ct)
                salvar(cp, ct)
                sp = pasta / "selecao_congelada.json"
                salvar(sp, {"contrato_sha256": ct["sha256_contrato"]})
                auds[regime]["resultados"].append({"tarefa": tarefa, "modelo": modelo, "ok": True,
                                                   "selecao_sha256": a.sha256(sp)})
                cts[(regime, tarefa, modelo)] = cp
    caso = {"raiz": raiz, "coleta": coleta_path, "protos": protos, "auditoria_dados": audit_path,
            "auditorias": auds, "contratos": cts, "saida": saida}
    originais = {p: p.read_bytes() for p in raiz.rglob("*") if p.is_file()}
    return caso, originais


@pytest.fixture
def caso(caso_base):
    base, originais = caso_base
    yield copy.deepcopy(base)
    # Mesmas 70 fontes e 88 contratos em todos os cenarios; restaura somente
    # arquivos adulterados pelo teste, sem recriar centenas de arquivos.
    for p in base["raiz"].rglob("*"):
        if p.is_file() and p not in originais:
            p.unlink()
    for p, conteudo in originais.items():
        if not p.exists() or p.read_bytes() != conteudo:
            p.write_bytes(conteudo)


def executar(c):
    return a.auditar_integridade_historica(c["protos"][a.REGIMES[0]], c["protos"][a.REGIMES[1]],
        c["auditoria_dados"], c["saida"], c["auditorias"], raiz=c["raiz"])


def atualizar_coleta(c, novo):
    assinar(novo)
    salvar(c["coleta"], novo)
    for p in c["protos"].values():
        proto = a.ler(p)
        proto["sha256_contrato_preparacao"] = novo["sha256_contrato"]
        proto["sha256_arquivo_contrato_preparacao"] = a.sha256(c["coleta"])
        salvar(p, proto)


def atualizar_treino(c, chave, novo):
    cp = c["contratos"][chave]
    salvar(cp, assinar(novo))
    sp = cp.with_name("selecao_congelada.json")
    salvar(sp, {"contrato_sha256": novo["sha256_contrato"]})
    r = next(r for r in c["auditorias"][chave[0]]["resultados"]
             if (r["tarefa"], r["modelo"]) == chave[1:])
    r["selecao_sha256"] = a.sha256(sp)


def test_liga_70_fontes_aos_88_treinamentos_e_mensal_derivado_do_diario(caso):
    out, fontes = executar(caso)
    assert out["ok"] and out["quantidade_fontes_dados"] == 70
    assert len(out["contratos_treinamento"]) == 88
    assert all(r["grupo_dados_usado"] == "diario" for r in out["contratos_treinamento"]
               if r["tarefa"].startswith("monthly"))
    assert len(fontes) > 70


@pytest.mark.parametrize('alteracao', ['ausente', 'warn_only', 'ambiente_diferente', 'hash_adaptador'])
def test_rejeita_politica_de_atencao_incompativel_entre_historicos(caso, alteracao):
    chave = (a.REGIMES[1], 'daily_30', 'Transformer')
    ct = a.ler(caso['contratos'][chave])
    if alteracao == 'ausente':
        ct.pop('execucao_numerica')
    elif alteracao == 'warn_only':
        ct['execucao_numerica']['warn_only'] = True
    elif alteracao == 'ambiente_diferente':
        ct['execucao_numerica']['ambiente'] = {'torch':'outro'}
    else:
        ct['codigo'][next(iter(ct['codigo']))] = '0' * 64
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match='politica|politicas|Fonte alterada'):
        executar(caso)


@pytest.mark.parametrize("grupo", list(a.QUANTIDADES_FONTES))
def test_rejeita_dado_alterado_inclusive_amostra_e_mensal_nao_usados_no_motor(caso, grupo):
    item = a.ler(caso["coleta"])["entradas"][grupo][0]
    with (caso["raiz"] / item["arquivo"]).open("ab") as f:
        f.write(b"alterado")
    with pytest.raises(ValueError, match="Fonte alterada"):
        executar(caso)


def test_rejeita_fonte_ausente(caso):
    item = a.ler(caso["coleta"])["entradas"]["horario"][0]
    (caso["raiz"] / item["arquivo"]).unlink()
    with pytest.raises(ValueError, match="Fonte ausente"):
        executar(caso)


@pytest.mark.parametrize("campo", ["sha256_contrato_preparacao", "sha256_arquivo_contrato_preparacao"])
def test_rejeita_hash_declarado_incorreto_em_qualquer_protocolo(caso, campo):
    p = caso["protos"][a.REGIMES[1]]
    obj = a.ler(p)
    obj[campo] = "0" * 64
    salvar(p, obj)
    with pytest.raises(ValueError, match="Fonte alterada|Hash de preparacao"):
        executar(caso)


def test_rejeita_hash_interno_da_coleta_mesmo_se_hash_fisico_do_protocolo_atualizado(caso):
    coleta = a.ler(caso["coleta"])
    coleta["comentario"] = "alteracao sem assinatura interna"
    salvar(caso["coleta"], coleta)
    p = caso["protos"][a.REGIMES[0]]
    proto = a.ler(p)
    proto["sha256_arquivo_contrato_preparacao"] = a.sha256(caso["coleta"])
    salvar(p, proto)
    with pytest.raises(ValueError, match="Hash interno invalido"):
        executar(caso)


def test_rejeita_coleta_incompleta(caso):
    coleta = a.ler(caso["coleta"])
    coleta["entradas"]["amostras_30min"].pop()
    atualizar_coleta(caso, coleta)
    with pytest.raises(ValueError, match="Quantidade de fontes"):
        executar(caso)


def test_rejeita_fonte_duplicada_entre_grupos(caso):
    coleta = a.ler(caso["coleta"])
    coleta["entradas"]["mensal"][0] = copy.deepcopy(coleta["entradas"]["diario"][0])
    atualizar_coleta(caso, coleta)
    with pytest.raises(ValueError, match="Fonte duplicada"):
        executar(caso)


def test_rejeita_treinamento_com_hash_atual_mas_dataset_diferente(caso):
    chave = (a.REGIMES[0], "monthly_1", "TimesNet")
    ct = a.ler(caso["contratos"][chave])
    trocada = caso["raiz"] / "dataset_alheio.csv"
    trocada.write_text("1,2,3\n", encoding="utf-8")
    ct["entradas"].pop(next(iter(ct["entradas"])))
    ct["entradas"][str(trocada)] = a.sha256(trocada)
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match="Entradas do treinamento divergem"):
        executar(caso)


def test_rejeita_entrada_de_treino_sem_hash_esperado(caso):
    chave = (a.REGIMES[1], "daily_30", "ARIMA")
    ct = a.ler(caso["contratos"][chave])
    ct["entradas"][next(iter(ct["entradas"]))] = "f" * 64
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match="Entradas do treinamento divergem"):
        executar(caso)


def test_rejeita_protocolo_de_treino_diferente_do_cli(caso):
    chave = (a.REGIMES[0], "monthly_6", "LSTM")
    ct = a.ler(caso["contratos"][chave])
    ct["protocolo"]["dispositivos"] = {"LSTM": "cuda"}
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match="Protocolo do treinamento diverge"):
        executar(caso)


def test_rejeita_mensal_treinado_com_csv_mensal_em_vez_da_fonte_diaria_do_motor(caso):
    chave = (a.REGIMES[0], "monthly_6", "Climatologia")
    ct = a.ler(caso["contratos"][chave])
    ct["entradas"] = {str(caso["raiz"] / e["arquivo"]): e["sha256"]
                      for e in a.ler(caso["coleta"])["entradas"]["mensal"]}
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match="Entradas do treinamento divergem"):
        executar(caso)


def test_rejeita_auditoria_parcial(caso):
    caso["auditorias"][a.REGIMES[1]]["resultados"].pop()
    with pytest.raises(ValueError, match="44 pares"):
        executar(caso)


def test_rejeita_ok_verdadeiro_sem_ligacao_a_coleta(caso):
    p = caso["raiz"] / "auditoria_alheia.json"
    salvar(p, {"ok": True, "aprovado": True})
    caso["auditoria_dados"] = p
    with pytest.raises(ValueError, match="sem ligacao"):
        executar(caso)


def test_aceita_parecer_posterior_ligado_ao_contrato_vigente(caso):
    p = caso["raiz"] / "parecer_posterior.json"
    salvar(p, {"ok": True, "contrato": {"arquivo": str(caso["coleta"]),
        "sha256_arquivo": a.sha256(caso["coleta"]),
        "sha256_contrato": a.ler(caso["coleta"])["sha256_contrato"]}})
    caso["auditoria_dados"] = p
    assert executar(caso)[0]["ok"]


@pytest.mark.parametrize("ok,aprovado", [(False, True), (True, False)])
def test_rejeita_parecer_com_flags_de_aprovacao_contraditorias(caso, ok, aprovado):
    p = caso["raiz"] / "parecer_contraditorio.json"
    salvar(p, {"ok": ok, "aprovado": aprovado, "contrato": {"arquivo": str(caso["coleta"]),
        "sha256_arquivo": a.sha256(caso["coleta"]),
        "sha256_contrato": a.ler(caso["coleta"])["sha256_contrato"]}})
    caso["auditoria_dados"] = p
    with pytest.raises(ValueError, match="Auditoria da base historica nao aprovada"):
        executar(caso)


def test_rejeita_publicavel_com_par_reprovado(caso):
    caso["auditorias"][a.REGIMES[0]]["resultados"][0]["ok"] = False
    with pytest.raises(ValueError, match="par reprovado"):
        executar(caso)


def test_rejeita_selecao_diferente_da_auditoria_anterior(caso):
    cp = caso["contratos"][(a.REGIMES[1], "daily_30", "XGBoost")]
    sp = cp.with_name("selecao_congelada.json")
    selecao = a.ler(sp)
    selecao["alteracao"] = True
    salvar(sp, selecao)
    with pytest.raises(ValueError, match="Fonte alterada"):
        executar(caso)


def test_rejeita_selecao_de_outro_contrato_mesmo_com_hash_fisico_atualizado(caso):
    chave = (a.REGIMES[1], "daily_30", "GRU")
    sp = caso["contratos"][chave].with_name("selecao_congelada.json")
    salvar(sp, {"contrato_sha256": "0" * 64})
    r = next(r for r in caso["auditorias"][chave[0]]["resultados"]
             if (r["tarefa"], r["modelo"]) == chave[1:])
    r["selecao_sha256"] = a.sha256(sp)
    with pytest.raises(ValueError, match="Selecao auditada pertence a outro contrato"):
        executar(caso)


def test_rechecagem_final_detecta_mudanca_apos_primeira_leitura(tmp_path):
    p = tmp_path / "fonte.csv"
    p.write_bytes(b"origem")
    fontes = {}
    a.registrar_fonte(fontes, p)
    p.write_bytes(b"mudou")
    with pytest.raises(ValueError, match="antes da publicacao"):
        a.conferir_fontes_finais(fontes)


@pytest.mark.parametrize("tarefa,modelo", sorted(a.PARES_CUDA_AUTORIZADOS))
def test_aceita_apenas_sobrescrita_cuda_autorizada_por_par(caso, tarefa, modelo):
    chave = (a.REGIMES[0], tarefa, modelo)
    ct = a.ler(caso["contratos"][chave])
    ct["protocolo"]["dispositivos"] = {modelo: "cuda"}
    ct["parametros"] = {"dispositivo": "cuda"}
    atualizar_treino(caso, chave, ct)
    out, _ = executar(caso)
    alterados = [r for r in out["contratos_treinamento"]
                if r["transformacao_protocolo"]["tipo"] != "protocolo_cli_inalterado"]
    assert len(alterados) == 1
    assert alterados[0]["transformacao_protocolo"]["campo"] == f"dispositivos.{modelo}"


def test_cuda_autorizada_nao_permite_alterar_datas(caso):
    chave = (a.REGIMES[0], "daily_30", "GRU")
    ct = a.ler(caso["contratos"][chave])
    ct["protocolo"]["dispositivos"] = {"GRU": "cuda"}
    ct["protocolo"]["inicio_validacao"] = "2000-01-01"
    ct["parametros"] = {"dispositivo": "cuda"}
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match="Protocolo do treinamento diverge"):
        executar(caso)


def test_cuda_autorizada_exige_parametro_efetivo_compativel(caso):
    chave = (a.REGIMES[0], "daily_30", "GRU")
    ct = a.ler(caso["contratos"][chave])
    ct["protocolo"]["dispositivos"] = {"GRU": "cuda"}
    ct["parametros"] = {"dispositivo": "cpu"}
    atualizar_treino(caso, chave, ct)
    with pytest.raises(ValueError, match="CUDA diverge dos parametros"):
        executar(caso)


def test_falha_invalida_relatorio_previamente_aprovado(tmp_path, monkeypatch):
    path = tmp_path / "pareamento.json"
    salvar(path, {"ok": True, "publicavel": True})
    def falhar(args):
        raise ValueError("Fonte adulterada")
    monkeypatch.setattr(a, "auditar", falhar)
    monkeypatch.setattr(sys, "argv", ["auditor", "--auditoria-longo", "l.json",
        "--auditoria-curto", "c.json", "--auditoria-dados", "d.json", "--relatorio", str(path)])
    with pytest.raises(ValueError, match="Fonte adulterada"):
        a.main()
    assert a.ler(path) == {"ok": False, "publicavel": False, "erro": "ValueError: Fonte adulterada"}
