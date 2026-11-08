"""Tres mecanismos encadeados, uma rede por vez, para a montagem EA019 V4.

A geometria e os pesos visuais sao didaticos. Nao sao estados, atencoes ou
previsoes extraidos de um modelo treinado. Ha 12 amostras visiveis para uma
sequencia historica mais longa e quatro componentes esquematicas de saida.
Nenhum texto institucional, cabecalho fixo, plataforma ou piso e criado.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_pilot import box, emission, polyline, reveal, sphere, surface, visible


FPS = 30
COLORS = {
    'white': '#F3F5F7', 'secondary': '#A9B2BE', 'axes': '#626D7A',
    'graphite': '#252D36', 'coral': '#F28779', 'coral_body': '#A85E56',
    'cyan': '#58CADA', 'cyan_body': '#387F8C',
    'violet': '#AA91E8', 'violet_body': '#706093',
}
# The identical, explicitly schematic GHI history is reused by all three nets.
GHI = (.02, .10, .72, 1.0, .60, .05, .01, .18, .76, .68, .36, .02)


def _rgba(hex_color):
    values = [int(hex_color.lstrip('#')[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
                 for v in values) + (1.,)


def _material(name, color, luminous=False):
    rgba = _rgba(color)
    mat = emission(name, rgba, 1.) if luminous else surface(name, rgba, 0, .5)
    mat.diffuse_color = rgba
    mat['design_srgb_hex'] = color
    return mat


def _frame(seconds):
    return round(float(seconds)*FPS)+1


def _keys(obj, path, entries, interpolation='BEZIER'):
    for seconds, value in entries:
        setattr(obj, path, value)
        obj.keyframe_insert(data_path=path, frame=_frame(seconds))
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            if curve.data_path == path:
                for key in curve.keyframe_points:
                    key.interpolation = interpolation
                    key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'


def _shown(obj, start, end, meaning, pop=.25):
    obj['meaning'] = meaning
    visible(obj, start, end)
    if pop:
        scale = tuple(obj.scale)
        _keys(obj, 'scale', [(start, (.001,)*3), (start+pop, scale)])
    return obj


def _line(name, points, material, start, end, meaning, draw=.45, radius=.026):
    obj = _shown(polyline(name, points, material, radius), start, end, meaning, 0)
    if draw:
        reveal(obj, start, draw)
    return obj


def _arc(a, b, height=.5, depth=.4, count=22):
    a, b = Vector(a), Vector(b)
    pts = []
    for i in range(count+1):
        u = i/count
        point = a.lerp(b, u)
        point.z += math.sin(math.pi*u)*height
        point.y -= math.sin(math.pi*u)*depth
        pts.append(tuple(point))
    return pts


def _particle(name, points, mat, start, end, radius=.095):
    obj = _shown(sphere(name, points[0], radius, mat), start, end,
                 'particula didatica de fluxo de representacao', .10)
    _keys(obj, 'location', [(start+(end-start)*i/(len(points)-1), point)
                            for i, point in enumerate(points)], 'LINEAR')
    return obj


def _label(scene, name, text, loc, size, color, start, end):
    # The root's common helper owns the standard font/billboard treatment.
    try:
        from common_v4 import billboard_label
    except ImportError:
        billboard_label = None
    if billboard_label:
        return billboard_label(scene, name, text, loc, size, color, start, end)
    data = bpy.data.curves.new(name, 'FONT')
    data.body, data.align_x, data.align_y = text, 'CENTER', 'CENTER'
    data.size, data.extrude, data.bevel_depth = size, .002, .001
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.exists():
        data.font = bpy.data.fonts.load(str(font))
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    data.materials.append(_material(name+' material', color, True))
    if scene.camera:
        constraint = obj.constraints.new('COPY_ROTATION')
        constraint.target = scene.camera
    return _shown(obj, start, end, 'rotulo curto junto ao mecanismo', 0)


def _camera(scene, shots):
    if scene.camera is None:
        bpy.ops.object.camera_add()
        scene.camera = bpy.context.object
    camera = scene.camera
    camera.name = 'Camera perspectiva dos mecanismos V4'
    camera.animation_data_clear()
    camera.data.animation_data_clear()
    camera.data.type = 'PERSP'
    camera.data.clip_start, camera.data.clip_end = .1, 250
    camera.data.sensor_width = 36
    for shot in shots:
        camera.location = shot['location']
        camera.rotation_euler = (Vector(shot['target'])-camera.location).to_track_quat('-Z','Y').to_euler()
        camera.data.lens = shot['lens']
        camera.keyframe_insert('location', frame=_frame(shot['t']))
        camera.keyframe_insert('rotation_euler', frame=_frame(shot['t']))
        camera.data.keyframe_insert('lens', frame=_frame(shot['t']))
    for owner in (camera, camera.data):
        if owner.animation_data and owner.animation_data.action:
            for curve in owner.animation_data.action.fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = 'BEZIER'
                    key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
                    if any(abs(key.co.x-_frame(shot['t'])) < .1 and shot.get('cut_after')
                           for shot in shots):
                        key.interpolation = 'CONSTANT'
    return camera


def _history(name, start, morph_end, end, destination, white, t):
    original = [(-5.2+i*10.4/11, .05, 2.3+1.85*v) for i,v in enumerate(GHI)]
    curve = _line(name+' curva', original, white, t(start), t(end),
                  'mesma serie GHI historica didatica nas tres arquiteturas', .5, .035)
    for point, a, b in zip(curve.data.splines[0].points, original, destination):
        point.co = (*a, 1)
        point.keyframe_insert('co', frame=_frame(t(start+.6)))
        point.co = (*b, 1)
        point.keyframe_insert('co', frame=_frame(t(morph_end)))
    for i,(a,b) in enumerate(zip(original,destination)):
        dot = _shown(sphere(name+f' amostra {i+1:02d}', a, .09, white),
                     t(start),t(end),'amostra historica de GHI; nao e previsao',.18)
        _keys(dot,'location',[(t(start+.6),a),(t(morph_end),b)])
    return original


def _vector(scene, prefix, position, mat, start, end, t, source=None):
    x,y,z = position
    dims = (.43,.68,1.0)
    heights = (.82,1.2,.96,.62)
    for i,height in enumerate(heights):
        loc = (x+i*.62,y,z+height/2)
        block = _shown(box(prefix+f' componente {i+1}',loc,
                           (dims[0],dims[1],height),mat,.09),
                       t(start),t(end),'componente do vetor futuro direto, sem valor numerico',.4)
        if source is not None:
            _keys(block,'location',[(t(start),source),(t(start+.85),loc)])
    _label(scene,prefix+' rotulo','Vetor futuro',(x+.93,y-.5,z-.45),.29,
           mat['design_srgb_hex'],t(start+.55),t(end))


def build_networks_v4(duration=75):
    """Acrescentar tres redes grandes em 0-24 / 24-50 / 50-75 segundos.

    A reducao do Informer ocorre uma vez entre os dois blocos do encoder,
    conforme a implementacao local. A atencao cruzada conserva todas as
    ligacoes. As portas LSTM e os pesos visuais nao sao valores aprendidos.
    """
    duration = float(duration)
    if duration <= 0:
        raise ValueError('duration deve ser positiva')
    t = lambda seconds: float(seconds)*duration/75.
    scene = bpy.context.scene
    before = {obj.name for obj in bpy.data.objects}
    m = {key:_material('V4 redes '+key,hex_color,key in ('white','secondary','axes'))
         for key,hex_color in COLORS.items()}
    white,soft = m['white'],m['secondary']
    coral,cyan,violet = m['coral'],m['cyan'],m['violet']

    shots = [
        {'t':t(0),'location':(2.4,-17.8,6.6),'target':(0,0,3.0),'lens':43},
        {'t':t(3),'location':(2.0,-16.6,6.0),'target':(0,0,3.0),'lens':44},
        {'t':t(9),'location':(1.1,-15.8,5.5),'target':(-.25,0,3.05),'lens':44},
        {'t':t(16),'location':(-1.0,-16.0,5.8),'target':(.3,0,3.1),'lens':43},
        {'t':t(21),'location':(.8,-16.8,6.1),'target':(.6,0,3.0),'lens':43},
        {'t':t(23.9666667),'location':(.8,-16.8,6.1),'target':(.6,0,3.0),'lens':43,'cut_after':True},
        {'t':t(24),'location':(-2.1,-17.6,6.5),'target':(0,0,3.1),'lens':43},
        {'t':t(28),'location':(-1.5,-17.2,6.3),'target':(0,0,3.3),'lens':43},
        {'t':t(34),'location':(.9,-16.8,6.0),'target':(.1,0,3.5),'lens':43},
        {'t':t(41),'location':(2.0,-17.0,6.2),'target':(.15,0,3.25),'lens':44},
        {'t':t(46),'location':(1.5,-17.5,6.3),'target':(.4,0,3.1),'lens':43},
        {'t':t(49.9666667),'location':(1.5,-17.5,6.3),'target':(.4,0,3.1),'lens':43,'cut_after':True},
        {'t':t(50),'location':(2.2,-17.8,6.5),'target':(0,0,3.2),'lens':43},
        {'t':t(54),'location':(1.2,-17.0,6.0),'target':(0,0,3.65),'lens':43},
        {'t':t(60),'location':(-1.1,-17.2,6.4),'target':(0,0,3.6),'lens':43},
        {'t':t(66),'location':(-1.5,-17.5,6.5),'target':(0,0,3.7),'lens':43},
        {'t':t(71),'location':(.8,-17.8,6.3),'target':(0,0,3.65),'lens':43},
        {'t':t(75),'location':(1.8,-17.0,6.2),'target':(0,0,3.4),'lens':43},
    ]
    camera = _camera(scene,shots)

    # LSTM: a single recurrent cell is revisited; memory is transformed, and
    # the forecast vector is produced together rather than fed back recursively.
    lstm_input = [(-5.45+i*2.15/11,.05,1.85+1.2*v) for i,v in enumerate(GHI)]
    _history('LSTM historico',0,3,24,lstm_input,white,t)
    _label(scene,'Nome LSTM','LSTM',(-4.6,0,5.8),.52,COLORS['coral'],t(.3),t(24))
    _label(scene,'LSTM entrada rotulo','GHI em ordem',(-4.5,-.2,1.34),.28,COLORS['white'],t(3),t(15))
    _shown(box('LSTM corpo da mesma celula',(-.35,.25,3.08),(4.3,1.1,2.7),m['coral_body'],.22),
           t(3),t(24),'uma celula recorrente revisitada no tempo',.7)
    _line('LSTM memoria transportada',[(-2.65,-.55,4.65),(2.0,-.55,4.65)],
          coral,t(3.6),t(19.5),'caminho de estado interno da celula',.7,.075)
    _label(scene,'LSTM memoria rotulo','Memória',(-.35,-.7,5.15),.32,COLORS['coral'],t(4),t(19))
    gate_positions = [(-1.78,-.5,3.1),(-.35,-.5,3.1),(1.08,-.5,3.1)]
    gate_names = ('Esquecer','Atualizar','Ler')
    for j,(pos,label) in enumerate(zip(gate_positions,gate_names)):
        gate = _shown(box('LSTM porta '+label,pos,(.68,.40,1.45),coral,.14),
                      t(4.1+j*.3),t(19.5),'porta aprendida de regulacao de informacao',.35)
        entries=[]
        for i,value in enumerate(GHI):
            second=4.4+i*.84
            scale=.40+.58*((value+.17*j)%1)
            entries.extend([(t(second),(1,1,scale)),(t(second+.34),(1,1,.95)),
                            (t(second+.67),(1,1,scale))])
        _keys(gate,'scale',entries)
        _label(scene,'LSTM rotulo porta '+label,label,(pos[0],-.9,2.05),.27,
               COLORS['white'],t(5.5),t(15.5))
    for i,value in enumerate(GHI):
        start=3.9+i*.83
        points=[lstm_input[i],(-2.75,-.5,2.8),(-1.75,-.9,3.25),
                (-.35,-.9,3.25),(1.0,-.9,3.25),(1.75,-.65,4.65)]
        _particle(f'LSTM amostra processada {i+1:02d}',points,coral,t(start),t(start+1.45),.12)
    for j in range(8):
        memory = _shown(box(f'LSTM componente de memoria {j+1}',
                            (-2.2+j*.53,-.65,4.66),(.29,.34,.34),coral,.06),
                        t(4+j*.13),t(19.6),'componente esquematica do estado, nao copia de amostra',.18)
        values=[(t(4+i*.83),(.65,.7,.45+.65*abs(math.sin(i*.8+j*.7)))) for i in range(13)]
        _keys(memory,'scale',values)
    _shown(sphere('LSTM identificacao da localidade',(-3.2,-.5,4.8),.20,white),
           t(15.1),t(21),'identificacao aprendida da localidade juntada ao estado final',.3)
    _label(scene,'LSTM ID rotulo','Localidade',(-3.7,-.6,5.22),.28,COLORS['white'],t(15.4),t(19.5))
    _line('LSTM ID para cabeca',[(-3.2,-.5,4.8),(-2.7,-.8,4.95),(1.8,-.8,4.95),(2.6,-.3,3.3)],
          white,t(16),t(21),'embedding local se combina com estado final na cabeca',1.0,.035)
    _line('LSTM estado para saida',[(1.8,-.5,4.65),(2.6,-.3,3.3),(3.2,-.2,3.3)],
          coral,t(17.6),t(24),'estado final alimenta uma unica cabeca de saida direta',1.0,.06)
    _vector(scene,'LSTM futuro',(3.15,-.1,2.25),coral,19,24,t,(2.6,-.2,3.3))
    _label(scene,'LSTM saida simultanea','Todo o horizonte',(4.1,-.7,4.35),.29,
           COLORS['white'],t(20.1),t(24))

    # Transformer: positional representations -> query/key comparison ->
    # normalized weights -> weighted values -> encoder/decoder forecast.
    keys=[(-4.95+i*.9,.1,4.0) for i in range(12)]
    _history('Transformer historico',24,27.8,28.4,keys,white,t)
    _label(scene,'Nome Transformer','Transformer',(-4.3,0,6.3),.48,COLORS['cyan'],t(24.2),t(50))
    for i,(x,y,z) in enumerate(keys):
        token = _shown(box(f'Transformer posicao historica {i+1:02d}',(x,y,z),
                           (.57,.76,.62+GHI[i]*.5),m['cyan_body'],.10),
                       t(26.5+i*.04),t(46),'representacao aprendida do valor GHI mais ordem e localidade',.4)
        # A visible sequence of position markers augments amplitudes.
        _shown(box(f'Transformer marca de ordem {i+1:02d}',(x,-.43,3.36),
                   (.14,.22,.12+i*.018),cyan,.025),t(27+i*.045),t(34),
               'codificacao da ordem temporal; alturas meramente simbolicas',.2)
    _label(scene,'Transformer posicoes rotulo','Valor + posição',(0,-.4,5.2),.30,
           COLORS['white'],t(26.9),t(28.5))
    query=(-4.75,-.55,5.15)
    _shown(sphere('Transformer consulta destacada',query,.24,cyan),t(28.1),t(40),
           'consulta de uma posicao para comparar com chaves',.4)
    _label(scene,'Transformer consulta rotulo','Consulta',(-4.55,-.7,5.72),.29,
           COLORS['cyan'],t(28.4),t(34))
    _label(scene,'Transformer comparar rotulo','Comparar com as chaves',(.7,-.7,5.55),.31,
           COLORS['white'],t(28.6),t(34))
    weights=(.03,.05,.08,.19,.12,.04,.03,.07,.18,.11,.06,.04)
    for i,key in enumerate(keys):
        pts=_arc(query,(key[0],-.42,4.28),.25,.25)
        _line(f'Transformer comparacao Q K {i+1:02d}',pts,soft,t(28.6+i*.14),t(34.3),
              'produto de consulta com chave, visualizacao esquematica',.35,.018)
        _particle(f'Transformer pulso comparacao {i+1:02d}',pts,cyan,
                  t(29.5+i*.2),t(30.4+i*.2),.075)
        h=.20+weights[i]*5.0
        bar = _shown(box(f'Transformer peso normalizado {i+1:02d}',(key[0],-.55,2.10+h/2),
                         (.43,.58,h),cyan,.075),t(34+i*.07),t(40.5),
                     'peso visual didatico normalizado, nao atencao medida',.55)
        _line(f'Transformer chave para peso {i+1:02d}',[(key[0],-.46,3.65),(key[0],-.55,2.10+h)],
              soft,t(34.2+i*.07),t(40.5),'escore de comparacao transformado em peso',.4,.015)
    _label(scene,'Transformer pesos rotulo','Pesos',(0,-.65,1.55),.34,COLORS['cyan'],t(34.4),t(40.5))
    # Values carry vector features; the unequal contributions converge visibly.
    for i,(key,weight) in enumerate(zip(keys,weights)):
        start=40.0+i*.08
        pos=(key[0],-.55,3.2)
        size=.17+weight*1.7
        contribution = _shown(box(f'Transformer valor ponderado {i+1:02d}',pos,
                                  (size,size*.9,size*1.4),cyan,.06),
                              t(start),t(45.7),'contribuicao do vetor valor multiplicado por seu peso',.25)
        target=(.5+(i%3-.9)*.2,-.6,2.5+(i//3)*.12)
        _keys(contribution,'location',[(t(start+.3),pos),(t(43.6+i*.09),target)])
        _line(f'Transformer caminho valor {i+1:02d}',_arc(pos,target,-.35,.15),soft,
              t(start+.3),t(45.7),'soma das contribuicoes ponderadas',.5,.014)
    _shown(box('Transformer representacao combinada',(.5,-.25,2.7),(.92,.88,1.0),m['cyan_body'],.16),
           t(43.8),t(46),'resultado da combinacao de valores e camadas de representacao',.7)
    _label(scene,'Transformer combinar rotulo','Combinar valores',(0,-.85,5.35),.34,
           COLORS['white'],t(40.5),t(45.9))
    _shown(box('Transformer decoder',(1.8,.15,3.35),(1.8,1.0,1.8),m['cyan_body'],.20),
           t(46),t(50),'decoder recebe memoria do encoder e contexto final com futuro vazio',.45)
    _label(scene,'Transformer decoder rotulo','Decoder',(1.8,-.55,4.65),.30,
           COLORS['cyan'],t(46.3),t(50))
    for i in range(6):
        px=-4.6+i*.7
        _shown(box(f'Transformer contexto final decoder {i+1}',(px,.1,3.85),(.48,.55,.56),soft,.07),
               t(46),t(50),'parte final observada do contexto fornecida ao decoder',.35)
    for i in range(4):
        px=-3.9+i*.8
        # Hollow future tokens denote unavailable inputs rather than true y.
        corners=[(px-.22,-.25,2.45),(px+.22,-.25,2.45),
                 (px+.22,-.25,3.0),(px-.22,-.25,3.0),(px-.22,-.25,2.45)]
        _line(f'Transformer futuro vazio decoder {i+1}',corners,soft,t(46),t(48.1),
              'posicao futura inicialmente vazia; alvos nao entram no decoder',.3,.025)
    _line('Transformer entrada decoder',[(-.2,-.2,3.3),(.7,-.2,3.3)],cyan,t(46.4),t(50),
          'decoder combina contexto com memoria codificada',.5,.055)
    _vector(scene,'Transformer futuro',(3.8,-.15,2.5),cyan,47.7,50,t,(2.7,-.15,3.3))

    # Informer: first sparse query updates; only then temporal distillation.
    # Distillation is one 12->6 operation, matching two encoder blocks and
    # one intervening convolution/max-pooling stage in the actual source.
    infkeys=[(-4.95+i*.9,.1,4.05) for i in range(12)]
    _history('Informer historico',50,53.6,54.0,infkeys,white,t)
    _label(scene,'Nome Informer','Informer',(-4.45,0,6.0),.49,COLORS['violet'],t(50.2),t(75))
    for i,pos in enumerate(infkeys):
        _shown(box(f'Informer representacao inicial {i+1:02d}',pos,(.59,.76,.72),m['violet_body'],.1),
               t(52.6+i*.04),t(66),'representacao interna da sequencia; nao ponto removido do dado',.4)
    selected=(3,8)
    for j,index in enumerate(selected):
        source=infkeys[index]
        q=(source[0],-.65,5.25)
        query_obj=_shown(sphere(f'Informer consulta selecionada {j+1}',source,.25,violet),
                         t(54+j*.28),t(60),'consulta selecionada para calculo detalhado sobre todas as chaves',.3)
        _keys(query_obj,'location',[(t(54+j*.28),source),(t(54.8+j*.28),q)])
        for k,key in enumerate(infkeys):
            pts=_arc(q,(key[0],-.42,4.35),.15,.30)
            _line(f'Informer consulta {j+1} compara chave {k+1:02d}',pts,soft,
                  t(55.1+j*.4+k*.055),t(60),
                  'para a consulta selecionada o calculo detalhado usa todas as chaves',.28,.017)
            if k in (0,4,8,11):
                _particle(f'Informer pulso consulta {j+1} chave {k+1}',pts,violet,
                          t(55.8+j*.45+k*.05),t(56.6+j*.45+k*.05),.08)
    _label(scene,'Informer selecao rotulo','Consultas selecionadas',(0,-.75,6.0),.31,
           COLORS['violet'],t(54.4),t(59.8))
    _label(scene,'Informer contexto rotulo','Contexto para as demais',(0,-.55,2.75),.28,
           COLORS['secondary'],t(56.6),t(59.8))
    _line('Informer contexto agregado',[(-4.95,-.1,3.38),(4.95,-.1,3.38)],soft,t(54.8),t(60),
          'consultas nao selecionadas conservam contexto agregado; nao sao descartadas',.7,.03)
    distilled=[(-4.5+i*1.8,.12,2.85) for i in range(6)]
    for j,dest in enumerate(distilled):
        for i in (max(0,2*j-1),2*j,min(11,2*j+1)):
            a=infkeys[i]
            pts=[(a[0],-.25,3.7),((a[0]+dest[0])*.5,-.7,3.35),(dest[0],-.25,3.15)]
            _line(f'Informer vizinhanca encoder {j+1} fonte {i+1}',pts,soft,
                  t(60.2+j*.08),t(65.9),'vizinhanca convolucional antes da reducao por pooling',.5,.022)
            _particle(f'Informer fluxo destilacao {j+1} fonte {i+1}',pts,violet,
                      t(61+j*.2),t(62+j*.2),.095)
        _shown(box(f'Informer representacao destilada {j+1}',dest,(1.04,.9,.9),violet,.15),
               t(61.6+j*.23),t(71.5),'representacao apos uma etapa de conv e maxpool entre encoders',.6)
    _label(scene,'Informer destilacao rotulo','Reduzir a sequência interna',(0,-.7,5.6),.34,
           COLORS['violet'],t(60.4),t(65.9))
    # Reorganize all six distilled encoder states into a memory row, then
    # display every encoder/decoder connection of the full cross-attention.
    memory=[(-4.5+i*1.8,.12,4.65) for i in range(6)]
    for i,(src,dest) in enumerate(zip(distilled,memory)):
        obj=bpy.data.objects[f'Informer representacao destilada {i+1}']
        _keys(obj,'location',[(t(65.9),src),(t(66.6),dest)])
    decoder_queries=[(-3.3+i*2.2,-.12,2.65) for i in range(4)]
    for j,q in enumerate(decoder_queries):
        _shown(box(f'Informer posicao futura no decoder {j+1}',q,(.72,.8,.72),m['violet_body'],.12),
               t(66.2),t(71.5),'posicao do decoder que consulta todas as representacoes do encoder',.45)
        for i,mem in enumerate(memory):
            pts=[(mem[0],-.34,4.24),((mem[0]+q[0])*.5,-.6,3.65),(q[0],-.48,3.05)]
            _line(f'Informer atencao cruzada completa q{j+1} m{i+1}',pts,soft,
                  t(66.8+j*.18),t(71.5),'atencao cruzada completa: nenhuma memoria omitida',.5,.018)
            if i in (0,2,5):
                _particle(f'Informer pulso cruzada q{j+1} m{i+1}',pts,violet,
                          t(67.5+j*.55+i*.04),t(68.35+j*.55+i*.04),.075)
    _label(scene,'Informer cruzada rotulo','Atenção cruzada completa',(0,-.8,5.7),.34,
           COLORS['white'],t(66.6),t(71.4))
    _vector(scene,'Informer futuro',(-1.1,-.25,2.8),violet,71.4,75,t,(0,-.15,3.5))
    _label(scene,'Informer saida rotulo','Previsão do horizonte',(0,-.75,4.95),.35,
           COLORS['violet'],t(72.3),t(75))

    # A metadata description makes overlay/narration timing deterministic.
    phase_data=[
        ('LSTM',0,3,'mesma serie GHI se reorganiza para leitura sequencial'),
        ('LSTM',3,15,'valores entram em ordem, portas modulam atualizacao de memoria'),
        ('LSTM',15,19,'estado final combina-se com identificacao aprendida da localidade'),
        ('LSTM',19,24,'cabeca produz todo o vetor futuro diretamente'),
        ('Transformer',24,28,'valores tornam-se representacoes com posicao temporal'),
        ('Transformer',28,34,'consulta compara-se com chaves de todas as posicoes'),
        ('Transformer',34,40,'comparacoes produzem pesos normalizados didaticos'),
        ('Transformer',40,46,'valores ponderados se combinam em nova representacao'),
        ('Transformer',46,50,'decoder usa contexto observado e futuro inicialmente vazio'),
        ('Informer',50,54,'a mesma serie torna-se sequencia de representacoes'),
        ('Informer',54,60,'consultas selecionadas recebem calculo detalhado; demais conservam contexto'),
        ('Informer',60,66,'uma etapa de destilacao reduz comprimento entre dois blocos do encoder'),
        ('Informer',66,71.4,'decoder consulta todas as representacoes na atencao cruzada completa'),
        ('Informer',71.4,75,'saida do horizonte de previsao'),
    ]
    scene.frame_set(1)
    return {
        'version':4,'builder':'build_networks_v4','duration_seconds':duration,
        'fps':FPS,'frame_count':round(duration*FPS),'camera':camera.name,
        'object_names':[obj.name for obj in bpy.data.objects if obj.name not in before],
        'camera_keyframes':shots,'palette_srgb':COLORS,'historical_values_schematic':list(GHI),
        'same_history_all_models':True,'visible_sample_count':12,
        'architecture_phases':[
            {'model':'LSTM','start':t(0),'end':t(24)},
            {'model':'Transformer','start':t(24),'end':t(50)},
            {'model':'Informer','start':t(50),'end':t(75)}],
        'shotphases':[{'model':model,'start':t(a),'end':t(b),'meaning':meaning}
                      for model,a,b,meaning in phase_data],
        'scientific_precision':{
            'visual_weights_and_gates':'didactic; not measured learned activations or attention',
            'lstm_forecast':'final hidden state plus locality embedding feeds direct horizon head',
            'transformer_decoder':'last observed context plus zero future inputs; no target leakage',
            'informer_sparse':'selected queries update full-key context; other queries retain aggregate context',
            'informer_distillation':'one conv/batchnorm/ELU/maxpool between two encoder blocks',
            'informer_cross_attention':'complete, including every encoded memory position',
            'numeric_forecast_values_shown':False,'efficiency_measurements_shown':False,
            'only_inputs':'historical GHI and learned locality ID',
            'output_components':'four visible schematic components represent a task-specific full horizon',
        },
        'caption_safe_area':'bottom 15 percent reserved; no footer/header or platform geometry',
        'source_files':['codigo_fonte/experimentos/experimento_horario_timesnet.py:LSTMEncoderDireto',
                        'codigo_fonte/modelos/modelos_baselines_adicionais.py:TransformerDireto/AtencaoProjetada/Distilacao/BlocoDecoder'],
    }
