"""Natural solar illumination and bounded atmospheric volumes for V6.

The light paths are explanatory scattering media, not measured radiance.
No yellow ray curves, arrow rays, emissive spheres, or global fog are used.
The solar cycle at 16--21 s covers exactly 24 h; solar contributions vanish
below the horizon. Factory and chart construction remain the caller's job.
"""
from __future__ import annotations

import math
import random

import bpy
from mathutils import Vector

FPS = 30
SOLAR_DISTANCE = 110.0


def _frame(second):
    return round(second * FPS) + 1


def _smooth(value):
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


def solar_state_at(second):
    """Return the shared explanatory Sun/lighting state for a local second."""
    if 16.0 <= second <= 21.0:
        hour = (second - 16.0) * 24.0 / 5.0
    else:
        hour = 10.0
    phase = math.pi * (hour - 6.0) / 12.0
    direction = Vector((-math.cos(phase), -.47 * math.sin(phase),
                        math.sqrt(1.0 - .47 ** 2) * math.sin(phase))).normalized()
    elevation = math.degrees(math.asin(direction.z))
    daylight = max(0.0, direction.z)
    attenuation = 1.0
    if 21.1 <= second <= 25.0:
        # A broad cloud crossing: direct fades much more than diffuse skylight.
        attenuation = 1.0 - .76 * math.exp(-((second - 22.55) / .68) ** 2)
    active = not (25.12 <= second < 35.0)
    if not active or daylight <= 0:
        direct = sky = 0.0
    else:
        direct = 2.8 * daylight ** .42 * attenuation
        sky = min(1.0, daylight / .40) * (.84 + .16 * attenuation)
    return {'hour': hour, 'direction': list(direction),
            'elevation_degrees': elevation, 'zenith_degrees': 90.0 - elevation,
            'direct_energy': direct, 'sky_factor': sky,
            'cloud_attenuation': attenuation, 'solar_active': active and daylight > 0}


def _smooth_keys(owner, path):
    animation = getattr(owner, 'animation_data', None)
    if not animation or not animation.action:
        return
    for curve in animation.action.fcurves:
        if curve.data_path != path:
            continue
        for key in curve.keyframe_points:
            key.interpolation = 'LINEAR'


def _key(owner, path, entries):
    for second, value in entries:
        setattr(owner, path, value)
        owner.keyframe_insert(path, frame=_frame(second))
    _smooth_keys(owner, path)


def _socket_key(socket, entries):
    for second, value in entries:
        socket.default_value = value
        socket.keyframe_insert('default_value', frame=_frame(second))


def _visibility(obj, intervals):
    events = {0.0: True}
    for start, end in intervals:
        events[start] = False
        events[end] = True
    for second, hidden in sorted(events.items()):
        obj.hide_render = hidden
        obj.keyframe_insert('hide_render', frame=_frame(second))


def _move_to_collection(obj, collection):
    for old in tuple(obj.users_collection):
        old.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def _math(tree, operation, first=None, second=None):
    node = tree.nodes.new('ShaderNodeMath')
    node.operation = operation
    for index, value in enumerate((first, second)):
        if value is None:
            continue
        if hasattr(value, 'node'):
            tree.links.new(value, node.inputs[index])
        else:
            node.inputs[index].default_value = value
    return node.outputs[0]


def _range(tree, socket, low, high, out_low, out_high):
    node = tree.nodes.new('ShaderNodeMapRange')
    node.interpolation_type = 'SMOOTHERSTEP'
    node.clamp = True
    node.inputs['From Min'].default_value = low
    node.inputs['From Max'].default_value = high
    node.inputs['To Min'].default_value = out_low
    node.inputs['To Max'].default_value = out_high
    tree.links.new(socket, node.inputs['Value'])
    return node.outputs['Result']


def _sun_card_material(name, halo=False):
    material = bpy.data.materials.new('V6 '+name)
    material.use_nodes = True
    if hasattr(material, 'surface_render_method'):
        # Alpha blending avoids the granular dither aureole. These are sky
        # images, not solar occluders; the shadow branch below stays clear.
        material.surface_render_method = 'BLENDED'
    if hasattr(material, 'use_backface_culling_shadow'):
        material.use_backface_culling_shadow = True
    tree = material.node_tree
    tree.nodes.clear()
    out = tree.nodes.new('ShaderNodeOutputMaterial')
    transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
    emission = tree.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = .36 if halo else 8.0
    emission.inputs['Color'].default_value = (1.0, .965, .90, 1.0)
    uv = tree.nodes.new('ShaderNodeTexCoord')
    distance = tree.nodes.new('ShaderNodeVectorMath')
    distance.operation = 'DISTANCE'
    tree.links.new(uv.outputs['UV'], distance.inputs[0])
    distance.inputs[1].default_value = (.5, .5, 0)
    r = distance.outputs['Value']
    if halo:
        alpha = _range(tree, r, .055, .5, .24, 0.0)
    else:
        alpha = _range(tree, r, .465, .5, 1.0, 0.0)
        # Limb darkening and fine photospheric granulation preserve a disk,
        # rather than shading it like a spherical yellow object.
        limb = _range(tree, r, .10, .49, 1.0, .59)
        noise = tree.nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 78
        noise.inputs['Detail'].default_value = 2.0
        tree.links.new(uv.outputs['UV'], noise.inputs['Vector'])
        grain = _range(tree, noise.outputs['Fac'], .1, .9, .93, 1.0)
        strength = _math(tree, 'MULTIPLY', _math(tree, 'MULTIPLY', limb, grain), 8.0)
        tree.links.new(strength, emission.inputs['Strength'])
    mix = tree.nodes.new('ShaderNodeMixShader')
    tree.links.new(alpha, mix.inputs[0])
    tree.links.new(transparent.outputs[0], mix.inputs[1])
    tree.links.new(emission.outputs[0], mix.inputs[2])
    shadow_path = tree.nodes.new('ShaderNodeLightPath')
    shadow_mix = tree.nodes.new('ShaderNodeMixShader')
    shadow_mix.name = 'Sky card is transparent to shadow rays'
    tree.links.new(shadow_path.outputs['Is Shadow Ray'], shadow_mix.inputs[0])
    tree.links.new(mix.outputs[0], shadow_mix.inputs[1])
    tree.links.new(transparent.outputs[0], shadow_mix.inputs[2])
    tree.links.new(shadow_mix.outputs[0], out.inputs['Surface'])
    return material


def _volume_material(name, colour, density, kind='cloud'):
    material = bpy.data.materials.new('V6 '+name)
    material.use_nodes = True
    tree = material.node_tree
    tree.nodes.clear()
    output = tree.nodes.new('ShaderNodeOutputMaterial')
    volume = tree.nodes.new('ShaderNodeVolumePrincipled')
    volume.inputs['Color'].default_value = (*colour, 1.0)
    volume.inputs['Anisotropy'].default_value = .24 if kind == 'cloud' else .28
    tree.links.new(volume.outputs['Volume'], output.inputs['Volume'])
    coords = tree.nodes.new('ShaderNodeTexCoord')
    subtract = tree.nodes.new('ShaderNodeVectorMath')
    subtract.operation = 'SUBTRACT'
    tree.links.new(coords.outputs['Generated'], subtract.inputs[0])
    subtract.inputs[1].default_value = (.5, .5, .5)
    if kind == 'cloud':
        distance = tree.nodes.new('ShaderNodeVectorMath')
        distance.operation = 'LENGTH'
        tree.links.new(subtract.outputs[0], distance.inputs[0])
        envelope = _range(tree, distance.outputs['Value'], .27, .49, 1.0, 0.0)
        noise = tree.nodes.new('ShaderNodeTexNoise')
        noise.noise_dimensions = '4D'
        noise.inputs['Scale'].default_value = 4.2
        noise.inputs['Detail'].default_value = 4.0
        noise.inputs['Roughness'].default_value = .72
        tree.links.new(coords.outputs['Generated'], noise.inputs['Vector'])
        _socket_key(noise.inputs['W'], [(0, .14), (25, .38), (40, .46)])
        billow = _range(tree, noise.outputs['Fac'], .30, .60, 0.0, 1.0)
        shape = _math(tree, 'MULTIPLY', envelope, billow)
    else:
        separate = tree.nodes.new('ShaderNodeSeparateXYZ')
        tree.links.new(subtract.outputs[0], separate.inputs[0])
        x2 = _math(tree, 'MULTIPLY', separate.outputs['X'], separate.outputs['X'])
        y2 = _math(tree, 'MULTIPLY', separate.outputs['Y'], separate.outputs['Y'])
        radial = _math(tree, 'SQRT', _math(tree, 'ADD', x2, y2))
        soft_radial = _range(tree, radial, .03, .48, 1.0, 0.0)
        # A narrow end feather keeps the shafts connected to the receiving
        # area. The former20% fade made them look suspended over the roof.
        end_fade = _range(tree, _math(tree, 'ABSOLUTE', separate.outputs['Z']), .475, .50, 1.0, 0.0)
        noise = tree.nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = 6.5
        noise.inputs['Detail'].default_value = 2.0
        travel = tree.nodes.new('ShaderNodeVectorMath')
        travel.operation = 'ADD'
        tree.links.new(coords.outputs['Generated'], travel.inputs[0])
        for second in (0,40):
            travel.inputs[1].default_value=(0,0,second*.22)
            travel.inputs[1].keyframe_insert('default_value',frame=_frame(second))
        tree.links.new(travel.outputs['Vector'], noise.inputs['Vector'])
        subtle_noise = _range(tree, noise.outputs['Fac'], .0, 1.0, .58, 1.0)
        shape = _math(tree, 'MULTIPLY', _math(tree, 'MULTIPLY', soft_radial, end_fade), subtle_noise)
        # A minute emissive term makes the scattering explanation visible on
        # black without turning the medium into a solid luminous line.
        if 'Emission Color' in volume.inputs:
            volume.inputs['Emission Color'].default_value = (*colour, 1.0)
            tree.links.new(_math(tree, 'MULTIPLY', shape, .075 if kind == 'direct' else .032),
                           volume.inputs['Emission Strength'])
    control = tree.nodes.new('ShaderNodeValue')
    control.name = 'Atmospheric visibility control'
    control.outputs[0].default_value = 1.0
    if kind != 'cloud' and volume.inputs['Emission Strength'].is_linked:
        source = volume.inputs['Emission Strength'].links[0].from_socket
        tree.links.new(_math(tree, 'MULTIPLY', source, control.outputs[0]), volume.inputs['Emission Strength'])
    tree.links.new(_math(tree, 'MULTIPLY', _math(tree, 'MULTIPLY', shape, density), control.outputs[0]),
                   volume.inputs['Density'])
    return material, control.outputs[0]


def _cone_volume(collection, name, start, end, bottom, top, material):
    end = Vector(end)
    start = Vector(start)
    axis = start - end
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=bottom, radius2=top,
                                    depth=axis.length, end_fill_type='NGON',
                                    location=(start + end) / 2)
    obj = _move_to_collection(bpy.context.object, collection)
    obj.name = 'V6 '+name
    obj.rotation_euler = axis.to_track_quat('Z', 'Y').to_euler()
    obj.data.materials.append(material)
    return obj


def _cube_volume(collection, name, location, dimensions, material):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = _move_to_collection(bpy.context.object, collection)
    obj.name = 'V6 '+name
    obj.dimensions = dimensions
    obj.data.materials.append(material)
    return obj


def build_solar_atmosphere_v6(scene, receiver):
    receiver = Vector(receiver)
    collection = bpy.data.collections.new('V6 natural solar atmosphere')
    scene.collection.children.link(collection)
    scene.unit_settings.system = 'METRIC'
    times = sorted(set([0, 10.9, 11, 15.95, 16, 21, 21.1, 21.15, 24.95,
                        25.0, 25.12, 34.99, 35, 40] +
                       [16 + i * .1 for i in range(51)] +
                       [21.15 + i * .1 for i in range(39)]))

    light_data = bpy.data.lights.new('V6 physical directional sunlight', 'SUN')
    light_data.energy = 2.5
    light_data.angle = math.radians(.65)
    light_data.use_shadow = True
    sun_light = bpy.data.objects.new('V6 physical directional sunlight', light_data)
    collection.objects.link(sun_light)
    sun_light.rotation_mode = 'QUATERNION'
    previous_quaternion = None
    sun_positions = []
    for second in times:
        state = solar_state_at(second)
        direction = Vector(state['direction'])
        rotation = (-direction).to_track_quat('-Z', 'Y')
        if previous_quaternion is not None and rotation.dot(previous_quaternion) < 0:
            rotation.negate()
        previous_quaternion = rotation.copy()
        sun_light.rotation_quaternion = rotation
        sun_light.keyframe_insert('rotation_quaternion', frame=_frame(second))
        light_data.energy = state['direct_energy']
        light_data.keyframe_insert('energy', frame=_frame(second))
        warm = _smooth(max(0.0, direction.z) / .45)
        light_data.color = (1.0, .68 + .29 * warm, .43 + .48 * warm)
        light_data.keyframe_insert('color', frame=_frame(second))
        sun_positions.append((second, receiver + direction * SOLAR_DISTANCE))
    _smooth_keys(sun_light, 'rotation_quaternion')
    _smooth_keys(light_data, 'energy')
    _smooth_keys(light_data, 'color')

    disk_material = _sun_card_material('luminous solar photosphere', False)
    halo_material = _sun_card_material('soft atmospheric solar aureole', True)
    sun_cards = []
    for name, size, material in [('solar photosphere', 2.7, disk_material),
                                  ('soft solar aureole', 11.0, halo_material)]:
        bpy.ops.mesh.primitive_plane_add(size=size)
        card = _move_to_collection(bpy.context.object, collection)
        card.name = 'V6 '+name
        card.data.materials.append(material)
        card.visible_shadow = False
        if scene.camera:
            track = card.constraints.new('TRACK_TO')
            track.name = 'Face active scene camera'
            track.target = scene.camera
            track.track_axis = 'TRACK_Z'
            track.up_axis = 'UP_Y'
        _key(card, 'location', sun_positions)
        _visibility(card, [(0, 16), (17.265, 19.735), (21.12, 25.1), (35, 40.01)])
        card['camera_facing_solar_card'] = True
        sun_cards.append(card)

    sky_fill_lights = []
    for name, location, watts, size, colour in [
        ('large sky hemisphere fill', (-8, -30, 80), 10500, 85, (.78, .87, 1.0)),
        ('east sky diffuse fill', (55, -22, 48), 2700, 65, (.79, .88, 1.0)),
        ('north sky diffuse fill', (-48, 30, 65), 2100, 75, (.83, .90, 1.0)),
    ]:
        data = bpy.data.lights.new('V6 '+name, 'AREA')
        data.shape = 'DISK'
        data.size = size
        data.color = colour
        data.use_shadow = True
        obj = bpy.data.objects.new('V6 '+name, data)
        collection.objects.link(obj)
        obj.location = Vector(location)
        obj.rotation_euler = (Vector((0, 0, 5)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        _key(data, 'energy', [(second, watts * solar_state_at(second)['sky_factor']) for second in times])
        sky_fill_lights.append(obj)

    direction = Vector(solar_state_at(12)['direction'])
    direct_material, direct_visibility = _volume_material('soft direct solar scattering',
                                                          (1.0, .975, .93), .022, 'direct')
    direct = _cone_volume(collection, 'soft direct solar scattering medium',
                          receiver + direction * min(43.0, SOLAR_DISTANCE*.72), receiver + Vector((0, 0, .10)),
                          1.1, 1.1, direct_material)
    direct['not_a_solid_ray'] = True
    _visibility(direct, [(11, 16), (21.15, 25)])
    _socket_key(direct_visibility, [(0, 0), (10.95, 0), (11.5, 1), (15.8, 1),
                                  (16, 0), (21.1, 0), (21.4, .55), (22.5, .15),
                                  (23.7, .55), (24.8, 0), (40, 0)])
    # Multiple broad, feathered media show sky directions; actual irradiance
    # is supplied by the broad sky AREA lights, without yellow ray graphics.
    diffuse_media = []
    for index, (offset, radius) in enumerate([
        ((-11, 8, 17), 1.5), ((12, 4, 20), 1.65), ((-8, -12, 18), 1.55),
        ((9, -10, 15), 1.35), ((1, 10, 24), 1.9),
    ]):
        material, factor = _volume_material('diffuse sky scattering '+str(index),
                                            (.74, .87, 1.0), .013, 'diffuse')
        target = receiver + Vector((.20 * math.cos(index), .20 * math.sin(index), .14))
        obj = _cone_volume(collection, 'diffuse sky scattering medium '+str(index),
                            receiver + Vector(offset), target, .45, radius*1.7, material)
        _visibility(obj, [(12.8 + index * .12, 16)])
        _socket_key(factor, [(0, 0), (12.7 + index * .12, 0),
                            (13.4 + index * .12, 1), (15.75, 1), (16, 0), (40, 0)])
        diffuse_media.append(obj)

    # Three cloud banks with multi-lobed, noise-cut, soft density volumes.
    # Geometry is invisible; density boundaries create the evolving silhouette.
    rng = random.Random(602)
    cloud_objects = []
    cloud_groups = []
    for bank in range(3):
        group = bpy.data.objects.new('V6 drifting cloud bank '+str(bank), None)
        collection.objects.link(group)
        if bank == 0:
            # Centre the main bank on the physical Sun-to-reference path
            # during the timed direct-light dip.
            height = 34.0
            intersection = receiver + direction * ((height-receiver.z)/direction.z)
            cx, cy = intersection.x, intersection.y
            positions = [(0, (-35, 14, 37)), (16, (-30, 12, 37)),
                         (21.1, (cx-24, cy, height)), (22.55, (cx, cy, height)),
                         (24.95, (cx+31, cy, height)), (35, (29, 12, 37)), (40, (33, 12, 37))]
        else:
            shift = 32 if bank == 1 else -32
            positions = [(0, (shift, 30 + 13 * bank, 42 + 5 * bank)),
                         (25, (shift + 8, 28 + 13 * bank, 42 + 5 * bank)),
                         (40, (shift + 12, 28 + 13 * bank, 42 + 5 * bank))]
        _key(group, 'location', positions)
        cloud_groups.append(group)
        profiles = [(-9.0, -.9, 0.0, 13.5, 10.5, 6.2),
                    (-4.1, .7, 2.0, 13.0, 11.0, 10.0),
                    (1.0, -.5, 4.0, 13.6, 11.4, 13.0),
                    (6.0, .7, 1.3, 12.2, 10.2, 8.6),
                    (10.4, -.5, -.3, 10.2, 9.0, 5.6)]
        for lobe, (lx, ly, lz, sx, sy, sz) in enumerate(profiles):
            material, factor = _volume_material(f'cloud density bank {bank} lobe {lobe}',
                                                (.94, .97, 1.0), .42 if bank == 0 else .31)
            local = Vector((lx, ly+rng.uniform(-.7, .7), lz+rng.uniform(-.3, .3)))
            obj = _cube_volume(collection, f'cumulus cloud volume {bank}-{lobe}', local,
                                (sx, sy, sz), material)
            obj.parent = group
            _visibility(obj, [(0, 25.05), (35, 40.01)])
            cloud_objects.append(obj)

    # Leave colour management/compositing to the director; provide exact
    # recommendations instead of changing existing text/bloom treatments.
    metadata = {
        'version': 6, 'sun_representation': 'near-white textured flat photosphere, limb darkening and feathered aureole',
        'sun_distance_m': SOLAR_DISTANCE, 'sun_angular_radius_exaggerated_for_legibility': True,
        'sun_spheres': 0, 'yellow_ray_curves': 0, 'ray_arrowheads': 0,
        'direct_representation': 'bounded soft volumetric air scattering aligned with physical sunlight',
        'diffuse_representation': 'five feathered sky scattering media plus three broad cool sky AREA fills',
        'cloud_representation': 'fifteen bounded procedural density volumes arranged in three multi-lobed cumulus banks',
        'cloud_shading': 'volumetric illumination and coordinated attenuation of directional sunlight',
        'cloud_objects': len(cloud_objects), 'global_volume': False,
        'night_solar_energy': 0, 'solar_cycle_seconds': [16, 21], 'solar_cycle_hours': [0, 24],
        'render_recommendations': {'engine': 'BLENDER_EEVEE_NEXT', 'samples': 24,
                                   'volumetric_tile_size': '8 or 16', 'volumetric_samples': 32,
                                   'colour_management': 'AgX Medium High Contrast',
                                   'glare': 'restrained FOG_GLOW; threshold>=2, small strength'},
        'sun_positions': {str(t): list(receiver + Vector(solar_state_at(t)['direction']) * SOLAR_DISTANCE)
                          for t in (0, 12, 14, 17.25, 18.5, 19.75, 20.5, 22.5, 37)},
        'default_receiver_m': list(receiver),
        'interpretation': 'Didactic solar/atmospheric animation; no weather model or PV performance simulation.'
    }
    scene.frame_set(1)
    return {'collection': collection, 'sun_light': sun_light,
            'sky_fill_lights': sky_fill_lights, 'cloud_objects': cloud_objects,
            'cloud_groups': cloud_groups, 'sun_cards': sun_cards,
            'direct_scattering_medium': direct, 'diffuse_scattering_media': diffuse_media,
            'metadata': metadata}
