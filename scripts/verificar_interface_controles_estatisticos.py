"""Compara interface nova e controles reais sem executar ajustes ARIMA.

As referencias sao recomputadas. ARIMA usa cache historico apenas para
validar grade/chaves/leitura da interface; seu replay de checkpoints real
e registrado separadamente em controles_referencias.json.
"""
from pathlib import Path
import numpy as np

from codigo_fonte import experimento_quantizacao_estatisticos as run


def main():
    destino = run.RAIZ / "relatorios/quantizacao_todos_modelos_20260929/interface_controles_estatisticos"
    registros = []
    for tarefa in ("monthly_1", "monthly_6", "daily_30", "hourly_72_extension"):
        for fase, particao, original in (("selecao", "validacao", "validacao_2023"), ("refit", "teste", "teste_2024")):
            print(f"[{tarefa}/{fase}] preparando contexto e referencias", flush=True)
            ctx = run.motor.preparar_contexto(tarefa, fase)
            referencias = run.q.previsoes_referencias(ctx, particao, None)
            for modelo, previsao in referencias.items():
                resultado = run.conferir_controle(ctx, modelo, particao, previsao, destino / tarefa / run.slug_modelo(modelo))
                registros.append({"tarefa": tarefa, "fase": fase, "modelo": modelo, "recomputado": True, **resultado})
            cache = run.e.SAIDA / tarefa / "arima_robusto/cache/deterministica.npz"
            with np.load(cache, allow_pickle=False) as z:
                bruto = z[f"{original}_bruta"]
            resultado = run.conferir_controle(ctx, "ARIMA", particao, bruto, destino / tarefa / "arima")
            registros.append({"tarefa": tarefa, "fase": fase, "modelo": "ARIMA", "recomputado": False,
                              "escopo": "interface_chaves_alvos_e_cache; replay_independente_em_controles_referencias.json", **resultado})
            run.m.salvar_json_atomico({"ok": False, "registros": registros}, destino / "verificacao.json")
    relatorio = {"ok": True, "registros": registros, "total": len(registros),
                 "concluido_em_utc": run.motor.agora(),
                 "codigo": run.motor.hashes([Path(run.__file__), Path(run.q.__file__), Path(run.motor.__file__)])}
    run.m.salvar_json_atomico(relatorio, destino / "verificacao.json")
    print({"ok": True, "total": len(registros), "saida": str(destino / "verificacao.json")}, flush=True)


if __name__ == "__main__":
    main()
