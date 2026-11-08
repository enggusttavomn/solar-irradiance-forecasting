from pathlib import Path
from html import escape
import json, shutil
import numpy as np
import pandas as pd
from PIL import ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = HERE / 'figuras'
OUT.mkdir(parents=True, exist_ok=True)
BLUE, ORANGE, GREEN = '#245680', '#B65B35', '#35776C'
INK, MUTED, GRID = '#202A30', '#52616B', '#D9E0E4'

def text(x,y,s,size=24,anchor='start',bold=False,color=INK,rotate=None):
    tf = f' transform="rotate({rotate} {x} {y})"' if rotate else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{700 if bold else 400}" fill="{color}"{tf}>{escape(str(s))}</text>'

def rect(x,y,w,h,fill='white',stroke=GRID,r=6):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="1.8"/>'

def line(x,y,x2,y2,color=GRID,width=2,dash=''):
    return f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-dasharray="{dash}"/>'

def arrow(x,y,x2,y2,color=MUTED):
    return line(x,y,x2,y2,color,2.4)+f'<path d="M{x2-8},{y2-6} L{x2},{y2} L{x2-8},{y2+6}" fill="none" stroke="{color}" stroke-width="2.4"/>'

def block(x,y,w,h,title,lines,color=BLUE,fill='#F1F6FA',size=23):
    z=rect(x,y,w,h,fill,color)
    def fit(s,desired,bold=False):
        font='C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf'
        while ImageFont.truetype(font,int(desired)).getlength(s)>w-30:desired-=.5
        assert desired>=19,(s,desired)
        return desired
    z+=text(x+15,y+31,title,fit(title,25,True),bold=True,color=color)
    for i,s in enumerate(lines):z+=text(x+15,y+65+i*29,s,fit(s,size))
    return z

def save(name,z,h):
    (OUT/(name+'.svg')).write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{h}" viewBox="0 0 1200 {h}"><rect width="1200" height="{h}" fill="white"/><g font-family="Arial,sans-serif">{z}</g></svg>',encoding='utf-8')

# Three bands follow the conceptual organization of Figure 2 of the supplied paper.
z=''
bands=[(15,'A','DADOS E TAREFAS',BLUE),(237,'B','SELEÇÃO E REFIT',ORANGE),(459,'C','TESTE E AVALIAÇÃO',GREEN)]
for y,letter,title,color in bands:
    z+=rect(10,y,53,192,color,color)
    z+=text(36,y+106,letter,33,'middle',True,'white')
    z+=text(79,y+26,title,24,bold=True,color=color)
z+=block(79,60,340,139,'Fonte e auditoria',['10 células da NSRDB','Brasil, EUA e México','GHI regular, finita e ≥ 0'])
z+=block(457,60,340,139,'Entradas causais',['Histórico de GHI + ID local','Escala anterior ao corte','Alvos dentro da partição'])
z+=block(835,60,350,139,'Quatro tarefas diretas',['336 h → 72 h; 365 d → 30 d','12 meses → 1 mês','12 → 6 meses exploratórios'])
z+=arrow(420,130,454,130)+arrow(798,130,832,130)
z+=block(79,282,340,139,'Condições de entrada',['Contínua, Q64, Q128 ou Q256','Quantização somente em X','LSTM, Transformer e Informer'],ORANGE,'#FCF5EF')
z+=block(457,282,340,139,'Validação fixa escolhas',['Épocas por variante/semente','Nível pelo macro-MAE completo','Teste fora da seleção'],ORANGE,'#FCF5EF')
z+=block(835,282,350,139,'Refit e congelamento',['Reiniciar na mesma semente','Ajuste com dados pré-teste','Fixar rede, escala e nível'],ORANGE,'#FCF5EF')
z+=arrow(420,352,454,352)+arrow(798,352,832,352)
z+=block(79,504,340,139,'Previsões de teste',['Origens com histórico causal','Vetor futuro contínuo direto','Sem reajustar pesos ou escala'],GREEN,'#F0F7F4')
z+=block(457,504,340,139,'Regras comuns',['Inversão; média de sementes','Piso zero em todas as tarefas','Noite zerada na tarefa horária'],GREEN,'#F0F7F4')
z+=block(835,504,350,139,'Evidência por localidade',['MAE, RMSE, nRMSE e R² locais','Média macro com pesos iguais','Horizontes cumulativos'],GREEN,'#F0F7F4')
z+=arrow(420,574,454,574)+arrow(798,574,832,574)
z+=text(80,689,'O alvo y e os pesos permanecem contínuos; o ID local não passa pelo quantizador.',24,color=MUTED)
save('01_fluxo',z,715)

# A precise amplitude diagram, including the deliberate asymmetry of clipping.
z=text(35,39,'Apenas a amplitude do histórico de GHI é transformada',27,bold=True)
x0,y0,w,h=100,448,625,315
xx=lambda v:x0+(v+.15)/1.3*w
yy=lambda v:y0-v*h
for v in [0,.25,.5,.75,1]:
    z+=line(x0,yy(v),x0+w,yy(v),GRID,1)+text(x0-13,yy(v)+7,str(v).replace('.',','),22,'end')
    z+=text(xx(v),y0+32,str(v).replace('.',','),22,'middle')
z+=line(x0,y0,x0+w,y0,INK)+line(x0,y0,x0,y0-h,INK)
z+=line(xx(-.15),yy(-.15),xx(1.15),yy(1.15),MUTED,2,'8 6')
pts=[f'{xx(v):.3f},{yy(np.rint(np.clip(v,0,1)*7)/7):.3f}' for v in np.linspace(-.15,1.15,800)]
z+=f'<polyline points="{" ".join(pts)}" fill="none" stroke="{BLUE}" stroke-width="4"/>'
z+=text(x0+w/2,525,'Entrada normalizada u',24,'middle')
z+=text(25,290,'Saída QN(u)',24,'middle',rotate=-90)
z+=line(790,115,850,115,MUTED,2,'8 6')+text(868,123,'Controle contínuo',23)
z+=line(790,160,850,160,BLUE,4)+text(868,168,'Entrada quantizada',23)
for i,s in enumerate(['8 níveis no esquema ilustrativo','64, 128 ou 256 no experimento','Passo de amplitude 1 / (N − 1)','Saturação abaixo de 0 e acima de 1','Reconstrução em float32']):z+=text(790,235+i*42,s,23)
z+=text(35,585,'O controle não aplica clipping; a comparação reúne arredondamento e saturação.',24,color=MUTED)
save('02_quantizador',z,615)

# Architectures are implementation diagrams, rather than generic model-family icons.
z=text(20,36,'Mesmo histórico causal e mesma identidade local',27,bold=True)
for y,name,color in [(65,'LSTM',GREEN),(280,'Transformer',BLUE),(520,'Informer',ORANGE)]:
    z+=text(20,y+28,name,28,bold=True,color=color)
z+=block(20,115,305,122,'Encoder recorrente',['Histórico C × 1','LSTM com 32 unidades'],GREEN,'#F0F7F4')
z+=block(370,115,380,122,'Estado e identidade',['Último estado oculto: 32','Concatenar embedding local: 8'],GREEN,'#F0F7F4')
z+=block(795,115,385,122,'Saída direta',['Camada linear 40 → H','H valores futuros contínuos'],GREEN,'#F0F7F4')
z+=arrow(327,177,367,177)+arrow(752,177,792,177)
z+=block(20,330,350,145,'Encoder completo',['Projeção GHI + posição + ID','2 camadas de encoder','Dimensão 16; 2 cabeças'])
z+=block(415,330,390,145,'Decoder completo',['Autoatenção com máscara causal','Atenção cruzada à memória','1 camada de decoder'])
z+=block(850,330,330,145,'Projeção futura',['Camada linear 16 → 1','Aplicada nas H posições','Saída contínua'])
z+=arrow(372,402,412,402)+arrow(807,402,847,402)
z+=block(20,570,350,155,'Encoder ProbSparse',['2 camadas; dimensão 16','Distilação entre as camadas','Conv + BN + ELU + Pool'],ORANGE,'#FCF5EF')
z+=block(415,570,390,155,'Decoder ProbSparse',['Autoatenção causal esparsa','Atenção cruzada completa','1 camada; fator de amostragem 5'],ORANGE,'#FCF5EF')
z+=block(850,570,330,155,'Projeção futura',['Camada linear 16 → 1','Aplicada nas H posições','Saída contínua'],ORANGE,'#FCF5EF')
z+=arrow(372,647,412,647)+arrow(807,647,847,647)
z+=text(20,775,'Entrada do decoder nas redes de atenção: metade final do histórico + H zeros.',24,color=MUTED)
z+=text(20,812,'Os zeros indicam posições futuras; os valores reais dos alvos não entram no decoder.',24,color=MUTED)
save('03_arquiteturas',z,840)

# Input/output windows distinguish temporal resolution from forecast horizon.
z=text(20,35,'De um histórico observado para um vetor de previsões',27,bold=True)
z+=text(360,80,'Contexto C',24,'middle',True,BLUE)+text(845,80,'Horizonte H',24,'middle',True,ORANGE)
z+=line(660,90,660,428,MUTED,2,'7 5')+text(660,466,'Origem da previsão',23,'middle',True)
rows=[('Horária','336 horas','72 horas',110),('Diária','365 dias','30 dias',187),('Mensal','12 meses','1 mês',264),('Mensal exploratória','12 meses','6 meses',341)]
for label,c,h,y in rows:
    z+=text(20,y+29,label,23,bold=True)
    z+=rect(250,y,390,47,'#EAF1F7',BLUE)+text(445,y+31,c,24,'middle',True,BLUE)
    z+=arrow(642,y+23,685,y+23)
    z+=rect(690,y,320,47,'#FCF0E6',ORANGE)+text(850,y+31,h,24,'middle',True,ORANGE)
    z+=text(1040,y+30,'y contínuo',23,color=MUTED)
z+=text(20,515,'Comprimentos desenhados de forma esquemática; as unidades mudam entre tarefas.',23,color=MUTED)
save('08_janelas',z,545)

# Temporal partitions: periods are represented categorically, not with misleading equal scales.
z=text(20,37,'Seleção antes do teste e comparação histórica pareada',27,bold=True)
colors=[('#EAF1F7',BLUE),('#FCF0E6',ORANGE),('#EAF4F0',GREEN)]
columns=[(250,330,'Treino inicial'),(605,265,'Validação'),(895,285,'Teste')]
for x,w,title in columns:z+=text(x+w/2,85,title,24,'middle',True)
periods=[('Atual',113,['jan 2019 a dez 2022','jan a dez 2023','jan a dez 2024']),('Histórico longo',207,['jan 1998 a mar 2018','abr 2018 a mar 2019','abr 2019 a dez 2022']),('Curto pareado',301,['abr 2014 a mar 2018','abr 2018 a mar 2019','abr 2019 a dez 2022'])]
for label,y,values in periods:
    z+=text(20,y+37,label,24,bold=True)
    for (x,w,title),val,(fill,color) in zip(columns,values,colors):
        z+=rect(x,y,w,58,fill,color)+text(x+w/2,y+36,val,23,'middle',color=color)
z+=line(611,382,1175,382,GREEN,2)+text(890,416,'Mesmas datas de validação e teste nos dois históricos',23,'middle',color=GREEN)
z+=text(20,468,'Refit incorpora o período pré-teste pelo número de épocas previamente escolhido.',23,color=MUTED)
z+=text(20,507,'Blocos sem escala de duração; 2024 é outro teste e deve ser analisado separadamente.',23,color=MUTED)
save('09_particoes',z,535)

# Real input series, selected by fixed calendar dates rather than forecast error.
dpath=ROOT/'dados/brutos/localidades_ev/byd_camacari.csv'
hpath=ROOT/'dados/brutos/localidades_ev_horario/nsrdb_ghi_horaria_2024.csv.gz'
daily=pd.read_csv(dpath,usecols=['data','ghi'])
daily['data']=pd.to_datetime(daily['data'])
daily=daily[daily.data.dt.year.eq(2024)].sort_values('data')
hourly=pd.read_csv(hpath,usecols=['timestamp_utc','ghi','localidade','timezone_nsrdb'])
hourly=hourly[hourly.localidade.eq('BYD Camacari')].copy()
assert len(daily)==366 and len(hourly)==8784
hourly['local_time']=pd.to_datetime(hourly.timestamp_utc,utc=True).dt.tz_localize(None)+pd.to_timedelta(hourly.timezone_nsrdb,unit='h')
hs=hourly[(hourly.local_time>='2024-01-01')&(hourly.local_time<'2024-01-08')].sort_values('local_time')
ds=daily[daily.data.dt.month.eq(1)]
ms=daily.set_index('data').ghi.resample('MS').mean()
z=text(20,36,'BYD Camaçari em 2024',27,bold=True)
z+=text(20,72,'Séries de referência da NSRDB em três resoluções temporais',24,color=MUTED)
chartdata=[]
panels=[('A  Médias horárias de 1 a 7 de janeiro',hs.ghi.to_numpy(),[0,24,48,72,96,120,144],['1','2','3','4','5','6','7'],'Dia de janeiro em hora local',0,1200),('B  Médias diárias de janeiro',ds.ghi.to_numpy(),[0,7,14,21,30],['1','8','15','22','31'],'Dia de janeiro',1,400),('C  Médias mensais de janeiro a dezembro',ms.to_numpy(),list(range(12)),['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez'],'Mês de 2024',2,400)]
for title,vals,ticks,labels,xlab,i,top in panels:
    ytop=115+i*250; x,y,w,hh=95,ytop+156,1065,130
    z+=text(20,ytop,title,24,bold=True)
    for v in [0,top/2,top]:
        yy_=y-v/top*hh
        z+=line(x,yy_,x+w,yy_,GRID,1)+text(x-12,yy_+7,int(v),21,'end')
    xp=lambda j:x+j/(len(vals)-1)*w
    pts=' '.join(f'{xp(j):.2f},{y-float(v)/top*hh:.2f}' for j,v in enumerate(vals))
    z+=f'<polyline points="{pts}" fill="none" stroke="{BLUE}" stroke-width="2.5"/>'
    if i>0:
        for j,v in enumerate(vals):z+=f'<circle cx="{xp(j):.2f}" cy="{y-v/top*hh:.2f}" r="3.5" fill="{BLUE}"/>'
    for tick,label in zip(ticks,labels):z+=text(xp(tick),y+29,label,21,'middle')
    z+=text(25,ytop+107,'GHI W/m²',21,'middle',rotate=-90)+text(630,y+64,xlab,22,'middle')
    chartdata.append({'panel':title,'values':list(map(float,vals))})
z+=text(20,877,'Horária: média de registros de 30 min; diária: consulta independente de 60 min.',22,color=MUTED)
z+=text(20,911,'Mensal: média aritmética das médias diárias. Escalas verticais próprias por painel.',22,color=MUTED)
save('10_perfis_dados',z,935)
(HERE/'dados_perfis_referencia.json').write_text(json.dumps({'daily_source':str(dpath),'hourly_source':str(hpath),'hourly_n':len(hs),'daily_n':len(ds),'monthly_n':len(ms),'data':chartdata},ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(ROOT/'artigos/revista_unificado/figures/mapa_contexto_geografico.png',OUT/'11_mapa.png')
print(json.dumps({'svg':len(list(OUT.glob('*.svg'))),'hourly_points':len(hs),'daily_points':len(ds),'monthly_points':len(ms)},ensure_ascii=False))
