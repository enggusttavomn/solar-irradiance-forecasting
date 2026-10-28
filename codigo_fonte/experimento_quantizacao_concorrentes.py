"""Experimentos isolados min-max + quantizacao de entradas dos concorrentes.

Selecao e refit sao comandos separados. O contrato de cada modelo preserva
semente, hardware, treino e criterio de epocas do benchmark; todos os niveis
sao avaliados depois de congelar a selecao. Nenhum arquivo antigo e escrito.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
import numpy as np
import pandas as pd
import torch

from codigo_fonte import experimento_multirresolucao as m
from codigo_fonte import experimento_baselines_adicionais as e
from codigo_fonte import experimento_horario_timesnet as h
from codigo_fonte import quantizacao_timesnet as q

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "resultados/quantizacao_todos_modelos_20260929"
FONTE = RAIZ / "resultados/avaliacao_baselines_revisao_20260912/consolidado"
MODELOS = ("XGBoost", "LSTM", "DilatedRNN", "GRU", "Transformer", "Informer", "TimesNet")
VARIANTES = (("sem_quantizacao", None), ("q64", 64), ("q128", 128), ("q256", 256))
REGIMES = ("atual", "historico_1998_2022", "historico_curto_pareado")
METRICAS = ("MAE_wm2", "MSE_w2m4", "RMSE_wm2", "nRMSE", "R2")


def ler_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def agora():
    return datetime.now(timezone.utc).isoformat()


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode()).hexdigest()


def hashes(paths):
    return {str(Path(p).resolve()): m.sha256_arquivo(p) for p in paths}


def conferir_hashes(registro):
    for path, digest in registro.items():
        if m.sha256_arquivo(path) != digest:
            raise ValueError(f"Arquivo alterado: {path}")


def protocolo_padrao(regime="atual"):
    if regime not in REGIMES:
        raise ValueError("Regime desconhecido.")
    if regime == "atual":
        return {"regime": regime, "inicio_dados": "2019-01-01", "fim_dados": "2024-12-31",
                "inicio_validacao": "2023-01-01", "inicio_teste": "2024-01-01",
                "pasta_diaria": str(RAIZ / "dados/brutos/localidades_ev"),
                "pasta_horaria": str(RAIZ / "dados/brutos/localidades_ev_horario")}
    raiz = RAIZ / "dados/brutos/localidades_ev_1998_2022"
    return {"regime": regime,
            "inicio_dados": "1998-01-01" if regime == "historico_1998_2022" else "2014-04-01",
            "fim_dados": "2022-12-31", "inicio_validacao": "2018-04-01",
            "inicio_teste": "2019-04-01", "pasta_diaria": str(raiz),
            "pasta_horaria": None, "carregador_historico": True}


def construir_tarefa(slug, protocolo):
    """Particoes civis; todo o alvo direto deve caber na respectiva fase."""
    t = e.TAREFAS[slug]
    p = protocolo
    inicio, val, teste = [pd.Timestamp(p[k]) for k in
                          ("inicio_dados", "inicio_validacao", "inicio_teste")]
    fim = pd.Timestamp(p["fim_dados"]).normalize() + pd.Timedelta(days=1)
    if not inicio < val < teste < fim:
        raise ValueError("Cortes temporais invalidos.")
    if t.resolucao == "mensal" and any(d.day != 1 for d in (inicio, val, teste, fim)):
        raise ValueError("Cortes mensais devem ocorrer no primeiro dia do mes.")
    if p["regime"] == "atual" and all(p[k] == protocolo_padrao()[k] for k in
            ("inicio_dados", "fim_dados", "inicio_validacao", "inicio_teste")):
        return t
    def intervalo(comeco, final):
        if t.resolucao == "mensal":
            primeiro = max(comeco, inicio + pd.DateOffset(months=t.seq_len)) + pd.offsets.MonthEnd(0)
            ultimo_alvo = final - pd.Timedelta(days=1)
            ultimo = ultimo_alvo - pd.offsets.MonthEnd(t.pred_len - 1)
            total = len(pd.date_range(primeiro, ultimo, freq="ME"))
        elif t.resolucao == "diaria":
            primeiro = max(comeco, inicio + pd.Timedelta(days=t.seq_len))
            ultimo_alvo = final - pd.Timedelta(days=1)
            ultimo = final - pd.Timedelta(days=t.pred_len)
            total = len(pd.date_range(primeiro, ultimo, freq="D"))
        else:
            primeiro = max(comeco, inicio + pd.Timedelta(hours=t.seq_len)).ceil("D")
            ultimo_alvo = final - pd.Timedelta(hours=1)
            ultimo = (final - pd.Timedelta(hours=t.pred_len)).floor("D")
            total = len(pd.date_range(primeiro, ultimo, freq="D"))
        if total < 1:
            raise ValueError("Historico insuficiente para contexto e horizonte.")
        return m.IntervaloParticao(str(primeiro), str(ultimo), str(ultimo_alvo), total)
    return replace(t, ajuste=intervalo(inicio, val), validacao=intervalo(val, teste),
                   refit=intervalo(inicio, teste), teste=intervalo(teste, fim))


def _filtrar_horarias(j, intervalo, limite):
    a, b, c = intervalo.datas()
    # O contrato canonico registra fim_alvo como data civil, incluindo 23h.
    final = c.normalize() + pd.Timedelta(days=1) if c.hour == 0 else c + pd.Timedelta(hours=1)
    keep = ((j.origem_local >= a) & (j.origem_local <= b)
            & (j.origem_local + pd.Timedelta(hours=j.pred_len) <= final))
    pos = np.flatnonzero(keep)
    if limite is not None:
        pos = np.concatenate([m._limitar_posicoes(pos[j.localidade_id[pos] == i], limite)
                              for i in np.unique(j.localidade_id)])
        pos.sort()
    return replace(j, x_bruto=j.x_bruto[pos], y_bruto=j.y_bruto[pos],
                   localidade_id=j.localidade_id[pos], localidade=j.localidade[pos],
                   origem_utc=j.origem_utc[pos], origem_local=j.origem_local[pos])


def preparar_contexto(slug, fase, modo="completa", protocolo=None, modelo=None):
    if fase not in ("selecao", "refit") or modo not in ("smoke", "completa"):
        raise ValueError("Fase/modo invalido.")
    p = dict(protocolo or protocolo_padrao())
    t = construir_tarefa(slug, p)
    c = m.ConfiguracaoMultirresolucao(modo_execucao=modo)
    limite = c.limite_origens_smoke if modo == "smoke" else None
    inicio = pd.Timestamp(p["inicio_dados"])
    fim = (pd.Timestamp(p["inicio_teste"]) if fase == "selecao" else
           pd.Timestamp(p["fim_dados"]).normalize() + pd.Timedelta(days=1))
    corte = p["inicio_validacao"] if fase == "selecao" else p["inicio_teste"]
    intervalos = {"ajuste": t.ajuste, "validacao": t.validacao} if fase == "selecao" else {
        "refit": t.refit, "teste": t.teste}
    if t.resolucao == "horaria":
        from codigo_fonte.dados_horarios_nsrdb import carregar_dados_horarios
        anos = range(inicio.year, (pd.Timestamp(p["fim_dados"])).year + 1)
        hc = h.ConfiguracaoExperimentoHorario(modo_execucao=modo)
        if p.get("carregador_historico"):
            from codigo_fonte.historico_nsrdb_expandido import carregar_historico_horario
            dados_h = carregar_historico_horario(anos=tuple(anos))
        else:
            dados_h = carregar_dados_horarios(p["pasta_horaria"], anos)
        series = h.preparar_series_localidades(dados_h, hc)
        series = tuple(replace(s, timestamp_local=s.timestamp_local[(s.timestamp_local >= inicio) & (s.timestamp_local < fim)],
            timestamp_utc=s.timestamp_utc[(s.timestamp_local >= inicio) & (s.timestamp_local < fim)],
            ghi=s.ghi[(s.timestamp_local >= inicio) & (s.timestamp_local < fim)]) for s in series)
        janelas = {}
        for part, it in intervalos.items():
            a, _, z = it.datas()
            j = h.construir_janelas_diarias(series, anos_origem=range(a.year, z.year + 1),
                seq_len=t.seq_len, pred_len=t.pred_len, particao=part)
            janelas[part] = _filtrar_horarias(j, it, limite)
        escalas = {fase: h.ajustar_escalas_pre_corte(series, primeiro_ano=inicio.year,
                                                   fim_local_exclusivo=corte, nome_ajuste=fase)}
        part = "validacao" if fase == "selecao" else "teste"
        elevacoes = {part: h.calcular_elevacao_solar(janelas[part], series, minutos_centro_intervalo=30)}
        if p.get("carregador_historico"):
            from codigo_fonte import historico_nsrdb_expandido as he
            entradas = [Path(he.__file__)]
            entradas += [Path(s) for s in p.get("arquivos_historicos", [])]
            if not p.get("arquivos_historicos"):
                raise ValueError("Protocolo historico exige arquivos_historicos para auditar a fonte real.")
        else:
            entradas = [Path(p["pasta_horaria"]) / f"nsrdb_ghi_horaria_{ano}.csv.gz" for ano in anos]
    else:
        diarias, _ = m.carregar_series_diarias(p["pasta_diaria"])
        if modo == "smoke":
            diarias = diarias[:c.limite_localidades_smoke]
        diarias = tuple(replace(s, datas=s.datas[(s.datas >= inicio) & (s.datas < fim)],
                                ghi=s.ghi[(s.datas >= inicio) & (s.datas < fim)]) for s in diarias)
        series = diarias if t.resolucao == "diaria" else m.agregar_series_mensais(diarias)
        janelas = {part: m.construir_janelas(series, seq_len=t.seq_len, pred_len=t.pred_len,
                   intervalo=it, particao=part, limite_origens_por_localidade=limite)
                   for part, it in intervalos.items()}
        escalas = {fase: m.ajustar_escalas_pre_corte(series, fim_exclusivo=corte, nome_ajuste=fase)}
        elevacoes = {}
        entradas = sorted({s.caminho_fonte for s in series}, key=str)
    ctx = e.Contexto(t, c, series, janelas, escalas, elevacoes, entradas)
    ctx.protocolo = p
    ctx.fase = fase
    return ctx


def parametros(ctx, modelo):
    if modelo not in MODELOS:
        raise ValueError("Modelo nao suportado.")
    t, c = ctx.tarefa, ctx.config
    mensal = t.resolucao == "mensal"
    fontes = [RAIZ / "resultados/avaliacao_multirresolucao_corrigida_v2" / t.slug / "contrato_execucao.json"]
    d = "cpu"
    perda = "mse"
    if modelo in ("GRU", "Transformer", "Informer"):
        fonte = RAIZ / "resultados/avaliacao_baselines_revisao_20260912" / t.slug / modelo.lower() / "contrato.json"
        antigo = ler_json(fonte)
        fontes.append(fonte)
        d = antigo.get("execucao", {}).get("dispositivo", "cpu")
    if modelo == "TimesNet":
        origem = RAIZ / ("resultados/busca_timesnet_mensal_20260920" if mensal else
                         "resultados/busca_timesnet_resolucoes_20260922") / t.slug
        fontes += [origem / "contrato_execucao.json", origem / "selecao_congelada.json"]
        vencedor = ler_json(fontes[-1])["vencedor"]
        perda = vencedor["perda"]
        if mensal:
            c = replace(c, taxa_aprendizado=vencedor["taxa_aprendizado"],
                        timesnet_d_model=vencedor["d_model"], timesnet_d_ff=vencedor["d_ff"],
                        timesnet_blocos=vencedor["blocos"], timesnet_dropout=vencedor["dropout"])
        else:
            c = replace(c, taxa_aprendizado=vencedor["taxa"], timesnet_d_model=vencedor["dimensao"],
                        timesnet_d_ff=2*vencedor["dimensao"], batch_size_diario=vencedor["lote"])
            d = ler_json(fontes[-2])["dispositivo"]
    seeds = [42] if t.resolucao == "horaria" else list(c.sementes_efetivas)
    original_device = d
    d = ctx.protocolo.get("dispositivos", {}).get(modelo, d)
    if d not in ("cpu", "cuda") or (modelo == "XGBoost" and d != "cpu"):
        raise ValueError("Dispositivo invalido.")
    return {"modelo": modelo, "dispositivo": d, "dispositivo_original": original_device,
            "novo_controle_por_dispositivo": d != original_device, "sementes": seeds, "perda": perda,
            "batch_size": c.batch_size_mensal if mensal else c.batch_size_diario,
            "max_epocas": c.epocas_smoke if c.modo_execucao == "smoke" else (
                c.max_epocas_mensal if mensal else c.max_epocas_diario),
            "paciencia": c.paciencia_mensal if mensal else c.paciencia_diario,
            "configuracao": asdict(c), "fontes_configuracao": hashes(fontes),
            "criterio_epocas": "macro_MAE_fisico" if modelo == "TimesNet" else "MSE_normalizado",
            "criterio_niveis": "macro_MAE_fisico_ensemble_horizonte_completo"}


def construir_contrato(ctx, modelo):
    par = parametros(ctx, modelo)
    codigos = [Path(__file__), Path(m.__file__), Path(e.__file__), Path(h.__file__), Path(q.__file__),
               Path(e.redes.__file__), RAIZ / "codigo_fonte/dilated_rnn_direta.py",
               RAIZ / "codigo_fonte/timesnet_horario.py",
               RAIZ / "codigo_fonte/treinamento_timesnet_otimizacao.py",
               RAIZ / "codigo_fonte/treinamento_timesnet_quantizado_resolucoes.py",
               RAIZ / "codigo_fonte/treinamento_timesnet_resolucoes.py"]
    result = {"schema": 1, "modelo": modelo, "tarefa": asdict(ctx.tarefa),
              "modo": ctx.config.modo_execucao, "protocolo": ctx.protocolo, "parametros": par,
              "variantes": [{"nome": n, "niveis": k} for n,k in VARIANTES],
              "quantizacao": "X_only_minmax_then_rint(clip(x,0,1)*(N-1))/(N-1)",
              "controle": "minmax_sem_clip_sem_quantizacao", "targets_quantizados": False,
              "controle_gpu": "mudanca_device_ou_divergencia_exige_aceite_com_replay_original_e_paridade_loop_auditados",
              "codigo": hashes(codigos), "entradas": hashes(ctx.entradas),
              "pacotes": {x: importlib.metadata.version(x) for x in ("numpy", "pandas", "torch", "xgboost")},
              "cuda": torch.version.cuda if par["dispositivo"] == "cuda" else None,
              "limitacoes": ["Avaliacao retrospectiva", "Clipping nao isolado por controle separado",
                             "Epocas e niveis usam a mesma validacao"]}
    result["sha256_contrato"] = hash_obj(result)
    return json.loads(json.dumps(result))


def nova_rede(ctx, modelo, seed, par):
    c = m.ConfiguracaoMultirresolucao(**par["configuracao"])
    m.fixar_semente(seed, c.threads_torch)
    if modelo in ("GRU", "Transformer", "Informer"):
        rede = e.redes.criar_baseline(modelo, ctx.tarefa.seq_len, ctx.tarefa.pred_len, len(ctx.series))
    else:
        rede = m.criar_modelo_neural(modelo, tarefa=ctx.tarefa, configuracao=c,
                                    num_localidades=len(ctx.series), semente=seed)
    if par["dispositivo"] == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA obrigatoria para reproduzir o hardware do benchmark.")
        # Mesmos hooks do executor original GPU; perda e DataLoader continuam CPU.
        rede.to("cuda")
        rede.register_forward_pre_hook(lambda _, xs: tuple(x.to("cuda") for x in xs))
        rede.register_forward_hook(lambda _, __, y: y.cpu())
    return rede


def treinar_seed(ctx, modelo, niveis, seed, fase, par, epocas_fixas=None):
    treino = ctx.janelas["ajuste" if fase == "selecao" else "refit"]
    avaliacao = ctx.janelas["validacao" if fase == "selecao" else "teste"]
    escalas = ctx.escalas[fase]
    c = m.ConfiguracaoMultirresolucao(**par["configuracao"])
    if modelo == "TimesNet":
        if ctx.tarefa.resolucao == "mensal":
            from codigo_fonte.treinamento_timesnet_otimizacao import treinar_candidato
            rede, epocas, hist = treinar_candidato(tarefa=ctx.tarefa, configuracao=c, semente=seed,
                ajuste=q.aplicar_quantizacao(treino, niveis), escalas=escalas,
                validacao=q.aplicar_quantizacao(avaliacao, niveis) if fase == "selecao" else None,
                perda=par["perda"], epocas_fixas=epocas_fixas)
        else:
            from codigo_fonte import treinamento_timesnet_quantizado_resolucoes as tq
            rede, epocas, hist = tq.treinar(tarefa=ctx.tarefa, config=c, semente=seed,
                ajuste=treino, escalas=escalas, validacao=avaliacao if fase == "selecao" else None,
                elevacao_validacao=ctx.elevacoes.get("validacao"), perda=par["perda"],
                epocas_fixas=epocas_fixas, dispositivo=par["dispositivo"], niveis=niveis)
            pred = tq.prever(rede, avaliacao, escalas, par["batch_size"], par["dispositivo"], niveis)
            return rede, pred, epocas, hist
        pred = avaliacao.inverter(m.prever_rede(rede, q.normalizar_entradas(avaliacao, escalas, niveis),
            avaliacao.localidade_id, batch_size=par["batch_size"]), escalas)
        return rede, pred, epocas, pd.DataFrame(hist)
    x, y = treino.normalizar(escalas)
    x = q.quantizar_entradas(x, niveis)
    xv = q.normalizar_entradas(avaliacao, escalas, niveis)
    if modelo == "XGBoost":
        rede = m.criar_xgboost(c, semente=seed, pred_len=ctx.tarefa.pred_len)
        rede.fit(m.matriz_xgboost(x, treino.localidade_id, len(ctx.series)),
                 y[:, 0] if ctx.tarefa.pred_len == 1 else y)
        previsao = np.asarray(rede.predict(m.matriz_xgboost(xv, avaliacao.localidade_id,
                    len(ctx.series))), dtype=float).reshape(avaliacao.y_bruto.shape)
        return rede, avaliacao.inverter(previsao, escalas), 0, pd.DataFrame()
    rede = nova_rede(ctx, modelo, seed, par)
    kwargs = {"x_treino": x, "y_treino": y, "ids_treino": treino.localidade_id,
              "epocas_fixas": epocas_fixas}
    if fase == "selecao":
        _, yv = avaliacao.normalizar(escalas)
        kwargs.update(x_validacao=xv, y_validacao=yv, ids_validacao=avaliacao.localidade_id)
    if modelo == "LSTM" and ctx.tarefa.resolucao == "horaria":
        hc = h.ConfiguracaoExperimentoHorario(modo_execucao=c.modo_execucao, semente=seed)
        rede, epocas, hist = h.treinar_rede_direta(rede, configuracao=hc, **kwargs)
        previsao = h.prever_rede_direta(rede, xv, avaliacao.localidade_id, batch_size=par["batch_size"])
    else:
        rede, epocas, hist = m.treinar_rede(rede, batch_size=par["batch_size"],
            taxa_aprendizado=c.taxa_aprendizado, peso_decay=c.peso_decay, semente=seed,
            threads_torch=c.threads_torch, max_epocas=par["max_epocas"], paciencia=par["paciencia"], **kwargs)
        previsao = m.prever_rede(rede, xv, avaliacao.localidade_id, batch_size=par["batch_size"])
    return rede, avaliacao.inverter(previsao, escalas), epocas, pd.DataFrame(hist)


def metricas(ctx, particao, bruto, modelo, variante):
    j = ctx.janelas[particao]
    pos = e.pos_processar(ctx, particao, bruto)
    rows = []
    for horizonte in ctx.tarefa.horizontes:
        for nome in np.unique(j.localidade):
            mascara = j.localidade == nome
            real = j.y_bruto[mascara, :horizonte].astype(float)
            prev = pos[mascara, :horizonte]
            z = m._metricas_vetor(real, prev)
            z["MSE_w2m4"] = float(np.mean((real - prev)**2))
            rows.append({"tarefa": ctx.tarefa.slug, "modelo": modelo, "variante": variante,
                         "particao": particao, "horizonte": horizonte, "localidade": nome, **z})
    local = pd.DataFrame(rows)
    keys = ["tarefa", "modelo", "variante", "particao", "horizonte"]
    macro = local.groupby(keys, as_index=False)[list(METRICAS)].mean()
    return local, macro


def salvar_avaliacao(ctx, particao, brutas, seeds, modelo, variante, pasta):
    media = np.mean(brutas, axis=0)
    tab = e.tabela_chaves(ctx, particao)
    tab[f"{modelo}_bruta_wm2"] = media.reshape(-1)
    tab[f"{modelo}_wm2"] = e.pos_processar(ctx, particao, media).reshape(-1)
    if ctx.tarefa.resolucao == "horaria":
        tab["elevacao_solar_graus"] = ctx.elevacoes[particao].reshape(-1)
    for s, bruto in zip(seeds, brutas, strict=True):
        tab[f"{modelo}_seed{s}_bruta_wm2"] = bruto.reshape(-1)
    local, macro = metricas(ctx, particao, media, modelo, variante)
    m.salvar_csv_atomico(tab, pasta / f"previsoes_{particao}.csv.gz")
    m.salvar_csv_atomico(local, pasta / f"metricas_por_localidade_{particao}.csv")
    m.salvar_csv_atomico(macro, pasta / f"metricas_{particao}.csv")
    return float(macro.loc[macro.horizonte == ctx.tarefa.pred_len, "MAE_wm2"].iloc[0])


def validar_aceite_gpu(caminho, contrato_hash, fonte_hash, relatorio_hash):
    """Excecao documentada; nunca converte falha de reproducao em aceite sozinho."""
    if not Path(caminho).is_file():
        raise ValueError(f"Controle GPU exige auditoria independente registrada em {caminho}")
    a = ler_json(caminho)
    esperado = {"contrato_sha256": contrato_hash, "fonte_sha256": fonte_hash,
                "relatorio_divergencia_sha256": relatorio_hash,
                "replay_checkpoint_original_aprovado": True,
                "arquitetura_e_loop_aprovados": True}
    if any(a.get(k) != v for k,v in esperado.items()):
        raise ValueError("Aceite GPU nao corresponde ao contrato/fonte/relatorio auditados.")
    if not isinstance(a.get("justificativa"), str) or not a["justificativa"].strip():
        raise ValueError("Aceite GPU exige justificativa explicita.")
    evidencias = a.get("auditoria_arquivos_sha256", {})
    if not evidencias:
        raise ValueError("Aceite GPU exige arquivos de evidencia independente.")
    conferir_hashes(evidencias)
    return a


def conferir_controle(ctx, modelo, particao, brutas, seeds, destino):
    if ctx.protocolo["regime"] != "atual" or ctx.config.modo_execucao == "smoke" or modelo == "TimesNet":
        return {"aplicavel": False, "motivo": "historico/smoke/TimesNet importada auditada"}
    fonte = FONTE / ctx.tarefa.slug / f"previsoes_{particao}.csv.gz"
    antigo = pd.read_csv(fonte, float_precision="round_trip")
    tab = e.tabela_chaves(ctx, particao)
    dates = ["origem_utc", "timestamp_alvo_utc"] if ctx.tarefa.resolucao == "horaria" else ["origem", "data_alvo"]
    keys = ["localidade", *dates, "passo_h" if ctx.tarefa.resolucao == "horaria" else "passo"]
    for col in dates:
        tab[col] = pd.to_datetime(tab[col], utc=True)
        antigo[col] = pd.to_datetime(antigo[col], utc=True)
    if len(tab) != len(antigo) or tab.duplicated(keys).any() or antigo.duplicated(keys).any():
        raise ValueError("Controle com grade diferente.")
    merged = tab.merge(antigo, on=keys, how="left", validate="one_to_one", suffixes=("", "_original"), sort=False)
    # A consolidacao antiga regravou doubles com diferencas de 1 ULP. Os alvos
    # cientificos sao float32; verificamos tambem seus doubles exatos na fonte
    # primaria, anterior a essa regravacao, sem afrouxar o contrato de dados.
    fonte_alvos = e.FONTE / ctx.tarefa.slug / f"previsoes_{particao}.csv.gz"
    alvos = pd.read_csv(fonte_alvos, usecols=keys + ["ghi_real_wm2"], float_precision="round_trip")
    for col in dates:
        alvos[col] = pd.to_datetime(alvos[col], utc=True)
    if len(alvos) != len(tab) or alvos.duplicated(keys).any():
        raise ValueError("Grade primaria de alvos difere do controle.")
    alvo_primario = tab.merge(alvos, on=keys, how="left", validate="one_to_one",
                             suffixes=("", "_primario"), sort=False)
    if (not np.array_equal(alvo_primario.ghi_real_wm2.to_numpy(), alvo_primario.ghi_real_wm2_primario.to_numpy())
            or not np.array_equal(merged.ghi_real_wm2.to_numpy(np.float32), merged.ghi_real_wm2_original.to_numpy(np.float32))):
        raise ValueError("Alvos diferentes do controle primario.")
    diffs = {}
    par = parametros(ctx, modelo)
    for s, bruto in zip(seeds, brutas, strict=True):
        coluna = f"previsao_bruta_{modelo.lower()}_seed{s}_wm2"
        if coluna not in merged and ctx.tarefa.resolucao == "horaria":
            possiveis = [f"{modelo}_bruta_wm2", f"previsao_bruta_{modelo.lower()}_wm2"]
            coluna = next((k for k in possiveis if k in merged), coluna)
        if coluna not in merged:
            raise ValueError(f"Coluna original ausente: {coluna}")
        diff = float(np.max(np.abs(merged[coluna].to_numpy() - bruto.reshape(-1))))
        diffs[str(s)] = diff
    novo = par["novo_controle_por_dispositivo"]
    passou = all(np.isfinite(d) and d <= 1e-6 for d in diffs.values())
    contrato_hash = ler_json(destino / "contrato_execucao.json")["sha256_contrato"]
    registro = {"aplicavel": True, "aprovado": passou and not novo,
                "reproducao_exata_exigida": not novo, "contrato_sha256": contrato_hash,
                "novo_controle_por_dispositivo": novo, "max_diferenca_por_seed": diffs,
                "fonte": str(fonte), "sha256": m.sha256_arquivo(fonte), "tolerancia": 1e-6,
                "fonte_alvos_primarios": str(fonte_alvos), "sha256_alvos_primarios": m.sha256_arquivo(fonte_alvos),
                "alvos_primarios_bitexatos": True,
                "dispositivo": par["dispositivo"], "dispositivo_original": par["dispositivo_original"]}
    if novo or not passou:
        divergencia = destino / f"controle_{particao}_divergencia.json"
        m.salvar_json_atomico(registro, divergencia)
        m.salvar_json_atomico(registro, destino / f"controle_{particao}.json")
        if par["dispositivo"] != "cuda" or not all(np.isfinite(d) for d in diffs.values()):
            raise ValueError(f"Controle {modelo} nao reproduzido; diferencas salvas em {divergencia}")
        aceite = destino / f"aceite_controle_gpu_{particao}.json"
        validar_aceite_gpu(aceite, contrato_hash, registro["sha256"], m.sha256_arquivo(divergencia))
        registro.update(aprovado=True, reproducao_exata_exigida=False,
                        novo_controle_gpu_auditado=True, aceite_sha256=m.sha256_arquivo(aceite))
    m.salvar_json_atomico(registro, destino / f"controle_{particao}.json")
    return registro


def validar_selecao(pasta):
    pasta = Path(pasta)
    c = ler_json(pasta / "contrato_execucao.json")
    if hash_obj({k:v for k,v in c.items() if k != "sha256_contrato"}) != c["sha256_contrato"]:
        raise ValueError("Hash de contrato invalido.")
    for grupo in (c["codigo"], c["entradas"], c["parametros"]["fontes_configuracao"]):
        conferir_hashes(grupo)
    s = ler_json(pasta / "selecao_congelada.json")
    if s["contrato_sha256"] != c["sha256_contrato"] or not s["selecao_concluida_antes_refit"]:
        raise ValueError("Selecao/contrato incompatíveis.")
    ranking = s["ranking"]
    if len(ranking) != 4 or {r["nome"] for r in ranking} != dict(VARIANTES).keys():
        raise ValueError("Quatro variantes unicas obrigatorias.")
    for r in ranking:
        if (r["niveis"] != dict(VARIANTES)[r["nome"]] or not np.isfinite(r["MAE_validacao_wm2"])
                or r["MAE_validacao_wm2"] < 0):
            raise ValueError("Nivel/MAE invalido.")
        if set(r["epocas"]) != {str(x) for x in c["parametros"]["sementes"]}:
            raise ValueError("Sementes incompletas.")
        minimo = 0 if c["modelo"] == "XGBoost" else 1
        if any(isinstance(x, bool) or not isinstance(x, int) or not minimo <= x <= c["parametros"]["max_epocas"]
               for x in r["epocas"].values()):
            raise ValueError("Epocas invalidas.")
    ordem = {n:i for i,(n,_) in enumerate(VARIANTES)}
    ordenado = sorted(ranking, key=lambda r:(r["MAE_validacao_wm2"], ordem[r["nome"]]))
    if ranking != ordenado or s["vencedor"] != ranking[0]:
        raise ValueError("Vencedor nao corresponde a validacao.")
    conferir_hashes(s["arquivos_selecao"])
    return c, s


def executar_fase(ctx, modelo, saida, fase):
    if fase != ctx.fase or fase not in ("selecao", "refit"):
        raise ValueError("Contexto de outra fase.")
    pasta = Path(saida).resolve() / ctx.tarefa.slug / modelo.lower()
    if fase == "refit" and not (pasta / "selecao_congelada.json").is_file():
        raise FileNotFoundError("Refit exige selecao congelada previamente.")
    for proibido in (e.FONTE, e.SAIDA, RAIZ / "resultados/avaliacao_horaria_timesnet"):
        if pasta == proibido.resolve() or proibido.resolve() in pasta.parents:
            raise ValueError("Proibido escrever nos resultados historicos.")
    c = construir_contrato(ctx, modelo)
    destino = pasta / "contrato_execucao.json"
    if destino.exists():
        if ler_json(destino) != c:
            raise ValueError("Contrato alterado: use outro diretorio.")
    elif pasta.exists() and any(pasta.iterdir()):
        raise ValueError("Destino nao vazio sem contrato.")
    else:
        m.salvar_json_atomico(c, destino)
    sel = validar_selecao(pasta)[1] if fase == "refit" else None
    if fase == "selecao" and (pasta / "selecao_congelada.json").exists():
        return validar_selecao(pasta)[1]
    par = c["parametros"]
    part = "validacao" if fase == "selecao" else "teste"
    ranking = []
    m.salvar_json_atomico({"etapa": fase, "iniciado_em_utc": agora(), "modo": c["modo"],
        "modelo": modelo, "tarefa": ctx.tarefa.slug, "resultado_publicavel": False}, pasta / "status.json")
    m.salvar_csv_atomico(ctx.escalas[fase], pasta / f"escalas_{fase}.csv")
    for variante, niveis in VARIANTES:
        pv = pasta / variante
        brutas, epocas = [], {}
        diag = {p: q.diagnosticar_quantizacao(q.normalizar_entradas(j, ctx.escalas[fase], None), niveis)
                for p,j in ctx.janelas.items()}
        m.salvar_json_atomico(diag, pv / f"clipping_{fase}.json")
        for seed in par["sementes"]:
            inicio = time.perf_counter()
            cache = pv / fase / f"seed{seed}.npz"
            meta_path = cache.with_suffix(".json")
            meta_esperada = {"contrato_sha256": c["sha256_contrato"], "niveis": niveis,
                             "seed": seed, "fase": fase, "variante": variante}
            fixas = None if fase == "selecao" else next(r for r in sel["ranking"] if r["nome"] == variante)["epocas"][str(seed)]
            if cache.exists() and meta_path.exists():
                meta = ler_json(meta_path)
                if any(meta.get(k) != v for k,v in meta_esperada.items()):
                    raise ValueError("Cache incompatível.")
                conferir_hashes(meta["arquivos_sha256"])
                with np.load(cache, allow_pickle=False) as z:
                    bruto, epoch = z["previsao"], int(z["epocas"].item())
                if fixas is not None and epoch != fixas:
                    raise ValueError("Refit diverge das epocas congeladas.")
                e.pos_processar(ctx, part, bruto)
            else:
                print(f"{ctx.tarefa.slug}/{modelo}/{variante}/{fase} seed={seed} inicio", flush=True)
                rede, bruto, epoch, hist = treinar_seed(ctx, modelo, niveis, seed, fase, par, fixas)
                checkpoint = pv / "modelos" / f"seed{seed}_{fase}.{'joblib' if modelo == 'XGBoost' else 'pt'}"
                prep = {"minmax": True, "niveis": niveis, "escalas": ctx.escalas[fase].to_dict("records"),
                        "quantizacao_somente_X": True, "dispositivo": par["dispositivo"], "batch_size": par["batch_size"]}
                payload = {**meta_esperada, "epocas": epoch, "tarefa": asdict(ctx.tarefa),
                           "parametros": par, "preprocessamento": prep,
                           "selecao_sha256": m.sha256_arquivo(pasta / "selecao_congelada.json") if fase == "refit" else None}
                if modelo == "XGBoost":
                    m.salvar_joblib_atomico({**payload, "estimador": rede}, checkpoint)
                else:
                    m.salvar_torch_atomico({**payload, "state_dict": rede.state_dict()}, checkpoint)
                if hist.empty and len(hist.columns) == 0:
                    hist = pd.DataFrame(columns=["epoca", "modelo_sem_epocas"])
                m.salvar_csv_atomico(hist, cache.with_suffix(".csv"))
                m.salvar_npz_atomico(cache, previsao=bruto, epocas=np.asarray(epoch))
                m.salvar_json_atomico({**meta_esperada, "epocas": epoch, "duracao_s": time.perf_counter()-inicio,
                    "concluido_em_utc": agora(), "arquivos_sha256": hashes([cache, cache.with_suffix(".csv"), checkpoint])}, meta_path)
                del rede
                gc.collect()
                print(f"{ctx.tarefa.slug}/{modelo}/{variante}/{fase} seed={seed} fim epocas={epoch}", flush=True)
            brutas.append(bruto)
            epocas[str(seed)] = epoch
        if niveis is None:
            conferir_controle(ctx, modelo, part, brutas, par["sementes"], pasta)
        mae = salvar_avaliacao(ctx, part, brutas, par["sementes"], modelo, variante, pv)
        ranking.append({"nome": variante, "niveis": niveis, "MAE_validacao_wm2": mae, "epocas": epocas})
    if fase == "selecao":
        ordem = {n:i for i,(n,_) in enumerate(VARIANTES)}
        ranking.sort(key=lambda r:(r["MAE_validacao_wm2"], ordem[r["nome"]]))
        files = [p for p in pasta.rglob("*") if p.is_file() and p.name not in ("status.json", "contrato_execucao.json")]
        sel = {"contrato_sha256": c["sha256_contrato"], "ranking": ranking,
               "vencedor": ranking[0], "selecao_concluida_antes_refit": True,
               "congelado_em_utc": agora(), "arquivos_selecao": hashes(files)}
        m.salvar_json_atomico(sel, pasta / "selecao_congelada.json")
        validar_selecao(pasta)
    m.salvar_json_atomico({"etapa": "selecao_concluida" if fase == "selecao" else "concluida",
                           "concluido_em_utc": agora(), "modo": c["modo"],
                           "modelo": modelo, "tarefa": ctx.tarefa.slug,
                           "resultado_publicavel": fase == "refit" and c["modo"] == "completa"}, pasta / "status.json")
    return sel


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tarefa", choices=list(e.TAREFAS), required=True)
    ap.add_argument("--modelo", choices=MODELOS, required=True)
    ap.add_argument("--regime", choices=REGIMES, default="atual")
    ap.add_argument("--fase", choices=("selecao", "refit", "congelar"), required=True)
    ap.add_argument("--saida", type=Path, default=SAIDA)
    ap.add_argument("--protocolo", type=Path)
    ap.add_argument("--dispositivo", choices=("cpu", "cuda"))
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args()
    saida = args.saida / args.regime
    if args.smoke and args.saida == SAIDA:
        saida = RAIZ / "tmp/quantizacao_todos_modelos_20260929/smoke" / args.regime
    if args.fase == "congelar":
        validar_selecao(saida / args.tarefa / args.modelo.lower())
        return
    if args.fase == "refit":
        validar_selecao(saida / args.tarefa / args.modelo.lower())
    protocolo = ler_json(args.protocolo) if args.protocolo else protocolo_padrao(args.regime)
    if args.dispositivo:
        protocolo.setdefault("dispositivos", {})[args.modelo] = args.dispositivo
    if protocolo["regime"] != args.regime:
        raise ValueError("Regime do arquivo difere do argumento.")
    ctx = preparar_contexto(args.tarefa, args.fase, "smoke" if args.smoke else "completa", protocolo, args.modelo)
    executar_fase(ctx, args.modelo, saida, args.fase)


if __name__ == "__main__":
    main()
