from pathlib import Path
import pandas as pd
import numpy as np
from html import escape
import json

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).parent/'figuras'; OUT.mkdir(exist_ok=True)
BASE=ROOT/'resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina'
D=pd.read_csv(BASE/'metricas_teste_modelos_disciplina.csv')
R=pd.read_csv(BASE/'classificacoes_modelos_disciplina.csv')
MODELS=['Transformer','Informer','LSTM']
COL={'Transformer':'#245680','Informer':'#B65B35','LSTM':'#35776C'}
TASKS=[('hourly_72_extension',72,'Horária 1–72 h'),('daily_30',30,'Diária 1–30 dias'),('monthly_1',1,'Mensal 1 passo'),('monthly_6',6,'Mensal 1–6 passos')]
# Resolve task names from saved data, without guessing experiment aliases.
ts=list(D.tarefa.unique())
for i,(key,h,label) in enumerate(TASKS):
    if key not in ts:
        matches=[t for t in ts if ('monthly' in t and str(h) in t)]
        assert len(matches)==1,(key,ts)
        TASKS[i]=(matches[0],h,label)

def fmt(x,n=1): return f'{float(x):.{n}f}'.replace('.',',')
def text(x,y,s,size=26,anchor='start',fill='#171717',weight='normal',rotate=None):
    trans=f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" font-weight="{weight}"{trans}>{escape(str(s))}</text>'
def line(x1,y1,x2,y2,color='#999',width=2,dash=''):
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-dasharray="{dash}"/>'
def rect(x,y,w,h,fill='#eef3f5',stroke='#c1cbd1',r=0):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>'
def save(name,body,w=1200,h=650):
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}"><rect width="100%" height="100%" fill="white"/><g font-family="Times New Roman,serif">{body}</g></svg>'
    (OUT/(name+'.svg')).write_text(svg,encoding='utf-8')
def box(x,y,w,h,lines,fill='#eef3f5',size=27):
    b=rect(x,y,w,h,fill,r=8)
    for i,s in enumerate(lines): b+=text(x+w/2,y+h/2-(len(lines)-1)*size*.58+i*size*1.16,s,size,'middle')
    return b
def arrow(x1,y1,x2,y2):
    return line(x1,y1,x2,y2,'#425865',3)+f'<path d="M{x2-9},{y2-6} L{x2},{y2} L{x2-9},{y2+6}" fill="none" stroke="#425865" stroke-width="3"/>'

# Causal workflow, explicit validation/test distinction and continuous target.
b=''
for x,ls in [(20,['NSRDB','checagem e agregação']),(425,['Cortes cronológicos','janelas causais']),(830,['Min max por local','antes do corte'])]: b+=box(x,20,350,105,ls)
b+=arrow(370,72,425,72)+arrow(775,72,830,72)
b+=line(1005,125,1005,170,'#425865',3)+line(190,170,1005,170,'#425865',3)
for x,ls in [(20,['X histórico','controle ou 64 128 256']),(425,['Modelo global','LSTM Transformer Informer']),(830,['Previsão contínua','inversão e regras físicas'])]: b+=box(x,205,350,110,ls)
b+=line(190,170,190,205,'#425865',3)+arrow(370,260,425,260)+arrow(775,260,830,260)
b+=box(20,365,350,85,['y contínuo preservado'],'#f6f3ed')+line(190,315,190,365,'#999',2,'6 6')
b+=box(425,365,350,85,['ID local → embedding'],'#f6f3ed')+line(600,315,600,365,'#999',2,'6 6')
b+=box(830,365,350,85,['Métricas por local','média macro'],'#eef4ef',25)+line(1005,315,1005,365,'#425865',3)
b+=box(20,505,550,110,['Validação escolhe épocas e nível','refit com dados anteriores ao teste'],'#edf3f7',27)
b+=box(630,505,550,110,['Teste avalia a escolha congelada','sem retorno para seleção'],'#f7f1ec',27)
save('01_fluxo',b,h=645)

# Quantization staircase, intentionally illustrative N=8 and actual error bounds.
b=text(100,42,'Transformação de amplitude',32,weight='bold')
x0,y0,w,h=110,440,630,330
xx=lambda x:x0+(x+.15)/1.3*w
yy=lambda y:y0-y*h
for v in [0,.25,.5,.75,1]:
    b+=line(x0,yy(v),x0+w,yy(v),'#e2e2e2',1)+text(x0-14,yy(v)+8,fmt(v,2),22,'end')
b+=line(x0,y0,x0+w,y0,'#333')+line(x0,y0,x0,y0-h,'#333')
b+=line(xx(-.15),yy(-.15),xx(1.15),yy(1.15),'#777',2,'8 6')
pts=[]
for u in np.linspace(-.15,1.15,700): pts.append(f'{xx(u):.2f},{yy(np.rint(np.clip(u,0,1)*7)/7):.2f}')
b+=f'<polyline points="{" ".join(pts)}" fill="none" stroke="#245680" stroke-width="4"/>'
for v in [0,.25,.5,.75,1]: b+=text(xx(v),y0+34,fmt(v,2),22,'middle')
b+=text(x0+w/2,515,'Entrada normalizada u',27,'middle')+text(28,285,'Q de u',27,'middle',rotate=-90)
b+=line(820,112,880,112,'#777',3,'8 6')+text(900,120,'Controle sem clip',26)
b+=line(820,165,880,165,'#245680',4)+text(900,173,'Quantizador ilustrado',26)
for i,ls in enumerate([['Escada ilustrativa com 8 níveis'],['Experimento: 64, 128 e 256 níveis'],['Passo normalizado: 1 / (N − 1)'],['Saturação fora de zero a um'],['Reconstrução mantida em float32']]):
    b+=text(815,245+i*53,ls[0],24)
b+=text(100,585,'A figura explica a operação e não representa uma série de GHI observada.',25)
save('02_quantizador',b,h=620)

# Actual compact architectures. No fabricated original-paper hyperparameters.
b=text(20,35,'Histórico causal e identidade local em todas as redes',29,weight='bold')
b+=text(20,97,'LSTM',30,weight='bold')
b+=box(20,122,260,120,['Histórico C × 1','LSTM 32 unidades'],size=27)+arrow(280,182,330,182)
b+=box(330,122,370,120,['Último estado oculto','+ embedding local de 8'],size=27)+arrow(700,182,750,182)
b+=box(750,122,430,120,['Camada linear 40 → H','vetor futuro contínuo'],size=27)
b+=text(20,300,'Transformer',30,weight='bold')
b+=box(20,325,360,135,['GHI + posição + ID local','2 encoders completos','dimensão 16'],size=26)+arrow(380,393,430,393)
b+=box(430,325,390,135,['1 decoder causal completo','cross attention completa','2 cabeças'],size=26)+arrow(820,393,870,393)
b+=box(870,325,310,135,['Projeção 16 → 1','em cada passo futuro'],size=26)
b+=text(20,518,'Informer',30,weight='bold')
b+=box(20,543,360,155,['2 encoders ProbSparse','1 distilação entre camadas','Conv BN ELU Pool'],size=26)+arrow(380,620,430,620)
b+=box(430,543,390,155,['Decoder causal ProbSparse','cross attention completa','fator 5'],size=26)+arrow(820,620,870,620)
b+=box(870,543,310,155,['Projeção 16 → 1','em cada passo futuro'],size=26)
b+=text(20,754,'Decoder de atenção: metade final do histórico seguida por H zeros, sem alvos futuros.',26)
save('03_arquiteturas',b,h=790)

def selected(regime,t,m):
    q=R[(R.regime==regime)&(R.tarefa==t)&(R.modelo==m)]
    assert len(q)==1,(regime,t,m,len(q)); return q.iloc[0]
def row(regime,t,m,h,var):
    q=D[(D.regime==regime)&(D.tarefa==t)&(D.modelo==m)&(D.horizonte==h)&(D.variante==var)]
    assert len(q)==1,(regime,t,m,h,var,len(q)); return q.iloc[0]

# 4 task panels, each own scale explicitly labelled.
b=''
for k,(t,H,label) in enumerate(TASKS):
    px=20+(k%2)*600; py=15+(k//2)*360
    b+=text(px+55,py+30,label,30,weight='bold')
    vals=[selected('atual',t,m).MAE_wm2 for m in MODELS]
    top=np.ceil(max(vals)/20)*20
    x,y,w,h=px+75,py+270,470,205
    for v in np.linspace(0,top,5): b+=line(x,y-v/top*h,x+w,y-v/top*h,'#dedede',1)+text(x-10,y-v/top*h+7,fmt(v,0),21,'end')
    for j,(m,v) in enumerate(zip(MODELS,vals)):
        bx=x+30+j*151
        b+=rect(bx,y-v/top*h,88,v/top*h,COL[m],COL[m])+text(bx+44,y-v/top*h-10,fmt(v),24,'middle')
        b+=text(bx+44,y+30,m,23,'middle')
    b+=text(px+18,py+177,'MAE em W/m²',23,'middle',rotate=-90)
b+=text(40,730,'Nível de entrada escolhido na validação; teste de 2024; escalas verticais próprias em cada painel.',25)
save('04_mae_atual',b,h=760)

# Full-horizon quantization sensitivity in current regime, no test-based selection.
b=text(20,35,'Variação percentual do MAE de teste em relação ao controle',30,weight='bold')
for j,q in enumerate(['q64','q128','q256']): b+=text(650+j*185,92,q[1:]+' níveis',26,'middle',weight='bold')
matrix=[]
for k,(t,H,label) in enumerate(TASKS):
    for j,m in enumerate(MODELS):
        y=112+(k*3+j)*45
        b+=text(20,y+29,(label if j==0 else '') ,24)+text(358,y+29,m,25)
        v0=row('atual',t,m,H,'sem_quantizacao').MAE_wm2
        chosen=selected('atual',t,m).variante
        for c,q in enumerate(['q64','q128','q256']):
            delta=(row('atual',t,m,H,q).MAE_wm2/v0-1)*100
            intensity=min(abs(delta)/10,1); rgb=(int(246-52*intensity),int(246-25*intensity),int(246-45*intensity)) if delta<0 else (int(246),int(246-75*intensity),int(246-92*intensity))
            fill='#%02x%02x%02x'%rgb
            b+=rect(565+c*185,y,170,42,fill,'#fff')+text(650+c*185,y+29,('★ ' if chosen==q else '')+('+' if delta>0 else '')+fmt(delta,2)+'%',24,'middle')
            matrix.append(dict(tarefa=t,modelo=m,variante=q,delta_pct=delta,selecionado=bool(chosen==q)))
b+=text(20,705,'Negativo indica menor erro. ★ Marca a variante escolhida na validação, quando quantizada.',25)
b+=text(20,744,'Células descrevem o teste e não são usadas para escolher o nível. Controle pode ser a escolha.',25)
save('05_quantizacao',b,h=775)

# Same-test paired history effect, unquantized inputs.
regs=list(D.regime.unique()); long='historico_1998_2022'; short='historico_curto_pareado'
history=[]
for t,H,label in TASKS:
    for m in MODELS:
        a=row(short,t,m,H,'sem_quantizacao').MAE_wm2; c=row(long,t,m,H,'sem_quantizacao').MAE_wm2
        history.append(dict(tarefa=t,rotulo=label,modelo=m,mae_curto=float(a),mae_longo=float(c),delta_pct=float((c/a-1)*100)))
b=text(20,35,'Efeito descritivo de ampliar o histórico com teste idêntico',30,weight='bold')
x0=1000; scale=5.5
for v in [-60,-40,-20,0,20]:
    x=x0+v*scale; b+=line(x,90,x,635,'#dedede',1)+text(x,676,('+' if v>0 else '')+str(v)+'%',23,'middle')
for i,z in enumerate(history):
    y=100+i*44; d=z['delta_pct']; end=x0+d*scale
    b+=text(20,y+26,(z['rotulo'] if i%3==0 else ''),24)+text(350,y+26,z['modelo'],25)
    b+=rect(min(x0,end),y+4,max(abs(d)*scale,2),29,'#35776C' if d<0 else '#B65B35','white')
    b+=text(end+(-10 if d<0 else 10),y+27,('+' if d>0 else '')+fmt(d,2)+'%',24,'end' if d<0 else 'start')
b+=line(x0,86,x0,638,'#333',2)
b+=text(20,732,'100 × (MAE longo dividido pelo MAE curto menos 1). Entradas sem quantização.',25)
save('06_historico',b,h=765)

# Horizon profiles. Cumulative, not exact-lead. Same choice from full-horizon validation.
b=''
for k,(t,H,label) in enumerate(TASKS):
    px=20+(k%2)*600; py=15+(k//2)*365
    x,y,w,h=px+82,py+270,445,200
    allrows=[]
    for m in MODELS:
        q=selected('atual',t,m).variante
        z=D[(D.regime=='atual')&(D.tarefa==t)&(D.modelo==m)&(D.variante==q)].sort_values('horizonte')
        allrows.append((m,z))
    horizons=sorted(allrows[0][1].horizonte.unique()); top=max(float(z.MAE_wm2.max()) for _,z in allrows)*1.18
    b+=text(px+65,py+30,label,30,weight='bold')
    for v in np.linspace(0,top,5): b+=line(x,y-v/top*h,x+w,y-v/top*h,'#dedede',1)+text(x-10,y-v/top*h+7,fmt(v,0),21,'end')
    xp=lambda v:x+w*.5 if len(horizons)==1 else x+(v-min(horizons))/(max(horizons)-min(horizons))*w
    for m,z in allrows:
        pts=[(xp(float(a.horizonte)),y-float(a.MAE_wm2)/top*h) for a in z.itertuples()]
        b+=f'<polyline points="{" ".join(f"{a},{c}" for a,c in pts)}" fill="none" stroke="{COL[m]}" stroke-width="4"/>'
        for a,c in pts:b+=f'<circle cx="{a}" cy="{c}" r="6" fill="{COL[m]}"/>'
    for v in horizons:b+=text(xp(v),y+29,str(v),23,'middle')
    b+=text(px+16,py+177,'MAE em W/m²',23,'middle',rotate=-90)
for j,m in enumerate(MODELS): b+=line(185+j*330,757,245+j*330,757,COL[m],4)+text(260+j*330,765,m,27)
b+=text(25,811,'Horizonte cumulativo em horas dias ou meses conforme o painel. Nível congelado pela validação.',25)
save('07_horizontes',b,h=845)
(OUT/'dados_graficos.json').write_text(json.dumps({'tarefas':TASKS,'quantizacao_atual':matrix,'historico_pareado':history},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'figuras':7,'tarefas':TASKS,'regimes':regs},ensure_ascii=False))
