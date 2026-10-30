"""Registra uma decisao revisada sobre troca CPU/CUDA, com evidencias hashadas."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from codigo_fonte.acompanhamento.metricas_quantizacao_todos import sha256


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def hashes_validos(dados):
    for path, digest in dados.items():
        exigir(sha256(Path(path)) == digest, f"Evidencia alterada: {path}")


def registrar(args):
    pasta = args.pasta.resolve()
    divergencia = pasta / f"controle_{args.particao}_divergencia.json"
    c = ler(pasta / "contrato_execucao.json")
    d, p, r, a = ler(divergencia), ler(args.parecer), ler(args.replay), ler(args.originais)
    exigir(c["modelo"] in {"GRU", "LSTM", "DilatedRNN"}, "Modelo fora da decisao revisada.")
    exigir(c["tarefa"]["slug"] in {"daily_30", "hourly_72_extension"}, "Tarefa fora da decisao revisada.")
    exigir(c["protocolo"]["regime"] == "atual" and c["modo"] == "completa", "Regime/modo incorreto.")
    exigir(d["novo_controle_por_dispositivo"] and d["dispositivo_original"] == "cpu" and d["dispositivo"] == "cuda",
           "A decisao cobre apenas mudanca CPU para CUDA definida previamente.")
    exigir(d["alvos_primarios_bitexatos"], "Alvos de outra grade.")
    exigir(all(x["contrato_sha256"] == c["sha256_contrato"] for x in (d, p, r)), "Contrato divergente.")
    exigir(all(x["modelo"] == c["modelo"] and x["tarefa"] == c["tarefa"]["slug"] for x in (p, r, a)), "Outro modelo/caso.")
    fase = "selecao" if args.particao == "validacao" else "refit"
    exigir(p["fase"] == r["fase"] == fase, "Outra fase.")
    exigir(a["aprovado"] is True and r["ok"] is True, "Reproducao nao aprovada.")
    exigir(r["normalizacao_e_inversao_independentes"] is True, "Falta verificacao independente de escala.")
    exigir({x["seed"] for x in r["checkpoints"]} == set(c["parametros"]["sementes"]), "Faltam sementes.")
    for cp in r["checkpoints"]:
        exigir(cp["aprovado"] and cp["max_diferenca_wm2"] <= 1e-6 and cp["alvos_substituidos_por_nan"], "Replay novo falhou.")
        hashes_validos({cp["checkpoint"]: cp["checkpoint_sha256"], cp["cache"]: cp["cache_sha256"]})
    for dados in (c["codigo"], c["entradas"], c["parametros"]["fontes_configuracao"],
                  p["arquivos_sha256"], r["codigo_auditoria_sha256"], a["codigo_auditoria_sha256"], a["fontes_sha256"]):
        hashes_validos(dados)
    for chave, pathkey in (("evidencia_complementar_loop", "testes"), ("relatorio_testes_loop", "arquivo")):
        hashes_validos({a[chave][pathkey]: a[chave]["sha256"]})
    hashes_validos({d["fonte"]: d["sha256"], d["fonte_alvos_primarios"]: d["sha256_alvos_primarios"]})
    exigir(bool(args.justificativa.strip()), "Justificativa vazia.")
    provas = (*args.evidencias, args.parecer, args.replay, args.originais,
              Path(a["relatorio_testes_loop"]["arquivo"]), Path(a["evidencia_complementar_loop"]["testes"]))
    registro = {"contrato_sha256": c["sha256_contrato"], "fonte_sha256": d["sha256"],
        "relatorio_divergencia_sha256": sha256(divergencia), "replay_checkpoint_original_aprovado": True,
        "arquitetura_e_loop_aprovados": True, "justificativa": args.justificativa,
        "auditoria_arquivos_sha256": {str(x.resolve()): sha256(x) for x in provas},
        "registrado_em_utc": datetime.now(timezone.utc).isoformat(),
        "limite": "CPs antigos apenas nas fases disponiveis, com politica numerica registrada. A comparacao de quantizacao usa o novo controle CUDA. Nao comprova retreinamento bitexato CPU/CUDA.",
        "fases_originais_sem_checkpoint": a["fases_sem_checkpoint_original"]}
    destino = pasta / f"aceite_controle_gpu_{args.particao}.json"
    exigir(not destino.exists(), "Decisao ja registrada; nao sobrescrever.")
    destino.write_text(json.dumps(registro, ensure_ascii=False, indent=2), encoding="utf-8")
    from codigo_fonte.experimentos.experimento_quantizacao_concorrentes import validar_aceite_gpu
    validar_aceite_gpu(destino, c["sha256_contrato"], d["sha256"], sha256(divergencia))
    print(f"Decisao revisada registrada: {destino}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pasta", type=Path, required=True)
    ap.add_argument("--particao", choices=("validacao", "teste"), required=True)
    ap.add_argument("--parecer", type=Path, required=True)
    ap.add_argument("--replay", type=Path, required=True)
    ap.add_argument("--originais", type=Path, required=True)
    ap.add_argument("--justificativa", required=True)
    ap.add_argument('--evidencias', type=Path, nargs='*', default=[])
    registrar(ap.parse_args())
