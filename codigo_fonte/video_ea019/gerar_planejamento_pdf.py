"""Export the agreed 75-shot planning table as a readable landscape PDF."""
from pathlib import Path
import json
import sys
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle

SOURCE = ROOT / 'documentacao/relatorio_final_ea019/video/planejamento_revisao/storyboard_75_planos.json'
OUTPUT = ROOT / 'output/pdf/Planejamento_Video_GHI_75_Planos.pdf'
NAVY = colors.HexColor('#173448')
INK = colors.HexColor('#243441')
MUTED = colors.HexColor('#576772')
TEAL = colors.HexColor('#167A83')
RULE = colors.HexColor('#D7E0E5')


def seconds(value):
    m, s = map(int, value.split(':'))
    return 60 * m + s


def footer(canvas, document):
    width, height = document.pagesize
    canvas.saveState()
    canvas.setFont('Segoe', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(document.leftMargin, height - 24, 'GHI  |  PLANEJAMENTO VISUAL PARA REVISÃO')
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(.5)
    canvas.line(document.leftMargin, 28, width - document.rightMargin, 28)
    canvas.drawString(document.leftMargin, 16, '75 planos  |  Parte animada: 6min55s  |  Tempos aproximados')
    canvas.drawRightString(width - document.rightMargin, 16, f'Página {document.page}')
    canvas.restoreState()


def main():
    rows = json.loads(SOURCE.read_text(encoding='utf-8'))
    assert len(rows) == 75
    previous = 0
    for index, (number, interval, idea, implementation) in enumerate(rows, 1):
        assert number == f'{index:02d}' and idea and implementation
        start, end = map(seconds, interval.split(' - '))
        assert start == previous and end > start
        previous = end
    assert previous == 415
    for name, file in [('Segoe', 'segoeui.ttf'), ('SegoeBold', 'segoeuib.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(Path('C:/Windows/Fonts') / file)))
    pdfmetrics.registerFontFamily('Segoe', normal='Segoe', bold='SegoeBold')
    body = ParagraphStyle('Body', fontName='Segoe', fontSize=9.4, leading=12.5,
                          textColor=INK, alignment=TA_LEFT, spaceAfter=0)
    note = ParagraphStyle('Note', parent=body, fontSize=9, leading=12, textColor=MUTED, spaceAfter=5)
    title = ParagraphStyle('Title', parent=body, fontName='SegoeBold', fontSize=21, leading=26,
                           textColor=NAVY, spaceAfter=5)
    subtitle = ParagraphStyle('Subtitle', parent=body, fontSize=10, leading=14,
                              textColor=TEAL, spaceAfter=11)
    heading = ParagraphStyle('Heading', parent=body, fontName='SegoeBold', fontSize=9.3,
                             leading=12, textColor=colors.white)
    index_style = ParagraphStyle('Index', parent=body, fontSize=9, leading=13)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=landscape(A4),
                            leftMargin=32, rightMargin=32, topMargin=39, bottomMargin=38,
                            title='Planejamento visual do vídeo - 75 planos',
                            author='Gustavo de Melo Nascimento',
                            subject='Storyboard para revisão: ideia e proposta de implementação de cada plano')
    story = [Paragraph('Planejamento visual do vídeo', title),
             Paragraph('Previsão de irradiância solar | LSTM, Transformer e Informer', subtitle),
             Paragraph('<b>Escopo:</b> 75 planos para os 6min55s da parte animada. “Frame” significa um plano do storyboard, composto por vários quadros de animação. Os tempos são aproximados; as gravações de abertura e encerramento ficam separadas.', note),
             Paragraph('<b>Direção visual:</b> acompanhar a mesma figura enquanto ela se transforma: luz, curva, amostras, operações das redes e previsão. Fundo preto, objetos grandes, movimentos suaves, textos curtos e cores naturais na fábrica. LSTM em coral, Transformer em ciano e Informer em roxo.', note),
             Paragraph('<b>Referência visual:</b> 3Blue1Brown, <link href="https://www.3blue1brown.com/lessons/attention/" color="#167A83">Attention in transformers, step-by-step</link>. Para sugerir alterações, cite o número do plano.', note),
             Spacer(1, 9)]
    table_data = [[Paragraph('Plano / tempo', heading),
                   Paragraph('Ideia que queremos passar', heading),
                   Paragraph('Proposta de implementação', heading)]]
    for number, interval, idea, implementation in rows:
        table_data.append([Paragraph(f'<b>{number}</b><br/>{escape(interval)}', index_style),
                           Paragraph(escape(idea), body), Paragraph(escape(implementation), body)])
    width = doc.width
    table = LongTable(table_data, colWidths=[89, 237, width - 326], repeatRows=1,
                      hAlign='LEFT', splitByRow=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), NAVY),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F7F9')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LINEBELOW', (0, 1), (-1, -1), .35, RULE),
        ('LINEAFTER', (0, 1), (0, -1), .35, RULE),
        ('LINEAFTER', (1, 1), (1, -1), .35, RULE),
    ]))
    story.append(table)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print(json.dumps({'pdf': str(OUTPUT), 'plans': len(rows), 'duration_seconds': previous,
                      'bytes': OUTPUT.stat().st_size}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
