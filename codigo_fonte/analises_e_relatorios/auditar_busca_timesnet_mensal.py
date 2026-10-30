"""Audita busca mensal e recarrega checkpoints, sem treino ou escrita nas fontes.

Exemplo: python -m codigo_fonte.analises_e_relatorios.auditar_busca_timesnet_mensal --fonte
resultados/busca_timesnet_mensal_v2_20260920 --saida
resultados/relatorios/otimizacao_timesnet_20260922
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import torch

from codigo_fonte.experimentos import experimento_multirresolucao as base
from codigo_fonte.experimentos import otimizacao_timesnet_mensal as busca


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ler_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def conferir_manifesto(pasta):
    manifesto = ler_json(pasta / "manifesto_artefatos.json")
    erros = []
    for registro in manifesto["arquivos"]:
        caminho = (pasta / registro["arquivo"]).resolve()
        if not caminho.is_relative_to(pasta.resolve()):
            raise ValueError("Manifesto aponta para fora da pasta fonte.")
        if (not caminho.is_file() or caminho.stat().st_size != registro["bytes"]
                or sha256(caminho) != registro["sha256"]):
            erros.append(registro["arquivo"])
    if erros:
        raise ValueError(f"Artefatos divergentes: {erros}")
    return {"arquivos_verificados": len(manifesto["arquivos"]), "divergencias": erros}


def mae_macro(quadro, coluna):
    erros = abs(quadro["ghi_real_wm2"] - quadro[coluna])
    return float(erros.groupby(quadro["localidade_id"]).mean().mean())


def conferir_proximidade(a, b, nome, tolerancia=1e-7):
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError(f"Forma ou finitude divergente: {nome}")
    erro = float(np.max(np.abs(a - b)))
    if erro > tolerancia:
        raise ValueError(f"{nome}: diferenca maxima {erro} > {tolerancia}")
    return erro


def tabela_ordenada(quadro):
    quadro = quadro.copy()
    for c in ("origem", "data_alvo"):
        quadro[c] = pd.to_datetime(quadro[c]).astype("datetime64[ns]")
    return quadro.sort_values(["localidade_id", "origem", "passo"]).reset_index(drop=True)


def auditar_tarefa(pasta, canonico):
    contrato = ler_json(pasta / "contrato_execucao.json")
    manifesto = conferir_manifesto(pasta)
    codigo = {nome: {"contrato": esperado,
                     "atual": sha256(ROOT / "codigo_fonte" / nome),
                     "confere_atualmente": sha256(ROOT / "codigo_fonte" / nome) == esperado}
              for nome, esperado in contrato["codigo"].items()}
    for entrada in contrato["entradas"]:
        if sha256(entrada["arquivo"]) != entrada["sha256"]:
            raise ValueError(f"Entrada original alterada: {entrada['arquivo']}")
    pastas = {Path(e["arquivo"]).parent for e in contrato["entradas"]}
    if len(pastas) != 1:
        raise ValueError("Entradas devem compartilhar a pasta de dados diarios.")
    diarias, _ = base.carregar_series_diarias(next(iter(pastas)))
    series = base.agregar_series_mensais(diarias)
    selecao = ler_json(pasta / "selecao_congelada.json")
    ranking = pd.read_csv(pasta / "ranking_validacao.csv")
    vencedor = selecao["vencedor"]
    menor = ranking.sort_values(["MAE_validacao_ensemble_wm2", "nome"]).iloc[0]
    if menor["nome"] != vencedor["nome"]:
        raise ValueError("Vencedor nao corresponde ao menor MAE na validacao.")
    dados = tabela_ordenada(pd.read_csv(pasta / "previsoes_teste.csv"))
    validacao = tabela_ordenada(pd.read_csv(pasta / "previsoes_validacao.csv"))
    sementes = contrato["configuracao"]["sementes"]
    ensemble_col = "previsao_bruta_timesnet_ensemble_wm2"
    soma = dados[[f"previsao_bruta_timesnet_seed{s}_wm2" for s in sementes]].mean(axis=1)
    diferenca_ensemble = conferir_proximidade(soma, dados[ensemble_col], "ensemble CSV")
    conferir_proximidade(np.maximum(dados[ensemble_col], 0),
                         dados["previsao_pos_timesnet_ensemble_wm2"], "piso zero ensemble")
    maes = {"teste_timesnet": mae_macro(dados, "previsao_pos_timesnet_ensemble_wm2"),
            "teste_climatologia": mae_macro(dados, "previsao_pos_climatologia_deterministica_wm2"),
            "validacao_timesnet": mae_macro(validacao, "previsao_pos_timesnet_ensemble_wm2"),
            "validacao_climatologia": mae_macro(validacao, "previsao_pos_climatologia_deterministica_wm2")}
    conferir_proximidade(maes["validacao_timesnet"], vencedor["MAE_validacao_ensemble_wm2"], "MAE vencedor")
    conferir_proximidade(maes["validacao_timesnet"], menor["MAE_validacao_ensemble_wm2"], "ranking validacao")
    status = ler_json(pasta / "status_execucao.json")
    conferir_proximidade(maes["teste_timesnet"], status["MAE_teste_wm2"], "status teste")
    conferir_proximidade(maes["validacao_timesnet"], status["MAE_validacao_wm2"], "status validacao")
    macros = pd.read_csv(pasta / "metricas_macro.csv")
    for modelo, chave, tipo in (("TimesNet", "teste_timesnet", "ensemble"),
                                ("Climatologia", "teste_climatologia", "deterministica")):
        selecionadas = macros.loc[(macros.modelo == modelo)
            & (macros.tipo_estimativa == tipo) & (macros.tipo_horizonte == "cumulativo")
            & (macros.horizonte == selecao["tarefa"]["pred_len"])]
        if len(selecionadas) != 1:
            raise ValueError("Linha macro de teste ausente ou duplicada.")
        conferir_proximidade(maes[chave], selecionadas.iloc[0]["MAE_wm2"], "macro salvo " + modelo)
    checkpoints = []
    for semente in sementes:
        caminho = pasta / "modelos" / f"timesnet_seed{semente}_refit.pt"
        cp = torch.load(caminho, map_location="cpu", weights_only=True)
        especificacao = dict(cp["tarefa"])
        for particao in ("ajuste", "validacao", "refit", "teste"):
            especificacao[particao] = base.IntervaloParticao(**especificacao[particao])
        tarefa = base.EspecificacaoTarefa(**especificacao)
        config = base.ConfiguracaoMultirresolucao(**cp["configuracao"])
        candidato = busca.Candidato(**cp["candidato"])
        if candidato.nome != vencedor["nome"] or cp["semente"] != semente:
            raise ValueError("Checkpoint difere de candidato/semente selecionados.")
        if cp["epocas_refit"] != vencedor["epocas"][str(semente)]:
            raise ValueError("Epocas de refit diferentes da selecao.")
        refit = busca._janelas(series, tarefa, "refit", config)
        teste = busca._janelas(series, tarefa, "teste", config)
        _, entrada, escalas, deslocamento = busca.preparar_treino(
            candidato, series, refit, teste, fim_exclusivo="2024-01-01", nome_ajuste="refit")
        escalas_salvas = pd.read_csv(pasta / "escalas_refit.csv")
        cols = ["minimo_treino_wm2", "maximo_treino_wm2", "amplitude_escala_wm2"]
        erro_escala = conferir_proximidade(escalas.sort_values("localidade_id")[cols],
                                          escalas_salvas.sort_values("localidade_id")[cols], "escalas")
        modelo = base.criar_modelo_neural("TimesNet", tarefa=tarefa, configuracao=config,
                                          num_localidades=len(series), semente=semente)
        modelo.load_state_dict(cp["state_dict"])
        previsao = busca._prever(modelo, entrada, escalas, config)
        if deslocamento is not None:
            previsao = previsao + deslocamento
        with np.load(pasta / "refit" / f"seed{semente}.npz", allow_pickle=False) as cache:
            erro_npz = conferir_proximidade(previsao, cache["previsao"], "checkpoint vs NPZ")
        reconstruido = tabela_ordenada(base.montar_tabela_previsoes(
            tarefa=tarefa, janelas=teste, estimativas=[base.Estimativa(
                "TimesNet", "semente", semente, previsao, np.maximum(previsao, 0))]))
        chaves = ["localidade_id", "localidade", "origem", "data_alvo", "passo"]
        pd.testing.assert_frame_equal(reconstruido[chaves], dados[chaves], check_dtype=False)
        col = f"previsao_bruta_timesnet_seed{semente}_wm2"
        erro_csv = conferir_proximidade(reconstruido[col], dados[col], "checkpoint vs CSV")
        conferir_proximidade(reconstruido["ghi_real_wm2"], dados["ghi_real_wm2"], "alvos CSV")
        checkpoints.append({"semente": semente, "epocas_refit": cp["epocas_refit"],
                            "campos": list(cp), "preprocessamento_embutido": "preprocessamento" in cp,
                            "erro_maximo_npz_wm2": erro_npz, "erro_maximo_csv_wm2": erro_csv,
                            "erro_maximo_escalas_wm2": erro_escala,
                            "MAE_teste_wm2": busca.macro_mae(teste, previsao)})
    antigo = tabela_ordenada(pd.read_csv(canonico / pasta.name / "previsoes_teste.csv.gz"))
    chaves = ["localidade_id", "localidade", "origem", "data_alvo", "passo"]
    pd.testing.assert_frame_equal(dados[chaves], antigo[chaves], check_dtype=False)
    conferir_proximidade(dados["ghi_real_wm2"], antigo["ghi_real_wm2"], "alvos canonicos")
    maes["canonico_timesnet"] = mae_macro(antigo, "previsao_pos_timesnet_ensemble_wm2")
    maes["reducao_absoluta_wm2"] = maes["canonico_timesnet"] - maes["teste_timesnet"]
    maes["reducao_percentual"] = 100 * maes["reducao_absoluta_wm2"] / maes["canonico_timesnet"]
    return {"tarefa": pasta.name, "manifesto": manifesto, "codigo": codigo,
            "entradas_integras": len(contrato["entradas"]), "vencedor": vencedor,
            "candidatos_avaliados": len(ranking), "descartados": ler_json(pasta / "candidatos_descartados.json"),
            "comparacao": maes, "linhas_teste": len(dados), "localidades": dados.localidade.nunique(),
            "origens_por_localidade": dados.groupby("localidade").origem.nunique().to_dict(),
            "erro_maximo_ensemble_csv_wm2": diferenca_ensemble,
            "checkpoints": checkpoints, "protocolo": selecao["tarefa"],
            "limitacoes": contrato["limitacoes"],
            "fontes": {p.name: sha256(p) for p in (pasta / "contrato_execucao.json",
                                                  pasta / "manifesto_artefatos.json",
                                                  pasta / "selecao_congelada.json")}}


def markdown(relatorio):
    linhas = ["# Auditoria da otimizacao mensal da TimesNet", "",
              "As previsoes historicas foram recalculadas a partir dos CSVs e reproduzidas pela recarga dos dez checkpoints, sem novo treinamento. Fontes historicas foram somente lidas.", "",
              "| Horizonte | MAE anterior | MAE otimizado | Reducao | Climatologia |",
              "|---|---:|---:|---:|---:|"]
    for t in relatorio["tarefas"]:
        c = t["comparacao"]
        linhas.append(f"| {t['tarefa']} | {c['canonico_timesnet']:.6f} | {c['teste_timesnet']:.6f} | {c['reducao_percentual']:.2f}% | {c['teste_climatologia']:.6f} |")
    linhas += ["", "MAE em W/m2: media dos erros absolutos de cada localidade, seguida de media entre dez localidades. O horizonte de seis meses agrega os seis passos de cada uma das sete origens por localidade; nao e previsao de cinco anos.", ""]
    for t in relatorio["tarefas"]:
        v, c = t["vencedor"], t["comparacao"]
        linhas += [f"## {t['tarefa']}", "",
                   f"Vencedor por validacao: `{v['nome']}`. Contexto {v['seq_len']} meses; alvo anomalia em relacao a climatologia mensal pre-corte; perda {v['perda']}; taxa {v['taxa_aprendizado']}; d_model={v['d_model']}; d_ff={v['d_ff']}; blocos={v['blocos']}.", "",
                   f"Validacao: TimesNet {c['validacao_timesnet']:.6f}; climatologia {c['validacao_climatologia']:.6f} W/m2. A climatologia ainda e melhor na validacao e no teste.", "",
                   f"Foram conferidos {t['manifesto']['arquivos_verificados']} hashes/tamanhos de artefatos e {t['entradas_integras']} hashes de entradas. {t['candidatos_avaliados']} candidatos foram avaliados com cinco sementes; contexto 36 foi descartado por falta de origens de treino.", "",
                   "| Semente | Epocas refit | MAE teste | Erro maximo checkpoint vs NPZ |",
                   "|---:|---:|---:|---:|"]
        for cp in t["checkpoints"]:
            linhas.append(f"| {cp['semente']} | {cp['epocas_refit']} | {cp['MAE_teste_wm2']:.6f} | {cp['erro_maximo_npz_wm2']:.3g} |")
        linhas += ["", "Os checkpoints historicos nao incorporam escalas/climatologia. A recarga auditada reconstruiu essas transformacoes exclusivamente dos insumos originais anteriores a 2024 e reproduziu previsoes NPZ/CSV. O pipeline atual passou a persistir preprocessamento nos novos checkpoints; os historicos nao foram regravados.", ""]
    linhas += ["## Proveniencia e limites", "",
               "A auditoria inicial desta sessao confirmou igualdade dos quatro hashes de codigo com os contratos historicos, antes das correcoes posteriores de persistencia e retomada. `auditoria_inicial_sha256.json` registra essa observacao; `auditoria.json` registra separadamente os hashes atuais, que podem diferir apos as correcoes.", "",
               "A variante vencedora e um pipeline residual (climatologia + TimesNet da anomalia), nao uma melhora atribuivel somente aos hiperparametros da TimesNet bruta. A arquitetura canonica nao foi substituida.", "",
               "A busca foi motivada por resultados de 2024 ja observados. A selecao interna usou 2023 e congelou o vencedor antes de avaliar 2024, mas 2024 nao pode ser apresentado como confirmacao externa inteiramente inedita. Requer avaliacao futura ou outro periodo independente.", "",
               "O mesmo ano seleciona epocas e hiperparametros; ha risco de sobreajuste da validacao. As origens de seis meses se sobrepoem. Os resultados sao descritivos, sem teste de significancia que trate janelas como independentes. Janelas maiores tambem mudam a quantidade de treino. O historico nao foi ampliado nesta busca.", "",
               "Reexecutar: `.\\.venv-baselines-gpu-20260912\\Scripts\\python.exe codigo_fonte/analises_e_relatorios/auditar_busca_timesnet_mensal.py --fonte resultados/busca_timesnet_mensal_v2_20260920 --saida resultados/relatorios/otimizacao_timesnet_20260922`", ""]
    return "\n".join(linhas)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", type=Path, default=ROOT / "resultados/busca_timesnet_mensal_v2_20260920")
    parser.add_argument("--canonico", type=Path, default=ROOT / "resultados/avaliacao_multirresolucao_corrigida_v2")
    parser.add_argument("--saida", type=Path, default=ROOT / "resultados/relatorios/otimizacao_timesnet_20260922")
    args = parser.parse_args()
    fonte, canonico, saida = args.fonte.resolve(), args.canonico.resolve(), args.saida.resolve()
    if any(saida == p or saida.is_relative_to(p) for p in (fonte, canonico)):
        parser.error("A saida deve ficar fora das fontes historicas.")
    tarefas = [auditar_tarefa(fonte / nome, canonico) for nome in ("monthly_1", "monthly_6")]
    relatorio = {"gerado_em_utc": datetime.now(timezone.utc).isoformat(),
                 "fonte": str(fonte), "canonico": str(canonico), "sem_treinamento": True,
                 "python": sys.version, "torch": str(torch.__version__), "tarefas": tarefas}
    saida.mkdir(parents=True, exist_ok=True)
    (saida / "auditoria.json").write_text(json.dumps(relatorio, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (saida / "auditoria.md").write_text(markdown(relatorio), encoding="utf-8")
    print(json.dumps({t["tarefa"]: t["comparacao"] for t in tarefas}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
