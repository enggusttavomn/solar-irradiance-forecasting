"""Sintese tabular dos resultados auditados, com classificacoes e comparacoes pareadas."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from scripts.gerar_pdf_quantizacao_unificado_compacto_v1 import (
    ROOT, REL, REGIMES, CASES, ORIGINALS, digest, load, source_data,
)
from scripts.metricas_quantizacao_todos import MODELOS, TAREFAS, VARIANTES

W, H = landscape(A4)
M = 28
GAP = 18
WIDTH = W - 2 * M
HALF = (WIDTH - GAP) / 2
INK = colors.HexColor('#243B4B')
MUTED = colors.HexColor('#526574')
BLUE = colors.HexColor('#E5EDF3')
PALE = colors.HexColor('#F3F5F7')
LINE = colors.HexColor('#C9D3DB')
BEST = colors.HexColor('#DCEBEF')
REG_LABEL = {'atual': 'Base 2019-2024', 'historico_1998_2022': 'Historico longo',
             'historico_curto_pareado': 'Historico curto pareado'}
REG_LABEL = {k: v.replace('Historico', 'Histórico') for k, v in REG_LABEL.items()}
TASK_LABEL = {'hourly_72_extension': 'Horário - 72 h', 'daily_30': 'Diário - 30 dias',
              'monthly_1': 'Mensal - tarefa de um mês', 'monthly_6': 'Mensal - tarefa de seis meses'}
AUDIT_DIRS = ('auditoria_final_atual', 'auditoria_historico_1998_2022', 'auditoria_historico_curto_pareado')


def fmt(value, digits=4, signed=False):
    value = float(value)
    out = f'{value:.{digits}f}'.replace('.', ',')
    return ('+' if signed and value > 0 else '') + out


def condition(value, long=False):
    if value == 'sem_quantizacao':
        return 'Sem quantização' if long else 'Sem'
    return value[1:] + (' níveis' if long else '')


def model_label(value):
    return {'Persistencia': 'Persistência', 'Sazonal ingenuo': 'Sazonal ingênuo'}.get(value, value)


def plain(text):
    text = re.sub(r'<br\s*/?>', ' ', str(text), flags=re.I)
    return html.unescape(re.sub(r'<[^>]+>', '', text))


class Data:
    def __init__(self):
        rows, pairs, self.choices, self.sources, self.audits = source_data()
        self.original_rows = len(rows)
        self.pairs = pairs
        self.frames, self.selected, self.full = {}, {}, {}
        self.quant_counts, self.rankings, self.rmse_leaders = {}, {}, {}
        for regime, folder in zip(REGIMES, AUDIT_DIRS, strict=True):
            audit = load(REL / folder / 'auditoria.json')
            path = Path(audit['metricas']['path'])
            assert digest(path) == audit['metricas']['sha256']
            self.sources[str(path)] = digest(path)
            frame = pd.read_csv(path)
            frame = frame.loc[frame.particao == 'teste'].copy()
            frame['horizonte'] = frame.horizonte.astype(int)
            assert len(frame) == 528
            frame['selecionado'] = [self.choices[regime][t, m] == v
                                    for t, m, v in frame[['tarefa', 'modelo', 'variante']].itertuples(index=False, name=None)]
            self.frames[regime] = frame
            self.selected[regime] = frame.loc[frame.selecionado].copy()
            full = frame.loc[[h == max(TAREFAS[t]) for t, h in frame[['tarefa', 'horizonte']].itertuples(index=False, name=None)]]
            self.full[regime] = full.copy()
            selected = full.loc[full.selecionado]
            control = full.loc[full.variante == 'sem_quantizacao'].set_index(['tarefa', 'modelo'])
            counts = Counter({'melhora': 0, 'piora': 0, 'empate': 0, 'controle': 0})
            for row in selected.itertuples():
                base = float(control.loc[(row.tarefa, row.modelo), 'MAE_wm2'])
                delta = row.MAE_wm2 - base
                key = ('controle' if row.variante == 'sem_quantizacao' else
                       'melhora' if delta < -1e-7 else 'piora' if delta > 1e-7 else 'empate')
                counts[key] += 1
            assert sum(counts.values()) == 44
            self.quant_counts[regime] = dict(counts)
            for task, hs in TAREFAS.items():
                for horizon in hs:
                    rank = self.selected[regime].loc[(self.selected[regime].tarefa == task) &
                                                     (self.selected[regime].horizonte == horizon)]
                    rank = rank.sort_values(['MAE_wm2', 'modelo'], kind='stable')
                    assert len(rank) == 11
                    self.rankings[regime, task, horizon] = rank
                self.rmse_leaders[regime, task] = self.rankings[regime, task, max(hs)].sort_values(['RMSE_wm2', 'modelo']).iloc[0]
        expected = {'atual': (13, 21, 10), 'historico_1998_2022': (16, 17, 11),
                    'historico_curto_pareado': (17, 15, 12)}
        for regime, counts in expected.items():
            assert tuple(self.quant_counts[regime][key] for key in ('melhora', 'piora', 'controle')) == counts
        self.history = {}
        self.history_counts = {}
        for task, hs in TAREFAS.items():
            horizon = max(hs)
            a = self.full[REGIMES[1]].loc[self.full[REGIMES[1]].tarefa == task]
            b = self.full[REGIMES[2]].loc[self.full[REGIMES[2]].tarefa == task]
            merged = b.merge(a, on=['tarefa', 'modelo', 'variante', 'horizonte'], suffixes=('_curto', '_longo'), validate='one_to_one')
            assert len(merged) == 44
            for field in ('N_localidades', 'N_origens', 'N_pontos'):
                assert (merged[field + '_curto'] == merged[field + '_longo']).all()
            merged['delta'] = merged.MAE_wm2_longo - merged.MAE_wm2_curto
            merged['delta_pct'] = 100 * merged.delta / merged.MAE_wm2_curto
            self.history[task] = merged
            control = merged.loc[merged.variante == 'sem_quantizacao']
            self.history_counts[task] = {
                'melhora': int((control.delta < -1e-7).sum()),
                'piora': int((control.delta > 1e-7).sum()),
                'empate': int((control.delta.abs() <= 1e-7).sum()),
            }
        assert tuple(sum(x[k] for x in self.history_counts.values()) for k in ('melhora', 'piora', 'empate')) == (34, 2, 8)

    def rank(self, regime, task, horizon=None):
        return self.rankings[regime, task, horizon or max(TAREFAS[task])]

    def baseline(self, regime, task, model):
        return float(self.full[regime].loc[(self.full[regime].tarefa == task) &
                                         (self.full[regime].modelo == model) &
                                         (self.full[regime].variante == 'sem_quantizacao'), 'MAE_wm2'].iloc[0])


class PDF:
    def __init__(self, path):
        self.c = canvas.Canvas(str(path), pagesize=(W, H), pageCompression=1)
        self.c.setTitle('Comparação dos modelos de previsão de GHI - síntese dos resultados')
        self.c.setAuthor('Gustavo de Melo Nascimento')
        self.page, self.cells, self.sections, self.blocks = 0, [], [], []

    def start(self, title, subtitle):
        self.page += 1
        self.c.setFillColor(INK)
        self.c.setFont('ReportArialBold', 15)
        self.c.drawString(M, H - 28, title)
        self.c.setFont('ReportArial', 9)
        self.c.setFillColor(MUTED)
        self.c.drawString(M, H - 44, subtitle)
        self.c.setStrokeColor(LINE)
        self.c.line(M, H - 53, W - M, H - 53)
        bookmark = f'pagina_{self.page}'
        self.c.bookmarkPage(bookmark)
        self.c.addOutlineEntry(title, bookmark, level=0)
        self.sections.append({'titulo': title, 'pagina': self.page})

    def end(self):
        self.c.setFillColor(MUTED)
        self.c.setFont('ReportArial', 7.3)
        self.c.drawString(M, 15, 'MAE e RMSE: W/m² | R²: adimensional | Valores menores de MAE e RMSE indicam menor erro')
        self.c.drawRightString(W - M, 15, f'{self.page} / 10')
        self.c.showPage()

    def paragraph(self, text, x, top, width, size=9.5, leading=13, color=INK):
        style = ParagraphStyle('body', fontName='ReportArial', fontSize=size, leading=leading, textColor=color)
        p = Paragraph(text, style)
        _, height = p.wrap(width, H)
        if top - height < 28:
            raise ValueError(f'Texto fora da area util na pagina {self.page}: {plain(text)}')
        p.drawOn(self.c, x, top - height)
        self.blocks.append({'pagina': self.page, 'rect': [x, H - top, x + width, H - top + height], 'texto': plain(text)})
        return top - height - 9

    def cell(self, text, x, bottom, width, height, *, align='right', bold=False,
             fill=None, size=9, paragraph=False, key=None):
        if fill:
            self.c.setFillColor(fill)
            self.c.rect(x, bottom, width, height, fill=1, stroke=0)
        if paragraph:
            style = ParagraphStyle('cell', fontName='ReportArialBold' if bold else 'ReportArial', fontSize=size,
                                   leading=size + 2, textColor=INK,
                                   alignment={'left': TA_LEFT, 'center': TA_CENTER, 'right': TA_RIGHT}[align])
            p = Paragraph(str(text), style)
            _, ph = p.wrap(width - 10, height)
            if ph > height - 5:
                raise ValueError(f'Celula nao cabe p{self.page}: {plain(text)}')
            p.drawOn(self.c, x + 5, bottom + (height - ph) / 2)
        else:
            font = 'ReportArialBold' if bold else 'ReportArial'
            if pdfmetrics.stringWidth(str(text), font, size) > width - 8:
                raise ValueError(f'Celula larga p{self.page}: {text}, largura {width}')
            self.c.setFont(font, size)
            self.c.setFillColor(INK)
            baseline = bottom + (height - size) / 2 + 1.5
            if align == 'right':
                self.c.drawRightString(x + width - 4, baseline, str(text))
            elif align == 'center':
                self.c.drawCentredString(x + width / 2, baseline, str(text))
            else:
                self.c.drawString(x + 4, baseline, str(text))
        self.cells.append({'pagina': self.page, 'rect': [x, H - bottom - height, x + width, H - bottom],
                           'texto': plain(text), 'chave': key})

    def table(self, title, headers, rows, x, top, widths, *, row_h=14.5, header_h=18,
              aligns=None, bold_rows=(), marks=None, size=9, paragraph=False, keys=None):
        if title:
            self.c.setFillColor(INK)
            self.c.setFont('ReportArialBold', 10.5)
            self.c.drawString(x, top - 10.5, title)
            top -= 19
        width = sum(widths)
        bottom = top - header_h
        self.c.setFillColor(BLUE)
        self.c.rect(x, bottom, width, header_h, fill=1, stroke=0)
        cursor = x
        for j, (label, cw) in enumerate(zip(headers, widths, strict=True)):
            self.cell(label, cursor, bottom, cw, header_h, align='left' if j == 0 else 'center',
                      bold=True, size=min(size, 8.7), paragraph='<br' in str(label))
            cursor += cw
        for i, row in enumerate(rows):
            bottom -= row_h
            if bottom < 27:
                raise ValueError(f'Tabela fora da pagina {self.page}')
            self.c.setFillColor(BLUE if i in bold_rows else PALE if i % 2 == 0 else colors.white)
            self.c.rect(x, bottom, width, row_h, fill=1, stroke=0)
            cursor = x
            for j, (value, cw) in enumerate(zip(row, widths, strict=True)):
                mark = (marks or {}).get((i, j))
                key = keys[i][j] if keys is not None else None
                self.cell(value, cursor, bottom, cw, row_h, align=(aligns or ['left'] + ['right'] * (len(row) - 1))[j],
                          bold=i in bold_rows, fill=mark, size=size, paragraph=paragraph, key=key)
                cursor += cw
        self.c.setStrokeColor(LINE)
        self.c.setLineWidth(.4)
        self.c.line(x, bottom, x + width, bottom)
        return bottom


def overview(pdf, data):
    pdf.start('Comparação dos modelos de previsão de GHI', 'Síntese dos menores MAEs | Horizonte completo | Condição de entrada escolhida na validação')
    rows = []
    for task in TAREFAS:
        row = ['<b>' + TASK_LABEL[task] + '</b>']
        for regime in REGIMES:
            rank = data.rank(regime, task)
            first, second = rank.iloc[0], rank.iloc[1]
            advantage = 100 * (second.MAE_wm2 - first.MAE_wm2) / second.MAE_wm2
            row.append(f'<b>{model_label(first.modelo)}</b> | {condition(first.variante, True)}<br/>'
                       f'MAE: <b>{fmt(first.MAE_wm2)}</b><br/>'
                       f'2º: {model_label(second.modelo)} | {fmt(second.MAE_wm2)}<br/>'
                       f'Diferença relativa: {fmt(advantage, 2)}%')
        rows.append(row)
    pdf.table('', ['Tarefa', 'Base 2019-2024<br/>Teste: 2024', 'Histórico longo<br/>Teste: abr/2019-dez/2022',
                   'Histórico curto pareado<br/>Teste: abr/2019-dez/2022'], rows, M, H - 67,
              [143] + [(WIDTH - 143) / 3] * 3, row_h=60, header_h=32, size=9.5,
              paragraph=True, aligns=['left'] * 4)
    left = H - 356
    left = pdf.paragraph('<b>Desempenho por tarefa.</b> A TimesNet apresentou os menores MAEs nos horizontes de 72 horas e 30 dias dos três conjuntos. '
                         'Nas tarefas mensais, a Climatologia liderou cinco das seis comparações. A DilatedRNN apresentou o menor MAE na tarefa mensal de um mês com histórico longo.', M, left, HALF)
    pdf.paragraph('<b>Critério de classificação.</b> Cada modelo mantém a condição de entrada escolhida na validação, considerando o horizonte completo de sua tarefa. '
                  'A diferença relativa corresponde a 100 × (MAE do segundo - MAE do primeiro) / MAE do segundo.', M, left, HALF)
    right = H - 356
    right = pdf.paragraph('<b>MAE e RMSE.</b> A liderança muda conforme a métrica em sete das 12 comparações. O XGBoost apresentou o menor RMSE horário nas três bases; '
                          'no diário, liderou na base 2019-2024 e no histórico curto. O Informer apresentou o menor RMSE diário no histórico longo.', M + HALF + GAP, right, HALF)
    pdf.paragraph('<b>Interpretação.</b> As classificações descrevem o teste. Os erros da base 2019-2024 e dos históricos correspondem a períodos diferentes. '
                  'As diferenças não foram submetidas a teste de significância e os valores agregados não garantem liderança em cada localidade.', M + HALF + GAP, right, HALF)
    pdf.end()


def protocol(pdf, data):
    pdf.start('Períodos de avaliação e efeito da quantização', 'Onze modelos | Dez localidades | 72 h, 30 dias, um mês e seis meses')
    periods = [
        ['Treino inicial', 'jan/2019-dez/2022', 'jan/1998-mar/2018', 'abr/2014-mar/2018'],
        ['Validação', 'jan-dez/2023', 'abr/2018-mar/2019', 'abr/2018-mar/2019'],
        ['Treino final', 'jan/2019-dez/2023', 'jan/1998-mar/2019', 'abr/2014-mar/2019'],
        ['Teste', 'jan-dez/2024', 'abr/2019-dez/2022', 'abr/2019-dez/2022'],
    ]
    y = pdf.table('Divisão cronológica', ['Etapa', 'Base 2019-2024', 'Histórico longo', 'Histórico curto pareado'],
                  periods, M, H - 67, [125] + [(WIDTH - 125) / 3] * 3, row_h=24,
                  aligns=['left', 'center', 'center', 'center'], size=10)
    y = pdf.paragraph('O treino inicial foi seguido pela seleção na validação e pelo treino final. A comparação dos históricos utiliza as mesmas origens, '
                      'alvos e localidades de teste. O recorte curto contém cinco anos de dados antes do teste.', M, y - 13, WIDTH)
    rows = []
    for regime in REGIMES:
        c = data.quant_counts[regime]
        rows.append([REG_LABEL[regime], c['melhora'], c['piora'], c['empate'], c['controle']])
    y = pdf.table('Quantização: escolha da validação versus controle do mesmo modelo',
                  ['Conjunto', 'Menor MAE', 'Maior MAE', 'Empate numérico', 'Escolha sem quantização'],
                  rows, M, y - 8, [206, 115, 115, 133, WIDTH - 569], row_h=24,
                  aligns=['left'] + ['center'] * 4, size=9.6)
    y = pdf.paragraph('As contagens abrangem 44 combinações de modelo e tarefa em cada conjunto, nos horizontes completos. As condições quantizadas selecionadas '
                      'são comparadas ao controle sem quantização; a última coluna reúne os casos em que a validação manteve o controle. '
                      'Não houve melhora consistente em todas as tarefas e modelos.', M, y - 12, WIDTH)
    left = y - 5
    left = pdf.paragraph('<b>Condições de entrada.</b> Foram comparados min-max sem quantização e 64, 128 e 256 níveis. A quantização foi aplicada ao histórico de GHI '
                         'usado pelos modelos, no ajuste e na previsão. Pesos, saídas e valores reais de avaliação permanecem contínuos. '
                         'O efeito medido combina clipping e arredondamento, sem controle separado de clipping.', M, left, HALF, size=9.2, leading=12.3)
    pdf.paragraph('<b>Métricas.</b> MAE e RMSE são apresentados em W/m²; o R² é adimensional. As métricas são calculadas por localidade e depois promediadas. '
                  'O RMSE atribui maior peso aos erros grandes. A classificação foi calculada com os valores completos; quatro casas decimais são exibidas nas tabelas.', M, left, HALF, size=9.2, leading=12.3)
    right = y - 5
    right = pdf.paragraph('<b>Escopo.</b> As páginas 3, 5 e 6 classificam os modelos na base 2019-2024 e nos históricos longo e curto, respectivamente. '
                          'A página 4 detalha as quatro condições na base atual; 7-9 comparam os históricos; 10 reúne os três menores MAEs por horizonte.', M + HALF + GAP, right, HALF, size=9.2, leading=12.3)
    pdf.paragraph('<b>Limites.</b> A avaliação é retrospectiva; os níveis foram escolhidos na validação. A tarefa de seis meses é exploratória e utiliza alvos sobrepostos. '
                  'As auditorias aprovaram o recálculo das métricas e a reprodução dos checkpoints novos. MSE, nRMSE e resultados intermediários completos constam nos relatórios detalhados.', M + HALF + GAP, right, HALF, size=9.2, leading=12.3)
    pdf.end()


def ranking_page(pdf, data, regime, block):
    subtitle = ('Teste em 2024' if regime == 'atual' else 'Teste de abril/2019 a dezembro/2022')
    pdf.start(f'{block}. {REG_LABEL[regime]} - classificação dos modelos', subtitle + ' | Posição pelo MAE | Condição escolhida na validação')
    widths = [27, 92, 44, 61, 61, 44, HALF - 329]
    for index, task in enumerate(TAREFAS):
        frame = data.rank(regime, task)
        rows, marks, keys = [], {}, []
        best_rmse = int(frame.RMSE_wm2.to_numpy().argmin())
        marks[best_rmse, 4] = BEST
        for pos, record in enumerate(frame.itertuples(), 1):
            base = data.baseline(regime, task, record.modelo)
            delta = 100 * (record.MAE_wm2 - base) / base
            rows.append([pos, model_label(record.modelo), condition(record.variante), fmt(record.MAE_wm2),
                         fmt(record.RMSE_wm2), fmt(record.R2, 3), fmt(delta, 3, signed=True)])
            key = [regime, task, record.modelo, record.variante, record.horizonte]
            keys.append([None, None, None] + [{'registro': key, 'metrica': k} for k in ('MAE_wm2', 'RMSE_wm2', 'R2', 'delta_quant_pct')])
        x = M + (index % 2) * (HALF + GAP)
        top = H - 67 - (index // 2) * 226
        pdf.table(TASK_LABEL[task], ['Pos.', 'Modelo', 'Entrada', 'MAE', 'RMSE', 'R²', 'Delta %'], rows,
                  x, top, widths, row_h=14.4, header_h=18, bold_rows=(0, 1, 2), marks=marks,
                  aligns=['center', 'left', 'center', 'right', 'right', 'right', 'right'], size=8.9, keys=keys)
    if regime == 'atual':
        text = 'A TimesNet apresentou o menor MAE horário e diário. O XGBoost apresentou o menor RMSE nessas duas tarefas. A Climatologia liderou MAE e RMSE nas duas tarefas mensais.'
    elif regime == 'historico_1998_2022':
        text = 'A TimesNet liderou o MAE horário e diário. Na tarefa mensal de um mês, a DilatedRNN teve o menor MAE e a Climatologia o menor RMSE. No diário, o menor RMSE foi do Informer.'
    else:
        text = 'A TimesNet liderou o MAE horário e diário; a Climatologia liderou as duas tarefas mensais. O menor RMSE horário e diário foi do XGBoost.'
    pdf.paragraph(text, M, 83, WIDTH, size=9.2, leading=12)
    pdf.paragraph('Sem: ausência de quantização. Entrada 64/128/256: número de níveis. Delta %: diferença do MAE selecionado em relação ao controle do mesmo modelo; negativo indica redução. '
                  'As três primeiras posições e o menor RMSE estão destacados.', M, 52, WIDTH, size=8.1, leading=10.5)
    pdf.end()


def quantization_current(pdf, data):
    pdf.start('1. Base 2019-2024 - MAE por condição de entrada', 'Teste em 2024 | Todas as condições | Destaque na condição escolhida na validação')
    widths = [95] + [62] * 4 + [HALF - 343]
    for index, task in enumerate(TAREFAS):
        frame = data.full['atual'].loc[data.full['atual'].tarefa == task].set_index(['modelo', 'variante'])
        rows, marks, keys = [], {}, []
        for i, model in enumerate(data.rank('atual', task).modelo):
            level = data.choices['atual'][task, model]
            rows.append([model_label(model)] + [fmt(frame.loc[(model, variant), 'MAE_wm2']) for variant in VARIANTES] + [condition(level)])
            marks[i, 1 + list(VARIANTES).index(level)] = BEST
            keys.append([None] + [{'registro': ['atual', task, model, variant, max(TAREFAS[task])], 'metrica': 'MAE_wm2'} for variant in VARIANTES] + [None])
        pdf.table(TASK_LABEL[task], ['Modelo', 'Sem', '64 níveis', '128 níveis', '256 níveis', 'Val.'], rows,
                  M + (index % 2) * (HALF + GAP), H - 67 - (index // 2) * 226,
                  widths, row_h=14.4, header_h=18, aligns=['left'] + ['right'] * 4 + ['center'], size=8.9, marks=marks, keys=keys)
    pdf.paragraph('Val.: condição escolhida na validação, destacada em azul. Essa condição não corresponde necessariamente ao menor MAE observado no teste. '
                  'A ordenação dos modelos segue o MAE da condição selecionada.', M, 83, WIDTH, size=9.2, leading=12)
    pdf.paragraph('As variantes quantizadas incluem clipping e arredondamento. Pequenas diferenças entre as condições não demonstram significância estatística.', M, 52, WIDTH, size=8.4, leading=11)
    pdf.end()


def history_control(pdf, data):
    pdf.start('4. Histórico longo versus curto - sem quantização', 'Mesmas origens, alvos e localidades | Horizonte completo | Ordenação pelo Delta: longo - curto')
    widths = [95, 65, 65, 78, HALF - 303]
    for index, task in enumerate(TAREFAS):
        frame = data.history[task].loc[data.history[task].variante == 'sem_quantizacao'].sort_values(['delta', 'modelo'])
        rows, keys = [], []
        for record in frame.itertuples():
            rows.append([model_label(record.modelo), fmt(record.MAE_wm2_curto), fmt(record.MAE_wm2_longo),
                         fmt(record.delta, signed=True), fmt(record.delta_pct, 2, signed=True)])
            base = [task, record.modelo, 'sem_quantizacao']
            keys.append([None] + [{'comparacao': base, 'metrica': k} for k in ('MAE_curto', 'MAE_longo', 'delta', 'delta_pct')])
        pdf.table(TASK_LABEL[task], ['Modelo', 'MAE curto', 'MAE longo', 'Delta W/m²', 'Delta %'], rows,
                  M + (index % 2) * (HALF + GAP), H - 67 - (index // 2) * 226, widths,
                  row_h=14.4, header_h=18, size=9, keys=keys)
    pdf.paragraph('O histórico longo apresentou menor MAE em 34 das 44 comparações, maior em duas e empate numérico em oito. '
                  'As duas pioras ocorreram no ARIMA e na LSTM no horizonte de 72 horas, sem quantização.', M, 83, WIDTH, size=9.2, leading=12)
    pdf.paragraph('Delta negativo favorece o longo. Empate numérico: diferença absoluta de até 0,0000001 W/m². Esta comparação mantém a condição sem quantização em ambos os históricos. '
                  'Os resultados não estabelecem causa climática.', M, 52, WIDTH, size=8.1, leading=10.5)
    pdf.end()


def history_quantized(pdf, data, tasks):
    label = 'horário e diário' if tasks[0] == 'hourly_72_extension' else 'tarefas mensais'
    pdf.start('4. Histórico longo versus curto - ' + label, 'Mesma condição de entrada em ambos os históricos | MAE e Delta em W/m² | Horizonte completo')
    model_w = 112
    cw = (WIDTH - model_w) / 9
    widths = [model_w] + [cw] * 9
    headers = ['Modelo'] + ['MAE curto', 'MAE longo', 'Delta'] * 3
    for index, task in enumerate(tasks):
        top = H - 67 - index * 231
        pdf.c.setFillColor(INK)
        pdf.c.setFont('ReportArialBold', 10.5)
        pdf.c.drawString(M, top - 10.5, TASK_LABEL[task])
        group_top = top - 20
        pdf.c.setFillColor(BLUE)
        pdf.c.rect(M, group_top - 15, WIDTH, 15, fill=1, stroke=0)
        pdf.cell('', M, group_top - 15, model_w, 15)
        for group, level in enumerate(('q64', 'q128', 'q256')):
            pdf.cell(condition(level, True), M + model_w + group * 3 * cw, group_top - 15, 3 * cw, 15, bold=True, align='center', size=9)
        frame = data.history[task].set_index(['modelo', 'variante'])
        rows, keys = [], []
        for model in sorted(MODELOS):
            row, kr = [model_label(model)], [None]
            for level in ('q64', 'q128', 'q256'):
                record = frame.loc[(model, level)]
                row += [fmt(record.MAE_wm2_curto), fmt(record.MAE_wm2_longo), fmt(record.delta, signed=True)]
                kr += [{'comparacao': [task, model, level], 'metrica': k} for k in ('MAE_curto', 'MAE_longo', 'delta')]
            rows.append(row)
            keys.append(kr)
        pdf.table('', headers, rows, M, group_top - 15, widths, row_h=14.4, header_h=18, size=9.1, keys=keys)
    pdf.paragraph('Delta negativo indica menor MAE no histórico longo. A comparação mantém o mesmo número de níveis; as condições escolhidas pela validação podem diferir entre os históricos.',
                  M, 60, WIDTH, size=8.8, leading=11.5)
    pdf.end()


def horizons(pdf, data):
    pdf.start('Três menores MAEs por horizonte', 'Mesma condição escolhida na validação do horizonte completo | Horizontes cumulativos')
    rows = []
    for task, hs in TAREFAS.items():
        for horizon in hs:
            unit = ('h' if task.startswith('hourly') else ('dia' if horizon == 1 else 'dias')
                    if task.startswith('daily') else 'mês' if horizon == 1 else 'meses')
            short = 'Horário' if task.startswith('hourly') else 'Diário' if task.startswith('daily') else 'Mensal (1 mês)' if task == 'monthly_1' else 'Mensal (6 meses)'
            row = [f'<b>{short}</b><br/>{horizon} {unit}']
            for regime in REGIMES:
                entries = []
                for pos, record in enumerate(data.rank(regime, task, horizon).head(3).itertuples(), 1):
                    text = f'{pos}º {model_label(record.modelo)} ({condition(record.variante)}) | {fmt(record.MAE_wm2)}'
                    entries.append('<b>' + text + '</b>' if pos == 1 else text)
                row.append('<br/>'.join(entries))
            rows.append(row)
    assert len(rows) == 12
    pdf.table('', ['Tarefa / horizonte', 'Base 2019-2024', 'Histórico longo', 'Histórico curto pareado'], rows,
              M, H - 67, [119] + [(WIDTH - 119) / 3] * 3, row_h=37.5, header_h=23,
              paragraph=True, aligns=['left'] * 4, size=8.65)
    pdf.paragraph('Sem: ausência de quantização. A tarefa mensal de um mês difere do primeiro horizonte da tarefa de seis meses. As posições descrevem o MAE no teste.',
                  M, 43, WIDTH, size=7.9, leading=10)
    pdf.end()


def generate(output, manifest):
    output, manifest = Path(output).resolve(), Path(manifest).resolve()
    for path in (output, manifest):
        if not path.is_relative_to(ROOT) or path.exists():
            raise ValueError('A autoria exige destinos novos dentro do projeto.')
        path.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('ReportArial', 'C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('ReportArialBold', 'C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('ReportArial', normal='ReportArial', bold='ReportArialBold',
                                italic='ReportArial', boldItalic='ReportArialBold')
    data = Data()
    pdf = PDF(output)
    overview(pdf, data)
    protocol(pdf, data)
    ranking_page(pdf, data, 'atual', 1)
    quantization_current(pdf, data)
    ranking_page(pdf, data, 'historico_1998_2022', 2)
    ranking_page(pdf, data, 'historico_curto_pareado', 3)
    history_control(pdf, data)
    history_quantized(pdf, data, list(TAREFAS)[:2])
    history_quantized(pdf, data, list(TAREFAS)[2:])
    horizons(pdf, data)
    assert pdf.page == 10
    pdf.c.save()
    for path, expected in data.sources.items():
        assert digest(path) == expected, path
    for path, expected in ORIGINALS.items():
        assert digest(path) == expected, path
    selected_rows = []
    for regime in REGIMES:
        for task in TAREFAS:
            for pos, record in enumerate(data.rank(regime, task).to_dict('records'), 1):
                record.update(regime=regime, posicao=pos)
                selected_rows.append(record)
    record = {
        'gerado_em_utc': datetime.now(timezone.utc).isoformat(),
        'pdf': {'path': str(output), 'sha256': digest(output), 'paginas': pdf.page},
        'fontes_sha256': data.sources, 'originais_sha256': {str(p): v for p, v in ORIGINALS.items()},
        'linhas_teste_origem': data.original_rows,
        'linhas_classificacao_horizonte_completo': len(selected_rows),
        'MAEs_todas_condicoes_horizonte_completo': 528,
        'comparacoes_historicas': 176,
        'rankings_selecionados': selected_rows,
        'contagens_quantizacao': data.quant_counts,
        'contagens_historico_sem_quantizacao': data.history_counts,
        'secoes': pdf.sections, 'celulas_pdf': pdf.cells, 'textos_pdf': pdf.blocks,
        'criterio': 'MAE no teste, condicao escolhida pela validacao no horizonte completo; classificacao descritiva.',
        'gerador_sha256': digest(Path(__file__)), 'revisao_visual_pendente': True,
    }
    manifest.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pdf': str(output), 'paginas': pdf.page, 'celulas': len(pdf.cells), 'classificacoes': len(selected_rows)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida', required=True, type=Path)
    parser.add_argument('--manifesto', required=True, type=Path)
    args = parser.parse_args()
    generate(args.saida, args.manifesto)
