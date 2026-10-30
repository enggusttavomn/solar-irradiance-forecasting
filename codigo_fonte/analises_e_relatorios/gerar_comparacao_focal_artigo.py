"""Rebuild focused manuscript tables and seven-day profiles from saved test forecasts.

This script never fits a model or modifies the source experiment artifacts.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'resultados/artigo_revista_unificado/artefatos_resultados_corrigidos_FINAL'
EXPERIMENT = ROOT / 'resultados/avaliacao_multirresolucao_corrigida_v2'
OUTPUT = ROOT / 'resultados/artigo_revista_unificado/revisao_20260907'
ARTICLE = ROOT / 'artigos/revista_unificado'
TASKS = [('hourly_72_extension','Hourly 336--72', 'h'), ('daily_30','Daily 365--30', 'd'),
         ('monthly_1','Monthly 12--1','mo'), ('monthly_6','Monthly 12--6','mo')]
COLORS = {'TimesNet':'#0072B2', 'DilatedRNN':'#D55E00'}


def select_week(predictions: pd.DataFrame, site: str, event_date: str) -> pd.DataFrame:
    """Use only leads 1--24 of seven distinct daily issuances, once per target."""
    event = pd.Timestamp(event_date)
    start, end = event - pd.Timedelta(days=3), event + pd.Timedelta(days=4)
    data = predictions.loc[(predictions.localidade == site) &
        (predictions.passo_h <= 24) &
        (predictions.timestamp_alvo_local_fixo >= start) &
        (predictions.timestamp_alvo_local_fixo < end)].copy()
    data = data.sort_values('timestamp_alvo_local_fixo').reset_index(drop=True)
    expected = pd.date_range(start, periods=168, freq='h')
    if len(data) != 168 or not np.array_equal(data.timestamp_alvo_local_fixo.to_numpy(), expected.to_numpy()):
        raise ValueError(f'Incomplete or duplicated seven-day profile: {site}')
    origins = data.origem_local_fixa
    targets = data.timestamp_alvo_local_fixo
    if origins.nunique() != 7 or not origins.eq(targets.dt.normalize()).all():
        raise ValueError(f'Profile must contain seven daily midnight issuances: {site}')
    if not data.passo_h.eq(targets.dt.hour + 1).all():
        raise ValueError('Inconsistent hourly lead indexing')
    return data


def format_supporting_tables() -> None:
    """Reformat archived tables; never alter their numeric values."""
    import re
    specifications = {
        'metricas_terminais.tex': (
            r'Task & Horizon & Model & MAE & RMSE & nRMSE (\%) & $R^2$',
            r'Terminal cumulative metrics for TimesNet and DilatedRNN. MAE and RMSE are in W/m$^2$; nRMSE is reported as a percentage.'),
        'comparacao_timesnet_dilatedrnn_resumo.tex': (
            r'Task & Horizon & Sites & Mean $\Delta$ & Median $\Delta$ & TN wins & DR wins & Ties',
            r'Descriptive site-paired cumulative comparison. $\Delta=\mathrm{MAE}_{\mathrm{TimesNet}}-\mathrm{MAE}_{\mathrm{DilatedRNN}}$ in W/m$^2$; negative values favor TimesNet (TN), positive values favor DilatedRNN (DR). Wins count sites, not forecast origins. Overlapping multi-step targets are not independent observations.')}
    for name, (header, caption) in specifications.items():
        text = (SOURCE / name).read_text(encoding='utf-8-sig')
        text = text.replace(r'\resizebox{\textwidth}{!}{%', r'\setlength{\tabcolsep}{5pt}')
        text = text.replace('\\end{tabular}%\n}', r'\end{tabular}')
        if name == 'metricas_terminais.tex':
            text = text.replace('{lrrrrrr}', '{ll l rrrr}')
        text = re.sub(r'(?m)^Task &.*$', lambda _: header + ' ' + r'\\', text)
        text = re.sub(r'(?m)^\\caption\{.*$', lambda _: r'\caption{' + caption + '}', text)
        head, remainder = text.split(r'\midrule', 1)
        body, tail = remainder.split(r'\bottomrule', 1)
        records = [line.strip() for line in body.splitlines() if '&' in line]
        if name.startswith('comparacao'):
            order = {'Hourly': 0, 'Daily': 1, 'Monthly': 2}
            records.sort(key=lambda row: (order[row.split()[0]], 0 if '12--1' in row else 1, int(row.split('&')[1])))
        output, last = [], None
        for line in records:
            cells = line.split('&'); task = cells[0].strip()
            if last is not None and task != last:
                output.append(r'\addlinespace')
            unit = 'h' if task.startswith('Hourly') else 'd' if task.startswith('Daily') else 'mo'
            cells[1] = ' ' + cells[1].strip() + ' ' + unit + ' '
            output.append('&'.join(cells)); last = task
        rendered = head + r'\midrule' + '\n' + '\n'.join(output) + '\n' + r'\bottomrule' + tail
        if name.startswith('comparacao'):
            rendered = rendered.replace(r'\begin{tabular}{lrrrrrrr}', r'\begin{tabular*}{\textwidth}{@{\extracolsep{\fill}}llrrrrrr@{}}')
            rendered = rendered.replace(r'\end{tabular}', r'\end{tabular*}')
        (ARTICLE / 'tables' / name).write_text(rendered, encoding='utf-8', newline='\n')
        (OUTPUT / name).write_text(rendered, encoding='utf-8', newline='\n')


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    format_supporting_tables()
    macro = pd.read_csv(SOURCE / 'desempenho_macro.csv')
    focus = macro[(macro.tipo_horizonte == 'cumulativo') & macro.modelo.isin(COLORS)].copy()
    rows = []
    for task, label, unit in TASKS:
        frame = focus[focus.tarefa == task]
        for horizon, group in frame.groupby('horizonte', sort=True):
            vals = group.set_index('modelo').MAE_wm2
            if len(group) != 2 or set(vals.index) != set(COLORS):
                raise ValueError('Each checkpoint needs exactly one estimate per architecture')
            tn, dr = float(vals['TimesNet']), float(vals['DilatedRNN'])
            rows.append(dict(tarefa=task, label=label, horizonte=int(horizon), unidade=unit,
                MAE_TimesNet=tn, MAE_DilatedRNN=dr, delta_TimesNet_menos_DilatedRNN=tn-dr,
                vencedor='TimesNet' if tn < dr else 'DilatedRNN' if dr < tn else 'Tie'))
    table = pd.DataFrame(rows)
    table.to_csv(OUTPUT / 'vencedores_por_horizonte.csv', index=False)
    lines = [r'\begin{table*}[!t]',r'\centering',
        r'\caption{Focused architecture comparison: cumulative test macro-MAE in W/m$^2$. Bold marks the lower unrounded MAE within each row. $\Delta=\mathrm{MAE}_{\mathrm{TimesNet}}-\mathrm{MAE}_{\mathrm{DilatedRNN}}$ is computed before rounding. Hourly estimates use seed 42; daily and monthly estimates use five-seed ensembles. Table~\ref{tab:benchmark_adicional_mae} reports the complete reference benchmark.}',
        r'\label{tab:architecture_winners}', r'\small',r'\setlength{\tabcolsep}{5pt}',
        r'\begin{tabular}{llrrrl}',r'\toprule',
        r'Task & Cumulative horizon & TimesNet & DilatedRNN & $\Delta$ & Lower MAE \\',r'\midrule']
    previous = None
    for row in rows:
        if previous is not None and previous != row['tarefa']:
            lines.append(r'\addlinespace')
        cells = []
        for name in COLORS:
            val = f"{row['MAE_'+name]:.2f}"
            if row['vencedor'] == name:
                val = r'\textbf{' + val + '}'
            cells.append(val)
        lines.append(f"{row['label']} & {row['horizonte']} {row['unidade']} & " +
            ' & '.join(cells) + f" & {row['delta_TimesNet_menos_DilatedRNN']:+.2f} & {row['vencedor']} " + r'\\')
        previous = row['tarefa']
    lines.extend([r'\bottomrule',r'\end{tabular}',r'\end{table*}'])
    (OUTPUT / 'vencedores_por_horizonte.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (ARTICLE / 'tables/vencedores_por_horizonte.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')

    hourly_path = EXPERIMENT / 'hourly_72_extension/previsoes_teste.csv.gz'
    cols = ['localidade','semente','origem_local_fixa','timestamp_alvo_local_fixo','passo_h',
            'ghi_real_wm2','previsao_pos_timesnet_wm2','previsao_pos_dilatedrnn_wm2']
    predictions = pd.read_csv(hourly_path, usecols=cols,
        parse_dates=['origem_local_fixa','timestamp_alvo_local_fixo'])
    if set(predictions.semente.unique()) != {42}:
        raise ValueError('Unexpected hourly seed contract')
    cases = [('GM Factory Zero','2024-03-31','Largest selected 24 h TimesNet gain'),
             ('Tesla Gigafactory Texas','2024-03-28','Largest selected 24 h TimesNet deficit'),
             ('Hyundai Metaplant Georgia','2024-08-05','Error-independent weather event')]
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8.5,'axes.spines.top':False,
                         'axes.spines.right':False,'savefig.facecolor':'white'})
    fig, axes = plt.subplots(3,1,figsize=(7.2,6.0),sharey=True,layout='constrained')
    fig.suptitle('Seven daily 24 h forecast prefixes per site (seed 42)', fontsize=9, fontweight='bold')
    profile_rows, errors = [], []
    for i,(ax,(site,event_date,reason)) in enumerate(zip(axes,cases)):
        data = select_week(predictions,site,event_date)
        x,y = data.timestamp_alvo_local_fixo,data.ghi_real_wm2
        ax.plot(x,y,color='#202020',lw=1.5,label='NSRDB reference',zorder=3)
        tn = data.previsao_pos_timesnet_wm2
        dr = data.previsao_pos_dilatedrnn_wm2
        ax.plot(x,tn,color=COLORS['TimesNet'],lw=1.35,ls='--',label='TimesNet',zorder=2)
        ax.plot(x,dr,color=COLORS['DilatedRNN'],lw=1.35,ls='-.',label='DilatedRNN',zorder=2)
        mae_tn,mae_dr = float(np.mean(np.abs(y-tn))),float(np.mean(np.abs(y-dr)))
        ax.set_title(f"({chr(97+i)}) {site}",loc='left',fontweight='bold',fontsize=9)
        ax.text(0.99,0.95,f"7-day MAE: TimesNet {mae_tn:.2f} | DilatedRNN {mae_dr:.2f} W/m²",
                transform=ax.transAxes,ha='right',va='top',fontsize=7.7,
                bbox=dict(facecolor='white',edgecolor='none',alpha=0.9,pad=2))
        event = pd.Timestamp(event_date)
        ax.axvspan(event,event+pd.Timedelta(days=1),color='#BDBDBD',alpha=0.24,zorder=0)
        ax.set_xlim(x.iloc[0],x.iloc[-1]+pd.Timedelta(hours=1))
        ax.set_ylim(0,1180)
        ax.set_yticks([0,300,600,900])
        ax.xaxis.set_major_locator(mdates.DayLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%d %b'))
        ax.grid(axis='y',alpha=0.2)
        ax.grid(axis='x',alpha=0.15)
        ax.set_ylabel('GHI (W/m²)')
        if i == 0:
            fig.legend(*ax.get_legend_handles_labels(),loc='outside lower center',ncol=3,frameon=False,fontsize=8.5)
        if i == 2:
            ax.set_xlabel('2024 fixed local date; shading marks the selected event')
        data['data_evento'] = event_date
        data['regra_janela'] = 'three_days_before_to_three_days_after; daily_24h_prefixes'
        profile_rows.append(data)
        errors.append(dict(localidade=site,data_evento=event_date,N_pontos=len(data),N_origens=7,
            horizonte_por_origem_h=24,inicio=str(x.iloc[0]),fim=str(x.iloc[-1]),
            MAE_TimesNet=mae_tn,MAE_DilatedRNN=mae_dr))
    # Keep local PDF exports in OUTPUT; publish only PNG/SVG article assets.
    for suffix in ('png','pdf','svg'):
        target=OUTPUT/f'perfis_sete_dias.{suffix}'
        fig.savefig(target,dpi=300,bbox_inches='tight')
        if suffix == 'svg':
            target.write_text('\n'.join(line.rstrip() for line in target.read_text(encoding='utf-8').splitlines()) + '\n', encoding='utf-8')
        if suffix in ('png', 'svg'):
            (ARTICLE/'figures'/target.name).write_bytes(target.read_bytes())
    plt.close(fig)
    pd.concat(profile_rows,ignore_index=True).to_csv(OUTPUT/'perfis_sete_dias.csv',index=False)
    pd.DataFrame(errors).to_csv(OUTPUT/'metricas_perfis_sete_dias.csv',index=False)

    # Figure 4 (variabilidade_arquiteturas) now comes from
    # codigo_fonte.analises_e_relatorios.gerar_figuras_benchmark_completo, drawn exactly like Figure S2.
    sources = [SOURCE/'desempenho_macro.csv', SOURCE/'variabilidade_sementes.csv',
               SOURCE/'metricas_terminais.tex', SOURCE/'comparacao_timesnet_dilatedrnn_resumo.tex',
               hourly_path, Path(__file__), ROOT/'codigo_fonte/publicacoes/artefatos_artigo_unificado.py']
    manifest=dict(description='Derived display artifacts; no retraining; complete benchmarks preserved.',
        weekly_profile_rule='seven days centered on each previously selected event; leads 1..24 from seven midnight origins',
        independent_verification='verificacao_tabelas.json is an independent audit record retained and hashed when present; this generator does not regenerate it.',
        inputs={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        outputs={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(OUTPUT.iterdir()) if p.is_file() and p.name!='manifesto_revisao.json'})
    (OUTPUT/'manifesto_revisao.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(table.to_string(index=False))
    print(pd.DataFrame(errors).to_string(index=False))

if __name__ == '__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    main()
