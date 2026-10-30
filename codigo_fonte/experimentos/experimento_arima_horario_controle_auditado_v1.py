"""Adaptador v1 restrito ao novo controle ARIMA horario de validacao.

Mantem treinamento, ordens, previsao, quantizacao e metricas do modulo
congelado. Importa o ajuste sem quantizacao ja executado e auditado,
registrando proveniencia e a divergencia historica explicitamente.
O refit continua usando a verificacao historica estrita original.
"""
from __future__ import annotations

from contextlib import contextmanager
import argparse
from pathlib import Path
import shutil

import numpy as np

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as base

RAIZ = base.RAIZ
ARQUIVO = RAIZ / "tmp/quantizacao_todos_modelos_20260929/antes_novo_controle_arima_horario_v1/arima"
EVIDENCIA = RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/diagnostico_arima_horario/controle_reexecutado_auditado_v1.json"
ESCOPO = {"regime": "atual", "tarefa": "hourly_72_extension", "modelo": "ARIMA",
          "fase": "selecao", "particao": "validacao", "variante": "sem_quantizacao"}
CONSTRUIR_ORIGINAL = base.construir_contrato
CONFERIR_ORIGINAL = base.conferir_controle
EXECUTAR_ORIGINAL = base.executar_fase


def validar_escopo(ctx, modelo):
    if (modelo != "ARIMA" or ctx.tarefa.slug != "hourly_72_extension" or
            ctx.protocolo["regime"] != "atual" or ctx.config.modo_execucao != "completa"):
        raise ValueError("Adaptador restrito a ARIMA horario atual completo.")
    if ctx.protocolo != base.motor.protocolo_padrao("atual"):
        raise ValueError("Adaptador exige o protocolo atual exato auditado.")


def ler_evidencia():
    ev = base.motor.ler_json(EVIDENCIA)
    if (ev.get("schema") != 1 or ev.get("id") != "arima_horario_novo_controle_v1" or
            ev.get("ok") is not True or ev.get("escopo") != ESCOPO or
            ev.get("controle_historico_reproduzido") is not False or
            ev.get("tolerancia_replay") != 1e-6 or
            ev.get("origem_arquivada") != str(ARQUIVO)):
        raise ValueError("Evidencia fora do escopo fechado deste adaptador.")
    if ev["comparacao_historica"]["delta_maximo"] != 4.490431751946744e-05:
        raise ValueError("Divergencia historica diferente da auditada.")
    replays = ev["replays"]
    if (len(replays) != 10 or {r["localidade_id"] for r in replays} != set(range(10)) or
            any(not r["bit_a_bit"] or r["delta_maximo"] != 0.0 for r in replays)):
        raise ValueError("Dez replays bitexatos obrigatorios para este controle.")
    base.motor.conferir_hashes(ev["fontes_sha256"])
    return ev


def construir_contrato(ctx, modelo):
    validar_escopo(ctx, modelo)
    ev = ler_evidencia()
    contrato = CONSTRUIR_ORIGINAL(ctx, modelo)
    contrato["codigo"].update(base.motor.hashes([Path(__file__)]))
    contrato["parametros"]["fontes_configuracao"].update(ev["fontes_sha256"])
    contrato["parametros"]["fontes_configuracao"].update(base.motor.hashes([EVIDENCIA]))
    contrato["controle_reexecutado_auditado"] = {
        "adaptador": "arima_horario_controle_auditado_v1", "escopo": ESCOPO,
        "referencia": "ajuste_novo_sem_quantizacao_reproduzido",
        "ajuste_importado_com_proveniencia": True, "historico_reproduzido": False,
        "diferenca_historica_maxima_wm2": ev["comparacao_historica"]["delta_maximo"],
        "contrato_origem": ev["hash_contrato_anterior"],
        "tolerancia_replay_wm2": 1e-6, "refit": "verificacao_historica_original_estrita"}
    contrato.pop("sha256_contrato")
    contrato["sha256_contrato"] = base.motor.hash_obj(contrato)
    return contrato


def conferir_controle(ctx, modelo, particao, bruto, destino):
    validar_escopo(ctx, modelo)
    if particao != "validacao":
        return CONFERIR_ORIGINAL(ctx, modelo, particao, bruto, destino)
    ev = ler_evidencia()
    cache = ARQUIVO / "sem_quantizacao/selecao/seed-1.npz"
    with np.load(cache, allow_pickle=False) as z:
        esperado = z["previsao"]
    atual = np.asarray(bruto)
    if atual.shape != esperado.shape or atual.dtype != esperado.dtype or atual.tobytes() != esperado.tobytes():
        raise ValueError("Controle importado diferente do cache exato auditado.")
    # O verificador congelado continua checando grade, alvos e comparacao
    # historica; somente a divergencia literal previamente auditada e aceita.
    mensagem = f"Controle ARIMA nao reproduzido: {ev['comparacao_historica']['delta_maximo']}"
    try:
        CONFERIR_ORIGINAL(ctx, modelo, particao, bruto, destino)
    except ValueError as erro:
        if str(erro) != mensagem:
            raise
    else:
        raise ValueError("Comparacao historica mudou; auditoria especifica precisa ser refeita.")
    registro = {"aplicavel": True, "aprovado": True,
                "novo_controle_reexecutado_auditado": True, "reproducao_historica_aprovada": False,
                "diferenca_maxima": 0.0, "referencia": "cache_novo_auditado", "tolerancia": 1e-6,
                "comparacao_historica": {"aprovado": False, "tolerancia": 1e-6,
                    "diferenca_maxima": ev["comparacao_historica"]["delta_maximo"]},
                "fontes": base.motor.hashes([EVIDENCIA, cache]),
                "proveniencia": "ajuste_previo_importado_sem_retreinamento_ou_mudanca_de_parametros"}
    base.m.salvar_json_atomico(registro, Path(destino) / "controle_validacao.json")
    return registro


def importar_controle(ctx, saida):
    validar_escopo(ctx, "ARIMA")
    contrato = construir_contrato(ctx, "ARIMA")
    pasta = Path(saida).resolve() / ctx.tarefa.slug / "arima"
    if pasta == ARQUIVO or ARQUIVO in pasta.parents:
        raise ValueError("Destino nao pode ser o arquivo preservado.")
    documento = pasta / "contrato_execucao.json"
    if documento.exists():
        if base.motor.ler_json(documento) != contrato:
            raise ValueError("Contrato de destino diverge do adaptador.")
    elif pasta.exists() and any(pasta.iterdir()):
        raise ValueError("Destino nao vazio sem contrato.")
    else:
        base.m.salvar_json_atomico(contrato, documento)
    pv = pasta / "sem_quantizacao"
    origem_meta = ARQUIVO / "sem_quantizacao/selecao/seed-1.json"
    meta = base.motor.ler_json(origem_meta)
    fontes = {}
    for logical, digest in meta["arquivos_sha256"].items():
        relativo = Path(logical).relative_to(base.SAIDA / "atual/hourly_72_extension/arima/sem_quantizacao")
        fonte, alvo = ARQUIVO / "sem_quantizacao" / relativo, pv / relativo
        if base.m.sha256_arquivo(fonte) != digest:
            raise ValueError("Artefato de controle arquivado alterado.")
        if alvo.exists():
            if base.m.sha256_arquivo(alvo) != digest:
                raise ValueError("Importacao anterior de controle diverge.")
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fonte, alvo)
        fontes[str(alvo)] = digest
    meta.update(contrato_sha256=contrato["sha256_contrato"], arquivos_sha256=fontes,
                ajuste_importado=True, contrato_original=ler_evidencia()["hash_contrato_anterior"],
                proveniencia=base.motor.hashes([origem_meta]))
    destino_meta = pv / "selecao/seed-1.json"
    if destino_meta.exists() and base.motor.ler_json(destino_meta) != meta:
        raise ValueError("Metadados da importacao divergem.")
    base.m.salvar_json_atomico(meta, destino_meta)
    proveniencia = {"ajuste_importado": True, "nenhum_ajuste_novo_alegado": True,
                   "fonte": str(ARQUIVO), "evidencia": str(EVIDENCIA),
                   "fontes": base.motor.hashes([origem_meta, EVIDENCIA]),
                   "contrato_original": meta["contrato_original"],
                   "contrato_destino": contrato["sha256_contrato"]}
    base.m.salvar_json_atomico(proveniencia, pasta / "proveniencia_controle_importado.json")


def executar_fase(ctx, modelo, saida, fase):
    validar_escopo(ctx, modelo)
    if fase == "selecao":
        importar_controle(ctx, saida)
    return EXECUTAR_ORIGINAL(ctx, modelo, saida, fase)


@contextmanager
def ativar_adaptador():
    anteriores = base.construir_contrato, base.conferir_controle, base.executar_fase
    base.construir_contrato = construir_contrato
    base.conferir_controle = conferir_controle
    base.executar_fase = executar_fase
    try:
        yield
    finally:
        base.construir_contrato, base.conferir_controle, base.executar_fase = anteriores


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=("hourly_72_extension",), required=True)
    ap.add_argument("--modelo", choices=("ARIMA",), required=True)
    ap.add_argument("--regime", choices=("atual",), default="atual")
    ap.add_argument("--fase", choices=("selecao", "refit", "congelar"), required=True)
    ap.add_argument("--saida", type=Path, default=base.SAIDA)
    ap.add_argument("--protocolo", type=Path)
    ap.parse_args()
    with ativar_adaptador():
        base.main()


if __name__ == "__main__":
    main()
