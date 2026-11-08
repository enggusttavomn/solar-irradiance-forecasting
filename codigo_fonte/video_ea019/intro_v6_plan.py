"""Narration and labels for the requested revised forty-second excerpt."""
import json
from pathlib import Path
import textwrap

from overlays import Cue, Overlay

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
PHASES=[
 (0,4.4,'GHI é a potência solar recebida por unidade de área horizontal.'),
 (4.4,10.8,'Aqui, a região mede um metro por um metro. A unidade é watt por metro quadrado.'),
 (10.8,16,'Parte da luz vem diretamente do Sol, e parte é espalhada pela atmosfera.'),
 (16,21,'A luz varia durante o dia. À noite, a irradiância solar praticamente zera.'),
 (21,25.2,'A passagem de nuvens modifica a luz recebida e a curva.'),
 (25.2,30,'O histórico reúne esses padrões diários e as variações da atmosfera.'),
 (30,35,'Com esse histórico, tentamos antecipar a continuação da curva.'),
 (35,40,'Prever o recurso solar pode apoiar o planejamento fotovoltaico. Meu objetivo foi...'),
]


def cues():
    result=[]
    for a,b,text in PHASES:
        lines=textwrap.wrap(text,42,break_long_words=False,break_on_hyphens=False)
        chunks=[lines[0],'\n'.join(lines[1:])] if len(lines)==3 else ['\n'.join(lines[i:i+2]) for i in range(0,len(lines),2)]
        total=sum(len(x) for x in chunks)
        t=a
        for i,chunk in enumerate(chunks):
            end=b if i==len(chunks)-1 else round(t+(b-a)*len(chunk)/total,3)
            result.append(Cue(t,end,chunk));t=end
    return result


def srt_time(second):
    value=round(second*1000)
    return f'{value//3600000:02d}:{value//60000%60:02d}:{value//1000%60:02d},{value%1000:03d}'


def write_ass(path,include_captions=True):
    o=Overlay(40)
    o.text(5.3,10.8,'Superfície horizontal',x=960,y=140,size=40,align=8)
    o.text(8.0,10.8,'W/m²',x=1500,y=215,size=48,align=8)
    o.text(11.1,16,'GHI = DNI · cos(θz) + DHI',x=960,y=70,size=59,align=8,bold=True)
    o.text(12.9,16,'DHI: difusa horizontal',x=1320,y=170,size=33,align=8,color='C6DFEE')
    o.text(11.1,16,'DNI: direta normal',x=550,y=170,size=33,align=8,color='EFE7D7')
    o.text(12,16,'θz: ângulo com a vertical',x=960,y=235,size=32,align=8,color='CFD5DC')
    o.text(11.2,16,'Direta',x=740,y=525,size=38,align=8,color='EFE7D7')
    o.text(13.4,16,'Difusa',x=1230,y=525,size=38,align=8,color='C6DFEE')
    o.text(35.1,40,'Planejamento fotovoltaico',x=960,y=80,size=46,align=8)
    if include_captions:
        for cue in cues():o.caption(cue)
    return o.write(path)


def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    data=[{'start':c.start,'end':c.end,'text':c.text} for c in cues()]
    (OUT/'plano_textos_v6.json').write_text(json.dumps({'duration':40,'phases':PHASES,'cues':data,
      'scope':'Revised excerpt0:00–0:40 only; original V5 preserved; narration to record later.'},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    stamp=lambda t:f'{int(t)//60}:{t%60:04.1f}'
    (OUT/'Falas_00_40_v6.txt').write_text('FALAS PARA NARRAR - REVISÃO DE 0:00 A 0:40\n\n'+
      '\n\n'.join(f'{stamp(a)} - {stamp(b)}\n{text}' for a,b,text in PHASES)+
      '\n\nA frase final retoma o trecho seguinte: “comparar LSTM, Transformer e Informer...”.\n',encoding='utf-8-sig')
    (OUT/'Legendas_00_40_v6.srt').write_text('\n\n'.join(f'{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}' for i,c in enumerate(cues(),1))+'\n',encoding='utf-8-sig')
    for captions,suffix in [(True,'com_legendas'),(False,'sem_legendas')]:
        report=write_ass(OUT/f'textos_{suffix}_v6.ass',captions)
        (OUT/f'verificacao_textos_{suffix}_v6.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return data


if __name__=='__main__':
    prepare();print('V6_TEXTS_READY',flush=True)
