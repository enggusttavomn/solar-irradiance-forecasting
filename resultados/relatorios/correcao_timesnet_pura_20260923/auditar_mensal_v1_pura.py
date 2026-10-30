"""Auditoria somente de leitura da busca mensal V1 com TimesNet de alvo bruto.

Recarrega dez checkpoints em CPU, verifica caches/epocas/ranking, integridade
das fontes e compara com a TimesNet canonica. Nao executa treinamento.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ["CUDA_VISIBLE_DEVICES"] = ""

import numpy as np
import pandas as pd
import torch

from codigo_fonte import experimento_multirresolucao as base
from codigo_fonte import otimizacao_timesnet_mensal as busca
from scripts import auditar_busca_timesnet_mensal as auditor


def especificacao(d):
    d = dict(d)
    for fase in ("ajuste", "validacao", "refit", "teste"):
        d[fase] = base.IntervaloParticao(**d[fase])
    return base.EspecificacaoTarefa(**d)


def impedir_climatologia(*args, **kwargs):
    raise AssertionError("Uma inferencia TimesNet pura nao deve consultar climatologia.")


def conferir_manifesto_canonico(pasta):
    manifesto = auditor.ler_json(pasta / "manifesto_artefatos.json")
    divergencias = []
    for registro in manifesto["arquivos"]:
        caminho = (pasta / registro["arquivo"]).resolve()
        assert caminho.is_relative_to(pasta.resolve()) and caminho.is_file()
        atual = auditor.sha256(caminho)
        if caminho.stat().st_size != registro["bytes"] or atual != registro["sha256"]:
            divergencias.append({**registro, "sha256_atual": atual,
                "bytes_atuais": caminho.stat().st_size,
                "mtime_atual_utc": datetime.fromtimestamp(caminho.stat().st_mtime, timezone.utc).isoformat()})
    # Metadados divergentes sao registrados, jamais corrigidos nesta auditoria.
    assert all(d["arquivo"] == "contrato_execucao.json" for d in divergencias)
    return {"arquivos_conferidos": len(manifesto["arquivos"]),
        "arquivos_integralmente_conformes": len(manifesto["arquivos"]) - len(divergencias),
        "divergencias": divergencias,
        "previsoes_e_checkpoints_conformes_manifesto": True}


def auditar_ranking(pasta):
    contrato = auditor.ler_json(pasta / "contrato_execucao.json")
    congelado = auditor.ler_json(pasta / "selecao_congelada.json")
    ranking = pd.read_csv(pasta / "ranking_validacao.csv").set_index("nome")
    por_semente = pd.read_csv(pasta / "selecao_por_semente.csv")
    diario, _ = base.carregar_series_diarias(Path(contrato["entradas"][0]["arquivo"]).parent)
    series = base.agregar_series_mensais(diario)
    series = tuple(replace(s, datas=s.datas[s.datas < "2024-01-01"],
                           ghi=s.ghi[s.datas < "2024-01-01"]) for s in series)
    config = base.ConfiguracaoMultirresolucao(**contrato["configuracao"])
    escalas = base.ajustar_escalas_pre_corte(series, fim_exclusivo="2023-01-01", nome_ajuste="selecao")
    cols = ["minimo_treino_wm2", "maximo_treino_wm2", "amplitude_escala_wm2"]
    auditor.conferir_proximidade(escalas.sort_values("localidade_id")[cols],
        pd.read_csv(pasta / "escalas_selecao.csv").sort_values("localidade_id")[cols], "escalas selecao")
    linhas = []
    epocas_auditadas = 0
    candidatos = {c["nome"]: busca.Candidato(**c) for c in contrato["candidatos"]}
    assert all(c.alvo == "bruto" for c in candidatos.values())
    for nome in ranking.index:
        cand = candidatos[nome]
        tarefa = especificacao(auditor.ler_json(pasta / "candidatos" / nome / "protocolo.json"))
        ajuste = busca._janelas(series, tarefa, "ajuste", config)
        validacao = busca._janelas(series, tarefa, "validacao", config)
        assert ajuste.datas_alvo.max() < np.datetime64("2023-01-01")
        assert validacao.datas_alvo.min() >= np.datetime64("2023-01-01")
        assert validacao.datas_alvo.max() < np.datetime64("2024-01-01")
        aj, val, _, deslocamento = busca.preparar_treino(cand, series, ajuste, validacao,
            fim_exclusivo="2023-01-01", nome_ajuste="selecao")
        assert aj is ajuste and val is validacao and deslocamento is None
        previsoes, maes, sementes = [], [], []
        for seed in config.sementes:
            cache = pasta / "candidatos" / nome / f"seed{seed}.npz"
            with np.load(cache, allow_pickle=False) as dados:
                p = dados["previsao"].copy()
                epocas = int(dados["epocas"].item())
            historico = pd.read_csv(cache.with_suffix(".csv"))
            melhor = historico.loc[historico.mae_validacao_wm2.idxmin()]
            assert epocas == int(melhor.epoca)
            mae = busca.macro_mae(validacao, p)
            auditor.conferir_proximidade(mae, melhor.mae_validacao_wm2, "historico/cache MAE")
            salvo = por_semente.loc[(por_semente.candidato == nome) & (por_semente.semente == seed)]
            assert len(salvo) == 1 and int(salvo.iloc[0].epocas) == epocas
            auditor.conferir_proximidade(mae, salvo.iloc[0].MAE_validacao_wm2, "MAE por semente")
            if nome == congelado["vencedor"]["nome"]:
                assert epocas == congelado["vencedor"]["epocas"][str(seed)]
            previsoes.append(p)
            maes.append(mae)
            sementes.append({"semente": seed, "epocas": epocas, "MAE_validacao_wm2": mae,
                             "historico_epocas": len(historico)})
            epocas_auditadas += 1
        ensemble = np.mean(previsoes, axis=0)
        mae = busca.macro_mae(validacao, ensemble)
        auditor.conferir_proximidade(mae, ranking.loc[nome, "MAE_validacao_ensemble_wm2"], "ranking ensemble")
        auditor.conferir_proximidade(np.mean(maes), ranking.loc[nome, "MAE_validacao_media_sementes_wm2"], "ranking media")
        auditor.conferir_proximidade(np.std(maes, ddof=1), ranking.loc[nome, "DP_MAE_sementes_wm2"], "ranking DP")
        if nome == congelado["vencedor"]["nome"]:
            reconstruida = auditor.tabela_ordenada(base.montar_tabela_previsoes(tarefa=tarefa,
                janelas=validacao, estimativas=[base.Estimativa("TimesNet", "ensemble", None,
                                              ensemble, np.maximum(ensemble, 0))]))
            salva = auditor.tabela_ordenada(pd.read_csv(pasta / "previsoes_validacao.csv"))
            chaves = ["localidade_id", "localidade", "origem", "data_alvo", "passo"]
            pd.testing.assert_frame_equal(reconstruida[chaves], salva[chaves], check_dtype=False)
            for col in ("ghi_real_wm2", "previsao_bruta_timesnet_ensemble_wm2"):
                auditor.conferir_proximidade(reconstruida[col], salva[col], "validacao CSV "+col)
        linhas.append({"nome": nome, "alvo": cand.alvo, "MAE_validacao_ensemble_wm2": mae,
                       "sementes": sementes})
    menor = min(linhas, key=lambda r: (r["MAE_validacao_ensemble_wm2"], r["nome"]))
    assert menor["nome"] == congelado["vencedor"]["nome"]
    return {"candidatos_declarados": len(candidatos), "candidatos_recalculados": len(linhas),
            "caches_e_historicos_conferidos": epocas_auditadas, "alvo_exclusivo": "bruto",
            "janelas_treino_ate_2022": True, "alvos_validacao_exclusivamente_2023": True,
            "ranking": linhas}


def main():
    fonte = ROOT / "resultados/busca_timesnet_mensal_20260920"
    canonico = ROOT / "resultados/avaliacao_multirresolucao_corrigida_v2"
    saida = Path(__file__).resolve().parent
    # O auditor recarrega as redes em CPU. Desativar consultas residuais fornece
    # uma verificacao executavel de que esses checkpoints nao as necessitam.
    busca.climatologia_mensal = impedir_climatologia
    busca.climatologia_nas_janelas = impedir_climatologia
    torch.set_num_threads(1)
    tarefas = []
    for nome in ("monthly_1", "monthly_6"):
        pasta = fonte / nome
        print(f"Auditando {nome}: hashes, ranking e CPU checkpoints", flush=True)
        detalhado = auditar_ranking(pasta)
        resultado = auditor.auditar_tarefa(pasta, canonico)
        resultado["auditoria_selecao_completa"] = detalhado
        original = auditor.tabela_ordenada(pd.read_csv(canonico / nome / "previsoes_validacao.csv.gz"))
        otimizada = auditor.tabela_ordenada(pd.read_csv(pasta / "previsoes_validacao.csv"))
        chaves = ["localidade_id", "localidade", "origem", "data_alvo", "passo"]
        pd.testing.assert_frame_equal(original[chaves], otimizada[chaves], check_dtype=False)
        auditor.conferir_proximidade(original.ghi_real_wm2, otimizada.ghi_real_wm2, "alvos validacao canonicos")
        resultado["comparacao"]["validacao_canonico_timesnet"] = auditor.mae_macro(original, "previsao_pos_timesnet_ensemble_wm2")
        resultado["vence_canonico_na_validacao"] = (resultado["comparacao"]["validacao_timesnet"]
            < resultado["comparacao"]["validacao_canonico_timesnet"])
        resultado["manifesto_apos_auditoria"] = auditor.conferir_manifesto(pasta)
        resultado["manifesto_canonico"] = conferir_manifesto_canonico(canonico / nome)
        resultado["sem_climatologia_inferencia"] = True
        tarefas.append(resultado)
        print(json.dumps(resultado["comparacao"], ensure_ascii=False), flush=True)
    relatorio = {"gerado_em_utc": datetime.now(timezone.utc).isoformat(),
        "sem_treinamento": True, "dispositivo_inferencia": "cpu", "torch": str(torch.__version__),
        "python": sys.version, "fonte": str(fonte), "canonico": str(canonico), "tarefas": tarefas,
        "conclusao": "Busca V1 de TimesNet pura reutilizavel; previsoes reproduzidas e selecao por validacao conferida.",
        "limite_proveniencia": "Os hashes atuais de modulos alterados podem divergir dos contratos historicos. A reproducao verifica pesos, entradas, escalas e saidas; nao reconstrui o treinamento nem comprova independentemente a ordem temporal original das gravacoes.",
        "limite_checkpoint": "Checkpoints antigos nao incluem escalas; a reproducao depende das entradas originais verificadas por hash.",
        "criterio_epocas_original": "MSE normalizado na validacao 2023",
        "criterio_epocas_otimizado": "macro-MAE fisico na validacao 2023",
        "limite_manifesto_canonico": "Os contratos de execucao canonicos divergem de seus manifestos historicos; a auditoria registra os hashes esperados e atuais. Previsoes e checkpoints canonicos permanecem conformes aos hashes dos manifestos. Nenhuma fonte foi alterada.",
        "script_sha256": auditor.sha256(__file__)}
    (saida / "auditoria_mensal_v1_pura.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    linhas = ["# Auditoria da TimesNet mensal pura (V1)", "",
        "Sem novo treinamento. Dez checkpoints reproduzidos em CPU. A inferencia e a reconstrucao do ranking foram executadas com as funcoes de climatologia residual bloqueadas.", "",
        "| Tarefa | Validacao original | Validacao otimizada | Teste original | Teste otimizado | Reducao teste |",
        "|---|---:|---:|---:|---:|---:|"]
    for t in tarefas:
        c = t["comparacao"]
        linhas.append(f"| {t['tarefa']} | {c['validacao_canonico_timesnet']:.6f} | {c['validacao_timesnet']:.6f} | {c['canonico_timesnet']:.6f} | {c['teste_timesnet']:.6f} | {c['reducao_percentual']:.2f}% |")
    linhas += ["", "MAE macro em W/m2; menor e melhor. O conjunto de teste e 2024. Ambos os vencedores tambem superam a TimesNet original em 2023, criterio de selecao.", ""]
    for t in tarefas:
        v = t["vencedor"]
        linhas += [f"## {t['tarefa']}", "",
            f"Vencedor: `{v['nome']}`; alvo GHI bruto; contexto {v['seq_len']}; perda {v['perda']}; taxa {v['taxa_aprendizado']}; d_model={v['d_model']}, d_ff={v['d_ff']}, blocos={v['blocos']}, dropout={v['dropout']}.", "",
            f"Conferidos {t['manifesto']['arquivos_verificados']} hashes/tamanhos, {t['entradas_integras']} entradas, oito candidatos e quarenta caches/historicos de selecao. As epocas salvas correspondem aos minimos de MAE de 2023; o ranking e o vencedor foram recalculados. Contexto 36 foi descartado por insuficiencia de origens de ajuste.", "",
            "| Semente | Epocas refit | MAE teste | Erro maximo checkpoint/NPZ |",
            "|---:|---:|---:|---:|"]
        for cp in t["checkpoints"]:
            linhas.append(f"| {cp['semente']} | {cp['epocas_refit']} | {cp['MAE_teste_wm2']:.6f} | {cp['erro_maximo_npz_wm2']:.3g} |")
        linhas += ["", "A previsao e a inversao min-max da saida TimesNet; as cinco sementes sao promediadas e aplica-se somente piso zero. Climatologia aparece nos CSVs como comparador independente, sem compor essas previsoes.", ""]
    linhas += ["## Limites", "", relatorio["limite_proveniencia"], "", relatorio["limite_checkpoint"], "",
        relatorio["limite_manifesto_canonico"], "",
        "A TimesNet original selecionava epocas por MSE normalizado; a busca seleciona por macro-MAE fisico. Portanto o ganho inclui essa mudanca no criterio de selecao de epocas, alem dos hiperparametros e da perda de treino; nao e uma ablacao isolada.", "",
        "A busca foi motivada por resultados de 2024 ja vistos; portanto o teste nao constitui confirmacao externa inteiramente inedita. Epocas e hiperparametros compartilham 2023; ha risco de sobreajuste. Os seis passos mensais usam sete origens sobrepostas por localidade. Os ganhos sao descritivos, sem alegacao de significancia.", "",
        "Fontes historicas foram somente lidas. Nenhum checkpoint, contrato, manifesto, CSV ou cache original foi alterado.", ""]
    (saida / "auditoria_mensal_v1_pura.md").write_text("\n".join(linhas), encoding="utf-8")
    print(relatorio["conclusao"], flush=True)


if __name__ == "__main__":
    main()
