"""Continuous 3D explanation of the two inputs and four forecasting tasks."""
import math
import bpy
from common_v7 import *

DURATION=70
CUES=[
 (0,8,'Uma entrada é o histórico de GHI: uma sequência de valores, organizada no tempo.'),
 (8,16,'A outra entrada identifica a localidade. Esse número se transforma numa representação aprendida pela rede.'),
 (16,24,'Neste experimento, os modelos recebem o histórico de GHI e a identificação da localidade.'),
 (24,32,'Cada modelo compartilha seus parâmetros entre as dez localidades. Os dados mudam; a estrutura é a mesma.'),
 (32,36,'A previsão foi organizada em quatro tarefas, com escalas e horizontes diferentes.'),
 (36,41.5,'Na tarefa horária, a entrada reúne 336 horas, equivalentes a duas semanas.'),
 (41.5,47,'Com esse histórico, a rede prevê as próximas 72 horas: três dias de irradiância.'),
 (47,52.5,'Na tarefa diária, 365 valores representam um ano de histórico.'),
 (52.5,58,'A saída contém os próximos trinta dias. A escala muda, mas a ideia de passado e futuro permanece.'),
 (58,64,'Na primeira tarefa mensal, doze meses de histórico ajudam a prever o mês seguinte.'),
 (64,70,'Na outra tarefa mensal, uma rede treinada separadamente prevê seis meses. Essa análise é exploratória.'),
]

def wave(count,cycles=3):
    return [max(0,math.sin(i/(count-1)*cycles*2*math.pi-.5))**1.4*(.76+.12*math.sin(i*.27)) for i in range(count)]

def curved(name,a,b,mat,start,end,bulge=.8):
    points=[]
    for i in range(45):
        t=i/44;points.append((a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t+bulge*math.sin(math.pi*t)))
    c=polyline(name,points,mat,.025);visible(c,start,end);reveal(c,start,1);return c

def build(scene):
    mats={k:surface('V7 entrada '+k,v,metallic=.15,roughness=.34) for k,v in [('cyan',CYAN),('coral',CORAL),('violet',VIOLET),('gold',GOLD),('silver',(.52,.61,.66,1))]}
    white=emission('V7 texto branco',WHITE,.9)
    ink=emission('V7 eixo neutro',(.38,.46,.50,1),.8)
    cyan=emission('V7 curva ciano',(.25,.78,.85,1),.9)
    past=emission('V7 curva histórica',(.80,.88,.91,1),.9)
    gold=emission('V7 ID ouro',(.91,.68,.28,1),.8)
    # A curve becomes an ordered strip of sampled values: same x/time positions.
    vals=wave(28,3)
    trace=polyline('Histórico contínuo de GHI',[(-6+i*12/27,0,2+v*2.4) for i,v in enumerate(vals)],past,.025)
    visible(trace,0,8);reveal(trace,0,2)
    axis=polyline('Tempo da sequência',[(-6.4,0,1.6),(6.4,0,1.6)],ink,.012);visible(axis,0,8)
    label('Valor e tempo','Histórico de GHI',(-.2,0,6.2),.56,white,0,8)
    label('Sequência temporal','Passado  →  agora',(0,-.1,.85),.35,white,1,8)
    for i,v in enumerate(vals):
        cube=box('Amostra GHI %02d'%i,(-6+i*12/27,0,2+v*2.4),(.20,.32,.20+v*.5),mats['cyan'],.045)
        visible(cube,2+i*.05,8);grow(cube,2+i*.05,.4)
        keys(cube,'location',[(4,tuple(cube.location)),(6.5,(-6+i*12/27,0,2.8))])
    # Local identity -> learned vector, with real geometric movement.
    tile=box('Identificador da localidade',(-4.6,0,3.3),(1.5,.38,1.5),mats['gold'],.15);visible(tile,8,16);grow(tile,8,.5)
    label('Identificador numérico','ID 01',(-4.6,-.28,3.3),.50,white,8,16)
    label('Entrada local','Localidade',(-4.6,0,5.6),.48,white,8,16)
    arrow('ID para embedding',(-3.2,0,3.3),(-1,0,3.3),white,9,16)
    for j in range(8):
        h=.35+.23*((j*7+3)%6)
        token=box('Componente aprendida %d'%j,(.1+j*.58,0,3.3),(.35,.45,h),mats['gold'],.06)
        visible(token,10+j*.12,16);grow(token,10+j*.12,.5)
    label('Embedding local','Representação aprendida',(2.3,0,5.6),.48,white,10,16)
    # Two information streams join one model. This is input scope, not invented internal wiring.
    roots=[]
    for layer in range(3):
        for j in range(4):
            node=sphere('Parâmetro compartilhado %d %d'%(layer,j),(1.1+layer*.9,.25,2.2+j*.62),.15,mats['silver'])
            visible(node,16,32);roots.append(node)
            if layer<2:
                for k in range(4):
                    c=polyline('Conexão interna %d %d %d'%(layer,j,k),[(1.1+layer*.9,.25,2.2+j*.62),(2+layer*.9,.25,2.2+k*.62)],ink,.006)
                    visible(c,16,32)
    label('Corpo único','Mesmo modelo',(2,0,5.6),.52,white,16,32)
    for i,v in enumerate(wave(16,2)):
        o=box('Histórico entrando %02d'%i,(-6.2+i*.24,0,4.1+v*.55),(.13,.18,.16),mats['cyan'],.025)
        visible(o,16,24);keys(o,'location',[(16,tuple(o.location)),(19.5,(-.3+i*.05,0,3.8))])
    label('Canal GHI','Histórico de GHI',(-4.6,0,5.4),.45,white,16,24)
    curved('Entrada GHI',(-2.6,0,4.4),(.8,0,3.9),cyan,17,24,.35)
    loc=box('Identidade da entrada',(-4.6,0,2.0),(1.4,.25,.72),mats['gold'],.08);visible(loc,16,24)
    label('Canal ID','ID da localidade',(-4.6,-.2,2),.31,white,16,24)
    curved('Entrada identidade',(-3.5,0,2),(.8,0,2.7),gold,18,24,-.4)
    arrow('Vetor de saída',(3.4,0,3.1),(4.5,0,3.1),cyan,18.5,32)
    for i,v in enumerate(wave(10,1.3)):
        o=box('Previsão vetorial %d'%i,(4.9+i*.24,0,2.7+v*.9),(.12,.18,.18),mats['cyan'],.02);visible(o,19,32);grow(o,19+i*.08,.4)
    label('Saída única','Previsão',(5.9,0,5.4),.45,white,19,32)
    # Ten sites take turns through identical fixed network; no per-site retraining animation.
    for i in range(10):
        t=24+i*.64
        row=1.9+(i%5)*.65;col=-6.2+(i//5)*1.55
        o=box('Localidade compartilhada %d'%i,(col,0,row),(1.05,.25,.45),mats['gold'],.05);visible(o,24,32)
        label('Nome local %d'%i,'%02d'%(i+1),(col,-.18,row),.26,white,24,32)
        dot=sphere('Fluxo local %d'%i,(col+.65,0,row),.07,mats['gold']);visible(dot,t,t+1)
        keys(dot,'location',[(t,(col+.65,0,row)),(t+.8,(.7,0,3.1))])
        curved('Percurso ID %d'%i,(col+.65,.1,row),(.7,.1,3.1),gold,t,min(32,t+1),.2)
    label('Conjunto de localidades','10 localidades',(-4.7,0,5.6),.48,white,24,32)
    # A common time axis survives every task. The camera approaches it once.
    for second,scale,target in [(0,17,(0,0,3.5)),(7.8,16.5,(0,0,3.5)),(8,17,(0,0,3.5)),(31.8,17,(0,0,3.5)),(32,17,(0,0,3.3)),(36,17,(0,0,3.3)),(70,16.7,(0,0,3.3))]:
        camera_key(scene,second,(target[0],-28,target[2]+3.2),target,scale)
    for j,name in enumerate(['Horária','Diária','Mensal: 1 mês','Mensal: 6 meses']):
        z=5.5-j*1.1
        label('Quatro tarefas '+name,name,(-4.8,0,z),.42,white,32,36)
        p=polyline('Faixa '+name,[(-1.8,0,z),(1.8,0,z)],past,.024);visible(p,32,36);reveal(p,32+j*.2,.6)
        p=polyline('Futuro '+name,[(2,0,z),(5.5,0,z)],cyan,.024);visible(p,32,36);reveal(p,32.7+j*.2,.6)
    # These are independently fitted input/output windows, not one uniform time scale.
    # A physical axis break keeps 336 past samples and 72 future samples readable.
    for name,points in [('Eixo histórico',[(-6.4,0,1.65),(1.22,0,1.65)]),
                        ('Eixo horizonte',[(1.83,0,1.65),(6.4,0,1.65)]),
                        ('Quebra de escala',[(1.30,0,1.52),(1.40,0,1.77),(1.50,0,1.52),(1.60,0,1.77)])]:
        baseline=polyline(name,points,ink,.012);visible(baseline,36,70)
    border=polyline('Fronteira do instante presente',[(1.5,0,1.3),(1.5,0,5.3)],ink,.012);visible(border,36,70)
    label('Passado comum','Histórico',(-2.5,0,1.0),.34,white,36,70)
    label('Futuro comum','Previsão',(4,0,1),.34,white,36,70)
    label('Potência por área','GHI (W/m²)',(-5.8,0,5.45),.30,white,36,70)
    task_defs=[(36,47,'Horária','336 horas = 14 dias','72 horas = 3 dias',14,3),
               (47,58,'Diária','365 dias = 1 ano','30 dias',5.4,1.2),
               (58,64,'Mensal · 1 passo','12 meses','1 mês',1.1,.2),
               (64,70,'Mensal · 6 passos','12 meses','6 meses',1.1,.55)]
    for idx,(a,b,title,hist,fut,cycles,fc) in enumerate(task_defs):
        label('Tarefa '+title,title,(0,0,6.3),.63,white,a,b)
        label('Entrada '+title,hist,(-2.5,0,.60),.44,white,a,b)
        label('Horizonte '+title,fut,(4,0,.60),.44,white,a,b)
        n=336 if idx==0 else 365 if idx==1 else 12
        values=wave(n,cycles) if idx==0 else [(.48+.22*math.sin(i/max(1,n-1)*cycles*2*math.pi)+.08*math.sin(i*.53)) for i in range(n)]
        pts=[(-6+i*7.2/(n-1),0,1.7+values[i]*2.4) for i in range(n)]
        c=polyline('Histórico '+title,pts,past,.024);visible(c,a,b);reveal(c,a,.95)
        if idx>=2:
            for j,p in enumerate(pts):
                o=sphere('Mês de entrada %d %d'%(idx,j),p,.075,mats['silver']);visible(o,a,b);grow(o,a+j*.035,.3)
        fn=72 if idx==0 else 30 if idx==1 else 1 if idx==2 else 6
        fvalues=wave(max(2,fn),fc) if idx==0 else [(.48+.22*math.sin((i/max(1,fn-1)*fc+.1)*2*math.pi)) for i in range(max(2,fn))]
        if fn==1:
            p=(3,0,1.7+fvalues[0]*2.4)
            o=box('Saída do próximo mês',p,(.18,.25,.18),mats['cyan'],.04);visible(o,a+2.2,b);grow(o,a+2.2,.65)
        else:
            # Visible dashed future curve, with a point for every month in the six-step task.
            points=[(1.8+i*4.1/(max(2,fn)-1),0,1.7+v*2.4) for i,v in enumerate(fvalues)]
            for j in range(0,len(points)-1,2):
                c=polyline('Previsão tracejada %d %d'%(idx,j),points[j:j+2],cyan,.027);visible(c,a+2.2,b);reveal(c,a+2.2,.7)
            if idx==3:
                for j,p in enumerate(points):
                    o=box('Mês previsto %d'%j,p,(.16,.25,.16),mats['cyan'],.035);visible(o,a+2.2+j*.18,b);grow(o,a+2.2+j*.18,.4)
        if idx==3:label('Caráter exploratório','Exploratória · rede própria',(0,0,5.65),.32,white,a+.6,b)
    return {'duration':DURATION,'qa_times':[3.5,6.8,12,20,28,34,39,44,50,55,61,67.5],
            'cues':CUES,'source_report_pages':[11,12,18,19,20,21],
            'illustrative_values':True,'tasks':{'hourly':[336,72],'daily':[365,30],'monthly1':[12,1],'monthly6':[12,6]},
            'monthly_networks_trained_separately':True,'input_scope':['GHI history','locality ID'],
            'input_output_windows_have_independent_horizontal_scales':True}
