from pathlib import Path
import json, hashlib, math, html
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RANK = ROOT / 'resultados/relatorios/pdfs_resumidos_legiveis_20261027/disciplina/classificacoes_modelos_disciplina.csv'
BASE = ROOT / 'resultados/quantizacao_todos_modelos_20260929/atual'
MODELS = ['Transformer', 'Informer', 'LSTM']
TASKS = [('hourly_72_extension', 72, 'Horária até 72 horas'), ('daily_30', 30, 'Diária até 30 dias'),
         ('monthly_1', 1, 'Mensal um passo'), ('monthly_6', 6, 'Mensal seis passos')]
SITES = [('BYD Camacari', 'BYD Camaçari'), ('Tesla Gigafactory Nevada', 'Tesla Nevada'),
         ('Tesla Gigafactory Texas', 'Tesla Texas'), ('Hyundai Metaplant Georgia', 'Hyundai Georgia'),
         ('Rivian Normal', 'Rivian Normal'), ('Tesla Fremont Factory', 'Tesla Fremont'),
         ('Lucid AMP 1 Casa Grande', 'Lucid Casa Grande'), ('GM Factory Zero', 'GM Factory Zero'),
         ('Ford Rouge Electric Vehicle Center', 'Ford Rouge EV'), ('BMW San Luis Potosi', 'BMW S. L. Potosí')]

def text(x,y,s,size=27,anchor='start',bold=False,fill='#222'):
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{"bold" if bold else "normal"}" fill="{fill}">{html.escape(str(s))}</text>'

def rect(x,y,w,h,fill,stroke='none',sw=1):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>'

def fmt(v,n=1): return f'{v:.{n}f}'.replace('.',',')
def variant(q): return 'Controle' if q=='sem_quantizacao' else 'Q'+q[1:]
rank = pd.read_csv(RANK)
all_data=[]; source_list=[]; audit=[]; panels=[]
for task,H,title in TASKS:
    grid=[]; variants=[]; paths=[]
    for model in MODELS:
        rr = rank[(rank.regime=='atual') & (rank.tarefa==task) & (rank.modelo==model)]
        assert len(rr)==1
        rr=rr.iloc[0]; variants.append(rr.variante)
        path=BASE/task/model.lower()/rr.variante/'metricas_por_localidade_teste.csv'
        dd=pd.read_csv(path); dd=dd[dd.horizonte==H]
        assert len(dd)==10 and dd.localidade.nunique()==10
        assert set(dd.localidade)==set(k for k,_ in SITES)
        vals=[float(dd.loc[dd.localidade==site,'MAE_wm2'].iloc[0]) for site,_ in SITES]
        macro=sum(vals)/len(vals)
        assert math.isclose(macro,float(rr.MAE_wm2),abs_tol=1e-10), (task,model,macro,rr.MAE_wm2)
        audit.append({'tarefa':task,'modelo':model,'variante':rr.variante,'macro_from_sites':macro,'macro_audited':float(rr.MAE_wm2),'match':True})
        grid.append(vals)
        src={'path':str(path.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        paths.append(src); source_list.append(src)
        for (site,label),value in zip(SITES,vals):
            all_data.append({'tarefa':task,'horizonte':H,'modelo':model,'variante':rr.variante,'localidade':site,'rotulo':label,'MAE_wm2':value})
    panels.append((task,H,title,variants,grid))

W,HIMG=1300,1210
b=text(18,36,'MAE por localidade no teste de 2024',32,bold=True)
b+=text(18,73,'Horizonte cumulativo completo e condição de entrada escolhida na validação',25)
for k,(task,HH,title,variants,grid) in enumerate(panels):
    px=18+(k%2)*650; py=107+(k//2)*526
    b+=text(px,py+30,chr(97+k)+') '+title,29,bold=True)
    if task=='monthly_6': b+=text(px+615,py+29,'Exploratório',22,'end',fill='#555')
    # Label column is compact enough for ten readable rows and three numeric columns.
    x=px+248; rowh=35; cw=120; y=py+112
    for j,m in enumerate(MODELS):
        b+=text(x+j*cw+cw/2,py+68,m,22,'middle',True)
        b+=text(x+j*cw+cw/2,py+96,variant(variants[j]),23,'middle',fill='#555')
    flat=[a for col in grid for a in col]; vmin=min(flat); vmax=max(flat)
    for i,(site,label) in enumerate(SITES):
        b+=text(px,y+i*rowh+25,label,25)
        best=min(grid[j][i] for j in range(3))
        for j in range(3):
            v=grid[j][i]; frac=(v-vmin)/(vmax-vmin)
            # A monotone blue scale within each task; darker means larger MAE.
            a=(247,250,252); z=(160,197,221)
            rgb=tuple(round(a[q]+(z[q]-a[q])*frac) for q in range(3))
            winner=math.isclose(v,best,abs_tol=1e-12)
            b+=rect(x+j*cw+1,y+i*rowh+1,cw-2,rowh-2,'#%02x%02x%02x'%rgb,'#344B5F' if winner else '#fff',2 if winner else 1)
            b+=text(x+j*cw+cw/2,y+i*rowh+25,fmt(v),26,'middle',winner)
    by=y+10*rowh+21
    b+=text(px,by+9,'Escala própria',22,fill='#555')
    gx=px+180; gw=270
    for n in range(90):
        frac=n/89; rgb=tuple(round(a[q]+(z[q]-a[q])*frac) for q in range(3))
        b+=rect(gx+n*gw/90,by-9,gw/90+0.3,17,'#%02x%02x%02x'%rgb)
    b+=text(gx,by+38,fmt(vmin)+' W/m²',22)
    b+=text(gx+gw,by+38,fmt(vmax)+' W/m²',22,'end')
    # Per-task local winners are descriptive, not significance results.

b+=text(18,1184,'Contorno e negrito indicam o menor MAE da localidade. A comparação é descritiva.',24)
svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{HIMG}" viewBox="0 0 {W} {HIMG}"><rect width="100%" height="100%" fill="white"/><g font-family="Arial,sans-serif">{b}</g></svg>'
(HERE/'11_mae_localidades.svg').write_text(svg,encoding='utf-8')
meta={'source_ranking':{'path':str(RANK.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(RANK.read_bytes()).hexdigest()},'source_files':source_list,'verification':audit,'values':all_data,'limitations':['Cores têm escala própria em cada tarefa.','Menor erro em uma localidade não comprova superioridade estatística.','Valores são MAEs das previsões combinadas, não média de MAEs por semente.']}
(HERE/'11_mae_localidades_dados.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
counts={}
for task,HH,title,variants,grid in panels:
    counts[task]={m:sum(grid[j][i]==min(col[i] for col in grid) for i in range(10)) for j,m in enumerate(MODELS)}
print(json.dumps({'figure':'11_mae_localidades.svg','cells':len(all_data),'macro_checks_passed':len(audit),'local_winner_counts':counts},ensure_ascii=False))
