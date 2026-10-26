"""Controle complementar fechado do refit XGBoost horario atual.

O treino e os quatro niveis seguem o motor congelado. A selecao permanece
inalterada. A referencia antiga continua reprovada; a nova referencia exige
replay e uma repeticao integral bitexata, com revisao independente vinculada.
A origem da divergencia antiga nao foi determinada.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import numpy as np

from codigo_fonte import experimento_quantizacao_concorrentes as base

RAIZ = base.RAIZ
ID = "xgboost_horario_controle_refit_auditado_v1"
ESCOPO = {"regime": "atual", "tarefa": "hourly_72_extension", "modelo": "XGBoost",
          "fase": "refit", "particao": "teste", "variante": "sem_quantizacao"}
DIAGNOSTICO = RAIZ / "relatorios/quantizacao_todos_modelos_20260929/diagnostico_xgboost_horario_v1"
EVIDENCIA = DIAGNOSTICO / "controle_reexecutado_auditado_v1.json"
REVISAO = DIAGNOSTICO / "revisao_independente_v1.json"
POLITICA = {"id": ID, "escopo": ESCOPO, "treinamento_alterado": False,
            "parametros_alterados": False, "selecao_alterada": False,
            "referencia": "refit_novo_sem_quantizacao_repetido_bitexatamente",
            "reproducao_legada_aprovada": False, "tolerancia_replay_wm2": 1e-6,
            "repeticao_integral_bitexata_obrigatoria": True,
            "metricas_usadas_como_criterio": False,
            "causa_divergencia_legada": "nao determinada"}
CONFERIR_ORIGINAL = base.conferir_controle
EXECUTAR_ORIGINAL = base.executar_fase


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def validar_escopo(ctx, modelo):
    exigir(modelo == "XGBoost" and ctx.tarefa.slug == ESCOPO["tarefa"]
           and ctx.protocolo == base.protocolo_padrao("atual")
           and ctx.fase == "refit" and ctx.config.modo_execucao == "completa",
           "Adaptador restrito ao refit XGBoost horario atual completo, protocolo original.")
    p = base.parametros(ctx, modelo)
    exigir(p["dispositivo"] == p["dispositivo_original"] == "cpu"
           and p["novo_controle_por_dispositivo"] is False and p["sementes"] == [42],
           "Dispositivo/semente fora do escopo fechado.")


def validar_relatorios(replay, piloto, repeticao):
    exigir(replay.get("old_config") == replay.get("new_config")
           and isinstance(replay.get("old_config"), dict), "Configuracoes efetivas dos boosters divergem.")
    dados = replay.get("dados", {})
    exigir(all(dados.get(k) is True for k in
           ("x_bruto", "y_bruto", "localidade_id", "localidade", "origem_utc", "origem_local")),
           "Janelas recriadas do construtor legado e atual divergem.")
    rr = replay.get("replay", {})
    exigir(np.isfinite(rr.get("old_cache_max", np.nan)) and rr["old_cache_max"] <= 1e-6
           and rr.get("new_cache_max") == 0.0 and rr.get("old_new_max") == 97.88775587081909,
           "Replays e comparacao antiga diferentes do diagnostico fechado.")
    labels = {"m_primeiro", "m_repeticao", "h_sequencial", "m_repeticao2"}
    exigir(isinstance(piloto, list) and len(piloto) == 4
           and {p.get("label") for p in piloto} == labels
           and all(p.get("new_tree0_exata") is True and p.get("old_tree0_exata") is False for p in piloto),
           "Piloto curto nao corresponde as quatro repeticoes auditadas.")
    exigir(repeticao.get("schema") == 1 and repeticao.get("id") == "xgboost_hourly_refit_repeticao_v1"
           and repeticao.get("ok") is True
           and repeticao.get("arvores_booster_json_bitexatas") is True
           and repeticao.get("previsoes_bitexatas") is True
           and repeticao.get("max_delta_previsao_wm2") == 0.0
           and repeticao.get("cpu_threads") == 1 and repeticao.get("dispositivo") == "cpu"
           and repeticao.get("random_state") == 42 and repeticao.get("quantizacao") is None
           and repeticao.get("metricas_usadas_como_criterio") is False
           and repeticao.get("controle_legado_reproduzido") is False,
           "Repeticao integral bitexata do novo controle nao comprovada.")
    exigir(repeticao.get("booster_original_sha256") == repeticao.get("booster_repeticao_sha256")
           and isinstance(repeticao.get("booster_original_sha256"), str),
           "Hashes dos boosters repetidos divergem.")


def preparar_evidencia(pasta):
    """Produz evidencia para revisao; nao aceita nem escreve o controle final."""
    pasta = Path(pasta).resolve()
    contrato, selecao = base.validar_selecao(pasta)
    exigir(contrato["modelo"] == "XGBoost" and contrato["tarefa"]["slug"] == ESCOPO["tarefa"]
           and contrato["modo"] == "completa" and contrato["protocolo"] == base.protocolo_padrao("atual"),
           "Contrato original fora do escopo.")
    relatorios = [DIAGNOSTICO / "replay_checkpoint.json", DIAGNOSTICO / "piloto_estado_rng.json",
                 DIAGNOSTICO / "repeticao_refit/verificacao.json"]
    replay, piloto, repeticao = [base.ler_json(p) for p in relatorios]
    validar_relatorios(replay, piloto, repeticao)
    with np.load(pasta / "sem_quantizacao/refit/seed42.npz", allow_pickle=False) as z:
        previsao_original = z["previsao"]
    with np.load(DIAGNOSTICO / "repeticao_refit/seed42_refit_repeticao.npz", allow_pickle=False) as z:
        previsao_repetida = z["previsao"]
    exigir(previsao_original.shape == previsao_repetida.shape
           and previsao_original.dtype == previsao_repetida.dtype
           and previsao_original.tobytes() == previsao_repetida.tobytes(),
           "Repeticao integral sem igualdade de shape, dtype e bytes da previsao.")
    exigir(repeticao["contrato_original_sha256"] == contrato["sha256_contrato"],
           "Repeticao nao corresponde ao contrato original.")
    grupos = [repeticao[k] for k in ("fontes_sha256", "codigo_sha256", "entradas_sha256", "fontes_configuracao_sha256")]
    exigir(repeticao["codigo_sha256"] == contrato["codigo"]
           and repeticao["entradas_sha256"] == contrato["entradas"]
           and repeticao["fontes_configuracao_sha256"] == contrato["parametros"]["fontes_configuracao"],
           "Hashes de codigo, entradas ou configuracao nao correspondem ao contrato.")
    for grupo in grupos:
        base.conferir_hashes(grupo)
    oficial = RAIZ / "resultados/avaliacao_horaria_timesnet_corrigida_retomavel"
    manifesto = base.ler_json(oficial / "manifesto_artefatos.json")
    for relativo in ("modelos/xgboost_multioutput_refit.joblib", "cache/refit/xgboost.npz",
                     "configuracao_execucao.json", "escalas_minmax_pre_corte.csv"):
        exigir(base.m.sha256_arquivo(oficial / relativo) == manifesto["arquivos"][relativo]["sha256"],
               "Fonte oficial antiga diferente do manifesto preservado.")
    global_path = pasta.parents[1] / "selecao_global_congelada.json"
    global_sel = base.ler_json(global_path)
    exigir(global_sel.get("regime") == "atual" and global_sel.get("modo") == "completa"
           and len(global_sel.get("pares", [])) == 44
           and [ESCOPO["tarefa"], "XGBoost"] in global_sel["pares"],
           "Congelamento global completo das 44 escolhas ausente.")
    base.conferir_hashes(global_sel["fontes_sha256"])
    exigir(global_sel["fontes_sha256"].get(str(pasta / "selecao_congelada.json"))
           == base.m.sha256_arquivo(pasta / "selecao_congelada.json"),
           "Selecao individual diferente do congelamento global.")
    fontes = base.hashes([*relatorios, global_path, oficial / "manifesto_artefatos.json",
                         oficial / "configuracao_execucao.json", oficial / "escalas_minmax_pre_corte.csv",
                         pasta / "contrato_execucao.json", pasta / "selecao_congelada.json",
                         oficial / "modelos/xgboost_multioutput_refit.joblib", oficial / "cache/refit/xgboost.npz",
                         pasta / "controle_teste_divergencia.json"])
    for grupo in grupos:
        fontes.update(grupo)
    return {"schema": 1, "id": ID, "ok": True, "politica": POLITICA,
            "contrato_original_sha256": contrato["sha256_contrato"],
            "selecao_original_sha256": base.m.sha256_arquivo(pasta / "selecao_congelada.json"),
            "congelamento_global_sha256": base.m.sha256_arquivo(global_path),
            "fontes_sha256": fontes, "fonte_referencia": str(pasta / "sem_quantizacao/refit/seed42.npz"),
            "replay_novo_bitexato": True, "repeticao_integral_bitexata": True,
            "replay_legado_aprovado": True, "reproducao_treinamento_legado_aprovada": False,
            "diferenca_legada_maxima_wm2": replay["replay"]["old_new_max"],
            "metricas_usadas_como_criterio": False,
            "limitacao": "Causa antiga nao determinada; repetibilidade limitada a esta maquina e ambiente. Janelas antigas foram reconstituidas pelo construtor; matrizes do treino antigo nao foram preservadas."
            }


def ler_evidencia(pasta, evidencia=EVIDENCIA, revisao=REVISAO):
    evidencia, revisao = Path(evidencia).resolve(), Path(revisao).resolve()
    esperado = preparar_evidencia(pasta)
    ev = base.ler_json(evidencia)
    exigir(ev == esperado, "Evidencia alterada ou diferente das fontes auditadas.")
    rev = base.ler_json(revisao)
    exigir(rev.get("schema") == 1 and rev.get("id") == ID and rev.get("aprovado") is True
           and rev.get("escopo") == ESCOPO and rev.get("metricas_usadas_como_criterio") is False
           and rev.get("evidencia_sha256") == base.m.sha256_arquivo(evidencia)
           and rev.get("codigo_adaptador_sha256") == base.m.sha256_arquivo(Path(__file__))
           and rev.get("contrato_original_sha256") == ev["contrato_original_sha256"]
           and rev.get("selecao_original_sha256") == ev["selecao_original_sha256"]
           and rev.get("congelamento_global_sha256") == ev["congelamento_global_sha256"]
           and isinstance(rev.get("justificativa"), str) and rev["justificativa"].strip(),
           "Revisao independente nao aprovada ou nao vinculada as fontes e selecao.")
    exigir(isinstance(rev.get("fontes_sha256"), dict) and rev["fontes_sha256"],
           "Revisao independente sem fontes hashadas.")
    base.conferir_hashes(rev["fontes_sha256"])
    return ev


def construir_contrato_complementar(pasta, evidencia=EVIDENCIA, revisao=REVISAO):
    pasta = Path(pasta).resolve()
    ev = ler_evidencia(pasta, evidencia, revisao)
    complemento = {"schema": 1, "id": ID, "politica": POLITICA,
                   "contrato_original_sha256": ev["contrato_original_sha256"],
                   "selecao_original_sha256": ev["selecao_original_sha256"],
                   "congelamento_global_sha256": ev["congelamento_global_sha256"],
                   "fontes_sha256": base.hashes([Path(__file__), Path(evidencia), Path(revisao)])}
    complemento["sha256_complemento"] = base.hash_obj(complemento)
    return complemento


def registrar_contrato_complementar(pasta):
    pasta = Path(pasta).resolve()
    esperado = construir_contrato_complementar(pasta)
    caminho = pasta / "contrato_complementar_controle_teste_xgboost_v1.json"
    if caminho.exists():
        exigir(base.ler_json(caminho) == esperado, "Contrato complementar existente diverge.")
    else:
        base.m.salvar_json_atomico(esperado, caminho)
    return esperado


def conferir_controle(ctx, modelo, particao, brutas, seeds, destino):
    validar_escopo(ctx, modelo)
    exigir(particao == "teste" and seeds == [42], "Controle complementar restrito a teste seed42.")
    pasta = Path(destino).resolve()
    complemento = registrar_contrato_complementar(pasta)
    ev = ler_evidencia(pasta)
    with np.load(ev["fonte_referencia"], allow_pickle=False) as z:
        esperado = z["previsao"]
    exigir(len(brutas) == 1 and isinstance(brutas[0], np.ndarray)
           and brutas[0].shape == esperado.shape and brutas[0].dtype == esperado.dtype
           and brutas[0].tobytes() == esperado.tobytes(),
           "Controle executado diferente da referencia nova repetida integralmente.")
    mensagem = f"Controle XGBoost nao reproduzido; diferencas salvas em {pasta / 'controle_teste_divergencia.json'}"
    try:
        CONFERIR_ORIGINAL(ctx, modelo, particao, brutas, seeds, destino)
    except ValueError as exc:
        exigir(str(exc) == mensagem, "Falha original diferente da divergencia literal auditada.")
    else:
        raise ValueError("Comparacao antiga mudou; necessario novo diagnostico fechado.")
    legado = base.ler_json(pasta / "controle_teste_divergencia.json")
    exigir(legado.get("aprovado") is False and legado.get("alvos_primarios_bitexatos") is True
           and legado.get("dispositivo") == legado.get("dispositivo_original") == "cpu"
           and legado.get("max_diferenca_por_seed") == {"42": ev["diferenca_legada_maxima_wm2"]}
           and legado.get("contrato_sha256") == ev["contrato_original_sha256"],
           "Comparacao antiga nao corresponde a divergencia independente auditada.")
    caminho_legado = pasta / "controle_teste_comparacao_legada.json"
    if caminho_legado.exists():
        exigir(base.ler_json(caminho_legado) == legado, "Comparacao antiga preservada diverge.")
    else:
        base.m.salvar_json_atomico(legado, caminho_legado)
    registro = {"aplicavel": True, "aprovado": True, "novo_controle_reexecutado_auditado": True,
                "novo_controle_refit_xgboost_reexecutado": True,
                "novo_controle_por_dispositivo": False, "reproducao_legada_aprovada": False,
                "referencia": POLITICA["referencia"], "tolerancia": 1e-6,
                "max_diferenca_por_seed": {"42": 0.0}, "replay_checkpoint_novo_bitexato": True,
                "repeticao_integral_bitexata": True, "metricas_usadas_como_criterio": False,
                "contrato_sha256": ev["contrato_original_sha256"],
                "contrato_complementar_sha256": complemento["sha256_complemento"],
                "selecao_original_sha256": ev["selecao_original_sha256"],
                "comparacao_legada": {"aprovado": False, "diferenca_maxima_wm2": ev["diferenca_legada_maxima_wm2"],
                                     "causa": "nao determinada"},
                "fontes_sha256": base.hashes([EVIDENCIA, REVISAO, caminho_legado,
                                             pasta / 'contrato_complementar_controle_teste_xgboost_v1.json'])}
    base.m.salvar_json_atomico(registro, pasta / "controle_teste.json")
    return registro


def validar_controle_adaptado(pasta):
    pasta = Path(pasta).resolve()
    esperado = construir_contrato_complementar(pasta)
    exigir(base.ler_json(pasta / "contrato_complementar_controle_teste_xgboost_v1.json") == esperado,
           "Contrato complementar diferente da evidencia revisada.")
    r = base.ler_json(pasta / "controle_teste.json")
    ev = ler_evidencia(pasta)
    fontes_esperadas = base.hashes([EVIDENCIA, REVISAO, pasta / "controle_teste_comparacao_legada.json",
                                  pasta / "contrato_complementar_controle_teste_xgboost_v1.json"])
    exigir(r.get("referencia") == POLITICA["referencia"] and r.get("tolerancia") == 1e-6
           and r.get("comparacao_legada") == {"aprovado": False,
               "diferenca_maxima_wm2": ev["diferenca_legada_maxima_wm2"], "causa": "nao determinada"}
           and r.get("fontes_sha256") == fontes_esperadas,
           "Referencia, comparacao antiga ou fontes obrigatorias do recibo divergem.")
    exigir(r.get("aprovado") is True and r.get("novo_controle_reexecutado_auditado") is True
           and r.get("novo_controle_refit_xgboost_reexecutado") is True
           and r.get("replay_checkpoint_novo_bitexato") is True
           and r.get("repeticao_integral_bitexata") is True
           and r.get("novo_controle_por_dispositivo") is False
           and r.get("reproducao_legada_aprovada") is False
           and r.get("metricas_usadas_como_criterio") is False
           and r.get("max_diferenca_por_seed") == {"42": 0.0}
           and r.get("contrato_complementar_sha256") == esperado["sha256_complemento"]
           and r.get("contrato_sha256") == esperado["contrato_original_sha256"]
           and r.get("selecao_original_sha256") == esperado["selecao_original_sha256"],
           "Controle novo nao possui recibo aprovado vinculado ao complemento.")
    legado_original = base.ler_json(pasta / "controle_teste_divergencia.json")
    legado_preservado = base.ler_json(pasta / "controle_teste_comparacao_legada.json")
    exigir(legado_original == legado_preservado and legado_original.get("aprovado") is False
           and legado_original.get("max_diferenca_por_seed") == {"42": ev["diferenca_legada_maxima_wm2"]},
           "Comparacao antiga preservada diferente da divergencia vinculada na evidencia.")
    base.conferir_hashes(r["fontes_sha256"])
    return esperado


@contextmanager
def ativar_adaptador():
    anterior = base.conferir_controle
    base.conferir_controle = conferir_controle
    try:
        yield
    finally:
        base.conferir_controle = anterior


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=("hourly_72_extension",), required=True)
    ap.add_argument("--modelo", choices=("XGBoost",), required=True)
    ap.add_argument("--regime", choices=("atual",), default="atual")
    ap.add_argument("--fase", choices=("refit",), required=True)
    ap.add_argument("--saida", type=Path, default=base.SAIDA)
    args = ap.parse_args()
    pasta = args.saida / args.regime / args.tarefa / args.modelo.lower()
    registrar_contrato_complementar(pasta)
    ctx = base.preparar_contexto(args.tarefa, args.fase, "completa", base.protocolo_padrao("atual"), args.modelo)
    with ativar_adaptador():
        EXECUTAR_ORIGINAL(ctx, args.modelo, args.saida / args.regime, args.fase)


if __name__ == "__main__":
    main()