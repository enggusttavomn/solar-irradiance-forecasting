"""Estilo fosco e render nativo 1080p/30 para os capitulos EA019.

``apply_style(scene, chapter_id)`` nao altera camera, duracao, movimento ou
geometria didatica. O Workbench ignora a intensidade dos nos Emission: os
focos existentes sao transferidos para animacao de ``diffuse_color`` uma
unica vez, sem callbacks por quadro. Retorna metadados JSON serializaveis.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import sys
import unicodedata
from pathlib import Path

import bpy


PALETTE = {
    'background': '#07090D', 'graphite': '#171C22',
    'white': '#F3F5F7', 'secondary': '#A9B2BE', 'axes': '#626D7A',
    'gold': '#E9B95F', 'coral': '#F28779',
    'cyan': '#58CADA', 'violet': '#AA91E8',
}
MODEL_CHAPTERS = frozenset((3, 7, 10, 13))


def linear_rgba(hex_color):
    channels = [int(hex_color.lstrip('#')[i:i+2], 16)/255 for i in (0, 2, 4)]
    return tuple(c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
                 for c in channels) + (1.0,)


def _plain(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c))


def _shader(material):
    if material.use_nodes:
        for node in material.node_tree.nodes:
            if node.type == 'EMISSION':
                return node, node.inputs['Color'], node.inputs['Strength']
        for node in material.node_tree.nodes:
            if node.type == 'BSDF_PRINCIPLED':
                return node, node.inputs['Base Color'], None
    return None, None, None


def _action_curves(owner):
    data = owner.animation_data
    if data and data.action:
        return list(data.action.fcurves)
    return []


def _choose_palette(material, chapter_id, source_color, emission):
    # New factory geometry already declares the approved sRGB design colors.
    declared = material.get('design_srgb_hex')
    if declared and isinstance(declared, str) and len(declared) == 7:
        return declared
    name = _plain(material.name)
    if not emission or 'preenchimento' in name:
        return PALETTE['graphite']
    if any(word in name for word in ('eixo', 'guia', 'meridiano', 'paralelo',
                                     'contorno discreto', 'moldura')):
        return PALETTE['axes']
    if 'costa' in name:
        return PALETTE['secondary']
    if chapter_id in MODEL_CHAPTERS:
        for word, key in [('lstm', 'coral'), ('transformer', 'cyan'),
                          ('informer', 'violet')]:
            if word in name:
                return PALETTE[key]
    if any(word in name for word in ('solar', 'sol ', 'radiacao', 'destaque')):
        return PALETTE['gold']
    hue, saturation, value = colorsys.rgb_to_hsv(*source_color[:3])
    if saturation > .3:
        if .025 < hue < .19:
            return PALETTE['gold' if chapter_id in (2, 8) else 'white']
        if chapter_id in MODEL_CHAPTERS:
            if hue > .94 or hue < .025:
                return PALETTE['coral']
            if .40 <= hue < .60:
                return PALETTE['cyan']
            if .60 <= hue <= .94:
                return PALETTE['violet']
        return PALETTE['secondary']
    return PALETTE['white' if value >= .35 else 'secondary']


def _hide_stage_object(obj):
    """Impedir que antigos keyframes hide_render reativem a decoracao."""
    name = _plain(obj.name)
    remove = name in ('piso', 'piso do palco')
    remove |= any(name.startswith(prefix) for prefix in (
        'grade longitudinal ', 'grade transversal ', 'grade longa ',
        'grade curta ', 'meridiano ', 'paralelo ',
    ))
    if remove and obj.type in ('MESH', 'CURVE', 'SURFACE'):
        for curve in _action_curves(obj):
            if curve.data_path == 'hide_render':
                # Boolean curves are constant, but set handles as well for a
                # complete, deterministic replacement of these keys only.
                for point in curve.keyframe_points:
                    point.co.y = point.handle_left.y = point.handle_right.y = 1
                    point.interpolation = 'CONSTANT'
        obj.hide_render = True
        return True
    return False


def _bake_emission_focus(material, color_socket, strength_socket, rgba):
    """Converter a intensidade animada, preservando suas chaves e rampas.

    A paleta permanece constante. Apenas o foco numerico da intensidade
    varia: clamp(Strength/1.8, .16, 1). Nao ha leitura de nos durante render.
    """
    if strength_socket is None:
        return None
    node_tree = material.node_tree
    strength_path = strength_socket.path_from_id('default_value')
    source_curves = _action_curves(node_tree)
    strength_curve = next((curve for curve in source_curves
                           if curve.data_path == strength_path), None)
    if strength_curve is None or not strength_curve.keyframe_points:
        return None
    color_path = color_socket.path_from_id('default_value')
    related = [curve for curve in source_curves
               if curve.data_path in (strength_path, color_path)]
    times = sorted({float(point.co.x) for curve in related
                    for point in curve.keyframe_points})
    for curve in list(_action_curves(material)):
        if curve.data_path == 'diffuse_color':
            material.animation_data.action.fcurves.remove(curve)
    factor = lambda value: max(.16, min(1., float(value)/1.8))
    for time in times:
        intensity = factor(strength_curve.evaluate(time))
        material.diffuse_color = tuple(c*intensity for c in rgba[:3]) + (1.,)
        material.keyframe_insert(data_path='diffuse_color', frame=time,
                                 group='EA019 foco Workbench')
    curves = [curve for curve in _action_curves(material)
              if curve.data_path == 'diffuse_color']
    originals = {round(float(key.co.x), 5): key
                 for key in strength_curve.keyframe_points}
    # Match the source horizontal easing. Transform Bezier handle values with
    # the same clamped intensity mapping; union-only extra color times use
    # AUTO_CLAMPED handles. The numeric focus stays within the approved range.
    for curve in curves:
        for key in curve.keyframe_points:
            source = originals.get(round(float(key.co.x), 5))
            key.interpolation = source.interpolation if source else 'BEZIER'
            key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'
            if source and source.interpolation == 'BEZIER' and curve.array_index < 3:
                channel = rgba[curve.array_index]
                key.handle_left_type = key.handle_right_type = 'FREE'
                key.handle_left = (source.handle_left.x,
                                   channel*factor(source.handle_left.y))
                key.handle_right = (source.handle_right.x,
                                    channel*factor(source.handle_right.y))
        curve.update()
    return {'material': material.name, 'source_path': strength_path,
            'source_key_count': len(strength_curve.keyframe_points),
            'baked_color_key_count': len(times), 'channels': 4,
            'mapping': 'clamp(Strength / 1.8, 0.16, 1.0)',
            'runtime_handlers': False}


def apply_style(scene, chapter_id):
    """Aplicar o estilo e devolver seu registro sem mudar camera ou tempos."""
    chapter_id = int(chapter_id)
    initial_frame = scene.frame_current
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.use_nodes = False
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.fps = 30
    scene.render.fps_base = 1
    scene.frame_step = 1
    scene.render.film_transparent = False
    scene.display.render_aa = '8'
    shade = scene.display.shading
    shade.light = 'STUDIO'
    shade.color_type = 'MATERIAL'
    shade.studiolight_rotate_z = .6
    shade.show_shadows = True
    shade.show_cavity = True
    shade.cavity_type = 'BOTH'
    shade.curvature_ridge_factor = 1.2
    shade.curvature_valley_factor = .8
    shade.cavity_ridge_factor = 1.1
    shade.cavity_valley_factor = 1
    shade.show_specular_highlight = False
    shade.show_object_outline = False
    shade.background_type = 'VIEWPORT'
    shade.background_color = linear_rgba(PALETTE['background'])[:3]
    if scene.world is None:
        scene.world = bpy.data.worlds.new('EA019 fundo preto fosco')
    scene.world.color = linear_rgba(PALETTE['background'])[:3]
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'None'
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'REALTIME'
    scene.render.ffmpeg.audio_codec = 'NONE'

    hidden = [obj.name for obj in scene.objects if _hide_stage_object(obj)]
    materials = {material for obj in scene.objects
                 for material in getattr(obj.data, 'materials', ())
                 if material is not None}
    colors, baked = [], []
    for material in sorted(materials, key=lambda item: item.name):
        node, color_socket, strength_socket = _shader(material)
        source = tuple(color_socket.default_value) if color_socket else tuple(material.diffuse_color)
        is_emission = node is not None and node.type == 'EMISSION'
        hex_color = _choose_palette(material, chapter_id, source, is_emission)
        rgba = linear_rgba(hex_color)
        material.diffuse_color = rgba
        material.roughness = .9
        material.metallic = 0
        material['ea019_style_v3_srgb'] = hex_color
        colors.append({'material': material.name, 'srgb_hex': hex_color,
                       'kind': 'line_or_marker' if is_emission else 'matte_surface'})
        animation = _bake_emission_focus(material, color_socket, strength_socket, rgba)
        if animation:
            baked.append(animation)
    scene.frame_set(initial_frame)
    return {'chapter_id': chapter_id, 'engine': scene.render.engine,
            'resolution': [1920, 1080], 'fps': 30, 'antialiasing': '8',
            'codec': 'H264', 'encoding_preset': 'REALTIME',
            'background_srgb_hex': PALETTE['background'],
            'palette': dict(PALETTE), 'hidden_decorative_objects': hidden,
            'materials': colors, 'baked_emission_focus': baked,
            'camera_and_timing_unchanged': True}


def _main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blend', type=Path, required=True)
    parser.add_argument('--chapter', type=int, required=True)
    parser.add_argument('--frame', type=int, default=241)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    bpy.ops.wm.open_mainfile(filepath=str(args.blend.resolve()))
    scene = bpy.context.scene
    metadata = apply_style(scene, args.chapter)
    scene.frame_set(args.frame)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = str(args.output.resolve())
    bpy.ops.render.render(write_still=True)
    args.output.with_suffix('.json').write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print('STYLE_V3_RENDERED '+json.dumps({'png': str(args.output),
          'baked_materials': len(metadata['baked_emission_focus'])}), flush=True)


if __name__ == '__main__':
    _main()
