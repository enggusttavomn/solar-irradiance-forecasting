"""Audited 2024 comparisons as front-facing, zero-based native 3D objects.

Local 0-88 s, global 388-476 s. The V7 prefix is never loaded or modified.
All numbers, choices, local leaders and horizon leaders come from the compact
audited JSON assembled directly from the frozen experiment CSVs.
"""
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from common_v7 import (ROOT, WHITE, CYAN, CORAL, VIOLET, frame, box, sphere,
                       polyline, surface, emission, visible, reveal, keys,
                       label, camera_key, grow)

OUT = ROOT / 'documentacao/relatorio_final_ea019/video/completo_v8'
DATA = OUT / 'fontes_resultados_v8.json'
ASSETS = Path(__file__).resolve().parent / 'assets'
MODELS = ('Transformer', 'Informer', 'LSTM')
COLORS = {'Transformer': CYAN, 'Informer': VIOLET, 'LSTM': CORAL}
TASKS = [('hourly_72_extension', 7., 24., 150., 'Horária · até 72 horas'),
         ('daily_30', 24., 40., 50., 'Diária · até 30 dias'),
         ('monthly_1', 40., 54., 16., 'Mensal · um mês'),
         ('monthly_6', 54., 68., 16., 'Mensal · até seis meses')]
DURATION = 88


def _show(obj, start, end):
    visible(obj, start, end)
    return obj


def _text(name, text, position, size, material, start, end):
    return label('V8 results ' + name, text, position, size, material, start, end)


def _line(name, points, material, start, end, radius=.012, draw=.7):
    obj = polyline('V8 results ' + name, points, material, radius)
    visible(obj, start, end)
    reveal(obj, start, draw)
    return obj


def _pbr(name, color, roughness=.66, metal=.04):
    material = surface('V8 results '+name, color, metal, roughness)
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Emission Color'].default_value = color
    shader.inputs['Emission Strength'].default_value = .025
    return material


def _bar(name, location, material, start, end):
    """Length shape key moves the endpoint; bevel radii never get stretched."""
    depth, height = .42, .57
    vertices = [(0, -depth/2, -height/2), (0, -depth/2, -height/2),
                (0, depth/2, -height/2), (0, depth/2, -height/2),
                (0, -depth/2, height/2), (0, -depth/2, height/2),
                (0, depth/2, height/2), (0, depth/2, height/2)]
    faces = [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
             (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)]
    mesh = bpy.data.meshes.new(name+' mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    obj.shape_key_add(name='Zero length at common origin')
    length = obj.shape_key_add(name='Actual normalised MAE length')
    length.slider_max = 10
    for index in (1, 2, 5, 6):
        length.data[index].co.x = 1
    bevel = obj.modifiers.new('Constant small physical edge radius', 'BEVEL')
    bevel.width = .055
    bevel.segments = 3
    obj.modifiers.new('Weighted matte surface normals', 'WEIGHTED_NORMAL')
    visible(obj, start, end)
    return obj, length


def _shape_keys(owner, values):
    for second, value in values:
        owner.value = value
        owner.keyframe_insert('value', frame=frame(second))


def _project(lon, lat, depth=0):
    return ((lon+100.)*.045-1., depth, 4.20+(lat-9.)*.045)


def _map_land(coast, material, edge, start, end):
    objects = []
    for index, ring in enumerate(coast['rings']):
        if not ring['outer']:
            continue
        coords = ring['coordinates']
        vectors = [Vector((float(lon), float(lat), 0)) for lon, lat in coords]
        lookup = {tuple(v): i for i, v in enumerate(vectors)}
        faces = [tuple(v if isinstance(v, int) else lookup[tuple(v)] for v in triangle)
                 for triangle in tessellate_polygon([vectors])]
        mesh = bpy.data.meshes.new('V8 actual map land '+str(index))
        mesh.from_pydata([_project(lon, lat, .10) for lon, lat in coords], [], faces)
        mesh.materials.append(material)
        mesh.update()
        obj = bpy.data.objects.new('V8 Natural Earth land '+str(index), mesh)
        bpy.context.scene.collection.objects.link(obj)
        solid = obj.modifiers.new('Shallow geographic relief', 'SOLIDIFY')
        solid.thickness = .075
        objects.append(_show(obj, start, end))
        line = polyline('V8 Natural Earth coastline '+str(index),
                        [_project(lon, lat, .045) for lon, lat in coords], edge, .0045, cyclic=True)
        objects.append(_show(line, start, end))
    return objects


def _factory(name, location, size, roof, white, glass, dark, start=68, end=80):
    x, y, z = location
    for part, pos, dims, mat in [
        ('hall', (x, y, z+size*.27), (size, size*.40, size*.44), white),
        ('roof', (x, y-.01, z+size*.51), (size*1.05, size*.45, size*.07), roof),
        ('glazing', (x, y-size*.21, z+size*.34), (size*.78, size*.025, size*.12), glass),
        ('door', (x-size*.27, y-size*.23, z+size*.15), (size*.18, size*.025, size*.23), dark),
        ('vent', (x+size*.18, y, z+size*.58), (size*.21, size*.17, size*.10), dark)]:
        _show(box(name+' '+part, pos, dims, mat, size*.018), start, end)


def _set_material_colors(material, values):
    shader = material.node_tree.nodes.get('Principled BSDF')
    for second, model in values:
        if shader:
            shader.inputs['Base Color'].default_value = COLORS[model]
            shader.inputs['Base Color'].keyframe_insert('default_value', frame=frame(second))
            shader.inputs['Emission Color'].default_value = COLORS[model]
            shader.inputs['Emission Color'].keyframe_insert('default_value', frame=frame(second))
        else:
            emitter = material.node_tree.nodes.get('Emission')
            emitter.inputs['Color'].default_value = COLORS[model]
            emitter.inputs['Color'].keyframe_insert('default_value', frame=frame(second))
    action = material.node_tree.animation_data.action
    for curve in action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = 'CONSTANT'


def _leader_halo(name, position, size, material):
    x, y, z = position
    points = [(x+size*.70*math.cos(index*math.tau/48), y-.29,
               z+size*.32+size*.43*math.sin(index*math.tau/48)) for index in range(49)]
    obj = polyline(name, points, material, .012 if size < .4 else .014, cyclic=True)
    _show(obj, 68, 80)
    return obj


def build(scene):
    before = set(bpy.data.objects)
    data = json.loads(DATA.read_text(encoding='utf-8'))
    assert data['synthetic_measured_data_used'] is False
    rows = data['main_results']
    selected = {task: {row['model']: row for row in rows if row['task'] == task} for task, *_ in TASKS}
    assert all(set(value) == set(MODELS) for value in selected.values())
    assert len(rows) == 12
    deltas = {row['task']: row for row in data['deltas_from_full_precision']}
    for task in ('hourly_72_extension', 'daily_30'):
        actual = selected[task]['LSTM']['mae'] - selected[task]['Transformer']['mae']
        assert abs(actual-deltas[task]['absolute_advantage_w_m2']) < 1e-10
    coast_path = ASSETS / 'americas_land.json'
    coords_path = ASSETS / 'localities_report.json'
    coast = json.loads(coast_path.read_text(encoding='utf-8'))
    places = json.loads(coords_path.read_text(encoding='utf-8'))['localities']
    assert len(places) == 10
    mats = {model: _pbr(model+' matte surface', color) for model, color in COLORS.items()}
    texts = {model: emission('V8 '+model+' clear text', color, 1.05) for model, color in COLORS.items()}
    white = emission('V8 results clear white labels', WHITE, 1.)
    muted = emission('V8 results quiet reference axes', (.27, .37, .43, 1), .9)
    pale = _pbr('generic factory light facade', (.65, .70, .70, 1), .82, .02)
    glass = _pbr('generic factory blue glazing', (.18, .36, .43, 1), .28, .08)
    dark = _pbr('generic factory structural trim', (.07, .12, .14, 1), .72, .08)
    # Quantitative front view stays fixed for every task and every bar. Native
    # shading supplies depth; the horizontal length-to-value mapping is exact.
    scene.camera.animation_data_clear()
    scene.camera.data.animation_data_clear()
    camera_key(scene, 0, (0, -26, 3.85), (0, 0, 3.85), 16.8)
    camera_key(scene, 88, (0, -26, 3.85), (0, 0, 3.85), 16.8)
    # 0-7 s: same three compared models, four different prediction problems.
    _text('comparison rule', 'Compare dentro de cada tarefa', (0, -.30, 7.45), .49, white, 0, 7)
    _text('different scales', 'Escalas e alvos diferentes', (0, -.30, 6.72), .34, muted, 0, 7)
    tasks_intro = [('72 horas', 'Horária'), ('30 dias', 'Diária'), ('1 mês', 'Mensal'), ('6 meses', 'Mensal')]
    for index, (horizon, task_name) in enumerate(tasks_intro):
        x = -5.7 + index*3.8
        _text('intro task '+str(index), task_name, (x, -.25, 5.45), .34, white, index*.35, 7)
        _text('intro horizon '+str(index), horizon, (x, -.25, 4.82), .44, white, index*.35+.12, 7)
        for j, model in enumerate(MODELS):
            obj = _show(box('V8 compared model '+str(index)+' '+model,
                             (x+(j-1)*.66, 0, 3.72), (.42, .42, .42), mats[model], .055), index*.35+j*.12, 7)
            grow(obj, index*.35+j*.12, .5)
    for model, x in [('LSTM', -3.8), ('Transformer', 0), ('Informer', 3.8)]:
        _text('intro legend '+model, model, (x, -.25, 2.48), .37, texts[model], .3, 7)
    _text('selection context', 'Seleção pela validação · avaliação retrospectiva de 2024',
          (0, -.25, 1.5), .28, muted, .7, 7)
    # 7-68 s: the same three physical objects change length as each distinct
    # task is introduced, without reordering rows or changing the zero origin.
    x0, axis_width = -4.4, 9.6
    zrows = {model: 6.0-index*1.4 for index, model in enumerate(MODELS)}
    for model in MODELS:
        obj, length = _bar('V8 zero-based MAE '+model, (x0, 0, zrows[model]), mats[model], 7, 68)
        obj['numeric_encoding'] = 'Horizontal bounding-box length: MAE/task_axis_max * 9.6 world units; zero origin fixed'
        values = []
        previous = .001
        for task, start, end, maximum, title in TASKS:
            target = selected[task][model]['mae']/maximum*axis_width
            values.extend([(start, previous), (start+1.8, target), (end-.035, target)])
            previous = target
        _shape_keys(length, values)
        _text('model '+model, model, (-6.25, -.28, zrows[model]+.02), .40, texts[model], 7, 68)
    _line('common zero origin', [(x0, .25, 2.13), (x0, .25, 6.43)], muted, 7, 68, .009)
    _line('common bar axis', [(x0, .25, 2.13), (x0+axis_width, .25, 2.13)], muted, 7, 68, .012)
    _text('common error unit', 'Macro-MAE (W/m²) · menor é melhor', (.4, -.25, 1.38), .29, white, 7, 68)
    for task, start, end, maximum, title in TASKS:
        _text('task title '+task, title, (0, -.28, 7.5), .49, white, start, end)
        detail = 'Configurações selecionadas · teste 2024'
        if task == 'monthly_1':
            detail = 'Rede de uma saída · configurações selecionadas'
        if task == 'monthly_6':
            detail = 'Exploratório · erro cumulativo da rede de seis saídas'
        delta_start = {'hourly_72_extension': 16., 'daily_30': 32.}.get(task, end)
        _text('task selection '+task, detail, (0, -.28, 6.84), .29, muted, start, delta_start)
        winner = min(selected[task], key=lambda model: selected[task][model]['mae'])
        for model in MODELS:
            row = selected[task][model]
            z = zrows[model]
            _text('selected input '+task+model, row['condition'], (-6.25, -.28, z-.43), .28, muted, start, end)
            _text('actual MAE '+task+model, row['mae_display'], (6.58, -.28, z), .49, white, start+1.8, end)
            if model == winner:
                _text('minimum error tag '+task, 'Menor MAE', (6.58, -.28, z+.46), .23, texts[model], start+2, end)
        for fraction in (0, .5, 1):
            x = x0+axis_width*fraction
            _line('axis tick '+task+str(fraction), [(x, .10, 2.13), (x, .10, 2.02)], muted, start, end, .009, .25)
            _text('axis number '+task+str(fraction), f'{maximum*fraction:g}'.replace('.', ','),
                  (x, -.23, 1.81), .30, white, start, end)
        if task in deltas:
            delta = deltas[task]
            _text('small advantage '+task,
                  'Vantagem pequena sobre a LSTM: ≈ '+delta['display']+' W/m²',
                  (.6, -.30, 6.84), .32, texts['Transformer'], delta_start, end)
            xt = x0+selected[task]['Transformer']['mae']/maximum*axis_width
            xl = x0+selected[task]['LSTM']['mae']/maximum*axis_width
            _line('true-width small-difference bracket '+task,
                  [(xt, -.29, 6.34), (xt, -.29, 6.49), (xl, -.29, 6.49), (xl, -.29, 6.34)],
                  texts['Transformer'], delta_start, end, .007, .6)
            for model, x in [('Transformer', xt), ('LSTM', xl)]:
                _show(sphere('V8 exact endpoint highlight '+task+model,
                             (x, -.28, zrows[model]), .055, texts[model]), delta_start, end)
    # 68-80 s: actual task-specific leaders colour the same exact coordinates.
    # Each monthly task reads its own locality mapping: their aggregate counts
    # coincide, while Normal and Fremont exchange leaders.
    land_mat = _pbr('natural geographic land', (.19, .27, .22, 1), .9, .02)
    edge_mat = emission('V8 map subdued coast', (.35, .46, .41, 1), .7)
    _map_land(coast, land_mat, edge_mat, 68, 80)
    local_tasks = [(task, 68+index*3, 71+index*3, title)
                   for index, (task, _, _, _, title) in enumerate(TASKS)]
    for point in places:
        changes = []
        for task, start, end, title in local_tasks:
            winner = data['per_locality_winners'][task]['by_locality_id'][str(point['id'])]
            assert winner['winner'] == min(winner['maes'], key=winner['maes'].get)
            changes.append((start, winner['winner']))
        roof = _pbr('locality selected model '+str(point['id']), COLORS[changes[0][1]], .67, .04)
        _set_material_colors(roof, changes)
        halo = emission('V8 locality leader halo '+str(point['id']), COLORS[changes[0][1]], 1.0)
        _set_material_colors(halo, changes)
        position = _project(point['longitude'], point['latitude'], -.10)
        _factory('V8 generic factory exact locality '+str(point['id']), position, .29,
                 roof, pale, glass, dark)
        _leader_halo('V8 local leader outline '+str(point['id']), position, .29, halo)
        anchor = _show(sphere('V8 exact report coordinate '+str(point['id']), position, .045, roof), 68, 80)
        anchor['locality_id'] = point['id']
        anchor['latitude'] = point['latitude']
        anchor['longitude'] = point['longitude']
        if point['id'] in (8, 9):
            z = 3.5 if point['id'] == 8 else 1.9
            _line('Detroit area geographic leader '+str(point['id']),
                  [position, (3.2, -.17, z+.15), (4.2, -.17, z+.15)], muted, 68, 80, .007)
            _factory('V8 generic factory detail '+str(point['id']), (4.75, -.13, z), .56,
                     roof, pale, glass, dark)
            _leader_halo('V8 Detroit area leader outline '+str(point['id']), (4.75, -.13, z), .56, halo)
            city = 'Detroit' if point['id'] == 8 else 'Dearborn'
            _text('Detroit area locality '+city, city, (4.75, -.30, z-.34), .27, white, 68, 80)
    for task, start, end, title in local_tasks:
        _text('local task title '+task, 'Por localidade · '+title, (0, -.30, 7.70), .40, white, start, end)
        counts = data['per_locality_winners'][task]['leader_counts']
        for index, model in enumerate(MODELS):
            _text('local leader count '+task+model, model+': '+str(counts.get(model, 0)),
                  (4.75, -.30, 6.25-index*.55), .29, texts[model], start, end)
    # 80-88 s: categorical horizon glyphs show the actual daily winner and
    # its actual MAE. Their identical size carries no quantitative value.
    _text('daily horizon title', 'Diária · horizontes cumulativos', (0, -.30, 7.45), .48, white, 80, 88)
    _text('daily horizon criterion', 'Modelo com menor Macro-MAE em cada recorte', (0, -.30, 6.76), .30, muted, 80, 88)
    _line('categorical horizon sequence', [(-5.7, .22, 4.20), (5.7, .22, 4.20)], muted, 80, 88, .012, 2.5)
    for index, row in enumerate(data['daily_horizon_leaders']):
        x = -5.7+index*2.85
        model = row['winner']
        start = 80+index*.40
        _text('cumulative day '+str(row['horizon']), str(row['horizon'])+' d', (x, -.25, 5.55), .48, white, start, 88)
        cube = _show(box('V8 categorical horizon leader '+str(row['horizon']),
                         (x, 0, 4.20), (.74, .55, .74), mats[model], .08), start, 88)
        cube['meaning'] = 'Categorical model identity only; size does not encode error or horizon'
        grow(cube, start, .6)
        _text('horizon winning model '+str(row['horizon']), model, (x, -.30, 3.08), .31, texts[model], start+.25, 88)
        value = Decimal(str(row['maes'][model]))
        _text('horizon winning MAE '+str(row['horizon']), f'{value:.2f}'.replace('.', ','),
              (x, -.30, 2.43), .37, white, start+.45, 88)
    _text('horizon unit', 'Macro-MAE (W/m²)', (0, -.25, 1.55), .30, white, 80.5, 88)
    return {
        'version': 8, 'chapter': 'resultados', 'duration': 88, 'duration_seconds': 88,
        'global_seconds': [388, 476],
        'qa_times': [3, 12, 21, 29, 37, 47, 61, 69.5, 72.5, 75.5, 78.5, 85],
        'cues': [[0, 7, 'Compare os modelos dentro de cada tarefa: escalas e alvos são diferentes.'],
                 [7, 16, 'No horizonte horário completo de 72 horas, o Transformer teve o menor Macro-MAE: 53,21 watts por metro quadrado.'],
                 [16, 24, 'A vantagem sobre a LSTM foi pequena: cerca de 0,32 watt por metro quadrado, calculada antes do arredondamento.'],
                 [24, 32, 'Na tarefa diária, até 30 dias, o Transformer também apresentou o menor Macro-MAE: 43,89 watts por metro quadrado.'],
                 [32, 40, 'A diferença para a LSTM foi de aproximadamente 0,30 watt por metro quadrado. Os valores são próximos.'],
                 [40, 48, 'No mensal de um passo, o Informer com 128 níveis teve o menor erro: 12,73 watts por metro quadrado.'],
                 [48, 54, 'Os três modelos são comparados na mesma tarefa, com as condições selecionadas para cada um.'],
                 [54, 61, 'Na tarefa de seis meses, o Informer Q128 também teve o menor MAE cumulativo: 13,67 watts por metro quadrado.'],
                 [61, 68, 'Essa rede é diferente da mensal de um passo. O resultado de seis meses permanece exploratório.'],
                 [68, 74, 'A liderança varia entre localidades. As cores indicam o menor MAE em cada região.'],
                 [74, 80, 'Nos dois mensais, o Informer lidera cinco localidades, mas as localidades vencedoras mudam.'],
                 [80, 88, 'Na diária, a LSTM liderou os horizontes menores, até 14 dias. Em 30 dias, o Transformer apresentou a menor média.']],
        'sources': {'audited_json': str(DATA.relative_to(ROOT)),
                    'audited_json_sha256': hashlib.sha256(DATA.read_bytes()).hexdigest(),
                    'primary_csv_extracts': data['extracted_csvs'],
                    'report': data['source_report'],
                    'map': str(coast_path.relative_to(ROOT)),
                    'coordinates': str(coords_path.relative_to(ROOT))},
        'selected_results_only': True,
        'selection_frozen_by_validation_not_reranked_on_test': True,
        'main_results': rows,
        'deltas_from_full_precision': data['deltas_from_full_precision'],
        'per_locality_leader_counts': {task: data['per_locality_winners'][task]['leader_counts'] for task, *_ in TASKS},
        'monthly_winner_maps_loaded_separately': True,
        'daily_horizon_leaders': data['daily_horizon_leaders'],
        'synthetic_measured_data_used': False,
        'camera_quantitative_front_orthographic': True,
        'all_numeric_bar_axes_start_at_zero': True,
        'small_differences_not_visually_exaggerated': True,
        'tasks_have_separate_axis_scales_and_targets': True,
        'horizon_glyph_sizes_are_categorical': True,
        'caption_reserve_y_pixels': [900, 1000],
        'object_count': len(set(bpy.data.objects)-before),
    }
