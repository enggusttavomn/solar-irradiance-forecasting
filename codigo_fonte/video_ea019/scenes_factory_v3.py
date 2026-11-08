"""Maquete industrial, irradiancia horizontal e ponte para a serie temporal.

Cena ilustrativa de 35 s. Nao representa uma unidade industrial real, um
sensor, uma instalacao fotovoltaica nem um resultado experimental. Os textos
da composicao final pertencem ao montador; sugestoes sao retornadas em JSON.
Este modulo acrescenta objetos a cena atual e configura sua camera existente.
"""

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_pilot import box, emission, polyline, reveal, sphere, surface, visible


FPS = 30
PALETTE = {
    'background': '#07090D', 'factory': '#171C22',
    'white': '#F3F5F7', 'secondary': '#A9B2BE',
    'gold': '#E9B95F', 'coral': '#F28779',
    'cyan': '#58CADA', 'violet': '#AA91E8', 'axes': '#626D7A',
}


def _rgba(hex_color):
    """Converter uma cor sRGB de projeto para o RGB linear do Blender."""
    channels = [int(hex_color.lstrip('#')[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
                 for c in channels) + (1.,)


def _frame(seconds):
    return round(float(seconds)*FPS)+1


def _material(name, color, luminous=False, strength=1.):
    rgba = _rgba(color)
    material = (emission(name, rgba, strength) if luminous else
                surface(name, rgba, metallic=0, roughness=.91))
    # Workbench reads diffuse_color rather than the node graph.
    material.diffuse_color = rgba
    material['design_srgb_hex'] = color
    return material


def _empty(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    return obj


def _linear_keys(obj, path):
    animation = obj.animation_data
    if animation and animation.action:
        for curve in animation.action.fcurves:
            if curve.data_path == path:
                for key in curve.keyframe_points:
                    key.interpolation = 'LINEAR'


def _register(obj, parent, start, end, meaning):
    obj.parent = parent
    obj['meaning'] = meaning
    visible(obj, start, end)
    return obj


def _arrow(name, start, end, material, parent, start_seconds, end_seconds,
           radius=.012, tip=.10, animate_for=.8):
    a, b = Vector(start), Vector(end)
    direction = (b-a).normalized()
    side = direction.cross(Vector((0, 1, 0)))
    if side.length < .001:
        side = direction.cross(Vector((1, 0, 0)))
    side.normalize()
    shaft = _register(polyline(name+' haste', [a, b], material, radius),
                      parent, start_seconds, end_seconds,
                      'direcao ilustrativa de incidencia da radiacao')
    reveal(shaft, start_seconds, animate_for)
    for sign in (-1, 1):
        head = polyline(name+f' ponta {sign:+d}',
                        [b-direction*tip+side*tip*.48*sign, b],
                        material, radius)
        _register(head, parent, start_seconds+animate_for*.75, end_seconds,
                  'ponta da seta de incidencia')
    return shaft


def _camera(scene, timing):
    cam = scene.camera
    if cam is None:
        bpy.ops.object.camera_add()
        cam = bpy.context.object
        scene.camera = cam
    cam.name = 'Camera GHI maquete e serie temporal'
    cam.animation_data_clear()
    cam.data.animation_data_clear()
    cam.data.type = 'ORTHO'
    cam.data.clip_start = .05
    cam.data.clip_end = 250
    # ortho_scale is the horizontal field of view for a 16:9 output.
    shots = [
        (0, (7.8, -12.2, 8.3), (-.3, .1, .60), 13.4),
        (3.8, (7.45, -12.25, 8.45), (-.2, .1, .65), 13.2),
        (6.5, (5.1, -9.4, 8.1), (.35, -.06, 1.82), 6.4),
        (11.9, (5.1, -9.4, 8.1), (.35, -.06, 1.82), 6.4),
        (13.0, (5.4, -10.1, 8.1), (.15, .1, 2.15), 11.0),
        (17.0, (5.4, -10.1, 8.1), (.15, .1, 2.15), 11.0),
        (19.0, (5.8, -10.3, 8.0), (-.2, .12, 1.8), 13.5),
        (23.966666667, (5.8, -10.3, 8.0), (-.2, .12, 1.8), 13.5),
        (24.0, (0, -16, 5.1), (0, 0, 1.9), 10.9),
        (35.0, (0, -16, 5.1), (0, 0, 1.9), 10.9),
    ]
    for seconds, location, target, scale in shots:
        cam.location = location
        cam.rotation_euler = (Vector(target)-cam.location).to_track_quat('-Z', 'Y').to_euler()
        cam.data.ortho_scale = scale
        # Leave the right column free for 40 px explanatory labels.
        cam.data.shift_x = .20 if seconds < 24 else 0.
        cam.keyframe_insert('location', frame=_frame(timing(seconds)))
        cam.keyframe_insert('rotation_euler', frame=_frame(timing(seconds)))
        cam.data.keyframe_insert('ortho_scale', frame=_frame(timing(seconds)))
        cam.data.keyframe_insert('shift_x', frame=_frame(timing(seconds)))
    # A one-frame cut at 24 s avoids an orbit through the illustration.
    for owner in (cam, cam.data):
        animation = owner.animation_data
        if animation and animation.action:
            for curve in animation.action.fcurves:
                for key in curve.keyframe_points:
                    key.interpolation = 'BEZIER'
                    key.handle_left_type = 'AUTO_CLAMPED'
                    key.handle_right_type = 'AUTO_CLAMPED'
    return cam


def _neutral_lighting(scene):
    if scene.world:
        scene.world.color = _rgba(PALETTE['background'])[:3]
        if scene.world.use_nodes:
            node = scene.world.node_tree.nodes.get('Background')
            if node:
                node.inputs['Color'].default_value = _rgba(PALETTE['background'])
                node.inputs['Strength'].default_value = .35
    # Replace inherited orange/cyan lamps with neutral, broad soft sources.
    lamps = [obj for obj in scene.objects if obj.type == 'LIGHT']
    for i, lamp in enumerate(lamps):
        lamp.data.color = (1, 1, 1)
        lamp.data.energy = 1000 if i == 0 else 480
        if lamp.data.type == 'AREA':
            lamp.data.size = 8
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1


def build_factory(duration=35):
    """Criar o capitulo e retornar metadados serializaveis.

    Tempos locais conforme P08-P14: 0-4 maquete; 4-9 area no telhado;
    9-12 W/m2; 12-17 direta/difusa; 17-24 padroes; 24-30 curva;
    30-35 janela de historico e futuro ainda desconhecido. ``duration``
    redimensiona proporcionalmente todos os tempos. Nao inicia renderizacao.
    """
    duration = float(duration)
    if duration <= 0:
        raise ValueError('duration deve ser positiva')
    t = lambda seconds: float(seconds)*duration/35.
    before = {obj.name for obj in bpy.data.objects}
    scene = bpy.context.scene
    _neutral_lighting(scene)
    camera = _camera(scene, t)

    graphite = _material('Maquete grafite fosco', PALETTE['factory'])
    roof_mat = _material('Telhado horizontal grafite', '#252D36')
    trim = _material('Detalhes neutros da fachada', '#46515D')
    window = _material('Janelas neutras sem reflexo', '#778592')
    ground_mat = _material('Base neutra sem grade', PALETTE['background'])
    gold_fill = _material('Area horizontal de 1 metro quadrado', PALETTE['gold'])
    gold = _material('Radiacao solar dourada', PALETTE['gold'], True, 1.1)
    diffuse = _material('Radiacao difusa dourada suave', '#D6BD8E', True, .8)
    white = _material('Historico de GHI branco', PALETTE['white'], True, 1)
    axis_mat = _material('Eixos da serie temporal', PALETTE['axes'], True, .8)
    secondary = _material('Marcadores neutros da serie', PALETTE['secondary'], True, .8)
    cloud_mat = _material('Nuvem ilustrativa neutra', '#87919D')

    factory = _empty('Maquete industrial ilustrativa - conjunto')
    factory['meaning'] = 'contexto industrial ilustrativo, sem vinculo com unidade real'
    factory['not_a_photovoltaic_system'] = True
    end_factory = t(24)
    def factory_obj(obj, meaning, start=0):
        return _register(obj, factory, t(start), end_factory, meaning)

    # A restrained plinth anchors the building; there is no grid or sheen.
    factory_obj(box('Base lisa da maquete', (-.4, 0, -.11),
                    (7.6, 5.1, .16), ground_mat, .05), 'base lisa da maquete')
    factory_obj(box('Galpao industrial principal', (-.4, 0, .88),
                    (5.4, 3.1, 1.76), graphite, .075), 'galpao industrial ilustrativo')
    factory_obj(box('Cobertura plana horizontal do galpao', (-.4, 0, 1.82),
                    (5.55, 3.26, .12), roof_mat, .035), 'telhado plano horizontal')
    factory_obj(box('Anexo administrativo', (-2.64, -1.62, .55),
                    (1.32, 1.02, 1.10), graphite, .055), 'anexo da maquete')
    factory_obj(box('Cobertura do anexo', (-2.64, -1.62, 1.12),
                    (1.39, 1.09, .07), roof_mat, .02), 'cobertura simples do anexo')
    # Facade panels, loading doors and shallow frames remain schematic.
    for i, x in enumerate((-.85, .50, 1.85)):
        factory_obj(box(f'Porta de acesso do galpao {i+1}', (x, -1.564, .56),
                        (.91, .027, 1.11), trim, .018), 'porta de acesso ilustrativa')
        factory_obj(box(f'Marquise da porta {i+1}', (x, -1.65, 1.17),
                        (1.04, .30, .055), roof_mat, .015), 'marquise da fachada')
    for i, x in enumerate((-1.25, -.42, .41, 1.24, 2.07)):
        factory_obj(box(f'Janela alta fachada {i+1}', (x, -1.566, 1.48),
                        (.55, .024, .20), window, .012), 'janela alta da fachada')
    for i, y in enumerate((-.85, 0, .85)):
        factory_obj(box(f'Janela lateral {i+1}', (2.314, y, 1.31),
                        (.025, .53, .27), window, .012), 'janela lateral')
    for i, x in enumerate((-2.96, -2.34)):
        factory_obj(box(f'Janela do anexo {i+1}', (x, -2.144, .76),
                        (.40, .025, .28), window, .012), 'janela do anexo')
    factory_obj(box('Entrada administrativa', (-2.63, -2.145, .31),
                    (.34, .028, .60), trim, .016), 'entrada do anexo')

    patch_center = Vector((.55, -.12, 1.889))
    patch = factory_obj(box('Referencia horizontal de exatamente 1 m2', patch_center,
                            (1., 1., .012), gold_fill, .004),
                        'area horizontal destacada para definir irradiancia', 4.3)
    patch['area_m2'] = 1.0
    patch['horizontal'] = True
    patch['not_a_sensor'] = True
    # Two dimension brackets reinforce that the highlighted square is an area.
    z = patch_center.z+.018
    for name, a, b, side in [
            ('largura', (.05, -.80, z), (1.05, -.80, z), (0, .07, 0)),
            ('profundidade', (1.23, -.62, z), (1.23, .38, z), (.07, 0, 0))]:
        a, b, side = Vector(a), Vector(b), Vector(side)
        bracket = polyline('Dimensao de um metro '+name, [a, b], gold, .008)
        factory_obj(bracket, 'dimensao de um metro da area de referencia', 6.0)
        reveal(bracket, t(6.0), t(.8))
        for k, point in enumerate((a, b)):
            factory_obj(polyline(f'Terminal dimensao {name} {k}',
                                 [point-side, point+side], gold, .008),
                        'terminal de cota da area de referencia', 6.7)

    # All direct rays have the same vector; the receiving plane is horizontal.
    ray_offset = Vector((-1.55, .45, 1.70))
    for i, (dx, dy) in enumerate(((-.33, -.28), (.0, -.28), (.33, -.28),
                                (-.33, .19), (.0, .19), (.33, .19))):
        end = patch_center+Vector((dx, dy, .025))
        _arrow(f'Feixe direto paralelo {i+1}', end+ray_offset, end, gold,
               factory, t(12.1+i*.08), t(18.0), .011, .12, t(.9))
    sun = factory_obj(sphere('Sol ilustrativo', patch_center+ray_offset*1.13,
                             .225, gold), 'fonte solar ilustrativa', 12.0)
    sun['illustrative_only'] = True
    visible(sun, t(12.0), t(17.0))
    # A compact neutral cloud gives visual context for scattering, not an input.
    cloud_center = Vector((1.85, .56, 3.72))
    for i, (offset, radius, scale) in enumerate([
            ((-.40, 0, -.08), .31, (1.0, .64, .75)),
            ((-.12, .03, .10), .40, (1.0, .72, .76)),
            ((.26, .02, -.01), .35, (1.0, .70, .72)),
            ((.52, .02, -.10), .25, (1.0, .68, .72))]):
        cloud = factory_obj(sphere(f'Nuvem ilustrativa volume {i+1}', cloud_center+Vector(offset),
                           radius, cloud_mat, scale),
                    'variacao atmosferica ilustrativa; nao e entrada do modelo', 17.3)
        for seconds, delta in ((17.3, (-1.35, 0, 0)), (22.5, (.3, 0, -.08))):
            cloud.location = cloud_center+Vector(offset)+Vector(delta)
            cloud.keyframe_insert('location', frame=_frame(t(seconds)))
    # Diffuse paths arrive from distinct sky directions, not just the cloud.
    diffuse_starts = [(-1.10, 1.5, 3.48), (2.34, .35, 3.24), (.50, -2.05, 3.38)]
    diffuse_ends = [(.24, .14, 1.92), (.85, .12, 1.92), (.63, -.40, 1.92)]
    for i, (a, b) in enumerate(zip(diffuse_starts, diffuse_ends)):
        _arrow(f'Componente difusa direcao {i+1}', a, b, diffuse, factory,
               t(14.0+i*.2), t(18.0), .010, .12, t(.85))

    # The solar arc is symbolic: it does not simulate a site, date or season.
    arc_points = []
    for i in range(41):
        angle = math.radians(24+130*i/40)
        arc_points.append((.15-2.55*math.cos(angle), .6,
                           2.0+2.10*math.sin(angle)))
    arc = factory_obj(polyline('Arco solar simbolico', arc_points, diffuse, .009),
                      'arco simbolico de padroes diarios e sazonais', 17.2)
    reveal(arc, t(17.2), t(1.3))
    moving_sun = factory_obj(sphere('Marcador do arco solar', arc_points[0], .13, gold),
                             'marcador de geometria solar, nao simulacao fisica', 17.4)
    for i in (0, 10, 20, 30, 40):
        moving_sun.location = arc_points[i]
        moving_sun.keyframe_insert('location', frame=_frame(t(17.4+i/40*5.3)))

    # Camera-facing lateral inset stays clear of the roof and caption strip.
    inset = _empty('Curva lateral conceitual - conjunto')
    inset.parent = camera
    # Compensate the 0.20 horizontal camera shift at ortho_scale 13.5.
    inset.location.x = 2.7
    inset['meaning'] = 'curva meramente conceitual, nao resultado experimental'
    inset_axis = polyline('Base da curva lateral',
                          [(1.0, -.65, -10), (4.25, -.65, -10)], axis_mat, .008)
    _register(inset_axis, inset, t(18.6), end_factory, 'eixo lateral ilustrativo')
    mini_points = []
    for i in range(85):
        u = i/84
        y = -.56+1.15*max(0, math.sin(2.6*math.pi*u))
        y -= .30*math.exp(-((u-.55)/.045)**2)
        mini_points.append((1.08+3.05*u, y, -9.98))
    mini = _register(polyline('Curva lateral de variacao atmosferica', mini_points, white, .016),
                     inset, t(18.8), end_factory, 'variacao temporal conceitual')
    reveal(mini, t(18.8), t(3.3))
    # One parent moves the entire factory coherently to accommodate the inset.
    for seconds, loc, scale in [(17.0, (0, 0, 0), 1.), (18.7, (-.7, .1, .1), .76),
                                (23.3, (-.7, .1, .1), .76),
                                (24.0, (-1.2, .1, .1), .001)]:
        factory.location = loc
        factory.scale = (scale,)*3
        factory.keyframe_insert('location', frame=_frame(t(seconds)))
        factory.keyframe_insert('scale', frame=_frame(t(seconds)))

    graph = _empty('Ponte para historico e futuro - conjunto')
    graph['meaning'] = 'serie temporal didatica de GHI, sem numeros experimentais'
    graph_start = t(24)
    graph_end = duration+.05
    def graph_obj(obj, meaning, start=24):
        return _register(obj, graph, t(start), graph_end, meaning)

    for name, points in [
            ('Eixo temporal', [(-4.25, 0, .52), (4.25, 0, .52)]),
            ('Eixo irradiancia', [(-4.25, 0, .52), (-4.25, 0, 3.25)])]:
        axis = graph_obj(polyline(name, points, axis_mat, .009), 'eixo conceitual sem escala numerica')
        reveal(axis, graph_start, t(.8))
    for i in range(9):
        x = -4.15+i
        graph_obj(polyline(f'Marca temporal {i+1}', [(x, 0, .46), (x, 0, .58)],
                           axis_mat, .007), 'marca do eixo temporal')
    points = []
    for i in range(150):
        u = i/149
        x = -4.15+4.90*u
        phase = (u*2.95+.10) % 1
        daylight = max(0., math.sin(math.pi*(phase-.12)/.76)) if .12 <= phase <= .88 else 0.
        cloud = 1-.20*math.exp(-((u-.49)/.045)**2)-.12*math.exp(-((u-.77)/.025)**2)
        points.append((x, -.02, .68+2.08*daylight*cloud))
    history = graph_obj(polyline('Historico ilustrativo de GHI', points, white, .022),
                        'curva de historico meramente ilustrativa')
    reveal(history, t(24.5), t(3.6))
    marker = graph_obj(polyline('Limite entre historico e futuro',
                                [(.75, -.04, .52), (.75, -.04, 3.22)],
                                secondary, .013), 'instante presente separando passado e futuro', 28.0)
    reveal(marker, t(28), t(.6))
    graph_obj(sphere('Amostra mais recente', points[-1], .057, white),
              'ultima observacao do historico ilustrativo', 28.0)
    # An empty dashed region and a question mark keep future values unknown.
    rectangle = [(1.02, -.02, .75), (4.15, -.02, .75),
                 (4.15, -.02, 3.02), (1.02, -.02, 3.02), (1.02, -.02, .75)]
    for edge_idx, (a, b) in enumerate(zip(rectangle[:-1], rectangle[1:])):
        a, b = Vector(a), Vector(b)
        count = max(2, round((b-a).length/.24))
        for i in range(count):
            p = a.lerp(b, i/count)
            q = a.lerp(b, (i+.53)/count)
            graph_obj(polyline(f'Regiao futura vazia {edge_idx} traco {i}',
                               [p, q], secondary, .008),
                      'contorno neutro do futuro sem valores previstos', 28.6)
    question = [(2.25, -.04, 2.40), (2.38, -.04, 2.56),
                (2.72, -.04, 2.57), (2.90, -.04, 2.40),
                (2.88, -.04, 2.17), (2.61, -.04, 1.96), (2.58, -.04, 1.68)]
    graph_obj(polyline('Interrogacao do futuro desconhecido', question, secondary, .027),
              'futuro desconhecido, sem curva de previsao', 28.6)
    graph_obj(sphere('Ponto da interrogacao', (2.58, -.04, 1.40), .042, secondary),
              'pontuacao da interrogacao', 28.6)
    history_frame = graph_obj(polyline('Janela ilustrativa do historico',
                                       [(-3.95, -.04, .67), (.40, -.04, .67),
                                        (.40, -.04, 3.02), (-3.95, -.04, 3.02)],
                                       secondary, .014, cyclic=True),
                              'janela de historico sem tamanho experimental especifico', 30.2)
    reveal(history_frame, t(30.2), t(.9))
    _arrow('Ligacao historico para pergunta futura', (.45, -.04, 1.66),
           (1.50, -.04, 1.66), secondary, graph, t(31.2), graph_end,
           .012, .13, t(.75))
    # A small neutral cursor travels across available observations only.
    cursor = graph_obj(sphere('Cursor de leitura do historico', points[0], .045, secondary),
                       'leitura sequencial das observacoes do historico', 24.5)
    for i in (0, 25, 50, 75, 100, 125, 149):
        cursor.location = points[i]
        cursor.keyframe_insert('location', frame=_frame(t(24.5+i/149*3.6)))
    _linear_keys(cursor, 'location')
    visible(cursor, t(24.5), t(28.3))

    scene.frame_set(1)
    objects = [obj.name for obj in bpy.data.objects if obj.name not in before]
    return {
        'version': 3, 'builder': 'build_factory', 'duration_seconds': duration,
        'fps': FPS, 'frame_count': round(duration*FPS), 'camera': camera.name,
        'palette_srgb': dict(PALETTE), 'materials_use_linear_rgb': True,
        'reference_area_m2': 1.0, 'reference_surface': 'horizontal roof',
        'illustrative_factory': True, 'illustrative_time_series': True,
        'no_grid': True, 'no_photovoltaic_panels': True, 'no_future_values': True,
        'shotphases': [
            {'id': 'P08', 'start': t(0), 'end': t(4), 'meaning': 'maquete industrial em vista obliqua'},
            {'id': 'P09', 'start': t(4), 'end': t(9), 'meaning': 'zoom da area horizontal de um metro quadrado no telhado'},
            {'id': 'P10', 'start': t(9), 'end': t(12), 'meaning': 'potencia por unidade de area em W/m2'},
            {'id': 'P11', 'start': t(12), 'end': t(17), 'meaning': 'radiacao direta obliqua mais difusa de varias direcoes'},
            {'id': 'P12', 'start': t(17), 'end': t(24), 'meaning': 'padroes solares e variacao atmosferica, curva lateral'},
            {'id': 'P13', 'start': t(24), 'end': t(30), 'meaning': 'historico disponivel e futuro ainda sem valores'},
            {'id': 'P14', 'start': t(30), 'end': t(35), 'meaning': 'janela ilustrativa do historico e pergunta futura'},
        ],
        'on_screen_suggestions': [
            {'start': t(.2), 'end': t(3.9), 'text': 'Irradiância global horizontal — GHI', 'x': 960, 'y': 220},
            {'start': t(5.0), 'end': t(8.9), 'text': 'Superfície horizontal', 'x': 1430, 'y': 340},
            {'start': t(6.2), 'end': t(8.9), 'text': 'Área de referência: 1 m²', 'x': 1390, 'y': 410},
            {'start': t(9.1), 'end': t(11.9), 'text': 'W/m²', 'x': 1450, 'y': 340},
            {'start': t(9.3), 'end': t(11.9), 'text': 'Potência por unidade de área', 'x': 1400, 'y': 410},
            {'start': t(12.7), 'end': t(16.9), 'text': 'Direta sobre a horizontal', 'x': 470, 'y': 290},
            {'start': t(14.6), 'end': t(16.9), 'text': 'Difusa do céu', 'x': 1470, 'y': 290},
            {'start': t(17.6), 'end': t(23.8), 'text': 'Padrões diários e sazonais', 'x': 1280, 'y': 300},
            {'start': t(19.0), 'end': t(23.8), 'text': 'Variação atmosférica', 'x': 1280, 'y': 730},
            {'start': t(25.0), 'end': t(29.9), 'text': 'Histórico de GHI', 'x': 510, 'y': 270},
            {'start': t(28.1), 'end': t(29.9), 'text': 'Presente', 'x': 1090, 'y': 270},
            {'start': t(28.7), 'end': t(29.9), 'text': 'Futuro a prever', 'x': 1455, 'y': 270},
            {'start': t(30.1), 'end': t(34.8), 'text': 'Quanto conseguimos antecipar?', 'x': 960, 'y': 220},
            {'start': t(30.3), 'end': t(34.8), 'text': 'Histórico', 'x': 510, 'y': 290},
            {'start': t(30.3), 'end': t(34.8), 'text': 'Futuro', 'x': 1455, 'y': 290},
            {'start': t(.2), 'end': t(34.8), 'text': 'Ilustração conceitual', 'x': 960, 'y': 800},
        ],
        'caption_safe_area': {'x_min': 120, 'x_max': 1800, 'y_min': 850, 'y_max': 1000},
        'objects': objects,
    }
