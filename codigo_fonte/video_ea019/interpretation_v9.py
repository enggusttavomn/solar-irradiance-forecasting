"""Conclude with the actual report findings and the physical factory setting."""
import bpy
from interpretation_v8 import build as original, hud
from common_v7 import WHITE,emission
from retime_v9 import retime_actions
DURATION=52
CUES=[
 (0,6,'Quantizar foi uma hipótese de melhoria, não uma garantia. Houve ganhos e perdas.'),
 (6,12,'Numa análise histórica separada, comparei históricos longo e curto nas mesmas datas de avaliação.'),
 (12,18,'O longo teve menor erro em onze de doze comparações. A exceção foi a LSTM horária.'),
 (18,22,'Isso não isola uma causa: anos e normalização também mudaram.'),
 (22,28,'As diferenças são descritivas. O horário usa uma semente; as demais tarefas combinam cinco previsões.'),
 (28,36,'A tarefa de seis meses é exploratória: sete origens por localidade, com alvos compartilhados.'),
 (36,39,'Localidades inéditas ainda precisam ser avaliadas.'),
 (39,45,'Transformer teve menor erro horário e diário; Informer, nas tarefas mensais.'),
 (45,52,'A escolha depende da tarefa e precisa ser confirmada em novos testes.')]
def build(scene):
    info=original(scene)
    retime_actions([(0,0),(11,6),(21,12),(31,18),(37,22),(45,28),(55.5,36),(59,39),(67,45),(74,52)])
    for o in bpy.data.objects:
        if o.type=='FONT' and o.data.body=='Efeito das entradas quantizadas':
            o.data.body='A quantização melhorou a previsão?'
    white=emission('V9 próximos passos',WHITE,.9)
    hud(scene,'Próximos passos do relatório','Novos anos de teste · métodos de referência simples',(0,3.8),.35,white,46,52)
    info.update(version=9,duration=52,cues=CUES,qa_times=[3,9,15,20,25,32,37.5,42,49.5],
                conclusion_report_page=30,personal_outro_footage_required=False)
    return info
