"""Amplitude quantization, input scope, clipping and validation in native3D.

All traces are explicitly illustrative in metadata. Zoomed rungs are a
subset of the real Q64/Q128/Q256 uniform lattices; no four-level stand-in
is presented as one of those experiments. Clip precedes rounding, and the
reconstructed inputs remain float32, as in quantizacao_timesnet.py.
"""
from __future__ import annotations

import math
import struct
import bpy
from mathutils import Vector
from common_v7 import box, sphere, polyline, surface, emission, visible, reveal, keys, label, camera_key, frame

DURATION = 54
CUES = [
    [0, 9, 'Nos três modelos, comparei entradas contínuas com 64, 128 ou 256 níveis.'],
    [9, 15, 'Quantizar aproxima cada amplitude de um dos níveis disponíveis.'],
    [15, 21, 'Mais níveis reduzem os degraus. Os instantes da série são mantidos.'],
    [21, 27, 'Somente o GHI passa pela transformação; a identificação da localidade segue separada.'],
    [27, 34, 'Os valores são reconstruídos em float32. Pesos, alvos e saídas continuam contínuos.'],
    [34, 38, 'Nas variantes quantizadas, o clipping vem antes do arredondamento.'],
    [38, 41, 'O contraste reúne os dois efeitos.'],
    [41, 45, 'O controle contínuo mantém os valores sem clipping.'],
    [45, 54, 'Para cada modelo e tarefa, a condição escolhida em 2023 segue para o teste de 2024.'],
]


def _show(obj,a,b,pop=0):
    visible(obj,a,b)
    if pop:
        size=tuple(obj.scale);keys(obj,'scale',[(a,(.001,)*3),(a+pop,size)])
    return obj


def _body(name,loc,dims,mat,a,b,pop=.25,bevel=.045):
    return _show(box('V8 '+name,loc,dims,mat,bevel),a,b,pop)


def _text(name,text,loc,mat,a,b,size=.39):
    return label('V8 '+name,text,loc,size,mat,a,b)


def _curve(name,points,mat,a,b,width=.024,draw=.6):
    obj=_show(polyline('V8 '+name,points,mat,width),a,b)
    if draw:reveal(obj,a,draw)
    return obj


def _arc(a,b,lift=.4,depth=.18,count=30):
    a,b=Vector(a),Vector(b);pts=[]
    for i in range(count+1):
        u=i/count;p=a.lerp(b,u);p.z+=lift*math.sin(math.pi*u);p.y-=depth*math.sin(math.pi*u);pts.append(tuple(p))
    return pts


def _packet(name,points,mat,a,b,r=.085):
    obj=_show(sphere('V8 '+name,points[0],r,mat),a,b,.10)
    keys(obj,'location',[(a+(b-a)*i/(len(points)-1),p) for i,p in enumerate(points)],True)
    return obj


def _quant(value,levels):
    clipped=max(0.0,min(1.0,value))
    reconstructed=round(clipped*(levels-1))/(levels-1)
    return struct.unpack('<f',struct.pack('<f',reconstructed))[0]


def _signal(u):
    return .5+.34*math.sin(u*math.tau*1.65)+.09*math.sin(u*math.tau*4.2)


def _overview(m):
    white,ink=m['white'],m['ink']
    _text('quantization overview title','Representação da entrada',(0,0,6.5),white,0,9,.54)
    original=[(-6.1+12.2*i/260,0,2.0+3.1*_signal(i/260)) for i in range(261)]
    _curve('continuous input overview',original,white,0,9,.030,.9)
    _curve('overview time axis',[(-6.35,0,1.8),(6.35,0,1.8)],ink,0,9,.014,.7)
    _text('overview time label','Tempo',(0,-.1,1.35),white,.7,9,.35)
    for level,a,b in [(64,1.1,4.0),(128,4.0,6.4),(256,6.4,9)]:
        quantized=[(-6.1+12.2*i/260,-.05,2.0+3.1*_quant(_signal(i/260),level)) for i in range(261)]
        _curve('uniform levels overview Q'+str(level),quantized,m['accent'],a,b,.024,.5)
        _text('overview Q label'+str(level),'Q'+str(level),(4.9,-.1,5.50),white,a,b,.50)
        _text('overview level count'+str(level),str(level)+' níveis',(4.9,-.1,4.98),white,a,b,.34)
        # Every mark is an actual level, kept at the amplitude axis only.
        for k in range(level):
            z=2.0+3.1*k/(level-1)
            _curve(f'overview real level {level}-{k}',[(-6.30,0,z),(-6.16,0,z)],ink,a,b,.005,0)


def _zoom(m):
    white,ink=m['white'],m['ink']
    _text('zoom title','Zoom nas amplitudes',(0,0,6.55),white,9,21,.53)
    _text('zoom shows subset','Trecho do intervalo normalizado',(-2.5,-.1,5.72),white,9.4,21,.33)
    x=-.15
    z=lambda value:1.75+(value-.46)/.08*3.9
    origin_z=z(.5)
    _curve('zoom fixed sample time',[(x,0,1.47),(x,0,5.82)],ink,9,21,.010,.6)
    _text('time unchanged explicit','Mesmo instante',(x,-.1,1.12),white,10,21,.37)
    point=_show(sphere('V8 same original amplitude',(x,-.18,origin_z),.12,m['white']),9.2,21,.2)
    _text('original amplitude label','Amplitude original',(-3.35,-.1,origin_z),white,9.4,21,.36)
    positions=[]
    for levels,a,b in [(64,9,14),(128,14,17.5),(256,17.5,21)]:
        _text('zoom Q label'+str(levels),'Q'+str(levels),(4.15,-.1,5.62),white,a,b,.54)
        _text('zoom actual level total'+str(levels),str(levels)+' níveis no total',(4.1,-.1,5.02),white,a,b,.32)
        visible_levels=[k/(levels-1) for k in range(levels) if .46<=k/(levels-1)<=.54]
        for i,value in enumerate(visible_levels):
            _curve(f'zoom actual lattice {levels}-{i}',[(-.80,0,z(value)),(1.55,0,z(value))],
                   m['accent_soft'],a,b,.013,0)
        target_z=z(_quant(.5,levels))
        obj=_show(sphere('V8 reconstructed amplitude Q'+str(levels),(x,-.38,origin_z),.14,m['gold']),a+.35,b,.2)
        keys(obj,'location',[(a+.35,(x,-.38,origin_z)),(a+1.3,(x,-.38,target_z)),(b,(x,-.38,target_z))])
        _curve('vertical approximation Q'+str(levels),[(x,-.30,origin_z),(x,-.30,target_z)],
               m['accent'],a+.7,b,.022,.65)
        _text('reconstructed amplitude label'+str(levels),'Amplitude aproximada',(3.5,-.1,target_z),white,a+1.2,b,.34)
        positions.append({'levels':levels,'original':.5,'reconstructed_float32':_quant(.5,levels),
                          'visible_subset_count':len(visible_levels)})
    return positions


def _scope(m):
    white,ink=m['white'],m['ink']
    _text('scope title','A transformação atua na entrada de GHI',(0,0,6.55),white,21,34,.49)
    points=[(-6.8+i*.23,0,4.0+.65*_signal(i/12)) for i in range(13)]
    _curve('GHI into quantizer',points,white,21,34,.028,.8)
    _text('scope GHI label','GHI',(-5.4,-.1,5.42),white,21.2,34,.40)
    for k in range(6):
        _body('quantizer amplitude level '+str(k),(-1.6,0,2.9+k*.36),(1.45,.65,.075),m['gold'],21.5,34,.25,.025)
    _text('input quantizer label','Quantizador',(-1.6,-.1,5.46),white,21.6,34,.39)
    _curve('GHI path before levels',_arc(points[-1],(-2.30,0,4.3),.15,.1),ink,21.7,34,.025,.7)
    _curve('reconstructed input path',_arc((-.8,0,4.0),(2.0,0,3.9),.2,.1),m['accent'],22.3,34,.025,.7)
    _text('reconstruction data type','float32',(.70,-.1,4.85),white,26.6,34,.43)
    for i in range(3):
        route=_arc(points[-1],(-1.6,-.10,3.35+i*.36),.1,.15)
        route+=_arc((-1.6,-.10,3.35+i*.36),(2.0,0,3.9),.15,.1)[1:]
        _packet('GHI reconstructed float sample'+str(i),route,m['gold'],22.6+i*.85,24.3+i*.85,.09)
    _body('locality identifier bypass',(-5.4,0,2.25),(1.28,.30,.50),m['silver'],21.4,34,.25)
    _text('locality bypass ID','ID',(-5.4,-.19,2.25),white,21.4,34,.30)
    _text('locality bypass label','Localidade',(-5.4,-.1,1.56),white,21.7,34,.34)
    bypass=_arc((-4.7,0,2.25),(2.0,0,3.15),-.35,.12)
    _curve('ID bypasses quantizer',bypass,ink,22.5,34,.025,.8)
    _packet('unquantized locality ID',bypass,white,23.0,25.0,.085)
    for i in range(3):
        for j in range(3):
            _show(sphere(f'V8 continuous model weight{i}-{j}',(2.4+i*.40,0,3.18+j*.37),.12,m['silver']),24.0,34,.25)
            if i<2:
                _curve(f'continuous model parameter link{i}-{j}',[(2.4+i*.4,0,3.18+j*.37),(2.8+i*.4,0,3.18+((j+1)%3)*.37)],
                       ink,24,34,.012,.6)
    _text('weights continuous label','Pesos contínuos',(2.85,-.1,5.40),white,27.0,34,.35)
    _curve('continuous output path',_arc((3.45,0,3.55),(4.9,0,3.55),.15,.1),m['cyan'],24.5,34,.027,.6)
    for j,v in enumerate((.32,.70,.55,.24)):
        _body('continuous output value'+str(j),(5.1+j*.43,0,3.0+v/2),(.25,.40,v),m['blue'],25.4+j*.08,34,.25)
    _text('continuous outputs label','Saídas contínuas',(5.7,-.1,2.22),white,27.0,34,.35)


def _clip(m):
    white,ink=m['white'],m['ink']
    values=[.5+.72*math.sin(i/240*math.tau*1.12) for i in range(241)]
    points=[(-6.1+i*12.2/240,0,2.1+3.0*v) for i,v in enumerate(values)]
    clipped=[(-6.1+i*12.2/240,0,2.1+3.0*max(0,min(1,v))) for i,v in enumerate(values)]
    original=_curve('unclipped normalized input',points,white,34,45,.026,.9)
    _text('clip before rounding title','1. Limitar extremos   2. Arredondar',(0,0,6.60),white,34,41,.48)
    for value in (0,1):
        z=2.1+3*value
        _curve('normalized limit '+str(value),[(-6.25,0,z),(6.25,0,z)],ink,34,45,.012,.7)
        _text('normalized limit label '+str(value),str(value),(-6.65,-.1,z),white,34,45,.34)
    transformed=_curve('clipped then rounded variant',points,m['accent'],34.6,41,.031,.6)
    for p,a,b,v in zip(transformed.data.splines[0].points,points,clipped,values):
        p.co=(*a,1);p.keyframe_insert('co',frame=frame(35.0))
        p.co=(*b,1);p.keyframe_insert('co',frame=frame(37.1))
        q=(b[0],-.06,2.1+3.0*_quant(v,64))
        p.co=(*b,1);p.keyframe_insert('co',frame=frame(38.0))
        p.co=(*q,1);p.keyframe_insert('co',frame=frame(39.2))
    _text('combined effects label','Clipping + discretização',(0,-.1,1.35),white,38.0,41,.36)
    _text('continuous control exception','Controle contínuo: sem clipping',(0,0,6.6),white,41,45,.48)
    _text('normalized amplitude axis','Amplitude normalizada',(-5.0,-.1,6.05),white,34.0,45,.33)
    for name,index in [('maximum',max(range(len(values)),key=values.__getitem__)),
                       ('minimum',min(range(len(values)),key=values.__getitem__))]:
        _show(sphere('V8 continuous extreme retained '+name,points[index],.11,m['white']),41.2,45,.2)


def _selection(m):
    white,ink=m['white'],m['ink']
    _text('selection title','Escolha mantida no teste',(0,0,6.55),white,45,54,.52)
    options=[('Contínuo',5.2),('Q64',4.2),('Q128',3.2),('Q256',2.2)]
    for i,(name,z) in enumerate(options):
        _text('selection option '+name,name,(-5.7,-.1,z),white,45,50,.36)
        pts=[(-4.7+j*.20,0,z+.12*math.sin(j*.65)) for j in range(9)]
        _curve('candidate condition '+name,pts,m['accent'] if i else white,45.2,50,.024,.5)
        _curve('candidate to validation '+name,_arc(pts[-1],(-.4,0,3.65),.1,.1),ink,45.8,50,.016,.7)
    _text('validation year label','Validação 2023',(-.4,-.1,5.25),white,45.4,54,.42)
    _text('test year label','Teste 2024',(5.15,-.1,5.25),white,48.0,54,.42)
    # Neutral configuration marker: no particular Q is falsely presented as
    # the winning input condition for every model/task.
    chosen=_body('selected input condition',(-.4,0,3.65),(.68,.48,.68),m['silver'],47.1,54,.3,.12)
    keys(chosen,'location',[(47.1,(-.4,0,3.65)),(49,(-.4,0,3.65)),(52.2,(5.15,0,3.65)),(54,(5.15,0,3.65))])
    _curve('selected condition carried unchanged',[(-.05,0,3.65),(5.15,0,3.65)],m['cyan'],48.5,54,.026,.8)
    _text('selected condition remains fixed','Condição selecionada',(2.45,-.1,2.55),white,49.4,54,.37)


def build(scene):
    before=set(bpy.data.objects)
    m={'white':emission('V8 quant readable white',(.89,.94,.98,1),1),
       'ink':emission('V8 quant subdued structural',(.21,.30,.36,1),.70),
       'accent':emission('V8 quant reconstructed trace',(.90,.64,.24,1),.85),
       'accent_soft':emission('V8 quant local lattice',(.39,.32,.19,1),.55),
       'cyan':emission('V8 quant continuous output trace',(.16,.55,.68,1),.85),
       'gold':surface('V8 quant matte levels',(.82,.54,.19,1),.025,.58),
       'silver':surface('V8 quant continuous parameters',(.44,.56,.64,1),.025,.58),
       'blue':surface('V8 quant continuous output',(.15,.48,.64,1),.025,.58)}
    for t,loc,target,scale in [(0,(.6,-26,7.1),(0,0,3.55),17),
                              (9,(-.5,-26,7.0),(0,0,3.65),17),
                              (21,(.6,-26,7.1),(0,0,3.65),17),
                              (34,(-.5,-26,7.1),(0,0,3.65),17),
                              (45,(.5,-26,7.1),(0,0,3.65),17),
                              (54,(-.5,-26,7.2),(0,0,3.65),17)]:
        camera_key(scene,t,loc,target,scale)
    _overview(m)
    zoom=_zoom(m)
    _scope(m)
    _clip(m)
    _selection(m)
    scene.frame_set(1)
    return {'version':8,'duration':DURATION,'cues':CUES,
            'qa_times':[2.6,5.2,7.6,12.3,16.1,19.4,24.6,30.5,36.5,39.4,43.0,50.8],
            'global_scope_seconds':[286,340],'levels':[64,128,256],
            'quantization_source':'codigo_fonte/experimentos/quantizacao_timesnet.py:43-61',
            'formula':'float32(rint(clip(x,0,1)*(N-1))/(N-1))',
            'rounding_ties':'nearest even','clipping_precedes_rounding':True,
            'quantization_applies_to':'input GHI only','timestamps_unchanged':True,
            'locality_identifier_bypasses_quantizer':True,'weights_targets_and_outputs_continuous':True,
            'reconstructed_dtype':'float32','integer_network_inference_claimed':False,
            'continuous_control_uses_clipping':False,'contrast_combines_clipping_and_rounding':True,
            'zoom_shows_actual_subset_of_declared_lattice':True,'zoom_example':zoom,
            'validation_selection_applied_per_task_and_model':True,
            'no_universal_selected_level_depicted':True,
            'illustrative_curves_not_measured_experimental_predictions':True,
            'object_count':len(set(bpy.data.objects)-before)}
