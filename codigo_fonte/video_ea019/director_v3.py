"""Construir e renderizar todo o miolo de 415 s segundo o plano novo.

Não inclui as duas filmagens futuras do aluno. Tipografia e gráficos exatos
da planilha são compostos separadamente por overlays_v3.py.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector

from blender_pilot import setup, emission, surface, polyline, sphere, box, visible, reveal, wire_box, frame, FPS
from blender_full import static_front_camera
from scenes_factory_v3 import build_factory
from scenes_models import build_models
from scenes_map import build_map
from scenes_explainer import build_objective, build_mae, build_complements, build_limits
from render_style_v3 import apply_style

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v3'
PLAN=ROOT/'documentacao/relatorio_final_ea019/video/trecho_animado_v2/plano_trecho_animado_v2.json'
SHOTS=OUT/'plano_73_extraido.json'
WHITE=(.88,.94,1,1)
GOLD=(1,.63,.20,1)
MUTED=(.14,.20,.27,1)


def warp(anchors):
    def transform(t):
        if t<=anchors[0][0]:
            a,b=anchors[0],anchors[1]
        elif t>=anchors[-1][0]:
            a,b=anchors[-2],anchors[-1]
        else:
            a,b=next((a,b) for a,b in zip(anchors,anchors[1:]) if a[0]<=t<=b[0])
        return a[1]+(t-a[0])*(b[1]-a[1])/(b[0]-a[0])
    return transform


def actions_for(objects):
    actions={}
    for obj in objects:
        owners=[obj,obj.data]
        for mat in getattr(obj.data,'materials',[]):
            if mat and mat.use_nodes:
                owners.append(mat.node_tree)
        for owner in owners:
            data=getattr(owner,'animation_data',None)
            if data and data.action:
                actions[data.action.as_pointer()]=data.action
    return list(actions.values())


def retime(objects,transform):
    for action in actions_for(objects):
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                for vec in (point.co,point.handle_left,point.handle_right):
                    vec.x=1+FPS*transform((vec.x-1)/FPS)
            curve.update()


def transform_group(name,objects,z_scale=1,z_offset=0):
    parent=bpy.data.objects.new(name,None)
    bpy.context.collection.objects.link(parent)
    for obj in objects:
        if obj.parent is None:
            obj.parent=parent
    parent.scale.z=z_scale
    parent.location.z=z_offset
    return parent


def trace(name,points,mat,start,end,draw=.5,radius=.012):
    obj=polyline(name,points,mat,radius)
    visible(obj,start,end)
    reveal(obj,start,draw)
    return obj


def cell_nsrd():
    gray=emission('Célula NSRDB · estrutura',MUTED,1)
    gold=emission('Célula NSRDB · coordenada',GOLD,1.7)
    for i in range(4):
        x=1.8+i*.55
        trace('Célula NSRDB · meridiano esquemático',[(x,0,1.75),(x,0,3.4)],gray,12,19)
        z=1.75+i*.55
        trace('Célula NSRDB · paralelo esquemático',[(1.8,0,z),(3.45,0,z)],gray,12,19)
    trace('Célula NSRDB · célula selecionada',[(2.35,-.01,2.3),(2.9,-.01,2.3),(2.9,-.01,2.85),(2.35,-.01,2.85),(2.35,-.01,2.3)],gold,13,19,.7)
    dot=sphere('Célula NSRDB · ponto de consulta',(2.625,-.03,2.575),.07,gold)
    visible(dot,13.5,19)


def map_v3():
    before=set(bpy.data.objects)
    info=build_map(40)
    created=set(bpy.data.objects)-before
    inputs=[o for o in created if o.name.startswith(('Fluxo','Modelo ·'))]
    detail=[o for o in created if o.name.startswith('Detroit')]
    other=list(created-set(inputs)-set(detail))
    retime(other,warp([(0,0),(18,19),(29,22),(40,40)]))
    retime(inputs,warp([(0,0),(29,19),(40,40)]))
    retime(detail,warp([(0,0),(12,6),(18,12),(40,40)]))
    transform_group('Entradas · composição compacta',inputs,.85,.57)
    cell_nsrd()
    info['v3_timing']='mapa 0–19; séries 19–22; entradas 19–40; célula 12–19; detalhe Detroit 6–12'
    return info


def tasks_v3():
    white=emission('Tarefas · histórico',WHITE,1.6)
    gray=emission('Tarefas · previsão',(.6,.7,.8,1),1.4)
    axis=emission('Tarefas · eixo',MUTED,.8)
    phases=[(5,11,1.8,4.2),(11,16,3.0,4.2),(16,21,4.7,2.3),(21,26,4.7,4.2)]
    for n,(a,b,period,future_end) in enumerate(phases):
        def height(x):
            phase=(x+4.2)%period
            pulse=math.sin(math.pi*phase/(period*.72))**2 if phase<period*.72 else 0
            return 1.90+1.60*pulse
        trace(f'Tarefa {n} · eixo',[(-4.3,0,1.86),(4.3,0,1.86)],axis,a,b,.3,.007)
        points=[(-4.2+4.5*i/119,0,height(-4.2+4.5*i/119)) for i in range(120)]
        trace(f'Tarefa {n} · observado',points,white,a+.1,b,1.2,.013)
        for edge in wire_box(f'Tarefa {n} · janela',(-1.25,-.23,1.88),(.3,.23,4.0),gray,.008):
            visible(edge,a+.7,b)
            reveal(edge,a+.7,.5)
        trace(f'Tarefa {n} · presente',[(.3,0,1.84),(.3,0,4.15)],white,a+1.2,b,.3,.005)
        for j in range(18):
            x=.42+(future_end-.42)*j/18
            end=x+(future_end-.42)*.55/18
            pp=[(x+(end-x)*k/3,0,height(x+(end-x)*k/3)) for k in range(4)]
            trace(f'Tarefa {n} · vetor futuro {j}',pp,gray,a+1.5+j*.04,b,.3,.013)
    for i,z in enumerate((2.2,3.3)):
        trace('Duas tarefas mensais distintas '+str(i),[(-4,0,z),(-1,0,z),(0,0,z),(3.7,0,z)],gray,26,35,.7,.011)
        for obj in wire_box('Rede mensal distinta '+str(i),(-.7,-.3,z-.4),(.3,.3,z+.4),white,.009):
            visible(obj,26,35)
    return {'phases':[[a,b] for a,b,*_ in phases],'input_future_distinct':True}


def evaluation_v3():
    gray=emission('Avaliação · linha temporal',MUTED,1)
    white=emission('Avaliação · dados disponíveis',WHITE,1.3)
    gold=emission('Avaliação · configuração escolhida',GOLD,1.4)
    body=surface('Avaliação · blocos',(.025,.035,.045,1),0,.9)
    stages=[(-3.7,0,1.55),(.1,7,1.15),(3.6,13,1.1)]
    for i,(x,start,width) in enumerate(stages):
        obj=box('Período cronológico '+str(i),(x,0,2.3),(width*1.7,.32,.8),body,.04)
        visible(obj,start,40)
        for edge in wire_box('Período cronológico borda '+str(i),(x-width*.85,-.16,1.9),(x+width*.85,.16,2.7),white,.009):
            visible(edge,start,40)
            reveal(edge,start,.6)
    trace('Avaliação · direção cronológica',[(-4.8,0,1.6),(4.8,0,1.6)],gray,0,40,.8,.01)
    selected=sphere('Configuração escolhida na validação',(.1,-.25,2.3),.12,gold)
    visible(selected,19,40)
    for t,loc in [(19,(.1,-.25,2.3)),(24,(.1,-.25,2.3)),(27,(-2.5,-.25,3.25)),(29,(3.6,-.25,2.3)),(40,(3.6,-.25,2.3))]:
        selected.location=loc
        selected.keyframe_insert('location',frame=frame(t))
    for edge in wire_box('Novo ajuste · inclui validação',(-4.8,-.2,3.0),(1.1,.2,3.6),gold,.01):
        visible(edge,24,40)
        reveal(edge,24,.6)
    return {'chronology':'2019–2022 / 2023 / refit2019–2023 / teste2024 retrospectivo'}


def quant_curve(levels,x0,x1,z0,h):
    pts=[(x0,0,z0)]
    for k in range(levels-1):
        x=x0+(x1-x0)*(k+.5)/(levels-1)
        pts.extend([(x,0,z0+h*k/(levels-1)),(x,0,z0+h*(k+1)/(levels-1))])
    pts.append((x1,0,z0+h))
    return pts


def quantization_v3():
    white=emission('Quantização · contínuo',WHITE,1.5)
    gold=emission('Quantização · amplitude representada',GOLD,1.5)
    gray=emission('Quantização · estrutura',MUTED,1)
    body=surface('Quantização · blocos de entrada',(.025,.035,.045,1),0,.9)
    for i,levels in enumerate((None,64,128,256)):
        x0=-4.6+i*2.45
        points=[(x0,0,1.55),(x0+1.8,0,3.5)] if levels is None else quant_curve(levels,x0,x0+1.8,1.55,1.95)
        trace('Comparação de amplitudes '+str(levels),points,white if levels is None else gold,0,10.5,1.5,.01)
        trace('Base da comparação '+str(i),[(x0,0,1.5),(x0+1.9,0,1.5)],gray,0,10.5,.6,.005)
    trace('Degraus didáticos de amplitude',quant_curve(8,-4.2,4.2,1.45,2.1),gold,10.5,14.5,1.0,.016)
    trace('Referência contínua dos degraus',[(-4.2,.02,1.45),(4.2,.02,3.55)],white,10.5,14.5,.6,.006)
    for i,(x,z,w) in enumerate([(-3.5,2.6,1.8),(0,2.6,1.7),(3.35,2.6,1.7)]):
        obj=box('Entrada de GHI · processo '+str(i),(x,.1,z),(w,.35,1.0),body,.04)
        visible(obj,14.5,21.6)
        for edge in wire_box('Entrada de GHI · moldura '+str(i),(x-w/2,-.1,z-.5),(x+w/2,.3,z+.5),gold if i==1 else white,.009):
            visible(edge,14.5,21.6)
    trace('GHI passa pelo quantizador',[(-2.6,0,2.6),(-.85,0,2.6),(.85,0,2.6),(2.5,0,2.6)],gold,15.2,21.6,1,.012)
    trace('Identificação contorna quantizador',[(-4.4,0,1.8),(-4.4,0,1.45),(4.2,0,1.45),(4.2,0,2.1)],white,15.2,21.6,1.6,.011)
    pts=[(-4.4,0,1.45),(-3.6,0,1.45)]+quant_curve(8,-3.6,3.6,1.45,2.1)+[(4.4,0,3.55)]
    trace('Clipping e arredondamento ilustrativos',pts,gold,21.6,28.2,1.3,.015)
    trace('Controle contínuo sem clipping',[(-4.4,.02,1.22),(4.4,.02,3.78)],white,21.6,28.2,1.3,.006)
    for x in (-3.6,3.6):
        trace('Limite do intervalo normalizado '+str(x),[(x,0,1.1),(x,0,3.8)],gray,21.6,28.2,.5,.006)
    for x in (-2.7,2.7):
        for edge in wire_box('Condição fixada '+str(x),(x-.8,-.25,1.8),(x+.8,.25,3.0),white,.01):
            visible(edge,28.2,35)
    trace('Condição da validação mantida no teste',[(-1.9,0,2.4),(1.9,0,2.4)],gold,28.5,35,1.4,.015)
    return {'real_levels':[64,128,256],'didactic_steps':8,'weights_continuous':True,'phases':[0,10.5,14.5,21.6,28.2,35]}


def build_chapter(number,duration,scene):
    before=set(bpy.data.objects)
    info={}
    if number==2:
        return build_factory(duration)
    if number==3:
        info=build_objective(duration)
        transform_group('Objetivo · espaço de leitura',set(bpy.data.objects)-before,1,1.1)
    elif number==4:
        info=map_v3()
    elif number==5:
        info=tasks_v3()
    elif number==6:
        info=evaluation_v3()
    elif number==7:
        info=build_models(duration)
        retime(set(bpy.data.objects)-before,warp([(0,6),(17,12.5),(34,30.8),(54.4,43.2),(55,55)]))
    elif number==8:
        info=quantization_v3()
    elif number==9:
        info=build_mae(duration)
        objects=set(bpy.data.objects)-before
        for obj in objects:
            for material in getattr(obj.data,'materials',[]):
                if material and 'previsão' in material.name:
                    material['design_srgb_hex']='#E9B95F'
        retime(objects,warp([(0,0),(14,13.4),(22,20),(30,30)]))
        transform_group('Métrica · posição para leitura',objects,1,.7)
    elif number==11:
        info=build_complements(duration)
        retime(set(bpy.data.objects)-before,warp([(0,0),(8,3.4),(20,20)]))
        markers=[obj for obj in set(bpy.data.objects)-before if obj.name.startswith(('Complementos · escolha','Complementos · comparação histórica','Complementos · indicador histórico'))]
        transform_group('Complementos · contagens acima das fontes',markers,1,1.0)
        white=emission('Históricos pareados · mesma avaliação',WHITE,1)
        gray=emission('Históricos pareados · duração',MUTED,1)
        gold=emission('Históricos pareados · alinhamento',GOLD,1.4)
        for z,x0 in [(3.3,-4.2),(2.35,-2.9)]:
            trace('Histórico pareado · ajuste',[(x0,0,z),(-.15,0,z)],gray,3.4,20,.8,.06)
            trace('Histórico pareado · validação',[(-.05,0,z),(.7,0,z)],white,3.4,20,.5,.05)
            trace('Histórico pareado · teste',[(.85,0,z),(2.1,0,z)],gold,3.4,20,.5,.05)
        trace('Mesmos cortes de avaliação',[(-.1,0,2),(-.1,0,3.65)],white,3.4,20,.4,.008)
    elif number==12:
        info=build_limits(duration)
        retime(set(bpy.data.objects)-before,warp([(0,0),(5,5.3),(10,10),(15,15)]))
    if number in (11,12):
        for obj in set(bpy.data.objects)-before:
            if obj.name.startswith(('Complementos · quantização','Complementos · histórico','Limitações · cartão')):
                animation=obj.animation_data
                if animation and animation.action:
                    for curve in list(animation.action.fcurves):
                        if curve.data_path=='hide_render':
                            animation.action.fcurves.remove(curve)
                obj.hide_render=True
    # Identity, numerical results and synthesis use clean front-facing vectors
    # from the ASS layer; they need no decorative 3D behind the data.
    static_front_camera(scene)
    if number==7:
        static_front_camera(scene,(1.6,-17,7),(0,0,1.55),14.3)
    return info


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--index',type=int,nargs='*')
    parser.add_argument('--qa',action='store_true')
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    out=args.output_dir.resolve()
    (out/'cenas').mkdir(parents=True,exist_ok=True)
    (out/'qa_3d').mkdir(exist_ok=True)
    source=json.loads(PLAN.read_text(encoding='utf-8'))
    shots=json.loads(SHOTS.read_text(encoding='utf-8'))['middle_shots']
    entries=[]
    qa_times={1:[8],2:[.5,7,15,20,27,32],3:[8],4:[6,15,22,33],5:[8,18,26],6:[15,27],7:[8,20,36,49],8:[3,12,18,25,32],9:[8,16,26],10:[3,41],11:[7,16],12:[7,12],13:[7]}
    bpy.context.preferences.filepaths.save_version=0
    for part in source['scenes']:
        number=part['id']
        if args.index and number not in args.index:
            continue
        duration=part['end_seconds']-part['start_seconds']
        started=time.monotonic()
        scene=setup(SimpleNamespace(engine='BLENDER_EEVEE_NEXT',samples=2,resolution_percentage=100))
        scene.name=f'EA019 v3 · capítulo {number:02d}'
        info=build_chapter(number,duration,scene)
        scene.frame_start=1
        scene.frame_end=duration*FPS
        scene.render.filepath=str(out/'cenas'/f'cena_{number:02d}_3d.mp4')
        style=apply_style(scene,number)
        scene.frame_set(1)
        blend=out/'cenas'/f'cena_{number:02d}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        if args.qa:
            oldpath=scene.render.filepath
            scene.render.image_settings.file_format='PNG'
            for second in qa_times[number]:
                scene.frame_set(frame(second))
                scene.render.filepath=str(out/'qa_3d'/f"cena_{number:02d}_t{str(second).replace('.','_')}.png")
                bpy.ops.render.render(write_still=True)
            scene.render.image_settings.file_format='FFMPEG'
            scene.render.filepath=oldpath
        if args.render:
            bpy.ops.render.render(animation=True)
        entry={'id':number,'title':part['title'],'start_seconds':part['start_seconds'],'end_seconds':part['end_seconds'],
               'duration_seconds':duration,'frame_count':duration*FPS,'blend':str(blend),
               'raw_mp4':scene.render.filepath,'rendered':bool(args.render),'seconds_elapsed':round(time.monotonic()-started,2),
               'shot_ids':[s['id'] for s in shots if part['start_seconds']<=s['start_s']<part['end_seconds']],
               'scene_metadata':info,'render_style':style}
        (out/'cenas'/f'cena_{number:02d}_manifesto.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        entries.append(entry)
        print('V3_CHAPTER '+json.dumps({'id':number,'rendered':bool(args.render),'seconds':entry['seconds_elapsed']}),flush=True)
    manifest={'version':3,'duration_seconds':415,'fps':30,'resolution':[1920,1080],'frame_count':12450,
              'shot_count':63,'chapters':entries,'all_prepared':len(entries)==13,
              'full_rendered':len(entries)==13 and all(x['rendered'] for x in entries),
              'camera_footage_included':False,'narration_recorded':False}
    manifest_name='manifesto_producao_v3.json' if not args.index else 'manifesto_parcial_'+('_'.join(map(str,args.index)))+'.json'
    (out/manifest_name).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('V3_PREPARED '+json.dumps({'chapters':len(entries),'rendered':manifest['full_rendered']}),flush=True)


if __name__=='__main__':
    main()
