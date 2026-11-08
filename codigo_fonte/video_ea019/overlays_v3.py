"""Text and honest zero-baseline result charts for the 63-shot EA019 cut.

The XLSX storyboard is the timing authority. All coordinates use 1920x1080;
the 3D render remains visible between headers and explanatory labels.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

try:
    from .overlays import Cue, ass_color, literal, load_results, pretty, timestamp
except ImportError:
    from overlays import Cue, ass_color, literal, load_results, pretty, timestamp

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "documentacao/relatorio_final_ea019/video/completo_v3/plano_73_extraido.json"
BG, WHITE, MUTED, GOLD = "07090D", "F3F5F7", "A9B2BE", "E9B95F"
CORAL, CYAN, VIOLET, AXES = "F28779", "58CADA", "AA91E8", "626D7A"
MODEL_COLORS = {"LSTM": CORAL, "Transformer": CYAN, "Informer": VIOLET}
TITLES = {
    "C01": "Identificação do trabalho", "C02": "Irradiância global horizontal",
    "C03": "Objetivo da comparação", "C04": "Dados e localidades",
    "C05": "Quatro tarefas de previsão", "C06": "Protocolo e avaliação retrospectiva",
    "C07": "Como os modelos tratam o histórico", "C08": "Quantização das entradas",
    "C09": "Como ler o erro da previsão", "C10": "Resultados por tarefa",
    "C11": "Quantização e histórico de treinamento", "C12": "Limitações da interpretação",
    "C13": "A escolha depende da tarefa",
}

try:
    from PIL import ImageFont
except ImportError:
    sys.path.insert(0, str(ROOT / ".venv/Lib/site-packages"))
    try:
        from PIL import ImageFont
    except ImportError:
        ImageFont = None

_fonts = {}


def width(text, size, bold=False):
    key = (size, bold)
    if ImageFont is not None:
        try:
            if key not in _fonts:
                _fonts[key] = ImageFont.truetype("C:/Windows/Fonts/" + ("seguisb.ttf" if bold else "segoeui.ttf"), size)
            return max((_fonts[key].getlength(line) for line in text.splitlines()), default=0)
        except OSError:
            pass
    return max((len(line)*size*.54 for line in text.splitlines()), default=0)


def fit(text, requested=40, available=1700, minimum=30, bold=False):
    size = requested
    while size > minimum and width(text, size, bold) > available:
        size -= 1
    return size


STYLES = f"""[Script Info]
Title: EA019 - 63-shot animated cut v3
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Segoe UI,44,{ass_color(WHITE)},&H00FFFFFF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,3,12,0,2,110,110,80,1
Style: Text,Segoe UI,40,{ass_color(WHITE)},&H00FFFFFF,&H9007090D,&H00000000,0,0,0,0,100,100,0,0,1,1,0,7,0,0,0,1
Style: Drawing,Segoe UI,40,{ass_color(WHITE)},&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


class OverlayV3:
    def __init__(self, plan):
        self.plan = plan
        self.events = []
        self.checks = []
        self.shot = ""

    def raw(self, start, end, body, *, style="Text", layer=4):
        if not 0 <= start < end <= 415:
            raise ValueError(f"Invalid event bounds: {start}..{end}")
        self.events.append(f"Dialogue: {layer},{timestamp(start)},{timestamp(end)},{style},,0,0,0,,{body}")

    def text(self, start, end, text, *, x=110, y=240, size=40, color=WHITE,
             align=7, bold=False, available=1700, minimum=30, fade=160,
             style="Text", layer=4, role="label"):
        size = fit(text, size, available, minimum, bold)
        tags = f"\\an{align}\\pos({x},{y})\\fs{size}\\c{ass_color(color)}&\\b{int(bold)}\\fad({fade},{fade})"
        self.raw(start,end,"{"+tags+"}"+literal(text),style=style,layer=layer)
        w, h = width(text,size,bold), len(text.splitlines())*size*1.24
        left = x if align in (1,4,7) else x-w/2 if align in (2,5,8) else x-w
        top = y if align in (7,8,9) else y-h/2 if align in (4,5,6) else y-h
        self.checks.append({"shot":self.shot,"start":start,"end":end,"text":text,
                            "font_size":size,"color":color,"role":role,
                            "bbox_approx":[round(left,1),round(top,1),round(left+w,1),round(top+h,1)],
                            "anchor":[x,y],"align":align,"layer":layer})

    def rect(self,start,end,x,y,w,h,color=BG,*,layer=1,alpha="00",grow=False):
        tags=f"\\an7\\pos({x},{y})\\p1\\bord0\\shad0\\c{ass_color(color)}&\\alpha&H{alpha}&"
        if grow:
            tags+=f"\\clip({x},{y},{x+1},{y+h})\\t(0,1000,\\clip({x},{y},{round(x+w)},{y+h}))"
        self.raw(start,end,"{"+tags+f"}}m 0 0 l {round(w)} 0 l {round(w)} {h} l 0 {h}{{\\p0}}",style="Drawing",layer=layer)

    def source(self,a,b,text):
        self.text(a,b,text,x=110,y=820,size=24,color=MUTED,minimum=24,role="source")

    def support(self,a,b,text,*,color=WHITE,size=40,y=730):
        self.text(a,b,text,x=960,y=y,size=size,color=color,align=8,available=1680,role="support")

    def side(self,a,b,text,*,y=330,size=40,color=WHITE):
        self.text(a,b,text,x=1350,y=y,size=size,color=color,available=470,minimum=34)

    def header(self,a,b,chapter):
        self.text(a,b,chapter+"  ·  EA019",x=110,y=46,size=24,color=MUTED,minimum=24,role="eyebrow",layer=3)
        self.text(a,b,TITLES[chapter],x=110,y=95,size=70,bold=True,available=1700,minimum=48,role="header",layer=3)

    def caption(self,cue):
        if len(cue.text.splitlines())>2 or max(map(len,cue.text.splitlines()))>42:
            raise ValueError("Caption exceeds the preserved SRT contract")
        self.text(cue.start,cue.end,cue.text,x=960,y=985,size=44,minimum=44,align=2,
                  fade=80,style="Caption",layer=10,role="caption")

    def write(self,path):
        path=Path(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(STYLES+"\n".join(self.events)+"\n",encoding="utf-8-sig")
        # Diagnostic estimates: text/font measurements; drawings deliberately excluded.
        issues=[]
        for c in self.checks:
            x0,y0,x1,y1=c["bbox_approx"]
            if x0<80 or x1>1840 or y0<25 or y1>1010:
                issues.append({"type":"outside_safe_area","event":c})
            if c["role"] not in ("caption","source") and y1>840:
                issues.append({"type":"enters_caption_band","event":c})
        overlaps=[]
        body=[c for c in self.checks if c["role"]!="caption"]
        for i,a in enumerate(body):
            for b in body[i+1:]:
                if a["start"]>=b["end"] or b["start"]>=a["end"]:
                    continue
                aa,bb=a["bbox_approx"],b["bbox_approx"]
                if min(aa[2],bb[2])-max(aa[0],bb[0])>3 and min(aa[3],bb[3])-max(aa[1],bb[1])>3:
                    overlaps.append({"shot":a["shot"] or b["shot"],"text_a":a["text"],"text_b":b["text"]})
        return {"path":str(path.resolve()),"duration_seconds":415,"shot_count":63,
                "event_count":len(self.events),"caption_count":sum(c["role"]=="caption" for c in self.checks),
                "canvas":[1920,1080],"font":"Segoe UI","palette":dict(background=BG,white=WHITE,muted=MUTED,gold=GOLD,LSTM=CORAL,Transformer=CYAN,Informer=VIOLET,axes=AXES),
                "regions":{"main_content":[96,80,1824,840],"source_y":820,"caption_band":[100,850,1820,1000],"caption_anchor":[960,985]},
                "event_count_by_shot":dict(Counter(c["shot"] for c in self.checks)),
                "layout_issues":issues,"potential_text_overlaps":overlaps,"events":self.checks,
                "measurement":"Segoe UI metrics when Pillow and Windows fonts are available; bounding heights estimated at 1.24 em. Review rendered frames."}


def opening(o,a,b,number):
    o.rect(a,b,0,0,1920,850,BG,layer=2)
    if number==5:
        o.text(a,b,"Universidade Estadual de Campinas",x=120,y=170,size=58,bold=True)
        o.text(a,b,"Faculdade de Engenharia Elétrica e de Computação",x=120,y=255,size=42,color=MUTED)
        o.text(a,b,"Gustavo de Melo Nascimento",x=120,y=400,size=60,bold=True)
        o.text(a,b,"RA 239679   ·   Engenharia Elétrica (41)",x=120,y=495,size=40,color=MUTED)
    elif number==6:
        o.text(a,b,"Previsão multirresolução de\nirradiância global horizontal\nem localidades associadas à\nfabricação de veículos elétricos",x=120,y=160,size=60,bold=True)
        o.text(a,b,"Avaliação comparativa de Transformer, Informer e LSTM",x=120,y=525,size=40,color=GOLD)
    else:
        o.text(a,b,"Orientador",x=120,y=185,size=36,color=MUTED)
        o.text(a,b,"Prof. Dr. Gustavo Fraidenraich",x=120,y=240,size=56,bold=True)
        o.text(a,b,"Coorientador",x=120,y=335,size=36,color=MUTED)
        o.text(a,b,"Thales Wulfert Cabral",x=120,y=390,size=56,bold=True)
        o.text(a,b,"EA019   ·   2º semestre de 2026",x=120,y=520,size=40,color=GOLD)
        o.text(a,b,"Campinas, 2026",x=120,y=590,size=36,color=MUTED)


def result_panel(o,a,b,title,rows,scale,*,left=110,right=1810,compact=False,exploratory=False):
    """All bar widths are proportional to the actual MAE with an explicit zero."""
    wide=right-left
    o.text(a,b,title,x=left+20,y=235,size=46 if not compact else 40,bold=True,available=wide-40)
    if exploratory:
        o.text(a,b,"Avaliação exploratória",x=left+20,y=295,size=30,color=VIOLET,minimum=30)
    if compact:
        x0=left+20
        barw=wide-170
        y0,step,h=385,117,21
        for i,model in enumerate(("Transformer","Informer","LSTM")):
            row=rows[model]; y=y0+i*step
            o.text(a,b,model,x=x0,y=y-40,size=36,color=MODEL_COLORS[model],bold=True)
            o.text(a,b,row["variant"],x=right-30,y=y-38,size=30,color=MUTED,align=9,minimum=30)
            o.rect(a,b,x0,y+16,barw,h,AXES,alpha="B8",layer=2)
            o.rect(a+.25+i*.1,b,x0,y+16,float(row["mae"])/scale*barw,h,MODEL_COLORS[model],grow=True,layer=3)
            o.text(a+.25+i*.1,b,pretty(row["mae"]),x=right-25,y=y+4,size=44,align=9,bold=row["position"]==1)
        ticks=(0,scale/2,scale)
        for t in ticks:
            o.text(a,b,f"{t:g}",x=round(x0+t/scale*barw),y=723,size=26,minimum=26,color=MUTED,align=8)
        o.text(a,b,"Macro-MAE [W/m²]",x=left+20,y=770,size=28,color=MUTED,minimum=28)
    else:
        x0,barw=690,800
        for i,model in enumerate(("Transformer","Informer","LSTM")):
            row=rows[model]; y=355+i*122
            o.text(a,b,model,x=145,y=y-5,size=42,color=MODEL_COLORS[model],bold=True)
            o.text(a,b,row["variant"],x=470,y=y+4,size=34,color=MUTED)
            o.rect(a,b,x0,y+6,barw,33,AXES,alpha="B8",layer=2)
            o.rect(a+.25+i*.12,b,x0,y+6,float(row["mae"])/scale*barw,33,MODEL_COLORS[model],grow=True,layer=3)
            o.text(a+.25+i*.12,b,pretty(row["mae"]),x=1770,y=y-15,size=54,align=9,bold=row["position"]==1)
        ticks=(0,50,100,150) if scale==150 else (0,scale/2,scale)
        for t in ticks:
            o.text(a,b,f"{t:g}",x=round(x0+t/scale*barw),y=724,size=28,minimum=28,color=MUTED,align=8)
        o.text(a,b,"Macro-MAE [W/m²]  ·  menor é melhor",x=690,y=775,size=28,color=MUTED,minimum=28)


def result_shot(o,a,b,n,r):
    # Keep the comparison frontal; this mask replaces the previous 3D table.
    o.rect(a,b,95,220,1730,588,BG,layer=1)
    if n==53:
        result_panel(o,a,b,"Horária · até 72 h",r["hourly_72_extension"],150)
    elif n==54:
        result_panel(o,a,b,"Diária · até 30 d",r["daily_30"],50)
    elif n==55:
        o.text(a,b,"Vantagem de MAE sobre a LSTM",x=130,y=245,size=46,bold=True)
        for x,label,key,scale in ((130,"Horária","hourly_72_extension",150),(1000,"Diária","daily_30",50)):
            delta=r[key]["LSTM"]["mae"]-r[key]["Transformer"]["mae"]
            o.text(a,b,label,x=x,y=345,size=40,color=MUTED)
            o.text(a,b,"≈ "+pretty(delta)+" W/m²",x=x,y=410,size=66,color=CYAN,bold=True,available=730)
            x0=x+245; bw=390
            for k,model in enumerate(("Transformer","LSTM")):
                yy=550+k*75
                o.text(a,b,model,x=x,y=yy,size=30,minimum=30,color=MODEL_COLORS[model])
                o.rect(a,b,x0,yy+10,bw,22,AXES,alpha="B8",layer=2)
                o.rect(a+.3,b,x0,yy+10,float(r[key][model]["mae"])/scale*bw,22,MODEL_COLORS[model],layer=3,grow=True)
            o.text(a,b,f"Escala: 0–{scale} W/m²",x=x+245,y=700,size=28,minimum=28,color=MUTED)
        o.support(a,b,"Diferenças pequenas e descritivas",color=MUTED,y=765,size=36)
    elif n==56:
        result_panel(o,a,b,"Mensal · 1 passo",r["monthly_1"],16)
    elif n==57:
        result_panel(o,a,b,"Mensal · 1 passo",r["monthly_1"],16,left=110,right=920,compact=True)
        result_panel(o,a,b,"Mensal · até 6 passos",r["monthly_6"],16,left=1000,right=1810,compact=True,exploratory=True)
    elif n==58:
        o.text(a,b,"A liderança varia por localidade",x=130,y=245,size=48,bold=True)
        for x,label,t,l in ((150,"Horária",7,3),(1030,"Diária",6,4)):
            o.text(a,b,label,x=x,y=360,size=44,bold=True)
            o.text(a,b,"Transformer",x=x,y=455,size=40,color=CYAN)
            o.text(a,b,str(t),x=x+490,y=430,size=80,color=CYAN,bold=True)
            o.text(a,b,"LSTM",x=x,y=580,size=40,color=CORAL)
            o.text(a,b,str(l),x=x+490,y=555,size=80,color=CORAL,bold=True)
        o.support(a,b,"Contagem entre as 10 localidades avaliadas",color=MUTED,size=36,y=755)
    elif n==59:
        o.text(a,b,"Diária · horizontes cumulativos",x=130,y=245,size=48,bold=True)
        xs=[250,600,950,1300,1650]
        o.rect(a,b,250,445,1400,3,AXES,layer=2)
        for x,days in zip(xs,(1,3,7,14,30)):
            model="LSTM" if days<30 else "Transformer"; color=MODEL_COLORS[model]
            o.rect(a,b,x-9,435,18,23,color,layer=3)
            o.text(a,b,f"{days} d",x=x,y=345,size=52,align=8,bold=True)
            o.text(a,b,model,x=x,y=505,size=36,align=8,color=color)
        o.support(a,b,"Condição selecionada mantida nos diferentes recortes",color=MUTED,size=36,y=700)
    source="Fonte: relatório, Tabela 10" if n==59 else "Fonte: relatório, Figura 6" if n==58 else "Fonte: relatório, Tabela 6 · condições selecionadas na validação"
    o.source(a,b,source)


def explanatory_shot(o,s):
    a,b,n=s["start_s"],s["end_s"],int(s["id"][1:])
    # Each entry introduces one idea. Supplemental text stays outside the
    # central volume of the 3D diagrams, with no reading material below y=840.
    if n==8:
        o.side(a,b,"GHI",size=64,color=GOLD)
        o.side(a,b,"Superfície\nhorizontal",y=505,size=40)
    elif n==9:
        o.side(a,b,"Superfície\nhorizontal",y=330)
        o.side(a,b,"Área de referência\n1 m²",y=505,color=GOLD)
    elif n==10:
        o.side(a,b,"W/m²",y=330,size=68,color=GOLD)
        o.side(a,b,"Potência por\nunidade de área",y=500)
    elif n==11:
        o.side(a,b,"Direta sobre\na horizontal",y=330,color=GOLD)
        o.side(a,b,"Difusa do céu",y=565,color=GOLD)
    elif n==12:
        o.side(a,b,"Padrões diários\ne sazonais",y=330,size=38)
        o.side(a,b,"Variação\natmosférica",y=555,size=38,color=MUTED)
    elif n in (13,14):
        o.text(a,b,"Histórico de GHI",x=400,y=265,size=38,align=8)
        o.text(a,b,"Presente",x=1115,y=265,size=36,color=MUTED,align=8)
        o.text(a,b,"Futuro a prever",x=1510,y=265,size=38,color=MUTED,align=8)
        if n==14:
            o.support(a,b,"Quanto conseguimos antecipar?",size=38,y=200)
    elif n==15:
        o.text(a,b,"Prever o recurso solar",x=1050,y=320,size=50,bold=True,available=720)
        o.support(a,b,"Informação para o planejamento energético",size=40)
    elif n==16:
        for x,model in ((350,"LSTM"),(960,"Transformer"),(1570,"Informer")):
            o.text(a,b,model,x=x,y=260,size=42,color=MODEL_COLORS[model],align=8,bold=True)
        o.support(a,b,"Comparar precisão preditiva",size=44)
    elif n==17:
        terms=("Escala temporal","Representação da entrada","Histórico de treinamento")
        for i,term in enumerate(terms):
            start=a+i*1.7
            o.text(start,b,term,x=220+i*560,y=260,size=36,available=520,color=WHITE)
        o.support(a,b,"Variável prevista: GHI",size=44,color=GOLD)
    elif n==18:
        o.text(a,b,"NSRDB",x=1290,y=310,size=60,bold=True,available=520)
        o.text(a,b,"Estimativas modeladas",x=1290,y=405,size=38,available=520)
        o.text(a,b,"10 localidades",x=1290,y=565,size=44,color=GOLD,available=520)
    elif n==19:
        for yy,count,country in ((300,"1","Brasil"),(445,"8","Estados Unidos"),(590,"1","México")):
            o.text(a,b,count,x=1260,y=yy,size=64,color=GOLD,bold=True)
            o.text(a,b,country,x=1350,y=yy+17,size=38,available=440)
        o.text(a,b,"Detroit · detalhe",x=265,y=520,size=24,minimum=24,color=MUTED)
        o.text(a+.5,b,"GM",x=430,y=590,size=24,minimum=24,color=MUTED)
        o.text(a+.5,b,"Ford",x=330,y=715,size=24,minimum=24,color=MUTED)
    elif n==20:
        o.text(a,b,"Célula da base NSRDB",x=1120,y=260,size=42,available=670,bold=True)
        o.support(a,b,"Estimativas nas coordenadas das localidades",size=40)
    elif n==21:
        o.text(a,b,"Histórico de GHI",x=150,y=260,size=40)
        o.text(a,b,"Identificação aprendida\nda localidade",x=1120,y=260,size=38,available=660)
        o.support(a,b,"Entradas da rede",size=42)
    elif n==22:
        o.text(a,b,"GHI + identificação da localidade",x=960,y=255,size=46,align=8,bold=True)
        o.support(a,b,"Sem temperatura, imagens ou previsão\nmeteorológica como entradas",size=36,y=700,color=MUTED)
    elif n==23:
        o.support(a,b,"Parâmetros compartilhados entre\nas localidades do conjunto",size=40,y=690)
    elif n==24:
        o.text(a,b,"Tarefa",x=180,y=245,size=42)
        o.text(a,b,"Histórico",x=680,y=245,size=42,align=8)
        o.text(a,b,"Previsão",x=1450,y=245,size=42,align=8,color=GOLD)
        tasks=(("Horária","336 horas","72 horas"),
               ("Diária","365 dias","30 dias"),
               ("Mensal · 1 passo","12 meses","1 mês"),
               ("Mensal · 6 passos","12 meses","6 meses"))
        for i,(label,history,future) in enumerate(tasks):
            start=a+.3+i*.6
            yy=340+i*100
            o.rect(start,b,130,yy-10,1640,82,"171C22",alpha="30")
            o.text(start,b,label,x=180,y=yy,size=38,bold=True,available=470)
            o.text(start,b,history,x=680,y=yy,size=38,align=8)
            o.text(start,b,"→",x=1060,y=yy,size=44,color=GOLD)
            o.text(start,b,future,x=1450,y=yy,size=38,align=8,color=GOLD)
    elif n in (25,26,27,28):
        label,window={25:("Horária","336 h de histórico  →  72 h de previsão"),26:("Diária","365 d de histórico  →  30 d de previsão"),27:("Mensal · 1 passo","12 meses  →  1 mês"),28:("Mensal · 6 passos","12 meses  →  6 meses")}[n]
        o.text(a,b,label,x=130,y=250,size=48,bold=True)
        o.support(a,b,window,size=44,y=710)
        if n==28:
            o.text(a,b,"Exploratória",x=1800,y=260,size=32,color=VIOLET,align=9,minimum=32)
    elif n==29:
        o.text(a,b,"Tarefas distintas",x=960,y=250,size=48,bold=True,align=8)
        o.support(a,b,"Redes treinadas separadamente\n1 passo ≠ primeiro passo da rede de 6 saídas",size=38,y=690)
    elif n in (30,31,32):
        o.text(a,b,"Treinamento inicial",x=190,y=265,size=36)
        o.text(a,b,"2019–2022",x=190,y=320,size=46,color=GOLD,bold=True)
        if n>=31:
            o.text(a,b,"Validação",x=1080,y=265,size=36)
            o.text(a,b,"2023",x=1080,y=320,size=46,color=GOLD,bold=True)
        if n==32:
            o.text(a,b,"Teste retrospectivo",x=1450,y=265,size=36,available=370)
            o.text(a,b,"2024",x=1450,y=320,size=46,color=WHITE,bold=True)
    elif n==33:
        o.text(a,b,"Seleção pela validação",x=960,y=250,size=46,align=8,bold=True)
        o.support(a,b,"Configuração selecionada",size=40,color=GOLD)
    elif n==34:
        o.text(a,b,"Novo ajuste: 2019–2023",x=960,y=255,size=46,align=8,bold=True)
        o.support(a,b,"Configuração selecionada mantida",size=40,color=GOLD)
    elif n==35:
        o.text(a,b,"Teste: 2024",x=1480,y=265,size=46,bold=True,available=320)
        o.support(a,b,"Avaliação retrospectiva",size=44)
    elif n==36:
        o.text(a,b,"Houve exposição anterior\nao período de teste",x=960,y=260,size=46,align=8,bold=True)
        o.support(a,b,"Interpretação retrospectiva dos resultados",size=38,color=MUTED)
    elif n==37:
        for x,model in ((350,"LSTM"),(960,"Transformer"),(1570,"Informer")):
            o.text(a,b,model,x=x,y=255,size=42,color=MODEL_COLORS[model],align=8,bold=True)
        o.support(a,b,"Mesmo histórico",size=40)
    elif n==38:
        o.text(a,b,"LSTM",x=130,y=245,size=52,color=CORAL,bold=True)
        o.text(a,b,"Memória temporal",x=430,y=255,size=40,color=CORAL)
        o.support(a,b,"Vetor futuro direto",size=38)
    elif n==39:
        o.text(a,b,"Transformer",x=130,y=245,size=52,color=CYAN,bold=True)
        o.support(a,b,"Atenção entre posições",size=44,color=CYAN)
    elif n==40:
        o.text(a,b,"Ordem temporal",x=130,y=245,size=46,bold=True)
        o.support(a,b,"Histórico de GHI + representação posicional",size=38)
    elif n==41:
        o.text(a,b,"Informer",x=130,y=245,size=52,color=VIOLET,bold=True)
        o.text(a,b,"ProbSparse",x=1430,y=255,size=40,color=VIOLET,available=370)
        o.support(a,b,"Consultas selecionadas",size=44,color=VIOLET)
    elif n==42:
        o.text(a,b,"ProbSparse",x=130,y=245,size=46,color=VIOLET,bold=True)
        o.support(a,b,"Redução temporal no codificador\nAtenção cruzada completa",size=38,y=695)
    elif n==43:
        o.text(a,b,"Avaliação realizada: precisão preditiva",x=960,y=250,size=46,align=8,bold=True)
        o.support(a,b,"Velocidade e memória não medidas",size=40,color=MUTED)
    elif n==44:
        for x,label in ((330,"Contínuo"),(750,"Q64"),(1170,"Q128"),(1590,"Q256")):
            o.text(a,b,label,x=x,y=255,size=42,align=8,color=WHITE if label=="Contínuo" else GOLD,bold=True)
        o.support(a,b,"Representação da entrada",size=40)
    elif n==45:
        o.text(a,b,"Aproximação por níveis",x=960,y=250,size=46,align=8,bold=True)
        o.support(a,b,"Poucos degraus: ilustração",size=36,color=MUTED)
    elif n==46:
        o.text(a,b,"Somente a entrada de GHI",x=130,y=250,size=46,bold=True)
        o.text(a,b,"Quantizador",x=920,y=320,size=36,color=GOLD,align=8)
        o.text(a,b,"Reconstrução\nem float32",x=1440,y=320,size=36,align=8)
        o.text(a,b,"Identificação da localidade",x=150,y=625,size=36)
        o.support(a,b,"Pesos, alvos e saída contínuos",size=38,y=740)
    elif n==47:
        o.text(a,b,"Clipping + arredondamento",x=960,y=250,size=46,align=8,bold=True)
        o.support(a,b,"Variantes quantizadas: intervalo normalizado [0,1]\nControle sem clipping",size=36,y=695)
    elif n==48:
        o.text(a,b,"Validação",x=500,y=270,size=44,align=8)
        o.text(a,b,"Teste",x=1430,y=270,size=44,align=8)
        o.support(a,b,"Condição selecionada mantida no teste",size=42,color=GOLD)
    elif n==49:
        o.text(a,b,"MAE",x=1350,y=300,size=70,color=GOLD,bold=True)
        o.text(a,b,"Erro absoluto\nmédio",x=1350,y=410,size=42,available=450)
        o.text(a,b,"W/m²",x=1350,y=575,size=48,color=GOLD)
    elif n==50:
        o.text(a,b,"Referência",x=280,y=265,size=36)
        o.text(a,b,"Previsão",x=650,y=265,size=36,color=GOLD)
        o.text(a,b,"Distâncias\nabsolutas",x=1350,y=370,size=42,available=450)
        o.support(a,b,"MAE em W/m²",size=42)
    elif n==51:
        o.text(a,b,"Métrica por localidade",x=130,y=255,size=44,bold=True)
        o.text(a,b,"Média macro",x=1390,y=255,size=44,bold=True,available=410)
        o.support(a,b,"10 localidades · mesmo peso",size=42)
    elif n==52:
        o.text(a,b,"Horizonte cumulativo",x=960,y=250,size=48,align=8,bold=True)
        o.support(a,b,"Até 72 h = passos 1 a 72\nTodos os passos até o horizonte",size=40,y=690)
    elif n==60:
        o.text(a,b,"Sem benefício universal",x=960,y=255,size=50,bold=True,align=8)
        for x,value,label in ((350,"5","melhoras"),(960,"4","pioras"),(1570,"3","controles")):
            o.text(a,b,value,x=x,y=330,size=76,bold=True,align=8,color=GOLD)
            o.text(a,b,label,x=x,y=435,size=36,align=8)
        o.support(a,b,"12 combinações de modelo e tarefa",size=40)
    elif n==61:
        o.text(a,b,"Análise histórica separada · teste pareado",x=130,y=250,size=44,bold=True)
        o.text(a,b,"11 de 12",x=1420,y=355,size=66,color=GOLD,bold=True,available=390)
        o.text(a,b,"controles\ncontínuos",x=1420,y=460,size=38,available=390)
        o.support(a,b,"Histórico longo: menor MAE",size=42)
    elif n==62:
        o.text(a,b,"Associação observada",x=960,y=255,size=48,bold=True,align=8)
        o.support(a,b,"Melhora na maioria dos controles; sem garantia\nQuantidade, anos e normalização mudam juntos",size=36,y=690)
    elif n==63:
        o.text(a,b,"Resultados descritivos",x=960,y=280,size=56,bold=True,align=8)
        o.support(a,b,"Sem demonstração de significância estatística",size=42,y=700)
    elif n==64:
        o.text(a,b,"Horário",x=480,y=300,size=48,align=8,bold=True)
        o.text(a,b,"Uma semente",x=480,y=690,size=42,align=8,color=MUTED)
        o.text(a,b,"Seis passos",x=1440,y=300,size=48,align=8,bold=True)
        o.text(a,b,"Exploratório",x=1440,y=690,size=42,align=8,color=VIOLET)
    elif n==65:
        o.text(a,b,"Janelas compartilham alvos",x=480,y=290,size=40,align=8,available=760)
        o.text(a,b,"Localidades inéditas",x=1440,y=290,size=40,align=8,available=760)
        o.text(a,b,"Não avaliadas",x=1440,y=690,size=42,align=8,color=MUTED)
    elif n in (66,67):
        # Stable four-task synthesis: no global winner is asserted.
        o.rect(a,b,100,225,1720,575,BG,layer=1)
        cards=((160,285,"Horária · até 72 h","Transformer","53,21"),(1060,285,"Diária · até 30 d","Transformer","43,89"),(160,510,"Mensal · 1 passo","Informer","12,73"),(1060,510,"Mensal · até 6 passos","Informer","13,67"))
        for x,y,label,model,value in cards:
            active=(n==66 and model=="Transformer") or (n==67 and model=="Informer")
            color=MODEL_COLORS[model] if active else MUTED
            o.text(a,b,label,x=x,y=y,size=36,color=WHITE,available=700)
            o.text(a,b,model,x=x,y=y+58,size=38,color=color,bold=True)
            o.text(a,b,value+" W/m²",x=x+420,y=y+55,size=40,color=color,available=330)
        o.text(a,b,"Seis passos: exploratório",x=1060,y=690,size=30,color=VIOLET,minimum=30)
        o.support(a,b,"Nas configurações avaliadas" if n==66 else "A escolha depende da tarefa",size=40,color=WHITE,y=755)
    else:
        raise ValueError(f"No layout for {s['id']}")

    if 8<=n<=14:
        o.source(a,b,"Ilustração conceitual · fábrica ilustrativa")
    elif n in (18,19):
        o.source(a,b,"Fonte: relatório, Tabela 1 · coordenadas das 10 localidades")
    elif n==20:
        o.source(a,b,"Esquema de localização · célula ilustrativa da base NSRDB")
    elif n==21:
        o.source(a,b,"Séries ilustrativas · entradas efetivas dos experimentos")
    elif 37<=n<=43:
        o.source(a,b,"Esquema simplificado das arquiteturas")
    elif n in (44,45,46,47):
        o.source(a,b,"Ilustração conceitual · quantização da entrada de GHI")
    elif n in (49,50):
        o.source(a,b,"Exemplo didático · curvas sem correspondência com resultados experimentais")
    elif n==60:
        o.source(a,b,"Fonte: relatório, Tabela 7 · condição selecionada na validação e teste de 2024")
    elif n in (61,62):
        o.source(a,b,"Fonte: relatório, Tabela 8 · análise histórica separada da avaliação principal")
    elif n in (66,67):
        o.source(a,b,"Fonte: relatório, Tabela 6 · resultados descritivos no teste retrospectivo de 2024")


def write_v3_ass(path,include_captions=True):
    plan=json.loads(PLAN.read_text(encoding="utf-8"))
    if plan["validation"]["middle_shots"]!=63 or plan["timing"]["render_duration_s"]!=415:
        raise ValueError("Expected the 63-shot, 415-second animated cut")
    o=OverlayV3(plan)
    results=load_results()
    # One stable chapter title; body labels follow the exact shot boundaries.
    for chapter in plan["overview"]:
        if chapter["id"] in TITLES and chapter["id"]!="C01":
            o.shot=chapter["id"]
            o.header(chapter["start_s"],chapter["end_s"],chapter["id"])
    for shot in plan["middle_shots"]:
        o.shot=shot["id"]
        a,b,n=shot["start_s"],shot["end_s"],int(shot["id"][1:])
        if n<=7:
            opening(o,a,b,n)
        elif 53<=n<=59:
            result_shot(o,a,b,n,results)
        else:
            explanatory_shot(o,shot)
    if include_captions:
        o.shot="captions"
        for cue in plan["subtitles"]:
            o.caption(Cue(cue["start_s"],cue["end_s"],cue["text"]))
    report=o.write(path)
    report["source_plan"]=str(PLAN.resolve())
    report["result_bar_scales_w_m2"]={"hourly_72_extension":[0,150],"daily_30":[0,50],"monthly_1":[0,16],"monthly_6":[0,16]}
    report["numeric_labels"]="Actual CSV values shown directly, rounded only for display; bar lengths interpolate for 1 second from a zero baseline."
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--no-captions",action="store_true")
    parser.add_argument("--report",type=Path,help="Optional event, occupancy and readability diagnostics JSON")
    args=parser.parse_args()
    report=write_v3_ass(args.output,include_captions=not args.no_captions)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={k:v for k,v in report.items() if k not in ("events","potential_text_overlaps","layout_issues")}
    summary["layout_issue_count"]=len(report["layout_issues"])
    summary["potential_text_overlap_count"]=len(report["potential_text_overlaps"])
    print(json.dumps(summary,ensure_ascii=True,indent=2))


if __name__=="__main__":
    main()
