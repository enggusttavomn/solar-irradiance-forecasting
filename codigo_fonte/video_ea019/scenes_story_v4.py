"""Direcao espacial dos capitulos 2-6 da versao 4 do video EA019.

Reutiliza a geometria e os dados conferidos da V3. Acrescenta representacoes
volumetricas, fluxos de informacao e percursos de camera perspectiva. Nao
renderiza, nao escreve arquivos e nao cria textos: os poucos rotulos curtos
sao compostos pelo montador. Todos os volumes/fluxos numericamente abstratos
sao ilustracoes, nunca novos resultados ou sensores nas fabricas.
"""

from __future__ import annotations

import math
from pathlib import Path
import sys
import unicodedata

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_pilot import box, emission, polyline, reveal, sphere, surface, visible, wire_box


FPS = 30
REFERENCE_DURATIONS = {2: 35., 3: 20., 4: 40., 5: 35., 6: 40.}
PALETTE = {
    'background': '#07090D', 'body': '#171C22', 'white': '#F3F5F7',
    'secondary': '#A9B2BE', 'axes': '#626D7A', 'gold': '#E9B95F',
    'coral': '#F28779', 'cyan': '#58CADA', 'violet': '#AA91E8',
}


def _plain(value):
    return ''.join(char for char in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(char))


def _frame(seconds):
    return round(float(seconds)*FPS)+1


def _rgba(hex_color):
    rgb = [int(hex_color.lstrip('#')[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4 for c in rgb)+(1.,)


def _mat(name, key='white', luminous=True):
    hex_color = PALETTE.get(key, key)
    rgba = _rgba(hex_color)
    material = emission('V4 '+name, rgba, 1.) if luminous else surface(
        'V4 '+name, rgba, metallic=0., roughness=.88)
    material.diffuse_color = rgba
    material['design_srgb_hex'] = hex_color
    return material


def _empty(name):
    obj = bpy.data.objects.new('V4 '+name, None)
    bpy.context.collection.objects.link(obj)
    return obj


def _action_curves(owner):
    data = getattr(owner, 'animation_data', None)
    return list(data.action.fcurves) if data and data.action else []


def _constant_visibility(obj, hidden=True):
    for curve in _action_curves(obj):
        if curve.data_path == 'hide_render':
            obj.animation_data.action.fcurves.remove(curve)
    obj.hide_render = hidden


def _show(obj, start, end, meaning, parent=None):
    if parent is not None:
        obj.parent = parent
    obj['meaning'] = meaning
    obj['v4_conceptual_geometry'] = True
    visible(obj, start, end+.01)
    return obj


def _trace(name, points, material, start, end, draw=.7, radius=.015, parent=None):
    obj = _show(polyline('V4 '+name, points, material, radius), start, end,
                'fluxo ou serie conceitual, sem novos valores experimentais', parent)
    reveal(obj, start, min(draw, max(.01, end-start)))
    return obj


def _keys(obj, path, values, linear=False):
    for seconds, value in values:
        setattr(obj, path, value)
        obj.keyframe_insert(path, frame=_frame(seconds))
    for curve in _action_curves(obj):
        if curve.data_path == path:
            for point in curve.keyframe_points:
                point.interpolation = 'LINEAR' if linear else 'BEZIER'
                if not linear:
                    point.handle_left_type = point.handle_right_type = 'AUTO_CLAMPED'


def _particle(name, points, moments, material, radius=.045, parent=None):
    obj = _show(sphere('V4 '+name, points[0], radius, material), moments[0], moments[-1],
                'pacote ilustrativo de informacao, nao medicao', parent)
    _keys(obj, 'location', list(zip(moments, points)), linear=True)
    return obj


def _arc(a, b, height=.45, depth=.24, count=24):
    a, b = Vector(a), Vector(b)
    points = []
    for i in range(count+1):
        u = i/count
        point = a.lerp(b, u)
        point.z += math.sin(math.pi*u)*height
        point.y += math.sin(math.pi*u)*depth
        points.append(tuple(point))
    return points


def _rail(scene, keys, timing):
    """Perspectiva real, com alvo acompanhado e pausas breves para leitura."""
    camera = scene.camera
    if camera is None:
        bpy.ops.object.camera_add()
        camera = bpy.context.object
        scene.camera = camera
    camera.name = 'V4 camera perspectiva acompanhando a explicacao'
    camera.animation_data_clear()
    camera.data.animation_data_clear()
    camera.data.type = 'PERSP'
    camera.data.sensor_width = 36.
    camera.data.sensor_fit = 'HORIZONTAL'
    camera.data.shift_x = camera.data.shift_y = 0.
    camera.data.clip_start = .035
    camera.data.clip_end = 250.
    camera.data.dof.use_dof = False
    description = []
    for second, location, target, lens in keys:
        camera.location = location
        camera.rotation_euler = (Vector(target)-camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.lens = lens
        camera.keyframe_insert('location', frame=_frame(timing(second)))
        camera.keyframe_insert('rotation_euler', frame=_frame(timing(second)))
        camera.data.keyframe_insert('lens', frame=_frame(timing(second)))
        description.append({'second': timing(second), 'location': list(location),
                            'target': list(target), 'lens_mm': lens})
    for owner in (camera, camera.data):
        for curve in _action_curves(owner):
            for point in curve.keyframe_points:
                point.interpolation = 'BEZIER'
                point.handle_left_type = point.handle_right_type = 'AUTO_CLAMPED'
    return {'projection': 'PERSP', 'name': camera.name, 'keys': description,
            'intent': 'acompanhar o objeto, aproximar detalhes e conservar profundidade',
            'caption_region': '15 por cento inferiores', 'header_region_reserved': False}


def _retime(objects, factor):
    if abs(factor-1.) < 1e-8:
        return
    actions = {}
    for obj in objects:
        owners = [obj, obj.data]
        owners.extend(material.node_tree for material in getattr(obj.data, 'materials', ())
                      if material and material.use_nodes)
        for owner in owners:
            data = getattr(owner, 'animation_data', None)
            if data and data.action:
                actions[data.action.as_pointer()] = data.action
    for action in actions.values():
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                for coordinate in (point.co, point.handle_left, point.handle_right):
                    coordinate.x = 1+(coordinate.x-1)*factor
            curve.update()


def _harmonize(objects, chapter):
    """Dar a todos os materiais legados cores declaradas para Workbench/PBR."""
    for material in {mat for obj in objects for mat in getattr(obj.data, 'materials', ()) if mat}:
        if material.get('design_srgb_hex'):
            material.diffuse_color = _rgba(material['design_srgb_hex'])
            continue
        name = _plain(material.name)
        key = 'secondary'
        if any(word in name for word in ('vidro', 'painel', 'blocos', 'preenchimento', 'base')):
            key = 'body'
        elif any(word in name for word in ('eixo', 'linha temporal', 'estrutura', 'moldura', 'contorno discreto')):
            key = 'axes'
        elif chapter == 3 and any(word in name for word in ('coral', 'lstm')):
            key = 'coral'
        elif chapter == 3 and any(word in name for word in ('cyan', 'ciano', 'transformer')):
            key = 'cyan'
        elif chapter == 3 and any(word in name for word in ('violeta', 'informer')):
            key = 'violet'
        elif any(word in name for word in ('solar', 'destaque', 'escolhida', 'futuro', 'previsao', 'ponto ')):
            key = 'gold'
        elif any(word in name for word in ('historico', 'ghi', 'disponiveis', 'referencia', 'borda', 'costa')):
            key = 'white'
        material['design_srgb_hex'] = PALETTE[key]
        material.diffuse_color = _rgba(PALETTE[key])
        if material.use_nodes:
            for node in material.node_tree.nodes:
                if node.type == 'EMISSION':
                    node.inputs['Color'].default_value = material.diffuse_color
                elif node.type == 'BSDF_PRINCIPLED':
                    node.inputs['Base Color'].default_value = material.diffuse_color
                    node.inputs['Roughness'].default_value = .88
                    node.inputs['Metallic'].default_value = 0.


def _factory(scene, duration):
    from scenes_factory_v3 import build_factory
    before = set(bpy.data.objects)
    base = build_factory(35)
    legacy = set(bpy.data.objects)-before
    factor = duration/35.
    _retime(legacy, factor)
    t = lambda second: second*factor
    for obj in legacy:
        if _plain(obj.name).startswith(('base lisa da maquete', 'base da curva lateral',
                                        'curva lateral de variacao atmosferica')):
            _constant_visibility(obj)
    assembly = next(obj for obj in legacy if obj.name.startswith('Maquete industrial ilustrativa'))
    assembly.animation_data_clear()
    assembly.location = (0, 0, 0)
    assembly.scale = (1, 1, 1)
    _keys(assembly, 'scale', [(t(0), (1,)*3), (t(23.2), (1,)*3),
                              (t(24), (.001,)*3)])
    neutral = _mat('factory juntas e espessuras', '#46515D', False)
    gold = _mat('factory particulas solares', 'gold')
    white = _mat('factory curva de transicao', 'white')
    # Shallow facade ribs articulate the solid building without a visual grid.
    for i, x in enumerate((-3.02, -1.65, -.3, 1.05, 2.23)):
        _show(box(f'V4 nervura vertical da fachada {i}', (x, -1.584, .88),
                  (.035, .032, 1.65), neutral, .007), t(0), t(24),
              'espessura construtiva ilustrativa', assembly)
    receiver = Vector((.55, -.12, 1.92))
    incoming = Vector((-1.55, .45, 1.70))
    for ray in range(4):
        target = receiver+Vector((-.30+.2*ray, -.18+.12*(ray % 2), 0))
        for pulse in range(3):
            a = 12.15+ray*.13+pulse*1.35
            _particle(f'fotons ilustrativos {ray} {pulse}',
                      [target+incoming, target], [t(a), t(a+1.0)], gold, .027, assembly)
    transition = _empty('curve leading from roof to temporal explanation')
    # The curve grows in physical foreground space before taking over the shot.
    curve_points = []
    for i in range(100):
        u = i/99
        pulse = max(0., math.sin(2.6*math.pi*u))**2
        curve_points.append((-3.2+6.4*u, -2.75+.42*math.sin(math.pi*u), .65+1.35*pulse))
    _trace('curva espacial emergindo da irradiancia', curve_points, white,
           t(19.4), t(24), t(3.0), .023, transition)
    _trace('ligacao telhado a curva temporal',
           _arc(receiver, (-.5, -2.75, 1.2), .25, -.15), gold,
           t(19.2), t(23.8), t(1.0), .012, transition)
    camera = _rail(scene, [
        (0, (6.2, -8.2, 5.2), (-.3, 0, 0), 40),
        (3.8, (5.4, -8.8, 5.3), (-.3, 0, .1), 40),
        (6.0, (2.65, -4.4, 5.25), (.5, -.05, 1.78), 48),
        (9.0, (1.8, -4.6, 5.6), (.55, -.12, 1.80), 48),
        (11.7, (.5, -4.9, 5.7), (.55, -.12, 1.80), 48),
        (13.3, (4.2, -8.0, 5.6), (.15, 0, 1.9), 42),
        (16.8, (3.0, -8.2, 5.8), (.25, 0, 1.9), 42),
        (19.5, (-3.0, -9.4, 5.6), (0, -.8, 1.6), 40),
        (23.5, (-1.4, -10.2, 4.8), (0, -1.2, 1.65), 42),
        (24, (.4, -13.6, 3.0), (0, 0, 1.7), 46),
        (29.8, (-.6, -13.4, 3.3), (0, 0, 1.7), 46),
        (35, (1.0, -13.3, 3.6), (0, 0, 1.7), 46),
    ], t)
    return {'source': base, 'camera': camera,
            'phases': [[t(a), t(b), label] for a, b, label in (
                (0, 4, 'maquete em orbita'), (4, 12, 'aproximacao da area horizontal de 1 m2'),
                (12, 17, 'radiacao direta e difusa em profundidade'),
                (17, 24, 'geometria solar e curva emergente'),
                (24, 35, 'historico e futuro desconhecido'))],
            'reference_area_m2': 1., 'factual_scope': 'GHI em superficie horizontal; fabrica ilustrativa',
            'empty_platform_removed': True}


def _objective(scene, duration):
    from scenes_explainer import build_objective
    before = set(bpy.data.objects)
    base = build_objective(20)
    legacy = set(bpy.data.objects)-before
    factor = duration/20.
    _retime(legacy, factor)
    t = lambda second: second*factor
    _harmonize(legacy, 3)
    # Open the model volumes so that information, not opaque empty boxes, is visible.
    for obj in legacy:
        if 'representacao' in _plain(obj.name) and obj.type == 'MESH':
            _constant_visibility(obj)
    white = _mat('objective common observations', 'white')
    for i in range(7):
        u = i/6
        x = -4.2+8.4*u
        phase = (x+4.3) % 2.8
        z = .43+.55*(math.sin(math.pi*phase/(2.8*.73))**2 if phase < 2.8*.73 else 0.)
        token = _show(box(f'V4 amostra historica fisica {i}', (x, -.75, z),
                          (.09, .15, .09), white, .018), t(.1+i*.12), duration,
                      'amostra ilustrativa de GHI disponivel')
        _keys(token, 'location', [(t(0), (x, -.75, z)),
                                   (t(4.8), (x, -.75, z)),
                                   (t(6.1+i*.06), (0, -.7, .70))])
    for model, (x, key) in enumerate(((-3., 'coral'), (0., 'cyan'), (3., 'violet'))):
        material = _mat('objective '+key+' internal information', key)
        nodes = []
        for layer in range(2):
            row = []
            for j in range(3):
                p = (x-.22+.44*layer, -.13+.19*layer, 1.39+j*.23)
                _show(sphere(f'V4 modelo {model} no {layer} {j}', p, .049, material),
                      t(7+model*.3), duration, 'representacao didatica interna da rede')
                row.append(p)
            nodes.append(row)
        for i, a in enumerate(nodes[0]):
            for j, b in enumerate(nodes[1]):
                _trace(f'modelo {model} relacao interna {i} {j}', [a, b], material,
                       t(7.4+model*.3), duration, t(.7), .007)
        for pulse in range(3):
            start = 8.+model*.3+pulse*1.0
            _particle(f'entrada compartilhada modelo {model} {pulse}',
                      [(0, -.7, .7), (x, -.12, 1.25), (x, .06, 2.05), (0, .65, 3.05)],
                      [t(start), t(start+1), t(start+1.8), t(start+2.7)],
                      material, .047)
        outputs = []
        for i in range(50):
            u = i/49
            outputs.append((-1.6+3.2*u, .52+model*.27,
                            3.05+.62*math.sin(math.pi*u)**2+model*.025*math.sin(4*math.pi*u)))
        curve = _trace(f'saida comparavel ilustrativa {model}', outputs, material,
                       t(12.4+model*.25), duration, t(1.5), .016)
        curve['not_an_experimental_prediction'] = True
    camera = _rail(scene, [
        (0, (-4.6, -7.3, 2.9), (-1.1, -.65, .65), 40),
        (4.6, (2.3, -8.0, 3.2), (0, -.65, .8), 42),
        (7.4, (3.6, -9.3, 4.8), (0, 0, 1.45), 42),
        (11.6, (-3.1, -9.7, 5.0), (0, 0, 1.85), 42),
        (14.3, (-1.7, -7.1, 5.3), (0, .35, 2.5), 44),
        (17.0, (2.8, -9.4, 4.8), (0, .1, 1.9), 42),
        (20, (1.1, -9.6, 4.4), (0, 0, 1.8), 42),
    ], t)
    return {'source': base, 'camera': camera, 'phases': [
        [t(0), t(6), 'historico compartilhado em primeiro plano'],
        [t(6), t(12), 'entrada atravessa tres modelos preenchidos'],
        [t(12), duration, 'saidas comparaveis e criterios da comparacao']],
        'outputs_are_illustrative': True, 'no_empty_model_bodies': True}


def _map(scene, duration):
    # Lazy import avoids a director_v4 -> story -> director_v4 cycle.
    from director_v3 import map_v3
    before = set(bpy.data.objects)
    base = map_v3()
    legacy = set(bpy.data.objects)-before
    factor = duration/40.
    _retime(legacy, factor)
    t = lambda second: second*factor
    _harmonize(legacy, 4)
    for obj in legacy:
        name = _plain(obj.name)
        if name.startswith(('meridiano ', 'paralelo ', 'detroit grade')):
            _constant_visibility(obj)
        if name.startswith('fluxo') and 'historico' in name and 'ghi' in name:
            _constant_visibility(obj)
        if name.startswith('terra natural earth') and obj.type == 'MESH':
            modifier = obj.modifiers.new('V4 espessura continental discreta', 'SOLIDIFY')
            modifier.thickness = .055
    points = base.get('localities', [])
    if len(points) != 10:
        raise ValueError('A historia V4 requer as dez coordenadas verificadas da V3')
    white = _mat('map observations', 'white')
    gold = _mat('map selected cell and locality', 'gold')
    body = _mat('map physical query cell', 'body', False)
    history_points = []
    for i in range(81):
        u = i/80
        pulse = max(0., math.sin(u*2.7*2*math.pi))**2
        history_points.append((-4.45+1.70*u, -.22, 3.4+.44*pulse))
    _trace('historico GHI visivel diante do painel de entrada', history_points,
           white, t(19), duration, t(2), .016)
    _show(box('V4 espessura da celula NSRDB', (2.625, .16, 2.575),
              (1.78, .18, 1.78), body, .035), t(12), t(19),
          'celula esquematica da base, sem escala geografica declarada')
    _show(box('V4 celula selecionada em relevo', (2.625, .02, 2.575),
              (.53, .10, .53), gold, .018), t(13), t(19),
          'selecionar uma coordenada da base, nao um sensor')
    for i in range(5):
        _particle(f'valor ilustrativo celula para historico {i}',
                  [(2.625, -.1, 2.575), (1.5, -.5, 3.3), (-1.7, -.4, 3.8)],
                  [t(16.8+i*.12), t(18.0+i*.12), t(19.5+i*.12)], gold, .035)
    # Larger input packets make both actual input types tangible in close-up.
    for i in range(8):
        x = -4.39+(i % 4)*.46
        z = 1.80+(i//4)*.25
        _show(box(f'V4 identidade local pacote {i}', (x, -.12, z),
                  (.095, .13, .095), gold, .018), t(23.+i*.09), duration,
              'vetor aprendido da identificacao da localidade')
    for i in range(4):
        start = 27+i*1.6
        _particle(f'fluxo GHI entra no modelo {i}',
                  [(-3.65, -.16, 3.65), (-2.55, -.16, 3.65), (-1.13, -.16, 3.0), (-.35, -.16, 2.8)],
                  [t(start), t(start+.7), t(start+1.5), t(start+2.4)], white, .050)
        _particle(f'identidade local entra no modelo {i}',
                  [(-3.65, -.16, 1.95), (-2.55, -.16, 1.95), (-1.13, -.16, 2.55), (-.35, -.16, 2.8)],
                  [t(start+.3), t(start+1), t(start+1.8), t(start+2.7)], gold, .045)
    camera = _rail(scene, [
        (0, (-.8, -11.5, 5.8), (-2.05, 0, 2.45), 48),
        (4.8, (-3.7, -9.6, 5.1), (-2.05, 0, 2.65), 46),
        (7.0, (-2.8, -5.8, 4.9), (-2.0, 0, 3.55), 48),
        (10.8, (-1.2, -4.4, 4.7), (-1.9, 0, 3.65), 48),
        (12.7, (3.15, -3.2, 3.6), (2.625, 0, 2.45), 45),
        (17.3, (2.15, -3.3, 3.45), (2.625, 0, 2.45), 45),
        (20, (-1.0, -10.0, 4.8), (-2.0, 0, 2.65), 44),
        (23.4, (-4.3, -7.8, 4.2), (-2.65, 0, 2.7), 44),
        (28.8, (-2.8, -7.1, 4.1), (-2.0, 0, 2.7), 44),
        (34.0, (-1.8, -6.4, 4.0), (-1.5, 0, 2.65), 46),
        (40, (-1.0, -6.0, 3.7), (-.9, 0, 2.65), 46),
    ], t)
    return {'source': base, 'camera': camera, 'phases': [
        [t(0), t(6), 'continente e dez coordenadas reais'],
        [t(6), t(12), 'aproximacao das localidades'],
        [t(12), t(19), 'consulta de celula NSRDB em relevo'],
        [t(19), t(23), 'historicos por localidade'],
        [t(23), duration, 'GHI mais identificacao entram em rede compartilhada']],
        'locality_count': 10, 'country_counts': {'BR': 1, 'US': 8, 'MX': 1},
        'coordinate_source': base.get('localities'),
        'no_new_model_inputs': True, 'coordinate_positions_preserved': True}


def _task_height(x, period):
    phase = (x+4.2) % period
    pulse = math.sin(math.pi*phase/(period*.72))**2 if phase < period*.72 else 0.
    return 1.90+1.60*pulse


def _tasks(scene, duration):
    from director_v3 import tasks_v3
    before = set(bpy.data.objects)
    base = tasks_v3()
    legacy = set(bpy.data.objects)-before
    factor = duration/35.
    _retime(legacy, factor)
    t = lambda second: second*factor
    _harmonize(legacy, 5)
    white = _mat('tasks physical history', 'white')
    gold = _mat('tasks future positions', 'gold')
    body = _mat('tasks window side walls', '#46515D', False)
    secondary = _mat('tasks common geometry', 'secondary')
    # Four floating histories establish the subject immediately: no blank intro.
    for i, period in enumerate((1.8, 3.0, 4.7, 4.7)):
        points = []
        for j in range(75):
            x = -3.8+7.6*j/74
            points.append((x, -.50+i*.38, .72+i*.68+.36*max(0, math.sin((x+4)*math.pi/period))**2))
        _trace(f'quatro resolucoes em fitas espaciais {i}', points, white,
               t(.05+i*.12), t(5.1), t(1.3), .023)
        _particle(f'pacote introduz tarefa {i}', [points[0], points[25], points[50], points[-1]],
                  [t(.8+i*.12), t(1.8+i*.12), t(2.8+i*.12), t(4.3+i*.12)],
                  gold, .047)
    phases = [(5, 11, 1.8), (11, 16, 3.0), (16, 21, 4.7), (21, 26, 4.7)]
    for index, (start, end, period) in enumerate(phases):
        group = _empty(f'physical task window {index}')
        group['task_index'] = index
        for obj in legacy:
            if obj.name.startswith(f'Tarefa {index} '):
                obj.parent = group
                # Monthly aggregates use seasonal, strictly positive schematic
                # shapes rather than a daily curve with apparent night zeros.
                if index >= 2 and any(word in _plain(obj.name) for word in ('observado', 'vetor futuro')):
                    _constant_visibility(obj)
                if index == 2 and 'eixo' in _plain(obj.name):
                    _constant_visibility(obj)
        def amplitude(x):
            return (2.55+.57*math.sin((x+4.2)*math.pi/3.9)
                    if index >= 2 else _task_height(x, period))
        if index >= 2:
            if index == 2:
                _trace('eixo apenas do horizonte mensal de um passo',
                       [(-4.3, 0, 1.86), (2.5, 0, 1.86)], secondary,
                       t(start), t(end), t(.3), .008, group)
            observed = [(-4.2+4.5*i/110, -.015, amplitude(-4.2+4.5*i/110)) for i in range(111)]
            _trace(f'mensal {index} variacao sazonal observada', observed, white,
                   t(start+.1), t(end), t(1.1), .020, group)
            count = 1 if index == 2 else 6
            for lead in range(count):
                x = 1.35 if count == 1 else .72+lead*.63
                point = _show(sphere(f'V4 mensal {index} posicao futura {lead+1}',
                                     (x, -.015, amplitude(x)), .065, gold),
                              t(start+1.45+lead*.11), t(end),
                              'componente ilustrativa do horizonte mensal', group)
                point['output_count_for_task'] = count
        for j in range(13):
            x = -1.19+j*.11
            value = amplitude(x)
            height = max(.055, value-1.88)
            _show(box(f'V4 tarefa {index} dado na janela {j}',
                      (x, -.11, 1.90+height/2), (.065, .21, height), white, .012),
                  t(start+.45+j*.025), t(end), 'amplitude ilustrativa dentro da janela historica', group)
        # Side rails have physical thickness and move with the selected window.
        for x in (-1.29, .34):
            _show(box(f'V4 tarefa {index} lateral volumetrica {x}',
                      (x, .03, 2.94), (.045, .56, 2.16), body, .012),
                  t(start+.45), t(end), 'parede lateral da janela de observacoes', group)
        _keys(group, 'rotation_euler', [(t(start), (0, 0, -.075)),
                                       (t(start+1.4), (0, 0, .025)),
                                       (t(end-.15), (0, 0, .075))])
        _keys(group, 'location', [(t(start), (.25, .22, .1)),
                                 (t(start+1.2), (0, 0, 0)),
                                 (t(end-.15), (-.12, -.12, .03))])
    # Two independently trained monthly networks now contain data and distinct
    # output counts instead of indistinguishable empty boxes.
    for row, (z, outputs) in enumerate(((3.3, 1), (2.2, 6))):
        for i in range(6):
            _show(box(f'V4 tarefa mensal {row} entrada {i}',
                      (-3.65+i*.37, -.12, z+.09*math.sin(i*1.4)),
                      (.12, .18, .16+.09*(i % 3)), white, .022),
                  t(26.15+i*.06), duration, 'amostras de entrada ilustrativas')
        for layer in range(2):
            for j in range(2):
                p = (-.48+layer*.35, -.12+layer*.20, z-.18+j*.36)
                _show(sphere(f'V4 rede mensal independente {row} no {layer} {j}',
                             p, .060, secondary), t(26.5), duration,
                      'rede mensal treinada separadamente')
        for i in range(outputs):
            x = 2.2 if outputs == 1 else 1.25+i*.43
            token = _show(box(f'V4 tarefa mensal {row} saida {i+1}', (x, -.12, z),
                              (.18, .24, .20), gold, .025),
                          t(27.2+i*.18), duration, 'um componente do vetor de saida da tarefa mensal')
            token['output_count_for_task'] = outputs
        _particle(f'processamento rede mensal independente {row}',
                  [(-3.7, -.18, z), (-1, -.18, z), (.2, -.18, z), (2.2, -.18, z)],
                  [t(27.0), t(28.5), t(29.4), t(31.0)], gold, .050)
    camera = _rail(scene, [
        (0, (-4.4, -11.8, 5.2), (0, 0, 1.7), 42),
        (4.8, (2.3, -12.1, 4.9), (0, 0, 2.35), 42),
        (6.4, (2.7, -12.0, 5.0), (0, 0, 2.65), 42),
        (10.6, (-1.8, -12.3, 4.7), (0, 0, 2.55), 42),
        (12.2, (-2.5, -12.1, 5.0), (0, 0, 2.55), 42),
        (15.7, (1.5, -12.4, 4.6), (0, 0, 2.55), 42),
        (17.3, (2.4, -9.8, 4.8), (-.45, 0, 2.55), 44),
        (20.6, (-1.5, -9.9, 4.7), (-.45, 0, 2.55), 44),
        (22.2, (-2.2, -12.1, 5.0), (0, 0, 2.55), 42),
        (25.7, (1.4, -12.0, 4.6), (0, 0, 2.55), 42),
        (27.1, (3.0, -11.9, 4.8), (0, 0, 2.5), 42),
        (35, (-2.0, -11.8, 4.6), (0, 0, 2.4), 42),
    ], t)
    return {'source': base, 'camera': camera, 'phases': [
        [t(0), t(5), 'quatro historias volumetricas introdutorias'],
        [t(5), t(11), '336 horas para 72 horas'],
        [t(11), t(16), '365 dias para 30 dias'],
        [t(16), t(21), '12 meses para um mes'],
        [t(21), t(26), '12 meses para seis meses, exploratoria'],
        [t(26), duration, 'duas redes mensais e vetores de 1 versus 6 saidas']],
        'monthly_networks_independently_trained': True,
        'curves_and_amplitudes_are_illustrative': True,
        'blank_intro_replaced': True, 'output_counts': [1, 6]}


def _protocol(scene, duration):
    from director_v3 import evaluation_v3
    before = set(bpy.data.objects)
    base = evaluation_v3()
    legacy = set(bpy.data.objects)-before
    factor = duration/40.
    _retime(legacy, factor)
    t = lambda second: second*factor
    _harmonize(legacy, 6)
    for obj in legacy:
        if _plain(obj.name).startswith('periodo cronologico ') and obj.type == 'MESH':
            _constant_visibility(obj)
    white = _mat('protocol observations', 'white')
    gold = _mat('protocol fixed selected configuration', 'gold')
    neutral = _mat('protocol rail', 'axes')
    sample_mat = _mat('protocol observation volumes', '#626D7A', False)
    stage_info = [(-3.7, 0, 4, (2019, 2020, 2021, 2022)),
                  (.1, 7, 1, (2023,)), (3.6, 13, 1, (2024,))]
    for stage, (x, start, years, actual_years) in enumerate(stage_info):
        for year in range(years):
            cx = x+(year-(years-1)/2)*.55
            for layer in range(2):
                for row in range(3):
                    p = (cx, -.10+layer*.21, 2.04+row*.24)
                    token = _show(box(f'V4 periodo {stage} ano {actual_years[year]} dado {layer} {row}',
                                      p, (.29 if years == 4 else .40, .16, .17),
                                      sample_mat, .027), t(start+.2+year*.1+row*.08), duration,
                                  'amostras abstratas do periodo cronologico; sem contagem real')
                    token['calendar_year'] = actual_years[year]
                    token['stage'] = ('initial_fit', 'validation', 'retrospective_test')[stage]
        _trace(f'periodo {stage} fluxo interno',
               [(x-.65, -.24, 2.2), (x, -.24, 2.5), (x+.65, -.24, 2.18)], white,
               t(start+.6), duration, t(.9), .014)
    # The rail indicates chronological ordering, not training on test targets.
    _trace('trajeto cronologico em profundidade',
           [(-4.9, .28, 1.55), (-2.2, .10, 1.55), (.1, .35, 1.55),
            (2.0, .10, 1.55), (4.8, .28, 1.55)], neutral,
           t(0), duration, t(2.0), .027)
    for i in range(10):
        x = -4.50+i*.55
        token = _show(box(f'V4 novo ajuste dados 2019 a 2023 {i}',
                          (x, -.02+(i % 2)*.12, 3.29), (.23, .18, .23), white, .025),
                      t(24.3+i*.08), duration, 'dados de 2019 a 2023 no novo ajuste')
        token['test_targets_included'] = False
    for i, (a, b) in enumerate((((-3.7, -.12, 2.5), (-2.7, -.12, 3.3)),
                                ((.1, -.12, 2.5), (-1.0, -.12, 3.3)))):
        path = _arc(a, b, .20, -.1)
        _trace(f'dados anteriores entram no novo ajuste {i}', path, white,
               t(24.0+i*.3), t(29), t(1.3), .014)
        _particle(f'pacote para novo ajuste {i}', [path[0], path[12], path[-1]],
                  [t(24.5+i*.3), t(25.5+i*.3), t(26.5+i*.3)], gold, .050)
    evaluation_path = _arc((-1.0, -.15, 3.3), (3.6, -.15, 2.92), .32, -.16)
    _trace('configuracao fixada segue para avaliacao de 2024', evaluation_path,
           gold, t(28.3), duration, t(1.4), .017)
    _particle('configuracao na avaliacao retrospectiva',
              [evaluation_path[0], evaluation_path[12], evaluation_path[-1]],
              [t(28.8), t(30.3), t(31.8)], gold, .065)
    # A quiet enclosing arc accompanies the explicit prior-exposure caveat;
    # there is intentionally no arrow feeding test targets back into fitting.
    caution = []
    for i in range(40):
        u = i/39
        caution.append((-4.9+9.8*u, .40, 3.8+.35*math.sin(math.pi*u)))
    _trace('escopo da interpretacao retrospectiva', caution, neutral,
           t(34.5), duration, t(1.8), .012)
    camera = _rail(scene, [
        (0, (-5.2, -3.8, 3.5), (-3.7, 0, 2.05), 44),
        (6.3, (-3.4, -7.5, 4.5), (-2.3, 0, 2.05), 42),
        (8.2, (-.75, -3.6, 3.4), (.1, 0, 2.3), 44),
        (12.5, (1.1, -7.8, 4.0), (.7, 0, 2.0), 42),
        (15.8, (4.9, -3.5, 3.6), (3.6, 0, 2.3), 44),
        (19.7, (-.6, -3.3, 3.6), (.1, 0, 2.15), 46),
        (23.4, (-.8, -8.3, 4.5), (-.7, 0, 2.5), 42),
        (26.5, (-3.0, -7.6, 5.5), (-1.8, 0, 2.9), 44),
        (29.8, (.6, -8.2, 4.6), (1.4, 0, 2.55), 42),
        (33.8, (5.5, -7.1, 4.3), (3.4, 0, 2.2), 44),
        (40, (1.2, -12.4, 5.2), (0, 0, 2.3), 42),
    ], t)
    return {'source': base, 'camera': camera, 'phases': [
        [t(0), t(7), 'ajuste inicial 2019 a 2022'],
        [t(7), t(13), 'validacao em 2023'],
        [t(13), t(19), 'teste retrospectivo 2024 no protocolo'],
        [t(19), t(24), 'selecao pela validacao'],
        [t(24), t(29), 'novo ajuste 2019 a 2023'],
        [t(29), t(34.5), 'configuracao fixa avaliada em 2024'],
        [t(34.5), duration, 'exposicao anterior e interpretacao retrospectiva']],
        'test_targets_enter_refit': False, 'prior_exposure_caveat_required': True,
        'dataset_blocks_are_abstract': True}


def build_story_v4(chapter_id, duration, scene):
    """API do montador V4. Acrescentar a cena, dirigir camera e devolver JSON."""
    chapter_id = int(chapter_id)
    duration = float(duration)
    if chapter_id not in REFERENCE_DURATIONS:
        raise ValueError('scenes_story_v4 implementa somente capitulos 2 a 6')
    if duration <= 0:
        raise ValueError('duration deve ser positiva')
    before = set(bpy.data.objects)
    builders = {2: _factory, 3: _objective, 4: _map, 5: _tasks, 6: _protocol}
    info = builders[chapter_id](scene, duration)
    created = set(bpy.data.objects)-before
    _harmonize(created, chapter_id)
    for obj in created:
        obj['ea019_v4_chapter'] = chapter_id
    scene.frame_set(1)
    return {'version': 4, 'chapter_id': chapter_id, 'duration_seconds': duration,
            'fps': FPS, 'frame_count': round(duration*FPS),
            'projection': 'PERSP', 'static_frontal_camera': False,
            'native_text_objects': 0, 'palette_srgb': dict(PALETTE),
            'objects_created': len(created), 'objects': sorted(obj.name for obj in created),
            'render_started': False, **info}
