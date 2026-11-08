"""Natural colour and surface treatment for the existing EA019 animation.

The material pass changes no object shape, visibility, trajectory or camera.
Large educational objects receive matte coloured surfaces, while small data
lines and labels retain enough self illumination to stay readable on black.
EEVEE is the PBR path; Workbench is a softer, non-metallic preview alternative.
"""
from __future__ import annotations

import colorsys
from collections import Counter, defaultdict
import math
import unicodedata

import bpy
from mathutils import Vector


BACKGROUND = '#07090D'
PALETTE = {
    'coral': '#EC8061', 'coral_body': '#D96D50',
    'cyan': '#40BACE', 'cyan_body': '#269CAF',
    'violet': '#AD8DDE', 'violet_body': '#9474CE',
    'gold': '#F0B84C', 'body': '#526A7C', 'graphite': '#405664',
    'white': '#F3F5F7', 'secondary': '#BBC7D0', 'axes': '#7C8C9A',
}
SOURCE_COLOURS = {
    '#F28779': 'coral', '#A85E56': 'coral_body',
    '#58CADA': 'cyan', '#387F8C': 'cyan_body',
    '#AA91E8': 'violet', '#706093': 'violet_body',
    '#E9B95F': 'gold', '#171C22': 'graphite', '#252D36': 'graphite',
    '#344456': 'body', '#A9B2BE': 'secondary', '#626D7A': 'axes',
    '#F3F5F7': 'white',
}


def _plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c))


def _rgba(code):
    values = [int(code.lstrip('#')[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
                 for c in values)+(1.,)


def _hex(color):
    def srgb(value):
        value = max(0., min(1., value))
        return value*12.92 if value <= .0031308 else 1.055*value**(1/2.4)-.055
    return '#'+''.join(f'{round(srgb(c)*255):02X}' for c in color[:3])


def _curves(owner):
    data = getattr(owner, 'animation_data', None)
    return list(data.action.fcurves) if data and data.action else []


def _source_colour(mat):
    for key in ('v5_source_srgb_hex', 'design_srgb_hex', 'ea019_style_v3_srgb'):
        code = mat.get(key)
        if isinstance(code, str) and len(code) == 7:
            return code.upper()
    return _hex(mat.diffuse_color)


def _target_colour(mat, role):
    source = _source_colour(mat)
    if source in SOURCE_COLOURS:
        return PALETTE[SOURCE_COLOURS[source]]
    # Respect other explicitly authored colours, especially physical materials
    # on the replacement factory. Only old neutral display surfaces are lifted.
    if role == 'panel':
        r, g, b, _ = _rgba(source)
        if max(r, g, b) < .075:
            return PALETTE['body']
    return source


def _role(obj, mat):
    if obj.type == 'FONT':
        return 'font'
    if obj.type == 'CURVE':
        return 'line'
    name = _plain(obj.name+' '+mat.name)
    if any(word in name for word in ('texto', 'rotulo')):
        return 'font'
    if any(word in name for word in ('particula', 'pulso', 'contribuicao',
                                     'consulta movel', 'ponto de consulta',
                                     'fotons', 'fluxo ghi entra', 'informacao em movimento')):
        return 'marker'
    if any(word in name for word in ('vidro', 'painel', 'laje', 'moldura', 'placa')):
        return 'panel'
    if any(word in name for word in ('metal', 'aluminio', 'aco', 'chapa', 'telhado')):
        return 'metal'
    return 'solid'


def _animated_factors(mat, source_hex):
    """Capture existing V3/V4 focus curves without changing their actions."""
    diffuse = [f for f in _curves(mat) if f.data_path == 'diffuse_color']
    strength = []
    if mat.use_nodes:
        for node in mat.node_tree.nodes:
            if node.type == 'EMISSION':
                socket = node.inputs.get('Strength')
                path = socket.path_from_id('default_value')
                strength += [f for f in _curves(mat.node_tree) if f.data_path == path]
    times = sorted({float(p.co.x) for f in diffuse+strength for p in f.keyframe_points})
    base = _rgba(source_hex)
    results = []
    for moment in times:
        factors = []
        if diffuse:
            ratios = [f.evaluate(moment)/base[f.array_index] for f in diffuse
                      if f.array_index < 3 and base[f.array_index] > .015]
            if ratios:
                factors.append(max(ratios))
        if strength:
            factors.append(strength[0].evaluate(moment)/1.8)
        factor = max(.16, min(1., min(factors) if factors else 1.))
        results.append((moment, factor))
    return results


def _material(source, role, preserve=False):
    old_hex = _source_colour(source)
    new_hex = old_hex if preserve else _target_colour(source, role)
    rgba = _rgba(new_hex)
    factors = _animated_factors(source, source.get('design_srgb_hex', old_hex))
    # Give each semantic role its own shader. A shared line material must not
    # force an entire mesh to behave like a light, or make a label shade dark.
    mat = source.copy()
    mat.name = source.name+' · V5 '+role
    mat['v5_source_srgb_hex'] = old_hex
    mat['design_srgb_hex'] = new_hex
    mat['v5_surface_role'] = role
    mat.diffuse_color = rgba
    if preserve:
        return mat, {'source': source.name, 'material': mat.name, 'role': role,
                     'source_srgb': old_hex, 'srgb': new_hex, 'preserved_pbr': True}
    if mat.animation_data and mat.animation_data.action:
        mat.animation_data.action = mat.animation_data.action.copy()
        for curve in list(mat.animation_data.action.fcurves):
            if curve.data_path == 'diffuse_color':
                mat.animation_data.action.fcurves.remove(curve)
    mat.use_nodes = True
    # A fresh node tree removes obsolete emission socket paths from the copy.
    # Their focus animation is baked explicitly below, so no RNA paths dangle.
    mat.node_tree.animation_data_clear()
    tree = mat.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    if role == 'font':
        shader = tree.nodes.new('ShaderNodeEmission')
        shader.name = 'V5 readable label'
        socket = shader.inputs['Color']
        socket.default_value = rgba
        shader.inputs['Strength'].default_value = 1.
        tree.links.new(shader.outputs[0], output.inputs['Surface'])
        roughness, metallic, emission = 1., 0., 1.
    else:
        shader = tree.nodes.new('ShaderNodeBsdfPrincipled')
        shader.name = 'V5 shaded surface'
        socket = shader.inputs['Base Color']
        socket.default_value = rgba
        roughness = {'solid': .57, 'panel': .66, 'line': .49,
                     'marker': .45, 'metal': .43}[role]
        metallic = .42 if role == 'metal' else 0.
        emission = {'line': .18, 'marker': .08}.get(role, 0.)
        shader.inputs['Roughness'].default_value = roughness
        shader.inputs['Metallic'].default_value = metallic
        shader.inputs['IOR'].default_value = 1.45
        if 'Specular IOR Level' in shader.inputs:
            shader.inputs['Specular IOR Level'].default_value = .24
        if 'Coat Weight' in shader.inputs:
            shader.inputs['Coat Weight'].default_value = 0.
        if 'Transmission Weight' in shader.inputs:
            shader.inputs['Transmission Weight'].default_value = 0.
        shader.inputs['Emission Color'].default_value = rgba
        shader.inputs['Emission Strength'].default_value = emission
        tree.links.new(shader.outputs['BSDF'], output.inputs['Surface'])
        if role in ('solid', 'panel'):
            # Subtle fine grain prevents a uniformly polished plastic surface.
            noise = tree.nodes.new('ShaderNodeTexNoise')
            noise.name = 'Fine matte surface'
            noise.inputs['Scale'].default_value = 65.
            noise.inputs['Detail'].default_value = 2.
            noise.inputs['Roughness'].default_value = .65
            bump = tree.nodes.new('ShaderNodeBump')
            bump.inputs['Strength'].default_value = .055
            bump.inputs['Distance'].default_value = .012
            tree.links.new(noise.outputs['Fac'], bump.inputs['Height'])
            tree.links.new(bump.outputs['Normal'], shader.inputs['Normal'])
    mat.roughness, mat.metallic = roughness, metallic
    for moment, factor in factors:
        colour = tuple(c*factor for c in rgba[:3])+(1.,)
        socket.default_value = colour
        socket.keyframe_insert('default_value', frame=moment)
        if role != 'font':
            shader.inputs['Emission Color'].default_value = colour
            shader.inputs['Emission Color'].keyframe_insert('default_value', frame=moment)
        mat.diffuse_color = colour
        mat.keyframe_insert('diffuse_color', frame=moment)
    for owner in (mat, tree):
        for curve in _curves(owner):
            for key in curve.keyframe_points:
                key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
    return mat, {'source': source.name, 'material': mat.name, 'role': role,
                 'source_srgb': old_hex, 'srgb': new_hex,
                 'roughness': roughness, 'metallic': metallic,
                 'emission_strength': emission, 'focus_keys': len(factors),
                 'fine_surface_grain': role in ('solid', 'panel')}


def _set(owner, key, value):
    if hasattr(owner, key):
        setattr(owner, key, value)
        return True
    return False


def _light(scene, name, location, target, energy, colour, size):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy, data.color, data.shape, data.size = energy, colour, 'DISK', size
    _set(data, 'use_shadow', True)
    _set(data, 'use_shadow_jitter', False)
    _set(data, 'shadow_filter_radius', 1.5)
    obj = bpy.data.objects.new(name, data)
    scene.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target)-obj.location).to_track_quat('-Z', 'Y').to_euler()
    return {'name': name, 'type': 'AREA', 'location': list(location),
            'energy_w': energy, 'colour': list(colour), 'size': size}


def _lighting(scene, chapter_id):
    retained = []
    for obj in list(scene.objects):
        if obj.type == 'LIGHT':
            if chapter_id == 2 and obj.data.type == 'SUN':
                retained.append(obj.name)
            else:
                bpy.data.objects.remove(obj, do_unlink=True)
    target = (0, 0, 2.25)
    if chapter_id == 2:
        # The new 24 m warehouse needs exterior sky-fill sources; the smaller
        # diagram setup would put two lamps inside the opaque building.
        lights = [
            _light(scene, 'V5 soft key', (8,-18,22), (0,0,3), 1800, (1.,.95,.88), 14),
            _light(scene, 'V5 sky fill', (-20,-12,12), (0,0,3), 3000, (.84,.92,1.), 18),
            _light(scene, 'V5 soft rim', (15,16,22), (0,0,3), 2200, (1.,.97,.92), 12),
        ]
    else:
        lights = [
            _light(scene, 'V5 soft key', (1.8,-5.5,9), target, 1450, (1.,.95,.88), 6),
            _light(scene, 'V5 sky fill', (-6,-3.5,4.5), target, 750, (.84,.92,1.), 5.5),
            _light(scene, 'V5 soft rim', (5,4,8), target, 1400, (1.,.97,.92), 5),
        ]
    if chapter_id == 2 and not retained:
        data = bpy.data.lights.new('V5 natural solar direction', 'SUN')
        data.energy, data.color, data.angle = 1.6, (1., .96, .88), math.radians(.65)
        obj = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(obj)
        obj.rotation_euler = tuple(math.radians(v) for v in (32, -24, -32))
        retained.append(obj.name)
    return {'areas': lights, 'retained_factory_sun': retained,
            'intent': 'broad neutral sources; subtle warm/cool separation, no coloured neon rim'}


def apply_natural_style(scene, chapter_id, engine='BLENDER_EEVEE_NEXT', samples=8):
    """Restyle a loaded V4 scene and return JSON-serializable metadata.

    Geometry, camera actions, object visibility, the frame range and FPS are
    preserved. For chapter 2, existing Principled materials and its SUN lamp
    are preserved, allowing the replacement factory to keep physical textures.
    """
    chapter_id = int(chapter_id)
    if engine == 'WORKBENCH':
        engine = 'BLENDER_WORKBENCH'
    if engine not in ('BLENDER_EEVEE_NEXT', 'BLENDER_WORKBENCH'):
        raise ValueError('Supported engines are BLENDER_EEVEE_NEXT and BLENDER_WORKBENCH')
    current_frame = scene.frame_current
    old_camera = scene.camera
    old_range = (scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)
    owners = defaultdict(list)
    source_map = {}
    for obj in list(scene.objects):
        slots = getattr(obj.data, 'materials', ())
        for index, mat in enumerate(slots):
            if mat:
                role = _role(obj, mat)
                key = (mat.as_pointer(), role)
                owners[key].append((obj, index))
                source_map[key] = mat
    treatment = []
    for key, bindings in owners.items():
        source = source_map[key]
        has_pbr = source.use_nodes and any(n.type == 'BSDF_PRINCIPLED' for n in source.node_tree.nodes)
        preserve = bool(source.get('v5_preserve_material')) or chapter_id == 2 and has_pbr
        mat, record = _material(source, key[1], preserve)
        for obj, index in bindings:
            obj.data.materials[index] = mat
        treatment.append(record)
    scene.render.engine = engine
    scene.use_nodes = False
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new('V5 dark studio background')
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get('Background')
    background.inputs['Color'].default_value = _rgba(BACKGROUND)
    background.inputs['Strength'].default_value = .5
    scene.world.color = _rgba(BACKGROUND)[:3]
    lights = _lighting(scene, chapter_id)
    if engine == 'BLENDER_EEVEE_NEXT':
        config = {}
        for key, value in {'taa_render_samples': max(1, int(samples)),
                           'taa_samples': max(1, int(samples)), 'use_raytracing': False,
                           'use_shadows': True, 'use_fast_gi': False,
                           'use_gtao': True, 'gtao_quality': .7, 'gtao_distance': 2.,
                           'shadow_ray_count': 1, 'shadow_step_count': 4,
                           'shadow_resolution_scale': .75,
                           'use_volumetric_shadows': False}.items():
            if _set(scene.eevee, key, value):
                config[key] = value
        scene.view_settings.view_transform = 'AgX'
        try:
            scene.view_settings.look = 'AgX - Medium High Contrast'
        except TypeError:
            scene.view_settings.look = 'None'
        scene.view_settings.exposure = .15
    else:
        shade = scene.display.shading
        shade.light, shade.color_type = 'STUDIO', 'MATERIAL'
        shade.studio_light = 'paint.sl'
        shade.studiolight_rotate_z = .15
        shade.show_specular_highlight = False
        shade.show_object_outline = False
        shade.show_shadows = True
        shade.show_cavity = True
        shade.cavity_type = 'BOTH'
        shade.curvature_ridge_factor, shade.curvature_valley_factor = .65, .8
        shade.cavity_ridge_factor, shade.cavity_valley_factor = .7, .85
        _set(shade, 'shadow_intensity', .45)
        shade.background_type = 'VIEWPORT'
        shade.background_color = _rgba(BACKGROUND)[:3]
        scene.display.render_aa = '8'
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'None'
        scene.view_settings.exposure = 0.
        config = {'studio_light': 'paint.sl', 'aa': '8', 'specular_highlights': False}
    scene.view_settings.gamma = 1.
    if scene.camera:
        scene.camera.data.dof.use_dof = False
    scene.frame_set(current_frame)
    assert scene.camera == old_camera
    assert old_range == (scene.frame_start, scene.frame_end, scene.render.fps, scene.render.fps_base)
    return {'version': 5, 'chapter_id': chapter_id, 'engine': engine,
            'background_srgb': BACKGROUND, 'palette': PALETTE,
            'material_count': len(treatment), 'roles': dict(Counter(r['role'] for r in treatment)),
            'materials': treatment, 'lights': lights, 'render_config': config,
            'compositor_enabled': False, 'raytracing_enabled': False,
            'camera_and_object_animation_unchanged': True,
            'timing_unchanged': True, 'focus_animation_baked_without_frame_handlers': True}
