"""Compact the validated protocol to make room for numerical explanations."""
from methodology_v8 import build as original
from retime_v9 import retime_actions
DURATION=54
CUES=[
 (0,6,'As tarefas mensais foram treinadas separadamente: uma prevê um mês; a outra, seis.'),
 (6,13,'Treinei inicialmente com dados de 2019 a 2022.'),
 (13,19,'A validação usa 2023. O teste usa 2024.'),
 (19,28,'Escolhi as configurações pela validação, por modelo e tarefa. A normalização respeitou os cortes temporais.'),
 (28,39,'Depois, reiniciei o treinamento com 2019 a 2023 e avaliei as previsões em 2024.'),
 (39,48,'Essa análise é retrospectiva: o teste de 2024 já havia sido examinado, o que limita sua independência.'),
 (48,54,'Comparei a precisão das previsões. Velocidade e memória computacional não foram medidas.')]
def build(scene):
    info=original(scene)
    retime_actions([(0,0),(12,6),(19,13),(26,19),(38,28),(49,39),(56,48),(62,54)])
    info.update(version=9,duration=54,cues=CUES,qa_times=[3,10,16,23,33,43,51])
    return info
