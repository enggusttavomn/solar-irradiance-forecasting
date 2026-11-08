"""Final spoken-text pacing, independent of frozen rendered geometry."""
from copy import deepcopy
OVERRIDES={
 'modelos':{
 0:'comparar LSTM, Transformer e Informer.',
 51:'O mesmo histórico e ID entram nos três modelos.',
 },
 'geografia':{
 25:'Estas distribuições usam valores reais do período de treinamento.',
 },
 'entradas_tarefas':{
 32:'Comparei quatro tarefas, em diferentes escalas de tempo.',
 36:'Na tarefa horária, 336 horas formam duas semanas de histórico.',
 41.5:'A rede prevê as próximas 72 horas: três dias de irradiância.',
 47:'Na diária, 365 valores representam um ano de histórico.',
 52.5:'A saída prevê os próximos trinta dias, mantendo a separação entre passado e futuro.',
 58:'Na mensal de um passo, doze meses ajudam a prever o mês seguinte.',
 64:'Na outra mensal, uma rede própria prevê seis meses. Essa análise é exploratória.',
 }
}

def final_cues(name,source):
    return [(a,b,OVERRIDES.get(name,{}).get(a,text)) for a,b,text in source]
