"""Figuras suplementares do benchmark completo (11 modelos), a partir da consolidacao.

S1: mapa de posicoes por macro-MAE cumulativo (tarefa x horizonte x modelo), com o
numero da posicao escrito em cada celula e uma unica escala sequencial de azul.
S2: variabilidade entre sementes dos modelos aprendidos estocasticos, com os
modelos deslocados lado a lado em cada horizonte e valores fora de escala
(Informer horario) marcados numa faixa acima da linha tracejada.
Figura 4 do artigo (variabilidade_arquiteturas): o mesmo desenho de S2, restrito a
TimesNet e DilatedRNN.

Reutiliza o estilo (grade de paineis, titulos, salvamento PNG/PDF/SVG) de
artefatos_artigo_unificado sem alterar aquele modulo. Paleta categorica validada com o
validador de paletas (verde, azul-claro, violeta, rosa, laranja, azul, vermelhao:
CVD adjacente minimo 16,6; visao normal minimo 18,4).

Grava ranking_por_tarefa e variabilidade_por_semente, os mesmos nomes usados por
artefatos_artigo_unificado: se as saidas daquele modulo forem copiadas para a
pasta do artigo, rode este script depois, senao S1 e S2 voltam a versao antiga.

Uso:
  python -m codigo_fonte.gerar_figuras_benchmark_completo
  python -m codigo_fonte.gerar_figuras_benchmark_completo --fonte <consolidado> --saida <pasta>
"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import transforms
from matplotlib.colors import LinearSegmentedColormap

from codigo_fonte import artefatos_artigo_unificado as a
from codigo_fonte.experimento_baselines_adicionais import RAIZ, SAIDA

ORDEM = ("Persistencia", "Sazonal ingenuo", "Climatologia", "ARIMA", "XGBoost", "LSTM",
         "GRU", "Transformer", "Informer", "TimesNet", "DilatedRNN")
NOMES = {"Persistencia": "Persistence", "Sazonal ingenuo": "Seasonal naive",
         "Climatologia": "Climatology"}
CORES_NOVAS = {"GRU": "#4A3AA7", "Transformer": "#CC79A7", "Informer": "#E69F00"}
MARCADORES_NOVOS = {"GRU": "P", "Transformer": "h", "Informer": "*"}
ORDEM_LEGENDA = ("XGBoost", "LSTM", "GRU", "Transformer", "Informer", "TimesNet", "DilatedRNN")
# Rampa sequencial azul (passos 250 a 700): o passo mais claro ainda contrasta 2:1.
RAMPA = LinearSegmentedColormap.from_list(
    "posicao", ["#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#86b6ef"])
TINTA_ESCURA, TINTA_CLARA, SEM_DADO = "#0b0b0b", "#ffffff", "#f0efec"
TINTA_SECUNDARIA, LINHA_FAIXA = "#52514e", "#B8BEC6"


def estimativas_principais(macro: pd.DataFrame) -> pd.DataFrame:
    """Ensemble ou deterministica no teste de 2024; semente 42 no horario."""
    base = macro.loc[(macro.particao == "teste_2024") & (macro.tipo_horizonte == "cumulativo") & (
        macro.tipo_estimativa.isin(["ensemble", "deterministica"]) |
        ((macro.tarefa == "hourly_72_extension") & (macro.tipo_estimativa == "semente")))].copy()
    if base.duplicated(["tarefa", "horizonte", "modelo"]).any():
        raise ValueError("Mais de uma estimativa principal por modelo e horizonte.")
    base["posicao"] = base.groupby(["tarefa", "horizonte"])["MAE_wm2"].rank(method="min").astype(int)
    return base


def _luminancia(cor) -> float:
    r, g, b = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in cor[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def figura_posicoes(base: pd.DataFrame, pasta: Path) -> None:
    tarefas = sorted(base.tarefa.unique(), key=lambda t: a._ORDEM_TAREFAS_ARTIGO.get(t, 9))
    modelos = [m for m in ORDEM if m in set(base.modelo)]
    n_max = len(modelos)
    figura, eixos = plt.subplots(2, 2, figsize=(7.25, 6.4), squeeze=False,
                                 gridspec_kw={"hspace": 0.36, "wspace": 0.14})
    eixos = eixos.ravel()
    for indice, (eixo, tarefa) in enumerate(zip(eixos, tarefas)):
        grupo = base.loc[base.tarefa == tarefa]
        horizontes = sorted(grupo.horizonte.unique())
        matriz = grupo.pivot(index="modelo", columns="horizonte", values="posicao").reindex(modelos)[horizontes]
        valores = matriz.to_numpy(dtype=float)
        rampa = RAMPA.copy()
        rampa.set_bad(SEM_DADO)
        eixo.pcolormesh(np.arange(len(horizontes) + 1) - 0.5, np.arange(len(modelos) + 1) - 0.5,
                        np.ma.masked_invalid(valores), cmap=rampa, vmin=1, vmax=n_max,
                        edgecolors="white", linewidth=1.2)
        eixo.set_xlim(-0.5, len(horizontes) - 0.5)
        eixo.set_ylim(len(modelos) - 0.5, -0.5)
        for (i, j), valor in np.ndenumerate(valores):
            if np.isnan(valor):
                eixo.text(j, i, "n/a", ha="center", va="center", fontsize=6.4, color="#52514e")
                continue
            cor = RAMPA((valor - 1) / (n_max - 1))
            tinta = TINTA_CLARA if _luminancia(cor) < 0.30 else TINTA_ESCURA
            eixo.text(j, i, f"{int(valor)}", ha="center", va="center", fontsize=7.2,
                      color=tinta, fontweight="bold" if valor == 1 else "normal")
        eixo.set_xticks(range(len(horizontes)))
        especificacao = a._ESPECIFICACOES_TAREFAS_FIGURA[tarefa]
        eixo.set_xticklabels([f"{int(h)}" for h in horizontes], fontsize=7.4)
        eixo.set_xlabel(f"Cumulative horizon ({especificacao['unidade']})", fontsize=7.8)
        eixo.set_yticks(range(len(modelos)))
        if indice % 2 == 0:
            eixo.set_yticklabels([NOMES.get(m, m) for m in modelos], fontsize=7.4)
            for rotulo in eixo.get_yticklabels():
                if rotulo.get_text() in a.MODELOS_COMPARADOS:
                    rotulo.set_fontweight("bold")
        else:
            eixo.set_yticklabels([])
        eixo.tick_params(which="both", length=0)
        for lado in eixo.spines.values():
            lado.set_visible(False)
        eixo.set_title(f"({a._ROTULOS_PAINEIS[indice]}) {especificacao['titulo']}",
                       loc="left", fontsize=7.9, fontweight="semibold", pad=5)
    for eixo in eixos[len(tarefas):]:
        eixo.set_visible(False)
    a._salvar_figura(figura, pasta / "ranking_por_tarefa")


def _fora_da_escala(grupo: pd.DataFrame) -> set[str]:
    """Modelos cujo pior MAE medio passa de 1,5 vez a mediana do painel."""
    pior = grupo.groupby("modelo").MAE_wm2_media.max()
    return set(pior.index[pior > 1.5 * pior.median()])


def figura_variabilidade(variabilidade: pd.DataFrame, pasta: Path, *,
                         modelos: Sequence[str] | None = None,
                         nome: str = "variabilidade_por_semente") -> None:
    dados = variabilidade.loc[(variabilidade.particao == "teste_2024") &
                              (variabilidade.tipo_horizonte == "cumulativo")]
    if modelos is not None:
        dados = dados.loc[dados.modelo.isin(modelos)]
    tarefas = sorted(dados.tarefa.unique(), key=lambda t: a._ORDEM_TAREFAS_ARTIGO.get(t, 9))
    modelos = [m for m in ORDEM_LEGENDA if m in set(dados.modelo)]
    cores = {**a._CORES_MODELOS, **CORES_NOVAS}
    marcadores = {**a._MARCADORES_MODELOS, **MARCADORES_NOVOS}
    figura, eixos = a._criar_grade_tarefas(tarefas)
    alcas = {}
    for indice, (eixo, tarefa) in enumerate(zip(eixos, tarefas)):
        grupo = dados.loc[dados.tarefa == tarefa]
        fora = _fora_da_escala(grupo)
        dentro = grupo.loc[~grupo.modelo.isin(fora)]
        desvio = dentro.MAE_wm2_desvio_padrao.fillna(0.0)
        baixo = (dentro.MAE_wm2_media - desvio).min()
        alto = (dentro.MAE_wm2_media + desvio).max()
        folga = 0.12 * (alto - baixo)
        faixa = 0.28 * (alto - baixo) if fora else 0.0
        # Deslocamento horizontal em pontos: separa modelos no mesmo horizonte.
        # Com poucos modelos ha espaco para afastar mais as barras de erro.
        unico = grupo.horizonte.nunique() == 1
        if len(modelos) > 3:
            passo = 7.0 if unico else 2.2
        else:
            passo = 10.0 if unico else 6.0
        for posicao, modelo in enumerate(modelos):
            serie = grupo.loc[grupo.modelo == modelo].sort_values("horizonte")
            if serie.empty:
                continue
            deslocado = transforms.offset_copy(eixo.transData, fig=figura, units="points",
                                               x=(posicao - (len(modelos) - 1) / 2) * passo, y=0)
            estilo = {"color": cores[modelo], "marker": marcadores[modelo], "markerfacecolor": "white",
                      "markeredgewidth": 0.9, "markersize": 4.8, "transform": deslocado, "zorder": 3}
            if modelo in fora:
                # Faixa acima da linha tracejada: posicao fora de escala, valor escrito.
                y_faixa = alto + folga + 0.4 * faixa
                eixo.plot(serie.horizonte, np.full(len(serie), y_faixa), linestyle="none", **estilo)
                for h, valor in zip(serie.horizonte, serie.MAE_wm2_media):
                    eixo.annotate(f"{valor:.1f}", (h, y_faixa), xycoords=deslocado, xytext=(0, 4),
                                  textcoords="offset points", ha="center", va="bottom",
                                  fontsize=6.6, color=TINTA_SECUNDARIA)
                continue
            desvios = serie.MAE_wm2_desvio_padrao.to_numpy(dtype=float)
            sem_desvio = bool(np.isnan(desvios).all())
            linha = eixo.errorbar(serie.horizonte, serie.MAE_wm2_media,
                                  yerr=None if sem_desvio else desvios,
                                  capsize=0 if sem_desvio else 2.5, elinewidth=0.9, linewidth=1.5,
                                  linestyle="-" if len(serie) > 1 else "none", **estilo)
            alcas.setdefault(modelo, linha)
        a._configurar_eixo_tarefa(eixo, tarefa=tarefa, horizontes=grupo.horizonte, indice_painel=indice)
        horizontes = sorted(grupo.horizonte.unique())
        if len(horizontes) > 1:
            # Limites explicitos: o deslocamento em pontos nao entra no autoescalonamento.
            margem = 0.08 * (horizontes[-1] - horizontes[0])
            eixo.set_xlim(horizontes[0] - margem, horizontes[-1] + margem)
        eixo.set_ylim(baixo - folga, alto + folga + faixa)
        if fora:
            eixo.set_yticks([t for t in eixo.get_yticks() if baixo - folga <= t <= alto + folga])
            eixo.axhline(alto + folga, color=LINHA_FAIXA, linewidth=0.8, linestyle=(0, (3, 2)), zorder=1)
        if (grupo.N_sementes == 1).all():
            eixo.text(0.98, 0.04, "n = 1 | SD unavailable", transform=eixo.transAxes, ha="right",
                      va="bottom", fontsize=7.0, color="#444444",
                      bbox={"boxstyle": "round,pad=0.22", "facecolor": "white",
                            "edgecolor": LINHA_FAIXA, "linewidth": 0.6})
        eixo.set_ylabel("Macro MAE (W m$^{-2}$)", fontsize=8.2)
    for eixo in eixos[len(tarefas):]:
        eixo.set_visible(False)
    ordem = [m for m in modelos if m in alcas]
    figura.legend([alcas[m] for m in ordem], ordem, ncol=4, fontsize=7.6, loc="upper center",
                  bbox_to_anchor=(0.5, 1.005), frameon=False, columnspacing=1.4, handlelength=1.8)
    figura.tight_layout(rect=(0.0, 0.0, 1.0, 0.94), h_pad=1.05, w_pad=0.9)
    a._salvar_figura(figura, pasta / nome)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fonte", type=Path, default=SAIDA / "consolidado")
    ap.add_argument("--saida", type=Path, default=RAIZ / "artigos/revista_unificado/figures")
    args = ap.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)
    variabilidade = pd.read_csv(args.fonte / "variabilidade_sementes.csv")
    figura_posicoes(estimativas_principais(pd.read_csv(args.fonte / "metricas_macro.csv")), args.saida)
    figura_variabilidade(variabilidade, args.saida)
    figura_variabilidade(variabilidade, args.saida, modelos=a.MODELOS_COMPARADOS,
                         nome="variabilidade_arquiteturas")
    print(f"Figuras S1, S2 e 4 gravadas em {args.saida}", flush=True)


if __name__ == "__main__":
    main()
