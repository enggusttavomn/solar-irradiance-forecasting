"""Renderizar o piloto 3D com o Python integrado ao Blender 4.5 LTS.

Uso: blender --background --python blender_pilot.py -- --output-dir PASTA
     --engine BLENDER_EEVEE_NEXT --stills 120 450 750 --render
O piloto tem roteiro visual condensado; não substitui o plano do vídeo completo.
"""
import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

FPS = 30
GOLD = (1.0, .57, .13, 1)
CYAN = (.10, .75, .90, 1)
WHITE = (.88, .94, 1.0, 1)
SOFT = (.025, .047, .065, 1)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--engine', default='BLENDER_EEVEE_NEXT')
    p.add_argument('--resolution-percentage', type=int, default=100)
    p.add_argument('--samples', type=int, default=24)
    p.add_argument('--stills', type=int, nargs='*', default=[])
    p.add_argument('--render', action='store_true')
    return p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])


def frame(seconds):
    return round(seconds * FPS) + 1


def emission(name, color, strength=1):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()
    out = tree.nodes.new('ShaderNodeOutputMaterial')
    shader = tree.nodes.new('ShaderNodeEmission')
    shader.inputs['Color'].default_value = color
    shader.inputs['Strength'].default_value = strength
    tree.links.new(shader.outputs[0], out.inputs[0])
    return mat


def surface(name, color, metallic=0, roughness=.35, transmission=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = color
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Roughness'].default_value = roughness
    if 'Transmission Weight' in bsdf.inputs:
        bsdf.inputs['Transmission Weight'].default_value = transmission
    return mat


def polyline(name, points, material, radius=.012, cyclic=False):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 2
    curve.bevel_depth = radius
    curve.bevel_resolution = 2
    spline = curve.splines.new('POLY')
    spline.points.add(len(points)-1)
    for p, co in zip(spline.points, points):
        p.co = (*co, 1)
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def sphere(name, loc, radius, material, scale=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=loc)
    obj = bpy.context.object
    obj.name = name
    if scale:
        obj.scale = scale
    obj.data.materials.append(material)
    for p in obj.data.polygons:
        p.use_smooth = True
    return obj


def box(name, loc, dimensions, material, bevel=.04):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = dimensions
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new('Bordas suaves', 'BEVEL')
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new('Normais', 'WEIGHTED_NORMAL')
    return obj


def visible(obj, start=0, end=30):
    obj['visible_start_seconds'] = start
    obj.hide_render = True
    obj.keyframe_insert(data_path='hide_render', frame=1)
    obj.hide_render = False
    obj.keyframe_insert(data_path='hide_render', frame=frame(start))
    obj.hide_render = True
    obj.keyframe_insert(data_path='hide_render', frame=frame(end))


def reveal(obj, start, duration):
    obj.data.bevel_factor_end = 0
    obj.data.keyframe_insert('bevel_factor_end', frame=frame(start))
    obj.data.bevel_factor_end = 1
    obj.data.keyframe_insert('bevel_factor_end', frame=frame(start+duration))


def scale_exit(obj, seconds=19.0, end=20.0):
    old = obj.scale.copy()
    obj.keyframe_insert(data_path='scale', frame=frame(seconds))
    obj.scale = (0.001, .001, .001)
    obj.keyframe_insert(data_path='scale', frame=frame(end))
    obj.scale = old
    visible(obj, obj.get('visible_start_seconds', 0), end)


def wire_box(name, a, b, material, radius=.012):
    x0,y0,z0 = a
    x1,y1,z1 = b
    points = [(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
              (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    edges = [(0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),(0,4),(1,5),(2,6),(3,7)]
    return [polyline(f'{name} {i:02d}', [points[j],points[k]], material, radius) for i,(j,k) in enumerate(edges)]


def setup(args):
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.name = 'Piloto GHI — laboratório de luz'
    scene.render.engine = args.engine
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = args.resolution_percentage
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = 900
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = 'RGB'
    if args.engine == 'CYCLES':
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.device = 'CPU'
        scene.cycles.max_bounces = 4
    elif hasattr(scene, 'eevee'):
        if hasattr(scene.eevee, 'taa_render_samples'):
            scene.eevee.taa_render_samples = args.samples
        if hasattr(scene.eevee, 'use_raytracing'):
            scene.eevee.use_raytracing = False
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (.003, .006, .010, 1)
    bg.inputs['Strength'].default_value = .12
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = 0
    scene.use_nodes = True
    nodes = scene.node_tree.nodes
    nodes.clear()
    render = nodes.new('CompositorNodeRLayers')
    glow = nodes.new('CompositorNodeGlare')
    glow.glare_type = 'FOG_GLOW'
    glow.quality = 'MEDIUM'
    # Blender 4.5 keeps the legacy properties; their new socket equivalents
    # can be set when exposed without depending on a particular UI locale.
    if hasattr(glow, 'threshold'):
        glow.threshold = 1.5
    if hasattr(glow, 'size'):
        glow.size = 8
    output = nodes.new('CompositorNodeComposite')
    scene.node_tree.links.new(render.outputs['Image'],glow.inputs['Image'])
    scene.node_tree.links.new(glow.outputs['Image'],output.inputs['Image'])
    bpy.ops.object.camera_add(location=(7.8,-13.8,8.2))
    cam = bpy.context.object
    cam.name = 'Câmera de explicação'
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = 12.8
    cam.rotation_euler = (Vector((0,0,1.9))-cam.location).to_track_quat('-Z','Y').to_euler()
    scene.camera = cam
    # Gentle dolly and orbit; orthographic projection preserves readable curves.
    cam.keyframe_insert('location',frame=1)
    cam.keyframe_insert('rotation_euler',frame=1)
    cam.location = (6.8,-14.2,8.5)
    cam.rotation_euler = (Vector((0,0,1.8))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.keyframe_insert('location',frame=frame(18))
    cam.keyframe_insert('rotation_euler',frame=frame(18))
    cam.location = (5.0,-15.0,8.2)
    cam.rotation_euler = (Vector((0,0,1.7))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.keyframe_insert('location',frame=frame(22))
    cam.keyframe_insert('rotation_euler',frame=frame(22))
    cam.location = (4.2,-15.0,7.6)
    cam.rotation_euler = (Vector((0,0,1.7))-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.keyframe_insert('location',frame=900)
    cam.keyframe_insert('rotation_euler',frame=900)
    for name,loc,power,color,size in [
        ('Luz suave',(1,-4,7),1000,(.65,.82,1),7),
        ('Contorno quente',(-4,1,6),1400,(1,.59,.21),5),
        ('Recorte ciano',(5,3,4),650,(.15,.55,.75),4)]:
        bpy.ops.object.light_add(type='AREA',location=loc)
        lamp=bpy.context.object
        lamp.name=name
        lamp.data.energy=power
        lamp.data.color=color
        lamp.data.shape='DISK'
        lamp.data.size=size
        lamp.rotation_euler=(Vector((0,0,1))-lamp.location).to_track_quat('-Z','Y').to_euler()
    return scene


def physical_scene():
    raymat = emission('Radiação direta · amarelo', GOLD, 3.0)
    diffusemat = emission('Radiação difusa · amarelo suave', (1,.71,.3,1), 1.9)
    edge = emission('Contorno da superfície',(.14,.42,.52,1),1.7)
    gridmat = emission('Grade discreta',(.018,.038,.050,1),.5)
    floor = surface('Preto acetinado',(.006,.011,.018,1),.5,.30)
    glass = surface('Superfície de medição',(.065,.19,.23,1),.25,.16,.35)
    cloudmat = surface('Atmosfera',(.31,.36,.42,1),0,.8)
    box('Piso',(0,0,-.13),(200,200,.12),floor,.02)
    for i in range(-11,12):
        polyline(f'Grade longitudinal {i}',[(i,-12,-.055),(i,12,-.055)],gridmat,.004)
        polyline(f'Grade transversal {i}',[(-12,i,-.055),(12,i,-.055)],gridmat,.004)
    physical_start=set(bpy.data.objects)
    plate=box('Área horizontal de referência',(.7,0,.26),(4.4,2.8,.18),glass,.075)
    scale_exit(plate,19,20)
    edges=wire_box('Borda do plano',(-1.5,-1.4,.17),(2.9,1.4,.35),edge,.013)
    for obj in edges:
        scale_exit(obj,19,20)
    sunmat = bpy.data.materials.new('Sol procedural')
    sunmat.use_nodes=True
    tree=sunmat.node_tree
    tree.nodes.clear()
    out=tree.nodes.new('ShaderNodeOutputMaterial')
    tex=tree.nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value=6
    tex.inputs['Detail'].default_value=4
    ramp=tree.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position=.15
    ramp.color_ramp.elements[0].color=(.8,.08,.004,1)
    ramp.color_ramp.elements[1].position=.8
    ramp.color_ramp.elements[1].color=(1,.62,.06,1)
    emit=tree.nodes.new('ShaderNodeEmission')
    emit.inputs['Strength'].default_value=2.2
    tree.links.new(tex.outputs['Fac'],ramp.inputs[0])
    tree.links.new(ramp.outputs[0],emit.inputs['Color'])
    tree.links.new(emit.outputs[0],out.inputs[0])
    sun=sphere('Sol',(-3.6,.45,4.5),.68,sunmat)
    scale_exit(sun,18.8,20)
    sun.rotation_euler.z=0
    sun.keyframe_insert('rotation_euler',frame=1)
    sun.rotation_euler.z=.35
    sun.keyframe_insert('rotation_euler',frame=frame(20))
    direction=Vector((-.65,.06,.76)).normalized()
    ray_points=[]
    for i,(x,y) in enumerate([(x,y) for x in (-.6,.55,1.7) for y in (-.7,.05,.8)]):
        end=Vector((x,y,.38))
        origin=end+direction*5.2
        obj=polyline(f'Raio direto {i}',[origin,end],raymat,.011)
        visible(obj,1.8,20)
        reveal(obj,1.8+i*.09,1.8)
        scale_exit(obj,19.2,20)
        ray_points.append((origin,end))
        particle=sphere(f'Fluxo de luz {i}',origin,.032,raymat)
        visible(particle,4,19.2)
        for axis in range(3):
            driver=particle.driver_add('location',axis).driver
            driver.expression=f'{end[axis]}+({origin[axis]-end[axis]})*(1-((frame/{FPS*2.6}+{i*.19})%1))'
    cloud_specs=[(-.75,.15,.12,.48),(-.30,.02,.16,.63),(.22,.05,.10,.50),(.65,.07,-.08,.41),(.02,-.3,-.14,.47),(-.42,-.26,-.13,.41)]
    meta=bpy.data.metaballs.new('Volume suave da nuvem')
    meta.resolution=.14
    meta.render_resolution=.09
    meta.threshold=.75
    cloud=bpy.data.objects.new('Nuvem explicativa',meta)
    bpy.context.collection.objects.link(cloud)
    for x,y,z,r in cloud_specs:
        element=meta.elements.new()
        element.co=(x,y,z)
        element.radius=r*1.55
    cloud.location=(.1,.45,2.8)
    cloud.scale=(1.12,.87,.76)
    cloud.data.materials.append(cloudmat)
    visible(cloud,10.4,20)
    cloud.location.x-=.45
    cloud.keyframe_insert('location',frame=frame(10.4))
    cloud.location.x+=.9
    cloud.keyframe_insert('location',frame=frame(19))
    scale_exit(cloud,19.0,20)
    for i,(origin,end) in enumerate([
        ((-.5,1.0,2.9),(-1.0,.7,.38)),((.3,.9,3.3),(.1,.35,.38)),
        ((1.4,1.1,3.3),(1.5,.7,.38)),((2.0,-.1,2.8),(2.2,-.4,.38)),
        ((-.7,-.8,3.0),(-.6,-.8,.38))]):
        # Distinct incoming directions illustrate atmospheric scattering.
        diff=polyline(f'Contribuição difusa {i}',[origin,end],diffusemat,.008)
        visible(diff,14,20)
        reveal(diff,14+i*.1,1.5)
        scale_exit(diff,19.3,20)
    # Keep the complete physical illustration inside the body area, below the
    # title and above the captions.  The floor remains at the shared scale.
    assembly=bpy.data.objects.new('Composição física',None)
    bpy.context.collection.objects.link(assembly)
    for obj in set(bpy.data.objects)-physical_start-{assembly}:
        obj.parent=assembly
    assembly.scale=(.70,.70,.70)
    assembly.location.z=.08


def pulse(x):
    phase=(x+5.3)%2.30
    return math.sin(math.pi*phase/1.7)**2 if phase<1.7 else 0


def temporal_scene():
    white=emission('Histórico · branco',WHITE,2.6)
    cyan=emission('Previsão e janela · ciano',CYAN,2.7)
    axis=emission('Eixos da série',(.08,.15,.19,1),1)
    line=polyline('Eixo temporal',[(-5.35,0,.37),(4.9,0,.37)],axis,.008)
    visible(line,20,30)
    reveal(line,20,.8)
    points=[]
    for i in range(250):
        x=-5.3+6.65*i/249
        amplitude=1.7+.22*math.sin(x*1.7)
        points.append((x,0,.40+amplitude*pulse(x)))
    curve=polyline('Histórico observado conceitual',points,white,.017)
    visible(curve,20,30)
    reveal(curve,20,4.0)
    for i,obj in enumerate(wire_box('Janela de entrada',(-.9,-.45,.38),(1.35,.45,2.75),cyan,.010)):
        visible(obj,24.8,30)
        reveal(obj,24.8+(i%4)*.06,.6)
    present=polyline('Separação presente-futuro',[(1.35,0,.35),(1.35,0,3.1)],white,.006)
    visible(present,25.2,30)
    reveal(present,25.2,.5)
    for i in range(21):
        xa=1.42+i*.165
        xb=xa+.095
        pp=[]
        for j in range(4):
            x=xa+(xb-xa)*j/3
            pp.append((x,0,.40+1.85*pulse(x)))
        dash=polyline(f'Futuro ilustrativo {i}',pp,cyan,.017)
        visible(dash,25.7+i*.09,30)
        reveal(dash,25.7+i*.09,.5)


def main():
    args=parse_args()
    args.output_dir=args.output_dir.resolve()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    scene=setup(args)
    physical_scene()
    temporal_scene()
    scene.frame_set(1)
    bpy.context.preferences.filepaths.save_version=0
    blend=args.output_dir/'piloto_ghi_v1.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    for fr in args.stills:
        scene.frame_set(fr)
        scene.render.image_settings.file_format='PNG'
        scene.render.filepath=str(args.output_dir/f'frame_{fr:04d}.png')
        bpy.ops.render.render(write_still=True)
    scene.frame_set(1)
    scene.render.image_settings.file_format='FFMPEG'
    scene.render.ffmpeg.format='MPEG4'
    scene.render.ffmpeg.codec='H264'
    scene.render.ffmpeg.constant_rate_factor='HIGH'
    scene.render.ffmpeg.ffmpeg_preset='GOOD'
    scene.render.ffmpeg.audio_codec='NONE'
    scene.render.filepath=str(args.output_dir/'piloto_ghi_v1_sem_textos.mp4')
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    metadata={'fps':FPS,'frame_count':900,'duration_seconds':30,'engine':scene.render.engine,
              'resolution':[round(1920*args.resolution_percentage/100),round(1080*args.resolution_percentage/100)],
              'audio':'sem narração; legendas demonstrativas adicionadas na composição',
              'type':'piloto visual condensado, não vídeo completo','blender_version':bpy.app.version_string}
    (args.output_dir/'metadata_cena_piloto_v1.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.render:
        bpy.ops.render.render(animation=True)
    print('PILOT_BUILD_OK '+json.dumps(metadata,ensure_ascii=True))


if __name__=='__main__':
    main()
