"""V9: a named factory's actual readings become a model input window."""
import json
import math
import bpy
from common_v7 import *
from inputs_tasks_v7 import wave, curved
from geography_data_v7 import _factory_symbol, CITY_LABELS, DATA

DURATION=64
CUES=[
 (0,6,'Usamos leituras anteriores da região da fábrica. Este trecho real é de Camaçari.'),
 (6,12,'Esses valores mantêm a ordem no tempo e formam parte da janela de entrada.'),
 (12,20,'A rede também identifica a região e aprende uma representação para cada localidade.'),
 (20,28,'Assim, entram duas informações: os valores anteriores de GHI e a região à qual pertencem.'),
 (28,34,'Em cada tarefa, uma mesma rede compartilha parâmetros entre as dez localidades.'),
 (34,38,'São quatro tarefas de previsão, com janelas e horizontes diferentes.'),
 (38,42,'Na horária, entram duas semanas de histórico.'),
 (42,46,'Prevemos os próximos três dias de irradiância.'),
 (46,50,'Na diária, entra um ano de histórico.'),
 (50,54,'A previsão contém os próximos trinta dias.'),
 (54,59,'Na primeira mensal, entram doze meses e prevemos o seguinte.'),
 (59,64,'A outra rede prevê seis meses. É uma análise exploratória.'),
]

def time_map(t):
    anchors=[(0,0),(32,34),(36,38),(47,46),(58,54),(64,59),(70,64)]
    for (a,c),(b,d) in zip(anchors,anchors[1:]):
        if t<=b:return c+(t-a)/(b-a)*(d-c)
    return 64+(t-70)

def all_fcurves(action):
    """Visit every Blender4.5 action slot, plus legacy curves, exactly once."""
    seen=set()
    for layer in getattr(action,'layers',[]):
        for strip in layer.strips:
            for bag in getattr(strip,'channelbags',[]):
                for curve in bag.fcurves:
                    token=curve.as_pointer()
                    if token not in seen:
                        seen.add(token);yield curve
    for curve in getattr(action,'fcurves',[]):
        token=curve.as_pointer()
        if token not in seen:
            seen.add(token);yield curve

def retime_action(action):
    for curve in all_fcurves(action):
        for key in curve.keyframe_points:
            co,left,right=key.co.copy(),key.handle_left.copy(),key.handle_right.copy()
            key.co=(1+30*time_map((co.x-1)/30),co.y)
            key.handle_left=(1+30*time_map((left.x-1)/30),left.y)
            key.handle_right=(1+30*time_map((right.x-1)/30),right.y)
        curve.update()

def show(obj,a,b):visible(obj,a,b);return obj

def build(scene):
    mats={k:surface('V9 inputs '+k,v,metallic=.12,roughness=.40) for k,v in [('cyan',CYAN),('coral',CORAL),('violet',VIOLET),('gold',GOLD),('silver',(.52,.61,.66,1))]}
    white=emission('V9 inputs text',WHITE,.9)
    ink=emission('V9 inputs axes',(.38,.46,.50,1),.8)
    cyan=emission('V9 inputs flow',(.25,.78,.85,1),.9)
    past=emission('V9 inputs actual values',(.80,.88,.91,1),.9)
    gold=emission('V9 locality information',(.91,.68,.28,1),.8)
    fac={'wall':surface('V9 factory ivory',(.66,.71,.68,1),.02,.70),
         'metal':surface('V9 factory roof',(.49,.61,.65,1),.2,.50),
         'glass':surface('V9 factory glazing',(.15,.35,.42,1),.13,.30),
         'frame':surface('V9 factory charcoal',(.055,.10,.12,1),.15,.50)}
    data=json.loads(DATA.read_text(encoding='utf-8'))
    real=data['localities'][0]['series_example']['values_w_m2']
    vals=real[5:11]
    assert vals==[19.,193.,439.,673.5,867.,1001.]
    _factory_symbol('V9 actual region source',(-5.5,0,3.4),2.0,fac,0,12)
    label('V9 source city','Camaçari',(-5.5,-.2,2.6),.45,white,0,12)
    label('V9 window headline','Uma janela reúne as leituras anteriores',(0,0,6.5),.51,white,0,12)
    label('V9 source window','Trecho real da NSRDB · 1 jan. 2019',(1.2,0,5.75),.29,white,0,12)
    points=[]
    for i,v in enumerate(vals):
        x=-2.8+i*1.65;z=2.5+v/1000*2.2
        points.append((x,0,z))
        o=show(box('V9 reading amplitude '+str(i),(x,0,2.5+v/1000*1.1),(.28,.34,max(.02,v/1000*2.2)),mats['cyan'],.02),.4+i*.35,12)
        grow(o,.4+i*.35,.5)
        label('V9 reading time '+str(i),f'{5+i:02d}h',(x,-.15,1.9),.30,white,.4+i*.35,12)
        txt=f'{v:g}'.replace('.',',')
        label('V9 reading value '+str(i),txt,(x,-.2,z+.42),.35,white,1+i*.35,12)
    line=polyline('V9 actual recent window',points,past,.02);show(line,2.6,12);reveal(line,2.6,1.8)
    label('V9 values units','GHI em W/m²',(1.2,0,.95),.31,white,0,12)
    label('V9 order meaning','Mais antigo  →  mais recente',(1.2,0,1.36),.27,white,6,12)
    # The same visible place has a model-internal identity; never a mystery ID box.
    for idx,(name,a,b) in enumerate([('Camaçari',12,16),('Nevada',16,20)]):
        _factory_symbol('V9 named factory '+name,(-4.8,0,3.1),2.1,fac,a,b)
        label('V9 named local '+name,name,(-4.8,0,5.6),.53,white,a,b)
        label('V9 region condition '+name,'Identificação da região',(-4.8,0,2.2),.29,white,a,b)
        arrow('V9 region lookup '+name,(-3.2,0,3.5),(-1.2,0,3.5),gold,a+.25,b)
        for j in range(8):
            h=.42+.2*((j*7+3+idx*2)%6)
            token=show(box('V9 learned schematic '+name+str(j),(.1+j*.61,0,3.5),(.35,.45,h),mats['gold'],.06),a+.6+j*.08,b)
            grow(token,a+.6+j*.08,.45)
        label('V9 representation title '+name,'Representação da região',(2.3,0,5.6),.43,white,a,b)
        label('V9 representation meaning '+name,'Aprendida durante o treinamento',(2.3,0,2.2),.28,white,a,b)
    # A fixed model receives the two inputs; localities take turns without refitting.
    for layer in range(3):
        for j in range(4):
            show(sphere('V9 shared parameter '+str(layer)+' '+str(j),(1.1+layer*.9,.25,2.2+j*.62),.15,mats['silver']),20,34)
            if layer<2:
                for k in range(4):
                    show(polyline('V9 shared model link '+str((layer,j,k)),[(1.1+layer*.9,.25,2.2+j*.62),(2+layer*.9,.25,2.2+k*.62)],ink,.006),20,34)
    label('V9 shared model heading','Rede compartilhada',(2,0,5.7),.48,white,20,34)
    pts=[(-6.2+i*.22,0,4.3+v/1000*.7) for i,v in enumerate(real[5:21])]
    flow=show(polyline('V9 history input channel',pts,past,.023),20,28);reveal(flow,20,.8)
    label('V9 history channel heading','Valores anteriores de GHI',(-4.6,0,5.7),.36,white,20,28)
    curved('V9 historic values into model',(-2.6,0,4.4),(.8,0,3.9),cyan,20.6,28,.35)
    _factory_symbol('V9 factory input channel',(-4.6,0,1.9),1.25,fac,20,28)
    label('V9 factory channel city','Camaçari',(-4.6,-.2,1.45),.32,white,20,28)
    curved('V9 place into model',(-3.5,0,2.1),(.8,0,2.7),gold,21,28,-.2)
    arrow('V9 forecast output',(3.4,0,3.1),(4.5,0,3.1),cyan,21.5,34)
    future=[(4.9+i*.24,0,2.7+v*.9) for i,v in enumerate(wave(10,1.3))]
    for j in range(0,len(future)-1,2):
        show(polyline('V9 dashed forecast output '+str(j),future[j:j+2],cyan,.025),22,34)
    label('V9 forecast output label','Previsão de GHI',(5.7,0,5.7),.39,white,22,34)
    for i in range(10):
        row=1.15+(i%5)*.91;col=-6.3+(i//5)*2.45
        _factory_symbol('V9 shared city '+str(i+1),(col,0,row),.77,fac,28,34)
        label('V9 shared city name '+str(i+1),CITY_LABELS[i+1],(col,-.18,row-.24),.23,white,28,34)
        t=28+i*.5
        curved('V9 city stream '+str(i),(col+.48,.1,row+.25),(.7,.1,3.1),gold,t,min(34,t+.8),.2)
    label('V9 shared city group','Dez localidades',(-5.1,0,6.1),.42,white,28,34)
    task_objects_before=set(bpy.data.objects)
    task_actions_before=set(bpy.data.actions)
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
    # Only the reused task actions are warped; first34seconds stay untouched.
    # Retime each action once, including all its layered action slots.
    task_actions=set(bpy.data.actions)-task_actions_before
    for action in task_actions:
        retime_action(action)
    for obj in set(bpy.data.objects)-task_objects_before:
        if 'visible_start_seconds' in obj:
            obj['visible_start_seconds']=time_map(obj['visible_start_seconds'])
    for t,scale,target in [(0,17,(0,0,3.5)),(11.8,17,(0,0,3.5)),(12,17,(0,0,3.5)),(33.8,17,(0,0,3.5)),(34,17,(0,0,3.3)),(64,16.7,(0,0,3.3))]:
        camera_key(scene,t,(target[0],-28,target[2]+3.2),target,scale)
    return {'duration':64,'qa_times':[5,9,14,17.5,24,31,36,43,51,57,62],'cues':CUES,
        'tasks':{'hourly':[336,72],'daily':[365,30],'monthly1':[12,1],'monthly6':[12,6]},
        'monthly_networks_trained_separately':True,'real_intro_window_values':vals,
        'real_window_source':str(DATA.relative_to(ROOT)),
        'named_localities_replace_ID_boxes':True,
        'embedding_geometry_illustrative_not_actual_weights':True,
        'task_curve_values_illustrative':True,
        'input_output_windows_have_independent_horizontal_scales':True}
