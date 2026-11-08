"""Natural solar introduction with an explicit normal-plane/zenith geometry."""
import math
import bpy
from mathutils import Vector
from blender_pilot import box, polyline, visible, frame, emission
from common_v4 import camera_path
from factory_site_v6 import build_factory_site_v6
import solar_atmosphere_v6 as atmosphere
from director_intro_v6 import keys, intervals, label, hud_root, hud_line, dimensions, graphs
from retime_v9 import all_fcurves

DURATION=52
CUES=[
 (0,5,'GHI mede a potência solar recebida por unidade de área horizontal.'),
 (5,11,'Aqui temos um metro quadrado. A unidade do GHI é watt por metro quadrado.'),
 (11,18,'A direta normal, DNI, é medida num plano perpendicular aos raios, como este.'),
 (18,25,'Na horizontal, projetamos a luz direta pelo cosseno do ângulo com a vertical e somamos a luz difusa.'),
 (25,30,'Durante o dia, a luz varia. À noite, o GHI solar zera.'),
 (30,34,'As nuvens alteram a luz e a curva.'),
 (34,38,'O histórico registra esses ciclos e as mudanças da atmosfera.'),
 (38,42,'A previsão tenta antecipar a continuação dessa curva.'),
 (42,47,'Prever o recurso solar pode apoiar estimativas de geração fotovoltaica.'),
 (47,52,'Essas estimativas podem orientar compras de energia, armazenamento e horários de consumo.'),
]


def mapped(t):
    anchors=[(0,0),(11,11),(16,25),(21,30),(25,34),(35,42),(40,52)]
    for (a,x),(b,y) in zip(anchors,anchors[1:]):
        if t<=b:return x+(t-a)*(y-x)/(b-a)
    return 52+(t-40)*2


def retime_actions(actions):
    for action in actions:
        for curve in all_fcurves(action):
            for point in curve.keyframe_points:
                positions=[point.co.x,point.handle_left.x,point.handle_right.x]
                for value,old in zip((point.co,point.handle_left,point.handle_right),positions):
                    value.x=mapped((old-1)/30)*30+1
            curve.update()


def hud_text(root,name,text,xy,size,mat,a,b):
    return label('V9 '+name,text,(xy[0],xy[1],.04),size,mat,a,b,root)


def geometry(scene,r,white,muted,cyan):
    direction=Vector(atmosphere.solar_state_at(12)['direction']).normalized()
    up=Vector((0,0,1));horizontal=Vector((direction.x,direction.y,0)).normalized()
    theta=math.acos(direction.dot(up))
    # This is a measurement/reference plane facing the Sun, NOT the roof.
    center=r+direction*6.5
    u=direction.cross(up).normalized();v=direction.cross(u).normalized()
    corners=[center+u*x+v*y for x,y in [(-1.2,-1.2),(1.2,-1.2),(1.2,1.2),(-1.2,1.2)]]
    border=polyline('V9 DNI plane perpendicular to beam',corners,cyan,.035,True);visible(border,11.8,24.95)
    bpy.ops.mesh.primitive_plane_add(size=2.4,location=center)
    plane=bpy.context.object;plane.name='V9 tilted DNI reference plane'
    plane.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    mat=bpy.data.materials.new('V9 translucent DNI reference surface');mat.use_nodes=True
    mat.surface_render_method='BLENDED';tree=mat.node_tree;tree.nodes.clear()
    out=tree.nodes.new('ShaderNodeOutputMaterial');clear=tree.nodes.new('ShaderNodeBsdfTransparent')
    ink=tree.nodes.new('ShaderNodeEmission');ink.inputs['Color'].default_value=(.25,.55,.63,1);ink.inputs['Strength'].default_value=.45
    mix=tree.nodes.new('ShaderNodeMixShader');mix.inputs[0].default_value=.20
    tree.links.new(clear.outputs[0],mix.inputs[1]);tree.links.new(ink.outputs[0],mix.inputs[2]);tree.links.new(mix.outputs[0],out.inputs['Surface'])
    plane.data.materials.append(mat);plane.visible_shadow=False;visible(plane,11.8,24.95)
    # A local right-angle square compares the beam normal with an in-plane tangent.
    c=center+u*.8
    marker=polyline('V9 ray versus plane 90 degrees',[c+v*.55,c+v*.55+direction*.55,c+direction*.55],white,.025)
    visible(marker,12.5,18)
    label('V9 ninety degree label','90°',tuple(c+v*.9+direction*.9),.48,white,12.5,18,billboard=True)
    label('V9 DNI plane explanation','Plano de medida da DNI',tuple(center+v*2.2),.50,white,12.2,18,billboard=True)
    # The roof's normal is vertical. theta_z is BETWEEN this normal and the Sun direction.
    normal=polyline('V9 vertical roof normal',[r,r+up*9],cyan,.025);visible(normal,18,24.95)
    arc=[r+(up*math.cos(theta*i/40)+horizontal*math.sin(theta*i/40))*3.9 for i in range(41)]
    obj=polyline('V9 solar zenith angle arc',arc,white,.035);visible(obj,18,24.95)
    label('V9 actual solar zenith label','θz ≈ '+str(round(math.degrees(theta)))+'°',tuple(r+(up*math.cos(theta/2)+horizontal*math.sin(theta/2))*4.6),.55,white,18,24.95,billboard=True)
    label('V9 vertical normal explanation','Vertical',tuple(r+up*5.5+Vector((2.0,0,0))),.48,cyan,18,24.95,billboard=True)
    root=hud_root(scene,'V9 irradiance definitions')
    hud_text(root,'GHI equation','GHI = DNI · cos(θz) + DHI',(0,2.55),.34,white,11,25)
    hud_text(root,'DNI plain definition','DNI: medida de frente para os raios',(0,2.08),.20,white,11,18)
    hud_text(root,'horizontal projection','DNI · cos(θz): parte direta na horizontal',(0,2.08),.20,white,18,25)
    hud_text(root,'diffuse plain definition','DHI: luz espalhada pelo céu, recebida na horizontal',(0,1.72),.18,cyan,19.2,25)
    return {'sun_direction_unit':list(direction),'zenith_angle_degrees':math.degrees(theta),
        'dni_plane_normal_dot_sun_direction':1.0,'ray_and_plane_tangent_angle_degrees':90,
        'horizontal_direct_projection_factor':direction.z,'diffuse_horizontal_refers_to_receiver_not_ray_direction':True}


def application(scene,white,muted,cyan):
    root=hud_root(scene,'V9 potential industrial applications')
    hud_text(root,'application context','Possíveis aplicações industriais',(0,2.45),.30,white,42,52)
    hud_text(root,'resource to PV','Recurso solar previsto  →  estimar geração FV',(0,1.93),.25,cyan,42,47)
    hud_text(root,'PV input qualification','com dados e modelo do sistema fotovoltaico',(0,1.53),.17,white,43.3,47)
    for i,(x,title) in enumerate([(-2.8,'Compra de energia'),(0,'Armazenamento'),(2.8,'Horários de consumo')]):
        hud_text(root,'application '+str(i),title,(x,1.28),.20,white,47+i*.12,52)
        hud_line(root,'application connector '+str(i),[(0,2.05,0),(x,1.66,0)],muted,47,52,draw=.65,radius=.008)
    # Three small line icons support the application words; the actual canopy remains 3D.
    hud_line(root,'battery icon',[(-.38,.55,0),(.38,.55,0),(.38,1.0,0),(-.38,1.0,0),(-.38,.55,0)],cyan,47.4,52,draw=.5,radius=.015)
    for x in [-.2,0,.2]:hud_line(root,'battery charge '+str(x),[(x,.65,0),(x,.9,0)],cyan,48,52,radius=.018)
    for x in [-3.05,-2.55]:hud_line(root,'grid pole '+str(x),[(x,.45,0),(x,.98,0)],cyan,47.3,52,radius=.012)
    hud_line(root,'grid wire',[(-3.13,.83,0),(-2.8,.72,0),(-2.46,.83,0)],cyan,47.3,52,draw=.6,radius=.012)
    circle=[(2.8+.27*math.cos(i*math.tau/48),.77+.27*math.sin(i*math.tau/48),0)for i in range(49)]
    hud_line(root,'consumption clock',circle,cyan,47.5,52,draw=.8,radius=.012)
    hud_line(root,'clock hands',[(2.8,.96,0),(2.8,.77,0),(2.98,.71,0)],cyan,48.1,52,radius=.012)


def build(scene):
    original_actions=set(bpy.data.actions)
    for obj in list(scene.objects):
        if obj.type=='LIGHT':bpy.data.objects.remove(obj,do_unlink=True)
    scene.world.node_tree.nodes.get('Background').inputs['Color'].default_value=(0,0,0,1)
    scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=0
    factory=build_factory_site_v6();r=Vector(factory['reference_center'])
    atmosphere.SOLAR_DISTANCE=72
    solar=atmosphere.build_solar_atmosphere_v6(scene,r)
    for light in solar['sky_fill_lights']:
        for curve in all_fcurves(light.data.animation_data.action):
            if curve.data_path=='energy':
                for point in curve.keyframe_points:
                    point.co.y*=6;point.handle_left.y*=6;point.handle_right.y*=6
    for obj in list(factory['collection'].objects):intervals(obj,[(0,25.12),(35,40.01)])
    for obj in list(factory['pv_collection'].objects):intervals(obj,[(35,40.01)])
    for material in factory['night_emitters']:
        socket=material.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength']
        for t in [0,15.99]+[16+i*.1 for i in range(51)]+[21.12,35,40]:
            socket.default_value=(.13 if 'glass' in material.name else .6) if atmosphere.solar_state_at(t)['elevation_degrees']<=0 else 0
            socket.keyframe_insert('default_value',frame=frame(t))
    data=bpy.data.lights.new('V9 dim nocturnal surroundings','AREA');data.color=(.24,.37,.62);data.size=100
    ambient=bpy.data.objects.new('V9 dim night ambient',data);scene.collection.objects.link(ambient)
    ambient.location=(10,-35,75);ambient.rotation_euler=(Vector((0,0,5))-ambient.location).to_track_quat('-Z','Y').to_euler()
    keys(data,'energy',[(t,45000 if atmosphere.solar_state_at(t)['elevation_degrees']<=0 else 0)for t in [0,15.99]+[16+i*.1 for i in range(51)]+[21.12,35,40]],True)
    dimensions(scene,r)
    white=emission('V9 solar white',(.90,.94,.98,1),1)
    muted=emission('V9 solar axes',(.25,.32,.38,1),1)
    cyan=emission('V9 solar cyan',(.19,.66,.75,1),1)
    graphs(scene,white,muted,cyan)
    arc=[tuple(r+Vector(atmosphere.solar_state_at(16+hour/24*5)['direction'])*72)for hour in [6+i*.1 for i in range(121)]]
    obj=polyline('V9 physical solar day arc',arc,muted,.035);visible(obj,16,21.05)
    shots=[(0,(45,-145,92),(0,-4,28)),(1.4,(43,-143,91),(0,-4,28)),(3.1,(57,-106,35),(1,-6,6)),
      (5.2,tuple(r+Vector((3.1,-4.5,4.4))),tuple(r)),(10.7,tuple(r+Vector((2.6,-4,4.1))),tuple(r)),
      (11.8,tuple(r+Vector((-10,-24,5))),tuple(r+Vector((0,0,5)))),(15.9,tuple(r+Vector((-9,-25,5))),tuple(r+Vector((0,0,5)))),
      (16,(48,-207,96),(0,-4,29)),(21,(43,-205,94),(0,-4,29)),(21.15,(65,-116,57),(1,-4,17)),
      (24,(57,-112,54),(1,-4,17)),(25.2,(54,-112,52),(1,-4,17)),(34.9,(54,-112,52),(1,-4,17)),
      (35,(43,-116,58),(0,-18,20)),(40,(38,-112,55),(0,-18,19))]
    camera_path(scene,[{'t':t,'location':loc,'target':target,'lens':36 if t<=1.4 else 28 if 11.8<=t<=15.9 else 43}for t,loc,target in shots])
    scene.camera.data.clip_end=2000;scene.camera.data.dof.use_dof=False
    retime_actions([a for a in bpy.data.actions if a not in original_actions])
    geometry_info=geometry(scene,r,white,muted,cyan)
    application(scene,white,muted,cyan)
    surface_root=hud_root(scene,'V9 horizontal area definition')
    hud_text(surface_root,'area words','Área horizontal de 1 m²',(0,1.8),.25,white,5.3,10.9)
    for key,value in {'use_volumetric_shadows':True,'volumetric_samples':32,'volumetric_tile_size':'8','volumetric_start':.1,'volumetric_end':300.}.items():
        if hasattr(scene.eevee,key):
            try:setattr(scene.eevee,key,value)
            except (TypeError,ValueError):pass
    scene.view_settings.exposure=.35
    scene.frame_end=52*30
    return {'duration':52,'cues':CUES,'qa_times':[7,14,20.5,26.5,28.5,31.8,39,44.5,49.5],
        'geometry':geometry_info,'reference_area_m2':1,'factory_generic':True,
        'pv_applications_potential_only':True,'electrical_generation_measured':False,
        'sources':['https://pvpmc.sandia.gov/modeling-guide/1-weather-design-inputs/irradiance-insolation/global-horizontal-irradiance/',
                   'https://power.larc.nasa.gov/docs/methodology/data/derived/derived-parameters/'],
        'v6_original_files_modified':False}
