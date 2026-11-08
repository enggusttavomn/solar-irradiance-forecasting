"""Native animated analysis, metrics and result geometry (no slide panels)."""
import math
import bpy
from blender_pilot import sphere,box,visible,frame
from common_v4 import material,keys,camera_path,billboard_label as label,trace,block,flow,orbit
from overlays import load_results

GOLD='#E9B95F';WHITE='#F3F5F7';MUTED='#A9B2BE';CYAN='#58CADA';CORAL='#F28779';VIOLET='#AA91E8'
COLORS={'Transformer':CYAN,'Informer':VIOLET,'LSTM':CORAL}

def _materials(prefix):
    return {k:material(prefix+k,c,k!='body') for k,c in [('white',WHITE),('gold',GOLD),
      ('cyan',CYAN),('coral',CORAL),('violet',VIOLET),('muted',MUTED),('body','#344456')]}

def _labels(scene,items,a,b):
    return [label(scene,text,text,loc,size,color,a,b) for text,loc,size,color in items]

def quantization(scene,d=35):
    m=_materials('Quantização v4 ')
    curve=lambda x:1.45+1.25*(.52+.42*math.sin(x*1.15)+.13*math.sin(x*3))
    for row,levels in enumerate((None,64,128,256)):
        y=-1.5+row*1.15
        pts=[]
        for i in range(100):
            x=-4.3+8.6*i/99;z=curve(x)
            if levels:z=1.45+round((z-1.45)/1.4*(levels-1))/(levels-1)*1.4
            pts.append((x,y,z))
        trace('Amplitude '+str(levels),pts,m['white' if levels is None else 'gold'],0,10.5,2.5,.025)
        label(scene,'Níveis '+str(levels),'Contínuo' if levels is None else 'Q'+str(levels),(-4.7,y,3.4),.28,WHITE if levels is None else GOLD,0,10.5)
        for i in range(0,100,8):
            x,yy,z=pts[i];sample=block('Amostra de amplitude',(x,yy,z/2+.4),(.10,.10,z-.8),m['body'],i*.014,10.5,.8)
    steps=8;pts=[(-4.3,0,1.15)]
    for i in range(steps):
        x=-4.3+8.6*i/steps;z=1.15+2.3*i/(steps-1)
        pts.extend([(x,0,z),(x+8.6/steps,0,z)])
        block('Degrau de amplitude',(x+4.3/steps,.25,(z+.7)/2),(8.6/steps,.5,z-.7),m['gold'],10.5+i*.07,14.5,.5)
    trace('Arredondamento de amplitudes',pts,m['white'],10.5,14.5,.9,.025)
    label(scene,'Arredondar','Amplitudes → níveis',(0,0,4.2),.44,WHITE,10.5,14.5)
    for x,text in [(-3.6,'GHI'),(0,'Quantizador'),(3.6,'float32')]:
        block('Processamento '+text,(x,0,2.6),(1.5,.7,1.3),m['body' if x else 'gold'],14.5,21.6,.6)
        label(scene,text,text,(x,-.55,3.7),.36,WHITE,14.5,21.6)
    path=[(-4.4,-.45,2.6),(0,-.45,2.6),(4.3,-.45,2.6)]
    trace('Fluxo GHI',path,m['gold'],14.7,21.6,.9,.03);flow('Informação GHI',path,m['gold'],15,21.6,2.5,6,.075)
    bypass=[(-4.3,0,1.7),(-4.3,0,.9),(4.3,0,.9),(4.3,0,1.7)]
    trace('ID preservado',bypass,m['cyan'],15,21.6,1.2,.022);flow('ID',bypass,m['cyan'],15,21.6,3,3,.055)
    label(scene,'ID','Identificação da localidade',(0,0,.55),.28,CYAN,15,21.6)
    for z,text in [(1.3,'0'),(3.6,'1')]:
        trace('Limite '+text,[(-4.5,0,z),(4.5,0,z)],m['muted'],21.6,28.2,.6,.018)
        label(scene,'Limite '+text,text,(-4.9,0,z),.32,MUTED,21.6,28.2)
    raw=[];clipped=[]
    for i in range(100):
        x=-4.3+8.6*i/99;z=2.45+1.65*math.sin(x*.9)
        limited=max(1.3,min(3.6,z))
        rounded=1.3+round((limited-1.3)/2.3*63)/63*2.3
        raw.append((x,.12,z));clipped.append((x,-.08,rounded))
    trace('Antes do clipping',raw,m['muted'],21.6,28.2,1.3,.018)
    trace('Depois do clipping',clipped,m['gold'],22.3,28.2,1.3,.035)
    label(scene,'Clipping','Clipping + arredondamento',(0,0,4.45),.40,GOLD,21.6,28.2)
    for x,text in [(-3.3,'Validação'),(3.3,'Teste')]:
        block('Condição '+text,(x,0,2.5),(1.75,.9,1.3),m['body'],28.2,35,.6)
        label(scene,text,text,(x,-.6,3.7),.38,WHITE,28.2,35)
    trace('Mesma condição',[(-2.4,0,2.5),(2.4,0,2.5)],m['gold'],28.5,35,1,.035)
    moving=block('Condição selecionada',(-2.4,-.3,2.5),(.5,.5,.5),m['gold'],28.5,35,.3)
    keys(moving,'location',[(28.5,(-2.4,-.3,2.5)),(32,(2.4,-.3,2.5)),(35,(2.4,-.3,2.5))])
    label(scene,'Mantida','Mesma condição',(0,0,1.5),.36,GOLD,29,35)
    camera_path(scene,[{'t':0,'location':(6.8,-15,10),'target':(0,0,1.7),'lens':48},
      {'t':8,'location':(-2.2,-15,7),'target':(0,0,1.7),'lens':52},
      {'t':10.5,'location':(2,-15,6.5),'target':(0,0,2.0),'lens':48},
      {'t':20,'location':(-1.7,-15,5.2),'target':(0,0,1.9),'lens':48},
      {'t':28,'location':(1.2,-15,5),'target':(0,0,2.1),'lens':48},
      {'t':35,'location':(-1,-14.5,6),'target':(0,0,2.0),'lens':48}])
    return {'native_geometry':True,'real_levels':[64,128,256],'steps_for_demonstration':8}

def mae(scene,d=30):
    m=_materials('MAE v4 ')
    ref=lambda x:2.4+.7*math.sin(x*1.25)+.16*math.cos(x*2.8)
    pred=lambda x:ref(x)+.26*math.sin(x*2.15+.7)+.13
    xs=[-4.4+8.8*i/180 for i in range(181)]
    for name,func,key in [('Referência',ref,'white'),('Previsão',pred,'gold')]:
        trace(name,[(x,0,func(x)) for x in xs],m[key],0 if key=='white' else 1,13.4,2.1,.035)
        label(scene,name,name,(-3 if key=='white' else 2.5,0,4.25),.36,WHITE if key=='white' else GOLD,0,13.4)
    for i in range(16):
        x=-4.1+i*.53;a=ref(x);b=pred(x)
        block('Erro absoluto '+str(i),(x,0,(a+b)/2),(.06,.22,max(.01,abs(a-b))),m['gold'],3+i*.3,13.4,.35)
    label(scene,'Métrica','MAE · W/m²',(0,0,1.1),.46,WHITE,4,13.4)
    center=(0,0,2.5)
    for i in range(10):
        angle=2*math.pi*i/10;loc=(3.8*math.cos(angle),.25*math.sin(angle),2.5+1.45*math.sin(angle))
        obj=sphere('Localidade '+str(i),loc,.16,m['cyan']);visible(obj,13.4+i*.05,20)
        trace('Peso igual '+str(i),[loc,center],m['muted'],14+i*.08,20,.5,.018)
        bead=sphere('Contribuição '+str(i),loc,.085,m['gold']);visible(bead,15+i*.05,20)
        keys(bead,'location',[(15+i*.05,loc),(18+i*.06,center)])
    obj=sphere('Média com pesos iguais',center,.26,m['gold']);visible(obj,17.5,20)
    label(scene,'Macro','10 localidades · mesmo peso',(0,0,4.5),.42,WHITE,13.4,20)
    for i in range(13):
        x=-4.3+i*8.6/12
        block('Passo cumulativo '+str(i),(x,0,2.3),(.44,.4,.75),m['body'],20+i*.07,30,.5)
        lit=block('Passo incluído '+str(i),(x,-.26,2.3),(.44,.13,.75),m['gold'],20.7+i*.34,30,.3)
    trace('Todos os passos',[(-4.6,0,3.45),(4.6,0,3.45)],m['gold'],21,30,4.2,.025)
    label(scene,'Horizonte','1 → 72 h',(0,0,4.25),.46,WHITE,20,30)
    label(scene,'Acumulado','Todos os passos até o horizonte',(0,0,1.3),.34,MUTED,21,30)
    orbit(scene,30,(0,0,2.1),15.6,48,1.5)
    return {'metric':'macro-MAE W/m²','equal_locality_weights':10,'cumulative':True}

def _result_rows():
    return load_results()

def results(scene,d=60):
    m=_materials('Resultados v4 ')
    # Input rows come directly from the consolidated report CSV.
    data=_result_rows()
    return _results_native(scene,m,data,d)

def _results_native(scene,m,data,d):
    # Match the public dictionary returned by overlays.load_results.
    phases=[(0,13.5,'hourly_72_extension',150,'Horária · até 72 h'),
      (13.5,19.9,'daily_30',50,'Diária · até 30 d'),
      (19.9,30,'gap',None,'Vantagens pequenas sobre a LSTM'),
      (30,38.6,'monthly_1',16,'Mensal · 1 passo'),
      (38.6,45.2,'monthly_6',16,'Mensal · até 6 passos'),
      (45.2,51,'local',None,'A liderança varia por localidade'),
      (51,60,'horizons',None,'Diária · horizontes cumulativos')]
    # Adapt result keys using task names from the data loader.
    aliases={'hourly_72_extension':'horario','daily_30':'diario','monthly_1':'mensal_1','monthly_6':'mensal_6'}
    animated_bars={}
    for a,b,key,scale,title in phases:
        label(scene,title,title,(0,0,4.65),.46,WHITE,a,b)
        if scale is not None:
            rows=data.get(key,data.get(aliases[key],[]))
            if isinstance(rows,dict): rows=[dict(model=k,**v) if isinstance(v,dict) else {'model':k,'mae':v} for k,v in rows.items()]
            if not rows: raise ValueError('No result rows for '+key+'; keys='+str(data.keys()))
            by_model={r.get('model',r.get('modelo')):r for r in rows}
            for i,model in enumerate(('Transformer','Informer','LSTM')):
                row=by_model[model];value=float(row.get('mae',row.get('MAE',row.get('mae_macro'))))
                condition=str(row.get('variant',row.get('condition',row.get('config',row.get('quantization','')))))
                z=3.55-i*1.1;length=value/scale*7.1
                group='hourly_daily' if a<20 else 'monthly'
                cache_key=(group,model)
                if cache_key not in animated_bars:
                    bar=box(model+' MAE '+group,(-2.4+length/2,0,z),(1,.46,.34),m[{'Transformer':'cyan','Informer':'violet','LSTM':'coral'}[model]],.06)
                    visible(bar,a,19.9 if a<20 else 45.2)
                    keys(bar,'scale',[(a,(.001,1,1)),(a+1.15,(length,1,1))])
                    keys(bar,'location',[(a,(-2.4,0,z)),(a+1.15,(-2.4+length/2,0,z))])
                else:
                    bar,previous=animated_bars[cache_key]
                    keys(bar,'scale',[(a-.2,(previous,1,1)),(a+1.15,(length,1,1))])
                    keys(bar,'location',[(a-.2,(-2.4+previous/2,0,z)),(a+1.15,(-2.4+length/2,0,z))])
                animated_bars[cache_key]=(bar,length)
                label(scene,model,model,(-4.55,0,z+.1),.32,COLORS[model],a,b,align='LEFT')
                label(scene,'Valor '+model,f'{value:.2f}'.replace('.',','),(5.3,0,z+.02),.42,WHITE,a+.25,b)
                if condition:label(scene,'Condição '+model,condition,(-3.6,0,z-.38),.23,MUTED,a,b)
            trace('Eixo zero '+key,[(-2.4,0,.75),(4.7,0,.75)],m['muted'],a,b,.6,.012)
            for frac in (0,.5,1):label(scene,'Escala '+str(frac),f'{scale*frac:g}',(-2.4+frac*7.1,0,.43),.25,MUTED,a,b)
            label(scene,'Unidade','Macro-MAE · W/m²',(1.1,0,.02),.28,MUTED,a,b)
            if key=='monthly_6':label(scene,'Exploratório','Exploratório',(3.8,0,4.2),.25,VIOLET,a,b)
            if key=='daily_30':label(scene,'Referência horária','Horária · Transformer 53,21',(-2.2,0,4.15),.26,MUTED,a,b)
            if key=='monthly_6':label(scene,'Referência mensal1','Mensal 1 · Informer 12,73',(-2.2,0,4.15),.26,MUTED,a,b)
        elif key=='gap':
            for x,text,value in [(-2.6,'Horária','≈ 0,32 W/m²'),(2.6,'Diária','≈ 0,30 W/m²')]:
                label(scene,text,text,(x,0,3.6),.36,WHITE,a,b)
                label(scene,value,value,(x,0,2.8),.54,CYAN,a,b)
                trace('Diferença pequena '+text,[(x-1.2,0,1.9),(x+1.2,0,1.9)],m['cyan'],a+.4,b,2,.055)
            label(scene,'Descritivas','Diferenças descritivas',(0,0,1),.32,MUTED,a,b)
        elif key=='local':
            for x,title,counts in [(-2.5,'Horária',(7,3)),(2.5,'Diária',(6,4))]:
                label(scene,title,title,(x,0,3.8),.36,WHITE,a,b)
                for j in range(10):
                    color='cyan' if j<counts[0] else 'coral'
                    block('Liderança '+title+str(j),(x-1.2+(j%5)*.6,0,2.8-(j//5)*.7),(.35,.35,.35),m[color],a+j*.12,b,.4)
                label(scene,'Contagem '+title,f'Transformer {counts[0]} · LSTM {counts[1]}',(x,0,1.15),.28,WHITE,a,b)
        else:
            for i,(text,model) in enumerate([('1 d','LSTM'),('3 d','LSTM'),('7 d','LSTM'),('14 d','LSTM'),('30 d','Transformer')]):
                x=-4+i*2;keymat='coral' if model=='LSTM' else 'cyan'
                block('Horizonte '+text,(x,0,2.5),(.8,.7,.8),m[keymat],a+i*.3,b,.6)
                label(scene,text,text,(x,0,3.6),.4,WHITE,a+i*.1,b)
                label(scene,model,model,(x,0,1.55),.28,COLORS[model],a+i*.2,b)
            trace('Horizontes',[(-4,0,2.5),(4,0,2.5)],m['muted'],a,b,1.6,.02)
    camera_path(scene,[{'t':0,'location':(.4,-17.5,6.1),'target':(.2,0,1.85),'lens':48},
      {'t':12.5,'location':(-.8,-17,5.8),'target':(.2,0,1.85),'lens':48},
      {'t':20,'location':(1.4,-17,6.2),'target':(0,0,1.95),'lens':48},
      {'t':30,'location':(-.5,-17,5.9),'target':(.2,0,1.85),'lens':48},
      {'t':45,'location':(.8,-17.4,6),'target':(.2,0,1.85),'lens':48},
      {'t':60,'location':(-.8,-17,6),'target':(0,0,1.95),'lens':48}])
    return {'actual_csv_values':True,'bars_start_zero':True,'native_3d_bars':True,'phases':phases}

def complements(scene,d=20):
    m=_materials('Complementos v4 ')
    for x,count,text,key in [(-3,5,'melhoras','gold'),(0,4,'pioras','coral'),(3,3,'controles','muted')]:
        label(scene,text,str(count),(x,0,3.7),.7,WHITE,0,3.4)
        label(scene,text+' label',text,(x,0,2.8),.34,WHITE,0,3.4)
        for i in range(count):
            obj=sphere(text+str(i),(x-.8+i*.38,0,1.9),.11,m[key]);visible(obj,i*.08,3.4)
    for z,x0,text in [(3.6,-4.4,'Histórico longo'),(2.3,-2.8,'Histórico curto')]:
        trace(text,[(x0,0,z),(-.25,0,z)],m['cyan'],3.4,20,1.3,.10)
        trace(text+' validação',[(-.1,0,z),(.65,0,z)],m['white'],3.4,20,.7,.10)
        trace(text+' teste',[(.85,0,z),(2.4,0,z)],m['gold'],3.4,20,.7,.10)
        label(scene,text,text,(-4.5,0,z+.45),.28,WHITE,3.4,20,align='LEFT')
    trace('Mesmo corte',[(-.18,0,1.9),(-.18,0,4.1)],m['muted'],4,20,.6,.02)
    label(scene,'Pareado','Mesmos cortes de avaliação',(0,0,4.8),.38,WHITE,3.4,20)
    for i in range(12):
        x=-4.4+i*.62
        block('Comparação '+str(i),(x,0,1.2),(.32,.32,.32),m['gold' if i<11 else 'muted'],5+i*.25,20,.6)
    label(scene,'Onze','11 de 12 controles contínuos',(0,0,.45),.40,GOLD,6,20)
    label(scene,'Associação','Associação observada',(3.8,0,3),.34,WHITE,12.9,20)
    orbit(scene,20,(0,0,2.1),16.5,48,1.3)
    return {'selected_conditions_counts':[5,4,3],'historical_paired_controls_improved':11,'historical_controls_total':12}

def limits(scene,d=15):
    m=_materials('Limitações v4 ')
    trace('Curva descritiva',[(-4+i*.05,0,2.2+.3*math.sin(i*.12)) for i in range(160)],m['white'],0,5.3,2,.035)
    label(scene,'Descritivo','Resultados descritivos',(0,0,3.7),.48,WHITE,0,5.3)
    label(scene,'Significância','Sem significância estatística demonstrada',(0,0,1.3),.34,MUTED,0,5.3)
    obj=sphere('Uma semente',(-2.7,0,2.5),.32,m['gold']);visible(obj,5.3,10)
    label(scene,'Uma semente','Horária · uma semente',(-2.7,0,3.7),.36,WHITE,5.3,10)
    for i in range(6):block('Passo mensal '+str(i),(1+i*.6,0,2.5),(.27,.27,.27),m['violet'],5.3+i*.15,10,.5)
    label(scene,'Exploratório','6 meses · exploratório',(2.6,0,3.7),.36,VIOLET,5.3,10)
    for i,x in enumerate((-2.8,-1.5)):
        z=2.5+i*.12;y=i*.25
        points=[(x-1.65,y,z-.55),(x+1.65,y,z-.55),(x+1.65,y,z+.55),(x-1.65,y,z+.55),(x-1.65,y,z-.55)]
        trace('Janela que compartilha alvos '+str(i),points,m['coral' if i==0 else 'cyan'],10+i*.2,15,.7,.035)
    for i in range(6):
        obj=sphere('Alvo compartilhado '+str(i),(-3.5+i*.7,-.3,2.5),.1,m['gold']);visible(obj,10.4+i*.1,15)
    label(scene,'Sobreposição','Janelas compartilham alvos',(-2,0,3.7),.34,WHITE,10,15)
    label(scene,'Novas localidades','Localidades inéditas\nnão avaliadas',(3.1,0,2.5),.38,MUTED,10,15)
    orbit(scene,15,(0,0,2.15),15.5,48,1.6)
    return {'descriptive':True,'hourly_seeds':1,'monthly6_exploratory':True,'overlapping_targets':True}

def closing(scene,d=10):
    m=_materials('Síntese v4 ')
    routes=[(-2.8,'Até 72 h / 30 d','Transformer','cyan'),(2.8,'Mensais','Informer','violet')]
    pts=[(-4.5+i*.05,0,1.6+.5*math.sin(i*.13)) for i in range(180)]
    trace('Histórico vira previsão',pts,m['white'],0,10,2.5,.035)
    for x,task,model,key in routes:
        block(model,(x,0,3),(.95,.7,.95),m[key],0,10,.7)
        trace('Ligação '+model,[(0,0,1.6),(x,0,2.5)],m[key],.8,10,1.3,.028)
        label(scene,model,model,(x,0,4.2),.44,COLORS[model],0,10)
        label(scene,task,task,(x,0,3.8),.30,WHITE,0,10)
    label(scene,'Depende da tarefa','A escolha depende da tarefa',(0,0,.8),.46,WHITE,3,10)
    orbit(scene,10,(0,0,2.1),15.5,48,1.1)
    return {'handoff_to_user_camera':True}

def build_analysis_v4(chapter_id,duration,scene):
    return {8:quantization,9:mae,10:results,11:complements,12:limits,13:closing}[chapter_id](scene,duration)
