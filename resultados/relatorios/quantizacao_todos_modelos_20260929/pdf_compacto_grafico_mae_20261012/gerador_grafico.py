"""Figura vetorial do MAE dos modelos nos horizontes completos."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

from scripts.metricas_quantizacao_todos import MODELOS, TAREFAS

REGIMES = ('atual', 'historico_1998_2022', 'historico_curto_pareado')
LABELS = ('Base 2019-2024', 'Histórico longo', 'Histórico curto pareado')
PALETTE = ('#2F5F7D', '#23888B', '#B66032')
MARKERS = ('o', 's', '^')


def create_mae_figure(data, directory, width_points, height_points, model_label, task_labels):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    font_manager.fontManager.addfont('C:/Windows/Fonts/arial.ttf')
    font_manager.fontManager.addfont('C:/Windows/Fonts/arialbd.ttf')
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 8.2, 'pdf.fonttype': 42,
                         'svg.fonttype': 'none', 'axes.unicode_minus': False})
    fig, axes = plt.subplots(2, 2, figsize=(width_points / 72, height_points / 72), dpi=150)
    fig.subplots_adjust(left=.118, right=.990, bottom=.075, top=.89, wspace=.47, hspace=.39)
    models = sorted(MODELOS)
    y = np.arange(len(models), dtype=float)
    records, panels = [], []
    for ax, task in zip(axes.flat, TAREFAS, strict=True):
        horizon = max(TAREFAS[task])
        max_mae, winning_models = 0.0, set()
        for series, regime in enumerate(REGIMES):
            frame = data.rank(regime, task).set_index('modelo')
            values = np.array([float(frame.loc[model, 'MAE_wm2']) for model in models])
            selected = int(np.argmin(values))
            winning_models.add(models[selected])
            offset = (series - 1) * .32
            positions = y + offset
            sizes = [20 if i == selected else 10 for i in range(len(models))]
            edges = ['#243B4B' if i == selected else PALETTE[series] for i in range(len(models))]
            scatter = ax.scatter(values, positions, s=sizes, c=PALETTE[series], marker=MARKERS[series],
                                 edgecolors=edges, linewidths=[.65 if i == selected else .25 for i in range(len(models))],
                                 zorder=3)
            assert np.array_equal(np.asarray(scatter.get_offsets())[:, 0], values)
            assert np.array_equal(np.asarray(scatter.get_offsets())[:, 1], positions)
            max_mae = max(max_mae, float(values.max()))
            for index, model in enumerate(models):
                row = frame.loc[model]
                records.append({'regime': regime, 'tarefa': task, 'modelo': model, 'modelo_exibido': model_label(model),
                                'variante': str(row.variante), 'horizonte': horizon, 'MAE_wm2': float(values[index]),
                                'menor_MAE_conjunto': index == selected, 'posicao_y': float(positions[index]),
                                'cor': PALETTE[series], 'simbolo': MARKERS[series]})
        ax.set_yticks(y, [model_label(model) for model in models], fontsize=8.2)
        for tick, model in zip(ax.get_yticklabels(), models, strict=True):
            if model in winning_models:
                tick.set_fontweight('bold')
        ax.set_ylim(len(models) - .25, -.75)
        ax.set_xlim(0, max_mae * 1.08)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=3))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, pos: f'{value:g}'.replace('.', ',')))
        ax.set_xlabel('MAE (W/m²)', fontsize=8.5, labelpad=3)
        ax.set_title(task_labels[task], loc='left', fontsize=10, fontweight='bold', color='#243B4B', pad=8)
        ax.tick_params(axis='y', length=0, pad=5)
        ax.tick_params(axis='x', labelsize=8.2, colors='#526574', length=3)
        ax.grid(axis='x', color='#DCE2E7', linewidth=.55, zorder=0)
        for spine in ('top', 'right'):
            ax.spines[spine].set_visible(False)
        for spine in ('bottom', 'left'):
            ax.spines[spine].set_color('#BBC7D0')
            ax.spines[spine].set_linewidth(.5)
        panels.append({'tarefa': task, 'horizonte': horizon, 'modelos': models, 'eixo_x': list(ax.get_xlim()),
                       'menores_MAE': sorted(winning_models), 'escala': 'linear, inicio em zero'})
    handles = [Line2D([], [], linestyle='none', marker=marker, markersize=4.5, color=color, label=label)
               for marker, color, label in zip(MARKERS, PALETTE, LABELS, strict=True)]
    handles.append(Line2D([], [], linestyle='none', marker='o', markersize=5.5, markerfacecolor='white',
                          markeredgecolor='#243B4B', markeredgewidth=.8, label='Contorno: menor MAE do conjunto'))
    fig.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, .988), ncol=4,
               frameon=False, fontsize=8.2, handletextpad=.5, columnspacing=1.25, borderaxespad=0)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_bbox = fig.bbox
    artist_bounds = [ax.get_tightbbox(renderer) for ax in axes.flat] + [legend.get_window_extent(renderer) for legend in fig.legends]
    assert all(box.x0 >= -.5 and box.y0 >= -.5 and box.x1 <= figure_bbox.x1 + .5 and box.y1 <= figure_bbox.y1 + .5
               for box in artist_bounds), 'Rotulo fora da figura'
    assert len(records) == 132 and sum(row['menor_MAE_conjunto'] for row in records) == 12
    paths = {kind: directory / f'mae_modelos_por_tarefa.{kind}' for kind in ('pdf', 'svg', 'png')}
    fig.savefig(paths['pdf'], facecolor='white', metadata={'Title': 'MAE dos modelos por tarefa e conjunto',
                                                         'Author': 'Gustavo de Melo Nascimento'})
    fig.savefig(paths['svg'], facecolor='white')
    fig.savefig(paths['png'], facecolor='white', dpi=320)
    plt.close(fig)
    record = {'pontos': records, 'paineis': panels, 'total_pontos': 132, 'menores_MAE_destacados': 12,
              'criterio': 'MAE no teste da condicao escolhida na validacao; horizonte completo.',
              'ordem_modelos': 'alfabetica, mesma em todos os paineis',
              'largura_pt': width_points, 'altura_pt': height_points,
              'arquivos': {kind: str(path) for kind, path in paths.items()}}
    (directory / 'dados_grafico.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record
