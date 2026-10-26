"""Figura vetorial do MAE entre as quatro tarefas de previsão."""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

from scripts.metricas_quantizacao_todos import MODELOS, TAREFAS

REGIMES = ('atual', 'historico_1998_2022', 'historico_curto_pareado')
TASK_TICKS = ('Horário\n72 h', 'Diário\n30 dias', 'Mensal\n1 mês', 'Mensal\n6 meses')
STYLES = {
    'TimesNet': ('#204E79', 'o', '-'),
    'XGBoost': ('#E58B25', 's', '--'),
    'LSTM': ('#8064A2', '^', '-.'),
    'DilatedRNN': ('#488D45', 'd', ':'),
    'GRU': ('#B4558D', 'v', '--'),
    'Transformer': ('#8C644F', '<', '-.'),
    'Informer': ('#C64A4A', 'P', '-'),
    'ARIMA': ('#747C84', 'X', '-.'),
    'Persistencia': ('#B86625', '*', '-'),
    'Sazonal ingenuo': ('#9A942F', 'h', '--'),
    'Climatologia': ('#218A8A', 'D', '-'),
}

def create_mae_figure(data, directory, width_points, height_points, model_label, task_labels, regime='atual'):
    if regime not in REGIMES:
        raise ValueError('Conjunto desconhecido para o gráfico.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    font_manager.fontManager.addfont('C:/Windows/Fonts/arial.ttf')
    font_manager.fontManager.addfont('C:/Windows/Fonts/arialbd.ttf')
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 9.5, 'pdf.fonttype': 42,
                         'svg.fonttype': 'none', 'axes.unicode_minus': False})
    fig, ax = plt.subplots(figsize=(width_points / 72, height_points / 72), dpi=150)
    fig.subplots_adjust(left=.080, right=.772, bottom=.155, top=.973)
    tasks = list(TAREFAS)
    models = list(MODELOS)
    x = np.arange(len(tasks), dtype=float)
    frames = {task: data.rank(regime, task).set_index('modelo') for task in tasks}
    winners = {task: str(data.rank(regime, task).iloc[0].modelo) for task in tasks}
    records, series = [], []
    max_mae = 0.0
    for model in models:
        color, marker, linestyle = STYLES[model]
        values = np.array([float(frames[task].loc[model, 'MAE_wm2']) for task in tasks])
        assert np.all(np.isfinite(values)) and np.all(values >= 0)
        winner = model in winners.values()
        line, = ax.plot(x, values, color=color, marker=marker, linestyle=linestyle,
                        linewidth=1.85 if winner else 1.25, markersize=5.5,
                        markeredgewidth=.55, label=model_label(model), zorder=4 if winner else 3)
        assert np.array_equal(line.get_xdata(), x)
        assert np.array_equal(line.get_ydata(), values)
        max_mae = max(max_mae, float(values.max()))
        model_records = []
        for index, task in enumerate(tasks):
            row = frames[task].loc[model]
            record = {'regime': regime, 'tarefa': task, 'modelo': model, 'modelo_exibido': model_label(model),
                      'variante': str(row.variante), 'horizonte': max(TAREFAS[task]),
                      'MAE_wm2': float(values[index]), 'menor_MAE_conjunto': winners[task] == model,
                      'posicao_x': float(x[index]), 'posicao_y': float(values[index]),
                      'cor': color, 'simbolo': marker, 'estilo_linha': linestyle}
            records.append(record)
            model_records.append(record)
        series.append({'modelo': model, 'cor': color, 'simbolo': marker, 'estilo_linha': linestyle,
                       'pontos': model_records})
    ax.set_xticks(x, TASK_TICKS, fontsize=10)
    ax.set_xlim(-.15, 3.15)
    ax.set_ylim(0, math.ceil(max_mae * 1.065 / 10) * 10)
    ax.set_xlabel('Tarefa de previsão', fontsize=10, labelpad=10, color='#243B4B')
    ax.set_ylabel('MAE (W/m²)', fontsize=10, labelpad=8, color='#243B4B')
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8, min_n_ticks=5))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, pos: f'{value:g}'.replace('.', ',')))
    ax.tick_params(axis='x', colors='#243B4B', length=3, pad=7)
    ax.tick_params(axis='y', colors='#526574', length=3)
    ax.grid(axis='y', color='#DCE2E7', linewidth=.65, zorder=0)
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('bottom', 'left'):
        ax.spines[spine].set_color('#BBC7D0')
        ax.spines[spine].set_linewidth(.65)
    legend = ax.legend(loc='center left', bbox_to_anchor=(1.018, .5), frameon=False,
                       title='Modelos', title_fontsize=10, fontsize=9.5, handlelength=2.5,
                       handletextpad=.8, labelspacing=1.05, borderaxespad=0)
    legend.get_title().set_color('#243B4B')
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_bbox = fig.bbox
    artist_bounds = [ax.get_tightbbox(renderer), legend.get_window_extent(renderer)]
    assert all(box.x0 >= -.5 and box.y0 >= -.5 and box.x1 <= figure_bbox.x1 + .5 and box.y1 <= figure_bbox.y1 + .5
               for box in artist_bounds), 'Rótulo fora da figura'
    assert len(records) == 44 and len(series) == 11
    assert sum(row['menor_MAE_conjunto'] for row in records) == 4
    paths = {kind: directory / f'mae_modelos_quatro_tarefas.{kind}' for kind in ('pdf', 'svg', 'png')}
    fig.savefig(paths['pdf'], facecolor='white', metadata={'Title': 'MAE dos modelos entre as quatro tarefas',
                                                         'Author': 'Gustavo de Melo Nascimento'})
    fig.savefig(paths['svg'], facecolor='white')
    fig.savefig(paths['png'], facecolor='white', dpi=320)
    plt.close(fig)
    record = {'regime': regime, 'pontos': records, 'series': series, 'total_series': 11,
              'total_pontos': 44, 'menores_MAE_destacados': 4,
              'paineis': [{'ordem_tarefas': tasks, 'rotulos_tarefas': list(TASK_TICKS),
                           'eixo_x': list(ax.get_xlim()), 'eixo_y': list(ax.get_ylim()),
                           'escala_y': 'linear, início em zero', 'eixo_x_categorico': True}],
              'criterio': 'MAE no teste da condição escolhida na validação; horizonte completo.',
              'interpretacao': 'As linhas conectam tarefas com resoluções distintas, sem isolar o efeito do horizonte.',
              'ordem_modelos': models, 'largura_pt': width_points, 'altura_pt': height_points,
              'arquivos': {kind: str(path) for kind, path in paths.items()}}
    (directory / 'dados_grafico.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record
