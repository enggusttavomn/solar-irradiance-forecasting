"""Revise prose in the retained TCC, preserving experimental and template parts."""
from pathlib import Path
from zipfile import ZipFile
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sys
from lxml import etree as ET

sys.stdout.reconfigure(encoding='utf-8')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Revisado.docx'
OUTPUT = SOURCE.with_name('Relatorio_Final_GHI_Transformer_Informer_LSTM_TCC.docx')
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
M = 'http://schemas.openxmlformats.org/officeDocument/2006/math'
NS = {'w': W, 'm': M, 'wp': 'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing',
      'a': 'http://schemas.openxmlformats.org/drawingml/2006/main'}
digest = lambda b: hashlib.sha256(b).hexdigest()

with ZipFile(SOURCE) as z:
    infos = z.infolist()
    original = {i.filename: z.read(i.filename) for i in infos}
root = ET.fromstring(original['word/document.xml'])
body = root.find('w:body', NS)
paragraphs = root.xpath('//w:body//w:p', namespaces=NS)
assert len(paragraphs) == 1255, 'Source document changed; remap the editorial indices.'
before_tables = [ET.tostring(e, method='c14n') for e in root.findall('.//w:tbl', NS)]
before_math = [ET.tostring(e, method='c14n') for e in root.findall('.//m:oMath', NS)]
assert len(before_tables) == 15 and len(before_math) == 7

edits = {int(k): v for k, v in json.loads((HERE / 'sugestoes_editoriais.json').read_text(encoding='utf-8'))['replacements'].items()}
edits.update({
    16: 'Trabalho de conclusão de curso apresentado à Faculdade de Engenharia Elétrica e de Computação da Universidade Estadual de Campinas, no âmbito da disciplina EA019 do curso de Engenharia Elétrica.',
    30: 'Este trabalho avalia a previsão de irradiância global horizontal (GHI) com LSTM, Transformer e Informer, considerando a discretização das entradas, as tarefas temporais e a duração do histórico de ajuste. São utilizadas estimativas da National Solar Radiation Database em dez localidades associadas à fabricação de veículos elétricos no Brasil, nos Estados Unidos e no México. O protocolo compreende previsão horária de até 72 horas, diária de até 30 dias, mensal de um passo e mensal de seis passos, sendo a última exploratória. Comparam-se históricos normalizados contínuos com reconstruções em 64, 128 e 256 níveis, mantendo alvos, pesos e saídas contínuos. O número de épocas e a condição de entrada são selecionados na validação. O erro absoluto médio (MAE) é calculado por localidade e agregado com pesos iguais.',
    31: 'No teste de 2024, o Transformer apresentou os menores MAEs cumulativos nos horizontes completos horário e diário, de 53,21 e 43,89 W/m². O Informer liderou as tarefas mensais, com 12,73 W/m² em um passo e 13,67 W/m² em seis passos. As entradas quantizadas selecionadas na validação reduziram o MAE de teste em cinco combinações de modelo e tarefa e o elevaram em quatro; nas três restantes, foi selecionado o controle contínuo. Na comparação histórica pareada, ampliar o histórico reduziu o erro do controle em onze das doze combinações. A ordenação dos modelos variou entre tarefas e localidades, e a quantização não ofereceu benefício uniforme. Como as variantes quantizadas também aplicam saturação (clipping), seus efeitos não podem ser atribuídos apenas ao arredondamento. As conclusões se restringem à precisão preditiva, sem mensuração de compressão, aceleração computacional ou produção fotovoltaica.',
    76: 'O problema central é avaliar como a redução da resolução de amplitude do histórico de GHI afeta a precisão de três redes de previsão temporal. Para isso, comparam-se históricos normalizados mantidos contínuos ou reconstruídos em 64, 128 ou 256 níveis. A análise investiga a sensibilidade das previsões à precisão da informação fornecida às redes, mantendo contínuos os alvos, os pesos e as saídas.',
    79: 'A contribuição do TCC é comparar a sensibilidade de três arquiteturas às condições de entrada em quatro tarefas de previsão de GHI, sob regras comuns de separação temporal e avaliação. A análise combina desempenho agregado e local com uma comparação pareada da duração do histórico de ajuste. Os resultados provêm dos experimentos do projeto e são apresentados com rastreabilidade aos dados e às configurações executadas.',
    81: 'O estudo responde a três questões: como as condições de entrada quantizadas alteram o erro em cada tarefa; como a condição selecionada na validação se comporta no teste em relação ao controle contínuo; e como a ampliação do histórico de ajuste se relaciona com o desempenho quando validação e teste são mantidos idênticos. Essas questões orientam a análise das quatro condições de entrada, a avaliação de 2024 e a comparação dos históricos longo e curto pareados.',
    83: 'As seções seguintes apresentam os objetivos, a metodologia, os fundamentos físicos e das arquiteturas, os resultados e as conclusões. Os apêndices detalham os horizontes de avaliação, as condições de entrada, a proveniência dos dados e os perfis de um estudo complementar.',
    99: 'A base contém dez séries de GHI associadas a coordenadas de referência de instalações industriais nas Américas. A Figura 1 situa as localidades, e a Tabela 1 apresenta suas coordenadas. A seleção é intencional e reúne contextos geográficos distintos, sem constituir uma amostra aleatória de fábricas ou climas. As coordenadas identificam células da NSRDB, e não sensores instalados nas unidades industriais.',
    100: 'A documentação da API PSM v4 informa resolução espacial nominal de 4 km e registros nativos de 30 minutos, com consultas em intervalos de 30 ou 60 minutos [2]. No projeto, a série horária é formada a partir dos registros de 30 minutos. As médias diárias provêm de uma consulta independente em 60 minutos, e as mensais são médias aritméticas das diárias. Todas conservam a unidade W/m²; contudo, as séries horária e diária não devem ser tratadas como agregações do mesmo conjunto de registros brutos.',
    150: 'A preparação verifica a coerência temporal e a identidade das localidades. Valores de GHI não finitos ou negativos, datas inválidas, duplicatas e lacunas provocam falha na validação dos dados; registros fora de ordem são reordenados. Não se utiliza preenchimento por interpolação ou inserção de zeros. Cada janela contém apenas observações anteriores à origem da previsão, e todo o vetor de alvos deve pertencer à partição correspondente.',
    151: 'A origem é o instante em que se emite um vetor de previsão. Janelas consecutivas podem compartilhar instantes-alvo, de modo que o número de pares de origem e passo previsto supera o de instantes distintos. Esses pares são preservados na avaliação, pois correspondem a previsões emitidas com informações disponíveis em momentos diferentes. A sobreposição também introduz dependência entre os erros.',
    153: 'A Figura 2 caracteriza a GHI de referência de BYD Camaçari em intervalos fixos de 2024. A série horária evidencia os ciclos diurnos, enquanto as médias diárias e mensais sintetizam períodos progressivamente mais longos. Os três painéis conservam a unidade W/m² e ilustram a mudança de estrutura dos dados com a agregação temporal; não representam previsões dos modelos.',
    154: 'Figura 2 — Perfis de referência da GHI nas resoluções horária diária e mensal',
    189: 'Os horizontes de avaliação são 24, 48 e 72 horas; 1, 3, 7, 14 e 30 dias; um mês na tarefa mensal curta; e 1, 3 e 6 meses na tarefa exploratória. As métricas apresentadas são cumulativas: o MAE de 72 horas, por exemplo, reúne os passos de 1 a 72 de todas as origens válidas, em vez de considerar somente o erro no último instante.',
    193: 'Fonte: elaboração própria. Blocos sem escala proporcional de duração. O novo ajuste anterior ao teste (refit) incorpora somente dados anteriores a esse período. Histórico longo e curto pareado compartilham validação e teste; o regime atual avalia outro período.',
    217: 'A comparação da duração do histórico utiliza os regimes longo e curto pareado, com validação, teste e alvos idênticos, conforme a auditoria de pareamento. Já a avaliação de 2024 corresponde a outro período. Comparar diretamente seus erros aos do teste histórico não permite atribuir as diferenças à quantidade de anos de treinamento.',
    218: 'Na tarefa horária histórica, a auditoria registra 1.368 origens válidas por localidade, em vez das 1.369 previstas genericamente no contrato. A cobertura em UTC não contém todo o horizonte local da origem de 29 de dezembro de 2022, que foi excluída dos dois históricos. As análises utilizam as contagens efetivamente auditadas, sem acrescentar observações artificiais.',
    221: 'Fonte: elaboração própria, com organização em faixas adaptada da Figura 2 de Nascimento, Cabral e Fraidenraich [14] para a comparação de três modelos sob quantização das entradas. As escolhas são fixadas na validação e avaliadas no teste. Na tarefa horária há uma semente; nas demais, combinam-se as previsões de cinco sementes.',
    223: 'Para cada localidade, o mínimo e o máximo usados na normalização são estimados exclusivamente com os dados anteriores ao corte da etapa correspondente. Na seleção do regime atual, utilizam-se dados anteriores a 2023; no refit, anteriores a 2024. A mesma regra vale para os cortes históricos. A Equação 1 transforma um valor x na entrada normalizada u, sendo a e b, respectivamente, o mínimo e o máximo estimados com os dados admissíveis.',
    225: 'As variantes quantizadas aplicam a Equação 2 ao histórico X, com N em {64, 128, 256}. Primeiro, a saturação, ou clipping, limita a entrada ao intervalo de zero a um. Em seguida, a função rint arredonda para o inteiro mais próximo, escolhendo o inteiro par em empates exatos. A Figura 6 ilustra a combinação de saturação e discretização.',
    250: 'O controle contínuo não aplica clipping. Assim, a comparação com as variantes quantizadas combina os efeitos do arredondamento e da saturação de entradas fora da faixa de treinamento. A ausência de um controle com apenas clipping impede separar esses efeitos. Além disso, o limite de arredondamento da Tabela 4 descreve a transformação da entrada e não estabelece um limite para o erro de previsão da rede.',
    255: 'O fluxo da Figura 5 organiza as etapas de dados, seleção e avaliação. Os três modelos minimizam MSE na escala normalizada. O número de épocas é selecionado pela perda de validação, separadamente por variante e semente. A condição de entrada é escolhida pelo menor macro-MAE em W/m² da previsão combinada na validação, considerando o horizonte completo. Em caso de empate, a prioridade é controle, 64, 128 e 256 níveis. A condição escolhida permanece fixa nos horizontes menores, sem nova seleção a partir do teste.',
    256: 'No refit, os pesos são reinicializados com a mesma semente, e o treinamento utiliza os dados anteriores ao teste pelo número de épocas já selecionado. Esse procedimento incorpora dados adicionais sem consultar o teste para decidir a duração do treinamento. Como épocas e condição de entrada são escolhidas na mesma validação, o protocolo não corresponde a uma validação aninhada.',
    289: 'As sementes controlam as fontes de aleatoriedade de cada execução. Nas tarefas diária e mensais, as previsões brutas das cinco sementes são convertidas de volta para W/m² e combinadas por média aritmética. As regras físicas de pós-processamento são aplicadas depois dessa média. Na tarefa horária utiliza-se somente a semente 42. Portanto, as tabelas principais apresentam o erro da previsão combinada, que difere da média dos erros individuais das sementes.',
    290: 'Aplica-se piso zero em todas as resoluções. Na tarefa horária, também se anulam previsões quando a elevação solar no centro do intervalo é não positiva, calculada com pvlib [11]. Não se aplica um teto físico comum. A geometria solar atua somente no pós-processamento. A ordem das operações importa: calcular a média antes do piso não equivale, em geral, a combinar previsões já truncadas.',
    292: 'As métricas são calculadas após a inversão da escala e o pós-processamento. Seja eᵢ o valor de referência yᵢ menos a previsão, e n o número de pares de origem e passo previsto em uma localidade. As Equações 3 e 4 definem o erro absoluto médio (MAE), o erro quadrático médio (MSE) e sua raiz quadrada (RMSE). O MAE é a medida principal por expressar diretamente a magnitude média do erro; MSE e RMSE atribuem maior influência a desvios grandes [8,9]. As Equações 5 e 6 apresentam o RMSE normalizado (nRMSE) e o coeficiente de determinação (R²).',
    297: 'O nRMSE divide o RMSE pela média da GHI de referência no vetor avaliado. Os arquivos CSV armazenam essa razão, e as tabelas percentuais a multiplicam por cem. O R² compara a soma dos erros quadráticos com a variação em torno da média de avaliação; pode ser negativo e fica indefinido quando seu denominador é numericamente nulo. Valores indefinidos não são substituídos por zero.',
    301: 'Na tarefa horária, as emissões à meia-noite fazem os passos exatos de 24, 48 e 72 horas coincidirem com intervalos noturnos. Erros nulos nesses instantes não demonstram previsão diurna perfeita. Por isso, os gráficos e as classificações utilizam métricas cumulativas, que incluem todos os passos até o horizonte indicado.',
    305: 'A evolução da GHI combina regularidades geométricas e variações atmosféricas. O movimento aparente do Sol estabelece ciclos diurnos e sazonais; nuvens, aerossóis e outras condições da atmosfera modificam a radiação que alcança a superfície. A agregação temporal pode atenuar oscilações rápidas, mas não elimina necessariamente a sazonalidade ou a persistência das condições meteorológicas. Assim, prever sequências horárias, médias diárias e médias mensais constitui problemas distintos, cujo desempenho deve ser interpretado junto à resolução do alvo, ao horizonte e às informações disponíveis na emissão [13].',
    328: 'Os estudos do projeto oferecem contexto, mas utilizam modelos e protocolos distintos. Os resultados de TimesNet e DilatedRNN são tratados como evidência complementar, separada da comparação principal deste TCC. Cabral, Fraidenraich e Capretz investigaram previsão mensal de longo prazo de GHI da NSRDB com GPT-Neo [12]. As diferenças de localidades, horizontes, processamento e modelos impedem a comparação direta de seus erros com os deste trabalho.',
    331: 'Esta seção apresenta a comparação de três modelos sob quatro condições de entrada. Os resultados principais utilizam a condição selecionada na validação e o horizonte cumulativo completo. O Apêndice A detalha os horizontes menores, e o Apêndice B reúne os MAEs das quatro condições nos três regimes. As escolhas e os gráficos usam a precisão integral dos arquivos auditados; o arredondamento é aplicado somente à apresentação.',
    332: 'Primeiro, discutem-se o teste de 2024, a heterogeneidade entre localidades, a resposta à quantização e o comportamento por horizonte. Em seguida, compara-se a duração do histórico sob validação e teste pareados. Essa organização separa perguntas experimentais distintas. Os perfis de TimesNet e DilatedRNN do estudo de referência [14] ficam no Apêndice D, como material complementar.',
    430: 'A Tabela 6 e a Figura 8 sintetizam o teste de 2024 nas quatro tarefas, utilizando as condições de entrada selecionadas em 2023. A comparação considera a semente 42 na tarefa horária e a média das previsões de cinco sementes nas tarefas diária e mensais, conforme a Tabela 5.',
    431: 'Nos horizontes completos horário e diário, o Transformer apresentou os menores macro-MAEs, de 53,21 e 43,89 W/m². Suas diferenças para a LSTM foram de 0,32 e 0,30 W/m². Essa proximidade recomenda examinar também o horizonte e o desempenho local antes de preferir uma arquitetura. O Informer apresentou MAE horário de 137,68 W/m², um resultado desfavorável dessa configuração que, com uma única semente, não permite identificar isoladamente a causa do erro.',
    432: 'Nas tarefas mensais, o Informer com 128 níveis apresentou os menores macro-MAEs, de 12,73 W/m² em um passo e 13,67 W/m² em seis passos. A mudança de liderança mostra que o desempenho horário não se transfere diretamente às tarefas mensais. As métricas complementares da Tabela 6 e a análise local a seguir ajudam a qualificar essa comparação.',
    439: 'Nos dois pontos de Detroit, GM Factory Zero e Ford Rouge EV Center, a LSTM apresentou o menor MAE nas duas tarefas mensais. Portanto, a configuração com melhor resultado agregado pode não ser a melhor para cada localidade. Os dados permitem descrever essa heterogeneidade, mas não atribuí-la a uma causa climática específica.',
    533: 'Fonte: elaboração própria a partir dos dados e contratos auditados do projeto. Todos os MAEs em W/m². Δ = 100 × (MAE escolha / MAE controle − 1). A condição é selecionada na validação; a última coluna descreve seu desempenho posterior no teste.',
    535: 'A condição de entrada selecionada na validação reduziu o MAE de teste em cinco das 12 combinações de modelo e tarefa, elevou-o em quatro e manteve o controle contínuo em três. A LSTM horária com 64 níveis apresentou redução de 1,0548% em relação ao seu controle. No Informer com 128 níveis, as reduções foram de 0,9461% na tarefa mensal de um passo e 1,5305% na de seis passos. Já o Transformer diário com 256 níveis apresentou aumento de 0,0141%. Assim, uma condição favorável na validação pode perder sua vantagem no teste.',
    536: 'A condição selecionada deve ser mantida mesmo quando outro nível apresenta menor erro posterior no teste. A LSTM horária selecionou 64 níveis, embora 256 níveis tenham obtido menor MAE de teste. No Informer mensal de um passo, selecionaram-se 128 níveis, com MAE de 12,7266 W/m², enquanto 256 níveis alcançaram 12,3181 W/m². Esses resultados adicionais descrevem a sensibilidade aos níveis; utilizá-los para refazer a seleção comprometeria a função do teste. As diferenças pequenas permanecem descritivas, sem demonstração de significância estatística.',
    541: 'A Figura 11 mostra como o erro cumulativo evolui com o horizonte, mantendo a condição selecionada na validação. No Transformer horário, o MAE passou de 51,2911 para 52,8295 e 53,2061 W/m² em 24, 48 e 72 horas. Na LSTM com 64 níveis, os valores foram 51,8429, 52,8804 e 53,5241 W/m². O crescimento foi limitado nesses recortes, e a pequena vantagem agregada do Transformer permaneceu nos três horizontes.',
    548: 'A comparação histórica utiliza validação de abril de 2018 a março de 2019 e teste de abril de 2019 a dezembro de 2022, comuns aos históricos longo e curto pareado. A auditoria confirmou a identidade dos alvos e das datas avaliadas. São 1.368 origens horárias válidas por localidade em ambos os regimes, conforme a exclusão de cobertura descrita na metodologia. Esse teste permite comparar a duração do histórico sem introduzir a mudança de período presente na avaliação de 2024.',
    549: 'A Figura 12 e a Tabela 8 mostram que o histórico longo apresentou menor MAE nos controles contínuos de 11 das 12 combinações de modelo e tarefa. No Informer horário, o erro passou de 136,2112 para 60,8980 W/m², redução de 55,2915%. A exceção foi a LSTM horária, cujo MAE aumentou de 53,7187 para 61,6058 W/m², ou 14,6823%. Portanto, incorporar anos anteriores foi favorável na maioria das configurações, mas não garantiu melhora. Quando se comparam condições selecionadas separadamente em cada histórico, a análise também pode incluir mudanças de nível, além da duração do ajuste.',
    550: 'No histórico longo diário, a LSTM selecionada apresentou MAE de 43,1961 W/m², próximo dos 43,2117 W/m² do Informer. O RMSE, porém, favoreceu o Informer: 54,8033 contra 55,2189 W/m². A escolha da métrica altera a ordenação porque o RMSE atribui maior influência a erros grandes. Esse exemplo reforça a utilidade de examinar medidas complementares, mantendo o MAE como critério principal definido no protocolo.',
    621: 'APÊNDICE D PERFIS DO ESTUDO DE REFERÊNCIA',
    622: 'A Figura 13 apresenta perfis horários de TimesNet e DilatedRNN arquivados no estudo de referência [14]. Eles ilustram diferenças entre trajetórias que o erro médio não revela, mas pertencem a outro protocolo e não integram a comparação de quantização de Transformer, Informer e LSTM.',
    623: 'Figura 13 — Perfis de GHI e previsões do estudo de referência',
    626: 'Nas semanas exibidas, a TimesNet apresentou menor MAE em GM e Hyundai, e a DilatedRNN, no Texas. As curvas mostram subestimação de picos e excesso de previsão em alguns períodos de GHI baixa. Esses casos não substituem a avaliação anual nem identificam causas meteorológicas.',
    628: 'A ordenação dos modelos variou entre as tarefas avaliadas, que diferem em resolução temporal, janela de entrada, horizonte e condições de treinamento. O desempenho mensal favorável do Informer não se estendeu à tarefa horária. Já as pequenas diferenças agregadas entre Transformer e LSTM, junto às mudanças de liderança local e por horizonte, não sustentam uma preferência geral por uma arquitetura. A comparação mantém dados e regras de avaliação, mas não equaliza quantidade de parâmetros, capacidade ou custo computacional.',
    629: 'A quantização não apresentou benefício uniforme, e a condição selecionada na validação nem sempre preservou sua vantagem sobre o controle no teste. A análise de todos os níveis permite examinar essa sensibilidade sem refazer a seleção retrospectivamente. Uma possível regularização por redução de precisão permanece como hipótese: o desenho não identifica esse mecanismo e combina arredondamento com clipping. O controle com apenas clipping é, portanto, uma extensão necessária para separar os dois efeitos.',
    630: 'Na comparação histórica pareada, ampliar o conjunto de dados esteve associado a menor erro na maioria das configurações. Essa ampliação altera simultaneamente a quantidade de janelas, a composição dos anos e os extremos usados na normalização. A exceção da LSTM horária mostra que a inclusão de anos anteriores não assegura melhora e que o resultado não deve ser interpretado como efeito isolado do número de observações.',
    631: 'As tarefas mensais têm poucas origens de teste, sobretudo a de seis passos. A sobreposição de alvos gera dependência temporal, e pode haver correlação espacial entre localidades. As médias macro não quantificam essas dependências e podem ocultar perdas locais, como evidencia a mudança de liderança entre os pontos avaliados. Novos anos de teste e análises por estação ajudariam a avaliar a estabilidade dessas diferenças.',
    632: 'A referência avaliada é um produto modelado da NSRDB, em localidades selecionadas intencionalmente. Além disso, o período de teste de 2024 já havia sido examinado em etapas anteriores do projeto; esta avaliação é retrospectiva. O protocolo de seleção descrito preserva a separação temporal das execuções aqui comparadas, mas essa exposição prévia limita a independência do teste no contexto do projeto. O estudo não reproduz a aquisição de dados em tempo real nem avalia geração fotovoltaica operacional.',
    633: 'A tarefa horária utiliza uma única semente, de modo que sua ordenação pode depender da execução específica de treinamento. Nas demais tarefas, a média de cinco sementes reduz a dependência de uma única inicialização, mas não fornece intervalo de confiança nem previsão probabilística calibrada. As conclusões são descritivas, sem alegação de significância estatística. A reprodutibilidade desta consolidação decorre dos artefatos congelados e auditados; sementes fixas, por si só, não garantem repetição bit a bit de novos treinamentos em GPU.',
    634: 'A comparação estabelece diferenças entre as três implementações, mas não quantifica seu ganho frente a persistência, climatologia ou referências sazonais sob o mesmo protocolo, aspecto relevante à verificação de previsões solares [9]. Também não avalia eficiência computacional: os valores discretizados continuam representados em float32, e os pesos não são quantizados. Conclusões sobre memória ou velocidade exigiriam implementar uma representação compacta ou aritmética inteira e medir custo e erro sob hardware definido.',
    636: 'O TCC avaliou a previsão de GHI com LSTM, Transformer e Informer sob quatro condições de entrada, quatro tarefas e três regimes temporais. O protocolo utilizou janelas causais, escalas ajustadas com dados admissíveis e seleção de épocas e da condição de entrada na validação. Os resultados permitiram descrever a sensibilidade às condições de entrada, o comportamento por horizonte e a comparação histórica pareada.',
    639: 'No teste histórico pareado, o histórico longo reduziu o MAE do controle contínuo em onze das doze combinações. A exceção da LSTM horária mostra que incluir anos anteriores não garante melhora. Esse resultado descreve os períodos avaliados, nos quais a ampliação modifica simultaneamente a quantidade de janelas, a composição dos anos e os extremos utilizados na normalização.',
    641: 'A contribuição do TCC é uma avaliação rastreável da precisão preditiva sob discretização das entradas, com clipping nas variantes quantizadas. A análise conjunta das tarefas, localidades e durações do histórico mostrou que a resposta a essa transformação depende da configuração avaliada. O trabalho documenta reduções e aumentos de erro em relação ao controle contínuo, estabelecendo uma base experimental para investigar a estabilidade desses resultados.',
    644: '[2] NATIONAL LABORATORY OF THE ROCKIES. GOES Aggregated: PSM v4 Download API. Documentação técnica. Disponível em: https://developer.nlr.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/. Acesso em: 30 out. 2026.',
    1253: 'A consolidação verifica a integridade dos arquivos e o pareamento histórico antes de comparar os resultados. Em cada combinação de regime, tarefa e modelo, recupera as quatro condições, confere a escolha pelo macro-MAE da validação e mantém essa escolha fixa nos demais horizontes. As métricas de teste são apenas então organizadas em figuras e tabelas. O arredondamento em casas decimais é aplicado somente na apresentação.',
})

changes = []
def text(p):
    return ''.join(p.xpath('.//w:t/text()', namespaces=NS))

def set_text(p, new):
    assert not p.findall('.//m:oMath', NS), 'Do not overwrite a native equation.'
    assert not p.findall('.//w:fldChar', NS), 'Do not overwrite a live Word field.'
    ts = p.findall('.//w:t', NS)
    assert ts
    ts[0].text = new
    ts[0].set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    for t in ts[1:]:
        t.text = ''

for index, new in sorted(edits.items()):
    p = paragraphs[index]
    assert p.getparent() is body, f'Editorial change unexpectedly targets a table: {index}'
    old = text(p)
    if old != new:
        set_text(p, new)
        changes.append({'paragraph': index, 'before': old, 'after': new})

# Consolidate the related-work discussion rather than strand its last paragraph
# on a nearly empty page. Its content and reference [12] are retained in p328.
assert not paragraphs[329].findall('.//w:bookmarkStart', NS)
body.remove(paragraphs[329])

# Ragged-right alignment makes long literal data paths legible without stretching
# the spaces between them. The literal paths and hashes remain unchanged.
for index in (1237, 1254):
    ppr = paragraphs[index].find('w:pPr', NS)
    if ppr is None:
        ppr = ET.Element('{' + W + '}pPr')
        paragraphs[index].insert(0, ppr)
    alignment = ppr.find('w:jc', NS)
    if alignment is None:
        alignment = ET.SubElement(ppr, '{' + W + '}jc')
    alignment.set('{' + W + '}val', 'left')

# Move the existing reference-study figure and narrative as a complete unit.
# No image, source note, or quantitative result is dropped.
moved = [paragraphs[i] for i in range(621, 627)]
assert all(e.getparent() is body for e in moved)
heading_properties = deepcopy(paragraphs[1235].find('w:pPr', NS))
old_properties = moved[0].find('w:pPr', NS)
moved[0].remove(old_properties)
moved[0].insert(0, heading_properties)
for element in moved:
    body.remove(element)
    body.insert(body.index(body.find('w:sectPr', NS)), element)

# A modest proportional reduction accommodates the appendix heading and source.
# Both extents are updated, preserving the original image and aspect ratio.
picture = paragraphs[624]
for tag in ('wp:extent', 'a:xfrm/a:ext'):
    for extent in picture.findall('.//' + tag, NS):
        for dimension in ('cx', 'cy'):
            extent.set(dimension, str(round(int(extent.get(dimension)) * 0.94)))

assert before_tables == [ET.tostring(e, method='c14n') for e in root.findall('.//w:tbl', NS)]
assert before_math == [ET.tostring(e, method='c14n') for e in root.findall('.//m:oMath', NS)]
assert len(root.findall('.//w:drawing', NS)) == 13

updated = dict(original)
updated['word/document.xml'] = ET.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)
core = ET.fromstring(original['docProps/core.xml'])
cp = 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties'
dc = 'http://purl.org/dc/elements/1.1/'
dct = 'http://purl.org/dc/terms/'
for tag, value in (
    ('{' + dc + '}subject', 'Trabalho de conclusão de curso de Engenharia Elétrica sobre previsão multirresolução de GHI e quantização das entradas'),
    ('{' + cp + '}lastModifiedBy', 'Gustavo de Melo Nascimento'),
):
    element = core.find(tag)
    if element is None:
        element = ET.SubElement(core, tag)
    element.text = value
modified = core.find('{' + dct + '}modified')
modified.text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
updated['docProps/core.xml'] = ET.tostring(core, encoding='UTF-8', xml_declaration=True, standalone=True)

with ZipFile(OUTPUT, 'w') as z:
    for info in infos:
        z.writestr(info, updated[info.filename])

audit = {
    'source': str(SOURCE), 'output': str(OUTPUT),
    'source_sha256': digest(SOURCE.read_bytes()), 'output_sha256': digest(OUTPUT.read_bytes()),
    'edited_paragraphs': len(changes), 'changes': changes,
    'changed_parts': [k for k in original if original[k] != updated[k]],
    'preserved_tables': len(before_tables), 'preserved_native_equations': len(before_math),
    'preserved_images': [k for k in original if k.startswith('word/media/')],
    'appendix_d': 'Former main-results Figure 13 and five related paragraphs moved to the end.',
    'reference_figure_scale': 0.94,
    'related_work_consolidated': 'Original paragraphs 328 and 329 consolidated into 328, retaining reference [12].',
    'path_paragraphs_left_aligned': [1237, 1254],
    'video': 'Author will supply the link after finishing the report; retained the existing field.',
}
(HERE / 'auditoria_edicao.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({k: audit[k] for k in ('output', 'edited_paragraphs', 'preserved_tables', 'preserved_native_equations')}, ensure_ascii=False))
