"""Reproduz referencias canonicas e ARIMA robusto antes de novos experimentos.

Nao retreina nem sobrescreve experimentos existentes. Para ARIMA usa os
checkpoints historicos de refit e o caminho novo de inferencia sem
quantizacao; compara cada elemento com o cache historico publicado.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from codigo_fonte import experimento_baselines_adicionais as e
from codigo_fonte import quantizacao_referencias as q


def verificar(saida: Path, tarefas: list[str]) -> dict:
    resultados = []
    fontes = {}
    relatorio = {"ok": False, "tipo": "replay_sem_quantizacao_referencias_arima",
                 "tarefas": tarefas, "resultados": resultados, "fontes_sha256": fontes}
    for slug in tarefas:
        print(f"[{slug}] preparando contexto", flush=True)
        ctx = e.preparar_contexto(slug, "completa")
        e.verificar_alinhamento(ctx)
        for fase, particao, arquivo in (("selecao", "validacao_2023", "previsoes_validacao.csv.gz"),
                                       ("refit", "teste_2024", "previsoes_teste.csv.gz")):
            print(f"[{slug}/{particao}] referencias", flush=True)
            fonte = e.FONTE / slug / arquivo
            antigas = pd.read_csv(fonte)
            fontes[str(fonte.relative_to(e.RAIZ))] = e.m.sha256_arquivo(fonte)
            novos = q.previsoes_referencias(ctx, particao, None)
            for modelo, bruto in novos.items():
                prefixo = {"Persistencia": "persistencia", "Sazonal ingenuo": "sazonal_ingenuo",
                           "Climatologia": "climatologia"}[modelo]
                if ctx.tarefa.resolucao == "horaria" and modelo == "Climatologia":
                    # Adicao explicitamente nova; nao existe controle historico.
                    resultados.append({"tarefa": slug, "fase": fase, "modelo": modelo,
                                       "controle_historico": False, "nova_referencia": True,
                                       "n_valores": int(bruto.size), "finito": bool(np.isfinite(bruto).all())})
                    continue
                sufixo = "" if ctx.tarefa.resolucao == "horaria" else "_deterministica"
                for tipo, atual in (("bruta", bruto), ("pos", e.pos_processar(ctx, particao, bruto))):
                    anterior = antigas[f"previsao_{tipo}_{prefixo}{sufixo}_wm2"].to_numpy().reshape(atual.shape)
                    diferenca = float(np.max(np.abs(atual - anterior)))
                    if not np.allclose(atual, anterior, rtol=0, atol=1e-9):
                        raise AssertionError(f"Controle {slug}/{modelo}/{particao}/{tipo}: {diferenca}")
                    resultados.append({"tarefa": slug, "fase": fase, "modelo": modelo, "tipo": tipo,
                                       "controle_historico": True, "diferenca_maxima": diferenca,
                                       "n_valores": int(atual.size), "ok": True})
        pasta = e.SAIDA / slug / "arima_robusto"
        cache = pasta / "cache/deterministica.npz"
        fontes[str(cache.relative_to(e.RAIZ))] = e.m.sha256_arquivo(cache)
        ordens = q.ordens_de_csv(pasta / "selecao_arima.csv")
        janelas = ctx.janelas["teste_2024"]
        replay = np.empty_like(janelas.y_bruto, dtype=float)
        for serie in ctx.series:
            print(f"[{slug}/ARIMA] replay {serie.localidade}", flush=True)
            caminho_cp = pasta / "modelos" / f"localidade{serie.localidade_id}_refit.joblib"
            fontes[str(caminho_cp.relative_to(e.RAIZ))] = e.m.sha256_arquivo(caminho_cp)
            cp = {"modelo": joblib.load(caminho_cp), "niveis": None,
                  "localidade_id": serie.localidade_id, "escalas": ctx.escalas["refit"]}
            mascara = janelas.localidade_id == serie.localidade_id
            replay[mascara] = q.prever_checkpoint_arima(cp, janelas)
        with np.load(cache, allow_pickle=False) as z:
            antigo = z["teste_2024_bruta"]
            diferenca = float(np.max(np.abs(replay - antigo)))
            if not np.allclose(replay, antigo, rtol=0, atol=1e-9):
                raise AssertionError(f"Replay ARIMA {slug}: {diferenca}")
        resultados.append({"tarefa": slug, "fase": "refit", "modelo": "ARIMA", "tipo": "bruta",
                           "diferenca_maxima": diferenca, "n_valores": int(replay.size), "ok": True,
                           "ordens_controle": {k: list(v) for k, v in ordens.items()}})
        e.m.salvar_json_atomico(relatorio, saida)
    relatorio.update(ok=True, concluido_em_utc=datetime.now(timezone.utc).isoformat())
    e.m.salvar_json_atomico(relatorio, saida)
    return relatorio


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, default=e.RAIZ / "relatorios/quantizacao_todos_modelos_20260929/controles_referencias.json")
    ap.add_argument("--tarefas", nargs="+", default=["monthly_1", "monthly_6", "daily_30", "hourly_72_extension"])
    args = ap.parse_args()
    resultado = verificar(args.saida, args.tarefas)
    print({"ok": resultado["ok"], "verificacoes": len(resultado["resultados"]), "saida": str(args.saida)}, flush=True)


if __name__ == "__main__":
    main()
