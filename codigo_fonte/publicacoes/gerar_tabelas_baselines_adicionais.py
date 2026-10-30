"""Tabelas LaTeX/Markdown derivadas apenas da consolidacao verificada.

Nao treina, nao altera figuras, nao escolhe modelos pela conveniencia do resultado.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from codigo_fonte.experimentos import experimento_multirresolucao as m
from codigo_fonte.experimentos.experimento_baselines_adicionais import SAIDA, RAIZ, TAREFAS
from codigo_fonte.analises_e_relatorios.consolidar_baselines_adicionais import METRICAS

ORDEM = ["Persistencia", "Sazonal ingenuo", "Climatologia", "ARIMA", "XGBoost", "GRU", "LSTM", "Transformer", "Informer", "DilatedRNN", "TimesNet"]
NOMES = {"Persistencia": "Persistence", "Sazonal ingenuo": r"Seasonal na\"ive", "Climatologia": "Climatology"}
TITULOS = {"hourly_72_extension": "Hourly", "daily_30": "Daily", "monthly_1": "Monthly, one step", "monthly_6": "Monthly, six steps"}
SLUGS = ("hourly_72_extension", "daily_30", "monthly_1", "monthly_6")


def estimativas_principais(macro):
    return macro.loc[(macro.particao == "teste_2024") & (macro.tipo_horizonte == "cumulativo") & (
        (macro.tipo_estimativa == "deterministica") | (macro.tipo_estimativa == "ensemble") |
        ((macro.tarefa == "hourly_72_extension") & (macro.tipo_estimativa == "semente")))].copy()


def formatar(valor, serie, metrica):
    if not np.isfinite(valor):
        return "--"
    if metrica == "nRMSE":
        texto = f"{100 * valor:.2f}"
    elif metrica == "R2":
        texto = f"{valor:.3f}"
    else:
        texto = f"{valor:.2f}"
    unicos = np.unique(np.asarray(serie)[np.isfinite(serie)])
    if metrica == "R2":
        unicos = unicos[::-1]
    if len(unicos) and np.isclose(valor, unicos[0], atol=1e-10, rtol=0):
        return r"\textbf{" + texto + "}"
    if len(unicos) > 1 and np.isclose(valor, unicos[1], atol=1e-10, rtol=0):
        return r"\underline{" + texto + "}"
    return texto


def tabela_mae(base):
    terminal = {s: base.loc[(base.tarefa == s) & (base.horizonte == TAREFAS[s].pred_len)].set_index("modelo") for s in SLUGS}
    linhas = [r"\begin{table}[!htbp]", r"\centering", r"\scriptsize", r"\setlength{\tabcolsep}{3pt}",
        r"\caption{Complete terminal-horizon cumulative macro-MAE (W/m$^2$). Bold and underline mark the best and second-best unrounded values within each task. Hourly results use seed 42; other learned-model results use five-seed ensembles.}",
        r"\label{tab:benchmark_adicional_mae}", r"\begin{tabular}{@{}lrrrr@{}}", r"\toprule", r"Model & 72 h & 30 d & 1 mo & 6 mo \\", r"\midrule"]
    for modelo in ORDEM:
        celulas = []
        for s in SLUGS:
            g = terminal[s]
            celulas.append(formatar(g.loc[modelo, "MAE_wm2"], g.MAE_wm2.to_numpy(), "MAE_wm2") if modelo in g.index else "--")
        linhas.append(NOMES.get(modelo, modelo) + " & " + " & ".join(celulas) + r" \\")
    return "\n".join(linhas + [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])


def tabelas_completas(base):
    linhas = []
    for s in SLUGS:
        for h in TAREFAS[s].horizontes:
            g = base.loc[(base.tarefa == s) & (base.horizonte == h)].set_index("modelo")
            unidade = {"horaria": "h", "diaria": "d", "mensal": "mo"}[TAREFAS[s].resolucao]
            linhas += [r"\begin{table}[!htbp]", r"\centering", r"\small", r"\setlength{\tabcolsep}{6pt}",
                "\\caption{" + TITULOS[s] + f": cumulative scores through {h} {unidade}. " +
                r"MAE and RMSE are in W/m$^2$, MSE in (W/m$^2$)$^2$, nRMSE in percent, and $R^2$ is dimensionless. Bold/underline indicate best/second-best values before rounding.}",
                r"\label{tab:baseline_" + s + "_" + str(h) + "}",
                r"\begin{tabular}{@{}lrrrrr@{}}", r"\toprule", r"Model & MAE & MSE & RMSE & nRMSE (\%) & $R^2$ \\", r"\midrule"]
            for modelo in ORDEM:
                if modelo in g.index:
                    celulas = [formatar(g.loc[modelo, met], g[met].to_numpy(), met) for met in METRICAS]
                    linhas.append(NOMES.get(modelo, modelo) + " & " + " & ".join(celulas) + r" \\")
            linhas += [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""]
    return "\n".join(linhas)


def tabela_sementes(macro):
    base = macro.loc[(macro.particao == "teste_2024") & (macro.tipo_horizonte == "cumulativo") & (macro.tipo_estimativa == "semente")]
    linhas = [r"\begin{table}[!htbp]", r"\centering", r"\small", r"\setlength{\tabcolsep}{5pt}",
        r"\caption{Terminal cumulative macro-MAE across individual seeds: mean $\pm$ sample standard deviation (W/m$^2$). These are seed-level errors, not the error of the ensemble forecast. Hourly runs have one seed and no standard deviation.}",
        r"\label{tab:baseline_seeds}", r"\begin{tabular}{@{}lrrrr@{}}", r"\toprule", r"Model & 72 h ($N=1$) & 30 d ($N=5$) & 1 mo ($N=5$) & 6 mo ($N=5$) \\", r"\midrule"]
    for modelo in ORDEM:
        if modelo not in base.modelo.unique():
            continue
        celulas = []
        for s in SLUGS:
            valores = base.loc[(base.modelo == modelo) & (base.tarefa == s) & (base.horizonte == TAREFAS[s].pred_len), "MAE_wm2"]
            celulas.append(f"{valores.mean():.2f}" if len(valores) == 1 else "$" + f"{valores.mean():.2f}" + r"\pm" + f"{valores.std(ddof=1):.2f}" + "$")
        linhas.append(NOMES.get(modelo, modelo) + " & " + " & ".join(celulas) + r" \\")
    return "\n".join(linhas + [r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])


def nota_reuniao(base, macro):
    linhas = ["## 9. Resultados da extensão experimental", "", "Execuções completas e consolidação verificadas. A tentativa ARIMA inicial que falhou foi preservada; a versão final aplica L-BFGS e, somente em caso de não convergência, Powell, sem escolher otimizador por erro de validação ou teste.", "",
        "Macro-MAE cumulativo terminal (W/m²):", "", "| Modelo | 72 h | 30 d | 1 mês | 6 meses |", "|---|---:|---:|---:|---:|"]
    grupos = {s: base.loc[(base.tarefa == s) & (base.horizonte == TAREFAS[s].pred_len)].set_index("modelo") for s in SLUGS}
    for modelo in ORDEM:
        valores = [f"{grupos[s].loc[modelo, 'MAE_wm2']:.2f}".replace(".", ",") if modelo in grupos[s].index else "Não avaliada" for s in SLUGS]
        linhas.append("| " + modelo + " | " + " | ".join(valores) + " |")
    linhas += ["", "Menor macro-MAE terminal por tarefa:", ""]
    for s in SLUGS:
        g = grupos[s]
        vencedor = g.MAE_wm2.idxmin()
        linhas.append(f"- {s}: {vencedor}, {g.loc[vencedor, 'MAE_wm2']:.4f} W/m².")
    linhas += ["", "Os valores são do protocolo local, não uma comparação de números publicados em datasets diferentes. A interpretação deve considerar também RMSE, MSE, nRMSE, R², sementes e diferenças por localidade.", "",
        "Rastreabilidade da extensão:", "", "- `resultados/avaliacao_baselines_revisao_20260912/consolidado/metricas_macro.csv`: todas as métricas e checkpoints, cumulativos e leads exatos.",
        "- `consolidado/metricas_por_localidade.csv`: dez localidades, modelos, checkpoints e estimativas individuais/ensemble.",
        "- `consolidado/variabilidade_sementes.csv`: média e desvio padrão amostral por métrica e checkpoint; uma semente não recebe desvio padrão zero artificial.",
        "- Pastas por tarefa/modelo: contratos, hashes, modelos reajustados, históricos, previsões brutas/pós-processadas e status.",
        "- `consolidado/auditoria_consolidacao.json`: preservação dos resultados anteriores e definição da nova coluna MSE.", ""]
    return "\n".join(linhas)


def main():
    fonte = SAIDA / "consolidado"
    auditoria = json.loads((fonte / "auditoria_consolidacao.json").read_text(encoding="utf-8"))
    if not auditoria.get("inclui_todos_novos_baselines"):
        raise ValueError("A consolidacao deve conter todos os modelos completos.")
    macro = pd.read_csv(fonte / "metricas_macro.csv")
    base = estimativas_principais(macro)
    pasta = RAIZ / "artigos/revista_unificado/tables"
    produtos = {"benchmark_adicional_mae.tex": tabela_mae(base),
        "benchmark_adicional_completo.tex": tabelas_completas(base), "benchmark_adicional_sementes.tex": tabela_sementes(macro)}
    for nome, texto in produtos.items():
        (pasta / nome).write_text(texto, encoding="utf-8")
    reuniao = RAIZ / "documentacao/REVISAO_BIBLIOGRAFICA_REUNIAO_ORIENTADOR.md"
    texto = reuniao.read_text(encoding="utf-8")
    marcador = "<!-- RESULTADOS_ADICIONAIS_INICIO -->"
    prefixo = texto.split(marcador)[0].rstrip()
    reuniao.write_text(prefixo + "\n\n" + marcador + "\n\n" + nota_reuniao(base, macro), encoding="utf-8")
    m.salvar_json_atomico({"gerador": str(Path(__file__).resolve()), "sha256_gerador": m.sha256_arquivo(__file__),
        "fonte_metricas": str(fonte / "metricas_macro.csv"), "sha256_metricas": m.sha256_arquivo(fonte / "metricas_macro.csv"),
        "tabelas": [{"arquivo": str(pasta / n), "sha256": m.sha256_arquivo(pasta / n)} for n in produtos]},
        fonte / "rastreabilidade_tabelas.json")
    print("Tabelas e seção de resultados do documento único atualizadas.", flush=True)


if __name__ == "__main__":
    main()
