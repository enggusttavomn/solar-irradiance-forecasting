"""Audita compactacao sem alterar checkpoints ou resultados originais.

Reproduz todas as previsoes dos 40 checkpoints canonicos de refit e de todos
os checkpoints disponiveis no smoke quantizado. A equivalencia e literal
(bytes float64), incluindo inicializacao do filtro em uma janela por CP.
"""
from __future__ import annotations

import argparse
import gc
import io
from pathlib import Path

import joblib
import numpy as np

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as r
from codigo_fonte.modelos.referencias_simples.arima_checkpoint_compacto import compactar_resultado, hash_array


def iguais_bits(a, b):
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def verificar_cp(path, payload, janelas, esperado, fonte_cache):
    original = payload["modelo"]
    novo = {**payload, "modelo": compactar_resultado(original)}
    buffer = io.BytesIO()
    joblib.dump(novo, buffer)
    bytes_compacto = len(buffer.getvalue())
    buffer.seek(0)
    reaberto = joblib.load(buffer)
    compacto = reaberto["modelo"]
    if not iguais_bits(original.params, compacto.params):
        raise AssertionError("Parametros modificados pela compactacao.")
    if "serie_ajuste_quantizada" in payload and not iguais_bits(payload["serie_ajuste_quantizada"], reaberto["serie_ajuste_quantizada"]):
        raise AssertionError("Historico modificado pela compactacao.")
    previsto = r.q.prever_checkpoint_arima(reaberto, janelas)
    if not iguais_bits(previsto, esperado):
        raise AssertionError(f"Forecast divergente: {path}; delta={np.max(np.abs(previsto-esperado))}")
    ident = reaberto["localidade_id"]
    x = r.q.normalizar_entradas(janelas, reaberto["escalas"], reaberto["niveis"])
    contexto = x[janelas.localidade_id == ident][0].astype(float)
    velho = original.apply(contexto, refit=False)
    novo_estado = compacto.apply(contexto, refit=False)
    for atributo in ("initial_state", "initial_state_cov"):
        if not iguais_bits(getattr(velho.filter_results, atributo), getattr(novo_estado.filter_results, atributo)):
            raise AssertionError(f"Inicializacao divergente: {path}/{atributo}")
    return {"checkpoint_original": str(path), "sha256_original": r.m.sha256_arquivo(path),
            "fonte_previsoes": str(fonte_cache), "niveis": reaberto["niveis"],
            "localidade_id": int(ident), "fase": reaberto["fase"],
            "ordem": list(compacto.especificacao["order"]), "trend": compacto.especificacao["trend"],
            "n_previsoes": int(previsto.size), "n_contextos": len(previsto),
            "bit_a_bit": True, "inicializacao_bit_a_bit": True, "delta_maximo": 0.0,
            "bytes_original": path.stat().st_size, "bytes_compacto": bytes_compacto,
            "serie_ajuste_sha256": hash_array(reaberto["serie_ajuste_quantizada"])}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", type=Path, default=r.RAIZ / "tmp/quantizacao_todos_modelos_20260929/smoke_estatisticos_roundtrip/atual")
    ap.add_argument("--saida", type=Path, default=r.RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/arima_compacto_equivalencia.json")
    args = ap.parse_args()
    registros = []
    tarefas = ("monthly_1", "monthly_6", "daily_30", "hourly_72_extension")
    def salvar(completo=False):
        relatorio = {"ok": completo, "registros": registros,
                     "checkpoints": len(registros), "codigo": r.motor.hashes([Path(__file__), r.RAIZ / "codigo_fonte/modelos/referencias_simples/arima_checkpoint_compacto.py"]),
                     "bytes_originais": sum(x["bytes_original"] for x in registros),
                     "bytes_compactos": sum(x["bytes_compacto"] for x in registros),
                     "previsoes": sum(x["n_previsoes"] for x in registros),
                     "atualizado_em_utc": r.motor.agora()}
        r.m.salvar_json_atomico(relatorio, args.saida)
    for tarefa in tarefas:
        print(f"[{tarefa}] canonicos completos", flush=True)
        ctx = r.e.preparar_contexto(tarefa, "completa")
        j = ctx.janelas["teste_2024"]
        pasta = r.e.SAIDA / tarefa / "arima_robusto"
        fonte_cache = pasta / "cache/deterministica.npz"
        with np.load(fonte_cache, allow_pickle=False) as z:
            esperado = z["teste_2024_bruta"]
        for serie in ctx.series:
            ident = serie.localidade_id
            path = pasta / "modelos" / f"localidade{ident}_refit.joblib"
            payload = {"modelo": joblib.load(path), "fase": "refit", "niveis": None,
                       "localidade_id": ident, "escalas": ctx.escalas["refit"],
                       "serie_ajuste_quantizada": r.e.serie_ajuste_arima(ctx, serie, "refit")}
            registros.append({"grupo": "canonico", "tarefa": tarefa,
                              **verificar_cp(path, payload, j, esperado[j.localidade_id == ident], fonte_cache)})
            print(f"  {serie.localidade}: bit a bit", flush=True)
            del payload
            gc.collect()
        salvar()
        del ctx, j, esperado
        gc.collect()
        for fase, part in (("selecao", "validacao"), ("refit", "teste")):
            paths = sorted((args.smoke / tarefa / "arima").glob(f"*/modelos/localidade*_{fase}.joblib"))
            if not paths:
                continue
            print(f"[{tarefa}] smoke {fase}: {len(paths)} checkpoints", flush=True)
            ctx = r.motor.preparar_contexto(tarefa, fase, "smoke")
            j = ctx.janelas[part]
            for path in paths:
                fonte_cache = path.parent.parent / fase / "seed-1.npz"
                payload = joblib.load(path)
                ident = payload["localidade_id"]
                if fonte_cache.exists():
                    with np.load(fonte_cache, allow_pickle=False) as z:
                        esperado = z["previsao"][j.localidade_id == ident]
                    tipo_referencia = "cache_original"
                else:
                    # O smoke foi interrompido por falta de espaco prevista:
                    # este CP ja estava completo, mas o cache conjunto ainda
                    # nao existia. Compare diretamente com o modelo original.
                    esperado = r.q.prever_checkpoint_arima(payload, j)
                    fonte_cache = path
                    tipo_referencia = "replay_modelo_original_checkpoint_de_execucao_interrompida"
                registros.append({"grupo": "smoke", "tarefa": tarefa,
                                  "tipo_referencia": tipo_referencia,
                                  **verificar_cp(path, payload, j, esperado, fonte_cache)})
                print(f"  {path.parent.parent.name}/{ident}: bit a bit", flush=True)
                del payload
                gc.collect()
            salvar()
            del ctx, j, esperado
            gc.collect()
    salvar(True)
    print({"ok": True, "checkpoints": len(registros), "saida": str(args.saida)}, flush=True)


if __name__ == "__main__":
    main()
