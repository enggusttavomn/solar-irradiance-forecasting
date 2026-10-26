"""Runner auditavel dos quatro niveis para ARIMA e referencias deterministicas.

Compartilha dados, particoes, metricas e formato de tabelas com o runner
neural. Selecao e refit sao fases distintas. A selecao do nivel usa MAE
macro fisico; a ordem ARIMA usa somente MSE de validacao do controle.
Nos niveis quantizados, a ordem fica fixa e os coeficientes sao reajustados.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import importlib.metadata
import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from codigo_fonte import experimento_quantizacao_concorrentes as motor
from codigo_fonte import quantizacao_referencias as q

m, e = q.m, q.e
MODELOS = ("ARIMA", *q.MODELOS_REFERENCIA)
VARIANTES, REGIMES, RAIZ, SAIDA = motor.VARIANTES, motor.REGIMES, motor.RAIZ, motor.SAIDA


def slug_modelo(modelo):
    if modelo not in MODELOS:
        raise ValueError("Modelo estatistico desconhecido.")
    return modelo.lower().replace(" ", "_")


def construir_contrato(ctx, modelo):
    slug_modelo(modelo)
    fonte = e.SAIDA / ctx.tarefa.slug / "arima_robusto"
    arquivos = [fonte / "contrato.json", fonte / "selecao_arima.csv"] if (
        modelo == "ARIMA" and ctx.protocolo["regime"] == "atual") else []
    par = {"modelo": modelo, "dispositivo": "cpu", "sementes": [-1],
           "sem_epocas": True, "max_epocas": 0,
           "configuracao": asdict(ctx.config), "fontes_configuracao": motor.hashes(arquivos),
           "criterio_niveis": "macro_MAE_fisico_horizonte_completo",
           "ordens_arima": [list(o) for o in e.ORDENS_ARIMA],
           "ordens_no_regime_atual": "ordens_historicas_selecionadas_em_2023" if modelo == "ARIMA" else None,
           "ordens_quantizadas": "mesma_ordem_do_controle_coeficientes_reajustados" if modelo == "ARIMA" else None}
    fontes_codigo = [Path(__file__), Path(q.__file__), Path(q.arima.__file__),
                     Path(motor.__file__), Path(e.__file__), Path(m.__file__), Path(q.h.__file__),
                     RAIZ / "codigo_fonte/quantizacao_timesnet.py",
                     RAIZ / "codigo_fonte/arima_checkpoint_compacto.py",
                     RAIZ / "codigo_fonte/climatologia_cache_localidade.py"]
    contrato = {"schema": 1, "modelo": modelo, "tarefa": asdict(ctx.tarefa),
                "modo": ctx.config.modo_execucao, "protocolo": ctx.protocolo, "parametros": par,
                "variantes": [{"nome": v, "niveis": n} for v,n in VARIANTES],
                "quantizacao": q.protocolo_referencias(), "targets_quantizados": False,
                "serie_endogena_arima_quantizada": modelo == "ARIMA",
                "codigo": motor.hashes(fontes_codigo), "entradas": motor.hashes(ctx.entradas),
                "pacotes": {p: importlib.metadata.version(p) for p in ("numpy", "pandas", "statsmodels", "scipy")},
                "cuda": None,
                "limitacoes": ["Avaliacao retrospectiva", "Clipping nao isolado por controle separado",
                               "ARIMA quantiza serie endogena historica; referencias quantizam historico antes da regra"]}
    contrato["sha256_contrato"] = motor.hash_obj(contrato)
    return json.loads(json.dumps(contrato))


def validar_selecao(pasta):
    pasta = Path(pasta)
    contrato = motor.ler_json(pasta / "contrato_execucao.json")
    if contrato["modelo"] not in MODELOS:
        raise ValueError("Contrato nao e de modelo estatistico.")
    if motor.hash_obj({k:v for k,v in contrato.items() if k != "sha256_contrato"}) != contrato["sha256_contrato"]:
        raise ValueError("Hash do contrato invalido.")
    for grupo in (contrato["codigo"], contrato["entradas"], contrato["parametros"]["fontes_configuracao"]):
        motor.conferir_hashes(grupo)
    selecao = motor.ler_json(pasta / "selecao_congelada.json")
    if selecao["contrato_sha256"] != contrato["sha256_contrato"] or not selecao["selecao_concluida_antes_refit"]:
        raise ValueError("Selecao diverge do contrato.")
    ranking = selecao["ranking"]
    if len(ranking) != 4 or {r["nome"] for r in ranking} != set(dict(VARIANTES)):
        raise ValueError("Selecao deve conter quatro variantes unicas.")
    for registro in ranking:
        if registro["niveis"] != dict(VARIANTES)[registro["nome"]] or not np.isfinite(registro["MAE_validacao_wm2"]):
            raise ValueError("Nivel/MAE invalido.")
        if registro["epocas"] != {"-1": 0}:
            raise ValueError("Referencias/ARIMA nao possuem epocas ou sementes neurais.")
    ordem = {nome:i for i,(nome,_) in enumerate(VARIANTES)}
    if ranking != sorted(ranking, key=lambda r:(r["MAE_validacao_wm2"], ordem[r["nome"]])) or selecao["vencedor"] != ranking[0]:
        raise ValueError("Ranking/vencedor nao correspondem a validacao.")
    if contrato["modelo"] == "ARIMA":
        controle = selecao["ordens_arima_controle"]
        if not controle:
            raise ValueError("Ordens ARIMA ausentes.")
        for variante,_ in VARIANTES:
            meta = motor.ler_json(pasta / variante / "selecao" / "detalhes.json")
            if meta["ordens"] != controle:
                raise ValueError("Ordem ARIMA mudou entre os niveis.")
    motor.conferir_hashes(selecao["arquivos_selecao"])
    return contrato, selecao


def conferir_controle(ctx, modelo, particao, bruto, destino):
    if ctx.protocolo["regime"] != "atual" or ctx.config.modo_execucao != "completa":
        return {"aplicavel": False, "motivo": "historico ou smoke"}
    if modelo == "Climatologia" and ctx.tarefa.resolucao == "horaria":
        registro = {"aplicavel": False, "motivo": "Climatologia horaria adicionada nesta etapa"}
        m.salvar_json_atomico(registro, destino / f"controle_{particao}.json")
        return registro
    orig_part = "validacao_2023" if particao == "validacao" else "teste_2024"
    if modelo == "ARIMA":
        pasta = e.SAIDA / ctx.tarefa.slug / "arima_robusto"
        fonte, cache = pasta / f"chaves_{orig_part}.csv.gz", pasta / "cache/deterministica.npz"
        antigo = pd.read_csv(fonte, float_precision="round_trip")
        with np.load(cache, allow_pickle=False) as z:
            antigo["_controle"] = z[f"{orig_part}_bruta"].reshape(-1)
        arquivos = [fonte, cache]
    else:
        fonte = e.FONTE / ctx.tarefa.slug / f"previsoes_{particao}.csv.gz"
        antigo = pd.read_csv(fonte, float_precision="round_trip")
        sufixo = "" if ctx.tarefa.resolucao == "horaria" else "_deterministica"
        antigo["_controle"] = antigo[f"previsao_bruta_{slug_modelo(modelo)}{sufixo}_wm2"]
        arquivos = [fonte]
    novo = e.tabela_chaves(ctx, particao)
    datas = ["origem_utc", "timestamp_alvo_utc"] if ctx.tarefa.resolucao == "horaria" else ["origem", "data_alvo"]
    chaves = ["localidade", *datas, "passo_h" if ctx.tarefa.resolucao == "horaria" else "passo"]
    for coluna in datas:
        novo[coluna], antigo[coluna] = pd.to_datetime(novo[coluna], utc=True), pd.to_datetime(antigo[coluna], utc=True)
    if len(novo) != len(antigo) or novo.duplicated(chaves).any() or antigo.duplicated(chaves).any():
        raise ValueError("Grade do controle diverge.")
    novo["_novo"] = np.asarray(bruto).reshape(-1)
    combinado = novo.merge(antigo[chaves + ["ghi_real_wm2", "_controle"]], how="left", on=chaves,
                            validate="one_to_one", suffixes=("", "_original"), sort=False)
    if not np.array_equal(combinado.ghi_real_wm2.to_numpy(), combinado.ghi_real_wm2_original.to_numpy()):
        raise ValueError("Alvos do controle divergem.")
    diferenca = float(np.max(np.abs(combinado._novo.to_numpy() - combinado._controle.to_numpy())))
    if not np.isfinite(diferenca) or diferenca > 1e-6:
        raise ValueError(f"Controle {modelo} nao reproduzido: {diferenca}")
    registro = {"aplicavel": True, "aprovado": True, "diferenca_maxima": diferenca,
                "fontes": motor.hashes(arquivos), "tolerancia": 1e-6}
    m.salvar_json_atomico(registro, destino / f"controle_{particao}.json")
    return registro


def _diagnosticos(ctx, fase, niveis):
    # Contagem de contextos sobrepostos; a serie endogena ARIMA e contada
    # separadamente nos detalhes do ajuste, sem misturar denominadores.
    return {p: q.diagnosticar_quantizacao(q.normalizar_entradas(j, ctx.escalas[fase], None), niveis)
            for p,j in ctx.janelas.items()}


def executar_fase(ctx, modelo, saida, fase):
    if fase != ctx.fase or fase not in ("selecao", "refit"):
        raise ValueError("Fase incompativel com contexto.")
    pasta = Path(saida).resolve() / ctx.tarefa.slug / slug_modelo(modelo)
    for proibido in (e.FONTE, e.SAIDA, RAIZ / "resultados/avaliacao_horaria_timesnet"):
        if pasta == proibido.resolve() or proibido.resolve() in pasta.parents:
            raise ValueError("Proibido alterar resultados historicos.")
    contrato = construir_contrato(ctx, modelo)
    arquivo = pasta / "contrato_execucao.json"
    if arquivo.exists():
        if motor.ler_json(arquivo) != contrato:
            raise ValueError("Contrato alterado: use outro diretorio.")
    elif pasta.exists() and any(pasta.iterdir()):
        raise ValueError("Destino nao vazio sem contrato.")
    else:
        m.salvar_json_atomico(contrato, arquivo)
    selecao = validar_selecao(pasta)[1] if fase == "refit" else None
    if fase == "selecao" and (pasta / "selecao_congelada.json").exists():
        return validar_selecao(pasta)[1]
    particao = "validacao" if fase == "selecao" else "teste"
    ordens = None
    if modelo == "ARIMA":
        if fase == "refit":
            ordens = selecao["ordens_arima_controle"]
        elif ctx.protocolo["regime"] == "atual":
            ordens = q.ordens_de_csv(e.SAIDA / ctx.tarefa.slug / "arima_robusto/selecao_arima.csv")
    m.salvar_json_atomico({"etapa": fase, "iniciado_em_utc": motor.agora(), "modo": contrato["modo"]}, pasta / "status.json")
    m.salvar_csv_atomico(ctx.escalas[fase], pasta / f"escalas_{fase}.csv")
    ranking = []
    try:
        for variante, niveis in VARIANTES:
            inicio = time.perf_counter()
            pv = pasta / variante
            cache = pv / fase / "seed-1.npz"
            meta_path = cache.with_suffix(".json")
            detalhes_path = cache.with_name("detalhes.json")
            esperado = {"contrato_sha256": contrato["sha256_contrato"], "niveis": niveis,
                        "seed": -1, "fase": fase, "variante": variante}
            if cache.exists() and meta_path.exists():
                meta = motor.ler_json(meta_path)
                if any(meta.get(k) != v for k,v in esperado.items()):
                    raise ValueError("Cache estatistico incompativel.")
                motor.conferir_hashes(meta["arquivos_sha256"])
                with np.load(cache, allow_pickle=False) as z:
                    bruto = z["previsao"]
                    if int(z["epocas"].item()) != 0:
                        raise ValueError("ARIMA/referencia nao possui epocas.")
                detalhes = motor.ler_json(detalhes_path)
                e.pos_processar(ctx, particao, bruto)
            else:
                print(f"{ctx.tarefa.slug}/{modelo}/{variante}/{fase} inicio", flush=True)
                if modelo == "ARIMA":
                    if fase == "selecao":
                        resultado = q.selecionar_arima(ctx, niveis, pv, ordens_fixas=ordens)
                    else:
                        congelado = motor.ler_json(pv / "selecao/detalhes.json")
                        resultado = q.refit_arima(ctx, niveis, pv, congelado)
                    bruto = resultado.pop("previsao_bruta")
                    detalhes = resultado
                else:
                    bruto = q.previsoes_referencias(ctx, particao, niveis, modelos=[modelo])[modelo]
                    detalhes = {"niveis": niveis, "modelo": modelo, "sem_epocas": True,
                                "corte_ajuste_exclusivo": str(q.corte_fase(ctx, fase)),
                                "regra": q.protocolo_referencias()}
                    cp = {**esperado, "modelo": modelo, "tarefa": asdict(ctx.tarefa),
                          "escalas": ctx.escalas[fase].copy(), "corte": str(q.corte_fase(ctx, fase)),
                          "protocolo": ctx.protocolo, "fontes_sha256": contrato["entradas"],
                          "receita_deterministica": True}
                    m.salvar_joblib_atomico(cp, pv / "modelos" / f"referencia_{fase}.joblib")
                m.salvar_json_atomico(detalhes, detalhes_path)
                m.salvar_json_atomico(_diagnosticos(ctx, fase, niveis), pv / f"clipping_{fase}.json")
                m.salvar_npz_atomico(cache, previsao=bruto, epocas=np.asarray(0))
                cps = list((pv / "modelos").glob(f"*_{fase}.joblib"))
                fontes_cache = [cache, detalhes_path, pv / f"clipping_{fase}.json", *cps]
                m.salvar_json_atomico({**esperado, "epocas": 0, "duracao_s": time.perf_counter()-inicio,
                    "concluido_em_utc": motor.agora(), "arquivos_sha256": motor.hashes(fontes_cache)}, meta_path)
                print(f"{ctx.tarefa.slug}/{modelo}/{variante}/{fase} fim", flush=True)
            if modelo == "ARIMA":
                if niveis is None:
                    ordens = detalhes["ordens"]
                elif detalhes["ordens"] != ordens:
                    raise ValueError("Ordens ARIMA diferem do controle.")
            if niveis is None:
                conferir_controle(ctx, modelo, particao, bruto, pasta)
            mae = motor.salvar_avaliacao(ctx, particao, [bruto], [-1], modelo, variante, pv)
            ranking.append({"nome": variante, "niveis": niveis, "MAE_validacao_wm2": mae, "epocas": {"-1": 0}})
        if fase == "selecao":
            ordem = {nome:i for i,(nome,_) in enumerate(VARIANTES)}
            ranking.sort(key=lambda r:(r["MAE_validacao_wm2"], ordem[r["nome"]]))
            arquivos = [p for p in pasta.rglob("*") if p.is_file() and p.name not in ("status.json", "contrato_execucao.json")]
            selecao = {"contrato_sha256": contrato["sha256_contrato"], "ranking": ranking,
                       "vencedor": ranking[0], "selecao_concluida_antes_refit": True,
                       "congelado_em_utc": motor.agora(), "arquivos_selecao": motor.hashes(arquivos),
                       "ordens_arima_controle": ordens if modelo == "ARIMA" else None}
            m.salvar_json_atomico(selecao, pasta / "selecao_congelada.json")
            validar_selecao(pasta)
        m.salvar_json_atomico({"etapa": "selecao_concluida" if fase == "selecao" else "concluida",
                               "concluido_em_utc": motor.agora(), "modo": contrato["modo"]}, pasta / "status.json")
        return selecao
    except Exception as erro:
        m.salvar_json_atomico({"etapa": "falhou", "fase": fase, "modo": contrato["modo"],
                               "erro": f"{type(erro).__name__}: {erro}", "atualizado_em_utc": motor.agora()}, pasta / "status.json")
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=list(e.TAREFAS), required=True)
    ap.add_argument("--modelo", choices=MODELOS, required=True)
    ap.add_argument("--regime", choices=REGIMES, default="atual")
    ap.add_argument("--fase", choices=("selecao", "refit", "congelar"), required=True)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--protocolo", type=Path)
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    saida = args.saida / args.regime
    if args.smoke and args.saida == SAIDA:
        saida = RAIZ / "tmp/quantizacao_todos_modelos_20260929/smoke" / args.regime
    if args.fase == "congelar":
        validar_selecao(saida / args.tarefa / slug_modelo(args.modelo))
        return
    if args.fase == "refit":
        validar_selecao(saida / args.tarefa / slug_modelo(args.modelo))
    protocolo = motor.ler_json(args.protocolo) if args.protocolo else motor.protocolo_padrao(args.regime)
    if protocolo["regime"] != args.regime:
        raise ValueError("Regime do arquivo difere do argumento.")
    ctx = motor.preparar_contexto(args.tarefa, args.fase, "smoke" if args.smoke else "completa", protocolo, args.modelo)
    executar_fase(ctx, args.modelo, saida, args.fase)


if __name__ == "__main__":
    main()
