"""A generic contemporary EV manufacturing site, modelled at metre scale.

Only architecture, landscaping and an optional PV carport are built here.
Lighting, irradiance, reference dimensions, camera moves and scene visibility
belong to the V6 director. No real manufacturer, logo or location is depicted.
"""
import math
import random
from pathlib import Path

import bpy
from mathutils import Vector


PREFIX = 'V6 factory '


def _rgba(code):
    values = [int(code.lstrip('#')[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values) + (1.,)


def _material(name, color, roughness=.65, metal=0., grain=0., scale=38., emission=0., emission_color=None):
    material = bpy.data.materials.new(PREFIX + name)
    material.use_nodes = True
    material.diffuse_color = _rgba(color)
    material['design_srgb_hex'] = color
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = material.diffuse_color
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metal
    shader.inputs['Emission Color'].default_value = _rgba(emission_color or color)
    shader.inputs['Emission Strength'].default_value = emission
    if grain:
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        noise = nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = scale
        noise.inputs['Detail'].default_value = 2.5
        bump = nodes.new('ShaderNodeBump')
        bump.inputs['Strength'].default_value = .15
        bump.inputs['Distance'].default_value = grain
        links.new(noise.outputs['Fac'], bump.inputs['Height'])
        links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    return material


def _link(obj, collection):
    for old in tuple(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def _box(collection, name, location, dimensions, material, bevel=.035):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new('Small manufactured edge radii', 'BEVEL')
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new('Weighted surface normals', 'WEIGHTED_NORMAL')
    return _link(obj, collection)


class _Batch:
    """Batch repeated small solids/branches/leaves into one shaded mesh."""
    def __init__(self):
        self.vertices = []
        self.faces = []
        self.indices = []

    def box(self, location, dimensions, material=0):
        x, y, z = location
        a, b, c = (d / 2 for d in dimensions)
        base = len(self.vertices)
        self.vertices.extend([(x - a, y - b, z - c), (x + a, y - b, z - c),
                              (x + a, y + b, z - c), (x - a, y + b, z - c),
                              (x - a, y - b, z + c), (x + a, y - b, z + c),
                              (x + a, y + b, z + c), (x - a, y + b, z + c)])
        self.faces.extend(tuple(base + n for n in face) for face in
                          [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
                           (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
        self.indices.extend([material] * 6)

    def cylinder(self, start, end, radius0, radius1, sides=7, material=0):
        start, end = Vector(start), Vector(end)
        direction = (end - start).normalized()
        helper = Vector((0, 0, 1)) if abs(direction.z) < .92 else Vector((0, 1, 0))
        u = direction.cross(helper).normalized()
        v = direction.cross(u).normalized()
        base = len(self.vertices)
        for point, radius in ((start, radius0), (end, radius1)):
            self.vertices.extend(tuple(point + radius * (math.cos(i * math.tau / sides) * u +
                                                        math.sin(i * math.tau / sides) * v)) for i in range(sides))
        self.faces.append(tuple(base + i for i in reversed(range(sides))))
        self.faces.append(tuple(base + sides + i for i in range(sides)))
        self.faces.extend((base + i, base + (i + 1) % sides,
                           base + sides + (i + 1) % sides, base + sides + i) for i in range(sides))
        self.indices.extend([material] * (sides + 2))

    def leaf(self, center, normal, length, width, roll, material):
        normal = Vector(normal).normalized()
        helper = Vector((0, 0, 1)) if abs(normal.z) < .9 else Vector((1, 0, 0))
        u = normal.cross(helper).normalized()
        v = normal.cross(u).normalized()
        axis = math.cos(roll) * u + math.sin(roll) * v
        side = normal.cross(axis).normalized()
        p = Vector(center)
        base = len(self.vertices)
        # A folded, six-sided lanceolate leaf. The ridge catches the light,
        # rather than the spherical puffs used in the previous site.
        self.vertices.extend([tuple(p - axis * length * .5),
                              tuple(p - axis * length * .12 - side * width * .5),
                              tuple(p + axis * length * .26 - side * width * .34),
                              tuple(p + axis * length * .5),
                              tuple(p + axis * length * .26 + side * width * .34),
                              tuple(p - axis * length * .12 + side * width * .5),
                              tuple(p + normal * width * .1)])
        self.faces.extend((base + i, base + (i + 1) % 6, base + 6) for i in range(6))
        self.indices.extend([material] * 6)

    def object(self, name, materials, collection, smooth=False):
        mesh = bpy.data.meshes.new(PREFIX + name + ' mesh')
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        for material in materials:
            mesh.materials.append(material)
        for polygon, index in zip(mesh.polygons, self.indices):
            polygon.material_index = index
            polygon.use_smooth = smooth
        obj = bpy.data.objects.new(PREFIX + name, mesh)
        collection.objects.link(obj)
        return obj


def _polygon(collection, name, points, material):
    mesh = bpy.data.meshes.new(PREFIX + name)
    mesh.from_pydata(points, [], [tuple(range(len(points)))])
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    return obj


def _tree(collection, seed, x, y, height, bark, leaves, animate=True):
    rng = random.Random(seed)
    wood = _Batch()
    crown = _Batch()
    # A slightly irregular leader, then major and secondary branching.
    base = Vector((x, y, .08))
    leader = [base]
    for i in range(1, 6):
        leader.append(base + Vector((.07 * math.sin(i + seed), .10 * math.cos(i * .7 + seed), height * i * .16)))
        wood.cylinder(leader[-2], leader[-1], height * .025 * (1 - (i - 1) * .11),
                      height * .025 * (1 - i * .11), 9)
    ends = []
    for i in range(11):
        angle = i * 2.39996 + rng.uniform(-.28, .28)
        start = leader[2 + i % 3]
        reach = height * rng.uniform(.20, .35)
        end = base + Vector((math.cos(angle) * reach, math.sin(angle) * reach,
                             height * rng.uniform(.66, .95)))
        middle = start.lerp(end, .5) + Vector((0, 0, height * .025))
        wood.cylinder(start, middle, height * .012, height * .006, 7)
        wood.cylinder(middle, end, height * .006, height * .0025, 6)
        for j in range(3):
            a = angle + (j - 1) * .6
            tip = end + Vector((math.cos(a) * height * .105, math.sin(a) * height * .105,
                                height * rng.uniform(.025, .13)))
            wood.cylinder(end.lerp(middle, .25), tip, height * .0032, .008, 5)
            ends.append(tip)
    for tip in ends:
        # Individual leaves around different tapered branches give an open,
        # irregular silhouette with genuine gaps and visible twig structure.
        for _ in range(100):
            direction = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
            distance = rng.random() ** (1 / 3)
            offset = Vector((direction.x * height * .115, direction.y * height * .11,
                             direction.z * height * .095)) * distance
            point = tip + offset
            normal = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(.25, 1.1)))
            size = height * rng.uniform(.023, .035)
            crown.leaf(point, normal, size, size * rng.uniform(.42, .62),
                       rng.random() * math.tau, rng.randrange(len(leaves)))
    wood_obj = wood.object(f'branched tree {seed} trunk', [bark], collection, smooth=True)
    leaf_obj = crown.object(f'branched tree {seed} leaves', leaves, collection)
    if animate:
        leaf_obj.shape_key_add(name='Rest leaves')
        breeze = leaf_obj.shape_key_add(name='Light irregular breeze')
        for vertex in breeze.data:
            co = vertex.co
            factor = max(0, (co.z - .4) / height)
            co.x += .07 * factor * math.sin(co.x * 2.5 + co.y * 1.7 + seed)
            co.y += .045 * factor * math.cos(co.x * 1.6 - co.y * 2.7)
        for second, value in [(0, .15), (4, .8), (9, .2), (15, .65), (21, .15), (27, .75), (33, .3), (40, .65)]:
            breeze.value = value
            breeze.keyframe_insert('value', frame=round(second * 30) + 1)
    return wood_obj, leaf_obj


def _car(collection, name, x, y, material, trim, rubber, alloy, glass, lamps, turn=0):
    group = bpy.data.objects.new(PREFIX + name, None)
    collection.objects.link(group)
    group.location = (x, y, .06)
    group.rotation_euler.z = turn
    def part(label, loc, dims, mat, bevel):
        obj = _box(collection, name + ' ' + label, loc, dims, mat, bevel)
        obj.parent = group
        return obj
    part('sculpted lower body', (0, 0, .59), (4.5, 1.86, .62), material, .25)
    part('roof cabin', (-.21, 0, 1.11), (2.37, 1.63, .72), material, .24)
    part('bonnet', (1.38, 0, .87), (1.28, 1.77, .28), material, .16)
    part('front fascia', (2.22, 0, .53), (.09, 1.63, .25), trim, .045)
    part('rear glazing', (-1.37, 0, 1.23), (.035, 1.4, .4), glass, .08)
    part('windscreen', (.94, 0, 1.23), (.035, 1.43, .43), glass, .08)
    for side in (-1, 1):
        part('side glass', (-.21, side * .825, 1.24), (2.0, .025, .40), glass, .06)
        part('window pillar', (-.2, side * .846, 1.23), (.07, .025, .43), trim, .01)
        part('side skirt', (0, side * .92, .41), (3.2, .07, .13), trim, .025)
        part('headlamp', (2.23, side * .60, .74), (.025, .43, .11), lamps, .025)
        for xx in (-1.35, 1.35):
            bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=.38, depth=.22,
                                               location=(xx, side * .94, .39), rotation=(math.pi / 2, 0, 0))
            obj = bpy.context.object
            obj.name = PREFIX + name + ' tyre'
            obj.data.materials.append(rubber)
            _link(obj, collection)
            obj.parent = group
            for polygon in obj.data.polygons:
                polygon.use_smooth = True
            bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=.23, depth=.025,
                                               location=(xx, side * 1.06, .39), rotation=(math.pi / 2, 0, 0))
            obj = bpy.context.object
            obj.name = PREFIX + name + ' alloy wheel'
            obj.data.materials.append(alloy)
            _link(obj, collection)
            obj.parent = group
    return group


def build_factory_site_v6():
    scene = bpy.context.scene
    site = bpy.data.collections.new('V6 generic EV manufacturing architecture')
    scene.collection.children.link(site)
    pv = bpy.data.collections.new('V6 optional solar parking application')
    scene.collection.children.link(pv)
    m = {
        'wall': _material('warm light aluminium facade', '#D9DDDA', .63, .19, .0014),
        'wall_dark': _material('lower stone-grey cladding', '#9AA7AC', .68, .12, .0015),
        'roof': _material('weathered pale zinc roof', '#BCC6C9', .63, .30, .0018),
        'concrete': _material('light cast concrete', '#BFC0B6', .88, grain=.012, scale=57),
        'asphalt': _material('fine dark asphalt', '#42494A', .94, grain=.006, scale=130),
        'frame': _material('charcoal anodised frames', '#334B55', .53, .26),
        'sign': _material('blue raised lettering', '#254F64', .62, .05),
        'glass': _material('office blue grey glazing', '#7096A6', .18, .06, emission_color='#FFE4BC'),
        'rubber': _material('matte dark rubber', '#20282A', .94),
        'bark': _material('tree bark', '#665748', .97, grain=.018, scale=42),
        'grass': _material('uneven living groundcover', '#627A43', .98, grain=.012, scale=19),
        'paint': _material('road marking warm white', '#E1DFCC', .91),
        'safety': _material('safety yellow paint', '#DDBF60', .68),
        'whitecar': _material('pearl white vehicle', '#DFE1DB', .3, .18),
        'bluecar': _material('muted blue vehicle', '#4D7484', .34, .16),
        'silvercar': _material('silver-grey vehicle', '#8D999E', .37, .20),
        'carglass': _material('tinted automotive glass', '#213B49', .2, .08),
        'lamp': _material('headlight covers', '#DCE6E5', .3),
        'night': _material('warm architectural light strips', '#DCD8C9', .5, emission_color='#FFDFB6'),
        'pv': _material('photovoltaic dark silicon', '#17374B', .24, .17),
        'pvline': _material('PV cell fine conductors', '#8196A0', .5, .35),
    }
    glass_shader = m['glass'].node_tree.nodes.get('Principled BSDF')
    glass_shader.inputs['Coat Weight'].default_value = .32
    glass_shader.inputs['Coat Roughness'].default_value = .13
    leaves = [_material('leaf '+str(i), code, .89) for i, code in enumerate(
        ['#486742', '#567744', '#68854B', '#758E51', '#4D713D', '#829A5C'])]
    for leaf in leaves:
        node = leaf.node_tree.nodes.get('Principled BSDF')
        node.inputs['Subsurface Weight'].default_value = .045
        node.inputs['Sheen Weight'].default_value = .15
    # The thin site edge is at grade, rather than a toy-like raised platform.
    _box(site, 'ground at grade', (0, 0, -.11), (88, 64, .2), m['asphalt'], .16)
    _box(site, 'main hall concrete plinth', (0, 0, .27), (60.3, 32.3, .5), m['concrete'], .06)
    _box(site, 'long manufacturing hall', (0, 0, 5.15), (60, 32, 10), m['wall'], .045)
    _box(site, 'dark lower facade band', (0, -16.035, 1.34), (60, .1, 2.25), m['wall_dark'], .015)
    _box(site, 'flat roof deck', (0, 0, 10.17), (60.3, 32.3, .16), m['roof'], .035)
    details = _Batch()
    for x in [-29.7 + i * 1.2 for i in range(50)]:
        # Keep an uninterrupted one-square-metre flat service area for GHI.
        if not 7.0 <= x <= 9.0:
            details.box((x, 0, 10.275), (.027, 31.8, .05))
        details.box((x, -16.10, 5.3), (.025, .025, 9.5), 1)
    for y in [-15.6 + i * 1.2 for i in range(27)]:
        details.box((30.06, y, 5.3), (.035, .025, 9.5), 1)
        details.box((-30.06, y, 5.3), (.035, .025, 9.5), 1)
    details.object('fine cladding and standing roof seams', [m['roof'], m['wall_dark']], site)
    _box(site, 'front roof parapet', (0, -16.15, 10.34), (60.5, .18, .38), m['frame'], .025)
    _box(site, 'rear roof parapet', (0, 16.15, 10.34), (60.5, .18, .38), m['frame'], .025)
    _box(site, 'east roof parapet', (30.16, 0, 10.34), (.18, 32.2, .38), m['frame'], .025)
    _box(site, 'west roof parapet', (-30.16, 0, 10.34), (.18, 32.2, .38), m['frame'], .025)
    # Contemporary administrative frontage: long glazing, deep mullions,
    # pale horizontal slabs and a projecting entrance roof.
    _box(site, 'administration frontage', (-17.3, -18.1, 3.87), (24, 4.1, 7.45), m['wall_dark'], .055)
    _box(site, 'office front glazing', (-17.3, -20.18, 4.0), (23.55, .055, 6.65), m['glass'], .008)
    _box(site, 'office west glazing', (-29.34, -18.15, 4.0), (.05, 3.8, 6.65), m['glass'], .008)
    office = _Batch()
    for x in [-29.1 + i * 1.47 for i in range(17)]:
        office.box((x, -20.25, 4.0), (.065, .14, 6.8))
    for z in (.61, 3.88, 7.39):
        office.box((-17.3, -20.26, z), (24.2, .22, .16), 1)
    office.object('office mullions and floor edges', [m['frame'], m['wall']], site)
    _box(site, 'administration thin overhang', (-17.3, -18.3, 7.73), (24.7, 4.7, .2), m['roof'], .035)
    _box(site, 'entrance canopy', (-17.4, -21.15, 3.35), (7.7, 2.4, .19), m['roof'], .025)
    _box(site, 'entrance step', (-17.4, -20.7, .20), (8.0, 1.4, .26), m['concrete'], .035)
    _box(site, 'entry doors', (-17.4, -20.31, 1.55), (3.5, .1, 2.8), m['carglass'], .015)
    for x in (-19.15, -17.4, -15.65):
        _box(site, 'entry door frame', (x, -20.38, 1.6), (.065, .1, 2.9), m['frame'], .01)
    # Three loading bays on the right make the scale and industrial function
    # readable without turning the whole facade into a generic storage shed.
    bays = _Batch()
    for index, x in enumerate((3., 13., 23.)):
        _box(site, f'loading bay {index} dark surround', (x, -16.15, 2.73), (6.2, .22, 5.2), m['rubber'], .04)
        _box(site, f'loading bay {index} sectional door', (x, -16.29, 2.73), (5.5, .07, 4.75), m['roof'], .025)
        _box(site, f'loading bay {index} canopy', (x, -17.1, 5.51), (6.65, 2., .20), m['frame'], .035)
        _box(site, f'loading bay {index} apron', (x, -17.1, .19), (6.0, 2.0, .24), m['concrete'], .035)
        for j in range(8):
            bays.box((x, -16.34, .62 + j * .59), (5.45, .018, .025))
        for side in (-1, 1):
            bays.cylinder((x + side * 3.35, -17.6, .05), (x + side * 3.35, -17.6, 1.2), .10, .10, 12, 1)
    bays.object('loading door joints and safety bollards', [m['frame'], m['safety']], site)
    # High clerestory panes and roof service hardware.
    clerestory = _Batch()
    for x in (-25, -17, -9, -1, 7, 15, 23):
        clerestory.box((x, -16.075, 7.5), (5.8, .04, .75))
    clerestory.object('clerestory glazing', [m['glass']], site)
    ventilation = _Batch()
    for x, y in [(-22, 5.5), (-7, 8.5), (12, 8.5), (24, 4.5)]:
        _box(site, 'roof ventilation curb', (x, y, 10.43), (3.8, 2.9, .36), m['roof'], .045)
        _box(site, 'roof ventilation housing', (x, y, 10.98), (3.35, 2.45, .8), m['wall_dark'], .07)
        for j in range(10):
            ventilation.box((x - 1.42 + j * .315, y - 1.24, 11.01), (.09, .035, .52))
    ventilation.object('roof ventilation slats', [m['frame']], site)
    # Generic English lettering is architectural channel lettering, with no
    # manufacturer name, trademark, original site name or corporate livery.
    _box(site, 'sign pale fascia', (5, -16.16, 9.02), (44.5, .12, 1.7), m['wall'], .015)
    curve = bpy.data.curves.new(PREFIX + 'generic facade lettering', 'FONT')
    curve.body = 'ELECTRIC VEHICLE MANUFACTURING'
    curve.align_x = 'CENTER'
    curve.align_y = 'CENTER'
    curve.size = 1.12
    curve.space_character = 1.12
    curve.extrude = .025
    curve.bevel_depth = .003
    font = Path('C:/Windows/Fonts/seguisb.ttf')
    if font.is_file():
        curve.font = bpy.data.fonts.load(str(font))
    curve.materials.append(m['sign'])
    sign = bpy.data.objects.new(PREFIX + 'ELECTRIC VEHICLE MANUFACTURING sign', curve)
    site.objects.link(sign)
    sign.location = (5, -16.24, 9.05)
    sign.rotation_euler = (math.pi / 2, 0, 0)
    # At-grade landscaping; slightly irregular bed boundaries break the
    # rectangular presentation-platform look of the former geometry.
    beds = [(-42, -33, -29, 29), (34, 43, -29, 29), (-31, 32, 19, 30)]
    grass = _Batch()
    rng = random.Random(6103)
    for index, (x0, x1, y0, y1) in enumerate(beds):
        inset = .8
        _polygon(site, f'irregular planted bed {index}',
                 [(x0 + inset, y0, .018), (x1 - inset, y0 + .35, .018),
                  (x1, y0 + inset, .018), (x1 - .3, y1 - inset, .018),
                  (x1 - inset, y1, .018), (x0 + inset, y1 - .25, .018),
                  (x0, y1 - inset, .018), (x0 + .2, y0 + inset, .018)], m['grass'])
        for _ in range(2100 if index < 2 else 3400):
            x, y = rng.uniform(x0 + .55, x1 - .55), rng.uniform(y0 + .55, y1 - .55)
            height = rng.uniform(.08, .23)
            a = rng.uniform(0, math.tau)
            side = Vector((math.cos(a), math.sin(a), 0)) * rng.uniform(.012, .026)
            p = Vector((x, y, .025))
            base = len(grass.vertices)
            grass.vertices.extend([tuple(p - side), tuple(p + side),
                                   tuple(p + Vector((.02 * math.sin(a), .02 * math.cos(a), height)))])
            grass.faces.append((base, base + 1, base + 2))
            grass.indices.append(rng.randrange(len(leaves)))
    grass.object('individual groundcover blades', leaves, site)
    tree_positions = [(-37.4, -22, 7.6), (-38.0, -7.0, 8.5), (-37.4, 9.0, 8.0),
                      (-36, 24, 8.4), (38, -20, 7.9), (38.7, -5, 8.6),
                      (38, 11, 8.0), (36, 24, 8.1), (-22, 24, 7.3), (0, 25, 7.8), (22, 25, 7.2)]
    for index, (x, y, height) in enumerate(tree_positions):
        _tree(site, 610 + index * 13, x, y, height, m['bark'], leaves)
    # Several low, fine-leaf shrubs have the same branch/leaf construction,
    # rather than smooth green primitive spheres.
    for index, x in enumerate((-29, -26.6, -24.2, -10.4, -8, -5.6)):
        _tree(site, 810 + index * 17, x, -22.5, 1.35 + index % 2 * .18,
              m['bark'], leaves, animate=False)
    markings = _Batch()
    for x in (-31, -26, -21, 26, 31):
        markings.box((x, -28, .025), (.065, 5.5, .013))
    for x in (-29, -20, -11, -2, 7, 16, 25, 34):
        markings.box((x, -23.65, .025), (3.0, .105, .013))
    for j in range(5):
        markings.box((-17.4, -24.4 + j * .5, .028), (4.8, .22, .013))
    markings.object('physical road and parking paint', [m['paint']], site)
    _car(site, 'white staff vehicle', -28.5, -28, m['whitecar'], m['frame'], m['rubber'], m['roof'], m['carglass'], m['lamp'], math.pi / 2)
    _car(site, 'blue staff vehicle', -23.5, -28, m['bluecar'], m['frame'], m['rubber'], m['roof'], m['carglass'], m['lamp'], math.pi / 2)
    _car(site, 'silver logistics vehicle', 28.5, -28, m['silvercar'], m['frame'], m['rubber'], m['roof'], m['carglass'], m['lamp'], math.pi / 2)
    # Optional application: a plausible PV carport. Its collection is returned
    # separately so that it only appears at the application's 35-40 s beat.
    _box(pv, 'solar carport shallow canopy', (0, -26.5, 4.61), (22.3, 8.4, .13), m['roof'], .025)
    solar = _Batch()
    for x in (-10, 0, 10):
        for y in (-29.7, -23.3):
            solar.box((x, y, 2.28), (.16, .16, 4.5), 0)
        solar.box((x, -26.5, 4.48), (.16, 8.0, .2), 0)
    for i in range(10):
        for j in range(4):
            x, y = -9.9 + i * 2.2, -29.65 + j * 2.1
            solar.box((x, y, 4.735), (2.08, 1.97, .055), 1)
            for line in range(1, 4):
                solar.box((x - 1.01 + line * .505, y, 4.767), (.009, 1.9, .003), 2)
            solar.box((x, y, 4.767), (2.0, .012, .003), 2)
    solar.object('solar canopy supports and PV modules', [m['frame'], m['pv'], m['pvline']], pv)
    # These emitters are deliberately unlit in daytime; the solar director
    # can keyframe their emission to show a small natural night-time glow.
    for x in (-25, -12, 1, 14, 27):
        _box(site, 'warm facade luminaire cover', (x, -16.20, 6.44), (.6, .13, .09), m['night'], .012)
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = 1.
    return {
        'collection': site,
        'reference_center': (8., -7.5, 10.26),
        'reference_size': 1.0,
        'pv_collection': pv,
        'night_emitters': [m['glass'], m['night']],
        'metadata': {
            'main_building_dimensions_m': [60, 32, 10],
            'site_dimensions_m': [88, 64],
            'front_negative_y': True,
            'reference_center_m': [8., -7.5, 10.26],
            'reference_horizontal': True,
            'reference_area_m2': 1.,
            'generic_sign': 'ELECTRIC VEHICLE MANUFACTURING',
            'generic_architecture_no_manufacturer_association': True,
            'landscaping': '11 individually branched broadleaf trees, 6 shrubs, individual batched leaves and grass blades',
            'tree_canopies_are_not_spheres': True,
            'pv_application_separate_collection': True,
            'site_object_count': len(site.objects),
            'pv_object_count': len(pv.objects),
            'bounds_min_m': [-44, -32, -.21],
            'bounds_max_m': [44, 32, 11.6],
        },
    }
