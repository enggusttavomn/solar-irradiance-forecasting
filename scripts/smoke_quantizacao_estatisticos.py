"""Smoke real reduzido: todas selecoes estatisticas antes de qualquer refit."""
from __future__ import annotations

import argparse
from pathlib import Path

from codigo_fonte import experimento_quantizacao_estatisticos as run


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, default=run.RAIZ / "tmp/quantizacao_todos_modelos_20260929/smoke_estatisticos")
    ap.add_argument("--tarefas", nargs="+", default=["monthly_1", "monthly_6", "daily_30", "hourly_72_extension"])
    ap.add_argument("--modelos", nargs="+", choices=run.MODELOS, default=list(run.MODELOS))
    args = ap.parse_args()
    saida = args.saida / "atual"
    arquivos = []
    for tarefa in args.tarefas:
        ctx = run.motor.preparar_contexto(tarefa, "selecao", "smoke", run.motor.protocolo_padrao(), None)
        for modelo in args.modelos:
            run.executar_fase(ctx, modelo, saida, "selecao")
            arquivos.append(saida / tarefa / run.slug_modelo(modelo) / "selecao_congelada.json")
    global_freeze = {"modo": "smoke", "selecao_concluida_antes_refit": True,
                     "tarefas": args.tarefas, "modelos": args.modelos,
                     "fontes_selecao": run.motor.hashes(arquivos), "congelado_em_utc": run.motor.agora()}
    run.m.salvar_json_atomico(global_freeze, saida / "selecao_global_congelada.json")
    for tarefa in args.tarefas:
        run.motor.conferir_hashes(global_freeze["fontes_selecao"])
        ctx = run.motor.preparar_contexto(tarefa, "refit", "smoke", run.motor.protocolo_padrao(), None)
        for modelo in args.modelos:
            run.executar_fase(ctx, modelo, saida, "refit")
            run.validar_selecao(saida / tarefa / run.slug_modelo(modelo))
    relatorio = {"ok": True, "modo": "smoke", "resultado_publicavel": False,
                 "tarefas": args.tarefas, "modelos": args.modelos,
                 "n_variantes": len(run.VARIANTES),
                 "n_execucoes": len(args.tarefas) * len(args.modelos) * len(run.VARIANTES) * 2,
                 "concluido_em_utc": run.motor.agora(), "selecao_global": global_freeze}
    run.m.salvar_json_atomico(relatorio, saida / "smoke_concluido.json")
    print({"ok": True, "execucoes": relatorio["n_execucoes"], "saida": str(saida)}, flush=True)


if __name__ == "__main__":
    main()
