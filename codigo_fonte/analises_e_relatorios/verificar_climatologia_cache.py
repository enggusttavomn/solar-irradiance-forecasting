"""Compara helper com codigo canonico e caches completos, sem treinar redes."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import time

import numpy as np
import pandas as pd

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as run

RAIZ = run.RAIZ
REL = RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/otimizacao_climatologia"
PARCIAL = RAIZ / "tmp/quantizacao_todos_modelos_20260929/antes_otimizacao_climatologia/climatologia"


def igual(a, b):
    if a.shape != b.shape or a.dtype != b.dtype or a.tobytes() != b.tobytes():
        raise AssertionError(f"Nao identicos bit a bit: {a.shape}/{b.shape}, delta={np.max(np.abs(a-b))}")


def amostrar(j):
    indices = []
    for ident in np.unique(j.localidade_id):
        locais = np.flatnonzero(j.localidade_id == ident)
        escolhidos = {int(locais[0]), int(locais[-1])}
        # Fronteiras anuais, meses e dias que cobrem 29/2 no horizonte.
        alvos = pd.DatetimeIndex(j.datas_alvo[locais].reshape(-1))
        especiais = ((alvos.month == 2) & (alvos.day == 29)) | ((alvos.month == 3) & (alvos.day == 1))
        linhas = np.flatnonzero(np.asarray(especiais).reshape(len(locais), -1).any(axis=1))
        for pos in (linhas[0], linhas[-1]) if len(linhas) else ():
            escolhidos.add(int(locais[pos]))
        escolhidos.update(int(locais[pos]) for pos in np.linspace(0, len(locais)-1, min(4, len(locais)), dtype=int))
        indices.extend(sorted(escolhidos))
    indices = np.asarray(indices)
    return SimpleNamespace(localidade_id=j.localidade_id[indices],
                           datas_alvo=j.datas_alvo[indices], y_bruto=j.y_bruto[indices])


def main():
    REL.mkdir(parents=True, exist_ok=True)
    registros, completos = [], []
    for tarefa in ("monthly_1", "monthly_6", "daily_30"):
        for fase, particao in (("selecao", "validacao"), ("refit", "teste")):
            print(f"[{tarefa}/{fase}] contexto completo", flush=True)
            ctx = run.motor.preparar_contexto(tarefa, fase)
            j = ctx.janelas[particao]
            amostra = amostrar(j)
            corte = run.q.corte_fase(ctx, fase)
            for variante, niveis in run.VARIANTES:
                series = ctx.series if niveis is None else tuple(
                    replace(s, ghi=run.q.quantizar_historico_bruto(s.ghi, ctx.escalas[fase], s.localidade_id, niveis))
                    for s in ctx.series)
                inicio = time.perf_counter()
                esperado = run.m.prever_climatologia(amostra, series, fim_ajuste_exclusivo=corte)
                segundos_original = time.perf_counter() - inicio
                inicio = time.perf_counter()
                atual = run.q.prever_climatologia_cache(amostra, series, fim_ajuste_exclusivo=corte)
                segundos_novo = time.perf_counter() - inicio
                igual(atual, esperado)
                registro = {"tarefa": tarefa, "fase": fase, "variante": variante, "bit_a_bit": True,
                            "origens": len(atual), "previsoes": int(atual.size),
                            "segundos_original": segundos_original, "segundos_cache": segundos_novo}
                registros.append(registro)
                print(f"  {variante}: bit a bit; {segundos_original:.3f}s -> {segundos_novo:.3f}s", flush=True)
                if niveis is None:
                    inicio = time.perf_counter()
                    bruto = run.q.previsoes_referencias(ctx, particao, niveis, modelos=["Climatologia"])["Climatologia"]
                    segundos = time.perf_counter() - inicio
                    controle = run.conferir_controle(ctx, "Climatologia", particao, bruto, REL / tarefa)
                    completos.append({"tarefa": tarefa, "fase": fase, "variante": variante,
                                      "origens": len(bruto), "previsoes": int(bruto.size),
                                      "segundos_previsao_nova": segundos, "controle_original": controle})
                cache = PARCIAL / variante / "selecao/seed-1.npz"
                if tarefa == "daily_30" and fase == "selecao" and cache.exists():
                    inicio = time.perf_counter()
                    bruto = run.q.previsoes_referencias(ctx, particao, niveis, modelos=["Climatologia"])["Climatologia"]
                    segundos = time.perf_counter() - inicio
                    with np.load(cache, allow_pickle=False) as z:
                        igual(bruto, z["previsao"])
                    antigos = run.motor.ler_json(cache.with_suffix(".json"))
                    completos.append({"tarefa": tarefa, "fase": fase, "variante": variante,
                                      "bit_a_bit_cache_anterior": True, "previsoes": int(bruto.size),
                                      "segundos_previsao_nova": segundos,
                                      "segundos_etapa_anterior_com_diagnosticos_e_serializacao": antigos["duracao_s"],
                                      "fonte": str(cache), "sha256": run.m.sha256_arquivo(cache)})
                run.m.salvar_json_atomico({"ok": False, "amostras": registros, "completos": completos}, REL / "equivalencia.json")
    resultado = {"ok": True, "amostras": registros, "completos": completos,
                 "n_comparacoes_amostradas": len(registros),
                 "concluido_em_utc": run.motor.agora(),
                 "codigo": run.motor.hashes([Path(run.q.__file__), Path(run.m.__file__),
                     RAIZ / "codigo_fonte/modelos/referencias_simples/climatologia_cache_localidade.py", Path(__file__)])}
    run.m.salvar_json_atomico(resultado, REL / "equivalencia.json")
    print({"ok": True, "amostras": len(registros), "completos": len(completos)}, flush=True)


if __name__ == "__main__":
    main()
