"""MAE as vertical distances, arithmetic mean, and improvement toward zero."""
import math
import bpy
from common_v7 import *
from retime_v9 import all_fcurves

DURATION=66
CUES=[
 (0,9,'MAE é o erro absoluto médio: o tamanho médio da diferença entre previsão e referência, na mesma hora.'),
 (9,18,'Aqui, a referência é seiscentos e a previsão, seiscentos e cinquenta. A distância é cinquenta, sem considerar o sinal.'),
 (18,28,'Reunimos as cinco diferenças e dividimos por cinco. Neste exemplo, o MAE vale vinte e oito watts por metro quadrado.'),
 (28,36,'Quando a previsão se aproxima da referência, as distâncias encolhem e o MAE diminui.'),
 (36,42,'Se todos os valores coincidem, o MAE é zero. Na mesma tarefa, menor é melhor.'),
 (42,54,'Calculamos o MAE de cada localidade e fazemos outra média. As dez localidades recebem o mesmo peso: um décimo cada.'),
 (54,66,'Na avaliação cumulativa, entram todos os passos até o limite, incluindo a noite. Setenta e duas horas correspondem a três dias.'),
]

def show(obj,a,b):visible(obj,a,b);return obj
def text(name,body,loc,size,mat,a,b):
    # Diagrams use front-facing annotations; keep them clear of coplanar
    # curves/mesh depth and preserve the reserved subtitle area.
    return label('V9 MAE '+name,body,(loc[0],loc[1]-.8,loc[2]),size,mat,a,b)
def trace(name,pts,mat,a,b,r=.023,draw=.65):
    obj=show(polyline('V9 MAE '+name,pts,mat,r),a,b)
    if draw:reveal(obj,a,draw)
    return obj
def arc(a,b,lift=.3):
    return [(a[0]+(b[0]-a[0])*u,-.1-.16*math.sin(math.pi*u),a[2]+(b[2]-a[2])*u+lift*math.sin(math.pi*u)) for u in [j/32 for j in range(33)]]
def key_point(point,values):
    for t,co in values:point.co=(*co,1);point.keyframe_insert('co',frame=frame(t))
    data=point.id_data
    if data.animation_data and data.animation_data.action:
        for curve in all_fcurves(data.animation_data.action):
            if '.points[' in curve.data_path and curve.data_path.endswith('.co'):
                for key in curve.keyframe_points:key.interpolation='LINEAR'
def factory(name,x,z,mat,glass,a,b):
    for obj in [box(name+' pavilhão',(x,0,z+.22),(1.1,.50,.44),mat,.035),
                box(name+' cobertura',(x,0,z+.47),(1.20,.58,.08),mat,.023),
                box(name+' janelas',(x,-.27,z+.28),(.74,.04,.14),glass,.01)]:
        show(obj,a,b);grow(obj,a,.45)

def build(scene):
    ref=[0,200,600,300,0];pred=[20,170,650,270,10]
    errors=[abs(a-b) for a,b in zip(ref,pred)];assert sum(errors)/5==28
    white=emission('V9 MAE referência',WHITE,.9)
    muted=emission('V9 MAE estrutura',(.34,.43,.48,1),.8)
    cyan=emission('V9 MAE previsão',(.19,.72,.83,1),.9)
    gold=emission('V9 MAE distância',(.98,.64,.28,1),.9)
    solid=surface('V9 MAE distâncias físicas',(.83,.56,.21,1),.10,.36)
    silver=surface('V9 MAE marcadores reais',(.62,.74,.78,1),.10,.33)
    blue=surface('V9 MAE marcadores previstos',(.17,.57,.71,1),.11,.33)
    glass=surface('V9 MAE fachada',(.10,.37,.48,1),.1,.37)
    included=surface('V9 MAE passos incluídos',(.17,.59,.71,1),.10,.36)
    inactive=surface('V9 MAE passos por incluir',(.15,.22,.27,1),.08,.43)
    p=lambda i,v:(-6+i*3,0,1.9+v/200)
    # First demonstrate the correct geometric distance: a vertical segment at
    # a shared time. Neither an area integral nor a Euclidean curve distance.
    text('título','Erro absoluto médio: medir a diferença',(0,0,6.45),.53,white,0,9)
    text('exemplo inicial','Exemplo didático · mesmas horas',(0,0,5.8),.32,white,0,9)
    trace('curva referência',[p(i,v) for i,v in enumerate(ref)],white,0,9,.027,1.1)
    trace('curva previsão',[p(i,v) for i,v in enumerate(pred)],cyan,.5,9,.024,1.1)
    for i,(r,f,e) in enumerate(zip(ref,pred,errors)):
        show(sphere('V9 MAE referência inicial '+str(i),p(i,r),.075,silver),0,9)
        show(sphere('V9 MAE previsão inicial '+str(i),p(i,f),.060,blue),.5,9)
        trace('segmento vertical inicial '+str(i),[p(i,r),p(i,f)],gold,2+i*.5,9,.044,.4)
        text('tempo inicial '+str(i),'t'+str(i+1),(-6+i*3,0,1.35),.28,white,0,9)
    trace('eixo tempo inicial',[(-6.35,0,1.8),(6.4,0,1.8)],muted,0,9,.012)
    trace('eixo GHI inicial',[(-6.35,0,1.8),(-6.35,0,5.48)],muted,0,9,.012)
    for v in [0,200,400,600]:text('tick inicial '+str(v),str(v),(-6.78,0,1.9+v/200),.25,white,0,9)
    text('unidade inicial','GHI (W/m²)',(-5.7,0,5.68),.28,white,0,9)
    text('legenda referência','Referência',(-1.45,0,5.38),.34,white,0,9)
    text('legenda previsão','Previsão',(1.45,0,5.38),.34,cyan,0,9)
    # The close-up keeps the exact vertical separation from the original axes.
    # A narrow view is deliberately used to make a 50 W/m² gap readable.
    text('zoom título','Mesma hora: t3',(0,0,6.36),.25,white,9,18)
    text('zoom fórmula','|650 − 600| = 50 W/m²',(0,0,5.92),.27,gold,10.5,18)
    for value,mat,caption,x in [(600,white,'Referência 600',-1.2),(650,cyan,'Previsão 650',1.2)]:
        z=p(2,value)[2]
        show(sphere('V9 MAE zoom '+caption,(0,-.04,z),.046,silver if value==600 else blue),9,18)
        trace('guia zoom '+caption,[(min(0,x),0,z),(max(0,x),0,z)],mat,9.4,18,.010,.4)
        text('número zoom '+caption,caption,(x,0,z-.21 if value==600 else z+.21),.19,mat,9.5,18)
    trace('distância vertical ampliada',[p(2,600),p(2,650)],gold,9.3,18,.018,.55)
    for value in [600,650]:
        z=p(2,value)[2]
        trace('limite distância '+str(value),[(-.10,-.04,z),(.10,-.04,z)],gold,9.5,18,.012,.3)
    text('módulo','Distância positiva, sem sinal',(0,0,4.35),.20,white,11.5,18)
    # The five extracted distances expand into a labelled arithmetic workbench.
    text('média título','Somar as distâncias e dividir por cinco',(0,0,6.45),.52,white,18,28)
    text('escala barras','Mesmas diferenças · escala ampliada para o cálculo',(0,0,5.75),.32,white,18,24)
    for i,e in enumerate(errors):
        x=-4.8+i*2.4;old=p(i,min(ref[i],pred[i]));initial_h=e/200;h=e*.045
        rod=show(box('V9 MAE distância extraída '+str(i),(old[0],0,old[2]+initial_h/2),(.30,.36,initial_h),solid,.025),18,28)
        keys(rod,'location',[(18,(old[0],0,old[2]+initial_h/2)),(20,(x,0,2+h/2)),(28,(x,0,2+h/2))])
        keys(rod,'scale',[(18,(1,1,1)),(20,(2.2,1.6,9)),(28,(2.2,1.6,9))])
        text('valor erro '+str(i),str(e),(x,0,2+h+.42),.48,white,20.2,28)
    text('operação média','MAE = (20 + 30 + 50 + 30 + 10) / 5',(0,0,1.25),.46,white,21,28)
    text('resultado média','28 W/m²',(0,0,5.48),.69,gold,24,28)
    # Same reference, progressively better forecast. Exact numerical labels
    # appear on plateaus only; no stale numeric MAE is shown during transitions.
    text('melhor título','Menor MAE = previsão mais próxima',(0,0,6.45),.54,white,28,42)
    text('comparabilidade','Comparando a mesma tarefa e a mesma referência',(0,0,5.76),.32,white,28,42)
    trace('referência melhoria',[p(i,v) for i,v in enumerate(ref)],white,28,42,.027,.8)
    changing=trace('previsão melhoria',[p(i,v) for i,v in enumerate(pred)],cyan,28,42,.023,.8)
    for point,i in zip(changing.data.splines[0].points,range(5)):
        mid=(pred[i]+ref[i])/2
        key_point(point,[(28,p(i,pred[i])),(30,p(i,pred[i])),(33,p(i,mid)),(34,p(i,mid)),(37,p(i,ref[i])),(42,p(i,ref[i]))])
    for i,(r,f,e) in enumerate(zip(ref,pred,errors)):
        show(sphere('V9 MAE referência melhoria '+str(i),p(i,r),.062,silver),28,42)
        sphere_pred=show(sphere('V9 MAE previsão melhoria '+str(i),p(i,f),.042,blue),28,42)
        mid=(f+r)/2
        keys(sphere_pred,'location',[(28,p(i,f)),(30,p(i,f)),(33,p(i,mid)),(34,p(i,mid)),(37,p(i,r)),(42,p(i,r))],True)
        segment=trace('erro encolhe '+str(i),[p(i,r),p(i,f)],gold,28,37,.032,.2)
        key_point(segment.data.splines[0].points[1],[(28,p(i,f)),(30,p(i,f)),(33,p(i,mid)),(34,p(i,mid)),(37,p(i,r))])
    trace('eixo melhoria',[(-6.35,0,1.8),(6.4,0,1.8)],muted,28,42,.012)
    for a,b,value in [(28,30,'28'),(33,34,'14'),(37,42,'0')]:
        text('MAE melhor '+value,'MAE = '+value+' W/m²',(0,0,1.12),.56,gold,a,b)
    text('menor erro em movimento','Distâncias menores → erro médio menor',(0,0,1.12),.40,white,30,33)
    text('erro rumo a zero','As curvas se aproximam',(0,0,1.12),.43,white,34,37)
    text('zero perfeito','Coincidência em todos os pontos',(0,0,5.2),.36,cyan,37,42)
    # Each site is recognisable and named. Equal marker size and explicit1/10
    # encode equal weighting; no fictional per-site error values are invented.
    text('macro título','Macro-MAE: cada localidade pesa 1/10',(0,0,6.45),.52,white,42,54)
    names=['Camaçari','Nevada','Texas','Geórgia','Normal','Fremont','Casa Grande','Detroit','Dearborn','San Luis Potosí']
    for i,name in enumerate(names):
        x=-5.8+(i%5)*2.9;z=3.45 if i<5 else 1.55
        factory('V9 MAE fábrica '+name,x,z,silver,glass,42+i*.04,54)
        text('cidade '+name,name,(x,0,z-.33),.29,white,42.3+i*.04,54)
        text('peso '+name,'1/10',(x+.84,0,z+.28),.26,gold,42.7+i*.04,54)
        pts=arc((x,0,z+.55),(0,0,5.10),.15)
        if name=='Detroit':
            # Route the lower central contribution through the gap, rather
            # than drawing a vertical line through the Texas factory/name.
            pts=[(p[0]+1.50*math.sin(math.pi*j/32),p[1],p[2]) for j,p in enumerate(pts)]
        trace('contribuição '+name,pts,muted,44+i*.15,54,.012,.7)
        contribution=show(sphere('V9 MAE peso igual '+name,pts[0],.06,blue),45+i*.18,47+i*.18)
        keys(contribution,'location',[(45+i*.18+j*2/32,p) for j,p in enumerate(pts)],True)
    show(sphere('V9 MAE média das localidades',(0,0,5.10),.23,silver),44,54)
    text('média de MAEs','Média dos dez MAEs locais',(0,0,5.75),.32,white,44,54)
    # Cumulative evaluation includes all earlier steps, not only hour72.
    text('cumulativo título','Cumulativo: todos os passos até o limite',(0,0,6.45),.52,white,54,66)
    for i in range(72):
        x=-6+i*12/71;h=.08+2.5*max(0,math.sin((i%24)/24*math.tau-math.pi/2))
        turn=54.7+i/71*7.2
        show(box('V9 MAE passo ainda fora '+str(i),(x,0,2.1+h/2),(.10,.35,h),inactive,.018),54,turn)
        show(box('V9 MAE passo incluído '+str(i),(x,0,2.1+h/2),(.10,.35,h),included,.018),turn,66)
    trace('eixo passos',[(-6.25,0,2),(6.25,0,2)],muted,54,66,.012)
    cursor=trace('limite de avaliação',[(0,0,1.8),(0,0,5.15)],gold,54.7,66,.018,0)
    keys(cursor,'location',[(54.7,(-6,0,0)),(61.9,(6,0,0)),(66,(6,0,0))],True)
    for i,body in [(0,'1'),(23,'24'),(47,'48'),(71,'72')]:text('passo '+body,body,(-6+i*12/71,0,1.45),.31,white,54,66)
    text('unidade passos','Passos horários',(0,0,.95),.33,white,54,66)
    text('inclui noite','Inclui também as horas da noite',(0,0,5.58),.37,white,59,66)
    text('três dias','72 horas = três dias inteiros',(0,0,4.98),.36,white,62,66)
    for t,loc,target,scale in [(0,(.1,-28,6.8),(0,0,3.6),17.5),(8.4,(.1,-28,6.8),(0,0,3.6),17.5),
        (9,(.05,-28,7.2),(0,0,5.15),5.8),(18,(.05,-28,6.8),(0,0,3.6),17.5),
        (28,(.05,-28,6.8),(0,0,3.6),17.5),(42,(0,-28,6.8),(0,0,3.6),17.5),
        (54,(0,-28,6.8),(0,0,3.6),17.5),(66,(.1,-28,6.8),(0,0,3.6),17.5)]:camera_key(scene,t,loc,target,scale)
    # Hold the numerical close-up, then return smoothly to the full workbench.
    camera_key(scene,17.4,(.05,-28,7.2),(0,0,5.15),5.8)
    return {'version':9,'duration':DURATION,'cues':CUES,'qa_times':[5.8,13,22.5,25.5,29,33.5,39.5,49.5,64.5],
        'example_reference':ref,'example_prediction':pred,'example_absolute_errors':errors,'example_mae':28,
        'numeric_example_is_not_an_experiment_result':True,'distance_is_vertical_at_same_time':True,
        'zoom_reference_W_m2':600,'zoom_prediction_W_m2':650,'zoom_absolute_error_W_m2':50,
        'improvement_example_mae_plateaus':[28,14,0],'mae_lower_is_better_for_same_task':True,
        'zero_means_all_example_predictions_match':True,'macro_equal_locality_weight':.1,
        'macro_localities':names,'cumulative_includes_steps_1_through_H':True,'cumulative_includes_night':True,
        'cumulative_bars_are_didactic_time_step_markers_not_measured_errors':True,
        'source_report_pages':[15,16,21,23]}
