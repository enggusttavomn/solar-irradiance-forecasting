"""Mapa real das localidades e fluxo didático das entradas do TCC.

Acrescenta geometria à cena Blender atual. Câmera, iluminação, legendas e
exportação pertencem ao montador. As coordenadas são as do cadastro do
projeto, conferidas na Tabela 1 (p. 10); não são sensores nas fábricas.
As curvas da segunda fase são explicitamente ilustrativas, sem previsões.
"""

import json
import math
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.geometry import tessellate_polygon

from blender_pilot import box, emission, polyline, reveal, sphere, surface, visible


ROOT = Path(__file__).resolve().parents[2]
GEODATA = Path(__file__).resolve().parent / 'assets'
CYAN = (.10, .75, .90, 1.0)
GOLD = (1.0, .63, .20, 1.0)
VIOLET = (.59, .29, 1.0, 1.0)
WHITE = (.88, .94, 1.0, 1.0)
COUNTRY_COLORS = {'BR': GOLD, 'US': CYAN, 'MX': VIOLET}
BOUNDS = (-171.0, -58.0, -30.0, 76.0)
MAP_SCALE = 3.8 / (BOUNDS[3] - BOUNDS[1])
MAP_CENTER_X = -2.05
MAP_CENTER_Z = 2.9
MAP_CENTER_LONGITUDE = (BOUNDS[0] + BOUNDS[2]) * .5
MAP_CENTER_LATITUDE = (BOUNDS[1] + BOUNDS[3]) * .5


def _frame(seconds):
    return round(float(seconds) * 30) + 1


def project(longitude, latitude, depth=0.0):
    """Projeção equiretangular uniforme no plano XZ, sem esticar contornos."""
    return (
        MAP_CENTER_X + (longitude - MAP_CENTER_LONGITUDE) * MAP_SCALE,
        depth,
        MAP_CENTER_Z + (latitude - MAP_CENTER_LATITUDE) * MAP_SCALE,
    )


def _ring(name, center, radius, material, segments=32, thickness=.009):
    x, y, z = center
    points = [(x + radius * math.cos(i * 2 * math.pi / segments), y,
               z + radius * math.sin(i * 2 * math.pi / segments))
              for i in range(segments)]
    return polyline(name, points, material, thickness, cyclic=True)


def _mesh_ring(name, coordinates, material):
    vertices = [Vector(project(lon, lat, .09)) for lon, lat in coordinates]
    triangles = tessellate_polygon([vertices])
    # Blender 4.5 returns vertex indices; older Blender releases return source
    # Vectors. Support both without an external geometry dependency.
    lookup = {tuple(vertex): i for i, vertex in enumerate(vertices)}
    faces = [tuple(vertex if isinstance(vertex, int) else lookup[tuple(vertex)]
                   for vertex in triangle) for triangle in triangles]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(v) for v in vertices], [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def _motion(obj, keys):
    for seconds, position in keys:
        obj.location = position
        obj.keyframe_insert('location', frame=_frame(seconds))


def _arrow(name, start, end, material, radius=.012):
    start, end = Vector(start), Vector(end)
    direction = (end-start).normalized()
    # This diagram lies in XZ. Its triangular arrow head stays readable from
    # the frontal camera instead of pointing toward the viewer.
    perpendicular = Vector((-direction.z, 0, direction.x))
    objects = [polyline(name, [tuple(start), tuple(end)], material, radius)]
    for side in (-1, 1):
        tip = end - direction*.16 + perpendicular*.085*side
        objects.append(polyline(name+' ponta '+str(side), [tuple(tip), tuple(end)], material, radius))
    return objects


def build_map(duration=40):
    """Construir mapa 0–18 s, dez séries 18–29 s e entradas 29–40 s.

    Todos os tempos são locais à cena; ``duration`` escala as três fases.
    Não cria câmera nem executa render. Retorna metadados para os textos ASS.
    """
    duration = float(duration)
    if duration <= 0:
        raise ValueError('A duração deve ser positiva.')
    factor = duration/40.0
    t = lambda seconds: seconds*factor
    coast = json.loads((GEODATA/'americas_land.json').read_text(encoding='utf-8'))
    point_source = json.loads((GEODATA/'localities_report.json').read_text(encoding='utf-8'))
    localities = point_source['localities']
    if len(localities) != 10 or sum(p['country']=='US' for p in localities) != 8:
        raise ValueError('O mapa requer exatamente as dez localidades conferidas.')

    before = set(bpy.data.objects)
    coastline = emission('Mapa · costa Natural Earth', (.15,.34,.43,1), .85)
    land = emission('Mapa · preenchimento discreto', (.011,.028,.038,1), .7)
    grid = emission('Mapa · meridianos e paralelos', (.025,.057,.073,1), .45)
    soft = emission('Mapa · molduras e conectores', (.08,.22,.28,1), .85)
    pale = emission('Mapa · fluxo GHI', WHITE, 1.0)
    cyan = emission('Mapa · fluxo da identidade local', CYAN, 1.8)
    country_material = {country: emission('Mapa · ponto '+country, color, 2.0)
                        for country,color in COUNTRY_COLORS.items()}
    panel = surface('Mapa · painel de entrada', (.018,.055,.07,1), .25,.24,.12)

    for i, ring in enumerate(coast['rings']):
        coords = ring['coordinates']
        if ring['outer']:
            obj = _mesh_ring('Terra Natural Earth %02d'%i, coords, land)
            visible(obj, 0, t(18))
        edge = polyline('Costa Natural Earth %02d'%i,
                        [project(lon,lat,.045) for lon,lat in coords],
                        coastline, .0075, cyclic=True)
        visible(edge, t(.15), t(18))
        reveal(edge, t(.2 + i*.012), t(2.5))

    for longitude in (-150,-120,-90,-60):
        line = polyline('Meridiano %s'%longitude,
                        [project(longitude,BOUNDS[1],.13),project(longitude,BOUNDS[3],.13)],grid,.003)
        visible(line, 0, t(18))
    for latitude in (-45,-15,15,45,75):
        line = polyline('Paralelo %s'%latitude,
                        [project(BOUNDS[0],latitude,.13),project(BOUNDS[2],latitude,.13)],grid,.003)
        visible(line, 0, t(18))

    positions=[]
    for i, point in enumerate(localities):
        position = project(point['longitude'],point['latitude'],-.035)
        positions.append(position)
        mat = country_material[point['country']]
        marker = sphere('Localidade %02d · %s'%(point['id'],point['label']),position,.042,mat)
        marker['latitude'] = point['latitude']
        marker['longitude'] = point['longitude']
        marker['report_locality_id'] = point['id']
        marker['meaning'] = 'Coordenada da célula consultada, não sensor fabril'
        visible(marker,t(3.0+i*.7),t(29))
        halo = _ring('Destaque da localidade %02d'%point['id'],
                     (position[0],-.07,position[2]),.085,mat,thickness=.006)
        visible(halo,t(3.0+i*.7),t(18))
        reveal(halo,t(3.0+i*.7),t(.55))
        # The geographic position stays exact throughout the map phase.
        # Only after it disappears do points reorganize into one row per series.
        destination=(-4.55,-.035,4.5-i*.355)
        _motion(marker,[(0,position),(t(18),position),(t(19.7+i*.045),destination),(t(29),destination)])

    # Detroit's two coordinates are about 13 km apart and intentionally overlap
    # at continental scale. A separate geographic inset distinguishes them,
    # without displacing or falsifying either main-map marker.
    inset_bounds=(-83.25,42.23,-82.98,42.46)
    inset_world=(-4.7,1.2,-3.25,2.5)
    ix0,iz0,ix1,iz1=inset_world
    border=polyline('Detroit · moldura do detalhe',[(ix0,-.06,iz0),(ix1,-.06,iz0),
                     (ix1,-.06,iz1),(ix0,-.06,iz1)],soft,.009,cyclic=True)
    visible(border,t(12),t(18))
    reveal(border,t(12),t(.55))
    def inset_project(lon,lat):
        return (ix0+(lon-inset_bounds[0])/(inset_bounds[2]-inset_bounds[0])*(ix1-ix0),
                -.085,iz0+(lat-inset_bounds[1])/(inset_bounds[3]-inset_bounds[1])*(iz1-iz0))
    for fraction in (.25,.5,.75):
        for axis in (0,1):
            if axis==0:
                x=ix0+fraction*(ix1-ix0); pts=[(x,-.035,iz0),(x,-.035,iz1)]
            else:
                z=iz0+fraction*(iz1-iz0); pts=[(ix0,-.035,z),(ix1,-.035,z)]
            obj=polyline('Detroit · grade %s %s'%(axis,fraction),pts,grid,.003)
            visible(obj,t(12),t(18))
    for point in localities[7:9]:
        projected=inset_project(point['longitude'],point['latitude'])
        obj=sphere('Detroit ampliado · '+point['label'],projected,.05,country_material['US'])
        obj['latitude']=point['latitude'];obj['longitude']=point['longitude']
        visible(obj,t(12.5),t(18))
        obj=_ring('Detroit ampliado · halo '+str(point['id']),projected,.09,cyan,thickness=.006)
        visible(obj,t(12.5),t(18))
    detroit_center=tuple((a+b)*.5 for a,b in zip(positions[7],positions[8]))
    connector=polyline('Detroit · ligação à ampliação',
                       [detroit_center,(-2.85,-.055,3.05),(-3.25,-.055,2.5)],soft,.007)
    visible(connector,t(12),t(18));reveal(connector,t(12),t(.65))

    # Each row is an illustrative history, not an experimental forecast.
    for i, point in enumerate(localities):
        baseline=4.5-i*.355
        pts=[]
        for j in range(81):
            u=j/80
            pulse=max(0,math.sin((u*3.1+.06*i)*2*math.pi))**2
            modulation=.72+.20*math.sin(u*7.3+i*.8)
            pts.append((-4.35+u*4.8,.01,baseline+.18*pulse*modulation))
        curve=polyline('Histórico ilustrativo da localidade %02d'%point['id'],pts,
                       country_material[point['country']],.010)
        curve['data_status']='Ilustração conceitual, sem valores de resultado'
        visible(curve,t(18.3+i*.09),t(29))
        reveal(curve,t(18.3+i*.09),t(2.1))
        axis=polyline('Base da série %02d'%point['id'],
                      [(-4.35,.07,baseline),(.45,.07,baseline)],grid,.003)
        visible(axis,t(18),t(29))

    # Final phase makes both actual input types explicit: GHI and locality ID.
    for name,loc,dimensions in [
        ('Entrada GHI',(-3.6,.1,3.65),(2.0,.24,1.05)),
        ('Identificação da localidade',(-3.6,.1,1.95),(2.0,.24,.75)),
        ('Modelo compartilhado',(-.35,.2,2.8),(1.45,.65,1.9)),
    ]:
        obj=box('Fluxo · '+name,loc,dimensions,panel,.045)
        visible(obj,t(29),duration+.05)
        x,y,z=loc;dx,dy,dz=(d*.5 for d in dimensions)
        corners=[(x-dx,y-dy,z-dz),(x+dx,y-dy,z-dz),(x+dx,y-dy,z+dz),(x-dx,y-dy,z+dz)]
        outline=polyline('Fluxo · borda '+name,corners,soft,.009,cyclic=True)
        visible(outline,t(29),duration+.05);reveal(outline,t(29),t(.65))
    pts=[]
    for j in range(65):
        u=j/64
        value=max(0,math.sin(u*2.7*2*math.pi))**2
        pts.append((-4.45+u*1.7,-.06,3.4+.44*value))
    curve=polyline('Fluxo · histórico ilustrativo GHI',pts,pale,.012)
    visible(curve,t(29.3),duration+.05);reveal(curve,t(29.3),t(1.8))
    for i,point in enumerate(localities):
        p=(-4.39+(i%5)*.38,-.065,1.81+(i//5)*.25)
        dot=sphere('Fluxo · identidade aprendida %02d'%point['id'],p,.044,country_material[point['country']])
        visible(dot,t(30+i*.07),duration+.05)
    for index,(a,b) in enumerate([((-2.52,-.06,3.65),(-1.13,-.06,3.0)),((-2.52,-.06,1.95),(-1.13,-.06,2.55))]):
        for obj in _arrow('Fluxo · entrada %s'%index,a,b,cyan):
            visible(obj,t(31),duration+.05);reveal(obj,t(31),t(1.1))
    nodes=[]
    for col in range(3):
        column=[]
        for row in range(3):
            point=(-.83+col*.47,-.16,2.28+row*.52)
            dot=sphere('Modelo · nó %s %s'%(col,row),point,.06,cyan)
            visible(dot,t(32+col*.45),duration+.05)
            column.append(point)
        nodes.append(column)
    for col in range(2):
        for i,a in enumerate(nodes[col]):
            for j,b in enumerate(nodes[col+1]):
                edge=polyline('Modelo · ligação %s %s %s'%(col,i,j),[a,b],soft,.006)
                visible(edge,t(32.5+col*.45),duration+.05)
                reveal(edge,t(32.5+col*.45),t(.6))

    created=[obj.name for obj in bpy.data.objects if obj not in before]
    return {
        'kind':'map_and_inputs', 'duration_seconds':duration,
        'objects_created':len(created), 'object_names':created,
        'camera_recommendation':{'location':[0,-16,2.65],'target':[0,0,2.65],'ortho_scale':13},
        'map_layout':{'plane':'XZ','x_range':[project(BOUNDS[0],0)[0],project(BOUNDS[2],0)[0]],'z_range':[1.0,4.8],'projection':'Equirectangular; equal scale per degree on both axes','inset_detroit':{'geographic_bbox':inset_bounds,'world_xz_bbox':inset_world}},
        'subphases':[{'start':0,'end':t(18),'name':'Mapa real e dez coordenadas'},
                     {'start':t(18),'end':t(29),'name':'Dez históricos ilustrativos'},
                     {'start':t(29),'end':duration,'name':'GHI e identificação local como entradas'}],
        'localities':[dict(point,marker_world=list(position)) for point,position in zip(localities,positions)],
        'country_counts':{'BR':1,'US':8,'MX':1},
        'labels':[
            {'text':'Detroit · ampliação geográfica','start':t(12),'end':t(18),'anchor_world':[-4.7,0,2.68]},
            {'text':'08 · GM Factory Zero','start':t(12.5),'end':t(18),'anchor_world':list(inset_project(localities[7]['longitude'],localities[7]['latitude']))},
            {'text':'09 · Ford Rouge EV Center','start':t(12.5),'end':t(18),'anchor_world':list(inset_project(localities[8]['longitude'],localities[8]['latitude']))},
            {'text':'Históricos de GHI · ilustração conceitual','start':t(18),'end':t(29)},
            {'text':'Histórico de GHI','start':t(29),'end':duration,'anchor_world':[-4.6,0,4.35]},
            {'text':'Identificação aprendida da localidade','start':t(29),'end':duration,'anchor_world':[-4.6,0,2.55]},
            {'text':'Modelo compartilhado','start':t(29),'end':duration,'anchor_world':[-1.1,0,4.05]},
        ],
        'source_notice':'Dados: NSRDB; coordenadas: relatório, Tabela 1 (p. 10) e cadastro do projeto. Base cartográfica: Natural Earth, domínio público.',
        'coastline_source':coast['source_page'],
        'locality_source':'codigo_fonte/coleta_e_preparacao/localidades.py',
        'technical_notes':['Não há sensores fabris representados.','Marcadores de Detroit sobrepõem-se na escala continental; o inset os distingue mantendo coordenadas exatas.','Séries desenhadas são exemplos conceituais de históricos, sem previsões nem resultados inventados.','Nenhum texto Blender foi criado; rótulos e fontes devem ser aplicados pelo ASS.'],
    }
