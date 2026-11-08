"""A naturally coloured industrial site and horizontal irradiance explanation.

The architecture is illustrative. Geometry is in metres; the highlighted roof
reference is exactly 1 x 1 m. No sensor, PV installation or industrial energy
result is represented. This builder creates objects and animation, not renders.
"""
import math
import random
import bpy
from mathutils import Vector
from blender_pilot import box, sphere, polyline, visible, reveal, frame
from common_v4 import camera_path


def _rgba(code):
    values=[int(code.lstrip('#')[i:i+2],16)/255 for i in (0,2,4)]
    return tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values)+(1.,)


def _mat(name,code,rough=.6,metal=0,grain=0,emission=0):
    mat=bpy.data.materials.new('V5 factory '+name);mat.use_nodes=True
    mat.diffuse_color=_rgba(code);mat['design_srgb_hex']=code;mat['v5_preserve_material']=True
    node=mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value=mat.diffuse_color
    node.inputs['Roughness'].default_value=rough;node.inputs['Metallic'].default_value=metal
    if emission:
        node.inputs['Emission Color'].default_value=mat.diffuse_color
        node.inputs['Emission Strength'].default_value=emission
    if grain:
        tree=mat.node_tree;noise=tree.nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value=42 if name=='concrete' else 95
        noise.inputs['Detail'].default_value=2
        bump=tree.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.17
        bump.inputs['Distance'].default_value=grain
        tree.links.new(noise.outputs['Fac'],bump.inputs['Height'])
        tree.links.new(bump.outputs['Normal'],node.inputs['Normal'])
    return mat


def _keys(obj,path,entries):
    for t,value in entries:
        setattr(obj,path,value);obj.keyframe_insert(path,frame=frame(t))
    if obj.animation_data and obj.animation_data.action:
        for curve in obj.animation_data.action.fcurves:
            if curve.data_path==path:
                for key in curve.keyframe_points:
                    key.handle_left_type=key.handle_right_type='AUTO_CLAMPED'


def build_factory_v5(duration=35):
    scene=bpy.context.scene;before=set(bpy.data.objects);duration=float(duration)
    t=lambda value:value*duration/35
    m={
      'concrete':_mat('concrete','#C4C6BE',.82,grain=.012),
      'facade':_mat('warm ivory metal cladding','#E3E1D5',.58,.23,grain=.002),
      'roof':_mat('zinc roof','#B6C2C8',.52,.57,grain=.0015),
      'trim':_mat('navy frames','#425A69',.5,.38),
      'glass':_mat('blue glazing','#548FA6',.22,.32),
      'darkglass':_mat('dark car glazing','#304B58',.28,.12),
      'asphalt':_mat('asphalt','#555D60',.93,grain=.018),
      'rubber':_mat('rubber','#293037',.91),
      'grass':_mat('green lawn','#497647',.95,grain=.015),
      'leaf':_mat('fresh foliage','#4D8A48',.88),
      'leaflight':_mat('sunlit foliage','#7FA553',.9),
      'trunk':_mat('tree bark','#695341',.93,grain=.02),
      'white':_mat('line white','#F3F5F7',.65,emission=.7),
      'gold':_mat('radiance gold','#F4BB4F',.55,emission=.5),
      'dim':_mat('plot axis','#8396A3',.8,emission=.2),
      'cloud':_mat('cloud white','#E4ECEF',.95),
      'sun':_mat('solar disk','#FFF0CA',.8,emission=5),
      'carwhite':_mat('pearl vehicle','#E0E5E5',.32,.2),
      'carblue':_mat('blue vehicle','#347A98',.38,.18),
      'carred':_mat('terracotta vehicle','#B85D47',.43,.15),
      'mark':_mat('parking paint','#E8E2C9',.9),
    }
    assembly=bpy.data.objects.new('V5 industrial site assembly',None)
    scene.collection.objects.link(assembly)
    _keys(assembly,'scale',[(t(0),(1,1,1)),(t(23.1),(1,1,1)),(t(24),(.001,.001,.001))])

    def show(obj,a=0,b=24,parent=True):
        if parent:obj.parent=assembly
        visible(obj,t(a),t(b));return obj

    def block(name,loc,dims,key,bevel=.04,a=0,b=24):
        return show(box('V5 '+name,loc,dims,m[key],bevel),a,b)

    def line(name,points,key,a,b,radius=.025,draw=.8,parent=True):
        obj=polyline('V5 '+name,points,m[key],radius)
        show(obj,a,b,parent);reveal(obj,t(a),t(draw));return obj

    def cylinder(name,loc,radius,depth,key,rotation=None,a=0,b=24):
        bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=radius,depth=depth,location=loc)
        obj=bpy.context.object;obj.name='V5 '+name;obj.data.materials.append(m[key])
        if rotation:obj.rotation_euler=rotation
        for polygon in obj.data.polygons:polygon.use_smooth=True
        return show(obj,a,b)

    # A contained site, with real industrial building proportions rather than
    # a dark presentation pedestal. Ground has no decorative coordinate grid.
    block('site foundation',(0,0,-.20),(40,28,.36),'concrete',.28)
    block('asphalt logistics yard',(0,-3.6,.005),(38,19.7,.055),'asphalt',.12)
    for x,y,w,h in [(-17,3.0,4.7,18),(17,3.0,4.7,18),(0,11.6,29,3.0),(-10,-10.5,13,3.8)]:
        block('landscape lawn',(x,y,.06),(w,h,.12),'grass',.14)
    block('warehouse concrete plinth',(2,2,.32),(24.3,14.3,.62),'concrete',.09)
    block('warehouse light facade',(2,2,3.25),(24,14,5.65),'facade',.08)
    block('flat zinc roof',(2,2,6.12),(24.5,14.5,.20),'roof',.07)
    # Seams and restrained corrugations describe sheet-metal construction.
    for i in range(32):
        x=-9.8+i*.76
        block('standing roof seam '+str(i),(x,2,6.25),(.045,14.35,.065),'roof',.013)
    for i in range(17):
        x=-9.9+i*1.48
        block('facade vertical seam '+str(i),(x,-5.018,3.25),(.032,.035,5.5),'trim',.006)
    block('roof front parapet',(2,-5.16,6.20),(24.6,.13,.28),'trim',.025)
    block('roof rear parapet',(2,9.16,6.20),(24.6,.13,.28),'trim',.025)
    # Administrative wing: concrete floor edges and separate blue glass bays.
    block('administration wing',(-12,-2.2,2.35),(6,9.4,4.7),'concrete',.08)
    block('administration roof',(-12,-2.2,4.78),(6.25,9.7,.18),'roof',.06)
    for z in (1.2,3.35):
        for x in (-13.95,-12.05,-10.15):
            block('office front glass bay',(x,-6.925,z),(1.72,.045,1.72),'glass',.015)
        for y in (-5.8,-3.7,-1.6,.5):
            block('office side glass bay',(-15.025,y,z),(.045,1.9,1.72),'glass',.015)
    for z in (.23,2.35,4.48):
        block('office horizontal slab',(-12,-6.98,z),(6.15,.16,.18),'facade',.02)
    block('office entrance canopy',(-12,-7.45,2.02),(4.7,1.4,.13),'roof',.035)
    block('office front step',(-12,-7.5,.17),(5.1,1.4,.25),'concrete',.025)
    for x in (-13.0,-11.0):
        block('office entrance door',(x,-7.0,1.1),(1.65,.09,2.02),'darkglass',.02)
    # Loading docks with rubber surrounds, sectional doors and safety bollards.
    for i,x in enumerate((-5.0,2.2,9.3)):
        block('loading dock surround '+str(i),(x,-5.12,2.3),(4.8,.25,4.65),'rubber',.05)
        block('sectional loading door '+str(i),(x,-5.29,2.26),(4.15,.075,4.25),'roof',.025)
        for row in range(8):
            block('loading door joint',(x,-5.345,.43+row*.52),(4.1,.025,.022),'trim',.004)
        block('dock shelter canopy',(x,-5.65,4.73),(5.05,1.35,.18),'trim',.035)
        block('dock approach ramp',(x,-6.0,.20),(4.6,1.6,.3),'concrete',.04)
        for side in (-1,1):
            cylinder('yellow safety bollard',(x+side*2.7,-6.25,.6),.11,1.2,'gold')
    for i,x in enumerate((-7.7,-.8,6.2,12.3)):
        block('high factory window '+str(i),(x,-5.055,5.35),(2.0,.05,.58),'glass',.015)
    for x,y in [(-5.2,4.8),(7.5,5.2)]:
        block('rooftop ventilation base',(x,y,6.42),(2.6,2.0,.45),'roof',.04)
        block('rooftop ventilation body',(x,y,6.92),(2.3,1.7,.7),'trim',.08)
        for j in range(7):
            block('ventilation grille',(x-.92+j*.30,y-.87,6.95),(.09,.025,.45),'roof',.01)
    # Subtle lane and parking marks, tied to the physical yard.
    for i in range(5):
        block('parking division',(-17+i*4.2,-10.2,.05),(.07,4.3,.018),'mark',0)
    for x in (-6,1,8,15):
        block('yard lane dash',(x,-10.2,.05),(2.5,.12,.018),'mark',0)

    def car(name,x,y,key):
        block(name+' lower body',(x,y,.56),(4.15,1.76,.62),key,.25)
        block(name+' cabin',(x-.15,y,1.12),(2.30,1.58,.70),key,.22)
        block(name+' hood',(x+1.43,y,.86),(1.0,1.68,.22),key,.16)
        for side in (-1,1):
            block(name+' side glazing',(x-.15,y+side*.805,1.25),(1.9,.025,.43),'darkglass',.09)
            for xx in (-1.25,1.25):
                cylinder(name+' tyre',(x+xx,y+side*.86,.39),.37,.20,'rubber',(math.pi/2,0,0))
                cylinder(name+' wheel',(x+xx,y+side*.975,.39),.20,.022,'roof',(math.pi/2,0,0))
        for side in (-1,1):
            block(name+' headlamp',(x+2.05,y+side*.55,.65),(.025,.34,.13),'white',.025)
    car('white parked vehicle',-14.6,-10.25,'carwhite')
    car('blue parked vehicle',-10.4,-10.25,'carblue')
    car('terracotta logistics vehicle',10.5,-10.0,'carred')

    rng=random.Random(51)
    def tree(name,x,y,height=4.8):
        cylinder(name+' trunk',(x,y,height*.36),.17,height*.72,'trunk')
        for i in range(5):
            a=i*math.tau/5
            p=(x+math.cos(a)*.72,y+math.sin(a)*.65,height*.76+(i%2)*.36)
            obj=sphere('V5 '+name+' foliage '+str(i),p,1.10,m['leaflight' if i%3==0 else 'leaf'],(1.0,.88,1.17))
            show(obj)
    for i,(x,y) in enumerate([(-17.2,7.8),(-17.2,2),(-17.2,-3.8),(17.1,7.7),(17.3,1.9),(17.2,-3.9),(-7.5,11.7),(2.0,11.7),(11.8,11.7)]):
        tree('site tree '+str(i),x,y,4.3+rng.random()*.9)
    for i in range(11):
        x=-15.8+i*1.1
        show(sphere('V5 front shrub '+str(i),(x,-8.35,.53),.52,m['leaf'],(1,.8,.82)))

    # Exactly one square metre, independent of architectural scale.
    receiver=Vector((4.,-.8,6.232))
    patch=block('horizontal reference exactly one square metre',receiver,(1.,1.,.004),'gold',.001,4.2,24)
    patch['area_m2']=1.;patch['horizontal']=True;patch['not_a_sensor']=True
    for i,(a,b) in enumerate([((3.5,-1.48,6.37),(4.5,-1.48,6.37)),((4.68,-1.3,6.37),(4.68,-.3,6.37))]):
        line('one metre dimension '+str(i),[a,b],'gold',6,12,.012,.8)
    offset=Vector((-10.,4.,14.))
    for i,(dx,dy) in enumerate([(-.32,-.28),(0,-.28),(.32,-.28),(-.32,.24),(0,.24),(.32,.24)]):
        end=receiver+Vector((dx,dy,.05));start=end+offset
        line('parallel direct light '+str(i),[start,end],'gold',12+i*.08,17.4,.035,.8)
        direction=offset.normalized();side=Vector((.22,.10,0))
        line('direct ray arrow '+str(i),[end+direction*.6+side,end,end+direction*.6-side],'gold',12.6+i*.08,17.4,.035,.3)
    for i,start in enumerate([(-7,-7,19),(10,8,17),(12,-6,20)]):
        end=receiver+Vector((-.3+i*.27,.1,.06))
        line('diffuse sky contribution '+str(i),[start,end],'white',14+i*.13,17.4,.028,.8)
    # A distant pale luminous disk and actual directional sunlight replace
    # the old gold sphere close to the roof. Diagram rays remain parallel.
    sun=sphere('V5 distant solar disk',receiver+offset*1.04,.62,m['sun'])
    show(sun,12,17.4)
    light_data=bpy.data.lights.new('V5 physical sunlight','SUN');light_data.energy=2.1
    light_data.color=(1.,.95,.84);light_data.angle=math.radians(.8)
    sunlight=bpy.data.objects.new('V5 physical sunlight',light_data);scene.collection.objects.link(sunlight)
    sunlight.rotation_euler=(-offset).to_track_quat('-Z','Y').to_euler()
    for moment,energy in [(0,2.1),(17.5,2.1),(20.4,1.35),(23.0,1.9),(24,1.9)]:
        light_data.energy=energy;light_data.keyframe_insert('energy',frame=frame(t(moment)))

    # A joined metaball cloud has an organic silhouette, with no expensive
    # volume shader. Its bright diffuse surface responds to the same sunlight.
    metaball=bpy.data.metaballs.new('V5 organic cloud form');metaball.resolution=.18;metaball.render_resolution=.14
    cloud=bpy.data.objects.new('V5 organic atmospheric cloud',metaball);scene.collection.objects.link(cloud)
    for loc,radius in [((-2,0,-.1),1.5),((-1,.2,.5),2.0),((.5,0,.8),2.3),((2,.2,.1),1.8),((3.1,0,-.2),1.2),((-.8,0,1.6),1.5),((1.1,.1,1.5),1.4)]:
        element=metaball.elements.new();element.co=loc;element.radius=radius
    bpy.context.view_layer.objects.active=cloud;cloud.select_set(True)
    for obj in bpy.context.selected_objects:
        if obj!=cloud:obj.select_set(False)
    bpy.ops.object.convert(target='MESH');cloud=bpy.context.object;cloud.name='V5 organic atmospheric cloud'
    cloud.data.materials.append(m['cloud']);cloud.scale=(1.1,.78,.72)
    for polygon in cloud.data.polygons:polygon.use_smooth=True
    show(cloud,17.2,24)
    _keys(cloud,'location',[(t(17.2),(-1.8,1,18)),(t(23.6),(9,1.7,18.4))])
    arc=[]
    for i in range(61):
        angle=math.radians(25+130*i/60)
        arc.append((-17*math.cos(angle),4,8+16*math.sin(angle)))
    line('solar geometry arc',arc,'gold',17.3,23.9,.024,1.2)
    arc_sun=show(sphere('V5 moving solar position',arc[0],.45,m['sun']),17.5,23.9)
    _keys(arc_sun,'location',[(t(17.5+i/60*5.4),arc[i]) for i in range(0,61,10)])
    # A visible curve grows out of the industrial scene before the graph cut.
    emerging=[]
    for i in range(121):
        u=i/120;pulse=max(0,math.sin(u*2.5*math.pi))**2
        emerging.append((-13+26*u,-11.4,1.2+7*pulse))
    line('emerging irradiance history',emerging,'white',19.2,24,.055,3.5,parent=False)

    # Last eleven seconds: same explanatory history/future grammar as V4.
    def pulse(x):
        phase=(x+4.3)%2.45
        return math.sin(math.pi*phase/1.72)**2 if phase<1.72 else 0
    history=[(-4.25+5.2*i/179,0,1.3+1.8*pulse(-4.25+5.2*i/179)) for i in range(180)]
    line('history plot axis',[(-4.35,0,1.24),(4.35,0,1.24)],'dim',24,35,.012,.8,parent=False)
    line('history plot curve',history,'white',24,35,.027,3.8,parent=False)
    line('present marker',[(.95,0,1.2),(.95,0,3.6)],'dim',28.5,35,.012,.5,parent=False)
    line('observed window',[(-4.25,0,1.24),(-4.25,0,3.5),(.95,0,3.5),(.95,0,1.24)],'white',30,35,.012,.8,parent=False)
    for j in range(10):
        x=1.24+j*.30
        line('unknown future top '+str(j),[(x,0,3.5),(x+.17,0,3.5)],'dim',30,35,.012,.3,parent=False)
        line('unknown future bottom '+str(j),[(x,0,1.24),(x+.17,0,1.24)],'dim',30,35,.012,.3,parent=False)
    q=[(2.34,0,2.85),(2.6,0,3.04),(2.99,0,2.98),(3.18,0,2.72),(3.02,0,2.48),(2.74,0,2.3),(2.74,0,2.06)]
    line('future question mark',q,'white',30.5,35,.025,.8,parent=False)
    dot=sphere('V5 question dot',(2.74,0,1.80),.04,m['white']);visible(dot,t(31.2),t(35))
    shots=[
      (0,(43,-58,39),(-1,-.5,1.5),43),(3.8,(38,-58,38),(-1,-.5,1.7),43),
      (6.0,(6.1,-5.1,10.9),(4,-.8,6.34),55),(9,(5.5,-5.1,10.6),(4,-.8,6.34),55),
      (11.8,(4.9,-5.3,10.7),(4,-.8,6.34),55),
      (13.3,(31,-47,29),(0,0,11),43),(16.9,(26,-49,28),(0,0,11),43),
      (19.4,(-32,-68,36),(0,-.5,10),43),(23.6,(-23,-66,33),(0,-2,9),43),
      (24,(.5,-15.1,4.3),(0,0,1.9),48),(29.7,(-.5,-14.7,4.1),(0,0,1.9),48),
      (35,(.6,-14.6,4.2),(0,0,1.9),48)]
    camera_path(scene,[{'t':t(sec),'location':loc,'target':target,'lens':lens} for sec,loc,target,lens in shots])
    scene.unit_settings.system='METRIC';scene.unit_settings.scale_length=1.
    return {'version':5,'builder':'build_factory_v5','duration_seconds':duration,
      'main_building_dimensions_m':[24,14,6.2],'site_dimensions_m':[40,28],
      'reference_area_m2':1.,'reference_horizontal':True,'reference_center_m':list(receiver),
      'factory_illustrative_not_specific_site':True,'not_pv_or_sensor':True,
      'sun':'directional SUN plus distant pale emission disk','cloud':'organic joined metaball mesh, no volume shader',
      'camera_keys':[{'second':t(sec),'location':list(loc),'target':list(target),'lens_mm':lens} for sec,loc,target,lens in shots],
      'object_count':len(set(bpy.data.objects)-before),'native_text':False,
      'phases':[[t(a),t(b),name] for a,b,name in [(0,4,'industrial site'),(4,12,'one square metre horizontal reference'),(12,17,'direct and diffuse irradiance'),(17,24,'solar geometry and atmospheric change'),(24,35,'history and unknown future')]],
      'no_grid':True,'scientific_variable':'GHI W/m2, power per horizontal area'}
