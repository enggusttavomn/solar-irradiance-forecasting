"""Certifica o controle ARIMA horario reexecutado sem novos ajustes."""
from pathlib import Path

import joblib
import numpy as np

from codigo_fonte.experimentos import experimento_quantizacao_estatisticos as run

RAIZ = run.RAIZ
ORIGEM_LOGICA = run.SAIDA / "atual/hourly_72_extension/arima"
ARQUIVO = RAIZ / "tmp/quantizacao_todos_modelos_20260929/antes_novo_controle_arima_horario_v1/arima"
REL = RAIZ / "resultados/relatorios/quantizacao_todos_modelos_20260929/diagnostico_arima_horario"


def traduzir(path):
    path = Path(path)
    try:
        return ARQUIVO / path.relative_to(ORIGEM_LOGICA)
    except ValueError:
        return path


def main():
    diagnostico = run.motor.ler_json(REL / "diagnostico.json")
    repeticoes = run.motor.ler_json(REL / "repeticoes.json")
    assert repeticoes["ok"] and len(repeticoes["registros"]) == 2
    assert repeticoes["replay_checkpoint"]["bit_a_bit"]
    for registro in repeticoes["registros"]:
        assert registro["vs_params_checkpoint"]["bit_a_bit"]
        assert registro["vs_previsoes_checkpoint"]["bit_a_bit"]
    for key in ("x_bruto", "y_bruto", "x_normalizado", "escalas", "ids"):
        assert diagnostico["dados"][key]["bit_a_bit"]
    assert diagnostico["dados"]["origens_locais_iguais"]
    assert diagnostico["comparacao_global"]["delta_maximo"] == 4.490431751946744e-05
    fontes = {}
    for doc in (diagnostico, repeticoes):
        for path, digest in doc["fontes"].items():
            real = traduzir(path)
            if run.m.sha256_arquivo(real) != digest:
                raise ValueError(f"Fonte diagnostica alterada: {real}")
            fontes[str(real)] = digest
    contrato = run.motor.ler_json(ARQUIVO / "contrato_execucao.json")
    run.motor.conferir_hashes(contrato["codigo"])
    run.motor.conferir_hashes(contrato["entradas"])
    meta = run.motor.ler_json(ARQUIVO / "sem_quantizacao/selecao/seed-1.json")
    for path, digest in meta["arquivos_sha256"].items():
        real = traduzir(path)
        if run.m.sha256_arquivo(real) != digest:
            raise ValueError(f"Cache arquivado alterado: {real}")
        fontes[str(real)] = digest
    fontes.update(run.motor.hashes([REL / "diagnostico.json", REL / "repeticoes.json",
                                   ARQUIVO / "contrato_execucao.json", Path(__file__)]))
    ctx = run.motor.preparar_contexto("hourly_72_extension", "selecao")
    j = ctx.janelas["validacao"]
    with np.load(ARQUIVO / "sem_quantizacao/selecao/seed-1.npz", allow_pickle=False) as z:
        esperado = z["previsao"].copy()
    registros = []
    for serie in ctx.series:
        ident = int(serie.localidade_id)
        cp = joblib.load(ARQUIVO / "sem_quantizacao/modelos" / f"localidade{ident}_selecao.joblib")
        historico = run.e.serie_ajuste_arima(ctx, serie, "selecao")
        assert np.array_equal(historico, cp["serie_ajuste_quantizada"])
        assert cp["niveis"] is None and cp["fase"] == "selecao"
        bruto = run.q.prever_checkpoint_arima(cp, j)
        alvo = esperado[j.localidade_id == ident]
        delta = float(np.max(np.abs(bruto-alvo)))
        if not np.isfinite(delta) or delta > 1e-6:
            raise ValueError(f"Replay do novo controle falhou: {serie.localidade}/{delta}")
        registros.append({"localidade_id": ident, "localidade": serie.localidade,
                          "bit_a_bit": bruto.dtype == alvo.dtype and bruto.tobytes() == alvo.tobytes(),
                          "delta_maximo": delta, "previsoes": int(bruto.size)})
        print(f"{serie.localidade}: replay delta={delta}", flush=True)
    assert len(registros) == 10
    arquivos = [p for p in (ARQUIVO / "sem_quantizacao").rglob("*") if p.is_file()]
    fontes.update(run.motor.hashes(arquivos))
    resultado = {"schema": 1, "id": "arima_horario_novo_controle_v1", "ok": True,
                 "escopo": {"regime": "atual", "tarefa": "hourly_72_extension", "modelo": "ARIMA",
                            "fase": "selecao", "particao": "validacao", "variante": "sem_quantizacao"},
                 "controle_historico_reproduzido": False,
                 "criterio": "novo_controle_mesmo_algoritmo_repetido_duas_vezes_e_replay_de_10_checkpoints",
                 "tolerancia_replay": 1e-6,
                 "comparacao_historica": diagnostico["comparacao_global"],
                 "mae_macro_historico": diagnostico["mae_macro_original"],
                 "mae_macro_novo": diagnostico["mae_macro_novo"],
                 "origem_logica_anterior": str(ORIGEM_LOGICA), "origem_arquivada": str(ARQUIVO),
                 "hash_contrato_anterior": contrato["sha256_contrato"],
                 "replays": registros, "fontes_sha256": fontes,
                 "concluido_em_utc": run.motor.agora()}
    run.m.salvar_json_atomico(resultado, REL / "controle_reexecutado_auditado_v1.json")
    print({"ok": True, "replays": len(registros)}, flush=True)


if __name__ == "__main__":
    main()
