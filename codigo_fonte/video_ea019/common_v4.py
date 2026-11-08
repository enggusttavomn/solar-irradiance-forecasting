"""Shared native 3D animation helpers for the continuous EA019 film."""
import math
from pathlib import Path
import bpy
from mathutils import Vector
from blender_pilot import box, sphere, polyline, visible, reveal, frame

PALETTE={'background':'#07090D','body':'#344456','white':'#F3F5F7','muted':'#A9B2BE',
         'gold':'#E9B95F','coral':'#F28779','cyan':'#58CADA','violet':'#AA91E8'}
_fonts={}

def rgba(code):
    v=[int(code.lstrip('#')[i:i+2],16)/255 for i in (0,2,4)]
    return tuple(x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in v)+(1,)

def material(name,code,emissive=False):
    mat=bpy.data.materials.new(name); mat.use_nodes=True
    color=rgba(code); mat.diffuse_color=color;mat['design_srgb_hex']=code
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=color
    shader.inputs['Roughness'].default_value=.3
    shader.inputs['Metallic'].default_value=.18
    if emissive:
        shader.inputs['Emission Color'].default_value=color
        shader.inputs['Emission Strength'].default_value=.5
    return mat

def keys(obj,path,values,linear=False):
    for t,value in values:
        setattr(obj,path,value);obj.keyframe_insert(path,frame=frame(t))
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            if fc.data_path==path:
                for p in fc.keyframe_points:
                    p.interpolation='LINEAR' if linear else 'BEZIER'
                    p.handle_left_type=p.handle_right_type='AUTO_CLAMPED'

def camera_path(scene,values):
    cam=scene.camera
    if cam is None:
        bpy.ops.object.camera_add();cam=bpy.context.object;scene.camera=cam
    cam.animation_data_clear();cam.data.animation_data_clear()
    cam.data.type='PERSP';cam.data.sensor_width=36;cam.data.clip_end=400
    for value in values:
        t=value['t'];cam.location=value['location']
        cam.rotation_euler=(Vector(value['target'])-cam.location).to_track_quat('-Z','Y').to_euler()
        cam.keyframe_insert('location',frame=frame(t));cam.keyframe_insert('rotation_euler',frame=frame(t))
        cam.data.lens=value.get('lens',48);cam.data.keyframe_insert('lens',frame=frame(t))
    for owner in (cam,cam.data):
        if owner.animation_data and owner.animation_data.action:
            for fc in owner.animation_data.action.fcurves:
                for p in fc.keyframe_points:
                    p.interpolation='BEZIER';p.handle_left_type=p.handle_right_type='AUTO_CLAMPED'
    return cam

def billboard_label(scene,name,text,loc,size=.32,color='#F3F5F7',start=0,end=415,align='CENTER'):
    curve=bpy.data.curves.new(name,'FONT');curve.body=text;curve.size=size
    curve.align_x=align;curve.align_y='CENTER';curve.space_line=1.12
    curve.extrude=.0015;curve.bevel_depth=.0006;curve.resolution_u=4
    path='C:/Windows/Fonts/seguisb.ttf' if size>.38 else 'C:/Windows/Fonts/segoeui.ttf'
    if path not in _fonts:
        _fonts[path]=bpy.data.fonts.load(path) if Path(path).is_file() else None
    if _fonts[path]:curve.font=_fonts[path]
    obj=bpy.data.objects.new(name,curve);bpy.context.collection.objects.link(obj);obj.location=loc
    curve.materials.append(material(name+' · texto',color,True))
    constraint=obj.constraints.new('COPY_ROTATION');constraint.target=scene.camera
    visible(obj,start,end);return obj

def trace(name,points,mat,a,b,draw=.8,radius=.025):
    obj=polyline(name,points,mat,radius);visible(obj,a,b);reveal(obj,a,draw);return obj

def block(name,loc,dims,mat,a,b,pop=.5):
    obj=box(name,loc,dims,mat,min(.07,min(dims)*.18));visible(obj,a,b)
    if pop:
        target=tuple(obj.scale);keys(obj,'scale',[(a,(.001,)*3),(a+pop,target)])
    return obj

def flow(name,path,mat,a,b,travel=2.0,count=4,radius=.065):
    objects=[]
    for i in range(count):
        start=a+i*travel/count
        obj=sphere(name+str(i),path[0],radius,mat);visible(obj,start,b)
        timeline=[];t=start
        while t<b:
            for j,pos in enumerate(path):
                timeline.append((min(b,t+travel*j/(len(path)-1)),pos))
            if t+travel<b:timeline.append((t+travel+.015,path[0]))
            t+=travel+.025
        keys(obj,'location',timeline,True);objects.append(obj)
    return objects

def orbit(scene,duration,target=(0,0,2.3),distance=16,lens=48,spread=1.5):
    return camera_path(scene,[{'t':0,'location':(spread,-distance,6.3),'target':target,'lens':lens},
      {'t':duration*.48,'location':(-spread*.65,-distance+.6,5.0),'target':target,'lens':lens+2},
      {'t':duration,'location':(spread*.4,-distance+.2,5.5),'target':target,'lens':lens}])
