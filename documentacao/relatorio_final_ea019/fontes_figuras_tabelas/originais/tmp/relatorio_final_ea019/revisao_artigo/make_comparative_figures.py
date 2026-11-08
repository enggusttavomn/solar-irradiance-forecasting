from pathlib import Path
from html import escape
import json
import math
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent / 'figuras_comparativas'
OUT.mkdir(parents=True, exist_ok=True)
BASE = ROOT / 'resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina'
D = pd.read_csv(BASE / 'metricas_teste_modelos_disciplina.csv')
R = pd.read_csv(BASE / 'classificacoes_modelos_disciplina.csv')
MODELS = ['Transformer', 'Informer', 'LSTM']
COL = {'Transformer': '#245680', 'Informer': '#B65B35', 'LSTM': '#35776C'}
TASKS = [('hourly_72_extension', 72, 'Horária 1–72 h'), ('daily_30', 30, 'Diária 1–30 dias'),
         ('monthly_1', 1, 'Mensal 1 passo'), ('monthly_6', 6, 'Mensal 1–6 passos · exploratório')]

def fmt(v, n=2):
    return f'{float(v):.{n}f}'.replace('.', ',')

def text(x, y, s, size=25, anchor='start', fill='#20262B', weight='normal', rotate=None):
    transform = f' transform="rotate({rotate} {x} {y})"' if rotate else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}"{transform}>{escape(str(s))}</text>'

def line(x1, y1, x2, y2, stroke='#DCE1E5', width=1.5, dash=''):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}" stroke-dasharray="{dash}"/>'

def rect(x, y, w, h, fill='#FFF', stroke='none', width=1.5, radius=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{width}" rx="{radius}"/>'

def circle(x, y, r, fill, stroke='none', width=2.5):
    return f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{width}"/>'

def save(name, body, height):
    (OUT / (name + '.svg')).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{height}" viewBox="0 0 1200 {height}">'
        f'<rect width="1200" height="{height}" fill="white"/><g font-family="Arial,sans-serif">{body}</g></svg>', encoding='utf-8')

def chosen(reg, task, model):
    z = R[(R.regime == reg) & (R.tarefa == task) & (R.modelo == model)]
    assert len(z) == 1
    return z.iloc[0]

def row(reg, task, model, horizon, variant):
    z = D[(D.regime == reg) & (D.tarefa == task) & (D.modelo == model) & (D.horizonte == horizon) & (D.variante == variant)]
    assert len(z) == 1
    return z.iloc[0]

def nice_top(v):
    base = 10 ** math.floor(math.log10(v))
    return next(n * base for n in [1, 2, 4, 6, 8, 10] if n * base >= v)

audit = {'ranking': [], 'quantizacao_atual': [], 'historico_pareado': [], 'horizontes': []}

# Ranking panels: rank always determined by the test MAE of each validation-frozen choice.
b = ''
for k, (t, H, label) in enumerate(TASKS):
    px, py = (k % 2) * 600, (k // 2) * 360
    title = label.replace(' · exploratório', '')
    b += text(px + 20, py + 34, f'{chr(65+k)}  {title}', 27, weight='bold')
    if H == 6:
        b += text(px + 20, py + 63, 'Exploratório', 22, fill='#666')
    vals = sorted([(m, chosen('atual', t, m)) for m in MODELS], key=lambda z: z[1].MAE_wm2)
    top = nice_top(max(float(z.MAE_wm2) for _, z in vals) * 1.23)
    x, w = px + 190, 380
    for tick in [0, top / 4, top / 2, 3 * top / 4, top]:
        xx = x + tick / top * w
        b += line(xx, py + 84, xx, py + 276) + text(xx, py + 305, fmt(tick, 0), 22, 'middle', '#5A6268')
    for rank, (m, z) in enumerate(vals, 1):
        y = py + 102 + (rank-1) * 66
        bw = float(z.MAE_wm2) / top * w
        b += text(px + 20, y + 23, str(rank), 23, fill=COL[m], weight='bold')
        b += text(px + 48, y + 23, m, 23, weight='bold' if rank == 1 else 'normal')
        b += rect(x, y, bw, 31, COL[m], radius=2)
        b += text(x + bw + 10, y + 24, fmt(z.MAE_wm2), 23, weight='bold' if rank == 1 else 'normal')
        audit['ranking'].append({'tarefa': t, 'modelo': m, 'variante': z.variante, 'mae': float(z.MAE_wm2), 'posicao': rank})
    b += text(px + 380, py + 340, 'MAE (W/m²) · menor é melhor', 22, 'middle', '#5A6268')
b += text(20, 758, 'Teste de 2024 · escolhas definidas na validação · escala própria em cada painel', 24, fill='#4E575E')
save('04_mae_atual', b, 785)

# Matrix: show continuous choice explicitly as well as the three quantization effects.
b = text(20, 36, 'Variação do MAE de teste em relação à entrada contínua', 28, weight='bold')
b += text(20, 70, 'Verde: menor erro  ·  laranja: maior erro  ·  ★ escolha na validação', 24, fill='#4E575E')
headers = [(20, 'Modelo'), (240, 'Validação'), (580, '64 níveis'), (810, '128 níveis'), (1040, '256 níveis')]
for x, s in headers:
    b += text(x, 119, s, 24, 'middle' if x > 400 else 'start', weight='bold')
for k, (t, H, label) in enumerate(TASKS):
    y0 = 147 + k * 219
    b += rect(10, y0 - 6, 1170, 35, '#F1F4F6')
    b += text(20, y0 + 19, label, 24, weight='bold')
    for j, m in enumerate(MODELS):
        y = y0 + 42 + j * 52
        v0 = float(row('atual', t, m, H, 'sem_quantizacao').MAE_wm2)
        qsel = chosen('atual', t, m).variante
        b += text(20, y + 29, m, 24, fill=COL[m], weight='bold')
        selection = 'Controle ★' if qsel == 'sem_quantizacao' else qsel[1:] + ' níveis'
        b += text(240, y + 29, selection, 24)
        for c, q in enumerate(['q64', 'q128', 'q256']):
            delta = (float(row('atual', t, m, H, q).MAE_wm2) / v0 - 1) * 100
            a = min(abs(delta) / 10, 1)
            color = (int(248-74*a), int(249-36*a), int(248-57*a)) if delta < 0 else (249, int(249-70*a), int(248-104*a))
            fill = '#%02x%02x%02x' % color
            x = 470 + c * 230
            b += rect(x, y, 220, 43, fill, '#64727D' if qsel == q else '#FFF', 2.2 if qsel == q else 1)
            value = ('★ ' if qsel == q else '') + ('+' if delta > 0 else '') + fmt(delta) + '%'
            b += text(x + 110, y + 29, value, 24, 'middle', weight='bold' if qsel == q else 'normal')
            audit['quantizacao_atual'].append({'tarefa': t, 'modelo': m, 'variante': q, 'delta_pct': delta, 'selecionado': qsel == q})
b += text(20, 1052, 'Δ = 100 × (MAE quantizado / MAE controle − 1). As células descrevem o teste.', 24, fill='#4E575E')
b += text(20, 1086, 'Intensidade de cor saturada em |Δ| ≥ 10%; valores exatos indicados em cada célula.', 23, fill='#4E575E')
save('05_quantizacao', b, 1110)

# Paired-history dumbbells: numeric MAEs make absolute and relative changes reviewable.
b = ''
for k, (t, H, label) in enumerate(TASKS):
    px, py = (k % 2) * 600, (k // 2) * 420
    b += text(px + 20, py + 34, f'{chr(65+k)}  {label.replace(" · exploratório", "")}', 27, weight='bold')
    b += text(px + 20, py + 69, 'MAE curto → longo', 22, fill='#5A6268')
    b += text(px + 575, py + 69, 'Δ longo', 22, 'end', '#5A6268')
    vals = []
    for m in MODELS:
        a = float(row('historico_curto_pareado', t, m, H, 'sem_quantizacao').MAE_wm2)
        c = float(row('historico_1998_2022', t, m, H, 'sem_quantizacao').MAE_wm2)
        vals.append((m, a, c, (c/a-1)*100))
    top = nice_top(max(max(a, c) for _, a, c, _ in vals) * 1.12)
    x, w = px + 70, 470
    for tick in [0, top/4, top/2, 3*top/4, top]:
        xx = x + tick / top * w
        b += line(xx, py + 112, xx, py + 337) + text(xx, py + 367, fmt(tick, 0), 22, 'middle', '#5A6268')
    for j, (m, a, c, delta) in enumerate(vals):
        y = py + 99 + j*82
        b += text(px + 20, y + 11, m, 23, fill=COL[m], weight='bold')
        b += text(px + 205, y + 11, fmt(a) + ' → ' + fmt(c), 23)
        b += text(px + 575, y + 11, ('+' if delta > 0 else '') + fmt(delta) + '%', 23, 'end', '#B65B35' if delta > 0 else '#35776C')
        xa, xc, yy = x + a/top*w, x + c/top*w, y + 40
        b += line(xa, yy, xc, yy, COL[m], 4)
        b += circle(xa, yy, 8, '#FFF', COL[m], 3) + circle(xc, yy, 8, COL[m])
        audit['historico_pareado'].append({'tarefa': t, 'modelo': m, 'mae_curto': a, 'mae_longo': c, 'delta_pct': delta})
    b += text(px + 300, py + 402, 'MAE (W/m²)', 23, 'middle', '#5A6268')
b += circle(34, 875, 8, '#FFF', '#475865', 3) + text(55, 883, 'Histórico curto', 24)
b += circle(315, 875, 8, '#475865') + text(336, 883, 'Histórico longo', 24)
b += text(20, 927, 'Controle sem quantização · mesmo teste histórico · Δ negativo indica melhora', 24, fill='#4E575E')
b += text(20, 963, 'Mensal de seis passos: exploratório. Escalas próprias em cada painel.', 23, fill='#4E575E')
save('06_historico', b, 990)

# Cumulative horizon profiles with actual physical horizon spacing.
b = ''
for k, (t, H, label) in enumerate(TASKS):
    px, py = (k % 2) * 600, (k // 2) * 400
    b += text(px + 20, py + 34, f'{chr(65+k)}  {label.replace(" · exploratório", "")}', 27, weight='bold')
    if H == 6:
        b += text(px + 20, py + 66, 'Exploratório', 22, fill='#666')
    groups = []
    for m in MODELS:
        q = chosen('atual', t, m).variante
        z = D[(D.regime == 'atual') & (D.tarefa == t) & (D.modelo == m) & (D.variante == q)].sort_values('horizonte')
        assert z.horizonte.is_unique
        groups.append((m, q, z))
    top = nice_top(max(float(z.MAE_wm2.max()) for _, _, z in groups) * 1.1)
    horizons = sorted(int(v) for v in groups[0][2].horizonte.unique())
    x, y, w, h = px + 95, py + 292, 460, 205
    for v in [0, top/4, top/2, 3*top/4, top]:
        yy = y - v/top*h
        b += line(x, yy, x+w, yy) + text(x-14, yy+8, fmt(v, 0), 22, 'end', '#5A6268')
    b += text(px+27, py+190, 'MAE (W/m²)', 23, 'middle', '#5A6268', rotate=-90)
    if len(horizons) == 1:
        for j, (m, q, z) in enumerate(groups):
            value = float(z.iloc[0].MAE_wm2)
            xx, yy = x + 70 + j*160, y-value/top*h
            b += circle(xx, yy, 7, COL[m]) + text(xx, yy-17, fmt(value), 23, 'middle', COL[m])
            b += text(xx, y+33, m, 22, 'middle', COL[m])
            audit['horizontes'].append({'tarefa':t,'modelo':m,'variante':q,'horizonte':1,'mae':value})
        b += text(px+325, py+372, 'Uma previsão mensal por origem', 23, 'middle', '#5A6268')
    else:
        xp = lambda v: x + (v-min(horizons))/(max(horizons)-min(horizons))*w
        for m, q, z in groups:
            pts = [(xp(float(a.horizonte)), y-float(a.MAE_wm2)/top*h) for a in z.itertuples()]
            b += f'<polyline points="{" ".join(f"{a},{c}" for a,c in pts)}" fill="none" stroke="{COL[m]}" stroke-width="3.5"/>'
            for (xx,yy),a in zip(pts,z.itertuples()):
                b += circle(xx,yy,5.5,COL[m])
                audit['horizontes'].append({'tarefa':t,'modelo':m,'variante':q,'horizonte':int(a.horizonte),'mae':float(a.MAE_wm2)})
        for v in horizons:
            b += text(xp(v), y+33, str(v), 22, 'middle', '#5A6268')
        unit = 'horas' if H == 72 else ('dias' if H == 30 else 'meses')
        b += text(px+325, py+372, f'Horizonte cumulativo ({unit})', 23, 'middle', '#5A6268')
for j, m in enumerate(MODELS):
    xx = 95 + j*365
    b += line(xx, 835, xx+50, 835, COL[m], 4) + circle(xx+25,835,5.5,COL[m]) + text(xx+65,843,m,25,fill=COL[m])
b += text(20, 890, 'Teste de 2024 · condição de entrada fixa pela validação do horizonte completo', 24, fill='#4E575E')
b += text(20, 926, 'Cada MAE reúne os passos de 1 até o horizonte indicado; não é erro de lead exato.', 23, fill='#4E575E')
save('07_horizontes', b, 950)

# Independent check against the numeric records used by the previous figures.
old = json.loads((Path(__file__).parents[1] / 'figuras/dados_graficos.json').read_text(encoding='utf-8'))
for category, fields in [('quantizacao_atual', ['tarefa','modelo','variante','delta_pct','selecionado']),
                         ('historico_pareado', ['tarefa','modelo','mae_curto','mae_longo','delta_pct'])]:
    assert len(old[category]) == len(audit[category])
    for prev,new in zip(old[category], audit[category]):
        for field in fields:
            assert prev[field] == new[field], (category,field,prev[field],new[field])
audit['validation'] = {'original_quantization_and_history_records_identical': True,
    'ranking_matches_frozen_validation_choices': True, 'source_csvs_unmodified': True}
(OUT / 'dados_graficos_revisados.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'output':str(OUT),'figures':4,'validation':audit['validation']},ensure_ascii=False))
