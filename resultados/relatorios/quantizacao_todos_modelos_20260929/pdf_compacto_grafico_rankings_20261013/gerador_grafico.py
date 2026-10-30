"""Rankings vetoriais dos cinco menores MAEs por tarefa."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np

from scripts.metricas_quantizacao_todos import TAREFAS

REGIMES = ('atual', 'historico_1998_2022', 'historico_curto_pareado')
PANEL_TITLES = ('Horário - 72 h', 'Diário - 30 dias', 'Mensal - 1 mês', 'Mensal - 6 meses')
INK, MUTED, BEST = '#243B4B', '#728B9D', '#218A8A'


def create_mae_figure(data, directory, width_points, height_points, model_label, task_labels, regime='atual'):
    if regime not in REGIMES:
        raise ValueError('Conjunto desconhecido para o gráfico.')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    font_manager.fontManager.addfont('C:/Windows/Fonts/arial.ttf')
    font_manager.fontManager.addfont('C:/Windows/Fonts/arialbd.ttf')
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 9.5, 'pdf.fonttype': 42,
                         'svg.fonttype': 'none', 'axes.unicode_minus': False})
    fig = plt.figure(figsize=(width_points / 72, height_points / 72), dpi=150)
    records, panels, axes, texts = [], [], [], []
    for index, task in enumerate(TAREFAS):
        column, row = index % 2, index // 2
        left, bottom = column * .51, .625 - row * .485
        ax = fig.add_axes([left + .146, bottom, .236, .282])
        axes.append(ax)
        frame = data.rank(regime, task).head(5).reset_index(drop=True)
        values = frame.MAE_wm2.to_numpy(dtype=float)
        assert len(frame) == 5 and np.all(np.diff(values) >= 0)
        low, high = float(values.min()), float(values.max())
        margin = max((high - low) * .13, .08)
        ax.set_xlim(max(0, low - margin), high + margin)
        ax.set_ylim(4.55, -.55)
        colors = [BEST] + [MUTED] * 4
        dots = ax.scatter(values, np.arange(5), s=[58] + [34] * 4, c=colors,
                          edgecolors='white', linewidths=.6, zorder=3)
        assert np.array_equal(np.asarray(dots.get_offsets())[:, 0], values)
        assert np.array_equal(np.asarray(dots.get_offsets())[:, 1], np.arange(5))
        for y in range(5):
            ax.axhline(y, color='#EFF2F5', linewidth=.65, zorder=0)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, pos: f'{value:.2f}'.replace('.', ',')))
        ax.set_xlabel('MAE (W/m²)', fontsize=9.2, labelpad=5, color=INK)
        ax.set_yticks([])
        ax.tick_params(axis='x', labelsize=9, colors='#526574', length=3, pad=4)
        ax.grid(axis='x', color='#DFE5EA', linewidth=.6, zorder=0)
        for spine in ('top', 'right', 'left'):
            ax.spines[spine].set_visible(False)
        ax.spines['bottom'].set_color('#BBC7D0')
        ax.spines['bottom'].set_linewidth(.65)
        title_y = .988 - row * .485
        header_y = .94 - row * .485
        texts.append(fig.text(left + .004, title_y, PANEL_TITLES[index], fontsize=11,
                              fontweight='bold', color=INK, ha='left', va='top'))
        texts.append(fig.text(left + .004, header_y, 'Modelo', fontsize=8.8, color='#526574', va='center'))
        texts.append(fig.text(left + .485, header_y, 'MAE (W/m²)', fontsize=8.8, color='#526574',
                              ha='right', va='center'))
        for position, record in enumerate(frame.to_dict('records'), 1):
            model = str(record['modelo'])
            value = float(record['MAE_wm2'])
            y_fig = bottom + .282 * (4.55 - (position - 1)) / 5.1
            color = BEST if position == 1 else INK
            weight = 'bold' if position == 1 else 'normal'
            texts.append(fig.text(left + .004, y_fig, f'{position}. {model_label(model)}',
                                  fontsize=10, color=color, fontweight=weight, va='center'))
            texts.append(fig.text(left + .485, y_fig, f'{value:.4f}'.replace('.', ','),
                                  fontsize=10, color=color, fontweight=weight, va='center', ha='right'))
            records.append({'regime': regime, 'tarefa': task, 'modelo': model,
                            'modelo_exibido': model_label(model), 'variante': str(record['variante']),
                            'horizonte': max(TAREFAS[task]), 'MAE_wm2': value, 'posicao': position,
                            'menor_MAE_conjunto': position == 1, 'posicao_x': value,
                            'posicao_y': position - 1, 'cor': colors[position - 1]})
        panels.append({'tarefa': task, 'horizonte': max(TAREFAS[task]),
                       'modelos': frame.modelo.tolist(), 'eixo_x': list(ax.get_xlim()),
                       'escala_x': 'linear; intervalo próprio', 'ordem_mae_crescente': True})
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    figure_bbox = fig.bbox
    artist_bounds = [ax.get_tightbbox(renderer) for ax in axes] + [t.get_window_extent(renderer) for t in texts]
    assert all(box.x0 >= -.5 and box.y0 >= -.5 and box.x1 <= figure_bbox.x1 + .5 and box.y1 <= figure_bbox.y1 + .5
               for box in artist_bounds), 'Rótulo fora da figura'
    assert len(records) == 20 and len(panels) == 4
    assert sum(record['menor_MAE_conjunto'] for record in records) == 4
    paths = {kind: directory / f'mae_cinco_menores_por_tarefa.{kind}' for kind in ('pdf', 'svg', 'png')}
    fig.savefig(paths['pdf'], facecolor='white', metadata={'Title': 'Cinco menores MAEs por tarefa',
                                                         'Author': 'Gustavo de Melo Nascimento'})
    fig.savefig(paths['svg'], facecolor='white')
    fig.savefig(paths['png'], facecolor='white', dpi=320)
    plt.close(fig)
    record = {'regime': regime, 'tipo': 'quatro rankings de pontos horizontais',
              'pontos': records, 'paineis': panels, 'total_pontos': 20, 'menores_MAE_destacados': 4,
              'criterio': 'Cinco menores MAEs observados no teste por tarefa, com condição escolhida na validação.',
              'interpretacao': 'Escalas próprias mostram diferenças dentro de cada tarefa. Os onze modelos constam nas tabelas.',
              'largura_pt': width_points, 'altura_pt': height_points,
              'arquivos': {kind: str(path) for kind, path in paths.items()}}
    (directory / 'dados_grafico.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    return record
