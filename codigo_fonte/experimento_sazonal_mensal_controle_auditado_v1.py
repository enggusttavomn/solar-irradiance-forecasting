"""Calendario mensal auditavel do Sazonal ingenuo historico, sem alterar motores.

Series ME consultam o mesmo mes do ano anterior em seu ultimo dia. O contrato
legado longo permanece intacto e exige paridade dos quatro caches de selecao e
revisao independente. Uma selecao nova curta inclui esta fonte no contrato.
"""
from __future__ import annotations

import argparse
import copy
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from codigo_fonte import experimento_quantizacao_estatisticos as est

motor, m, q = est.motor, est.m, est.q
RAIZ = est.RAIZ
ID = "sazonal_mensal_calendario_auditado_v1"
MODELO = "Sazonal ingenuo"
TAREFAS = ("monthly_1", "monthly_6")
REGIMES = ("historico_1998_2022", "historico_curto_pareado")
CAMPO = "adaptacao_calendario_sazonal_mensal"
COMPLEMENTO = "contrato_complementar_sazonal_mensal_v1.json"
DIAGNOSTICO = RAIZ / "relatorios/quantizacao_todos_modelos_20260929/correcao_sazonal_mensal_v1"
POLITICA = {"id": ID, "modelo": MODELO, "tarefas": list(TAREFAS), "regimes": list(REGIMES),
            "regra_mensal": "mes_ano_anterior_fim_mes_canonico_Period_M_menos12",
            "regra_diaria_alterada": False, "regra_horaria_alterada": False,
            "quantizacao_alterada": False, "minmax_alterado": False,
            "alvos_alterados": False, "origens_alteradas": False,
            "selecao_legada_alterada": False, "metricas_usadas_como_criterio": False,
            "causalidade_original_preservada": True, "imputacao_ou_descarte_de_janelas": False}
CONSTRUIR_ORIGINAL = est.construir_contrato
DATA_ORIGINAL = m._data_ano_anterior


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def validar_escopo(ctx, modelo=MODELO):
    exigir(modelo == MODELO and ctx.tarefa.slug in TAREFAS
           and ctx.tarefa.resolucao == "mensal" and ctx.tarefa.frequencia == "ME"
           and ctx.tarefa.seq_len == 12
           and ctx.tarefa.pred_len == (1 if ctx.tarefa.slug == "monthly_1" else 6)
           and ctx.fase in ("selecao", "refit")
           and ctx.config.modo_execucao == "completa"
           and ctx.protocolo.get("regime") in REGIMES,
           "Adaptador restrito ao Sazonal mensal 1/6 historico completo.")
    esperado = motor.protocolo_padrao(ctx.protocolo["regime"])
    exigir(all(ctx.protocolo.get(k) == esperado[k] for k in
               ("inicio_dados", "fim_dados", "inicio_validacao", "inicio_teste", "carregador_historico")),
           "Cortes temporais historicos fora do escopo fechado.")
    exigir(asdict(ctx.tarefa) == asdict(motor.construir_tarefa(ctx.tarefa.slug, ctx.protocolo)),
           "Janelas/horizontes diferentes do protocolo historico.")
    exigir(all(s.frequencia == "ME" for s in ctx.series), "Serie mensal sem calendario ME.")


def data_ano_anterior(data: pd.Timestamp, *, mensal: bool) -> pd.Timestamp:
    if not mensal:
        return DATA_ORIGINAL(data, mensal=False)
    data = pd.Timestamp(data)
    exigir(not pd.isna(data) and data.tz is None and data == data.normalize()
           and data.is_month_end, "Alvo mensal deve ser data civil valida no fim do mes.")
    return (data.to_period("M") - 12).end_time.normalize()


@contextmanager
def _calendario():
    anterior = m._data_ano_anterior
    m._data_ano_anterior = data_ano_anterior
    try:
        yield
    finally:
        m._data_ano_anterior = anterior


def construir_contrato(ctx, modelo=MODELO):
    validar_escopo(ctx, modelo)
    contrato = CONSTRUIR_ORIGINAL(ctx, modelo)
    if ctx.protocolo["regime"] == "historico_curto_pareado":
        contrato[CAMPO] = copy.deepcopy(POLITICA)
        contrato["codigo"].update(motor.hashes([Path(__file__)]))
        contrato["sha256_contrato"] = motor.hash_obj({k: v for k, v in contrato.items()
                                                     if k != "sha256_contrato"})
    return contrato


def _contrato_escopo(contrato):
    tarefa, p = contrato.get("tarefa", {}), contrato.get("protocolo", {})
    exigir(contrato.get("modelo") == MODELO and tarefa.get("slug") in TAREFAS
           and tarefa.get("resolucao") == "mensal" and tarefa.get("frequencia") == "ME"
           and tarefa.get("seq_len") == 12
           and tarefa.get("pred_len") == (1 if tarefa.get("slug") == "monthly_1" else 6)
           and contrato.get("modo") == "completa" and p.get("regime") in REGIMES,
           "Contrato fora do escopo sazonal mensal historico.")
    esperado = motor.protocolo_padrao(p["regime"])
    exigir(all(p.get(k) == esperado[k] for k in
               ("inicio_dados", "fim_dados", "inicio_validacao", "inicio_teste", "carregador_historico")),
           "Cortes do contrato fora do escopo fechado.")
    exigir(contrato.get("targets_quantizados") is False
           and contrato.get("parametros", {}).get("sementes") == [-1]
           and contrato["parametros"].get("max_epocas") == 0,
           "Alvos/semente/epocas fora do contrato deterministico.")


def _global(pasta, contrato):
    global_path = pasta.parents[1] / "selecao_global_congelada.json"
    sel = motor.ler_json(global_path)
    exigir(sel.get("regime") == contrato["protocolo"]["regime"] and sel.get("modo") == "completa"
           and len(sel.get("pares", [])) == 44
           and [contrato["tarefa"]["slug"], MODELO] in sel["pares"],
           "Congelamento global completo das 44 escolhas ausente.")
    motor.conferir_hashes(sel["fontes_sha256"])
    for nome in ("contrato_execucao.json", "selecao_congelada.json"):
        path = pasta / nome
        exigir(sel["fontes_sha256"].get(str(path)) == m.sha256_arquivo(path),
               "Contrato/selecao individual diverge do congelamento global.")
    return global_path


def _bytes_hash(arr):
    return hashlib.sha256(arr.tobytes()).hexdigest()


def preparar_evidencia_paridade(ctx, pasta):
    """Recalcula so a referencia de validacao; nao ajusta nem escreve caches."""
    validar_escopo(ctx)
    exigir(ctx.fase == "selecao" and ctx.protocolo["regime"] == "historico_1998_2022",
           "Paridade legada exige selecao historica longa.")
    pasta = Path(pasta).resolve()
    contrato, selecao = est.validar_selecao(pasta)
    _contrato_escopo(contrato)
    exigir(CAMPO not in contrato and CONSTRUIR_ORIGINAL(ctx, MODELO) == contrato,
           "Contexto diferente do contrato legado original.")
    global_path = _global(pasta, contrato)
    j = ctx.janelas["validacao"]
    exigir(np.isfinite(j.y_bruto).all(), "Alvos de validacao invalidos.")
    novo = copy.copy(ctx)
    novo.janelas = dict(ctx.janelas)
    sem_alvos = copy.copy(j)
    object.__setattr__(sem_alvos, "y_bruto", np.full_like(j.y_bruto, np.nan))
    novo.janelas["validacao"] = sem_alvos
    registros, caminhos = [], [Path(__file__), pasta / "contrato_execucao.json",
                              pasta / "selecao_congelada.json", global_path]
    for variante, niveis in est.VARIANTES:
        cache = pasta / variante / "selecao/seed-1.npz"
        meta_path = cache.with_suffix(".json")
        meta = motor.ler_json(meta_path)
        esperado = {"contrato_sha256": contrato["sha256_contrato"], "niveis": niveis,
                    "seed": -1, "fase": "selecao", "variante": variante, "epocas": 0}
        exigir(all(meta.get(k) == v for k, v in esperado.items()), "Cache de selecao incompativel.")
        motor.conferir_hashes(meta["arquivos_sha256"])
        with np.load(cache, allow_pickle=False) as z:
            congelado = z["previsao"]
            exigir(int(z["epocas"].item()) == 0, "Referencia nao possui epocas.")
        legado = q.previsoes_referencias(ctx, "validacao", niveis, modelos=[MODELO])[MODELO]
        with _calendario():
            adaptado = q.previsoes_referencias(ctx, "validacao", niveis, modelos=[MODELO])[MODELO]
            nan = q.previsoes_referencias(novo, "validacao", niveis, modelos=[MODELO])[MODELO]
        for arr in (legado, adaptado, nan):
            exigir(arr.shape == congelado.shape and arr.dtype == congelado.dtype
                   and np.array_equal(arr, congelado) and arr.tobytes() == congelado.tobytes(),
                   "Paridade bitexata da validacao congelada reprovada.")
        registros.append({"variante": variante, "niveis": niveis, "shape": list(congelado.shape),
                          "dtype": str(congelado.dtype), "previsao_bytes_sha256": _bytes_hash(congelado),
                          "cache_sha256": m.sha256_arquivo(cache), "legado_bitexato": True,
                          "adaptado_bitexato": True, "alvos_nan_bitexatos": True})
        caminhos.extend([cache, meta_path])
    return {"schema": 1, "id": ID, "ok": True, "politica": copy.deepcopy(POLITICA),
            "regime": contrato["protocolo"]["regime"], "tarefa": contrato["tarefa"]["slug"],
            "contrato_original_sha256": contrato["sha256_contrato"],
            "selecao_original_sha256": m.sha256_arquivo(pasta / "selecao_congelada.json"),
            "congelamento_global_sha256": m.sha256_arquivo(global_path),
            "variantes": registros, "fontes_sha256": {**contrato["codigo"], **contrato["entradas"],
                                                         **motor.hashes(caminhos)},
            "metricas_usadas_como_criterio": False, "selecao_alterada": False,
            "causa": "ME_2021_02_28_requer_2020_02_29_nao_2020_02_28"}


def _caminhos_evidencia(pasta, evidencia=None, revisao=None):
    raiz = DIAGNOSTICO / pasta.parent.name
    return (Path(evidencia or raiz / "paridade_validacao.json").resolve(),
            Path(revisao or raiz / "revisao_independente.json").resolve())


def construir_contrato_complementar(pasta, evidencia=None, revisao=None):
    pasta = Path(pasta).resolve()
    contrato, _ = est.validar_selecao(pasta)
    _contrato_escopo(contrato)
    exigir(contrato["protocolo"]["regime"] == "historico_1998_2022" and CAMPO not in contrato,
           "Complemento restrito ao contrato longo legado.")
    global_path = _global(pasta, contrato)
    evidencia, revisao = _caminhos_evidencia(pasta, evidencia, revisao)
    ev, rev = motor.ler_json(evidencia), motor.ler_json(revisao)
    vinculos = {"contrato_original_sha256": contrato["sha256_contrato"],
               "selecao_original_sha256": m.sha256_arquivo(pasta / "selecao_congelada.json"),
               "congelamento_global_sha256": m.sha256_arquivo(global_path)}
    exigir(ev.get("schema") == 1 and ev.get("id") == ID and ev.get("ok") is True
           and ev.get("politica") == POLITICA and ev.get("regime") == contrato["protocolo"]["regime"]
           and ev.get("tarefa") == contrato["tarefa"]["slug"]
           and ev.get("metricas_usadas_como_criterio") is False and ev.get("selecao_alterada") is False
           and all(ev.get(k) == v for k, v in vinculos.items()),
           "Evidencia de paridade ausente ou desvinculada do legado.")
    registros = ev.get("variantes", [])
    exigir(len(registros) == 4 and [(r.get("variante"), r.get("niveis")) for r in registros] == list(est.VARIANTES),
           "Paridade exige quatro variantes na ordem original.")
    for r in registros:
        cache = pasta / r["variante"] / "selecao/seed-1.npz"
        exigir(all(r.get(k) is True for k in ("legado_bitexato", "adaptado_bitexato", "alvos_nan_bitexatos"))
               and r.get("cache_sha256") == m.sha256_arquivo(cache), "Paridade de variante nao comprovada.")
    exigir(isinstance(ev.get("fontes_sha256"), dict) and ev["fontes_sha256"], "Evidencia sem fontes hashadas.")
    motor.conferir_hashes(ev["fontes_sha256"])
    exigir(rev.get("schema") == 1 and rev.get("id") == ID and rev.get("aprovado") is True
           and rev.get("politica") == POLITICA and rev.get("tarefa") == ev["tarefa"]
           and rev.get("regime") == ev["regime"] and rev.get("metricas_usadas_como_criterio") is False
           and rev.get("evidencia_sha256") == m.sha256_arquivo(evidencia)
           and rev.get("codigo_adaptador_sha256") == m.sha256_arquivo(Path(__file__))
           and all(rev.get(k) == v for k, v in vinculos.items())
           and isinstance(rev.get("justificativa"), str) and rev["justificativa"].strip()
           and isinstance(rev.get("fontes_sha256"), dict) and rev["fontes_sha256"],
           "Revisao independente nao aprovada ou nao vinculada a paridade/fonte.")
    motor.conferir_hashes(rev["fontes_sha256"])
    complemento = {"schema": 1, "id": ID, "politica": copy.deepcopy(POLITICA),
                   "regime": ev["regime"], "tarefa": ev["tarefa"], **vinculos,
                   "evidencia": str(evidencia), "revisao": str(revisao),
                   "fontes_sha256": motor.hashes([Path(__file__), evidencia, revisao])}
    complemento["sha256_complemento"] = motor.hash_obj(complemento)
    return complemento


def registrar_contrato_complementar(pasta, evidencia=None, revisao=None):
    pasta = Path(pasta).resolve()
    esperado = construir_contrato_complementar(pasta, evidencia, revisao)
    caminho = pasta / COMPLEMENTO
    if caminho.exists():
        exigir(motor.ler_json(caminho) == esperado, "Complemento existente diverge da revisao.")
    else:
        m.salvar_json_atomico(esperado, caminho)
    return esperado


def validar_comp(pasta, contrato=None):
    """Gate readonly para auditor/replay; nao cria evidencias nem complemento."""
    pasta = Path(pasta).resolve()
    original, _ = est.validar_selecao(pasta)
    exigir(contrato is None or contrato == original, "Contrato informado diferente do congelado.")
    _contrato_escopo(original)
    if CAMPO in original:
        exigir(original["protocolo"]["regime"] == "historico_curto_pareado"
               and original[CAMPO] == POLITICA
               and original["codigo"].get(str(Path(__file__).resolve())) == m.sha256_arquivo(Path(__file__)),
               "Contrato novo sem politica/fonte exata do calendario.")
        return {"id": ID, "politica": copy.deepcopy(POLITICA), "tipo": "contrato_nativo",
                "contrato_sha256": original["sha256_contrato"],
                "codigo_adaptador_sha256": m.sha256_arquivo(Path(__file__))}
    salvo = motor.ler_json(pasta / COMPLEMENTO)
    esperado = construir_contrato_complementar(pasta, salvo.get("evidencia"), salvo.get("revisao"))
    exigir(salvo == esperado, "Complemento salvo diferente da evidencia revisada.")
    return {"id": ID, "politica": copy.deepcopy(POLITICA), "tipo": "complemento_legado",
            "contrato_sha256": original["sha256_contrato"],
            "contrato_complementar_sha256": esperado["sha256_complemento"],
            "contrato_complementar_arquivo_sha256": m.sha256_arquivo(pasta / COMPLEMENTO),
            "codigo_adaptador_sha256": m.sha256_arquivo(Path(__file__))}


def validar_contrato_complementar(pasta, contrato=None):
    return validar_comp(pasta, contrato)


def validar_metadados(pasta, fase, contrato=None, exigir_todos=True):
    exigir(fase in ("selecao", "refit"), "Fase invalida para proveniencia.")
    pasta = Path(pasta).resolve()
    provenance = validar_comp(pasta, contrato)
    # Selecao longa foi feita pelo legado e permanece bitexata, sem regravacao.
    if provenance["tipo"] == "complemento_legado" and fase == "selecao":
        return provenance
    for variante, _ in est.VARIANTES:
        meta_path = pasta / variante / fase / "seed-1.json"
        cache = meta_path.with_suffix(".npz")
        if not meta_path.exists() and not cache.exists() and not exigir_todos:
            continue
        exigir(meta_path.exists() and cache.exists(), "Cache adaptado incompleto.")
        meta = motor.ler_json(meta_path)
        exigir(meta.get(CAMPO) == provenance, "Cache sem proveniencia exata do calendario adaptado.")
        motor.conferir_hashes(meta["arquivos_sha256"])
        detalhes = motor.ler_json(meta_path.with_name("detalhes.json"))
        exigir(detalhes.get(CAMPO) == provenance, "Detalhes sem proveniencia exata do calendario.")
    return provenance


@contextmanager
def ativar_adaptador(ctx, modelo=MODELO, pasta=None, contrato=None):
    validar_escopo(ctx, modelo)
    exigir(pasta is not None, "Pasta auditavel obrigatoria para ativar adaptador.")
    pasta = Path(pasta).resolve()
    esperado = construir_contrato(ctx, modelo)
    arquivo = pasta / "contrato_execucao.json"
    if arquivo.exists():
        original = motor.ler_json(arquivo)
        exigir(original == esperado and (contrato is None or contrato == original),
               "Contexto/contrato diferente do contrato preservado.")
        if CAMPO not in original or ctx.fase == "refit":
            provenance = validar_comp(pasta, original)
        else:
            provenance = {"id": ID, "politica": copy.deepcopy(POLITICA), "tipo": "contrato_nativo",
                          "contrato_sha256": original["sha256_contrato"],
                          "codigo_adaptador_sha256": m.sha256_arquivo(Path(__file__))}
    else:
        exigir(ctx.fase == "selecao" and ctx.protocolo["regime"] == "historico_curto_pareado"
               and contrato is None and not (pasta.exists() and any(pasta.iterdir())),
               "Contrato legado/complemento obrigatorio antes de refit.")
        provenance = {"id": ID, "politica": copy.deepcopy(POLITICA), "tipo": "contrato_nativo",
                      "contrato_sha256": esperado["sha256_contrato"],
                      "codigo_adaptador_sha256": m.sha256_arquivo(Path(__file__))}
    if ctx.fase == "refit":
        validar_metadados(pasta, "refit", contrato, exigir_todos=False)
    construir_anterior, salvar_anterior, joblib_anterior = (
        est.construir_contrato, m.salvar_json_atomico, m.salvar_joblib_atomico)

    def salvar(obj, caminho):
        caminho = Path(caminho).resolve()
        try:
            rel = caminho.relative_to(pasta)
        except ValueError:
            return salvar_anterior(obj, caminho)
        if len(rel.parts) == 3 and rel.parts[0] in dict(est.VARIANTES) and rel.parts[1] == ctx.fase \
                and rel.name in ("seed-1.json", "detalhes.json"):
            obj = {**obj, CAMPO: copy.deepcopy(provenance)}
            if rel.name == "seed-1.json":
                obj["arquivos_sha256"] = {**obj["arquivos_sha256"], **motor.hashes([Path(__file__)])}
                if provenance["tipo"] == "complemento_legado":
                    obj["arquivos_sha256"].update(motor.hashes([pasta / COMPLEMENTO]))
        return salvar_anterior(obj, caminho)

    def salvar_joblib(obj, caminho):
        caminho = Path(caminho).resolve()
        try:
            rel = caminho.relative_to(pasta)
        except ValueError:
            return joblib_anterior(obj, caminho)
        if len(rel.parts) == 3 and rel.parts[0] in dict(est.VARIANTES) and rel.parts[1] == "modelos" \
                and rel.name == f"referencia_{ctx.fase}.joblib":
            obj = {**obj, CAMPO: copy.deepcopy(provenance)}
        return joblib_anterior(obj, caminho)

    est.construir_contrato, m.salvar_json_atomico, m.salvar_joblib_atomico = construir_contrato, salvar, salvar_joblib
    try:
        with _calendario():
            yield provenance
    finally:
        est.construir_contrato, m.salvar_json_atomico, m.salvar_joblib_atomico = (
            construir_anterior, salvar_anterior, joblib_anterior)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=TAREFAS, required=True)
    ap.add_argument("--modelo", choices=(MODELO,), required=True)
    ap.add_argument("--regime", choices=REGIMES, required=True)
    ap.add_argument("--fase", choices=("selecao", "refit", "congelar", "paridade"), required=True)
    ap.add_argument("--saida", type=Path, default=est.SAIDA)
    ap.add_argument("--protocolo", type=Path)
    ap.add_argument("--evidencia", type=Path)
    ap.add_argument("--revisao", type=Path)
    args = ap.parse_args()
    pasta = args.saida / args.regime / args.tarefa / est.slug_modelo(args.modelo)
    if args.fase == "congelar":
        validar_comp(pasta)
        return
    protocolo = motor.ler_json(args.protocolo) if args.protocolo else motor.protocolo_padrao(args.regime)
    exigir(protocolo["regime"] == args.regime, "Regime do protocolo difere do argumento.")
    fase = "selecao" if args.fase == "paridade" else args.fase
    if fase == "refit":
        if args.regime == "historico_1998_2022":
            registrar_contrato_complementar(pasta, args.evidencia, args.revisao)
        validar_comp(pasta)
    ctx = motor.preparar_contexto(args.tarefa, fase, "completa", protocolo, args.modelo)
    if args.fase == "paridade":
        exigir(args.evidencia is not None, "Informe destino exclusivo para evidencia de paridade.")
        exigir(not args.evidencia.exists(), "Nao sobrescrever evidencia existente.")
        m.salvar_json_atomico(preparar_evidencia_paridade(ctx, pasta), args.evidencia)
        return
    with ativar_adaptador(ctx, modelo=args.modelo, pasta=pasta):
        est.executar_fase(ctx, args.modelo, args.saida / args.regime, fase)
    validar_metadados(pasta, fase)


if __name__ == "__main__":
    main()
