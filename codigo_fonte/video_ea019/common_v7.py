"""Shared studio, timing and geometry for the revised educational sequence."""
from pathlib import Path
import math
import bpy
from mathutils import Vector
from blender_pilot import box, sphere, polyline, surface, emission, frame, visible, reveal

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
FPS=30
WHITE=(.88,.93,.97,1)
CYAN=(.10,.60,.76,1)
CORAL=(.90,.28,.20,1)
VIOLET=(.49,.30,.78,1)
GREEN=(.19,.55,.34,1)
GOLD=(.91,.61,.17,1)

def keys(obj,prop,values,linear=False):
    for second,value in values:
        setattr(obj,prop,value);obj.keyframe_insert(prop,frame=frame(second))
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            if curve.data_path==prop:
                for k in curve.keyframe_points:
                    k.interpolation='LINEAR' if linear else 'BEZIER'
                    k.handle_left_type=k.handle_right_type='AUTO_CLAMPED'
    return obj

def camera_key(scene,second,location,target,scale=17):
    cam=scene.camera;cam.location=location
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.ortho_scale=scale
    cam.keyframe_insert('location',frame=frame(second))
    cam.keyframe_insert('rotation_euler',frame=frame(second))
    cam.data.keyframe_insert('ortho_scale',frame=frame(second))

def label(name,text,location,size,material,start,end,billboard=True):
    data=bpy.data.curves.new(name,'FONT');data.body=text
    data.align_x='CENTER';data.align_y='CENTER';data.size=size;data.resolution_u=3
    font=Path('C:/Windows/Fonts/segoeui.ttf')
    if font.is_file():data.font=bpy.data.fonts.load(str(font))
    obj=bpy.data.objects.new(name,data);bpy.context.scene.collection.objects.link(obj)
    obj.location=location;data.materials.append(material)
    if billboard:
        c=obj.constraints.new('COPY_ROTATION');c.target=bpy.context.scene.camera
    else:obj.rotation_euler=(math.pi/2,0,0)
    obj.visible_shadow=False;visible(obj,start,end)
    return obj

def group(name,objects):
    root=bpy.data.objects.new(name,None);bpy.context.scene.collection.objects.link(root)
    for obj in objects:obj.parent=root
    return root

def grow(obj,start,duration=.7):
    size=tuple(obj.scale)
    return keys(obj,'scale',[(max(0,start-.01),(.001,.001,.001)),(start,(.001,.001,.001)),(start+duration,size)])

def arrow(name,a,b,material,start,end,radius=.014):
    a,b=Vector(a),Vector(b);direction=(b-a).normalized();side=Vector((-direction.z,0,direction.x))
    if side.length<.1:side=Vector((1,0,0))
    tip=b-direction*.19
    obj=polyline(name,[a,b,tip+side*.09,b,tip-side*.09],material,radius)
    visible(obj,start,end);reveal(obj,start,.7);return obj

def setup(duration,samples=16,percentage=100):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.render.engine='BLENDER_EEVEE_NEXT'
    scene.render.resolution_x=1920;scene.render.resolution_y=1080
    scene.render.resolution_percentage=percentage;scene.render.fps=FPS
    scene.frame_start=1;scene.frame_end=round(duration*FPS)
    scene.render.film_transparent=False;scene.world.use_nodes=True
    bg=scene.world.node_tree.nodes.get('Background');bg.inputs['Color'].default_value=(0,0,0,1);bg.inputs['Strength'].default_value=0
    scene.eevee.taa_render_samples=samples;scene.eevee.use_raytracing=False
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=.2;scene.use_nodes=False
    bpy.ops.object.camera_add(location=(0,-26,7.5));scene.camera=bpy.context.object
    scene.camera.name='Câmera contínua V7';scene.camera.data.type='ORTHO';scene.camera.data.ortho_scale=17
    camera_key(scene,0,(0,-26,7.5),(0,0,3),17)
    for name,loc,power,col,size in [('Softbox principal',(-6,-9,12),1900,(1,.93,.85),9),('Preenchimento',(8,-4,7),1300,(.73,.86,1),8),('Recorte',(-2,5,10),2200,(.83,.94,1),7)]:
        bpy.ops.object.light_add(type='AREA',location=loc);lamp=bpy.context.object;lamp.name=name
        lamp.data.energy=power;lamp.data.color=col;lamp.data.shape='DISK';lamp.data.size=size
        lamp.rotation_euler=(Vector((0,0,3))-lamp.location).to_track_quat('-Z','Y').to_euler()
    return scene
