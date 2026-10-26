"""Monitora a fila estatistica existente; nao inicia ou altera experimentos."""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import time

RAIZ = Path(__file__).resolve().parents[1]
REL = RAIZ / "relatorios/quantizacao_todos_modelos_20260929"
RESULTADOS = RAIZ / "resultados/quantizacao_todos_modelos_20260929/atual"
TAREFAS = ("daily_30", "hourly_72_extension", "monthly_6", "monthly_1")
MODELOS = ("Climatologia", "Persistencia", "Sazonal ingenuo", "ARIMA")
VARIANTES = ("sem_quantizacao", "q64", "q128", "q256")


def ler(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inspecionar():
    registros = []
    for tarefa in TAREFAS:
        for modelo in MODELOS:
            pasta = RESULTADOS / tarefa / modelo.lower().replace(" ", "_")
            arquivo = pasta / "selecao_congelada.json"
            if not arquivo.exists():
                continue
            selecao = ler(arquivo)
            controle = ler(pasta / "controle_validacao.json")
            registro = {"tarefa": tarefa, "modelo": modelo,
                        "selecao_congelada": str(arquivo), "controle": controle,
                        "ranking": selecao["ranking"], "ordens_iguais_controle": None}
            if {v["nome"] for v in selecao["ranking"]} != set(VARIANTES):
                raise ValueError(f"Variantes incompletas: {arquivo}")
            if not selecao["selecao_concluida_antes_refit"]:
                raise ValueError(f"Selecao nao congelada: {arquivo}")
            if controle["aplicavel"]:
                if not controle["aprovado"]:
                    raise ValueError(f"Controle reprovado: {pasta}")
            elif not (modelo == "Climatologia" and tarefa == "hourly_72_extension"):
                raise ValueError(f"Controle inesperadamente nao aplicavel: {pasta}")
            if modelo == "ARIMA":
                fonte = (RAIZ / "resultados/avaliacao_baselines_revisao_20260912" /
                         tarefa / "arima_robusto/selecao_arima.csv")
                with fonte.open(encoding="utf-8", newline="") as stream:
                    originais = {r["localidade"]: list(ast.literal_eval(r["ordem"]))
                                 for r in csv.DictReader(stream)
                                 if r["fase"] == "selecao" and r["selecionada"].lower() == "true"}
                if not originais or originais != selecao["ordens_arima_controle"]:
                    raise ValueError(f"Ordem do controle ARIMA alterada: {pasta}")
                for variante in VARIANTES:
                    detalhes = ler(pasta / variante / "selecao/detalhes.json")
                    if detalhes["ordens"] != originais:
                        raise ValueError(f"Ordem ARIMA diverge: {pasta / variante}")
                registro["ordens_iguais_controle"] = True
                registro["ordens_arima"] = originais
            registros.append(registro)
    return registros


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--uma-vez", action="store_true")
    args = ap.parse_args()
    runner = REL / "fila_estatisticos/atual/completa/runner.json"
    destino = REL / "fila_estatisticos/atual/completa/controle_selecoes_monitor.json"
    anterior = None
    while True:
        estado = ler(runner)
        registros = inspecionar()
        resumo = {"etapa": estado["etapa"], "selecoes": len(registros),
                  "concluidos_runner": len(estado["concluidos"]), "falhas": estado["falhas"],
                  "processos": [[p["tarefa"], p["modelo"], p["pid"]] for p in estado["processos"]]}
        assinatura = json.dumps(resumo, sort_keys=True)
        if assinatura != anterior:
            print(json.dumps(resumo, ensure_ascii=False), flush=True)
            anterior = assinatura
            payload = {"ok": len(registros) == 16 and not estado["falhas"],
                       "atualizado_em_utc": datetime.now(timezone.utc).isoformat(),
                       "escopo": "monitoramento_selecao; auditoria_independente_ainda_obrigatoria",
                       **resumo, "registros": registros}
            tmp = destino.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(destino)
        if args.uma_vez or estado["etapa"] in ("selecao_concluida", "concluida", "erro", "interrompida"):
            if estado["falhas"]:
                for falha in estado["falhas"]:
                    if "log" in falha:
                        print(Path(falha["log"]).read_text(encoding="utf-8")[-6000:], flush=True)
                raise SystemExit(1)
            return
        time.sleep(10)


if __name__ == "__main__":
    main()
