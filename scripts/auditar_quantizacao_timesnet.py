"""Auditoria independente dos artefatos mensais de quantizacao, sem treinamento."""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from codigo_fonte import experimento_multirresolucao as base
from codigo_fonte import experimento_quantizacao_timesnet as exp
from codigo_fonte import otimizacao_timesnet_mensal as mensal
from codigo_fonte import quantizacao_timesnet as quant

CHAVES = ["localidade_id", "localidade", "origem", "data_alvo", "passo"]
METRICAS = ["MAE_wm2", "RMSE_wm2", "nRMSE", "R2"]


def exigir(condicao, mensagem):
    if not condicao:
        raise AssertionError(mensagem)


def perto(a, b, nome, tolerancia=1e-7):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    exigir(a.shape == b.shape, f"Formas divergentes: {nome}")
    exigir(np.allclose(a, b, rtol=1e-9, atol=tolerancia, equal_nan=True),
           f"Valores divergentes: {nome}")
    diferenca = np.abs(a-b)
    return float(np.nanmax(diferenca)) if diferenca.size and np.isfinite(diferenca).any() else 0.


def conferir_hashes(fontes):
    for arquivo, digest in fontes.items():
        exigir(base.sha256_arquivo(arquivo) == digest, f"Arquivo alterado: {arquivo}")
    return len(fontes)


def conferir_snapshot_historico(fontes):
    """Aceita apenas a troca do PDF final comprovada pela entrega e pelo backup."""
    pdf_permitido = (exp.RAIZ/"documentacao/tabela_resultados_ghi_2024.pdf").resolve()
    entrega_path = exp.RAIZ/"relatorios/quantizacao_timesnet_20260923/entrega_pdf.json"
    alteracoes = []
    preservados = 0
    for arquivo, digest in fontes.items():
        caminho = Path(arquivo).resolve()
        atual = base.sha256_arquivo(caminho)
        if atual == digest:
            preservados += 1
            continue
        exigir(caminho == pdf_permitido and entrega_path.is_file(),
               f"Arquivo historico alterado sem entrega autorizada: {arquivo}")
        entrega = exp.ler_json(entrega_path)
        pdf, anterior = entrega.get("pdf", {}), entrega.get("pdf_anterior", {})
        exigir(pdf.get("path") and anterior.get("path"), "Entrega sem caminhos do PDF e backup")
        final = Path(pdf["path"]).resolve()
        backup = Path(anterior["path"]).resolve()
        exigir(final == pdf_permitido and backup != pdf_permitido,
               "Entrega aponta para PDF ou backup incorreto")
        exigir(pdf.get("sha256") == atual, "Hash do PDF atual diverge da entrega autorizada")
        exigir(anterior.get("sha256") == digest and backup.is_file(),
               "Backup nao corresponde ao PDF historico")
        exigir(base.sha256_arquivo(backup) == digest, "Conteudo do backup historico foi alterado")
        alteracoes.append({"arquivo": str(caminho), "sha256_anterior": digest,
            "sha256_atual": atual, "backup": str(backup), "backup_sha256": digest,
            "entrega": str(entrega_path.resolve()), "entrega_sha256": base.sha256_arquivo(entrega_path),
            "motivo": "PDF atualizado apos auditoria; original preservado e entrega verificada"})
    return {"arquivos_verificados": len(fontes), "arquivos_preservados": preservados,
            "alteracoes_autorizadas": alteracoes}


def tabela(caminho):
    frame = pd.read_csv(caminho, parse_dates=["origem", "data_alvo"])
    exigir(not frame.duplicated(CHAVES).any(), f"Chaves duplicadas em {caminho}")
    return frame.sort_values(CHAVES).reset_index(drop=True)


def conferir_identidade(atual, esperado, nome):
    pd.testing.assert_frame_equal(atual[CHAVES], esperado[CHAVES], check_dtype=False,
                                  check_names=True, obj=nome)
    perto(atual.ghi_real_wm2, esperado.ghi_real_wm2, nome+" alvos", tolerancia=0)


def metricas_vetor(real, previsto):
    real, previsto = np.asarray(real, float), np.asarray(previsto, float)
    erro = real-previsto
    rmse = np.sqrt(np.mean(erro**2))
    den = np.sum((real-real.mean())**2)
    return {"MAE_wm2": np.mean(np.abs(erro)), "RMSE_wm2": rmse,
            "nRMSE": np.nan if np.isclose(real.mean(), 0) else rmse/real.mean(),
            "R2": np.nan if len(real) < 2 or np.isclose(den, 0) else 1-np.sum(erro**2)/den}


def recalcular_metricas(frame, tarefa, sementes, particao):
    linhas = []
    estimativas = [("semente", int(s), f"seed{s}") for s in sementes]+[("ensemble", None, "ensemble")]
    for (localidade, dados) in frame.groupby("localidade", sort=True):
        for tipo, semente, identificador in estimativas:
            coluna = f"previsao_pos_timesnet_{identificador}_wm2"
            for horizonte in tarefa.horizontes:
                for tipo_h, mascara in (("cumulativo", dados.passo <= horizonte),
                                        ("lead_exato", dados.passo == horizonte)):
                    d = dados.loc[mascara]
                    linhas.append({"tarefa": tarefa.slug, "resolucao": tarefa.resolucao,
                        "particao": particao, "modelo": "TimesNet", "tipo_estimativa": tipo,
                        "semente": semente, "localidade": localidade, "tipo_horizonte": tipo_h,
                        "horizonte": horizonte, "N_origens": d.origem.nunique(), "N_pontos": len(d),
                        **metricas_vetor(d.ghi_real_wm2, d[coluna])})
    local = pd.DataFrame(linhas)
    chaves = ["tarefa", "resolucao", "particao", "modelo", "tipo_estimativa", "semente",
              "tipo_horizonte", "horizonte"]
    macro = local.groupby(chaves, dropna=False, as_index=False).agg(
        N_localidades=("localidade", "nunique"), N_origens=("N_origens", "sum"),
        N_pontos=("N_pontos", "sum"), **{c: (c, "mean") for c in METRICAS})
    return local, macro


def conferir_metricas(salvas, recalculadas, local=False):
    chaves = ["tarefa", "resolucao", "particao", "modelo", "tipo_estimativa", "semente",
              "tipo_horizonte", "horizonte"]+(["localidade"] if local else [])
    exigir(not salvas.duplicated(chaves).any(), "Metricas salvas duplicadas")
    a, b = [f.sort_values(chaves, na_position="first").reset_index(drop=True) for f in
            (salvas, recalculadas)]
    pd.testing.assert_frame_equal(a[chaves], b[chaves], check_dtype=False)
    contagens = ["N_origens", "N_pontos"]+([] if local else ["N_localidades"])
    perto(a[contagens], b[contagens], "contagens de metricas", 0)
    return perto(a[METRICAS], b[METRICAS], "metricas recalculadas")


def conferir_quantizacao(janelas, escalas, niveis, diagnostico):
    # O calculo independente abaixo confronta o adaptador usado pelo treinador
    # e a preparacao usada ao reproduzir checkpoints; os alvos sao confrontados bit a bit.
    x, y = janelas.normalizar(escalas)
    esperado = x.copy() if niveis is None else (
        np.rint(np.clip(x, 0, 1).astype(np.float64)*(niveis-1))/(niveis-1)).astype(np.float32)
    adaptador = quant.aplicar_quantizacao(janelas, niveis)
    x_treino, y_treino = adaptador.normalizar(escalas)
    np.testing.assert_array_equal(y_treino, y)
    np.testing.assert_array_equal(adaptador.y_bruto, janelas.y_bruto)
    np.testing.assert_array_equal(x_treino, esperado)
    np.testing.assert_array_equal(quant.normalizar_entradas(janelas, escalas, niveis), esperado)
    alteradas = replace(janelas, y_bruto=janelas.y_bruto+10000)
    np.testing.assert_array_equal(quant.normalizar_entradas(alteradas, escalas, niveis), esperado)
    recortes = {"total": np.ones(len(x), bool), **{
        str(int(i)): janelas.localidade_id == i for i in np.unique(janelas.localidade_id)}}
    exigir(set(recortes) == set(diagnostico), "Recortes de diagnostico divergentes")
    for nome, m in recortes.items():
        a, q, d = x[m], esperado[m], diagnostico[nome]
        abaixo, acima = int((a < 0).sum()), int((a > 1).sum())
        alterados = int((a != q).sum())
        saturados = abaixo+acima if niveis is not None else 0
        for chave, valor in {"total": a.size, "abaixo_zero": abaixo, "acima_um": acima,
                            "alterados": alterados, "saturados": saturados}.items():
            exigir(d[chave] == valor, f"Diagnostico {nome}/{chave} divergente")
        exigir(d["niveis"] == niveis, "Nivel do diagnostico divergente")
        perto(d["fracao_alterados"], alterados/a.size, "fracao alterados")
        perto(d["fracao_saturados"], saturados/a.size, "fracao saturados")
        perto(d["erro_medio_quantizacao_normalizado"], np.abs(a.astype(float)-q).mean(), "erro quantizacao")
        perto(d["erro_medio_somente_clip_normalizado"],
              np.abs(a.astype(float)-np.clip(a, 0, 1)).mean() if niveis is not None else 0, "erro clip")
    return {"alvos_brutos_e_normalizados_identicos": True, "treino_inferencia_identicos": True,
            "inferencia_independe_de_y": True, "diagnostico_confere": True}


def auditar_fase(pasta, tarefa, candidato, cfg, series, contrato, linha, niveis, fase,
                 congelado_em, reproduzir=True):
    selecao = fase == "selecao"
    treino_nome, avaliacao_nome = ("ajuste", "validacao") if selecao else ("refit", "teste")
    corte = "2023-01-01" if selecao else "2024-01-01"
    nome_particao = "validacao_2023" if selecao else "teste_2024"
    treino = mensal._janelas(series, tarefa, treino_nome, cfg)
    avaliacao = mensal._janelas(series, tarefa, avaliacao_nome, cfg)
    exigir(treino.datas_alvo.max() < np.datetime64(corte), "Alvos de treino cruzam corte")
    exigir(avaliacao.datas_alvo.min() >= np.datetime64(corte), "Avaliacao anterior ao corte")
    exigir(avaliacao.datas_alvo.max() < np.datetime64("2024-01-01" if selecao else "2025-01-01"),
           "Alvos de avaliacao cruzam ano")
    escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo=corte, nome_ajuste=fase)
    escala_path = pasta.parent.parent/f"escalas_{fase}.csv"
    salvas = pd.read_csv(escala_path)
    campos = ["localidade_id", "N_observacoes", "minimo_treino_wm2", "maximo_treino_wm2",
              "amplitude_real_wm2", "amplitude_escala_wm2"]
    perto(salvas[campos], escalas[campos], "escalas pre corte")
    exigir((pd.to_datetime(salvas.fim_exclusivo) == pd.Timestamp(corte)).all(), "Corte de escala incorreto")
    diag = exp.ler_json(pasta/f"diagnostico_{fase}.json")
    controles = {p: conferir_quantizacao(j, escalas, niveis, diag[p]) for p, j in
                 ((treino_nome, treino), (avaliacao_nome, avaliacao))}
    previsoes_path = pasta/("previsoes_validacao.csv" if selecao else "previsoes_teste.csv")
    frame = tabela(previsoes_path)
    esperado = base.montar_tabela_previsoes(tarefa=tarefa, janelas=avaliacao, estimativas=[])
    esperado = esperado.sort_values(CHAVES).reset_index(drop=True)
    conferir_identidade(frame, esperado, "previsoes versus janelas reconstruidas")
    antigo = tabela(exp.FONTE/tarefa.slug/("previsoes_validacao.csv" if selecao else "previsoes_teste.csv"))
    if cfg.modo_execucao == "smoke":
        antigo = frame[CHAVES].merge(antigo, on=CHAVES, how="left", validate="one_to_one")
        antigo = antigo.sort_values(CHAVES).reset_index(drop=True)
    conferir_identidade(frame, antigo, "benchmark original: datas/origens/localidades/alvos")
    resultados, brutas = [], []
    for semente in cfg.sementes_efetivas:
        cache = pasta/fase/f"seed{semente}.npz"
        registro = exp.ler_json(cache.with_suffix(".json"))
        checkpoint = pasta/"modelos"/f"timesnet_seed{semente}_{fase}.pt"
        exigir(registro["contrato_sha256"] == contrato["sha256_contrato"], "Registro de outro contrato")
        exigir(registro["niveis"] == niveis and registro["semente"] == semente, "Registro de outro nivel/semente")
        arquivos_esperados = {str(p.resolve()) for p in (cache, cache.with_suffix(".csv"), checkpoint)}
        exigir(set(registro["arquivos_sha256"]) == arquivos_esperados, "Registro nao cobre todos artefatos")
        conferir_hashes(registro["arquivos_sha256"])
        fim = pd.Timestamp(registro["concluido_em_utc"])
        exigir(fim <= congelado_em if selecao else fim >= congelado_em, "Fase fora da ordem do congelamento")
        historico = pd.read_csv(cache.with_suffix(".csv"))
        np.testing.assert_array_equal(historico.epoca, np.arange(1, len(historico)+1))
        n = int(linha["epocas"][str(semente)])
        exigir(np.isfinite(historico.perda_treino).all(), "Perda de treinamento nao finita")
        if selecao:
            melhor, epoca = float("inf"), 0
            exigir(np.isfinite(historico.mae_validacao_wm2).all(), "Validacao nao finita")
            for registro_h in historico.itertuples():
                if registro_h.mae_validacao_wm2 < melhor-1e-12:
                    melhor, epoca = registro_h.mae_validacao_wm2, registro_h.epoca
            exigir(epoca == n, "Epoca congelada diverge do historico de validacao")
        else:
            exigir(len(historico) == n and historico.mae_validacao_wm2.isna().all(),
                   "Refit nao respeita epocas fixas ou usa validacao")
        with np.load(cache, allow_pickle=False) as z:
            bruto = z["previsao"].copy()
            exigir(int(z["epocas"].item()) == n, "Epocas do cache divergem")
        exigir(np.isfinite(bruto).all() and bruto.shape == avaliacao.y_bruto.shape, "Cache de previsao invalido")
        cp = torch.load(checkpoint, map_location="cpu", weights_only=True)
        exigir(cp["fase"] == fase and cp["variante"] == linha["nome"], "Fase/variante do checkpoint diverge")
        exigir(cp["semente"] == semente and cp["epocas"] == n and registro["epocas"] == n,
               "Epocas/semente do checkpoint divergem")
        exigir(cp["contrato_sha256"] == contrato["sha256_contrato"], "Checkpoint de outro contrato")
        for chave, obj in (("tarefa", tarefa), ("candidato", candidato), ("configuracao", cfg)):
            exigir(exp.hash_obj(cp[chave]) == exp.hash_obj(asdict(obj)), "Checkpoint difere em "+chave)
        prep = cp["preprocessamento"]
        exigir(prep["niveis"] == niveis and prep["onde"] == "somente_entradas" and prep["minmax"],
               "Preprocessamento incorreto")
        exigir(prep["escala_fim_exclusivo"] == corte and prep["dispositivo"] == "cpu", "Corte/dispositivo incorreto")
        perto(pd.DataFrame(prep["escalas"])[campos], escalas[campos], "escalas no checkpoint")
        exigir(prep["localidades"] == {str(s.localidade_id): s.localidade for s in series}, "Identidades no checkpoint")
        erro_replay = None
        if reproduzir:
            replay = exp.prever_checkpoint(checkpoint, avaliacao)
            erro_replay = perto(replay, bruto, "checkpoint versus cache")
            # Verifica a previsao real, alem da preparacao de x, com outro y bruto.
            replay_y = exp.prever_checkpoint(checkpoint, replace(avaliacao, y_bruto=avaliacao.y_bruto+10000))
            perto(replay, replay_y, "previsao independente de y", 0)
        reconstruido = base.montar_tabela_previsoes(tarefa=tarefa, janelas=avaliacao,
            estimativas=[base.Estimativa("TimesNet", "semente", semente, bruto, np.maximum(bruto, 0))])
        reconstruido = reconstruido.sort_values(CHAVES).reset_index(drop=True)
        coluna = f"previsao_bruta_timesnet_seed{semente}_wm2"
        erro_csv = perto(reconstruido[coluna], frame[coluna], "cache versus CSV")
        perto(np.maximum(frame[coluna], 0), frame[coluna.replace("bruta", "pos")], "piso por semente")
        mae = float(np.mean([np.abs(d.ghi_real_wm2-d[coluna.replace("bruta", "pos")]).mean()
                            for _, d in frame.groupby("localidade")]))
        if selecao:
            perto(mae, linha["MAE_validacao_sementes"][str(semente)], "MAE individual congelado")
            perto(mae, historico.loc[historico.epoca == n, "mae_validacao_wm2"].iloc[0], "MAE da melhor epoca")
        brutas.append(bruto)
        resultados.append({"semente": int(semente), "epocas": n, "duracao_s": registro["duracao_s"],
            "checkpoint_reproduzido": reproduzir, "erro_maximo_replay_wm2": erro_replay,
            "erro_maximo_csv_wm2": erro_csv, "MAE_wm2": mae})
    cols = [f"previsao_bruta_timesnet_seed{s}_wm2" for s in cfg.sementes_efetivas]
    ensemble = frame[cols].mean(axis=1)
    perto(ensemble, frame.previsao_bruta_timesnet_ensemble_wm2, "media bruta antes do piso")
    perto(np.maximum(ensemble, 0), frame.previsao_pos_timesnet_ensemble_wm2, "piso ensemble")
    local, macro = recalcular_metricas(frame, tarefa, cfg.sementes_efetivas, nome_particao)
    sufixo = "_validacao" if selecao else ""
    erro_local = conferir_metricas(pd.read_csv(pasta/f"metricas_por_localidade{sufixo}.csv"), local, True)
    erro_macro = conferir_metricas(pd.read_csv(pasta/f"metricas_macro{sufixo}.csv"), macro)
    mae = float(macro.loc[(macro.tipo_estimativa == "ensemble") & (macro.tipo_horizonte == "cumulativo")
                         & (macro.horizonte == tarefa.pred_len), "MAE_wm2"].item())
    if selecao:
        perto(mae, linha["MAE_validacao_wm2"], "MAE de selecao")
    return {"fase": fase, "linhas_previsao": len(frame), "localidades": frame.localidade.nunique(),
            "origens_por_localidade": frame.groupby("localidade").origem.nunique().to_dict(),
            "MAE_ensemble_wm2": mae, "erro_maximo_metricas_locais": erro_local,
            "erro_maximo_metricas_macro": erro_macro, "controles_quantizacao": controles,
            "checkpoints": resultados}


def auditar(pasta_saida, reproduzir_selecao=True):
    pasta_saida = Path(pasta_saida).resolve()
    snapshot_path = exp.RAIZ/"relatorios/quantizacao_timesnet_20260923/fontes_anteriores_sha256.json"
    anteriores = exp.ler_json(snapshot_path) if snapshot_path.is_file() else {}
    snapshot_verificado = conferir_snapshot_historico(anteriores)
    exp.validar_congelamento_global(pasta_saida)
    global_path = pasta_saida/"selecao_global_congelada.json"
    global_hash = base.sha256_arquivo(global_path)
    congelado = exp.ler_json(global_path)
    congelado_em = pd.Timestamp(congelado["congelado_em_utc"])
    fontes = congelado["fontes_selecao_sha256"]
    tarefas = []
    for slug in exp.TAREFAS:
        pasta = pasta_saida/slug
        contrato = exp.ler_json(pasta/"contrato_execucao.json")
        conteudo = {k: v for k, v in contrato.items() if k != "sha256_contrato"}
        exigir(exp.hash_obj(conteudo) == contrato["sha256_contrato"], "Hash interno de contrato incorreto")
        for chave in ("entradas_sha256", "codigo_sha256", "fontes_configuracao"):
            conferir_hashes(contrato[chave])
        for nome in ("contrato_execucao.json", "escalas_selecao.csv", "selecao_congelada.json"):
            p = str((pasta/nome).resolve())
            exigir(p in fontes, "Congelamento global nao cobre "+p)
        smoke = contrato["configuracao"]["modo_execucao"] == "smoke"
        series, tarefa, candidato, cfg = exp.preparar_contexto(slug, smoke=smoke)
        exigir(exp.hash_obj(asdict(candidato)) == exp.hash_obj(contrato["candidato_base"]), "Candidato alterado")
        exigir(exp.hash_obj(asdict(cfg)) == exp.hash_obj(contrato["configuracao"]), "Configuracao alterada")
        exigir(exp.hash_obj(asdict(tarefa)) == exp.hash_obj(contrato["tarefa"]), "Tarefa alterada")
        exigir(candidato.alvo == "bruto", "Alvo nao e GHI direto")
        selecao = exp.ler_json(pasta/"selecao_congelada.json")
        exigir(selecao["contrato_sha256"] == contrato["sha256_contrato"], "Selecao de outro contrato")
        exigir(selecao["selecao_concluida_antes_do_teste"], "Selecao nao concluida antes de teste")
        ranking = selecao["ranking"]
        nomes = [r["nome"] for r in ranking]
        exigir(len(nomes) == 4 and set(nomes) == {n for n, _ in exp.VARIANTES}, "Grade incompleta")
        ordem = {nome: i for i, (nome, _) in enumerate(exp.VARIANTES)}
        esperado = sorted(ranking, key=lambda r: (r["MAE_validacao_wm2"], ordem[r["nome"]]))
        exigir(ranking == esperado and selecao["vencedor"] == esperado[0], "Vencedor nao segue validacao")
        comparacao = pd.read_csv(pasta/"comparacao.csv").set_index("nome")
        exigir(set(comparacao.index) == set(nomes) and comparacao.index.is_unique, "Comparacao incompleta")
        exigir(comparacao.selecionada.sum() == 1 and bool(comparacao.loc[esperado[0]["nome"], "selecionada"]),
               "Vencedor alterado no teste")
        variantes = []
        for nome, niveis in exp.VARIANTES:
            linha = next(r for r in ranking if r["nome"] == nome)
            exigir(linha["niveis"] == niveis, "Nivel congelado divergente")
            exigir(set(linha["epocas"]) == {str(s) for s in cfg.sementes_efetivas}, "Sementes incompletas")
            variante = pasta/"variantes"/nome
            sel = auditar_fase(variante, tarefa, candidato, cfg, series, contrato, linha, niveis,
                              "selecao", congelado_em, reproduzir_selecao)
            refit = auditar_fase(variante, tarefa, candidato, cfg, series, contrato, linha, niveis,
                                "refit", congelado_em, True)
            perto(comparacao.loc[nome, "MAE_validacao_wm2"], sel["MAE_ensemble_wm2"], "comparacao validacao")
            perto(comparacao.loc[nome, "MAE_teste_wm2"], refit["MAE_ensemble_wm2"], "comparacao teste")
            variantes.append({"nome": nome, "niveis": niveis, "selecao": sel, "refit": refit})
        manifesto = exp.ler_json(pasta/"manifesto_artefatos.json")
        exigir(manifesto["N_arquivos"] == len(manifesto["arquivos"]), "Contagem do manifesto incorreta")
        for r in manifesto["arquivos"]:
            p = pasta/r["arquivo"]
            exigir(p.stat().st_size == r["bytes"] and base.sha256_arquivo(p) == r["sha256"], "Manifesto divergente: "+str(p))
        tarefas.append({"tarefa": slug, "modo": cfg.modo_execucao, "vencedor_validacao": esperado[0]["nome"],
            "contrato_sha256": contrato["sha256_contrato"], "manifesto_arquivos": manifesto["N_arquivos"],
            "variantes": variantes})
    conferir_hashes(fontes)
    exigir(conferir_snapshot_historico(anteriores) == snapshot_verificado,
           "Snapshot historico mudou durante a auditoria")
    exigir(base.sha256_arquivo(global_path) == global_hash, "Congelamento alterado durante auditoria")
    total_refit = sum(len(v["refit"]["checkpoints"]) for t in tarefas for v in t["variantes"])
    total_selecao = sum(sum(c["checkpoint_reproduzido"] for c in v["selecao"]["checkpoints"])
                        for t in tarefas for v in t["variantes"])
    return {"aprovado": True, "gerado_em_utc": datetime.now(timezone.utc).isoformat(),
            "pasta_experimento": str(pasta_saida), "script_sha256": base.sha256_arquivo(__file__),
            "congelamento_global_sha256": global_hash, "fontes_congeladas_verificadas": len(fontes),
            "arquivos_historicos_preservados": snapshot_verificado["arquivos_preservados"],
            "snapshot_historico": snapshot_verificado,
            "checkpoints_refit_reproduzidos": total_refit, "checkpoints_selecao_reproduzidos": total_selecao,
            "metricas_recalculadas_independentemente": METRICAS,
            "dados_brutos_e_codigo_preservados": True,
            "interpretacao": "Comparacao retrospectiva; nivel escolhido somente pela validacao 2023; sem reselecao por 2024.",
            "tarefas": tarefas}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pasta", type=Path, default=exp.SAIDA)
    parser.add_argument("--saida", type=Path, default=exp.RAIZ/"relatorios/quantizacao_timesnet_20260923/auditoria_quantizacao.json")
    parser.add_argument("--sem-reproduzir-selecao", action="store_true")
    args = parser.parse_args()
    relatorio = auditar(args.pasta, not args.sem_reproduzir_selecao)
    base.salvar_json_atomico(relatorio, args.saida)
    print(json.dumps({"aprovado": relatorio["aprovado"], "saida": str(args.saida),
        "checkpoints_refit": relatorio["checkpoints_refit_reproduzidos"],
        "checkpoints_selecao": relatorio["checkpoints_selecao_reproduzidos"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
