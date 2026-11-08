"""Editable, deterministic opening artwork matching the approved video palette."""
from pathlib import Path
import sys, math, json, html, hashlib, base64

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
import fitz
from PIL import Image

OUT = ROOT / 'documentacao/relatorio_final_ea019/video/abertura_apresentacao_v1'
OUT.mkdir(parents=True, exist_ok=True)
W, H = 1920, 1080
COLORS = dict(bg='#040609', white='#ecf1f2', muted='#9baeb8', aqua='#9bcfd9',
              gold='#d2b487', purple='#b8adcc', coral='#d69b8c')
FONTS = {name: TTFont('C:/Windows/Fonts/' + filename) for name, filename in
         [('regular','segoeui.ttf'), ('semibold','seguisb.ttf')]}
parts = []
boxes = []

def add(value): parts.append(value)
def text(value, x, y, size, color, weight='regular', tracking=0):
    font = FONTS[weight]; glyphs = font.getGlyphSet(); cmap = font.getBestCmap()
    scale = size / font['head'].unitsPerEm
    start = x
    add(f'<g aria-label="{html.escape(value, quote=True)}"><title>{html.escape(value)}</title>')
    for ch in value:
        name = cmap.get(ord(ch), '.notdef')
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale,0,0,-scale,x,y)))
        path = pen.getCommands()
        if path: add(f'<path d="{path}" fill="{color}"/>')
        x += font['hmtx'][name][0] * scale + tracking
    add('</g>')
    boxes.append(dict(text=value,x=start,baseline=y,size=size,width=round(x-start,2)))
    return x

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}px" height="{H}px" viewBox="0 0 {W} {H}">')
add('<title>Previsão multirresolução de irradiância global horizontal — abertura</title>')
add('<defs><radialGradient id="presenterGlow" cx="82%" cy="80%" r="52%"><stop offset="0" stop-color="#17313b" stop-opacity=".65"/><stop offset=".58" stop-color="#0c171d" stop-opacity=".3"/><stop offset="1" stop-color="#040609" stop-opacity="0"/></radialGradient><linearGradient id="lineFade"><stop offset="0" stop-color="#9bcfd9" stop-opacity=".12"/><stop offset=".5" stop-color="#9bcfd9" stop-opacity=".68"/><stop offset="1" stop-color="#9bcfd9" stop-opacity=".1"/></linearGradient></defs>')
add(f'<rect width="{W}" height="{H}" fill="{COLORS["bg"]}"/>')
for i in range(160,0,-1):
    r=i/160; strength=(1-r)**1.55
    base=(4,6,9); center=(22,43,53)
    rgb=tuple(round(a+(b-a)*strength) for a,b in zip(base,center))
    add(f'<ellipse cx="1620" cy="950" rx="{650*r:.3f}" ry="{650*r:.3f}" fill="rgb{rgb}"/>')

text('UNICAMP',96,91,27,COLORS['aqua'],'semibold',2.1)
add('<path d="M285 69V97" stroke="#3b535e" stroke-width="1.5"/>')
text('ENGENHARIA ELÉTRICA',310,91,23,COLORS['muted'],'regular',1.8)
text('Faculdade de Engenharia Elétrica e de Computação',96,132,25,COLORS['muted'])
add(f'<path d="M96 181H158" stroke="{COLORS["gold"]}" stroke-width="4"/>')

text('Previsão multirresolução',96,268,64,COLORS['white'],'semibold')
text('de irradiância global horizontal',96,347,64,COLORS['aqua'],'semibold')
text('em localidades associadas à',98,423,39,COLORS['white'])
text('fabricação de veículos elétricos',98,476,39,COLORS['white'])

text('Avaliação comparativa de',98,559,31,COLORS['muted'])
x=text('Transformer',98,613,40,COLORS['aqua'],'semibold')
x=text(', ',x,613,40,COLORS['muted'])
x=text('Informer',x,613,40,COLORS['purple'],'semibold')
x=text(' e ',x,613,40,COLORS['muted'])
text('LSTM',x,613,40,COLORS['coral'],'semibold')

# Restrained irradiance motif: no grid, invented metric, or numbered scene label.
points=[]
for i in range(321):
    x=98+i*3.3
    daylight=max(0,math.sin((i/320)*math.pi*3.1-.45))
    h=daylight**2*(.85+.15*math.sin(i*.037))
    y=680-h*48
    points.append(f'{x:.2f},{y:.2f}')
add(f'<polyline points="{" ".join(points)}" fill="none" stroke="#37525d" stroke-width="2.2"/>')
add('<path d="M98 680H1154" stroke="#20333c" stroke-width="1"/>')

text('Gustavo de Melo Nascimento',98,750,36,COLORS['white'],'semibold')
text('RA 239679',99,789,23,COLORS['muted'])
text('ORIENTADOR',99,824,19,COLORS['gold'],'semibold',1.6)
text('Prof. Dr. Gustavo Fraidenraich',98,863,28,COLORS['white'])
text('COORIENTADOR',686,824,19,COLORS['gold'],'semibold',1.6)
text('Thales Wulfert Cabral',685,863,28,COLORS['white'])
text('Campinas · 2026',685,789,23,COLORS['muted'])
add('</svg>')

svg = OUT / 'capa_apresentacao_fundo_v1.svg'
png = OUT / 'capa_apresentacao_fundo_v1.png'
svg.write_text('\n'.join(parts),encoding='utf-8')
with fitz.open(stream=svg.read_bytes(),filetype='svg') as drawing:
    pdf_bytes=drawing.convert_to_pdf()
with fitz.open(stream=pdf_bytes,filetype='pdf') as doc:
    page=doc[0];page.get_pixmap(matrix=fitz.Matrix(W/page.rect.width,H/page.rect.height),alpha=False).save(png)

if any(b['x']+b['width']>1280 for b in boxes):
    raise ValueError('Cover text intrudes into the reserved presenter area')
record={'width':W,'height':H,'palette':COLORS,'text':boxes,
    'presenter_placement':{'x':1300,'y':600,'width':560,'height':480,'anchor':'bottom-right'},
    'caption_safe_rect':{'x':96,'y':905,'width':1120,'height':140},
    'report_source':'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf',
    'video_source':'C:/Users/gusta/Pictures/Camera Roll/WIN_20261104_20_01_05_Pro.mp4',
    'video_duration_seconds':14.15,'video_background_processing_applied':False,
    'source_frame_seconds':4,'png_sha256':hashlib.sha256(png.read_bytes()).hexdigest()}
(OUT/'capa_apresentacao_v1.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(str(png))

cutout=OUT/'recorte_ilustrativo_estatico_v1.png'
if cutout.exists():
    with Image.open(cutout) as im:
        iw,ih=im.size; box=im.getchannel('A').point(lambda a:255 if a>=24 else 0).getbbox()
    if not box:raise ValueError('Empty alpha in static preview cutout')
    x0,y0,x1,y1=box
    url='data:image/png;base64,'+base64.b64encode(cutout.read_bytes()).decode('ascii')
    scale=min(560/(x1-x0),480/(y1-y0))
    dx=1300+(560-(x1-x0)*scale)/2-x0*scale
    dy=1080-y1*scale
    insert=('<defs><clipPath id="presenterClip"><rect x="1300" y="600" width="560" height="480"/></clipPath></defs>'
        f'<g clip-path="url(#presenterClip)"><image x="{dx}" y="{dy}" width="{iw*scale}" height="{ih*scale}" href="{url}"/></g>')
    content=svg.read_text(encoding='utf-8').replace('</svg>',insert+'</svg>')
    preview_svg=OUT/'previa_capa_com_apresentador_v1.svg'
    preview_svg.write_text(content,encoding='utf-8')
    with fitz.open(stream=content.encode('utf-8'),filetype='svg') as drawing:
        pdf_bytes=drawing.convert_to_pdf()
    preview_png=OUT/'previa_capa_com_apresentador_v1.png'
    with fitz.open(stream=pdf_bytes,filetype='pdf') as doc:
        page=doc[0];page.get_pixmap(matrix=fitz.Matrix(W/page.rect.width,H/page.rect.height),alpha=False).save(preview_png)
    record['static_preview']={'path':str(preview_png.relative_to(ROOT)),
        'sha256':hashlib.sha256(preview_png.read_bytes()).hexdigest(),
        'method':'Native vector title-card layout with image_gen static illustrative cutout from video frame',
        'not_a_temporal_video_matte':True,'video_original_unmodified':True,
        'cutout_alpha_bbox':box,'placement':record['presenter_placement']}
    (OUT/'capa_apresentacao_v1.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(preview_png))
