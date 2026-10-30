"""PDF compacto novo, a partir dos resultados apresentados e auditados.

Nao altera PDFs originais, motores, dados, escolhas ou artefatos de treinamento.
O marcador PDF deve ser executado uma vez antes da primeira autoria.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos import numero
from codigo_fonte.acompanhamento.metricas_quantizacao_todos import MODELOS, TAREFAS, VARIANTES

ROOT = Path(__file__).resolve().parents[2]
REL = ROOT / 'resultados/relatorios/quantizacao_todos_modelos_20260929'
REGIMES = ('atual', 'historico_1998_2022', 'historico_curto_pareado')
LABELS = {'atual': 'Base 2019-2024 - teste de 2024',
          'historico_1998_2022': 'Histórico longo 1998-2022',
          'historico_curto_pareado': 'Histórico curto pareado - início em abril de 2014'}
CASES = {'hourly_72_extension': 'Horário', 'daily_30': 'Diário',
         'monthly_1': 'Mensal de um mês', 'monthly_6': 'Mensal exploratório de seis meses'}
LEVELS = {'sem_quantizacao': 'Sem quantização', 'q64': '64 níveis', 'q128': '128 níveis', 'q256': '256 níveis'}
ORIGINALS = {
    ROOT / 'documentacao/tabela_resultados_ghi_2024.pdf': '155e58187c1da01d6030334d086933bf0f200d13cb02d60c0db76b28b7bac776',
    ROOT / 'documentacao/tabela_resultados_ghi_1998_2022.pdf': '03890694608a7d07a039c8379f69898c30c81839352f83e3cf4a1f88c3f9605c',
}
W, H = landscape(A4)
MARGIN, GAP = 20, 16
WIDTH = W - 2 * MARGIN
PANEL_WIDTH = (WIDTH - GAP) / 2
ROW_H, HEADER_H, TITLE_H = 9.6, 10.6, 12
PANEL_H = TITLE_H + HEADER_H + 11 * ROW_H
INK = colors.HexColor('#19364E')
BLUE = colors.HexColor('#E2EBF2')
PALE = colors.HexColor('#F3F6F9')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def local_output(path):
    path = Path(path)
    result = path.parent.resolve() / path.name
    if not result.is_relative_to(ROOT) or result in ORIGINALS:
        raise ValueError('Saida deve ser nova e dentro do projeto.')
    return result


def source_data():
    for path, sha in ORIGINALS.items():
        if digest(path) != sha:
            raise ValueError(f'PDF original divergiu: {path}')
    manifests = [REL / 'pdf_atual/manifesto.json', REL / 'pdf_historico/manifesto.json']
    sources, tables = {}, []
    for path in manifests:
        m = load(path)
        sources[str(path)] = digest(path)
        if digest(m['pdf']['path']) != m['pdf']['sha256']:
            raise ValueError('PDF de origem divergiu do manifesto.')
        sources[m['pdf']['path']] = m['pdf']['sha256']
        for s in m['fontes']:
            if digest(s['path']) != s['sha256']:
                raise ValueError(f'Fonte alterada: {s["path"]}')
            sources[s['path']] = s['sha256']
        tables.extend(m['tabelas'])
    if len(tables) != 48:
        raise ValueError('Esperadas 48 tabelas originais completas.')
    frames, audits, choices = {}, {}, {}
    for regime, folder in zip(REGIMES, ('auditoria_final_atual', 'auditoria_historico_1998_2022',
                                       'auditoria_historico_curto_pareado'), strict=True):
        path = REL / folder / 'auditoria.json'
        a = load(path)
        if not all(a.get(k) is True for k in ('ok', 'publicavel', 'escopo_completo', 'replay_novo_executado')):
            raise ValueError('Auditoria incompleta.')
        if a['modo'] != 'completa' or a['pares_verificados'] != 44 or a['regime'] != regime:
            raise ValueError('Escopo da auditoria divergente.')
        df = pd.read_csv(a['metricas']['path'])
        if digest(a['metricas']['path']) != a['metricas']['sha256']:
            raise ValueError('CSV auditado alterado.')
        keycols = ['tarefa', 'modelo', 'variante', 'particao', 'horizonte']
        expected = {(t, m, v, p, h) for t, hs in TAREFAS.items() for m in MODELOS
                    for v in VARIANTES for p in ('validacao', 'teste') for h in hs}
        if df.duplicated(keycols).any() or set(df[keycols].itertuples(index=False, name=None)) != expected:
            raise ValueError('Grade de metricas incompleta ou duplicada.')
        if set(df.regime) != {regime} or set(df.N_localidades) != {10}:
            raise ValueError('Regime/localidades divergentes.')
        choices[regime] = {(r['tarefa'], r['modelo']): r['vencedor_validacao'] for r in a['resultados']}
        if len(choices[regime]) != 44:
            raise ValueError('Escolhas de validacao incompletas.')
        audits[regime] = {'path': str(path), 'sha256': digest(path), 'pares': 44}
        frames[regime] = df[df.particao == 'teste'].set_index(['tarefa', 'modelo', 'variante', 'horizonte'])
    rows, seen = [], set()
    for t in tables:
        regime, task, level = t['regime'], t['tarefa'], t['variante']
        for r in t['linhas']:
            model, horizon = r['modelo'], r['horizonte']
            key = (regime, task, model, level, horizon)
            if key in seen:
                raise ValueError('Linha duplicada nos manifestos originais.')
            seen.add(key)
            raw = frames[regime].loc[(task, model, level, horizon)]
            control = frames[regime].loc[(task, model, 'sem_quantizacao', horizon), 'MAE_wm2']
            delta = 100 * (raw.MAE_wm2 - control) / control if control else float('nan')
            chosen = choices[regime][task, model] == level
            values = [numero(raw.MAE_wm2), numero(raw.MSE_w2m4, 2), numero(raw.RMSE_wm2),
                      numero(100 * raw.nRMSE, 3), numero(raw.R2), ('+' if delta > 0 else '') + numero(delta, 4)]
            if r['valores_exibidos'][2:] != values or r['escolhido_validacao'] != chosen:
                raise ValueError(f'Valor exibido original divergente do CSV: {key}')
            rows.append({'regime': regime, 'tarefa': task, 'modelo': model, 'variante': level,
                         'horizonte': horizon, 'modelo_exibido': r['valores_exibidos'][1],
                         'valores': values, 'escolhido_validacao': chosen})
    expected_rows = {(reg, t, m, v, h) for reg in REGIMES for t, hs in TAREFAS.items()
                     for m in MODELOS for v in VARIANTES for h in hs}
    if seen != expected_rows or len(rows) != 1584:
        raise ValueError('Compactacao omitiu registros originais.')
    pairing = load(REL / 'auditoria_pareamento_historico/pareamento.json')
    if pairing['ok'] is not True or pairing['publicavel'] is not True:
        raise ValueError('Pareamento nao aprovado.')
    if len(pairing['resultados']) != 8 or not all(r['observacoes_e_datas_iguais'] is True for r in pairing['resultados']):
        raise ValueError('Datas e observacoes nao pareadas.')
    pairs = []
    for task in TAREFAS:
        h = max(TAREFAS[task])
        for model in sorted(MODELOS):
            for level in VARIANTES:
                k = (task, model, level, h)
                long, short = frames[REGIMES[1]].loc[k], frames[REGIMES[2]].loc[k]
                if any(long[c] != short[c] for c in ('N_localidades', 'N_origens', 'N_pontos')):
                    raise ValueError('Comparacao com tamanhos de amostra diferentes.')
                pairs.append({'tarefa': task, 'modelo': model, 'variante': level,
                              'MAE_curto': numero(short.MAE_wm2), 'MAE_longo': numero(long.MAE_wm2),
                              'delta_wm2': numero(long.MAE_wm2 - short.MAE_wm2)})
    if len(pairs) != 176:
        raise ValueError('Comparacao pareada incompleta.')
    return rows, pairs, choices, sources, audits


class Builder:
    def __init__(self, path, *, somente_tabelas=False):
        self.c = canvas.Canvas(str(path), pagesize=(W, H), pageCompression=1)
        self.c.setTitle('Quantização de GHI - relatório unificado compacto')
        self.c.setAuthor('Gustavo de Melo Nascimento - Projeto TCC')
        self.page = 0
        self.somente_tabelas = somente_tabelas
        self.cells = []
        self.sections = []
        self.body_style = ParagraphStyle('CompactBody', fontName='CompactArial', fontSize=9.1,
                                         leading=12, textColor=INK, spaceAfter=4)

    def start(self, title, sub, bookmark):
        self.page += 1
        self.c.setFillColor(INK)
        self.c.setFont('CompactArialBold', 12)
        self.c.drawString(MARGIN, H - 21, title)
        self.c.setFont('CompactArial', 8.1)
        self.c.drawString(MARGIN, H - 34, sub)
        self.c.bookmarkPage(bookmark)
        self.c.addOutlineEntry(title, bookmark, level=0)
        self.sections.append({'titulo': title, 'pagina': self.page})

    def end(self, metrics=False):
        self.c.setFillColor(colors.HexColor('#526A7D'))
        self.c.setFont('CompactArial', 7.1)
        note = ('MAE/RMSE: W/m² | MSE: (W/m²)² | nRMSE/Delta: % | R²: adimensional | * escolha da validação.'
                if metrics else ('Projeto GHI | Comparação dos históricos longo e curto'
                                 if self.somente_tabelas else
                                 'Projeto GHI | Conteúdo completo dos dois PDFs auditados | Originais preservados'))
        self.c.drawString(MARGIN, 16, note)
        self.c.drawRightString(W - MARGIN, 16, str(self.page))
        self.c.showPage()

    def paragraphs(self, columns):
        for i, paragraphs in enumerate(columns):
            x, top = MARGIN + i * (PANEL_WIDTH + GAP), H - 53
            for text in paragraphs:
                p = Paragraph(text, self.body_style)
                _, height = p.wrap(PANEL_WIDTH, H)
                if top - height < 34:
                    raise ValueError('Texto metodologico nao cabe com legibilidade.')
                p.drawOn(self.c, x, top - height)
                top -= height + 6

    def draw_cell(self, text, x, bottom, width, height, *, bold=False, right=True,
                  font_size=7.7, track=None):
        font = 'CompactArialBold' if bold else 'CompactArial'
        if pdfmetrics.stringWidth(str(text), font, font_size) > width - 5:
            raise ValueError(f'Celula nao cabe: {text}')
        self.c.setFont(font, font_size)
        self.c.setFillColor(INK)
        baseline = bottom + 2.15
        if right:
            self.c.drawRightString(x + width - 3, baseline, str(text))
        else:
            self.c.drawString(x + 3, baseline, str(text))
        if track is not None:
            self.cells.append({'pagina': self.page, 'rect': [x, H - bottom - height, x + width, H - bottom],
                               'texto': str(text), 'registro': track})

    def panel(self, rows, x, top, task, level, horizon):
        unit = 'h' if task.startswith('hourly') else 'd' if task.startswith('daily') else ('mês' if horizon == 1 else 'meses')
        title = f'{CASES[task]} | {LEVELS[level]} | {horizon} {unit}'
        self.c.setFillColor(INK)
        self.c.rect(x, top - TITLE_H, PANEL_WIDTH, TITLE_H, fill=1, stroke=0)
        self.c.setFillColor(colors.white)
        self.c.setFont('CompactArialBold', 8)
        self.c.drawString(x + 4, top - 8.5, title)
        widths = [79, 48, 63, 51, 45, 39, PANEL_WIDTH - 325]
        headers = ['Modelo', 'MAE', 'MSE', 'RMSE', 'nRMSE', 'R²', 'Delta MAE %']
        cursor, bottom = x, top - TITLE_H - HEADER_H
        self.c.setFillColor(BLUE)
        self.c.rect(x, bottom, PANEL_WIDTH, HEADER_H, fill=1, stroke=0)
        for j, (head, width) in enumerate(zip(headers, widths, strict=True)):
            self.draw_cell(head, cursor, bottom, width, HEADER_H, bold=True, right=j > 0, font_size=7.1)
            cursor += width
        for i, row in enumerate(rows):
            bottom -= ROW_H
            self.c.setFillColor(PALE if i % 2 == 0 else colors.white)
            self.c.rect(x, bottom, PANEL_WIDTH, ROW_H, fill=1, stroke=0)
            cursor = x
            key = [row[k] for k in ('regime', 'tarefa', 'modelo', 'variante', 'horizonte')]
            for j, (text, width) in enumerate(zip([row['modelo_exibido']] + row['valores'], widths, strict=True)):
                self.draw_cell(text, cursor, bottom, width, ROW_H,
                               bold=j == 0 and row['escolhido_validacao'], right=j > 0,
                               track={'chave': key, 'coluna': j})
                cursor += width

    def compare(self, pairs, task, top):
        self.c.setFillColor(INK)
        self.c.setFont('CompactArialBold', 10)
        self.c.drawString(MARGIN, top, f'{CASES[task]} - horizonte completo')
        top -= 8
        model_w = 113
        cell_w = (WIDTH - model_w) / 12
        group_w = 3 * cell_w
        self.c.setFillColor(INK)
        self.c.rect(MARGIN, top - 15, WIDTH, 15, fill=1, stroke=0)
        self.c.setFillColor(colors.white)
        self.c.setFont('CompactArialBold', 8.3)
        self.c.drawString(MARGIN + 3, top - 11, 'Modelo')
        for i, level in enumerate(VARIANTES):
            self.c.drawCentredString(MARGIN + model_w + (i + .5) * group_w, top - 11, LEVELS[level])
        bottom = top - 28
        self.c.setFillColor(BLUE)
        self.c.rect(MARGIN, bottom, WIDTH, 13, fill=1, stroke=0)
        for i in range(4):
            for j, text in enumerate(('MAE curto', 'MAE longo', 'Delta W/m²')):
                x = MARGIN + model_w + (3 * i + j) * cell_w
                self.draw_cell(text, x, bottom, cell_w, 13, bold=True, font_size=7.5)
        by_key = {(r['modelo'], r['variante']): r for r in pairs if r['tarefa'] == task}
        for i, model in enumerate(sorted(MODELOS)):
            bottom -= 13
            self.c.setFillColor(PALE if i % 2 == 0 else colors.white)
            self.c.rect(MARGIN, bottom, WIDTH, 13, fill=1, stroke=0)
            self.draw_cell(model, MARGIN, bottom, model_w, 13, right=False, font_size=8)
            for j, level in enumerate(VARIANTES):
                row = by_key[model, level]
                for k, column in enumerate(('MAE_curto', 'MAE_longo', 'delta_wm2')):
                    x = MARGIN + model_w + (3 * j + k) * cell_w
                    self.draw_cell(row[column], x, bottom, cell_w, 13, font_size=8,
                                   track={'comparacao': [task, model, level], 'coluna': column})


INTRO = [
    [
        '<b>Escopo completo.</b> Onze modelos, quatro casos e quatro condições de entrada: min-max sem quantização, 64, 128 e 256 níveis. As 48 tabelas originais são reorganizadas em 144 painéis por caso, nível e horizonte, preservando todas as 1.584 linhas de teste. Os históricos têm ainda 176 comparações pareadas. Os dois PDFs anteriores permanecem intactos.',
        '<b>Base atual 2019-2024.</b> Ajuste antes de 2023; validação em 2023; treinamento final até 2023; teste em 2024. O teste de 2024 já havia sido consultado em estudos anteriores: esta análise é retrospectiva. As escolhas dos níveis usam a validação.',
        '<b>Controles atuais.</b> A TimesNet pura otimizada reutiliza experimentos completos e auditados. Os concorrentes têm seus próprios controles. LSTM, GRU e DilatedRNN horários/diários usam novos controles GPU no mesmo dispositivo das variantes. A climatologia horária foi acrescentada. O ARIMA horário usa novo controle de validação reproduzido e auditado; a pequena divergência com o ajuste histórico está documentada.',
        '<b>XGBoost horário atual.</b> O novo controle sem quantização foi repetido integralmente e auditado. A execução antiga divergiu por causa não identificada. A seleção dos níveis permaneceu congelada e as variantes são comparadas ao controle reexecutado; diferenças com o antigo não são atribuídas à quantização.',
        '<b>Resumo atual.</b> Pelas escolhas da validação, 13 pares tiveram menor MAE no teste e 21 maior; em 10, manteve-se o controle sem quantização. Não houve ganho uniforme. A maior redução entre escolhas quantizadas foi de 2,63% no ARIMA mensal exploratório de seis meses. São resultados descritivos, sem teste de significância.',
    ],
    [
        '<b>Históricos nas mesmas datas.</b> Longo: início em janeiro de 1998; curto: abril de 2014. Validação: abril de 2018 a março de 2019; teste: abril de 2019 a dezembro de 2022, últimos 45 dos 300 meses (15%). O ajuste longo usa dados até março de 2018 e o refit até março de 2019. Ambos têm as mesmas origens, alvos e dez localidades.',
        '<b>Cortes horários históricos.</b> Fuso local fixo; 1.368 origens de teste por localidade. A última é 28/12/2022, com alvos até 30/12 às 23h locais. A fonte não cobre o horizonte local completo da origem seguinte, excluída em ambos os históricos, sem imputação nem dados de 2023.',
        '<b>Resumo pareado.</b> No horizonte completo, sem quantização, o longo teve menor MAE em 34 dos 44 pares, maior em 2 e diferença praticamente nula em 8. Empate numérico: diferença absoluta até 0,0000001 W/m². A comparação mantém modelo, nível e teste fixos; não demonstra causa climática. As localidades e o protocolo diferem dos do artigo do Luís; não é reprodução integral desse estudo.',
        '<b>Auditoria e leitura.</b> Os três regimes passaram por auditoria completa dos 44 pares, recálculo independente de 1.056 linhas de validação/teste e reprodução dos novos checkpoints. O pareamento foi aprovado. Pequenas diferenças numéricas não são teste de significância. Os modelos e configurações foram definidos anteriormente; também o estudo histórico é retrospectivo.',
        '<b>Mapa do documento.</b> Método e interpretação: páginas 1-2. Base atual: 3-8. Histórico longo: 9-14. Histórico curto: 15-20. Comparação pareada de todos os níveis: 21-22. Os painéis são agrupados por nível; o horizonte aparece no título. O asterisco marca a escolha da validação no horizonte completo, sem escolher novamente pelo teste.',
    ],
]
METHOD = [
    [
        '<b>Min-max e quantização.</b> Ajuste por localidade, somente nos dados permitidos para treino de cada fase. Após min-max, as entradas são limitadas a [0, 1] e arredondadas para N níveis uniformes, incluindo os extremos: rint(clip(x, 0, 1) × (N − 1)) / (N − 1). O controle conserva min-max sem clipping nem arredondamento.',
        '<b>Redes e XGBoost.</b> Entradas de GHI quantizadas no treino e na previsão. Alvos, pesos, saídas e identificadores das localidades não são quantizados.',
        '<b>ARIMA.</b> Quantiza a série histórica endógena usada no ajuste e os contextos usados na previsão. A ordem é selecionada por localidade pelo MSE normalizado na validação do controle e mantida entre níveis; os coeficientes são reajustados. Os valores reais avaliados permanecem contínuos.',
        '<b>Referências simples.</b> Persistência, sazonal ingênuo e climatologia aplicam suas regras ao histórico quantizado. A climatologia usa somente dados anteriores ao corte de ajuste. Nas referências, o histórico é reconvertido para W/m² antes da regra; nos modelos ajustados, a saída é reconvertida após prever.',
        '<b>Sementes e pós-processamento.</b> Redes horárias: semente 42. Diário e mensais: 11, 23, 42, 67 e 89. A média das previsões brutas precede o piso zero; no horário usa-se a mesma máscara noturna. Referências aplicam regras fixas, e o ARIMA estima coeficientes numericamente; não usam sementes ou épocas de redes.',
        '<b>Execução numérica.</b> Transformer e Informer horários/diários usam novos controles com determinismo estrito, preservando arquitetura, parâmetros e dados entre níveis. Os controles antigos permanecem preservados. Diferenças de execução numérica não são atribuídas à quantização. A política é a mesma nos dois históricos.',
    ],
    [
        '<b>Métricas físicas.</b> MAE e RMSE em W/m²; MSE em (W/m²)²; nRMSE em %. Cada métrica é calculada por localidade e depois promediada. O nRMSE divide o RMSE pela média de GHI observada em cada localidade; apresenta-se a média dessas razões em porcentagem. R² é adimensional e pode ser negativo. Não se obtém o macro-RMSE pela raiz do macro-MSE.',
        '<b>Horizontes cumulativos.</b> Horário: 24, 48 e 72 h; diário: 1, 3, 7, 14 e 30 d; mensal de um mês: 1 mês; mensal exploratório de seis meses: 1, 3 e 6 meses. Todos os horizontes dos originais são mantidos. Em cada painel, a ordenação pelo MAE do teste é apenas descritiva.',
        '<b>Deltas e escolhas.</b> Delta MAE % = 100 × (MAE da variante − MAE do controle) / MAE do controle, para o mesmo modelo/caso/horizonte/regime. Positivo indica piora. Na comparação entre históricos, Delta W/m² = MAE longo − MAE curto; negativo favorece o longo. O asterisco assinala a escolha feita na validação, considerando o horizonte completo.',
        '<b>Clipping e interpretação.</b> O experimento mede conjuntamente clipping e arredondamento, sem controle separado de clipping. Diagnósticos contam posições em janelas sobrepostas; no ARIMA contam também a série de ajuste. Essas contagens não são observações independentes nem cobrem automaticamente todo o histórico das referências.',
        '<b>Agregação histórica.</b> Horário: média de duas amostras de 30 minutos. Diário: definição original da coleta API, com amostras no meio da hora, fuso fixo local e tratamento da fronteira anual registrado na auditoria. Mensal: média dos valores diários. A sobreposição com a base anterior foi conferida. O tratamento anual original foi preservado e difere de agregação física contínua em algumas fronteiras de ano.',
        '<b>Integridade.</b> Valores, sinais, casas decimais e escolhas foram conferidos contra os manifestos dos PDFs originais e os CSVs auditados. A compactação altera somente a apresentação. Os dois PDFs originais, dados e resultados de treinamento foram preservados por SHA-256.',
    ],
]


def generate(output, manifest_path, *, somente_tabelas=False):
    output, manifest_path = local_output(output), local_output(manifest_path)
    if output.exists() or manifest_path.exists():
        raise ValueError('Nao sobrescrever artefatos existentes; use nova saida para cada revisao.')
    rows, pairs, choices, sources, audits = source_data()
    pdfmetrics.registerFont(TTFont('CompactArial', 'C:/Windows/Fonts/arial.ttf'))
    pdfmetrics.registerFont(TTFont('CompactArialBold', 'C:/Windows/Fonts/arialbd.ttf'))
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    b = Builder(output, somente_tabelas=somente_tabelas)
    if not somente_tabelas:
        b.start('Quantização de GHI - relatório unificado compacto',
                'Todos os modelos | Base atual e dois históricos | Resultados completos auditados | 09/10/2026', 'abertura')
        b.paragraphs(INTRO)
        b.end()
        b.start('Método, métricas e limites da comparação', 'Como ler os painéis e a comparação histórica', 'metodo')
        b.paragraphs(METHOD)
        b.end()
    panels_meta = []
    for regime in REGIMES:
        panels = []
        for task, hs in TAREFAS.items():
            for level in VARIANTES:
                for horizon in hs:
                    selected = [r for r in rows if (r['regime'], r['tarefa'], r['variante'], r['horizonte'])
                                == (regime, task, level, horizon)]
                    if len(selected) != 11:
                        raise ValueError('Painel sem todos os modelos.')
                    panels.append((task, level, horizon, selected))
        for offset in range(0, len(panels), 8):
            b.start(LABELS[regime], 'Onze modelos por painel | Todos os níveis e horizontes | * escolha da validação',
                    f'{regime}_{offset // 8 + 1}')
            for j, (task, level, horizon, selected) in enumerate(panels[offset:offset + 8]):
                x = MARGIN + (j % 2) * (PANEL_WIDTH + GAP)
                top = H - 44 - (j // 2) * (PANEL_H + 2)
                b.panel(selected, x, top, task, level, horizon)
                panels_meta.append({'regime': regime, 'tarefa': task, 'variante': level,
                                    'horizonte': horizon, 'pagina': b.page, 'linhas': selected})
            b.end(metrics=True)
    tasks = list(TAREFAS)
    for i in range(2):
        b.start('Histórico longo versus curto - mesmo teste',
                'MAE e Delta em W/m² | Delta = longo − curto; negativo favorece o longo | Sem interpretação causal',
                f'pareamento_{i + 1}')
        for j, task in enumerate(tasks[2 * i:2 * i + 2]):
            b.compare(pairs, task, H - 64 - 231 * j)
        b.end()
    expected_pages = 20 if somente_tabelas else 22
    if b.page != expected_pages or len(panels_meta) != 144 or len(b.cells) != 1584 * 7 + 176 * 3:
        raise ValueError('Contagem final de paginas/painéis/celulas divergente.')
    b.c.save()
    for path, old_sha in ORIGINALS.items():
        if digest(path) != old_sha:
            raise ValueError('PDF original alterado durante a autoria.')
    for path, source_sha in sources.items():
        if digest(path) != source_sha:
            raise ValueError('Fonte cientifica mudou durante a autoria.')
    data = {'gerado_em_utc': datetime.now(timezone.utc).isoformat(),
            'pdf': {'path': str(output), 'sha256': digest(output), 'paginas': b.page},
            'somente_tabelas': somente_tabelas,
            'originals_preservados_sha256': {str(p): v for p, v in ORIGINALS.items()},
            'fontes_sha256': sources, 'auditorias': audits,
            'linhas_resultados': len(rows), 'comparacoes_pareadas': len(pairs),
            'paineis': panels_meta, 'comparacoes': pairs, 'celulas_pdf': b.cells,
            'secoes': b.sections, 'escolhas_validacao': {reg: [dict(tarefa=k[0], modelo=k[1], variante=v)
                                                          for k, v in c.items()] for reg, c in choices.items()},
            'correspondencia_valores_originais_csv': True, 'revisao_visual_pendente': True,
            'gerador_sha256': digest(Path(__file__))}
    with manifest_path.open('x', encoding='utf-8') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    print(json.dumps({'pdf': str(output), 'sha256': data['pdf']['sha256'], 'paginas': b.page,
                      'linhas': len(rows), 'comparacoes': len(pairs), 'manifesto': str(manifest_path)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--manifesto', type=Path, required=True)
    parser.add_argument('--somente-tabelas', action='store_true',
                        help='Inicia diretamente nas tabelas, com paginas renumeradas a partir de 1.')
    args = parser.parse_args()
    generate(args.saida, args.manifesto, somente_tabelas=args.somente_tabelas)
