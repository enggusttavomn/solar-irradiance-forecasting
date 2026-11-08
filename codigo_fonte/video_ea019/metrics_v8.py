"""Explain MAE, equal locality weights and cumulative forecast horizons."""
import math
import bpy
from common_v7 import *

DURATION=48
CUES=[
 (0,8,'Para comparar precisão, usamos principalmente o erro absoluto médio, o MAE. Ele mantém a unidade do GHI.'),
 (8,16,'Em cada instante, tomamos a distância entre previsão e referência, sem considerar o sinal.'),
 (16,21,'Neste exemplo, cinco distâncias são reunidas para calcular a média.'),
 (21,27,'A média deste exemplo é vinte e oito watts por metro quadrado.'),
 (27,38,'Primeiro calculamos o erro de cada localidade. Depois, as dez localidades recebem o mesmo peso na macro média.'),
 (38,48,'Nos horizontes cumulativos, entram todos os passos até o limite. Em 72 horas, o erro reúne três dias inteiros.'),
]

def shown(obj,a,b):visible(obj,a,b);return obj
def trace(name,pts,mat,a,b,r=.022,draw=.8):
    o=polyline(name,pts,mat,r);shown(o,a,b);reveal(o,a,draw);return o
def arc(a,b,lift=.5):
    return [(a[0]+(b[0]-a[0])*u, -.10-.16*math.sin(math.pi*u),a[2]+(b[2]-a[2])*u+lift*math.sin(math.pi*u)) for u in [i/32 for i in range(33)]]

def build(scene):
    ref=[0,200,600,300,0];pred=[20,170,650,270,10]
    errors=[abs(a-b) for a,b in zip(ref,pred)];assert sum(errors)/5==28
    white=emission('V8 métrica texto',WHITE,.9);muted=emission('V8 eixos',(.37,.45,.49,1),.8)
    cyan=emission('V8 previsão ciano',(.18,.72,.82,1),.9);orange=emission('V8 distância absoluta',(.98,.63,.30,1),.9)
    solid=surface('V8 barras de erro',GOLD,.15,.34);silver=surface('V8 estatísticas locais',(.52,.65,.70,1),.15,.32)
    refmat=surface('V8 referência física',(.75,.84,.87,1),.15,.3)
    current=surface('V8 passos incluídos',CYAN,.1,.32);future=surface('V8 passos ainda não incluídos',(.18,.24,.28,1),.1,.42)
    label('Nome da métrica','Erro absoluto médio',(0,0,6.4),.58,white,0,27)
    p=lambda i,v:(-6+i*3,0,1.9+v/200)
    trace('Referência cinco instantes',[p(i,v) for i,v in enumerate(ref)],white,0,16,.025,1.3)
    trace('Previsão cinco instantes',[p(i,v) for i,v in enumerate(pred)],cyan,.6,16,.026,1.4)
    trace('Eixo dos instantes',[(-6.3,0,1.8),(6.5,0,1.8)],muted,0,16,.012)
    trace('Eixo de potência',[(-6.3,0,1.8),(-6.3,0,5.45)],muted,0,16,.012)
    label('Unidade da comparação','GHI (W/m²)',(-5.7,0,5.75),.30,white,0,16)
    label('Legenda referência','Referência',(-1.5,0,5.7),.35,white,0,16)
    label('Legenda previsão','Previsão',(1.5,0,5.7),.35,cyan,0,16)
    for i,(r,f,e) in enumerate(zip(ref,pred,errors)):
        shown(sphere('Referência %d'%i,p(i,r),.075,refmat),0,16)
        o=shown(sphere('Previsão %d'%i,p(i,f),.075,current),.6,16);grow(o,.6+i*.10,.4)
        trace('Distância absoluta %d'%i,[p(i,r),p(i,f)],orange,5+i*.35,16,.048,.45)
        label('Instante %d'%i,'t'+str(i+1),(-6+i*3,0,1.3),.27,white,0,16)
    for v in [0,200,400,600]:label('Tick GHI %d'%v,str(v),(-6.8,0,1.9+v/200),.25,white,0,16)
    # The distances become a separate set of physical rods with their values.
    # Their new scale is an arithmetic workbench, not the old irradiance axis.
    for i,e in enumerate(errors):
        x=-4.8+i*2.4;h=e*.055
        rod=shown(box('Distância reunida %d'%i,(x,0,2+h/2),(.68,.65,h),solid,.06),16,27)
        grow(rod,16+i*.15,.65)
        label('Erro absoluto numérico %d'%i,str(e),(x,0,2+h+.42),.43,white,16.7+i*.15,27)
        label('Erro etiqueta %d'%i,'|erro|',(x,0,1.6),.28,white,16,21)
    label('Operação média','MAE = (20 + 30 + 50 + 30 + 10) / 5',(0,0,1.2),.44,white,19,27)
    label('Resultado exemplo','28 W/m²',(0,0,5.75),.68,orange,21,27)
    # Equal-size contributions preserve the equal weighting of all ten sites.
    label('Macro média','Macro-MAE: média dos dez locais',(0,0,6.2),.52,white,27,38)
    for i in range(10):
        x=-6.1+i*1.355
        o=shown(box('Estatística local %d'%i,(x,0,2.5),(.72,.55,.74),silver,.09),27,38);grow(o,27+i*.10,.45)
        label('MAE local %d'%i,'m'+str(i+1),(x,0,3.25),.28,white,27,38)
        label('Peso local %d'%i,'1/10',(x,0,1.77),.28,white,28,38)
        pts=arc((x,0,2.9),(0,0,4.7),.25)
        trace('Contribuição de peso igual %d'%i,pts,cyan,29+i*.22,38,.014,.7)
        particle=shown(sphere('Contribuição local %d'%i,pts[0],.07,current),30+i*.22,32.2+i*.22)
        keys(particle,'location',[(30+i*.22+j*2.2/32,pt) for j,pt in enumerate(pts)],True)
    shown(sphere('Centro da macro média',(0,0,4.7),.28,silver),29,38)
    label('Pesos iguais','Mesmo peso por localidade',(0,0,.95),.39,white,30,38)
    # A cumulative horizon keeps every earlier step in the highlighted region.
    label('Nome do horizonte','Horizonte cumulativo',(0,0,6.3),.58,white,38,48)
    for i in range(72):
        x=-6+i*12/71
        value=max(0,math.sin((i%24)/24*2*math.pi-math.pi/2))
        h=.16+2.45*value
        turn=38.7+i/71*7.2
        inactive=shown(box('Passo futuro %d'%i,(x,0,2+h/2),(.10,.35,h),future,.025),38,turn)
        active=shown(box('Passo incluído %d'%i,(x,0,2+h/2),(.10,.35,h),current,.025),turn,48)
    trace('Eixo dos 72 passos',[(-6.2,0,1.9),(6.2,0,1.9)],muted,38,48,.012)
    cursor=trace('Limite que avança',[(0,0,1.7),(0,0,5.1)],orange,38.7,48,.018,0)
    keys(cursor,'location',[(38.7,(-6,0,0)),(45.9,(6,0,0)),(48,(6,0,0))],True)
    for i,text in [(0,'1'),(23,'24'),(47,'48'),(71,'72')]:
        label('Posição do horizonte '+text,text,(-6+i*12/71,0,1.4),.30,white,38,48)
    label('Unidade do horizonte','Passos horários',(0,0,.85),.34,white,38,48)
    label('Todos os passos','1 até 72 h: todos os passos',(0,0,5.55),.39,white,45.9,48)
    # Subtle orbit for depth; frontal framing is retained for numerical reading.
    for t,loc,target,scale in [(0,(.15,-28,6.8),(0,0,3.5),17.5),(7.8,(.35,-28,6.8),(0,0,3.5),17.2),
        (8,(.3,-28,6.8),(0,0,3.5),17.2),(16,(0,-28,6.8),(0,0,3.5),17.3),
        (27,(0,-28,6.7),(0,0,3.5),17.3),(38,(0,-28,6.7),(0,0,3.5),17.2),(48,(.2,-28,6.7),(0,0,3.5),17.0)]:
        camera_key(scene,t,loc,target,scale)
    return {'duration':48,'cues':CUES,'qa_times':[3,10,18.5,23.5,32,40.5,46.8],
      'example_reference':ref,'example_prediction':pred,'example_absolute_errors':errors,'example_mae':28,
      'numeric_example_is_not_an_experiment_result':True,'macro_equal_locality_weight':.1,
      'cumulative_includes_steps_1_through_H':True,'cumulative_hourly_includes_night':True,
      'source_notes':'fontes_resultados_v8.json','source_report_pages':[15,16,21,23]}
