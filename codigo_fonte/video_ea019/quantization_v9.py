"""Numerical, beginner-facing input quantization; all examples are didactic."""
import math
import struct
import bpy
from common_v7 import *

DURATION=64
CUES=[
 (0,8,'Quantizar aproxima cada leitura de um nível disponível. Aqui usamos um exemplo, numa escala de zero a mil.'),
 (8,15,'A leitura original é quatrocentos e trinta e sete. Primeiro, ela é normalizada.'),
 (15,23,'Com sessenta e quatro níveis, escolhemos o degrau mais próximo e reconstruímos aproximadamente quatrocentos e quarenta e quatro.'),
 (23,31,'Com cento e vinte e oito níveis, o mesmo valor vira aproximadamente quatrocentos e trinta e três.'),
 (31,37,'Com duzentos e cinquenta e seis, fica próximo de quatrocentos e trinta e cinco.'),
 (37,44,'Mais níveis diminuem o espaço entre degraus. O instante da leitura continua o mesmo.'),
 (44,51,'A transformação atua só no GHI de entrada. A localidade segue separada; pesos, alvos e saídas continuam contínuos.'),
 (51,58,'Nas variantes quantizadas, limitamos extremos antes de arredondar. O controle contínuo não faz essas duas operações.'),
 (58,64,'A condição é escolhida na validação e mantida no teste, para cada modelo e tarefa.'),
]

def show(obj,a,b):visible(obj,a,b);return obj
def text(name,body,loc,size,mat,a,b):return label('V9 quant '+name,body,loc,size,mat,a,b)
def trace(name,pts,mat,a,b,r=.021,draw=.65):
    obj=show(polyline('V9 quant '+name,pts,mat,r),a,b)
    if draw:reveal(obj,a,draw)
    return obj
def arc(a,b,lift=.3):
    return [(a[0]+(b[0]-a[0])*u,-.05-.16*math.sin(math.pi*u),a[2]+(b[2]-a[2])*u+lift*math.sin(math.pi*u)) for u in [j/32 for j in range(33)]]
def packet(name,pts,mat,a,b,r=.08):
    obj=show(sphere('V9 quant '+name,pts[0],r,mat),a,b)
    keys(obj,'location',[(a+(b-a)*j/(len(pts)-1),p) for j,p in enumerate(pts)],True)
    return obj
def quant(v,n):
    value=round(max(0,min(1,v))*(n-1))/(n-1)
    return struct.unpack('<f',struct.pack('<f',value))[0]
def fmt(v,places=2):return f'{v:.{places}f}'.replace('.',',')
def factory(name,x,z,mat,glass,a,b,scale=1):
    objects=[box(name+' pavilhão',(x,0,z+.24*scale),(1.05*scale,.50*scale,.48*scale),mat,.04),
             box(name+' cobertura',(x,0,z+.51*scale),(1.15*scale,.59*scale,.08*scale),mat,.025),
             box(name+' fachada',(x,-.27*scale,z+.28*scale),(.72*scale,.04*scale,.15*scale),glass,.012)]
    for obj in objects:show(obj,a,b);grow(obj,a,.4)
    return objects

def build(scene):
    white=emission('V9 quant branco',WHITE,.9)
    muted=emission('V9 quant estrutura',(.30,.40,.46,1),.8)
    gold=emission('V9 quant nível',(.96,.66,.26,1),.9)
    cyan=emission('V9 quant GHI',(.20,.73,.83,1),.9)
    levelmat=surface('V9 quant degrau físico',(.80,.54,.22,1),.08,.43)
    silver=surface('V9 quant parâmetros contínuos',(.57,.68,.72,1),.1,.35)
    blue=surface('V9 quant vidro',(.10,.40,.52,1),.12,.38)
    output=surface('V9 quant saída',(.22,.64,.76,1),.12,.34)
    # A reading remains attached to its sample time, rather than becoming an
    # unexplained moving curve with nearly indistinguishable discretizations.
    text('introdução','Uma leitura, vários níveis possíveis',(0,0,6.45),.53,white,0,15)
    text('escala ilustrativa','Exemplo didático · escala de 0 a 1000 W/m²',(0,-.75,5.74),.34,white,0,44)
    pts=[(-6+i*3,0,2.0+v/250) for i,v in enumerate([170,360,437,620,400])]
    trace('série exemplo',pts,white,0,8,.029,1)
    trace('eixo temporal',[(-6.3,0,1.85),(6.3,0,1.85)],muted,0,8,.013)
    for i,p in enumerate(pts):
        obj=show(sphere('V9 quant leitura '+str(i),p,.08,silver),0,8);grow(obj,.2+i*.15,.4)
    show(sphere('V9 quant leitura selecionada',pts[2],.13,levelmat),1.5,8)
    text('valor selecionado','437 W/m²',(0,0,4.58),.53,gold,2,8)
    text('instante original','Mesmo instante de observação',(0,0,1.15),.35,white,3,8)
    for t in range(5):text('tempo exemplo '+str(t),'t'+str(t+1),(-6+t*3,0,1.45),.26,white,0,8)
    text('leitura em watts','437 W/m²',(-3.8,0,3.9),.76,white,8,15)
    text('normalizado','0,437',(3.8,0,3.9),.76,gold,8,15)
    arrow('V9 quant normalização',(-1.8,0,3.9),(1.8,0,3.9),cyan,8.2,15,.025)
    packet('leitura normalizada',[(-1.8,0,3.9),(1.8,0,3.9)],levelmat,9,10.5,.14)
    text('operação normalizar','(437 − 0) / (1000 − 0)',(0,0,2.48),.48,white,9.3,15)
    text('escala do experimento','No experimento: escala ajustada ao histórico de treino de cada local',(0,0,1.36),.32,white,10.5,15)
    # Uniform lattices are shown as an accurately labelled local zoom. Every
    # rung belongs to the declared N-level grid; the total is never replaced by
    # an arbitrary four-level stand-in.
    records=[]
    for n,a,b in [(64,15,23),(128,23,31),(256,31,37)]:
        q=quant(.437,n);physical=q*1000;error=abs(physical-437);index=round(.437*(n-1))
        records.append({'levels':n,'normalized_original':.437,'nearest_index':index,
                        'normalized_float32':q,'reconstructed_W_m2':physical,'input_absolute_difference_W_m2':error})
        text('título Q'+str(n),str(n)+' níveis disponíveis',(0,0,6.45),.54,white,a,b)
        z=lambda v:1.90+(v-400)/65*3.65
        trace('tempo fixo '+str(n),[(0,0,1.6),(0,0,5.7)],muted,a,b,.011)
        for k in range(n):
            v=1000*k/(n-1)
            if 400<=v<=465:
                trace(f'degrau real {n}-{k}',[(-.95,0,z(v)),(1.0,0,z(v))],muted,a,b,.014,0)
                if n<256 or k%2==0:
                    text(f'valor degrau {n}-{k}',fmt(v,1),(1.58,0,z(v)),.24,white,a,b)
        show(sphere('V9 quant original '+str(n),(0,-.12,z(437)),.10,silver),a,b)
        moving=show(sphere('V9 quant aproximado '+str(n),(0,-.30,z(437)),.13,levelmat),a+.4,b)
        keys(moving,'location',[(a+.4,(0,-.30,z(437))),(a+1.8,(0,-.30,z(physical))),(b,(0,-.30,z(physical)))])
        trace('deslocamento em amplitude '+str(n),[(0,-.22,z(437)),(0,-.22,z(physical))],gold,a+.8,b,.024,.7)
        trace('nível escolhido '+str(n),[(-.95,-.05,z(physical)),(1.0,-.05,z(physical))],gold,a+1.6,b,.025,.4)
        text('original em watts '+str(n),'Original\n437 W/m²',(-4.2,0,4.1),.48,white,a,b)
        text('reconstrução em watts '+str(n),fmt(physical)+' W/m²',(4.20,0,4.55),.57,gold,a+1.6,b)
        text('erro de entrada '+str(n),'Diferença da entrada\n'+fmt(error)+' W/m²',(4.2,0,3.33),.34,white,a+2.2,b)
        text('cálculo do nível '+str(n),f'Índice: arredondar(0,437 × {n-1}) = {index}',(0,0,1.50),.39,white,a+.8,b)
        text('cálculo reconstruir '+str(n),f'{index} / {n-1} × 1000 = '+fmt(physical)+' W/m²',(0,0,1.00),.35,white,a+2.0,b)
    text('comparação título','Mesmo instante · degraus mais próximos',(0,0,6.45),.52,white,37,44)
    text('comparação original','Original: 437 W/m²',(0,0,5.07),.52,white,37,44)
    for i,row in enumerate(records):
        x=-4.7+i*4.7
        show(sphere('V9 quant comparação Q'+str(row['levels']),(x,0,3.75),.28,levelmat),37,44)
        trace('ramo comparação '+str(i),arc((0,0,4.7),(x,0,4.05),.2),cyan,37.3+i*.12,44,.019,.7)
        text('níveis comparação '+str(i),'Q'+str(row['levels']),(x,0,3.05),.44,white,37.2,44)
        text('valor comparação '+str(i),fmt(row['reconstructed_W_m2'])+' W/m²',(x,0,2.35),.48,gold,37.8,44)
        text('diferença comparação '+str(i),'Diferença da entrada\n'+fmt(row['input_absolute_difference_W_m2'])+' W/m²',(x,0,1.55),.30,white,38.2,44)
    # The locality is an identifiable physical object, not an unexplained ID.
    text('escopo','Só o GHI de entrada é quantizado',(0,0,6.45),.52,white,44,51)
    trace('ghi de entrada',[(-6.8,0,4.7),(-6.3,0,4.9),(-5.8,0,4.5),(-5.3,0,4.8),(-4.8,0,4.2)],white,44,51,.025)
    text('nome GHI','GHI',(-5.8,0,5.45),.38,white,44,51)
    for j in range(5):show(box('V9 quant níveis do quantizador',(-2.3,0,3.4+j*.32),(1.25,.55,.08),levelmat,.025),44,51)
    text('quantizador','Quantizar',(-2.3,0,5.38),.37,white,44,51)
    trace('fluxo original',arc((-4.8,0,4.2),(-2.3,0,4.2),.2),muted,44,51)
    trace('fluxo reconstruído',arc((-1.6,0,4.2),(1.5,0,4.1),.2),gold,44,51)
    text('dtype','Reconstrução float32',(.1,0,5.35),.31,white,44.5,51)
    packet('amostra atravessa níveis',arc((-4.8,0,4.2),(1.5,0,4.1),.3),levelmat,44.8,47,.08)
    factory('V9 quant fábrica Camaçari',-5.6,1.7,silver,blue,44,51,1.10)
    text('nome fábrica','Camaçari',(-5.6,0,1.15),.36,white,44,51)
    bypass=arc((-4.8,0,2.0),(1.5,0,3.4),-.28)
    trace('localidade separada',bypass,cyan,44.5,51,.021)
    packet('informação do local',bypass,silver,45.2,47.1,.10)
    text('bypass expl','Identificação do local',(-1.9,0,1.60),.31,white,44.5,51)
    for i in range(3):
        for j in range(3):
            show(sphere(f'V9 quant peso contínuo{i}-{j}',(2+i*.43,0,3.1+j*.43),.11,silver),44.8,51)
            if i<2:trace(f'peso ligação{i}-{j}',[(2+i*.43,0,3.1+j*.43),(2+(i+1)*.43,0,3.1+((j+1)%3)*.43)],muted,44.8,51,.012)
    text('rede contínua','Pesos contínuos',(2.55,0,5.32),.33,white,45,51)
    trace('saídas contínuas',arc((3.3,0,3.6),(4.55,0,3.6),.15),cyan,45.2,51)
    for j,h in enumerate([.5,.9,.75,.35]):show(box('V9 quant previsão contínua'+str(j),(4.8+j*.46,0,3.1+h/2),(.27,.40,h),output,.04),45.4,51)
    text('saídas','Alvos e saídas contínuos',(5.4,0,2.25),.31,white,45.6,51)
    # Clip and round are two operations; control does neither, as in the code.
    text('ordem clipping','Quantizadas: limitar extremos, depois arredondar',(0,0,6.45),.47,white,51,58)
    values=[.5+.69*math.sin(i/240*math.tau*1.1) for i in range(241)]
    pts=[(-6.15+i*12.3/240,0,2.25+2.5*v) for i,v in enumerate(values)]
    trace('controle sem clipping',pts,white,51,58,.026,.5)
    changed=trace('limitar e arredondar',pts,gold,51.4,58,.030,.5)
    for point,p,v in zip(changed.data.splines[0].points,pts,values):
        clipped=(p[0],-.04,2.25+2.5*max(0,min(1,v)))
        rounded=(p[0],-.04,2.25+2.5*quant(v,64))
        for t,co in [(51.6,p),(53.1,clipped),(53.7,clipped),(55.1,rounded),(58,rounded)]:
            point.co=(*co,1);point.keyframe_insert('co',frame=frame(t))
    for v in [0,1]:
        z=2.25+2.5*v;trace('limite '+str(v),[(-6.3,0,z),(6.3,0,z)],muted,51,58,.010,.4)
        text('valor limite '+str(v),str(v),(-6.6,0,z),.30,white,51,58)
    text('controle explícito','Branco: controle contínuo, sem limitar nem arredondar',(0,0,1.30),.34,white,52,58)
    text('seleção título','Escolher na validação, manter no teste',(0,0,6.45),.51,white,58,64)
    for i,name in enumerate(['Contínuo','Q64','Q128','Q256']):
        x=-5.7+i*1.7
        show(box('V9 quant condição '+name,(x,0,4.0),(.8,.6,.7),silver if i==0 else levelmat,.08),58,61.1)
        text('nome condição '+name,name,(x,0,3.22),.31,white,58,61.1)
        trace('condição até seleção '+name,arc((x,0,4.4),(2.2,0,4.4),.18),muted,58.2+i*.13,61.1,.013,.7)
    chosen=show(box('V9 quant condição selecionada',(2.2,0,4.4),(.65,.55,.65),silver,.09),59.6,64)
    keys(chosen,'location',[(59.6,(2.2,0,4.4)),(61,(2.2,0,4.4)),(63.2,(5.5,0,4.4)),(64,(5.5,0,4.4))])
    text('ano validação','Validação 2023',(2.2,0,5.32),.36,white,58,64)
    text('ano teste','Teste 2024',(5.5,0,5.32),.36,white,60.2,64)
    trace('condição congelada',[(2.2,0,4.4),(5.5,0,4.4)],cyan,60.4,64,.023,.8)
    text('por modelo e tarefa','Escolha por modelo e tarefa',(0,0,1.8),.40,white,59,64)
    for t,loc,target,scale in [(0,(.15,-28,7),(0,0,3.6),17.5),(8,(0,-28,7),(0,0,3.6),17.5),
         (15,(0,-28,7),(0,0,3.6),17.5),(37,(.1,-28,7),(0,0,3.6),17.5),
         (44,(-.1,-28,7),(0,0,3.6),17.5),(51,(0,-28,7),(0,0,3.6),17.5),
         (58,(0,-28,7),(0,0,3.6),17.5),(64,(.1,-28,7),(0,0,3.6),17.5)]:camera_key(scene,t,loc,target,scale)
    return {'version':9,'duration':DURATION,'cues':CUES,
            'qa_times':[4,11.5,20.3,27.5,34.5,40.5,48,54.8,62.5],
            'numerical_example_is_didactic':True,'illustrative_scaler_min':0,'illustrative_scaler_max':1000,
            'original_example_W_m2':437,'examples':records,'levels':[64,128,256],
            'formula':'float32(rint(clip(u,0,1)*(N-1))/(N-1))','clipping_precedes_rounding':True,
            'continuous_control_uses_clipping':False,'continuous_control_rounds':False,
            'locality_identifier_bypasses_quantizer':True,'reconstructed_dtype':'float32',
            'quantization_applies_to':'input GHI only','weights_targets_outputs_continuous':True,
            'uniform_quantization_not_integer_network_inference':True,'timestamps_unchanged':True,
            'source_code':'codigo_fonte/experimentos/quantizacao_timesnet.py:43-61'}
