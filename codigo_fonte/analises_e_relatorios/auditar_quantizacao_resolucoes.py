"""Auditoria independente, sem treino, da quantizacao TimesNet diaria/horaria.

Reconstroi um contexto por tarefa e reproduz checkpoints no dispositivo/lote
salvos com os alvos substituidos por NaN. Escreve somente o relatorio externo.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch

from codigo_fonte.experimentos import experimento_baselines_adicionais as dados
from codigo_fonte.experimentos import experimento_multirresolucao as base
from codigo_fonte.experimentos import experimento_quantizacao_resolucoes as exp
from codigo_fonte.experimentos import treinamento_timesnet_quantizado_resolucoes as treino
from codigo_fonte.analises_e_relatorios.auditar_timesnet_resolucoes import conferir_manifesto, comparar_metricas, epoca_historico, metricas_independentes

RELATORIOS = ROOT / "resultados/relatorios/quantizacao_timesnet_quatro_casos_20260927"
VARIANTES = (("sem_quantizacao", None), ("q64", 64), ("q128", 128), ("q256", 256))


def ler(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def exigir(valor, mensagem):
    if not valor:
        raise AssertionError(mensagem)


def perto(a, b, nome, atol=1e-7):
    a, b = np.asarray(a, float), np.asarray(b, float)
    exigir(a.shape == b.shape, f"Forma divergente: {nome}")
    exigir(np.array_equal(np.isnan(a), np.isnan(b)), f"NaNs divergentes: {nome}")
    mascara = ~np.isnan(a)
    exigir(np.isfinite(a[mascara]).all() and np.isfinite(b[mascara]).all(), f"Inf: {nome}")
    delta = float(np.max(np.abs(a[mascara]-b[mascara]))) if mascara.any() else 0.
    exigir(delta <= atol, f"{nome}: diferenca {delta} > {atol}")
    return delta


def hashes(fontes):
    for path, digest in fontes.items():
        exigir(Path(path).is_file(), f"Arquivo ausente: {path}")
        exigir(base.sha256_arquivo(path) == digest, f"Hash divergente: {path}")
    return len(fontes)


def snapshot_historico(path):
    """So admite PDF final diferente mediante backup e registro de entrega."""
    if path is None:
        return {"verificado": False}
    fontes = ler(path)
    final = (ROOT/"documentacao/tabela_resultados_ghi_2024.pdf").resolve()
    entrega_path = Path(path).parent/"entrega_pdf.json"
    mudancas = []
    for arquivo, digest in fontes.items():
        p = Path(arquivo).resolve()
        atual = base.sha256_arquivo(p)
        if atual == digest:
            continue
        exigir(p == final and entrega_path.is_file(), f"Historico alterado: {p}")
        entrega = ler(entrega_path)
        pdf, anterior = entrega.get("pdf", {}), entrega.get("pdf_anterior", {})
        exigir(pdf.get("path") and anterior.get("path"), "Entrega sem caminhos")
        backup = Path(anterior["path"]).resolve()
        exigir(Path(pdf["path"]).resolve() == final and backup != final, "Entrega de outro PDF")
        exigir(pdf.get("sha256") == atual, "PDF diverge da entrega")
        exigir(anterior.get("sha256") == digest and base.sha256_arquivo(backup) == digest,
               "Backup nao preserva PDF anterior")
        mudancas.append({"arquivo": str(p), "anterior": digest, "atual": atual,
                         "backup": str(backup), "entrega_sha256": base.sha256_arquivo(entrega_path)})
    return {"verificado": True, "arquivos": len(fontes), "alteracoes_autorizadas": mudancas}


def contrato_valido(c):
    bruto = {k: v for k, v in c.items() if k != "sha256_contrato"}
    digest = hashlib.sha256(json.dumps(bruto, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    exigir(c["sha256_contrato"] == digest, "Contrato interno alterado")
    exigir(c["minmax"] is True and c["quantizacao"]["onde"] == "somente_entradas", "Pre-processamento errado")
    exigir(c["quantizacao"]["alvos_quantizados"] is False and
           c["quantizacao"]["pesos_quantizados"] is False, "Alvos/pesos quantizados")
    exigir(c["variantes"] == [{"nome": n, "niveis": k} for n, k in VARIANTES], "Grade alterada")
    return {grupo: hashes(c[grupo]) for grupo in ("codigo", "entradas", "fontes_configuracao")}


def congelamento_global(root):
    registro = ler(root/"selecao_global_congelada.json")
    exigir(set(registro["tarefas"]) == set(exp.TAREFAS), "Congelamento sem ambas tarefas")
    fontes = registro["fontes_selecao_sha256"]
    for t in exp.TAREFAS:
        p = root/t
        s = ler(p/"selecao_congelada.json")
        exigir(s["selecao_concluida_antes_do_teste"] is True, "Selecao nao congelada")
        exigir(pd.Timestamp(s["criado_em_utc"]) <= pd.Timestamp(registro["congelado_em_utc"]),
               "Selecao posterior ao congelamento global")
        expected = dict(s["fontes_selecao_sha256"])
        for n in ("contrato_execucao.json", "selecao_congelada.json", "escalas_selecao.csv"):
            expected[str((p/n).resolve())] = base.sha256_arquivo(p/n)
        exigir(all(fontes.get(k) == v for k, v in expected.items()), "Congelamento omite fonte de selecao")
    hashes(fontes)
    return registro


def chaves(ctx):
    if ctx.tarefa.resolucao == "horaria":
        datas_col = ["origem_utc", "timestamp_alvo_utc"]
        return ["localidade", *datas_col, "passo_h"], datas_col
    datas_col = ["origem", "data_alvo"]
    return ["localidade", *datas_col, "passo"], datas_col


def alinhar(ctx, particao, frame, subconjunto=False):
    esperado = dados.tabela_chaves(ctx, particao).copy()
    frame = frame.copy()
    keys, dates = chaves(ctx)
    for col in dates:
        esperado[col] = pd.to_datetime(esperado[col], utc=True)
        frame[col] = pd.to_datetime(frame[col], utc=True)
    exigir(not frame.duplicated(keys).any(), "Previsoes duplicadas")
    exigir(subconjunto or len(frame) == len(esperado), "Quantidade de previsoes divergente")
    junto = esperado[keys+["ghi_real_wm2"]].merge(frame, on=keys, how="left",
                    validate="one_to_one", sort=False, suffixes=("_esperado", ""))
    perto(junto.ghi_real_wm2, junto.ghi_real_wm2_esperado, "Observacoes das janelas", 1e-6)
    return junto.drop(columns="ghi_real_wm2_esperado")


def pos_processar(bruto, elevacao=None):
    out = np.maximum(np.asarray(bruto, float), 0.)
    if elevacao is not None:
        out[np.asarray(elevacao) <= 0.] = 0.
    return out


def mae_macro(real, previsto, ids):
    return float(np.mean([np.mean(np.abs(np.asarray(real)[ids == i]-np.asarray(previsto)[ids == i]))
                          for i in np.unique(ids)]))


def conferir_quantizacao(janelas, escalas, niveis, diagnostico):
    tabela = escalas.set_index("localidade_id").loc[janelas.localidade_id]
    x = ((janelas.x_bruto.astype(np.float32)-tabela.minimo_treino_wm2.to_numpy(np.float32)[:, None]) /
         tabela.amplitude_escala_wm2.to_numpy(np.float32)[:, None])
    q = x.copy() if niveis is None else (
        np.rint(np.clip(x, 0, 1).astype(float)*(niveis-1))/(niveis-1)).astype(np.float32)
    alvo_antes = janelas.y_bruto.copy()
    np.testing.assert_array_equal(treino._normalizar_contexto(janelas, escalas, niveis), q)
    np.testing.assert_array_equal(janelas.y_bruto, alvo_antes)
    sem_alvos = copy.copy(janelas)
    object.__setattr__(sem_alvos, "y_bruto", np.full_like(janelas.y_bruto, np.nan))
    np.testing.assert_array_equal(treino._normalizar_contexto(sem_alvos, escalas, niveis), q)
    recortes = {"total": np.ones(len(x), bool), **{
        str(int(i)): janelas.localidade_id == i for i in np.unique(janelas.localidade_id)}}
    exigir(set(diagnostico) == set(recortes), "Recortes de diagnostico divergentes")
    for nome, mask in recortes.items():
        z, w, d = x[mask], q[mask], diagnostico[nome]
        abaixo, acima = int((z < 0).sum()), int((z > 1).sum())
        alterados, saturados = int((z != w).sum()), abaixo+acima if niveis is not None else 0
        expected = {"total": z.size, "abaixo_zero": abaixo, "acima_um": acima,
                    "alterados": alterados, "saturados": saturados, "niveis": niveis}
        exigir(all(d[k] == v for k, v in expected.items()), f"Diagnostico divergente: {nome}")
        perto(d["fracao_alterados"], alterados/z.size, "Fracao alterados")
        perto(d["fracao_saturados"], saturados/z.size, "Fracao saturados")
        perto(d["erro_medio_quantizacao_normalizado"], np.abs(z.astype(float)-w).mean(), "Erro quantizacao")
        perto(d["erro_medio_somente_clip_normalizado"], np.abs(z.astype(float)-np.clip(z, 0, 1)).mean()
              if niveis is not None else 0., "Erro clipping")
    return {"x_confere": True, "y_bruto_preservado": True, "inferencia_independe_de_y": True}


def conferir_cortes(ctx, fase):
    p_treino, p_eval = ("ajuste", "validacao_2023") if fase == "selecao" else ("refit", "teste_2024")
    limite = pd.Timestamp("2023-01-01" if fase == "selecao" else "2024-01-01")
    final = limite + pd.DateOffset(years=1)
    for nome, treino_flag in ((p_treino, True), (p_eval, False)):
        j = ctx.janelas[nome]
        if ctx.tarefa.resolucao == "horaria":
            # Cortes civis individuais preservam os fusos de cada localidade.
            datas_alvo = j.origem_local.to_numpy()[:, None] + np.arange(j.pred_len)[None, :]*np.timedelta64(1, "h")
        else:
            datas_alvo = j.datas_alvo
        exigir(np.asarray(datas_alvo).max() < np.datetime64(limite if treino_flag else final),
               "Alvos atravessam corte temporal")
        if not treino_flag:
            exigir(np.asarray(datas_alvo).min() >= np.datetime64(limite), "Avaliacao anterior ao corte")


def auditar_fase(ctx, pasta, c, ranking, nome, niveis, fase, global_doc, replay):
    variante = pasta/"variantes"/nome
    selecao = fase == "selecao"
    particao = "validacao_2023" if selecao else "teste_2024"
    sufixo = "validacao" if selecao else "teste"
    ajuste_nome = "ajuste" if selecao else "refit"
    j, esc = ctx.janelas[particao], ctx.escalas[fase]
    elevacao = ctx.elevacoes.get(particao)
    conferir_cortes(ctx, fase)
    salvas = pd.read_csv(pasta/f"escalas_{fase}.csv")
    pd.testing.assert_frame_equal(salvas, esc, check_dtype=False, atol=1e-12, rtol=1e-12)
    diag = ler(variante/f"diagnostico_{fase}.json")
    for rotulo, janela in ((ajuste_nome, ctx.janelas[ajuste_nome]), (sufixo, j)):
        conferir_quantizacao(janela, esc, niveis, diag[rotulo])
    frame = alinhar(ctx, particao, pd.read_csv(variante/f"previsoes_{sufixo}.csv.gz"))
    benchmark = alinhar(ctx, particao, pd.read_csv(exp.FONTE/ctx.tarefa.slug/f"previsoes_{sufixo}.csv.gz"),
                       subconjunto=ctx.config.modo_execucao == "smoke")
    if elevacao is not None:
        perto(frame.elevacao_solar_graus, elevacao.reshape(-1), "Elevacao solar")
    resultados, brutas = [], []
    for seed in c["sementes"]:
        cache = variante/fase/f"seed{seed}.npz"
        hist_path, cp_path = cache.with_suffix(".csv"), variante/"modelos"/f"timesnet_seed{seed}_{fase}.pt"
        meta, cp = ler(cache.with_suffix(".json")), torch.load(cp_path, map_location="cpu", weights_only=True)
        exigir(meta["contrato_sha256"] == cp["contrato_sha256"] == c["sha256_contrato"], "Contrato CP/cache errado")
        exigir(meta["semente"] == cp["semente"] == seed and meta["niveis"] == niveis, "Seed/niveis errados")
        exigir(cp["fase"] == fase and cp["variante"] == nome, "Fase/variante errada")
        exigir(json.loads(json.dumps(cp["configuracao"])) == c["configuracao"] and
               json.loads(json.dumps(cp["tarefa"])) == c["tarefa"], "Arquitetura/configuracao alterada")
        exigir(cp["candidato"] == c["candidato_base"], "Candidato alterado")
        exigir(set(meta["arquivos_sha256"]) == {str(p.resolve()) for p in (cache, hist_path, cp_path)},
               "Registro nao cobre cache/historico/checkpoint")
        hashes(meta["arquivos_sha256"])
        p = cp["preprocessamento"]
        exigir(p["minmax"] is True and p["niveis"] == niveis and p["onde"] == "somente_entradas", "Prep CP errado")
        exigir(p["dispositivo"] == c["dispositivo"] and p["batch_size"] == c["configuracao"]["batch_size_diario"],
               "Dispositivo/lote de inferencia alterado")
        exigir(p["escala_fim_exclusivo"] == ("2023-01-01" if selecao else "2024-01-01"), "Corte CP errado")
        locais_esperados = {str(int(i)): str(n) for i, n in zip(j.localidade_id, j.localidade)}
        exigir(p["localidades"] == locais_esperados, "Identidade de localidade no CP incorreta")
        exigir(p["pos_processamento"] == ("piso_zero_e_mascara_solar" if elevacao is not None else "piso_zero"),
               "Pos-processamento do CP incorreto")
        pd.testing.assert_frame_equal(pd.DataFrame(p["escalas"]), esc, check_dtype=False, atol=1e-12, rtol=1e-12)
        with np.load(cache, allow_pickle=False) as z:
            bruto, epoca = z["previsao"], int(z["epocas"].item())
        exigir(bruto.shape == j.y_bruto.shape and np.isfinite(bruto).all(), "Cache de previsoes invalido")
        exigir(epoca == meta["epocas"] == cp["epocas"] == ranking["epocas"][str(seed)], "Epocas divergentes")
        hist = pd.read_csv(hist_path)
        exigir(np.array_equal(hist.epoca, np.arange(1, len(hist)+1)), "Epocas nao consecutivas")
        exigir(np.isfinite(hist.perda_treino).all(), "Loss nao finita")
        mae = mae_macro(j.y_bruto, pos_processar(bruto, elevacao), j.localidade_id)
        if selecao:
            exigir(epoca == epoca_historico(hist), "Epoca nao corresponde a melhor validacao")
            perto(mae, hist.iloc[epoca-1].mae_validacao_wm2, "MAE melhor epoca")
            exigir(pd.Timestamp(meta["concluido_em_utc"]) <= pd.Timestamp(global_doc["congelado_em_utc"]),
                   "Selecao posterior ao congelamento")
        else:
            exigir(len(hist) == epoca and hist.mae_validacao_wm2.isna().all(), "Refit usa validacao ou epocas diferentes")
            exigir(cp["selecao_global_sha256"] == base.sha256_arquivo(pasta.parent/"selecao_global_congelada.json")
                   and cp["selecao_tarefa_sha256"] == base.sha256_arquivo(pasta/"selecao_congelada.json"),
                   "Refit nao vinculado a selecao congelada")
            inicio = pd.Timestamp(meta["concluido_em_utc"])-pd.Timedelta(seconds=meta["duracao_s"])
            exigir(inicio >= pd.Timestamp(global_doc["congelado_em_utc"]), "Refit iniciou antes do congelamento")
        perto(frame[f"previsao_bruta_timesnet_seed{seed}_wm2"], bruto.reshape(-1), "CSV vs cache")
        perto(frame[f"previsao_pos_timesnet_seed{seed}_wm2"], pos_processar(bruto, elevacao).reshape(-1), "Pos seed")
        item = {"semente": seed, "epocas": epoca, "MAE": mae}
        if replay:
            sem_alvos = copy.copy(j)
            object.__setattr__(sem_alvos, "y_bruto", np.full_like(j.y_bruto, np.nan))
            obtido = exp.prever_checkpoint(cp_path, sem_alvos)
            item["replay_com_y_nan_diferenca_maxima"] = perto(obtido, bruto, "Replay CP com y=NaN", 1e-6)
            del obtido
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        brutas.append(bruto)
        resultados.append(item)
    media = np.mean(brutas, axis=0)
    perto(frame.previsao_bruta_timesnet_ensemble_wm2, media.reshape(-1), "Media bruta entre sementes")
    perto(frame.previsao_pos_timesnet_ensemble_wm2, pos_processar(media, elevacao).reshape(-1), "Media antes pos-processamento")
    para_metricas = frame.rename(columns={"previsao_pos_timesnet_ensemble_wm2": "previsao_pos_timesnet_otimizada_wm2"})
    locais, macro = metricas_independentes(para_metricas, ctx.tarefa.horizontes, ctx.tarefa.resolucao == "horaria")
    comparar_metricas(locais, pd.read_csv(variante/f"metricas_{sufixo}_por_localidade.csv"), local=True)
    comparar_metricas(macro, pd.read_csv(variante/f"metricas_{sufixo}_macro.csv"))
    mae = mae_macro(j.y_bruto, pos_processar(media, elevacao), j.localidade_id)
    if selecao:
        perto(mae, ranking["MAE_validacao_wm2"], "MAE ranking")
    else:
        status = ler(variante/"status_execucao.json")
        exigir(status["etapa"] == "concluida" and status["epocas"] == ranking["epocas"], "Status variante invalido")
        perto(status["MAE_teste_wm2"], mae, "MAE status")
    controle = None
    if nome == "sem_quantizacao" and ctx.config.modo_execucao == "completa":
        controle = perto(media.reshape(-1), benchmark.previsao_bruta_timesnet_otimizada_wm2, "Controle historico", 1e-6)
        registro = ler(variante/f"reproducao_controle_{fase}.json")
        exigir(registro["aprovado"] is True, "Controle historico nao aprovado")
        perto(registro["diferenca_maxima_wm2"], controle, "Registro controle")
    return {"fase": fase, "MAE": mae, "N_previsoes": len(frame), "checkpoints": resultados,
            "controle_delta": controle, "metricas_recalculadas": macro.to_dict("records")}


def auditar(root=exp.SAIDA, smoke=False, replay=True, snapshot=None):
    root = Path(root).resolve()
    snapshot = Path(snapshot) if snapshot else (None if smoke else RELATORIOS/"snapshot_anteriores.json")
    historico_antes = snapshot_historico(snapshot)
    global_doc = congelamento_global(root)
    report = {"gerado_em_utc": datetime.now(timezone.utc).isoformat(), "fonte": str(root),
              "smoke": smoke, "reproduz_checkpoints": replay, "tarefas": []}
    for slug in exp.TAREFAS:
        print(f"Auditando {slug}; reconstruindo contexto uma vez.", flush=True)
        pasta = root/slug
        c, s = ler(pasta/"contrato_execucao.json"), ler(pasta/"selecao_congelada.json")
        contagem_hashes = contrato_valido(c)
        exigir(c["modo"] == ("smoke" if smoke else "completa"), "Modo incorreto")
        manifest = conferir_manifesto(pasta)
        tarefa, candidato, conf, seeds, device = exp.parametros(slug, smoke)
        exigir(c["sementes"] == seeds and c["dispositivo"] == device, "Sementes/dispositivo diferentes do controle")
        exigir(c["configuracao"] == json.loads(json.dumps(asdict(conf))) and
               c["tarefa"] == json.loads(json.dumps(asdict(tarefa))), "Hiperparametros/tarefa diferentes do controle")
        exigir(c["candidato_base"] == asdict(candidato), "Candidato nao e o controle vencedor original")
        exigir(s["contrato_sha256"] == c["sha256_contrato"], "Selecao de outro contrato")
        ctx = dados.preparar_contexto(slug, "smoke" if smoke else "completa")
        ctx.tarefa, ctx.config = tarefa, conf
        exigir(len(ctx.series) == c["n_localidades"], "Localidades divergentes")
        ranking = {r["nome"]: r for r in s["ranking"]}
        exigir(set(ranking) == {n for n, _ in VARIANTES}, "Ranking incompleto")
        ordered = sorted(s["ranking"], key=lambda r: (r["MAE_validacao_wm2"], [n for n, _ in VARIANTES].index(r["nome"])))
        exigir(s["ranking"] == ordered and s["vencedor"] == ordered[0], "Escolha nao segue validacao")
        csv_ranking = pd.read_csv(pasta/"ranking_validacao.csv")
        exigir(csv_ranking.nome.tolist() == [r["nome"] for r in ordered], "Ordem CSV ranking incorreta")
        perto(csv_ranking.MAE_validacao_wm2, [r["MAE_validacao_wm2"] for r in ordered], "MAE CSV ranking")
        status = ler(pasta/"status_execucao.json")
        exigir(status["etapa"] == "concluida" and status["teste_avaliado"] is True and
               status["vencedor"] == s["vencedor"], "Status final invalido")
        comparacao = pd.read_csv(pasta/"comparacao.csv").set_index("nome")
        exigir(set(comparacao.index) == set(ranking), "Comparacao incompleta")
        task = {"tarefa": slug, "hashes": contagem_hashes, "manifesto": manifest,
                "vencedor_validacao": s["vencedor"], "variantes": []}
        for nome, niveis in VARIANTES:
            exigir(ranking[nome]["niveis"] == niveis, "Niveis do ranking errados")
            fases = [auditar_fase(ctx, pasta, c, ranking[nome], nome, niveis, fase, global_doc, replay)
                     for fase in ("selecao", "refit")]
            perto(comparacao.loc[nome, "MAE_validacao_wm2"], fases[0]["MAE"], "Comparacao validacao")
            perto(comparacao.loc[nome, "MAE_teste_wm2"], fases[1]["MAE"], "Comparacao teste")
            exigir(bool(comparacao.loc[nome, "selecionada"]) == (nome == s["vencedor"]["nome"]), "Marca de selecao incorreta")
            task["variantes"].append({"nome": nome, "niveis": niveis, "fases": fases})
            print(f"{slug}/{nome}: selecao, teste, metricas e checkpoints conferidos.", flush=True)
        report["tarefas"].append(task)
        del ctx
    report["historico"] = snapshot_historico(snapshot)
    exigir(report["historico"] == historico_antes, "Historico alterado durante auditoria")
    report["checkpoints_verificados"] = sum(len(f["checkpoints"]) for t in report["tarefas"]
                                           for v in t["variantes"] for f in v["fases"])
    exigir(report["checkpoints_verificados"] == (16 if smoke else 48), "Numero de checkpoints incompleto")
    report["ok"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", type=Path, default=exp.SAIDA)
    parser.add_argument("--saida", type=Path, default=RELATORIOS/"auditoria_quantizacao_resolucoes.json")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--sem-replay", action="store_true")
    args = parser.parse_args()
    report = auditar(args.fonte, args.smoke, not args.sem_replay, args.snapshot)
    base.salvar_json_atomico(report, args.saida)
    print(json.dumps({"ok": report["ok"], "checkpoints": report["checkpoints_verificados"],
                      "relatorio": str(args.saida.resolve())}), flush=True)


if __name__ == "__main__":
    main()
