"""Keep the approved mechanisms, make the locality visible as a factory."""
import bpy
from common_v7 import *
from models_explainer_v7 import build as original
from narration_v7 import final_cues
DURATION=60
def icon(name,x,z,a,b):
    mat=surface(name+' parede',(.55,.65,.68,1),.02,.55)
    glass=surface(name+' vidro',(.13,.40,.52,1),.05,.38)
    objs=[box(name+' galpão',(x,0,z),(.96,.5,.58),mat,.04),
          box(name+' cobertura',(x,0,z+.34),(1.02,.55,.10),mat,.02),
          box(name+' fachada',(x,-.27,z+.02),(.75,.035,.18),glass,.015)]
    for o in objs:visible(o,a,b);grow(o,a,.4)
    return objs
def build(scene):
    info=original(scene)
    for o in bpy.data.objects:
        if o.type=='FONT':
            if o.data.body=='Mesmo histórico + ID':o.data.body='Mesmo histórico e localidade'
            elif o.data.body=='ID da localidade':o.data.body='Camaçari'
            elif o.data.body=='ID':o.data.body='Camaçari'
        if 'comparison exact same locality embedding' in o.name:
            o.animation_data_clear();o.hide_render=True
    icon('V9 fábrica na comparação',-5.5,2.15,51.5,60)
    # A familiar site symbol accompanies the already learned locality vector.
    icon('V9 identidade da fábrica LSTM',4.65,4.8,16,18.4)
    info.update(version=9,cues=final_cues('modelos',info['cues']),qa_times=[17,53.8,58],
                updated_ranges_seconds=[[16,19],[51,60]],known_factory_city='Camaçari')
    info['cues'][0]=(0,4,'Comparei LSTM, Transformer e Informer. Como funcionam?')
    info['cues']=[(a,b,'O mesmo histórico e a mesma localidade entram nos três modelos.' if a==51 else t)
                  for a,b,t in info['cues']]
    return info
