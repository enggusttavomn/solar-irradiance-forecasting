"""V9 actual geography and a step-by-step explanation of histogram frequency.

The time curve locates readings in time; the histogram groups strictly positive
hourly observations into shared 50 W/m2 bins. Zero-valued hours use a separate
all-hours denominator. Factory symbols mark the queried NSRDB regions.
"""
import hashlib
import json
import math
from pathlib import Path
import random

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from common_v7 import (ROOT, OUT, WHITE, frame, box, sphere, polyline, surface,
                       emission, visible, reveal, keys, label, camera_key,
                       group, grow, arrow)

ASSETS = Path(__file__).resolve().parent / 'assets'
DATA = OUT / 'referencias/ghi_distributions_training.json'
DURATION = 60
COUNTRY_HEX = {'BR': '#88B878', 'US': '#77B9D0', 'MX': '#DBAE78'}
CITY_LABELS = {1: 'Camaçari', 2: 'Nevada', 3: 'Texas', 4: 'Geórgia',
               5: 'Normal', 6: 'Fremont', 7: 'Casa Grande', 8: 'Detroit',
               9: 'Dearborn', 10: 'San Luis Potosí'}


def _rgba(code):
    rgb = [int(code.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb) + (1,)


def _mat(name, code, rough=.6, metal=.05, luminous=False):
    color = _rgba(code)
    return emission('V7 geography ' + name, color, 1.25) if luminous else surface('V7 geography ' + name, color, metal, rough)


def _show(obj, start, end):
    visible(obj, start, end)
    return obj


def _trace(name, points, material, start, end, radius=.014, draw=.8, cyclic=False):
    obj = polyline('V7 geography ' + name, points, material, radius, cyclic=cyclic)
    visible(obj, start, end)
    reveal(obj, start, draw)
    return obj


def _font(name, text, loc, size, mat, start, end):
    if name.startswith('V9 '):
        loc=(loc[0],min(loc[1],-.8),loc[2])
    return label('V7 geography ' + name, text, loc, size, mat, start, end)


def _project(lon, lat, depth=0):
    return ((lon + 100.) * .050 - 1.0, depth, 3.65 + (lat - 9.) * .050)


def _triangles(coords):
    vertices = [Vector((float(lon), float(lat), 0)) for lon, lat in coords]
    triangles = tessellate_polygon([vertices])
    lookup = {tuple(v): i for i, v in enumerate(vertices)}
    return [tuple(v if isinstance(v, int) else lookup[tuple(v)] for v in face) for face in triangles]


def _land_material():
    mat = _mat('natural sage land shading', '#8C9B73', .83, .03)
    tree = mat.node_tree
    shader = tree.nodes.get('Principled BSDF')
    position = tree.nodes.new('ShaderNodeNewGeometry')
    separate = tree.nodes.new('ShaderNodeSeparateXYZ')
    tree.links.new(position.outputs['Position'], separate.inputs[0])
    normalize = tree.nodes.new('ShaderNodeMapRange')
    normalize.inputs['From Min'].default_value = .1
    normalize.inputs['From Max'].default_value = 7.2
    tree.links.new(separate.outputs['Z'], normalize.inputs['Value'])
    noise = tree.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1.6
    noise.inputs['Detail'].default_value = 2.5
    tree.links.new(position.outputs['Position'], noise.inputs['Vector'])
    mult = tree.nodes.new('ShaderNodeMath')
    mult.operation = 'MULTIPLY'
    mult.inputs[1].default_value = .09
    tree.links.new(noise.outputs['Fac'], mult.inputs[0])
    add = tree.nodes.new('ShaderNodeMath')
    add.operation = 'ADD'
    tree.links.new(mult.outputs[0], add.inputs[0])
    tree.links.new(normalize.outputs[0], add.inputs[1])
    ramp = tree.nodes.new('ShaderNodeValToRGB')
    palette = [(0., '#92A58A'), (.20, '#748F68'), (.48, '#6E8F68'),
               (.66, '#B5AA80'), (.85, '#98A38C'), (1., '#CFD5CB')]
    ramp.color_ramp.elements.remove(ramp.color_ramp.elements[1])
    ramp.color_ramp.elements[0].position = palette[0][0]
    ramp.color_ramp.elements[0].color = _rgba(palette[0][1])
    for value, color in palette[1:]:
        ramp.color_ramp.elements.new(value).color = _rgba(color)
    tree.links.new(add.outputs[0], ramp.inputs[0])
    tree.links.new(ramp.outputs['Color'], shader.inputs['Base Color'])
    return mat


def _map_mesh(name, coords, mat, depth):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([_project(lon, lat, depth) for lon, lat in coords], [], _triangles(coords))
    mesh.materials.append(mat)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _factory_symbol(name, position, size, materials, start=0, end=10.2):
    """Small generic building; its geographic anchor remains exact."""
    x, y, z = position
    objects = []
    def block(tag, loc, dims, material, bevel=.01):
        obj = box(name + ' ' + tag, loc, dims, material, bevel)
        objects.append(_show(obj, start, end))
    block('hall', (x, y - size * .08, z + size * .30),
          (size, size * .46, size * .47), materials['wall'])
    block('flat metal roof', (x, y - size * .08, z + size * .55),
          (size * 1.06, size * .51, size * .06), materials['metal'])
    block('glazing band', (x, y - size * .32, z + size * .37),
          (size * .78, size * .025, size * .12), materials['glass'], .002)
    block('entrance', (x - size * .25, y - size * .34, z + size * .17),
          (size * .18, size * .08, size * .25), materials['frame'], .003)
    block('roof ventilation', (x + size * .20, y - size * .08, z + size * .62),
          (size * .21, size * .20, size * .1), materials['frame'], .004)
    return objects


def _world(lon, lat, center, radius):
    phi, lam = math.radians(lat), math.radians(lon + 95.)
    return Vector(center) + Vector((radius * math.cos(phi) * math.sin(lam),
                                    -radius * math.cos(phi) * math.cos(lam),
                                    radius * math.sin(phi)))


def _globe_land(rings, center, radius, mat, start, end):
    verts, faces = [], []
    for ring in rings:
        if not ring['outer']:
            continue
        coords = ring['coordinates']
        for triangle in _triangles(coords):
            a, b, c = [Vector(coords[index]) for index in triangle]
            longest = max((a-b).length, (a-c).length, (b-c).length)
            n = max(1, min(18, math.ceil(longest / 6)))
            indices = {}
            for i in range(n + 1):
                for j in range(n + 1 - i):
                    p = a + (b - a) * (i / n) + (c - a) * (j / n)
                    indices[i, j] = len(verts)
                    verts.append(tuple(_world(p.x, p.y, center, radius)))
            for i in range(n):
                for j in range(n - i):
                    faces.append((indices[i, j], indices[i+1, j], indices[i, j+1]))
                    if j < n - i - 1:
                        faces.append((indices[i+1, j], indices[i+1, j+1], indices[i, j+1]))
    mesh = bpy.data.meshes.new('V7 geography globe actual Americas')
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(mat)
    mesh.update()
    obj = bpy.data.objects.new('V7 geography globe land Natural Earth', mesh)
    bpy.context.scene.collection.objects.link(obj)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return _show(obj, start, end)


def _satellite(materials, start=10.2, end=25):
    before = set(bpy.data.objects)
    center = Vector((-4.4, -.25, 6.0))
    body = _show(box('V7 NSRDB satellite unbranded body', center, (.65, .47, .62), materials['metal'], .055), start, end)
    for side in (-1, 1):
        x = center.x + side * 1.0
        _show(box('V7 satellite solar array', (x, -.25, 6), (1.0, .055, .68), materials['pv'], .015), start, end)
        _show(box('V7 satellite panel support', (center.x + side * .49, -.24, 6), (.35, .07, .055), materials['frame'], .008), start, end)
        for i in range(1, 5):
            _show(box('V7 satellite fine cell row', (x - .50 + i * .2, -.287, 6), (.008, .005, .64), materials['glass'], .001), start, end)
        for i in (-1, 0, 1):
            _show(box('V7 satellite fine cell column', (x, -.287, 6 + i * .17), (.96, .005, .006), materials['glass'], .001), start, end)
    dishverts = [(0, 0, 0)]
    dishfaces = []
    for i in range(33):
        angle = i * math.tau / 32
        dishverts.append((.28 * math.cos(angle), -.15, .28 * math.sin(angle)))
    for i in range(32):
        dishfaces.append((0, i + 1, i + 2))
    mesh = bpy.data.meshes.new('V7 satellite shallow communications dish')
    mesh.from_pydata(dishverts, [], dishfaces)
    mesh.materials.append(materials['wall'])
    dish = bpy.data.objects.new('V7 satellite shallow dish', mesh)
    bpy.context.scene.collection.objects.link(dish)
    dish.location = center + Vector((.06, -.30, -.09))
    _show(dish, start, end)
    collection = set(bpy.data.objects) - before
    root = group('V7 satellite assembly', collection)
    keys(root, 'location', [(start, (0, 0, 0)), (end, (.34, .10, .16))])
    return root


def _cloud(name, center, radius, material, start, end):
    rng = random.Random(name)
    metaball = bpy.data.metaballs.new(name)
    metaball.resolution = .13
    metaball.render_resolution = .11
    obj = bpy.data.objects.new(name, metaball)
    bpy.context.scene.collection.objects.link(obj)
    for x, y, z, r in [(-.64, 0, 0, .7), (-.16, .05, .25, .9), (.35, 0, .28, .87), (.8, .06, -.04, .60)]:
        element = metaball.elements.new()
        element.co = (x * radius, y * radius, z * radius)
        element.radius = r * radius
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    obj = bpy.context.object
    obj.location = center
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    # Restrained surface irregularity gives soft atmospheric form, not a
    # collection of perfect primitive spheres.
    texture = bpy.data.textures.new(name + ' fine contours', type='CLOUDS')
    texture.noise_scale = .22
    mod = obj.modifiers.new('Soft irregular cloud contour', 'DISPLACE')
    mod.texture = texture
    mod.strength = radius * .065
    keys(obj, 'location', [(start, center), (end, (center[0] + .27, center[1], center[2]))])
    return _show(obj, start, end)


def _data_flow(name, path, material, start, end, count=5):
    objects = []
    for i in range(count):
        obj = sphere(name + ' ' + str(i), path[0], .035, material)
        _show(obj, start + i * .14, end)
        entries = []
        t = start + i * .14
        while t < end:
            for j, point in enumerate(path):
                entries.append((min(end, t + 1.4 * j / (len(path) - 1)), point))
            if t + 1.4 < end:
                entries.append((t + 1.405, path[0]))
            t += 1.42
        keys(obj, 'location', entries, linear=True)
        objects.append(obj)
    return objects


def _cell_grid(name, center, material, selected, start, end, size=.6):
    x, y, z = center
    objects = []
    for row in range(3):
        for column in range(3):
            pos = (x + (column - 1) * size, y, z + (row - 1) * size)
            item = box(name + ' cell ' + str(row * 3 + column), pos,
                       (size * .94, .15, size * .94), selected if row == 1 and column == 1 else material, .015)
            objects.append(_show(item, start, end))
    return objects


def _histogram_bars(name, values, edges, x0, x1, z0, height, ymax, material, start, end):
    vertices, faces = [], []
    for i, probability in enumerate(values):
        left = x0 + (x1-x0)*edges[i]/edges[-1] + .008
        right = x0 + (x1-x0)*edges[i+1]/edges[-1] - .008
        top = z0 + max(.001, height*probability/ymax)
        base = len(vertices)
        vertices.extend([(left, -.025, z0), (right, -.025, z0),
                         (right, .095, z0), (left, .095, z0),
                         (left, -.025, top), (right, -.025, top),
                         (right, .095, top), (left, .095, top)])
        faces.extend(tuple(base+j for j in face) for face in
                     [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
                      (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
    mesh = bpy.data.meshes.new(name+' mesh')
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    _show(obj, start, end)
    obj.shape_key_add(name='Observed class frequencies')
    flat = obj.shape_key_add(name='Grow from zero frequency')
    for vertex in flat.data:
        vertex.co.z = z0
    for second, value in [(start, 1), (start+.6, 0)]:
        flat.value = value
        flat.keyframe_insert('value', frame=frame(second))
    return obj


def build(scene):
    before = set(bpy.data.objects)
    coast_path = ASSETS / 'americas_land.json'
    points_path = ASSETS / 'localities_report.json'
    coast = json.loads(coast_path.read_text(encoding='utf-8'))
    locations = json.loads(points_path.read_text(encoding='utf-8'))['localities']
    distributions = json.loads(DATA.read_text(encoding='utf-8'))
    assert len(locations) == len(distributions['localities']) == 10
    assert [p['id'] for p in locations] == list(range(1, 11))
    assert distributions['synthetic_data_used'] is False
    data_by_id = {item['id']: item for item in distributions['localities']}
    for point in locations:
        assert point['latitude'] == data_by_id[point['id']]['latitude']
        assert point['longitude'] == data_by_id[point['id']]['longitude']
    m = {
        'land': _land_material(),
        'coast': _mat('subtle natural coastline', '#BAC9AF', luminous=True),
        'water': _mat('dark ocean inlets', '#162934', .43, .05),
        'wall': _mat('generic building ivory', '#E0E3DA'),
        'metal': _mat('matte satellite and roof metal', '#9BAFB7', .51, .36),
        'glass': _mat('blue grey glazing and fine lines', '#7FAABB', .25, .15),
        'frame': _mat('charcoal structural frames', '#435B64'),
        'pv': _mat('satellite silicon blue', '#254963', .27, .23),
        'white': _mat('clear labels and irradiance curve', '#F0F4F5', luminous=True),
        'muted': _mat('quiet reference axes', '#6E858D', luminous=True),
        'cloud': _mat('cloud soft ivory', '#D8E0DE', .91, 0),
        'cell': _mat('unselected geographical cells', '#52705F', .85, .02),
        'selected': _mat('selected geographical cell', '#D9B46B', .72, .03),
        'flow': _mat('estimated information flow', '#8ECBD4', luminous=True),
        'ocean': _mat('earth ocean blue', '#315B72', .52, .08),
    }
    country = {code: _mat('country ' + code, value, luminous=True) for code, value in COUNTRY_HEX.items()}
    # 0-10 s: exact projected coast and exact point anchors. The two Detroit
    # localities stay distinct in data even when their symbols overlap at
    # continental scale. No marker is moved to make the figure look cleaner.
    map_objects = []
    for index, ring in enumerate(coast['rings']):
        obj = _map_mesh('V7 Americas Natural Earth ' + str(index), ring['coordinates'],
                        m['land'] if ring['outer'] else m['water'], .03 if ring['outer'] else -.01)
        _show(obj, 0, 10.2)
        if ring['outer']:
            mod = obj.modifiers.new('Physical continental relief', 'SOLIDIFY')
            mod.thickness = .10
        map_objects.append(obj)
        line = _trace('coast ' + str(index), [_project(lon, lat, -.03) for lon, lat in ring['coordinates']],
                      m['coast'], .05, 10.2, .006, 1.8, True)
        map_objects.append(line)
    for index, point in enumerate(locations):
        position = _project(point['longitude'], point['latitude'], -.13)
        marker = _show(sphere('V7 exact geographic anchor ' + str(point['id']), position, .047,
                              country[point['country']]), .35 + index * .10, 10.2)
        marker['report_locality_id'] = point['id']
        marker['latitude'] = point['latitude']
        marker['longitude'] = point['longitude']
        marker['meaning'] = 'Exact queried-cell reference coordinate; not a factory sensor'
        map_objects.append(marker)
        map_objects.extend(_factory_symbol('V7 generic factory locality ' + str(point['id']),
                                           position, .29, m, .4 + index * .10, 10.2))
    map_objects.append(_font('geographic title', 'Dez localidades nas Américas', (-.5, -.2, 7.30), .40, m['white'], 0, 3.3))
    for code, text, z in [('BR', '1 Brasil', 5.25), ('US', '8 Estados Unidos', 4.65), ('MX', '1 México', 4.05)]:
        map_objects.append(_font('country count ' + code, text, (4.0, -.2, z), .32, country[code], 0, 3.35))
        map_objects.append(_font('country count return ' + code, text, (4.0, -.2, z), .32, country[code], 8.4, 10.2))
    brazil = _project(locations[0]['longitude'], locations[0]['latitude'], -.13)
    for point, z in [(locations[7], 5.45), (locations[8], 3.75)]:
        anchor = _project(point['longitude'], point['latitude'], -.15)
        destination = (4.10, -.14, z)
        map_objects.append(_trace('exact Detroit area callout '+str(point['id']),
                                  [anchor, (2.65, -.18, z+.15), (3.72, -.18, z+.15)],
                                  m['muted'], 3.8, 8.15, .008, .85))
        map_objects.extend(_factory_symbol('V7 enlarged generic locality '+str(point['id']),
                                           destination, .62, m, 4.15, 8.15))
        map_objects.append(_font('Detroit area city '+str(point['id']), CITY_LABELS[point['id']],
                                 (4.10, -.32, z-.32), .28, country['US'], 4.15, 8.15))
    map_group = group('V7 Americas and coordinate symbols', map_objects)
    keys(map_group, 'scale', [(0, (1, 1, 1)), (9.6, (1, 1, 1)), (10.2, (.001, .001, .001))])
    # 10-25 s: satellite observations and atmospheric processing are upstream
    # of the irradiance data. NSRDB is a database/model workflow, never a
    # building or a physical sensor located in the factory.
    globe_center = (-4.2, .8, 3.35)
    _show(sphere('V7 observed Earth ocean', globe_center, 1.45, m['ocean']), 10.2, 25)
    _globe_land(coast['rings'], globe_center, 1.47, m['land'], 10.2, 25)
    _satellite(m)
    _font('satellite label', 'Observações de satélite', (-4.1, -.5, 1.38), .29, m['white'], 10.2, 25)
    _font('NSRDB textmark', 'NSRDB', (.0, -.10, 6.35), .61, m['white'], 10.5, 25)
    _font('NSRDB subtitle', 'National Solar Radiation Database', (.1, -.10, 5.81), .25, m['muted'], 10.8, 25)
    _cloud('V7 retrieved cloud properties cloud', (-.25, .0, 4.25), .75, m['cloud'], 13, 25)
    for index in range(3):
        radius = .75 + index * .22
        points = [(radius * math.cos(i * math.tau / 60), .05 + index * .15,
                   3.0 + .30 * math.sin(i * math.tau / 60)) for i in range(61)]
        _trace('atmospheric physical layer ' + str(index), points, m['flow'], 14.0 + index * .25, 25, .012, 1, True)
    _font('physical model', 'Nuvens + atmosfera', (.0, -.25, 2.04), .32, m['white'], 13, 25)
    _font('model operation', 'Modelo físico de radiação', (.0, -.25, 1.57), .25, m['muted'], 15, 25)
    _cell_grid('V7 NSRDB surface estimation', (4.1, .0, 3.5), m['cell'], m['selected'], 18, 25, .65)
    _font('geographic estimates label', 'Estimativas por célula', (4.1, -.25, 1.75), .30, m['white'], 18, 25)
    _data_flow('V7 Earth observation packets', [(-4.2, -.45, 4.30), (-4.5, -.55, 4.9), (-4.4, -.55, 5.6)], m['white'], 10.5, 16, 4)
    arrow('V7 satellite to atmospheric properties', (-2.95, -.2, 4.5), (-1.25, -.2, 4.05), m['muted'], 13.2, 25)
    arrow('V7 atmospheric processing to cell', (1.28, -.2, 3.5), (2.65, -.2, 3.5), m['muted'], 18.1, 25)
    _data_flow('V7 retrieved atmospheric values', [(-2.9, -.3, 4.5), (-2.05, -.3, 4.4), (-1.25, -.3, 4.05)], m['flow'], 13.5, 25, 4)
    _data_flow('V7 modelled irradiance values', [(1.28, -.3, 3.5), (1.9, -.3, 3.5), (2.65, -.3, 3.5)], m['flow'], 18.4, 25, 4)
    # A time series answers WHEN; a histogram answers HOW OFTEN a range occurs.
    example = data_by_id[1]['series_example']
    series = example['values_w_m2'][:72]
    a, b = 25, 32
    _font('V9 temporal contrast', 'No tempo: quando cada valor ocorreu?', (0, -.2, 6.9), .48, m['white'], a, b)
    _font('V9 temporal source', 'Camaçari · 1–3 jan. 2019 · dados reais da NSRDB', (0, -.2, 6.25), .27, m['muted'], a, b)
    px0, px1, pz0, ph = -6.2, 6.2, 1.8, 3.5
    pts = [(px0+(px1-px0)*i/71, -.1, pz0+ph*v/1200) for i,v in enumerate(series)]
    _trace('V9 actual 72 hour series', pts, m['white'], a, b, .021, 1.7)
    _trace('V9 time baseline', [(px0, 0, pz0), (px1, 0, pz0)], m['muted'], a, b, .01, .3)
    for hour in (0,24,48,72):
        x=px0+(px1-px0)*hour/72
        _font('V9 time '+str(hour), str(hour)+' h', (x,-.2,pz0-.35), .28,m['white'],a,b)
    _font('V9 time unit','GHI (W/m²)',(-5.4,-.2,5.5),.27,m['white'],a,b)
    chosen = [7,31,55]
    for i,idx in enumerate(chosen):
        value=series[idx]
        point=sphere('V9 actual selected reading '+str(idx),pts[idx],.085,m['selected'])
        _show(point,26+i*.3,38)
        keys(point,'location',[(26+i*.3,pts[idx]),(31,pts[idx]),(33.7,(-1.2+i*1.2,-.25,3.7+i*.2))])
        _font('V9 selected actual reading '+str(idx),str(value).replace('.',',')+' W/m²',
              (pts[idx][0],-.2,pts[idx][2]+.5),.24,m['selected'],26+i*.3,32)
    _font('V9 histogram contrast','Por faixas: quantas horas em cada intervalo?',(0,-.2,6.9),.46,m['white'],32,45)
    _font('V9 selected range','400 ≤ GHI < 450 W/m²',(0,-.2,5.8),.48,m['selected'],32,45)
    _trace('V9 range bucket',[(-2.6,-.10,4.5),(-2.6,-.10,2.5),(2.6,-.10,2.5),(2.6,-.10,4.5)],m['selected'],32,38,.035,.7)
    _font('V9 three real reading examples','439,0     428,5     430,5 W/m²',(0,-.3,1.65),.35,m['white'],32.5,38)
    _font('V9 examples not full count','Três exemplos reais que pertencem à mesma faixa',(0,-.25,.95),.27,m['muted'],32.5,38)
    bin_index=8
    counted=data_by_id[1]['positive_counts'][bin_index]
    positives=data_by_id[1]['positive_sample_count']
    percent=100*counted/positives
    assert counted==881 and positives==18496
    pct=f'{percent:.1f}'.replace('.',',')
    _font('V9 denominator count','881 horas nesta faixa',(0,-.2,4.55),.55,m['white'],38,45)
    _font('V9 denominator fraction','881 ÷ 18.496 × 100 ≈ '+pct+'%',(0,-.2,3.5),.55,m['selected'],38.5,45)
    _font('V9 denominator explanation','18.496 = todas as horas com GHI > 0',(0,-.2,2.5),.32,m['white'],39,45)
    _font('V9 positive sample scope','Camaçari · período de treinamento: 2019–2022',(0,-.2,1.65),.29,m['muted'],38,45)
    # Same measured bins across all ten sites, no fictitious profile or labels.
    edges=distributions['bin_edges_w_m2']
    centers=[(aa+bb)/2 for aa,bb in zip(edges,edges[1:])]
    ymax=math.ceil(max(max(d['positive_probability']) for d in data_by_id.values())*20)/20
    x0,x1,z0,height=-4.75,6.3,1.5,4.2
    _font('V9 distribution interpretation','Como os valores se distribuem em cada localidade?',(0,-.2,7.1),.42,m['white'],45,60)
    _font('V9 distribution scope','Cada barra: faixa de 50 W/m² · treinamento 2019–2022',(0,-.2,6.6),.26,m['muted'],45,60)
    _font('V9 frequency explicit axis','% das horas com GHI > 0',(-2.8,-.2,6.05),.29,m['white'],45,60)
    _trace('V9 histogram horizontal axis',[(x0,.1,z0),(x1,.1,z0)],m['muted'],45,60,.010,.4)
    _trace('V9 histogram vertical axis',[(x0,.1,z0),(x0,.1,z0+height)],m['muted'],45,60,.010,.4)
    for value in range(0,round(ymax*100)+1,5):
        z=z0+height*(value/100)/ymax
        _font('V9 percent tick '+str(value),str(value)+'%',(x0-.4,-.2,z),.23,m['white'],45,60)
    for value in (0,300,600,900,1200):
        x=x0+(x1-x0)*value/1200
        _font('V9 bin x tick '+str(value),str(value),(x,-.2,z0-.27),.25,m['white'],45,60)
    _font('V9 bin x meaning','Faixa de GHI (W/m²)',(4.4,-.2,.82),.29,m['white'],45,60)
    overview=57
    for index,point in enumerate(locations):
        d=data_by_id[point['id']]
        start=45+index*1.2;end=start+1.2
        color=country[point['country']]
        vals=d['positive_probability']
        profile=[(x0+(x1-x0)*center/1200,-.19,z0+height*prob/ymax) for center,prob in zip(centers,vals)]
        fill=_mat('V9 observed histogram '+str(point['id']),COUNTRY_HEX[point['country']],.65,.08)
        _histogram_bars('V9 positive hour bins '+str(point['id']),vals,edges,x0,x1,z0,height,ymax,fill,start,end)
        _trace('V9 selected profile '+str(point['id']),profile,color,start,end,.022,.5)
        _trace('V9 comparison profile '+str(point['id']),profile,color,overview,60,.010,.2)
        city=point['country']+' · '+CITY_LABELS[point['id']]
        pos=(-6.55,-.2,5.65-index*.43)
        if start>45:
            _font('V9 site list before '+str(point['id']),city,pos,.24,m['muted'],45,start)
        if end<60:
            _font('V9 site list after '+str(point['id']),city,pos,.24,m['muted'],end,60)
        _font('V9 active site list '+str(point['id']),city,(pos[0],-.25,pos[2]),.255,color,start,end)
        _font('V9 active city '+str(point['id']),CITY_LABELS[point['id']],(1.05,-.2,6.05),.34,color,start,end)
        zero=f"{100*d['zero_fraction']:.1f}%".replace('.',',')
        _font('V9 zero excluded '+str(point['id']),'GHI = 0: '+zero+' de todas as horas',(3.6,-.2,5.48),.25,m['white'],start,end)
    _font('V9 comparison heading','Mesmos intervalos e escala',(1.8,-.2,6.05),.31,m['white'],overview,60)
    _font('V9 zeros explicit overview','Zeros ficam fora destas barras',(2.5,-.2,5.48),.27,m['white'],overview,60)
    for second,location,target,scale in [
        (0,(-.7,-26,8),(-1,0,3.8),13.9),(9.1,(-.7,-26,8),(-1,0,3.8),13.9),
        (10.2,(0,-26,7.7),(0,0,3.6),16.1),(24.6,(0,-26,7.7),(0,0,3.6),16.1),
        (25,(0,-26,6.7),(0,0,3.5),16),(31.8,(0,-26,6.7),(0,0,3.5),16),
        (32,(0,-26,6.7),(0,0,3.5),16),(44.8,(0,-26,6.7),(0,0,3.5),16),
        (45,(0,-26,6.1),(0,0,3.5),16.2),(60,(0,-26,6.1),(0,0,3.5),16.2)]:
        camera_key(scene,second,location,target,scale)
    return {'version':9,'duration':60,'qa_times':[4.5,16.5,29,35,42,49,56,59],
        'cues':[[0,4,'As localidades deste estudo estão nas Américas.'],
        [4,10,'São dez regiões: uma no Brasil, oito nos Estados Unidos e uma no México.'],
        [10,16,'A NSRDB usa observações de satélite e informações da atmosfera para estimar o recurso solar.'],
        [16,25,'Modelos físicos combinam essas informações e estimam a irradiância em cada região consultada.'],
        [25,32,'A curva mostra quando os valores ocorreram. Já as barras agrupam esses valores por faixa.'],
        [32,38,'Estas três leituras reais de Camaçari pertencem à mesma faixa de GHI.'],
        [38,45,'Essa faixa reúne cerca de quatro vírgula oito por cento das horas com valor positivo.'],
        [45,53,'Cada barra mostra a porcentagem naquela faixa. As horas com valor zero são contadas separadamente.'],
        [53,60,'Com intervalos e escalas iguais, comparamos a distribuição dos valores entre as dez localidades.']],
        'distribution_source':str(DATA.relative_to(ROOT)),'distribution_source_sha256':hashlib.sha256(DATA.read_bytes()).hexdigest(),
        'synthetic_distribution_or_history':False,'frequency_denominator':'per-locality hours strictly GHI > 0',
        'example_bin':{'locality':'Camaçari','range_w_m2':[400,450],'left_closed_right_open':True,'count':counted,'positive_hours':positives,'percent':percent},
        'source_period':distributions['source_period'],'all_ten_localities_shown':True,
        'temporal_curve_and_histogram_distinguished':True,'no_factory_sensor_claim':True,'zeros_separate':True}
