"""Reutiliza previsoes TimesNet ja auditadas em um formato comum, sem retreino."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.metricas_quantizacao_todos import (
    TAREFAS, VARIANTES, calcular_metricas, comparar_amostras, sha256, validar_previsoes,
)

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "resultados/quantizacao_todos_modelos_20260929"


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def salvar(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def importar(saida: Path):
    auditorias = [
        RAIZ / "relatorios/quantizacao_timesnet_20260923/auditoria_quantizacao.json",
        RAIZ / "relatorios/quantizacao_timesnet_quatro_casos_20260927/auditoria_quantizacao_resolucoes.json",
    ]
    for path in auditorias:
        a = ler(path)
        if not (a.get("aprovado") is True or a.get("ok") is True):
            raise ValueError(f"Auditoria fonte nao aprovada: {path}")
    resumo = []
    for tarefa, horizontes in TAREFAS.items():
        mensal = tarefa.startswith("monthly")
        fonte = RAIZ / ("resultados/quantizacao_timesnet_mensal_20260923" if mensal else
                        "resultados/quantizacao_timesnet_resolucoes_20260927") / tarefa
        status = ler(fonte / "status_execucao.json")
        selecao = ler(fonte / "selecao_congelada.json")
        if (status.get("modo") != "completa" or status.get("etapa") != "concluida"
                or status.get("teste_avaliado") is not True
                or selecao.get("selecao_concluida_antes_do_teste") is not True):
            raise ValueError(f"Fonte incompleta: {tarefa}")
        if {r["nome"]: r["niveis"] for r in selecao["ranking"]} != VARIANTES:
            raise ValueError("Ranking fonte com niveis inesperados.")
        for path, digest in selecao["fontes_selecao_sha256"].items():
            if sha256(Path(path)) != digest:
                raise ValueError(f"Fonte de selecao alterada: {path}")
        destino = saida / "atual" / tarefa / "timesnet"
        fontes = [fonte / n for n in ("status_execucao.json", "selecao_congelada.json",
                                     "contrato_execucao.json")] + auditorias
        amostras = {}
        matrizes = {}
        destino.mkdir(parents=True, exist_ok=True)
        for variante in VARIANTES:
            pasta = destino / variante
            pasta.mkdir(parents=True, exist_ok=True)
            for fase in ("validacao", "teste"):
                nome = f"previsoes_{fase}.csv" + ("" if mensal else ".gz")
                path = fonte / "variantes" / variante / nome
                df = pd.read_csv(path).rename(columns={
                    "previsao_bruta_timesnet_ensemble_wm2": "TimesNet_bruta_wm2",
                    "previsao_pos_timesnet_ensemble_wm2": "TimesNet_wm2",
                })
                df = validar_previsoes(df, tarefa, "TimesNet")
                if fase in amostras:
                    comparar_amostras(amostras[fase], df)
                else:
                    amostras[fase] = df
                metricas = calcular_metricas(df, tarefa, "TimesNet")
                metricas["variante"] = variante
                metricas["particao"] = fase
                if fase == "validacao":
                    mae = float(metricas.loc[metricas.horizonte == max(horizontes), "MAE_wm2"].iloc[0])
                    esperado = next(r["MAE_validacao_wm2"] for r in selecao["ranking"] if r["nome"] == variante)
                    if not np.isclose(mae, esperado, rtol=0, atol=1e-7):
                        raise ValueError(f"MAE de selecao divergente: {tarefa}/{variante}")
                matrizes[f"{variante}/{fase}"] = metricas.to_dict(orient="records")
                df.to_csv(pasta / f"previsoes_{fase}.csv.gz", index=False)
                metricas.to_csv(pasta / f"metricas_{fase}.csv", index=False)
                fontes.append(path)
            for diag in ("diagnostico_selecao.json", "diagnostico_refit.json"):
                path = fonte / "variantes" / variante / diag
                fontes.append(path)
                salvar(ler(path), pasta / diag)
        fontes_hash = {str(p.resolve()): sha256(p) for p in fontes}
        c = {"schema": 1, "origem": "reutilizacao_de_experimento_completo_auditado",
             "regime": "atual", "tarefa": tarefa, "modelo": "TimesNet", "modo": "completa",
             "rotulo": "TimesNet pura otimizada", "minmax": True,
             "variantes": VARIANTES, "fontes_sha256": fontes_hash,
             "contrato_original": ler(fonte / "contrato_execucao.json"),
             "gerador_sha256": sha256(Path(__file__)),
             "calculadora_metricas_sha256": sha256(RAIZ / "scripts/metricas_quantizacao_todos.py")}
        salvar(c, destino / "contrato.json")
        salvar({**selecao, "reutilizada": True, "fonte_original": str(fonte.resolve()),
                "modelo": "TimesNet"}, destino / "selecao_congelada.json")
        artefatos = {str(p.resolve()): sha256(p) for p in destino.rglob("*")
                     if p.is_file() and p.name not in {"manifesto_artefatos.json", "status.json"}}
        salvar({"arquivos": artefatos}, destino / "manifesto_artefatos.json")
        salvar({"etapa": "concluida", "modo": "completa", "resultado_publicavel": True,
                "reutilizado": True, "tarefa": tarefa, "modelo": "TimesNet",
                "atualizado_em_utc": datetime.now(timezone.utc).isoformat()}, destino / "status.json")
        resumo.append({"tarefa": tarefa, "variantes": len(VARIANTES), "metricas": matrizes})
        print(f"{tarefa}: quatro variantes importadas e metricas recalculadas.", flush=True)
    salvar(resumo, saida / "atual" / "reutilizacao_timesnet.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    importar(ap.parse_args().saida)
