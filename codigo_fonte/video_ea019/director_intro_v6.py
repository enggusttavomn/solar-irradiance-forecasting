"""Build only the revised 0:00-0:40 factory/solar introduction."""
import argparse
import json
import math
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector
from blender_pilot import setup, box, polyline, visible, reveal, frame, emission
from common_v4 import camera_path
from factory_site_v6 import build_factory_site_v6
import solar_atmosphere_v6 as atmosphere

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
QA_TIMES = [1, 3.5, 7, 10, 12, 14.5, 17, 18.5, 20.5, 22.5, 24.5, 27, 31, 34, 36.5, 39]


def keys(obj, path, values, linear=False):
    for second, value in values:
        setattr(obj, path, value)
        obj.keyframe_insert(path, frame=frame(second))
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            if curve.data_path == path:
                for key in curve.keyframe_points:
                    key.interpolation = 'LINEAR' if linear else 'BEZIER'
                    key.handle_left_type = key.handle_right_type = 'AUTO_CLAMPED'


def intervals(obj, ranges):
    events = {0: True}
    for start, end in ranges:
        events[start] = False
        events[end] = True
    for second, hidden in sorted(events.items()):
        obj.hide_render = hidden
        obj.keyframe_insert('hide_render', frame=frame(second))


def label(name, text, location, size, material, start, end, parent=None, billboard=False):
    data = bpy.data.curves.new(name, 'FONT')
    data.body = text
    data.align_x = 'CENTER'
    data.align_y = 'CENTER'
    data.size = size
    data.resolution_u = 4
    font = Path('C:/Windows/Fonts/segoeui.ttf')
    if font.is_file():
        data.font = bpy.data.fonts.load(str(font))
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    obj.location = location
    data.materials.append(material)
    if parent:
        obj.parent = parent
    if billboard:
        constraint = obj.constraints.new('COPY_ROTATION')
        constraint.target = bpy.context.scene.camera
    if hasattr(obj,'visible_shadow'):
        obj.visible_shadow=False
    visible(obj, start, end)
    return obj


def hud_root(scene, name, location=(0, 0, -12)):
    root = bpy.data.objects.new(name, None)
    scene.collection.objects.link(root)
    root.parent = scene.camera
    root.location = location
    return root


def hud_line(root, name, points, mat, start, end, draw=0, radius=.009):
    obj = polyline(name, points, mat, radius)
    obj.parent = root
    visible(obj, start, end)
    if draw:
        reveal(obj, start, draw)
    return obj


def daylight(hour):
    return max(0, math.sin(math.pi * ((hour % 24) - 6) / 12)) ** 1.45


def reveal_by_time(obj,points,start,end):
    distances=[0.]
    for a,b in zip(points,points[1:]):
        distances.append(distances[-1]+(Vector(b)-Vector(a)).length)
    total=distances[-1]
    keys(obj.data,'bevel_factor_end',[(start+(end-start)*i/(len(points)-1),value/total)
                                      for i,value in enumerate(distances)],True)


def graphs(scene, white, muted, forecast):
    # A compact 24-hour diagram remains synchronized to the actual light.
    root = hud_root(scene, 'V6 synchronized 24h diagram')
    x0, width, y0, height = -3.55, 2.85, .65, .85
    hud_line(root, 'V6 day plot axes', [(x0,y0+height,0),(x0,y0,0),(x0+width,y0,0)], muted, 16, 21.05, radius=.006)
    points = [(x0+width*i/240, y0+height*daylight(i/10),0) for i in range(241)]
    daycurve=hud_line(root, 'V6 24-hour irradiance curve', points, white, 16, 21.05, radius=.012)
    reveal_by_time(daycurve,points,16,21)
    for hour in [0,6,12,18,24]:
        label('V6 day hour '+str(hour),str(hour)+'h',(x0+width*hour/24,y0-.18,0),.17,white,16,21.05,root)
    label('V6 day plot quantity','GHI',(x0+.15,y0+height+.19,0),.17,white,16,21.05,root)
    cursor = hud_line(root,'V6 synchronized hour cursor',[(0,0,0),(0,height+.12,0)],forecast,16,21.05,radius=.006)
    keys(cursor,'location',[(16,(x0,y0,0)),(21,(x0+width,y0,0))],True)
    label('V6 daily cycle title','Ciclo de 24 h',(x0+width*.65,y0+height+.19,0),.17,white,16,21.05,root)
    for a,b,text in [(16,17.25,'Noite'),(17.25,19.75,'Dia'),(19.75,21.05,'Noite')]:
        marker=label('V6 day status '+str(a),text,(0,0,0),.17,white,a,b,root)
        keys(marker,'location',[(t,(max(x0+.3,min(x0+width-.3,x0+width*(t-16)/5)),y0-.49,0))
                                 for t in [a,b]],True)
    # A second synchronized trace makes cloud attenuation visible.
    cloud = hud_root(scene, 'V6 cloud effect trace')
    x0, width, y0, height = -3.55, 2.85, .65, .85
    hud_line(cloud,'V6 cloud graph axes',[(x0,y0+height,0),(x0,y0,0),(x0+width,y0,0)],muted,21.15,25.12,radius=.006)
    pts=[]
    for i in range(121):
        second=21.15+i/120*3.85
        state=atmosphere.solar_state_at(second)
        value=.19+.70*state['cloud_attenuation']
        pts.append((x0+width*i/120,y0+height*value,0))
    cloudcurve=hud_line(cloud,'V6 cloud irradiance dip',pts,white,21.15,25.12,radius=.012)
    reveal_by_time(cloudcurve,pts,21.15,25)
    label('V6 cloud trace title','Passagem de nuvens',(x0+width*.5,y0+height+.2,0),.17,white,21.15,25.12,cloud)
    # Full-screen history is a continuation of the same day/night grammar.
    main = hud_root(scene,'V6 history and dashed future')
    x0,x1,y0,height=-3.45,3.45,-.7,1.65
    present=1.0
    hud_line(main,'V6 history graph axes',[(x0,y0+height+.25,0),(x0,y0,0),(x1,y0,0)],muted,25,35,radius=.006)
    history=[]
    for i in range(401):
        u=i/400
        hour=72*u
        cloudmod=1-.35*math.exp(-((hour-34)/1.7)**2)-.22*math.exp(-((hour-59)/2.1)**2)
        history.append((x0+(present-x0)*u,y0+height*daylight(hour)*cloudmod,0))
    hud_line(main,'V6 observed history',history,white,25,35,draw=2.5,radius=.014)
    label('V6 observed history label','Histórico de GHI',(-1.3,1.48,0),.24,white,25.5,35,main)
    label('V6 plot power unit','W/m²',(x0+.25,y0+height+.48,0),.16,white,25,35,main)
    hud_line(main,'V6 present boundary',[(present,y0-.04,0),(present,y0+height+.19,0)],muted,28,35,radius=.006)
    label('V6 present text','Presente',(present,y0-.55,0),.18,white,28,35,main)
    label('V6 future text','Futuro',(2.25,1.48,0),.24,forecast,29,35,main)
    # The future is only a dashed continuation: no question mark or boxes.
    for k in range(23):
        u0=k/23
        u1=min(1,u0+.024)
        segment=[]
        for j in range(6):
            u=u0+(u1-u0)*j/5
            value=daylight(72+36*u)*(1-.19*math.exp(-((u-.39)/.075)**2))
            segment.append((present+(x1-present)*u,y0+height*value,0))
        hud_line(main,'V6 dashed future segment '+str(k),segment,forecast,29+k*.075,35,radius=.014)
    # Short brackets identify the observed context without a static card.
    hud_line(main,'V6 historical context bracket',[(x0,y0-.24,0),(x0,y0-.34,0),(present-.4,y0-.34,0),(present-.4,y0-.24,0)],muted,30,35,radius=.005)
    return {'day_cycle_chart':[16,21],'cloud_chart':[21.15,25.12],'history_chart':[25,35],
            'future_style':'dashed curve only','question_mark':False,'night_ghi_zero':True}


def dimensions(scene, receiver):
    r = Vector(receiver)
    dark = emission('V6 technical dimension ink',(.025,.055,.075,1),1)
    dark.surface_render_method='BLENDED'
    shadow=dark.node_tree.nodes.new('ShaderNodeLightPath')
    clear=dark.node_tree.nodes.new('ShaderNodeBsdfTransparent')
    mix=dark.node_tree.nodes.new('ShaderNodeMixShader')
    out=next(n for n in dark.node_tree.nodes if n.type=='OUTPUT_MATERIAL')
    ink=next(n for n in dark.node_tree.nodes if n.type=='EMISSION')
    dark.node_tree.links.new(shadow.outputs['Is Shadow Ray'],mix.inputs[0])
    dark.node_tree.links.new(ink.outputs[0],mix.inputs[1])
    dark.node_tree.links.new(clear.outputs[0],mix.inputs[2])
    dark.node_tree.links.new(mix.outputs[0],out.inputs['Surface'])
    edge = emission('V6 one square metre edge',(.08,.23,.30,1),1)
    mat = bpy.data.materials.new('V6 horizontal reference neutral paint')
    mat.use_nodes=True
    shader=mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(.52,.68,.73,1)
    shader.inputs['Roughness'].default_value=.8
    for t,color in [(0,(.52,.68,.73,1)),(10.8,(.52,.68,.73,1)),(11.1,(.12,.31,.40,1)),(16,(.12,.31,.40,1)),(25,(.12,.31,.40,1))]:
        shader.inputs['Base Color'].default_value=color
        shader.inputs['Base Color'].keyframe_insert('default_value',frame=frame(t))
    patch=box('V6 exact 1m2 horizontal reference',r,(1,1,.006),mat,.001)
    visible(patch,4,25.12)
    patch['area_m2']=1.0
    patch['horizontal']=True
    z=r.z+.014
    border=[(r.x-.5,r.y-.5,z),(r.x+.5,r.y-.5,z),(r.x+.5,r.y+.5,z),(r.x-.5,r.y+.5,z)]
    outline=polyline('V6 horizontal square perimeter',border,edge,.006,True)
    visible(outline,4,25.12)
    dimlines=[]
    for axis in ['x','y']:
        if axis=='x':
            a,b=Vector((r.x-.5,r.y-.73,z)),Vector((r.x+.5,r.y-.73,z))
            side=Vector((0,.045,0));text=(r.x,r.y-.90,z+.03)
            for x in [r.x-.5,r.x+.5]:
                dimlines.append([(x,r.y-.51,z),(x,r.y-.83,z)])
        else:
            a,b=Vector((r.x+.73,r.y-.5,z)),Vector((r.x+.73,r.y+.5,z))
            side=Vector((.045,0,0));text=(r.x+.94,r.y,z+.03)
            for y in [r.y-.5,r.y+.5]:
                dimlines.append([(r.x+.51,y,z),(r.x+.83,y,z)])
        direction=(b-a).normalized()
        dimlines.append([a,b])
        for tip,sign in [(a,1),(b,-1)]:
            dimlines.append([tip+direction*.085*sign+side,tip,tip+direction*.085*sign-side])
        label('V6 technical dimension '+axis,'1,00 m',text,.115,dark,5.5,11, billboard=True)
    for i,line in enumerate(dimlines):
        obj=polyline('V6 dimension extension and arrow '+str(i),line,dark,.0045)
        visible(obj,5.1,11)
    label('V6 measured surface area','1 m²',(r.x,r.y,z+.08),.16,dark,5.8,11,billboard=True)
    label('V6 light receiver annotation','1 m²',(r.x-1.3,r.y-.4,z+.30),.62,dark,11.1,16,billboard=True)
    return {'reference_area_m2':1,'dimensions_m':[1,1],'dimension_style':'technical extension lines and double-headed arrows'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--qa',action='store_true')
    parser.add_argument('--samples',type=int,default=24)
    parser.add_argument('--percentage',type=int,default=100)
    parser.add_argument('--qa-times',type=float,nargs='*')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'qa_3d').mkdir(exist_ok=True)
    scene=setup(SimpleNamespace(engine='BLENDER_EEVEE_NEXT',samples=args.samples,resolution_percentage=args.percentage))
    for obj in list(scene.objects):
        if obj.type=='LIGHT':bpy.data.objects.remove(obj,do_unlink=True)
    scene.world.node_tree.nodes.get('Background').inputs['Color'].default_value=(0,0,0,1)
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=0
    factory=build_factory_site_v6()
    r=Vector(factory['reference_center'])
    atmosphere.SOLAR_DISTANCE=72.0
    solar=atmosphere.build_solar_atmosphere_v6(scene,r)
    for light in solar['sky_fill_lights']:
        if light.data.animation_data and light.data.animation_data.action:
            for curve in light.data.animation_data.action.fcurves:
                if curve.data_path=='energy':
                    for point in curve.keyframe_points:
                        point.co.y*=6
                        point.handle_left.y*=6
                        point.handle_right.y*=6
    for obj in list(factory['collection'].objects):
        intervals(obj,[(0,25.12),(35,40.01)])
    for obj in list(factory['pv_collection'].objects):
        intervals(obj,[(35,40.01)])
    # Night-time office glow gives context while all solar contributions vanish.
    for material in factory['night_emitters']:
        socket=material.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength']
        for t in [0,15.99]+[16+i*.1 for i in range(51)]+[21.12,35,40]:
            state=atmosphere.solar_state_at(t)
            socket.default_value=(.13 if 'glass' in material.name else .6) if state['elevation_degrees']<=0 else 0
            socket.keyframe_insert('default_value',frame=frame(t))
    ambient_data=bpy.data.lights.new('V6 very dim nocturnal surroundings','AREA')
    ambient_data.energy=0;ambient_data.color=(.24,.37,.62);ambient_data.shape='DISK';ambient_data.size=100
    ambient=bpy.data.objects.new('V6 dim night ambient',ambient_data);scene.collection.objects.link(ambient)
    ambient.location=(10,-35,75);ambient.rotation_euler=(Vector((0,0,5))-ambient.location).to_track_quat('-Z','Y').to_euler()
    keys(ambient_data,'energy',[(t,45000 if atmosphere.solar_state_at(t)['elevation_degrees']<=0 else 0)
                               for t in [0,15.99]+[16+i*.1 for i in range(51)]+[21.12,35,40]],True)
    dimension_info=dimensions(scene,r)
    white=emission('V6 graph warm white',(.9,.94,.98,1),1)
    muted=emission('V6 graph subdued axes',(.25,.32,.38,1),1)
    future=emission('V6 graph forecast cyan',(.19,.66,.75,1),1)
    graph_info=graphs(scene,white,muted,future)
    # The physical arc uses the same position/direction function as the SUN.
    arc=[tuple(r+Vector(atmosphere.solar_state_at(16+hour/24*5)['direction'])*atmosphere.SOLAR_DISTANCE)
         for hour in [6+i*.1 for i in range(121)]]
    obj=polyline('V6 physical solar day arc',arc,muted,.035)
    visible(obj,16,21.05)
    # Diagram stages keep a fixed lens; the roof-level light shot is wider.
    shots=[
      (0,(45,-145,92),(0,-4,28)),(1.4,(43,-143,91),(0,-4,28)),(3.1,(57,-106,35),(1,-6,6)),
      (5.2,tuple(r+Vector((3.1,-4.5,4.4))),tuple(r)),
      (10.7,tuple(r+Vector((2.6,-4.0,4.1))),tuple(r)),
      (11.8,tuple(r+Vector((-10,-24,5))),tuple(r+Vector((0,0,5)))),
      (15.9,tuple(r+Vector((-9,-25,5))),tuple(r+Vector((0,0,5)))),
      (16.0,(48,-207,96),(0,-4,29)),(21.0,(43,-205,94),(0,-4,29)),
      (21.15,(65,-116,57),(1,-4,17)),(24.0,(57,-112,54),(1,-4,17)),
      (25.2,(54,-112,52),(1,-4,17)),(34.9,(54,-112,52),(1,-4,17)),
      (35.0,(43,-87,34),(0,-18,6)),(40.0,(38,-82,31),(0,-18,6))]
    camera_path(scene,[{'t':t,'location':loc,'target':target,'lens':36 if t<=1.4 else 28 if 11.8<=t<=15.9 else 43} for t,loc,target in shots])
    scene.camera.data.clip_end=2000
    scene.camera.data.dof.use_dof=False
    scene.render.fps=30;scene.render.fps_base=1;scene.frame_start=1;scene.frame_end=1200
    scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=args.percentage
    settings={'taa_render_samples':args.samples,'taa_samples':args.samples,'use_raytracing':False,
      'use_shadows':True,'use_fast_gi':False,'shadow_ray_count':1,'shadow_step_count':6,
      'shadow_resolution_scale':1.0,'use_volumetric_shadows':True,
      'volumetric_samples':32,'volumetric_tile_size':'8','volumetric_start':.1,'volumetric_end':300.}
    actual={}
    for key,value in settings.items():
        if hasattr(scene.eevee,key):
            try:setattr(scene.eevee,key,value);actual[key]=value
            except (ValueError,TypeError):pass
    scene.view_settings.view_transform='AgX'
    scene.view_settings.look='AgX - Medium High Contrast'
    scene.view_settings.exposure=.35
    # Only a restrained aureole blooms; ordinary curves and text stay sharp.
    glare=next((n for n in scene.node_tree.nodes if n.type=='GLARE'),None)
    if glare:
        if hasattr(glare,'threshold'):glare.threshold=2.2
        if hasattr(glare,'mix'):glare.mix=-.88
        if hasattr(glare,'size'):glare.size=7
    scene.render.image_settings.file_format='FFMPEG';scene.render.image_settings.color_mode='RGB'
    scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264'
    scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.ffmpeg.ffmpeg_preset='REALTIME';scene.render.ffmpeg.audio_codec='NONE'
    raw=OUT/'intro_00_40_3d_v6.mp4';scene.render.filepath=str(raw)
    scene.frame_set(1)
    bpy.context.preferences.filepaths.save_version=0
    blend=OUT/'intro_00_40_v6.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    manifest={'version':6,'scope_seconds':[0,40],'duration_seconds':40,'frame_count':1200,'fps':30,
      'resolution':[1920,1080],'blend':str(blend),'raw_mp4':str(raw),'qa_times':QA_TIMES,
      'factory':factory['metadata'],'solar':solar['metadata'],'reference':dimension_info,'graphs':graph_info,
      'render_config':actual,'reference_sources':[
        {'kind':'architecture','url':'https://www.hyundaimotorgroup.com/en/news/hyundai-motor-group-metaplant-america-celebrates-grand-opening-powering-us-economic-growth','role':'architectural vocabulary only; generic unbranded model'},
        {'kind':'scientific','file':'Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf','pages':[7,8,17,29],'equation':'GHI = DHI + DNI cos(theta_z)'}],
      'pv_application_potential_only':True,'pv_generation_estimated':False,'factory_name_generic':True,'v5_files_modified':False}
    (OUT/'manifesto_intro_v6.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.qa:
        scene.render.image_settings.file_format='PNG'
        for second in (args.qa_times if args.qa_times is not None else QA_TIMES):
            scene.frame_set(frame(second))
            scene.render.filepath=str(OUT/'qa_3d'/f't_{format(second,"g").replace(".","_")}.png')
            bpy.ops.render.render(write_still=True)
            print('V6_QA '+str(second),flush=True)
    print('V6_INTRO_PREPARED',flush=True)


if __name__=='__main__':main()
