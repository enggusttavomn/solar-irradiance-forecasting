"""Observed input/history effects, study limits, and a physical solar finale."""
import json
import math
from pathlib import Path
import bpy
from common_v7 import *

DURATION=74
NOTES=ROOT/'documentacao/relatorio_final_ea019/video/completo_v8/fontes_resultados_v8.json'
CUES=[
 (0,11,'A quantização não teve vantagem universal: cinco combinações melhoraram, quatro pioraram e três mantiveram o controle.'),
 (11,21,'Em uma análise histórica separada, os dois históricos usaram os mesmos alvos e datas de avaliação.'),
 (21,31,'O histórico longo teve menor erro em onze dos doze controles contínuos. A exceção foi a LSTM horária.'),
 (31,37,'Essa associação não isola uma causa: os anos e a normalização também mudaram.'),
 (37,45,'Os resultados são descritivos, sem significância estatística demonstrada. O horário utilizou uma semente.'),
 (45,52,'A tarefa de seis meses tem apenas sete origens de teste por localidade e permanece exploratória.'),
 (52,59,'Há alvos compartilhados entre janelas. A generalização para localidades inéditas não foi avaliada.'),
 (59,67,'No conjunto avaliado, Transformer liderou os horizontes completos horário e diário; Informer, os mensais.'),
 (67,74,'Portanto, a escolha depende da tarefa, dentro dos limites deste estudo.'),
]
MODELS=['LSTM','Transformer','Informer']
TASKS=['hourly_72_extension','daily_30','monthly_1','monthly_6']
SHORT={'hourly_72_extension':'H','daily_30':'D','monthly_1':'M1','monthly_6':'M6'}

def show(obj,a,b):visible(obj,a,b);return obj
def trace(name,pts,mat,a,b,r=.018,draw=.65):
    obj=polyline(name,pts,mat,r);show(obj,a,b)
    if draw:reveal(obj,a,draw)
    return obj
def text(name,body,loc,size,mat,a,b):return label('V8 interpretação '+name,body,loc,size,mat,a,b)
def hud(scene,name,body,xy,size,mat,a,b):
    obj=text(name,body,(0,0,0),size,mat,a,b);obj.parent=scene.camera;obj.location=(xy[0],xy[1],-20)
    return obj

def factory_icon(name,loc,mat,glass,a,b,wire=False):
    x,y,z=loc
    if wire:
        points=[(x-.45,y,z),(x+.45,y,z),(x+.45,y,z+.55),(x-.45,y,z+.55),(x-.45,y,z)]
        return [trace(name,points,mat,a,b,.016)]
    objects=[box(name+' hall',(x,y,z+.24),(.9,.42,.48),mat,.03),
      box(name+' roof',(x,y,z+.50),(.98,.49,.07),mat,.025),
      box(name+' glass',(x,y-.23,z+.29),(.66,.04,.12),glass,.01)]
    for o in objects:show(o,a,b)
    return objects

def build(scene):
    data=json.loads(NOTES.read_text(encoding='utf-8'))
    white=emission('V8 síntese texto',WHITE,.9);muted=emission('V8 síntese eixos',(.34,.43,.48,1),.8)
    ink=emission('V8 inscrição de alto contraste',(.018,.030,.040,1),.85)
    cyan=emission('V8 síntese Transformer',(.20,.72,.81,1),.9)
    purple=emission('V8 síntese Informer',(.62,.43,.84,1),.9)
    coral=emission('V8 síntese LSTM',(.92,.45,.36,1),.9)
    neutral=surface('V8 tokens neutros',(.46,.55,.60,1),.1,.37)
    good=surface('V8 menor MAE observado',(.22,.58,.38,1),.1,.36)
    worse=surface('V8 maior MAE observado',(.82,.40,.31,1),.1,.38)
    control=surface('V8 controle mantido',(.56,.62,.67,1),.1,.4)
    gold=surface('V8 detalhe histórico',GOLD,.15,.35)
    sky=surface('V8 referência azul',CYAN,.1,.35)
    colors={'improved':good,'worse':worse,'control_retained':control}
    outcomes=data['quantization']['results']
    assert len(outcomes)==12
    counts={key:sum(r['outcome']==key for r in outcomes) for key in colors}
    assert counts=={'improved':5,'worse':4,'control_retained':3}
    # Twelve observed model/task outcomes sort into three physical groups.
    text('Quantização sem universalidade','Efeito das entradas quantizadas',(0,0,6.5),.56,white,0,11)
    group_counts={key:0 for key in colors}
    for i,row in enumerate(outcomes):
        start=(-5.5+(i%6)*2.2,0,4.9-(i//6)*1.3)
        kind=row['outcome'];j=group_counts[kind];group_counts[kind]+=1
        if kind=='improved':end=(-4.8+(j%3-1)*1.05,0,2.8+(j//3)*.67)
        elif kind=='worse':end=((j%2-.5)*1.1,0,2.8+(j//2)*.67)
        else:end=(4.8+(j-1)*1.05,0,2.8)
        root=bpy.data.objects.new('Resultado de entrada '+str(i),None);scene.collection.objects.link(root)
        root.location=start
        token=show(box('Condição selecionada '+str(i),(0,0,0),(1.5,.55,.66),colors[kind],.09),0,11);token.parent=root
        tag={'Transformer':'Trf','Informer':'Inf','LSTM':'LSTM'}[row['model']]+' · '+SHORT[row['task']]
        tagobj=text('Combinação '+str(i),tag,(0,-.34,0),.22,ink,0,3.6);tagobj.parent=root
        grow(root,.15+i*.04,.45)
        keys(root,'location',[(0,start),(2.1,start),(4.3,end)])
        keys(root,'scale',[(1,(1,1,1)),(2.1,(1,1,1)),(4.3,(.64,.64,.64))])
    for x,number,title in [(-4.8,'5','Menor MAE'),(0,'4','Maior MAE'),(4.8,'3','Controle mantido')]:
        text('Contagem '+number,number,(x,0,5.2),.85,white,4.4,11)
        text('Categoria '+number,title,(x,0,4.5),.38,white,4.4,11)
    # Separate historical experiment: available past differs; evaluation is paired.
    text('Análise separada','Análise histórica pareada',(0,0,6.5),.56,white,11,21)
    text('Datas iguais','Mesmos alvos e datas de avaliação',(0,0,5.8),.36,white,11,21)
    for row,z in [('Longo',4.3),('Curto',2.5)]:
        left=-6 if row=='Longo' else -2.5
        start_year='1998' if row=='Longo' else '2014'
        for j in range(20 if row=='Longo' else 5):
            x=left+(j+.5)*((-1.2-left)/(20 if row=='Longo' else 5))
            o=show(box('Histórico '+row+' '+str(j),(x,0,z),(.18,.45,.52),neutral,.025),11,21)
            grow(o,11+j*.035,.4)
        text('Período '+row,row+': '+start_year+'–2019',(-4.8,0,z+.6),.34,white,11,21)
        trace('Transição para avaliação '+row,[(-.9,0,z),(-.7,0,z+.12),(-.5,0,z-.12),(-.3,0,z)],muted,11,21,.015)
        for x,width,name in [(1.1,1.9,'Validação'),(4.2,3.3,'Teste')]:
            o=show(box(row+' '+name,(x,0,z),(width,.45,.55),sky if name=='Validação' else gold,.055),11,21);grow(o,12,.6)
    text('Validação histórica','Validação\n2018–2019',(1.1,0,1.4),.30,white,11,21)
    text('Teste histórico','Teste histórico\n2019–2022',(4.2,0,1.4),.30,white,11,21)
    # Actual twelve continuous-control comparisons; token size encodes no MAE magnitude.
    history=data['paired_history']['results']
    by_pair={(r['task'],r['model']):r for r in history}
    assert sum(r['long_improved'] for r in history)==11
    text('Onze controles','Histórico longo: menor MAE em 11 de 12',(0,0,6.9),.52,white,21,31)
    text('Caráter da análise','Controles contínuos · análise histórica separada',(0,0,6.35),.30,white,21,31)
    for col,model in enumerate(MODELS):
        x=-3.8+col*4.0
        text('Cabeçalho '+model,model,(x,0,5.7),.37,{'LSTM':coral,'Transformer':cyan,'Informer':purple}[model],21,31)
        for r,task in enumerate(TASKS):
            z=4.8-r*1.1;value=by_pair[(task,model)]
            for k,kind in enumerate(['L','C']):
                winner=(kind=='L')==value['long_improved']
                obj=show(box('Controle histórico '+model+task+kind,(x-.6+k*1.2,0,z),(.83,.50,.55),good if winner else neutral,.07),21,31)
                grow(obj,21.4+(r*3+col)*.11,.45)
                text('Rótulo histórico '+model+task+kind,kind,(x-.6+k*1.2,-.32,z),.29,ink,21,31)
    for i,name in enumerate(['Horária','Diária','Mensal 1','Mensal 6']):text('Linha histórica '+name,name,(-6.7,0,4.8-i*1.1),.28,white,21,31)
    text('Legenda históricos','L: longo   C: curto',(0,0,.85),.32,white,21,31)
    text('Exceção histórica','Exceção: LSTM horária',(0,0,1.35),.36,coral,27,31)
    # Association: two factors changed, rather than one isolated cause.
    text('Associação','Associação observada',(0,0,6.2),.58,white,31,37)
    for x,name,mat in [(-3.0,'Composição dos anos',sky),(3.0,'Normalização',gold)]:
        shown=show(sphere('Fator '+name,(x,0,3.5),.63,mat),31,37);grow(shown,31,.65)
        text('Nome fator '+name,name,(x,0,2.2),.40,white,31,37)
    trace('Fatores não isolados',[(-2.2,0,3.5),(2.2,0,3.5)],muted,31.7,37,.025)
    text('Causa não isolada','Efeitos não isolados',(0,0,4.8),.40,white,32,37)
    # Repeated seeds do not create a demonstrated confidence interval.
    text('Limite estatístico','Diferenças descritivas',(0,0,6.3),.58,white,37,45)
    text('Sem demonstração estatística','Significância não demonstrada',(0,0,5.5),.41,white,37,45)
    show(sphere('Uma semente horária',(-4,0,3.5),.38,gold),37,45)
    text('Uma semente','Horária: 1 semente',(-4,0,2.5),.37,white,37,45)
    for i in range(5):
        x=1+i*.75;show(sphere('Previsão combinada '+str(i),(x,0,3.5),.21,neutral),37,45)
        trace('Combinação de previsões '+str(i),[(x,0,3.2),(2.5,0,2.65)],muted,38+i*.12,45,.014)
    text('Cinco previsões','Diária/mensais: média de 5 previsões',(2.5,0,1.9),.32,white,38,45)
    # Seven 6-month rolling origins share many target months in the 2024 test.
    text('Sete origens','Mensal de seis passos: 7 origens por localidade',(0,0,6.6),.49,white,45,55.5)
    text('Teste exploratório','Teste de 2024 · exploratório',(0,0,5.9),.34,white,45,55.5)
    month_names=['jan','fev','mar','abr','mai','jun','jul','ago','set','out','nov','dez']
    for month,name in enumerate(month_names):text('Mês alvo '+name,name,(-4.9+month*.93,0,5.2),.23,white,45,55.5)
    for origin in range(7):
        z=4.55-origin*.44
        text('Origem '+str(origin),str(origin+1),(-6.0,0,z),.23,white,45,55.5)
        for offset in range(6):
            col=origin+offset;x=-4.9+col*.93
            obj=show(box('Alvo origem %d passo%d'%(origin,offset),(x,0,z),(.72,.30,.30),sky,.035),45,55.5)
            grow(obj,45.2+origin*.22+offset*.035,.35)
            if col==5:
                overlay=show(box('Alvo compartilhado '+str(origin),(x,-.04,z),(.77,.34,.34),gold,.04),52,55.5);grow(overlay,52,.5)
    text('Alvo repetido','Mesmo alvo em várias janelas',(0,0,1.0),.36,white,52,55.5)
    # A new locality is a symbolic untested site, not an invented geographic point.
    text('Generalização','Localidades inéditas não avaliadas',(0,0,6.1),.53,white,55.5,59)
    for i in range(10):factory_icon('Localidade conhecida '+str(i),(-5.6+(i%5)*1.5,0,2.4+(i//5)*1.3),neutral,sky,55.5,59)
    text('Conjunto conhecido','10 localidades do estudo',(-2.6,0,1.6),.34,white,55.5,59)
    factory_icon('Localidade inédita simbólica',(4.5,0,3.0),muted,sky,55.5,59,True)
    text('Não avaliada','Localidade nova',(4.5,0,2.3),.35,white,55.5,59)
    # Return to the approved physical setting for the handoff to the student's outro.
    from factory_site_v6 import build_factory_site_v6
    site=build_factory_site_v6()
    for mat in bpy.data.materials:
        if 'photovoltaic dark silicon' in mat.name and mat.use_nodes:
            bsdf=mat.node_tree.nodes.get('Principled BSDF')
            bsdf.inputs['Roughness'].default_value=.43
            bsdf.inputs['Metallic'].default_value=.10
            bsdf.inputs['Specular IOR Level'].default_value=.25
    objects=list(site['collection'].objects)+list(site['pv_collection'].objects)
    for o in objects:
        o.animation_data_clear();show(o,59,74)
    # Preserve the factory's nested tree/vehicle hierarchy when scaling the site.
    object_set=set(objects)
    bpy.context.view_layer.update()
    site_root=bpy.data.objects.new('Contexto industrial final genérico',None)
    scene.collection.objects.link(site_root)
    for o in objects:
        if o.parent not in object_set:
            world=o.matrix_world.copy();o.parent=site_root;o.matrix_world=world
    site_root.scale=(.17,.17,.17)
    keys(site_root,'scale',[(59,(.001,.001,.001)),(60.3,(.17,.17,.17))])
    hud(scene,'Liderança Transformer','Transformer',(-5,4.8),.64,cyan,59,67)
    hud(scene,'Tarefas Transformer','Horária · Diária',(-5,4.1),.43,white,59,67)
    hud(scene,'Liderança Informer','Informer',(5,4.8),.64,purple,59,67)
    hud(scene,'Tarefas Informer','Mensais',(5,4.1),.43,white,59,67)
    hud(scene,'Síntese final','A escolha depende da tarefa',(0,4.7),.65,white,67,74)
    # The final curve is a qualitative resource forecast, not simulated generation.
    graphroot=bpy.data.objects.new('Curva final em plano da câmera',None);scene.collection.objects.link(graphroot)
    graphroot.parent=scene.camera;graphroot.location=(0,2.4,-20)
    resource=lambda phase:max(0,math.sin(phase*.23))**1.35*(.65+.08*math.sin(phase*.57))
    pts=[(-4.7+i*.10,0,-resource(i)) for i in range(60)]
    curve=trace('Histórico final do recurso',pts,white,65,74,.022,1.2)
    curve.parent=graphroot;curve.rotation_euler=(math.pi/2,0,0)
    for i in range(12):
        x=1.4+i*.27
        p1=(x,0,-resource(60+i*2.7))
        p2=(x+.14,0,-resource(61.4+i*2.7))
        c=trace('Futuro final tracejado '+str(i),[p1,p2],cyan,66+i*.06,74,.024,.3);c.parent=graphroot;c.rotation_euler=(math.pi/2,0,0)
    # Camera remains quantitative/frontal until the final physical orbit.
    for second,loc,target,scale in [(0,(0,-28,6.9),(0,0,3.5),17.5),(11,(0,-28,6.9),(0,0,3.5),17.5),
        (21,(0,-28,6.9),(0,0,3.5),17.8),(31,(0,-28,6.9),(0,0,3.5),17.3),
        (45,(0,-28,6.9),(0,0,3.5),17.5),(55.5,(0,-28,6.9),(0,0,3.5),17.5),
        (58.8,(0,-28,6.9),(0,0,3.5),17.5),(59,(9,-23,15),(0,-.8,2.5),22),
        (74,(7,-24,14),(0,-.8,2.5),21.5)]:camera_key(scene,second,loc,target,scale)
    return {'duration':74,'cues':CUES,'qa_times':[1.5,6,16,25,29.5,34,41,48.5,53.5,57,63,70.5],
      'quantization_observed_counts':counts,'paired_history_count':11,'paired_history_total':12,
      'history_evaluation_period':data['paired_history']['test_period'],'history_values_are_separate_from_2024':True,
      'historical_exception':data['paired_history']['exception'],'source_notes':str(NOTES.relative_to(ROOT)),
      'no_inferential_significance_claim':True,'unseen_site_is_symbolic_not_a_geographic_point':True,
      'monthly6_test_origins':7,'final_factory_generic':True,'factory_site_metadata':site['metadata'],
      'final_curve_is_not_electricity_generation':True,'personal_camera_footage_included':False}
