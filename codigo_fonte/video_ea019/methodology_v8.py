"""Native3D methodology continuation after the approved224second prefix.

The diagrams illustrate the protocol, not measured activations or scores.
The first output in both monthly tasks refers to the same next month;
their independently trained objectives differ.
"""
from __future__ import annotations

import math
import bpy
from mathutils import Vector
from common_v7 import box, sphere, polyline, surface, emission, visible, reveal, keys, label, camera_key, frame

DURATION = 62
CUES = [
    [0, 6, 'As tarefas mensais usam redes distintas: uma prevê um mês e outra, seis.'],
    [6, 12, 'Embora seus primeiros valores se refiram ao mês seguinte, vêm de treinamentos diferentes.'],
    [12, 19, 'Treinei inicialmente com dados de 2019 a 2022.'],
    [19, 26, 'A validação usa 2023, e o teste, 2024.'],
    [26, 32, 'A validação orientou a escolha das configurações. A normalização respeitou os cortes temporais.'],
    [32, 38, 'A escolha foi feita por tarefa e modelo, entre as alternativas do protocolo consolidado.'],
    [38, 49, 'Após a seleção, reiniciei o treinamento em 2019–2023. Depois, avaliei em 2024.'],
    [49, 56, 'Teste retrospectivo: havia exposição anterior a 2024, com independência limitada.'],
    [56, 59, 'Neste estudo, comparamos a precisão das previsões.'],
    [59, 62, 'Velocidade e memória computacional não foram medidas.'],
]


def _show(obj, a, b, pop=0):
    visible(obj, a, b)
    if pop:
        scale = tuple(obj.scale)
        keys(obj, 'scale', [(a, (.001,)*3), (a+pop, scale)])
    return obj


def _body(name, loc, dims, mat, a, b, pop=.3, bevel=.06):
    return _show(box('V8 '+name, loc, dims, mat, bevel), a, b, pop)


def _text(name, text, loc, mat, a, b, size=.39):
    return label('V8 '+name, text, loc, size, mat, a, b)


def _curve(name, points, mat, a, b, radius=.022, draw=.6):
    obj = _show(polyline('V8 '+name, points, mat, radius), a, b)
    if draw:
        reveal(obj, a, draw)
    return obj


def _arc(a, b, lift=.5, depth=.2, count=32):
    a, b = Vector(a), Vector(b)
    result = []
    for i in range(count+1):
        u = i/count
        p = a.lerp(b, u)
        p.z += lift*math.sin(math.pi*u)
        p.y -= depth*math.sin(math.pi*u)
        result.append(tuple(p))
    return result


def _packet(name, points, mat, a, b, radius=.09):
    obj = _show(sphere('V8 '+name, points[0], radius, mat), a, b, .1)
    keys(obj, 'location', [(a+(b-a)*i/(len(points)-1), p) for i,p in enumerate(points)], True)
    return obj


def _network(name, center, mat, wire, a, b, scale=1):
    x,y,z = center
    result=[]
    for layer in range(3):
        for row in range(3):
            p=(x+(layer-1)*.48*scale,y,z+(row-1)*.38*scale)
            result.append(_show(sphere(f'V8 {name} state {layer}-{row}',p,.13*scale,mat),a,b,.3))
            if layer < 2:
                for target in (row, (row+1)%3):
                    q=(x+layer*.48*scale,y,z+(target-1)*.38*scale)
                    result.append(_curve(f'{name} internal{layer}-{row}-{target}',[p,q],wire,a,b,.011*scale,.5))
    return result


def _monthly(m):
    white, ink, cyan = m['white'], m['ink'], m['cyan']
    _text('monthly distinction title','Duas tarefas, redes próprias',(0,0,6.65),white,0,12,.55)
    vals=[.45+.17*math.sin(i*.55) for i in range(12)]
    points=[(-6.8+i*.255,0,3.8+v) for i,v in enumerate(vals)]
    _curve('same twelve months',points,white,0,12,.030,.8)
    for i,p in enumerate(points):
        _show(sphere('V8 shared monthly input'+str(i),p,.075,m['silver']),.15+i*.025,12,.15)
    _text('monthly common input label','Mesmo histórico: 12 meses',(-5.4,-.1,3.05),white,.6,12,.34)
    for title,z,count in [('1 passo',5.0,1),('6 passos',2.55,6)]:
        _network('independently trained monthly '+title,(-.45,0,z),m['silver'],ink,.6,12,1.10)
        _text('monthly task '+title,title,(-.45,-.1,z+.88),white,.6,12,.43)
        route=_arc(points[-1],(-1.2,0,z),.12,.1)
        _curve('monthly input branch '+title,route,ink,.5,12,.025,.7)
        _packet('monthly data '+title,route,white,1.3,2.5,.105)
        _curve('monthly output route '+title,_arc((.45,0,z),(3.35,0,z),.12,.10),cyan,2.3,12,.027,.7)
        for j in range(count):
            # Cubes encode output positions only, not synthetic forecast errors.
            _body(f'{title} future month{j+1}',(3.50+j*.57,0,z),(.27,.45,.28),m['output'],2.8+j*.08,12,.3)
        _text('monthly output size '+title,'1 saída' if count==1 else '6 saídas',(4.65,-.1,z-.70),white,3.0,12,.35)
    # The upper output and lower first output share the exact month column.
    for z in (5.0,2.55):
        ring=[(3.50+.25*math.cos(i*math.tau/44),-.26,z+.27*math.sin(i*math.tau/44)) for i in range(45)]
        _curve('same next-month focus'+str(z),ring,m['accent'],6.0,12,.020,.45)
    _curve('same target month bracket',[(3.16,-.1,5.0),(2.98,-.1,5.0),(2.98,-.1,2.55),(3.16,-.1,2.55)],ink,6.4,12,.013,.6)
    _text('shared monthly target','Mesmo mês seguinte',(5.6,-.2,4.0),white,6.6,12,.34)
    _text('monthly independent objectives','Treinamentos distintos',(-.45,-.1,3.80),white,6.7,12,.34)


def _timeline(scene,m):
    white,ink=m['white'],m['ink']
    timeline=bpy.data.objects.new('V8 continuous protocol timeline',None)
    scene.collection.objects.link(timeline)
    years=list(range(2019,2025))
    xs=[-5.75+i*2.3 for i in range(6)]
    def parent(obj):
        obj.parent=timeline
        return obj
    val_mat=surface('V8 validation year material',(.78,.48,.17,1),.025,.60)
    for i,(year,x) in enumerate(zip(years,xs)):
        mat=m['blue'] if year<2023 else val_mat if year==2023 else m['silver']
        for k in range(4):
            parent(_body(f'{year} chronological data layer{k}',(x,.10*k,3.35+k*.15),(1.50,1.0,.16),mat,
                         12+i*.16,56,.32))
        for k in range(6):
            parent(_body(f'{year} data mark{k}',(x-.57+k*.225,-.425,3.35),(.055,.035,.12),m['silver'],
                         12.3+i*.16,56,.20,.008))
        parent(_text('protocol year '+str(year),str(year),(x,-.15,2.70),white,12+i*.16,56,.46))
    parent(_curve('chronological rail',[(-6.60,0,2.98),(6.65,0,2.98)],ink,12,56,.018,1.2))
    def bracket(name,lo,hi,z,a,b,title,mat):
        parent(_curve(name,[(lo,0,z-.18),(lo,0,z),(hi,0,z),(hi,0,z-.18)],mat,a,b,.020,.7))
        parent(_text(name+' caption',title,((lo+hi)/2,-.12,z+.48),white,a+.25,b,.40))
    bracket('initial training group',-6.55,1.95,4.72,12.5,38,'Treino inicial',m['cyan'])
    bracket('validation group',2.65,4.25,4.72,19.0,38,'Validação',m['accent'])
    bracket('test year group',4.95,6.55,4.72,21.7,56,'Teste',m['white'])
    keys(timeline,'scale',[(12,(1,1,1)),(25.7,(1,1,1)),(27.0,(.70,.70,.70)),
                           (37.7,(.70,.70,.70)),(39.1,(1,1,1)),(56,(1,1,1))])
    keys(timeline,'location',[(12,(0,0,0)),(25.7,(0,0,0)),(27.0,(0,.6,1.90)),
                              (37.7,(0,.6,1.90)),(39.1,(0,0,0)),(56,(0,0,0))])
    _text('validation selection title','Escolha pela validação',(0,-.1,6.75),white,26,38,.52)
    chosen=None
    for j,x in enumerate((-4.5,-1.3,1.9)):
        root=bpy.data.objects.new('V8 candidate configuration '+str(j),None)
        scene.collection.objects.link(root)
        for k in range(4):
            h=.30+.12*((j+k*2)%4)
            obj=_body(f'candidate{j} component{k}',(x+(k-1.5)*.22,0,2.15+h/2),(.15,.42,h),
                      m['silver'] if j!=1 else m['blue'],26.2+j*.15,38 if j==1 else 35.1,.25)
            obj.parent=root
        _text('candidate label'+str(j),'Configuração '+chr(65+j),(x,-.1,1.60),white,26.5+j*.15,34.6,.30)
        route=_arc((x,0,2.6),(2.42,.6,4.40),.25,.15)
        _curve('validation candidate path'+str(j),route,ink,27+j*.40,33.7,.017,.6)
        _packet('candidate assessed on validation'+str(j),route,m['white'],28+j*.65,29.25+j*.65,.10)
        if j==1:
            chosen=root
            keys(root,'location',[(26,(0,0,0)),(33.8,(0,0,0)),(35.0,(3.5,0,.25)),(38,(3.5,0,.25))])
        else:
            keys(root,'scale',[(26,(1,1,1)),(33.8,(1,1,1)),(35.1,(.16,.16,.16)),(38,(.16,.16,.16))])
    _text('selected configuration label','Condição selecionada',(2.2,-.1,1.65),white,35.1,38,.36)
    # The validation year joins the fresh pre-test fit; it is not kept aside.
    node=val_mat.node_tree.nodes.get('Principled BSDF')
    for t,col in [(0,(.78,.48,.17,1)),(38,(.78,.48,.17,1)),(39.2,(.16,.43,.58,1))]:
        node.inputs['Base Color'].default_value=col
        node.inputs['Base Color'].keyframe_insert('default_value',frame=frame(t))
    bracket('fresh training group',-6.55,4.25,4.72,38.5,49,'Novo treino: 2019–2023',m['cyan'])
    _text('refit restart title','Treinamento reiniciado',(0,-.1,6.7),white,38,49,.51)
    model_nodes=_network('freshly fitted network',(-.30,0,1.9),m['blue'],ink,39,49,.88)
    for index,obj in enumerate(model_nodes):
        if obj.type=='MESH':
            keys(obj,'scale',[(39,(.20,)*3),(40.2,(.20,)*3),(42.4,(1,1,1)),
                              (44.0,(.85,.95,1.15)),(46,(1,1,1))])
    for i,x in enumerate(xs[:-1]):
        route=_arc((x,0,3.5),(-.30,0,2.0),.10,.12)
        _packet('fresh fit past data '+str(i),route,m['white'],40.2+i*.34,41.55+i*.34,.095)
    evaluation=_arc((.35,0,1.9),(5.75,0,3.5),.42,.25)
    _curve('trained model reaches evaluation',evaluation,m['cyan'],45.6,49,.025,.7)
    _packet('new fit evaluation',evaluation,m['white'],46.2,47.6,.12)
    _text('retrospective interpretation','Teste retrospectivo',(0,-.1,6.7),white,49,56,.53)
    # A review lens marks earlier knowledge of the test period without a
    # misleading data arrow from2024 into a training block.
    lens_center=(5.75,-.65,4.05)
    ring=[(lens_center[0]+.72*math.cos(i*math.tau/52),lens_center[1],
           lens_center[2]+.72*math.sin(i*math.tau/52)) for i in range(53)]
    _curve('earlier review lens',ring,m['accent'],49.3,56,.055,.7)
    _curve('earlier review lens handle',[(6.24,-.65,3.53),(6.83,-.65,2.91)],m['accent'],49.6,56,.070,.5)
    _text('earlier exposure fact','Exposição anterior a 2024',(-1.8,-.1,5.7),white,49.7,56,.40)
    _text('test independence limitation','Independência limitada',(-1.8,-.1,4.9),white,52.0,56,.36)
    return {'years':years,'training_initial':[2019,2022],'validation':2023,'refit':[2019,2023],
            'test':2024,'configuration_selection_visual':'symbolic candidates without invented validation error scores',
            'fresh_training_restarted':True,'prior_exposure_to_test_explicit':True,
            'prior_exposure_not_drawn_as_training_on_test':True}


def build(scene):
    before=set(bpy.data.objects)
    m={'white':emission('V8 methodology readable white',(.88,.94,.98,1),1),
       'ink':emission('V8 methodology structural ink',(.20,.29,.35,1),.75),
       'cyan':emission('V8 methodology timeline cyan',(.15,.57,.68,1),.9),
       'accent':emission('V8 methodology selected condition',(.82,.59,.27,1),.85),
       'silver':surface('V8 methodology matte silver',(.48,.58,.65,1),.025,.58),
       'blue':surface('V8 methodology matte blue',(.16,.43,.58,1),.025,.58),
       'output':surface('V8 methodology future position',(.22,.62,.48,1),.025,.58)}
    for t,loc,target,scale in [(0,(.8,-26,7.2),(0,0,3.65),17),
                              (12,(-.6,-26,7.1),(0,0,3.65),17),
                              (26,(.7,-26,7.1),(0,0,3.7),17),
                              (38,(-.6,-26,7.15),(0,0,3.7),17),
                              (49,(.6,-26,7.0),(0,0,3.7),17),
                              (56,(0,-26,7.1),(0,0,3.65),17),
                              (62,(-.7,-26,7.2),(0,0,3.65),17)]:
        camera_key(scene,t,loc,target,scale)
    _monthly(m)
    protocol=_timeline(scene,m)
    # A generic paired-curve illustration bridges to evaluation scope; no
    # values or paths claim to be forecasts extracted from an experiment.
    reference=[];prediction=[]
    for i in range(121):
        u=i/120;x=-6.1+12.2*u
        reference.append((x,0,3.45+.75*math.sin(u*math.tau*2)))
        prediction.append((x,0,3.45+.67*math.sin(u*math.tau*2+.18)))
    _curve('precision reference illustration',reference,m['white'],56,62,.028,.9)
    _curve('precision prediction illustration',prediction,m['cyan'],56.5,62,.029,.9)
    _text('comparison scope precision','Comparação de precisão',(0,-.1,6.3),m['white'],56,62,.54)
    _text('no speed or memory measurement','Velocidade e memória computacional não medidas',(0,-.1,1.8),m['white'],59,62,.37)
    scene.frame_set(1)
    return {'version':8,'duration':DURATION,'cues':CUES,
            'qa_times':[3,8.5,16,23,29,35.5,41.8,47.5,52.5,59.5],
            'global_scope_seconds':[224,286],'monthly_first_outputs_same_target_month':True,
            'monthly_training_objectives_distinct':[1,6],'separate_monthly_networks':True,
            'comparison_variable':'predictive precision','speed_measured':False,'memory_measured':False,
            'protocol':protocol,'source_report_pages':[11,12,13,15,29],
            'source_audit':'documentacao/relatorio_final_ea019/video/completo_v8/fontes_resultados_v8.json',
            'illustrative_geometry_not_measured_forecasts':True,
            'object_count':len(set(bpy.data.objects)-before)}
