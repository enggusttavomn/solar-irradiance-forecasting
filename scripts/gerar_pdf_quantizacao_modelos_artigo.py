"""Recortes dos resultados auditados para o artigo ou para a disciplina."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pymupdf
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from scripts import gerar_pdf_quantizacao_analise_compacta as base

ROOT = Path(__file__).resolve().parents[1]
REL = ROOT / 'relatorios/quantizacao_todos_modelos_20260929'
MODELS = ('TimesNet', 'Persistencia', 'Sazonal ingenuo', 'Transformer', 'Informer', 'LSTM')
LABELS = {'Persistencia': 'Persistence', 'Sazonal ingenuo': 'Sazonal Ingênuo'}
OUTPUT = ROOT / 'output/pdf/quantizacao_ghi_modelos_para_artigo.pdf'
REPORT = ROOT / 'relatorios/quantizacao_modelos_artigo_20261019'
TITLE = 'Modelos para o artigo'
AUDIENCE = 'artigo'
BODY_SHIFT = 15
PAGE_INTROS = (
    'Compara os seis modelos nas dez localidades, no teste de 2024 e no horizonte completo de cada tarefa. '
    'A entrada foi escolhida na validação; Delta % compara seu MAE com o controle sem quantização do mesmo modelo.',
    'Avalia o efeito da quantização no teste de 2024: compara o MAE sem quantização e com 64, 128 e 256 níveis. '
    'O destaque marca a escolha da validação, mantida mesmo quando outra condição tem menor erro no teste.',
    'Compara os seis modelos com histórico iniciado em janeiro/1998 e teste de abril/2019 a dezembro/2022. '
    'A entrada foi escolhida na validação; Delta % compara seu MAE com o controle sem quantização do mesmo modelo.',
    'Compara os seis modelos com histórico iniciado em abril/2014 e teste de abril/2019 a dezembro/2022. '
    'A entrada foi escolhida na validação; Delta % compara seu MAE com o controle sem quantização do mesmo modelo.',
    'Avalia o efeito de ampliar o histórico de treino, sem quantização e com o mesmo teste de abril/2019 a dezembro/2022. '
    'Compara o histórico longo (início em 1998) ao curto (início em 2014); Delta negativo favorece o longo.',
    'Avalia os históricos longo e curto nas previsões de 72 horas e 30 dias, com teste de abril/2019 a dezembro/2022 e o mesmo nível de quantização. '
    'MAE e Delta estão em W/m²; Delta = longo menos curto, e valores negativos favorecem o longo.',
    'Avalia os históricos longo e curto nas previsões mensais de um e seis meses, com teste de abril/2019 a dezembro/2022 e o mesmo nível de quantização. '
    'MAE e Delta estão em W/m²; Delta = longo menos curto, e valores negativos favorecem o longo.',
    'Apresenta os três menores MAEs entre os seis modelos em cada horizonte e nos três conjuntos, mantendo a entrada escolhida na validação do horizonte completo. '
    'Os horizontes são cumulativos: 48 h, por exemplo, inclui todos os passos das primeiras 48 horas.',
    'Mostra quando os dados foram usados para treino inicial, validação, treino final e teste em cada conjunto. '
    'A validação orienta a escolha da entrada antes do treino final; os dois históricos compartilham os períodos de validação e teste.',
    'Mostra o MAE dos seis modelos no teste de 2024, com a entrada escolhida na validação e o horizonte completo de cada tarefa. '
    'Barras menores indicam menor erro; os eixos começam em zero e cada painel tem sua própria escala.',
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def label(model):
    return LABELS.get(model, model)


def model_count_text():
    return {3: 'três', 6: 'seis'}[len(MODELS)]


class ArticleData:
    def __init__(self):
        self.sources, self.audits, self.choices = {}, {}, {}
        self.frames, self.full, self.selected, self.rankings = {}, {}, {}, {}
        self.quant_counts, self.history_counts, self.history = {}, {}, {}
        self.selected_rows = []
        for regime, folder in zip(base.REGIMES, base.AUDIT_DIRS, strict=True):
            audit_path = REL / folder / 'auditoria.json'
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            assert all(audit.get(k) is True for k in ('ok', 'publicavel', 'escopo_completo', 'replay_novo_executado'))
            assert audit['regime'] == regime and audit['pares_verificados'] == 44
            csv_path = REL / folder / 'metricas_auditadas.csv'
            assert sha(csv_path) == audit['metricas']['sha256']
            self.sources[str(audit_path)] = sha(audit_path)
            self.sources[str(csv_path)] = sha(csv_path)
            self.audits[regime] = {'path': str(audit_path), 'sha256': sha(audit_path)}
            choices = {(r['tarefa'], r['modelo']): r['vencedor_validacao']
                       for r in audit['resultados'] if r['modelo'] in MODELS}
            assert len(choices) == len(MODELS) * len(base.TAREFAS)
            self.choices[regime] = choices
            all_rows = pd.read_csv(csv_path)
            frame = all_rows.loc[all_rows.modelo.isin(MODELS)].copy()
            keycols = ['tarefa', 'modelo', 'variante', 'particao', 'horizonte']
            expected = {(t, m, v, p, h) for t, hs in base.TAREFAS.items() for m in MODELS
                        for v in base.VARIANTES for p in ('validacao', 'teste') for h in hs}
            assert len(frame) == len(expected) and not frame.duplicated(keycols).any()
            assert set(frame[keycols].itertuples(index=False, name=None)) == expected
            assert set(frame.N_localidades) == {10} and set(frame.regime) == {regime}
            frame = frame.loc[frame.particao == 'teste'].copy()
            frame['selecionado'] = [choices[t, m] == v for t, m, v in
                                    frame[['tarefa', 'modelo', 'variante']].itertuples(index=False, name=None)]
            self.frames[regime] = frame
            self.selected[regime] = frame.loc[frame.selecionado].copy()
            full = frame.loc[[h == max(base.TAREFAS[t]) for t, h in
                              frame[['tarefa', 'horizonte']].itertuples(index=False, name=None)]].copy()
            assert len(full) == len(MODELS) * len(base.TAREFAS) * len(base.VARIANTES)
            self.full[regime] = full
            counts = Counter(melhora=0, piora=0, empate=0, controle=0)
            for record in full.loc[full.selecionado].itertuples():
                delta = record.MAE_wm2 - self.baseline(regime, record.tarefa, record.modelo)
                key = ('controle' if record.variante == 'sem_quantizacao' else
                       'melhora' if delta < -1e-7 else 'piora' if delta > 1e-7 else 'empate')
                counts[key] += 1
            self.quant_counts[regime] = dict(counts)
            for task, horizons in base.TAREFAS.items():
                for horizon in horizons:
                    rank = self.selected[regime].loc[(self.selected[regime].tarefa == task) &
                                                      (self.selected[regime].horizonte == horizon)]
                    rank = rank.sort_values(['MAE_wm2', 'modelo'], kind='stable')
                    assert len(rank) == len(MODELS)
                    self.rankings[regime, task, horizon] = rank
                for pos, record in enumerate(self.rank(regime, task).to_dict('records'), 1):
                    record.update(posicao=pos, modelo_exibido=label(record['modelo']))
                    self.selected_rows.append(record)
        for task in base.TAREFAS:
            short = self.full[base.REGIMES[2]].loc[self.full[base.REGIMES[2]].tarefa == task]
            long = self.full[base.REGIMES[1]].loc[self.full[base.REGIMES[1]].tarefa == task]
            merged = short.merge(long, on=['tarefa', 'modelo', 'variante', 'horizonte'],
                                 suffixes=('_curto', '_longo'), validate='one_to_one')
            assert len(merged) == len(MODELS) * len(base.VARIANTES)
            for field in ('N_localidades', 'N_pontos', 'N_origens'):
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
        pairing_path = REL / 'auditoria_pareamento_historico/pareamento.json'
        pairing = json.loads(pairing_path.read_text(encoding='utf-8'))
        assert pairing['ok'] and pairing['publicavel']
        assert all(r['observacoes_e_datas_iguais'] for r in pairing['resultados'])
        self.sources[str(pairing_path)] = sha(pairing_path)
        assert len(self.selected_rows) == len(MODELS) * len(base.TAREFAS) * len(base.REGIMES)

    def rank(self, regime, task, horizon=None):
        return self.rankings[regime, task, horizon or max(base.TAREFAS[task])]

    def baseline(self, regime, task, model):
        frame = self.full[regime]
        return float(frame.loc[(frame.tarefa == task) & (frame.modelo == model) &
                               (frame.variante == 'sem_quantizacao'), 'MAE_wm2'].iloc[0])


class ArticlePDF(base.PDF):
    def __init__(self, path):
        super().__init__(path)
        self.c.setTitle(TITLE + ' - Quantização de GHI')
        self.c.setSubject(', '.join(label(model) for model in MODELS))

    def start(self, title, subtitle):
        self.page += 1
        if len(MODELS) == 3 and title == 'Três menores MAEs por horizonte':
            title = 'Classificação dos modelos por horizonte'
        self.c.setFillColor(base.INK)
        self.c.setFont('ReportArialBold', 17)
        self.c.drawString(base.M, base.H - 23, TITLE)
        self.c.setFont('ReportArialBold', 12)
        self.c.drawString(base.M, base.H - 42, title)
        intro = PAGE_INTROS[self.page - 1].replace('seis modelos', model_count_text() + ' modelos')
        if len(MODELS) == 3 and self.page == 8:
            intro = intro.replace('os três menores MAEs entre os três modelos', 'a classificação dos três modelos pelo MAE')
        bottom = base.PDF.paragraph(self, intro, base.M, base.H - 51, base.WIDTH,
                                    size=9, leading=11, color=base.MUTED)
        if bottom < base.H - 83:
            raise ValueError('A explicação inicial deve ocupar no máximo duas linhas.')
        self.c.setStrokeColor(base.LINE)
        self.c.line(base.M, base.H - 77, base.W - base.M, base.H - 77)
        bookmark = f'pagina_{self.page}'
        self.c.bookmarkPage(bookmark)
        self.c.addOutlineEntry(title, bookmark, level=0)
        self.sections.append({'titulo': title, 'pagina': self.page, 'explicacao': intro})
        self.c.saveState()
        self.c.translate(0, -BODY_SHIFT)

    def cell(self, *args, **kwargs):
        previous = len(self.cells)
        result = super().cell(*args, **kwargs)
        if len(self.cells) > previous:
            self.cells[-1]['rect'][1] += BODY_SHIFT
            self.cells[-1]['rect'][3] += BODY_SHIFT
        return result

    def paragraph(self, text, x, top, width, *args, **kwargs):
        footer = top < 90
        if footer:
            self.c.saveState()
            self.c.translate(0, BODY_SHIFT)
        result = super().paragraph(text, x, top, width, *args, **kwargs)
        if footer:
            self.c.restoreState()
        else:
            self.blocks[-1]['rect'][1] += BODY_SHIFT
            self.blocks[-1]['rect'][3] += BODY_SHIFT
        return result

    def end(self):
        self.c.restoreState()
        super().end()

    def table(self, title, headers, rows, *args, **kwargs):
        if len(rows) == len(MODELS) and kwargs.get('row_h') == 14.4:
            kwargs['row_h'] = 32 if len(MODELS) == 3 else 22
            kwargs['size'] = max(kwargs.get('size', 9), 10 if len(MODELS) == 3 else 9.3)
        if len(rows) == 12 and kwargs.get('row_h') == 37.5:
            kwargs['row_h'] = 37
        return super().table(title, headers, rows, *args, **kwargs)


def ranking_page(pdf, data, regime, block):
    test = 'Teste em 2024' if regime == 'atual' else 'Teste de abril/2019 a dezembro/2022'
    pdf.start(f'{block}. {base.REG_LABEL[regime]} - classificação dos modelos',
              test + f' | Posição entre os {model_count_text()} modelos pelo MAE | Entrada escolhida na validação')
    for index, task in enumerate(base.TAREFAS):
        frame = data.rank(regime, task)
        rows, keys = [], []
        best_rmse = int(frame.RMSE_wm2.to_numpy().argmin())
        for pos, record in enumerate(frame.itertuples(), 1):
            delta = 100 * (record.MAE_wm2 - data.baseline(regime, task, record.modelo)) / data.baseline(regime, task, record.modelo)
            rows.append([pos, label(record.modelo), base.condition(record.variante), base.fmt(record.MAE_wm2),
                         base.fmt(record.RMSE_wm2), base.fmt(record.R2, 3), base.fmt(delta, 3, signed=True)])
            key = [regime, task, record.modelo, record.variante, record.horizonte]
            keys.append([None, None, None] + [{'registro': key, 'metrica': metric}
                         for metric in ('MAE_wm2', 'RMSE_wm2', 'R2', 'delta_quant_pct')])
        pdf.table(base.TASK_LABEL[task], ['Pos.', 'Modelo', 'Entrada', 'MAE', 'RMSE', 'R²', 'Delta %'], rows,
                  base.M + (index % 2) * (base.HALF + base.GAP), base.H - 67 - (index // 2) * 226,
                  [27, 92, 44, 61, 61, 44, base.HALF - 329], row_h=14.4, header_h=18,
                  bold_rows=(0,), marks={(best_rmse, 4): base.BEST},
                  aligns=['center', 'left', 'center', 'right', 'right', 'right', 'right'], size=8.9, keys=keys)
    leaders = [label(str(data.rank(regime, task).iloc[0].modelo)) for task in base.TAREFAS]
    text = (f'Menor MAE entre os {model_count_text()} modelos: horário - {leaders[0]}; diário - {leaders[1]}; '
            f'um mês - {leaders[2]}; seis meses - {leaders[3]}. A primeira posição e o menor RMSE estão destacados.')
    pdf.paragraph(text, base.M, 83, base.WIDTH, size=9.1, leading=12)
    pdf.paragraph('Sem: ausência de quantização. Entrada 64/128/256: número de níveis. Delta %: diferença do MAE selecionado em relação ao controle do mesmo modelo; '
                  f'negativo indica redução. Classificações restritas aos modelos para {"a disciplina" if AUDIENCE == "disciplina" else "o artigo"}.',
                  base.M, 52, base.WIDTH, size=8.1, leading=10.5)
    pdf.end()


def history_control(pdf, data):
    pdf.start('4. Histórico longo versus curto - sem quantização',
              'Mesmas origens, alvos e localidades | Horizonte completo | Delta = longo - curto')
    for index, task in enumerate(base.TAREFAS):
        frame = data.history[task].loc[data.history[task].variante == 'sem_quantizacao'].sort_values(['delta', 'modelo'])
        rows, keys = [], []
        for record in frame.itertuples():
            rows.append([label(record.modelo), base.fmt(record.MAE_wm2_curto), base.fmt(record.MAE_wm2_longo),
                         base.fmt(record.delta, signed=True), base.fmt(record.delta_pct, 2, signed=True)])
            keys.append([None] + [{'comparacao': [task, record.modelo, 'sem_quantizacao'], 'metrica': metric}
                         for metric in ('MAE_curto', 'MAE_longo', 'delta', 'delta_pct')])
        pdf.table(base.TASK_LABEL[task], ['Modelo', 'MAE curto', 'MAE longo', 'Delta W/m²', 'Delta %'], rows,
                  base.M + (index % 2) * (base.HALF + base.GAP), base.H - 67 - (index // 2) * 226,
                  [95, 65, 65, 78, base.HALF - 303], row_h=14.4, header_h=18, size=9, keys=keys)
    counts = {key: sum(value[key] for value in data.history_counts.values()) for key in ('melhora', 'piora', 'empate')}
    pdf.paragraph(f'Entre as {len(MODELS) * len(base.TAREFAS)} comparações dos modelos para {"a disciplina" if AUDIENCE == "disciplina" else "o artigo"}, '
                  f'o histórico longo teve menor MAE em {counts["melhora"]}, '
                  f'maior em {counts["piora"]} e empate numérico em {counts["empate"]}. A piora ocorreu na LSTM horária de 72 h.',
                  base.M, 83, base.WIDTH, size=9.2, leading=12)
    pdf.paragraph('Delta negativo favorece o longo. Empate numérico: diferença absoluta de até 0,0000001 W/m². '
                  'Mantém-se a condição sem quantização nos dois históricos. Os resultados são descritivos e não estabelecem causa climática.',
                  base.M, 52, base.WIDTH, size=8.1, leading=10.5)
    pdf.end()


def article_chart(data, directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    from matplotlib.ticker import FuncFormatter, MaxNLocator
    directory.mkdir(parents=True, exist_ok=True)
    font_manager.fontManager.addfont('C:/Windows/Fonts/arial.ttf')
    plt.rcParams.update({'font.family': 'Arial', 'font.size': 9, 'pdf.fonttype': 42, 'axes.unicode_minus': False})
    figure, axes = plt.subplots(2, 2, figsize=(base.WIDTH / 72, 460 / 72), layout='constrained')
    records = []
    for axis, task in zip(axes.flat, base.TAREFAS, strict=True):
        frame = data.rank('atual', task)
        values = frame.MAE_wm2.to_numpy()
        names = [label(m) for m in frame.modelo]
        axis.barh(range(len(MODELS)), values, color=['#218A8A'] + ['#91A9BA'] * (len(MODELS) - 1), height=.63)
        axis.set_yticks(range(len(MODELS)), names)
        axis.invert_yaxis()
        axis.set_xlim(0, max(values) * 1.25)
        axis.set_title(base.TASK_LABEL[task], loc='left', fontsize=10.5, fontweight='bold', pad=10)
        axis.set_xlabel('MAE (W/m²)', fontsize=9)
        axis.xaxis.set_major_formatter(FuncFormatter(lambda value, _: base.fmt(value, 0)))
        axis.xaxis.set_major_locator(MaxNLocator(nbins=4))
        axis.set_axisbelow(True)
        axis.grid(axis='x', color='#E4EBF0', linewidth=.6)
        axis.tick_params(axis='both', length=0, labelsize=9)
        for spine in axis.spines.values():
            spine.set_visible(False)
        for y, record in enumerate(frame.itertuples()):
            axis.text(record.MAE_wm2 + max(values) * .025, y, base.fmt(record.MAE_wm2), va='center', fontsize=8.4)
            records.append({'regime': 'atual', 'tarefa': task, 'modelo': record.modelo,
                            'variante': record.variante, 'horizonte': record.horizonte, 'MAE_wm2': record.MAE_wm2})
    paths = {ext: directory / f'mae_modelos_{AUDIENCE}.{ext}' for ext in ('pdf', 'png', 'svg')}
    for ext, path in paths.items():
        figure.savefig(path, dpi=180 if ext == 'png' else 150, facecolor='white')
    plt.close(figure)
    assert len(records) == len(MODELS) * len(base.TAREFAS)
    return {'arquivos': {ext: str(path) for ext, path in paths.items()}, 'registros': records}


def generate():
    if OUTPUT.exists() or REPORT.exists():
        raise ValueError('Use destinos novos; os relatórios existentes devem ser preservados.')
    preserved_paths = [p for p in (ROOT / 'output/pdf').glob('*.pdf')]
    preserved = {str(p): sha(p) for p in preserved_paths}
    data = ArticleData()
    REPORT.mkdir(parents=True)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont('ReportArial', 'C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('ReportArialBold', 'C:/Windows/Fonts/arialbd.ttf'))
    pdfmetrics.registerFontFamily('ReportArial', normal='ReportArial', bold='ReportArialBold',
                                italic='ReportArial', boldItalic='ReportArialBold')
    base.MODELOS = MODELS
    base.model_label = label
    intermediate = REPORT / 'tabelas_base.pdf'
    pdf = ArticlePDF(intermediate)
    ranking_page(pdf, data, 'atual', 1)
    base.quantization_current(pdf, data)
    ranking_page(pdf, data, 'historico_1998_2022', 2)
    ranking_page(pdf, data, 'historico_curto_pareado', 3)
    history_control(pdf, data)
    base.history_quantized(pdf, data, list(base.TAREFAS)[:2])
    base.history_quantized(pdf, data, list(base.TAREFAS)[2:])
    base.horizons(pdf, data)
    base.periods_page(pdf)
    pdf.start(f'MAE dos {model_count_text()} modelos por tarefa',
              'Base 2019-2024 | Teste em 2024 | Entrada escolhida na validação | Horizonte completo')
    pdf.paragraph(f'São apresentados os {model_count_text()} modelos para {"a disciplina" if AUDIENCE == "disciplina" else "o artigo"}. '
                  'As barras partem de zero, e cada tarefa tem sua própria escala. '
                  'O menor MAE está destacado em verde. A tarefa de seis meses é exploratória.',
                  base.M, 48, base.WIDTH, size=8.3, leading=10.5)
    pdf.end()
    assert pdf.page == 10
    pdf.c.save()
    chart = article_chart(data, REPORT / 'grafico')
    with pymupdf.open(intermediate) as doc, pymupdf.open(chart['arquivos']['pdf']) as graph:
        doc[-1].show_pdf_page(pymupdf.Rect(base.M, 86, base.W - base.M, base.H - 68), graph, 0)
        doc.save(OUTPUT, garbage=4, deflate=True)
    for path, expected in {**data.sources, **preserved}.items():
        assert sha(path) == expected, path
    pd.concat(data.frames.values(), ignore_index=True).to_csv(REPORT / f'metricas_teste_modelos_{AUDIENCE}.csv', index=False, encoding='utf-8-sig')
    pd.DataFrame(data.selected_rows).to_csv(REPORT / f'classificacoes_modelos_{AUDIENCE}.csv', index=False, encoding='utf-8-sig')
    manifest = {'gerado_em_utc': datetime.now(timezone.utc).isoformat(),
                'titulo': TITLE, 'modelos': list(MODELS), 'rotulos': [label(m) for m in MODELS],
                'pdf': {'path': str(OUTPUT), 'sha256': sha(OUTPUT), 'paginas': 10},
                'fontes_sha256': data.sources, 'pdfs_preservados_sha256': preserved,
                'auditorias_origem': data.audits, 'rankings_selecionados': data.selected_rows,
                'escolhas_validacao': {reg: [dict(tarefa=t, modelo=m, variante=v) for (t, m), v in choices.items()]
                                      for reg, choices in data.choices.items()},
                'linhas_teste': sum(len(frame) for frame in data.frames.values()),
                'classificacoes': len(data.selected_rows), 'comparacoes_historicas': sum(len(frame) for frame in data.history.values()),
                'contagens_quantizacao': data.quant_counts, 'contagens_historico_sem_quantizacao': data.history_counts,
                'secoes': pdf.sections, 'celulas_pdf': pdf.cells, 'textos_pdf': pdf.blocks,
                'grafico': chart, 'gerador_sha256': sha(Path(__file__)), 'revisao_visual_pendente': True,
                'criterio': f'Classificação entre {model_count_text()} modelos pelo MAE do teste, mantendo a escolha original da validação.'}
    (REPORT / 'manifesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'pdf': str(OUTPUT), 'paginas': 10, 'modelos': manifest['rotulos'],
                      'classificacoes': manifest['classificacoes'], 'comparacoes_historicas': manifest['comparacoes_historicas']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida', type=Path, default=OUTPUT)
    parser.add_argument('--relatorio', type=Path, default=REPORT)
    parser.add_argument('--perfil', choices=('artigo', 'disciplina'), default='artigo')
    args = parser.parse_args()
    AUDIENCE = args.perfil
    if AUDIENCE == 'disciplina':
        MODELS = ('Transformer', 'Informer', 'LSTM')
        TITLE = 'Modelos para a disciplina'
    OUTPUT, REPORT = args.saida.absolute(), args.relatorio.absolute()
    if not OUTPUT.is_relative_to(ROOT) or not REPORT.is_relative_to(ROOT):
        raise ValueError('As saídas devem permanecer dentro do projeto.')
    generate()
