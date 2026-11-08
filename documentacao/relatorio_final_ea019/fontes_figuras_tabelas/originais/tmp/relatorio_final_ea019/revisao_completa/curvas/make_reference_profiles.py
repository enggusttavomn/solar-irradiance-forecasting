"""Replot the article's archived forecasts, never substitute current experiment results."""
from pathlib import Path
from html import escape
import json, hashlib
import numpy as np
import pandas as pd

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=ROOT/'resultados/artigo_revista_unificado/revisao_20260907/perfis_sete_dias.csv'
METRICS=ROOT/'resultados/artigo_revista_unificado/revisao_20260907/metricas_perfis_sete_dias.csv'
DATA=pd.read_csv(SOURCE,parse_dates=['origem_local_fixa','timestamp_alvo_local_fixo','data_evento'])
EXPECTED=pd.read_csv(METRICS)
CASES=[('GM Factory Zero','2024-03-31','28 mar a 3 abr de 2024'),('Tesla Gigafactory Texas','2024-03-28','25 a 31 mar de 2024'),('Hyundai Metaplant Georgia','2024-08-05','2 a 8 ago de 2024')]
COLORS={'Referência NSRDB':'#202020','TimesNet':'#0072B2','DilatedRNN':'#D55E00'}
STYLES={'Referência NSRDB':'','TimesNet':'10 6','DilatedRNN':'12 5 3 5'}

def txt(x,y,s,size=26,anchor='start',bold=False,color='#202020',rotate=None):
    tr=f' transform="rotate({rotate} {x} {y})"' if rotate else ''
    return f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" font-weight="{700 if bold else 400}" fill="{color}"{tr}>{escape(str(s))}</text>'
def line(x,y,x2,y2,color='#D9E0E4',width=1,dash=''):
    return f'<line x1="{x}" y1="{y}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-dasharray="{dash}"/>'
def fmt(v):return f'{v:.2f}'.replace('.',',')

z=txt(20,39,'GHI de referência e previsões em sete dias',32,bold=True)
z+=txt(20,80,'Estudo de referência do artigo',29,bold=True,color='#52616B')
z+=txt(20,118,'Curvas arquivadas de TimesNet e DilatedRNN para os mesmos casos do artigo',24,color='#52616B')
audits=[]; rows=[]
for k,(site,event,period) in enumerate(CASES):
    event=pd.Timestamp(event); start=event-pd.Timedelta(days=3)
    d=DATA[DATA.localidade.eq(site)].sort_values('timestamp_alvo_local_fixo').copy()
    targets=pd.date_range(start,periods=168,freq='h')
    assert len(d)==168 and np.array_equal(d.timestamp_alvo_local_fixo.to_numpy(),targets.to_numpy())
    assert d.origem_local_fixa.nunique()==7 and d.origem_local_fixa.eq(d.timestamp_alvo_local_fixo.dt.normalize()).all()
    assert d.passo_h.eq(d.timestamp_alvo_local_fixo.dt.hour+1).all()
    assert set(d.semente)=={42}
    ytop=164+k*303
    z+=txt(20,ytop,f'{chr(97+k)}) {site}',29,bold=True)
    z+=txt(1260,ytop,period,23,'end',color='#52616B')
    px,py,w,h=95,ytop+208,1165,166
    xp=lambda j:px+j/168*w
    yp=lambda v:py-float(v)/1200*h
    # The selected event day is fixed by the source article, not reselected here.
    z+=f'<rect x="{xp(72)}" y="{py-h}" width="{w/7}" height="{h}" fill="#F1F1F1"/>'
    for v in [0,300,600,900,1200]:
        z+=line(px,yp(v),px+w,yp(v))+txt(px-14,yp(v)+7,str(v),23,'end')
    for j in range(8):
        z+=line(xp(j*24),py-h,xp(j*24),py,'#E3E7EA',1)
        if j<7:
            day=start+pd.Timedelta(days=j)
            months={3:'mar',4:'abr',8:'ago'}
            label=str(day.day)+' '+months[day.month]
            z+=txt(xp(j*24)+w/14,py+32,label,24,'middle')
    maes={}
    for label,col in [('TimesNet','previsao_pos_timesnet_wm2'),('DilatedRNN','previsao_pos_dilatedrnn_wm2'),('Referência NSRDB','ghi_real_wm2')]:
        vals=d[col].to_numpy(dtype=float)
        assert np.isfinite(vals).all() and vals.min()>=0 and vals.max()<=1200
        pts=' '.join(f'{xp(i):.2f},{yp(v):.2f}' for i,v in enumerate(vals))
        z+=f'<polyline points="{pts}" fill="none" stroke="{COLORS[label]}" stroke-width="{3.5 if label=="Referência NSRDB" else 3.1}" stroke-dasharray="{STYLES[label]}"/>'
        if label!='Referência NSRDB':
            maes[label]=float(np.mean(np.abs(d.ghi_real_wm2.to_numpy()-vals)))
            expected=float(EXPECTED.loc[EXPECTED.localidade.eq(site),'MAE_'+label].iloc[0])
            assert np.isclose(maes[label],expected,atol=1e-12)
    z+=txt(27,ytop+126,'GHI W/m²',24,'middle',rotate=-90)
    z+=txt(1260,ytop+33,'MAE nos 168 pontos  TimesNet '+fmt(maes['TimesNet'])+'  |  DilatedRNN '+fmt(maes['DilatedRNN'])+' W/m²',22,'end',color='#52616B')
    audits.append({'localidade':site,'inicio':str(targets.min()),'fim':str(targets.max()),'N_pontos':168,'N_origens':7,'passos':'1 a 24 de cada saída de 72 h','seed':42,'evento':str(event.date()),'MAE':maes,'timesnet_and_dilatedrnn_match_archived_metrics':True})
    rows.append(d)

for j,(label,lx) in enumerate(zip(COLORS,[140,600,930])):
    z+=line(lx,1101,lx+50,1101,COLORS[label],3.4,STYLES[label])+txt(lx+65,1110,label,25)
z+=txt(20,1163,'Sete prefixos de 24 h das saídas de 72 h; uma nova emissão a cada meia-noite local.',23,color='#52616B')
z+=txt(20,1201,'Faixa cinza: dia destacado no artigo. Mesma escala de GHI nos três painéis.',23,color='#52616B')
z+=txt(20,1239,'Curvas de referência anteriores ao experimento de quantização; semente 42.',23,color='#52616B')
svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="1300" height="1265" viewBox="0 0 1300 1265"><rect width="100%" height="100%" fill="white"/><g font-family="Arial,sans-serif">{z}</g></svg>'
(HERE/'perfis_sete_dias_artigo_referencia.svg').write_text(svg,encoding='utf-8')
pd.concat(rows,ignore_index=True).to_csv(HERE/'perfis_sete_dias_artigo_referencia.csv',index=False)
manifest={'description':'Curvas arquivadas do estudo de referência do artigo, replotadas sem treinamento ou inferência nova.','sources':[{'path':str(p.relative_to(ROOT)).replace('\\','/'),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [SOURCE,METRICS]],'checks':audits,'scope':'TimesNet e DilatedRNN da versão final do artigo. Não representam Transformer/Informer/LSTM Q64 da avaliação de quantização atual.','selection':'Mesmos eventos e janela do artigo: dia selecionado mais três dias anteriores e três posteriores. GM em 31mar2024 e Texas em 28mar2024 foram escolhidos por diferenças de erro de TimesNet versus DilatedRNN no dia; Hyundai em 5ago2024 foi escolhido no artigo por evento meteorológico independente dos erros. A figura não acrescenta interpretação meteorológica.','display':'7 prefixos de 24 h extraídos das saídas de 72 h; não é uma previsão única de 168 h.','processing':'Usam as previsões pós-processadas em W/m², já invertidas para unidade física na fonte, com piso zero e anulação noturna. Nenhuma desnormalização ou clipping adicional foi aplicada.','limitation':'As curvas são descritivas dos casos previamente selecionados e não entram nos rankings ou conclusões sobre quantização.'}
(HERE/'perfis_sete_dias_artigo_referencia_manifesto.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(audits,ensure_ascii=False))
