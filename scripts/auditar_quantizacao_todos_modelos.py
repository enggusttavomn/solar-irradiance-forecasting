"""Audita amostras, metricas, selecoes e replay dos novos modelos quantizados."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gc
import json
import os
from pathlib import Path

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import numpy as np
import pandas as pd

from scripts.metricas_quantizacao_todos import (
    CHAVES, METRICAS, MODELOS, TAREFAS, VARIANTES, calcular_metricas,
    comparar_amostras, comparar_metricas, normalizar_chaves, sha256, validar_previsoes,
)

RAIZ = Path(__file__).resolve().parents[1]
ESTATISTICOS = {"ARIMA", "Persistencia", "Sazonal ingenuo", "Climatologia"}


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exigir(valor, mensagem):
    if not valor:
        raise AssertionError(mensagem)


def conferir_hashes(fontes):
    for path, digest in fontes.items():
        exigir(sha256(Path(path)) == digest, f"Fonte alterada: {path}")


def normalizacao_independente(janelas, escalas, niveis):
    por_id = escalas.set_index("localidade_id").loc[janelas.localidade_id]
    minimo = por_id.minimo_treino_wm2.to_numpy(np.float32)[:, None]
    amplitude = por_id.amplitude_escala_wm2.to_numpy(np.float32)[:, None]
    exigir(np.isfinite(minimo).all() and np.isfinite(amplitude).all() and (amplitude > 0).all(),
           "Escalas invalidas.")
    x = (np.asarray(janelas.x_bruto, np.float32) - minimo) / amplitude
    return x.copy() if niveis is None else (np.rint(np.clip(x, 0, 1).astype(float) *
                                                   (niveis - 1)) / (niveis - 1)).astype(np.float32)


def auditar_controle_suplementar(pasta, regime, tarefa, modelo, modo):
    pasta = Path(pasta)
    complemento_path = pasta / 'contrato_complementar_controle_teste_xgboost_v1.json'
    elegivel = (regime == 'atual' and tarefa == 'hourly_72_extension'
                and modelo == 'XGBoost' and modo == 'completa')
    if not elegivel:
        exigir(not complemento_path.exists(), 'Controle complementar fora do escopo fechado.')
        return None
    controle_path = pasta / 'controle_teste.json'
    controle = ler(controle_path)
    if not complemento_path.exists():
        exigir(controle.get('aprovado') is True
               and controle.get('novo_controle_refit_xgboost_reexecutado') is not True,
               'Controle XGBoost reprovado ou suplemento ausente.')
        return None
    from codigo_fonte import experimento_xgboost_horario_controle_auditado_v1 as adaptador
    complemento = adaptador.validar_controle_adaptado(pasta)
    evidencia = ler(adaptador.EVIDENCIA)
    fontes = {**evidencia['fontes_sha256'], **complemento['fontes_sha256'],
              **controle['fontes_sha256'], str(controle_path.resolve()): sha256(controle_path),
              str(complemento_path.resolve()): sha256(complemento_path)}
    conferir_hashes(fontes)
    return {'id': adaptador.ID, 'controle_refit_reexecutado': True,
            'reproducao_treinamento_legado_aprovada': False,
            'causa_divergencia_legada': 'nao determinada',
            'selecao_alterada': False, 'metricas_usadas_como_criterio': False,
            'fontes_sha256': fontes}


def auditar_calendario_suplementar(pasta, regime, tarefa, modelo, modo, contrato):
    pasta = Path(pasta)
    complemento_path = pasta / 'contrato_complementar_sazonal_mensal_v1.json'
    elegivel = (regime in ('historico_1998_2022', 'historico_curto_pareado')
                and tarefa in ('monthly_1', 'monthly_6') and modelo == 'Sazonal ingenuo'
                and modo == 'completa')
    if not elegivel:
        exigir(not complemento_path.exists(), 'Calendario complementar fora do escopo fechado.')
        return None
    from codigo_fonte import experimento_sazonal_mensal_controle_auditado_v1 as calendario
    calendario.validar_metadados(pasta, 'selecao', contrato=contrato)
    provenance = calendario.validar_metadados(pasta, 'refit', contrato=contrato)
    fonte_adapter = Path(calendario.__file__)
    fontes = {**contrato['codigo'], str(fonte_adapter.resolve()): sha256(fonte_adapter)}
    if provenance['tipo'] == 'complemento_legado':
        complemento = ler(complemento_path)
        evidencia, revisao = ler(Path(complemento['evidencia'])), ler(Path(complemento['revisao']))
        fontes.update(complemento['fontes_sha256'])
        fontes.update(evidencia['fontes_sha256'])
        fontes.update(revisao['fontes_sha256'])
        fontes[str(complemento_path.resolve())] = sha256(complemento_path)
    for variante in VARIANTES:
        for fase in ('selecao', 'refit'):
            meta_path = pasta / variante / fase / 'seed-1.json'
            meta = ler(meta_path)
            fontes[str(meta_path.resolve())] = sha256(meta_path)
            fontes.update(meta['arquivos_sha256'])
    conferir_hashes(fontes)
    return {**provenance, 'fontes_sha256': fontes}


def replay_aprendido(ctx, pasta, modelo, variante, fase, contrato):
    politica = contrato.get('execucao_numerica')
    if politica is not None:
        from codigo_fonte import experimento_atencao_deterministica_v1 as estrito
        exigir(politica.get('id') == 'atencao_cuda_deterministica_v1',
               'Politica numerica desconhecida no replay.')
        conferir_hashes(contrato['codigo'])
        with estrito.ativar_adaptador(contrato=contrato):
            esperado = estrito.construir_contrato(ctx, modelo)
            exigir(contrato == esperado, 'Contrato estrito difere do ambiente/piloto auditado.')
            estrito.validar_controle_adaptado(pasta, 'validacao' if fase == 'selecao' else 'teste', contrato)
            return _replay_aprendido(ctx, pasta, modelo, variante, fase, contrato)
    return _replay_aprendido(ctx, pasta, modelo, variante, fase, contrato)


def _replay_aprendido(ctx, pasta, modelo, variante, fase, contrato):
    import joblib
    import torch
    from codigo_fonte import experimento_quantizacao_concorrentes as exp
    from codigo_fonte import experimento_multirresolucao as m
    from codigo_fonte import experimento_horario_timesnet as h
    from codigo_fonte import quantizacao_timesnet as q

    part = "validacao" if fase == "selecao" else "teste"
    j = copy.copy(ctx.janelas[part])
    object.__setattr__(j, "y_bruto", np.full_like(j.y_bruto, np.nan))
    escalas, niveis = ctx.escalas[fase], VARIANTES[variante]
    x = normalizacao_independente(j, escalas, niveis)
    np.testing.assert_array_equal(x, q.normalizar_entradas(j, escalas, niveis))
    par = contrato["parametros"]
    tabela = normalizar_chaves(pd.read_csv(pasta / variante / f"previsoes_{part}.csv.gz"))
    chaves = exp.e.tabela_chaves(ctx, part)
    registros = []
    for seed in par["sementes"]:
        cp_path = pasta / variante / "modelos" / f"seed{seed}_{fase}.{'joblib' if modelo == 'XGBoost' else 'pt'}"
        cp = joblib.load(cp_path) if modelo == "XGBoost" else torch.load(cp_path, map_location="cpu", weights_only=False)
        exigir(cp["seed"] == seed and cp["niveis"] == niveis and cp["fase"] == fase,
               f"Checkpoint de outra configuracao: {cp_path}")
        exigir(cp["contrato_sha256"] == contrato["sha256_contrato"], "Checkpoint de outro contrato")
        pd.testing.assert_frame_equal(pd.DataFrame(cp["preprocessamento"]["escalas"]), escalas,
                                      check_dtype=False, check_like=True)
        if modelo == "XGBoost":
            rede = cp["estimador"]
            pred = np.asarray(rede.predict(m.matriz_xgboost(x, j.localidade_id, len(ctx.series))), float)
            pred = pred.reshape(j.y_bruto.shape)
            bruto = j.inverter(pred, escalas)
        else:
            rede = exp.nova_rede(ctx, modelo, seed, par)
            rede.load_state_dict(cp["state_dict"], strict=True)
            if modelo == "TimesNet" and ctx.tarefa.resolucao != "mensal":
                from codigo_fonte import treinamento_timesnet_quantizado_resolucoes as tq
                # O treinador TimesNet gerencia diretamente a passagem para CUDA.
                rede._forward_pre_hooks.clear()
                rede._forward_hooks.clear()
                bruto = tq.prever(rede, j, escalas, par["batch_size"], par["dispositivo"], niveis)
            else:
                prever = h.prever_rede_direta if modelo == "LSTM" and ctx.tarefa.resolucao == "horaria" else m.prever_rede
                bruto = j.inverter(prever(rede, x, j.localidade_id, batch_size=par["batch_size"]), escalas)
        atual = chaves.copy()
        atual["replay"] = bruto.reshape(-1)
        atual = normalizar_chaves(atual)
        comparar_amostras(atual, tabela)
        coluna = f"{modelo}_seed{seed}_bruta_wm2"
        delta = float(np.max(np.abs(atual.replay.to_numpy() - tabela[coluna].to_numpy())))
        exigir(np.isfinite(delta) and delta <= 1e-6, f"Replay divergente {cp_path}: {delta}")
        registros.append({"checkpoint": str(cp_path.resolve()), "sha256": sha256(cp_path),
                          "diferenca_maxima": delta, "alvos_substituidos_por_nan": True})
        del rede, cp
        gc.collect()
    return registros


def replay_estatistico(ctx, pasta, modelo, variante, fase):
    import joblib
    from codigo_fonte import experimento_baselines_adicionais as e
    from codigo_fonte import quantizacao_referencias as q
    part = "validacao" if fase == "selecao" else "teste"
    novo = copy.copy(ctx)
    novo.janelas = dict(ctx.janelas)
    j = copy.copy(ctx.janelas[part])
    object.__setattr__(j, "y_bruto", np.full_like(j.y_bruto, np.nan))
    novo.janelas[part] = j
    niveis = VARIANTES[variante]
    registros = []
    complemento_calendario = None
    if modelo == "ARIMA":
        bruto = np.empty(j.y_bruto.shape, float)
        for serie in ctx.series:
            path = pasta / variante / "modelos" / f"localidade{serie.localidade_id}_{fase}.joblib"
            cp = joblib.load(path)
            exigir(cp["niveis"] == niveis and cp["fase"] == fase, "ARIMA nivel/fase divergente")
            mascara = j.localidade_id == serie.localidade_id
            bruto[mascara] = q.prever_checkpoint_arima(cp, j)
            registros.append({"checkpoint": str(path.resolve()), "sha256": sha256(path)})
    else:
        if (modelo == "Sazonal ingenuo" and ctx.tarefa.resolucao == "mensal"
                and ctx.protocolo["regime"] in ("historico_1998_2022", "historico_curto_pareado")):
            from codigo_fonte import experimento_sazonal_mensal_controle_auditado_v1 as calendario
            contrato = ler(pasta / "contrato_execucao.json")
            complemento_calendario = calendario.validar_metadados(pasta, fase, contrato=contrato)
            with calendario.ativar_adaptador(novo, modelo=modelo, pasta=pasta, contrato=contrato):
                bruto = q.previsoes_referencias(novo, part, niveis, fase=fase, modelos=[modelo])[modelo]
        else:
            bruto = q.previsoes_referencias(novo, part, niveis, fase=fase, modelos=[modelo])[modelo]
    tabela = normalizar_chaves(pd.read_csv(pasta / variante / f"previsoes_{part}.csv.gz"))
    atual = e.tabela_chaves(ctx, part)
    atual["replay"] = bruto.reshape(-1)
    atual = normalizar_chaves(atual)
    comparar_amostras(atual, tabela)
    delta = float(np.max(np.abs(atual.replay.to_numpy() - tabela[f"{modelo}_bruta_wm2"].to_numpy())))
    exigir(np.isfinite(delta) and delta <= 1e-6, f"Replay estatistico divergente: {modelo}/{delta}")
    for r in registros:
        r.update(diferenca_maxima=delta, alvos_substituidos_por_nan=True)
    resultado = registros or [{"modelo": modelo, "referencia_recalculada": True,
                               "diferenca_maxima": delta, "alvos_substituidos_por_nan": True}]
    if complemento_calendario is not None:
        for registro in resultado:
            registro["adaptacao_calendario"] = complemento_calendario
    return resultado


def auditar(args):
    from codigo_fonte import experimento_quantizacao_concorrentes as exp
    resultados, metricas, amostras = [], [], {}
    fontes_suplementares = {}
    n_locais = 2 if args.smoke else 10
    raiz = args.saida / args.regime
    completos = set(args.tarefas) == set(TAREFAS) and set(args.modelos) == set(MODELOS)
    if completos and not args.smoke:
        global_path = raiz / "selecao_global_congelada.json"
        global_sel = ler(global_path)
        conferir_hashes(global_sel["fontes_sha256"])
        exigir(global_sel["modo"] == "completa", "Congelamento global smoke")
        exigir({tuple(x) for x in global_sel["pares"]} == {(t, m) for t in TAREFAS for m in MODELOS},
               "Congelamento global incompleto")
    for tarefa in args.tarefas:
        for modelo in args.modelos:
            pasta = raiz / tarefa / modelo.lower().replace(" ", "_")
            print(f"Auditoria {args.regime}/{tarefa}/{modelo}", flush=True)
            status = ler(pasta / "status.json")
            exigir(status["etapa"] == "concluida" and status["modo"] == ("smoke" if args.smoke else "completa"),
                   f"Execucao incompleta: {pasta}")
            importada = status.get("reutilizado") is True
            if importada:
                contrato = ler(pasta / "contrato.json")
                conferir_hashes(contrato["fontes_sha256"])
                conferir_hashes(ler(pasta / "manifesto_artefatos.json")["arquivos"])
                sel = ler(pasta / "selecao_congelada.json")
            elif modelo in ESTATISTICOS:
                from codigo_fonte import experimento_quantizacao_estatisticos as est
                contrato, sel = est.validar_selecao(pasta)
            else:
                contrato, sel = exp.validar_selecao(pasta)
            exigir({r["nome"]: r["niveis"] for r in sel["ranking"]} == VARIANTES,
                   "Ranking com niveis incorretos")
            suplemento = auditar_controle_suplementar(pasta, args.regime, tarefa, modelo,
                                                    'smoke' if args.smoke else 'completa')
            if suplemento is not None:
                fontes_suplementares.update(suplemento['fontes_sha256'])
            suplemento_calendario = auditar_calendario_suplementar(
                pasta, args.regime, tarefa, modelo, 'smoke' if args.smoke else 'completa', contrato)
            if suplemento_calendario is not None:
                fontes_suplementares.update(suplemento_calendario['fontes_sha256'])
            ranking_real = {}
            replays = []
            for fase, part in (("selecao", "validacao"), ("refit", "teste")):
                ctx = None
                if args.replay and not importada:
                    ctx = exp.preparar_contexto(tarefa, fase, "smoke" if args.smoke else "completa",
                                               contrato["protocolo"], None if modelo in ESTATISTICOS else modelo)
                for variante in VARIANTES:
                    path = pasta / variante / f"previsoes_{part}.csv.gz"
                    df = validar_previsoes(pd.read_csv(path), tarefa, modelo, n_locais)
                    chave = (tarefa, part)
                    if chave in amostras:
                        comparar_amostras(amostras[chave], df)
                    else:
                        amostras[chave] = df[CHAVES + ["ghi_real_wm2"]].copy()
                    seedcols = [c for c in df if c.startswith(f"{modelo}_seed") and c.endswith("_bruta_wm2")]
                    if seedcols:
                        exigir(np.allclose(df[seedcols].mean(axis=1), df[f"{modelo}_bruta_wm2"], atol=1e-7, rtol=0),
                               "Media das sementes divergente")
                    calc = calcular_metricas(df, tarefa, modelo)
                    salvas = pd.read_csv(pasta / variante / f"metricas_{part}.csv")
                    comparar_metricas(salvas, calc)
                    calc["regime"], calc["variante"], calc["particao"] = args.regime, variante, part
                    metricas.extend(calc.to_dict(orient="records"))
                    if part == "validacao":
                        ranking_real[variante] = float(calc.loc[calc.horizonte == max(TAREFAS[tarefa]), "MAE_wm2"].iloc[0])
                    if ctx is not None:
                        replay = replay_estatistico(ctx, pasta, modelo, variante, fase) if modelo in ESTATISTICOS else replay_aprendido(ctx, pasta, modelo, variante, fase, contrato)
                        replays.extend(replay)
                del ctx
                gc.collect()
            for r in sel["ranking"]:
                exigir(abs(ranking_real[r["nome"]] - r["MAE_validacao_wm2"]) <= 1e-7, "MAE de selecao divergente")
            ordem = {v: i for i, v in enumerate(VARIANTES)}
            vencedor = min(ranking_real, key=lambda v: (ranking_real[v], ordem[v]))
            exigir(sel["vencedor"]["nome"] == vencedor, "Vencedor nao corresponde a validacao")
            resultados.append({"tarefa": tarefa, "modelo": modelo, "reutilizado_auditado_anteriormente": importada,
                               "vencedor_validacao": vencedor, "replays": replays,
                               "controle_teste_suplementar": suplemento,
                               "calendario_sazonal_suplementar": suplemento_calendario,
                               "selecao_sha256": sha256(pasta / "selecao_congelada.json"), "ok": True})
            args.relatorio.parent.mkdir(parents=True, exist_ok=True)
            args.relatorio.with_name("progresso_auditoria.json").write_text(json.dumps(resultados, indent=2), encoding="utf-8")
    frame = pd.DataFrame(metricas)
    caminho_metricas = args.relatorio.with_name("metricas_auditadas.csv")
    frame.to_csv(caminho_metricas, index=False)
    return {"ok": True, "modo": "smoke" if args.smoke else "completa", "regime": args.regime,
            "escopo_completo": completos, "replay_novo_executado": args.replay,
            "publicavel": completos and not args.smoke and args.replay,
            "concluido_em_utc": datetime.now(timezone.utc).isoformat(), "resultados": resultados,
            "metricas": {"path": str(caminho_metricas.resolve()), "sha256": sha256(caminho_metricas)},
            "pares_verificados": len(resultados), "metricas_macro_linhas": len(frame),
            "fontes_controles_suplementares_sha256": fontes_suplementares,
            "codigo_auditor_sha256": sha256(Path(__file__))}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--saida", type=Path, default=RAIZ / "resultados/quantizacao_todos_modelos_20260929")
    ap.add_argument("--regime", choices=("atual", "historico_1998_2022", "historico_curto_pareado"), default="atual")
    ap.add_argument("--tarefas", nargs="+", choices=list(TAREFAS), default=list(TAREFAS))
    ap.add_argument("--modelos", nargs="+", choices=list(MODELOS), default=list(MODELOS))
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--replay", action="store_true")
    ap.add_argument("--relatorio", type=Path, required=True)
    args = ap.parse_args()
    try:
        resultado = auditar(args)
    except Exception as exc:
        args.relatorio.parent.mkdir(parents=True, exist_ok=True)
        args.relatorio.write_text(json.dumps({"ok": False, "publicavel": False,
                                              "erro": f"{type(exc).__name__}: {exc}"}, indent=2), encoding="utf-8")
        raise
    args.relatorio.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in resultado.items() if k != "resultados"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
