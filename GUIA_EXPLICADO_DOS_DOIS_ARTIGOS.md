# Guia explicado dos dois artigos

## Como usar este material

Este guia acompanha os dois textos do projeto:

1. o artigo completo no formato IEEE;
2. o artigo resumido no formato do III MCSM.

Os dois artigos apresentam o mesmo experimento. O artigo IEEE contém mais detalhes técnicos; o artigo MCSM é uma versão mais curta. Por isso, a explicação principal segue o artigo IEEE e, no final, mostra o que muda no MCSM.

Em cada parte aparecem:

- **O trecho quer dizer:** tradução para uma linguagem simples;
- **Por que isso importa:** função daquela informação no trabalho;
- **Como explicar falando:** sugestão de fala para uma apresentação.

---

# ARTIGO 1 — VERSÃO IEEE

## 1. Título

### Trecho identificado

“Avaliação do DeepNPTS e de Modelos de Referência para Previsão Mensal de Irradiância Global Horizontal em Localidades de Fábricas de Veículos Elétricos.”

### O trecho quer dizer

O trabalho testa um modelo chamado **DeepNPTS** para prever a quantidade média de radiação solar do próximo mês. O teste é feito em dez pontos geográficos onde existem fábricas de veículos elétricos. O DeepNPTS não é avaliado sozinho: seu resultado é comparado ao de outros métodos, desde regras simples até redes neurais.

As fábricas apenas determinam as coordenadas geográficas. O artigo não usa produção de veículos, consumo elétrico, painéis solares ou dados internos das empresas.

### Como explicar falando

“Nosso trabalho verifica se o DeepNPTS consegue prever a irradiância solar média do mês seguinte. Usamos dez localidades de fábricas de veículos elétricos como pontos geográficos e comparamos o modelo com nove alternativas.”

---

## 2. Resumo

### “Este artigo avalia o DeepNPTS na previsão mensal de GHI”

**O trecho quer dizer:** o objeto principal do estudo é o DeepNPTS. A variável prevista é a GHI média mensal.

**GHI** é a irradiância total que chega a uma superfície horizontal. Ela informa a potência solar disponível por unidade de área e é expressa em W/m².

**Como explicar falando:** “A GHI mostra quanta potência solar chega a uma superfície horizontal. O modelo tenta prever a média dessa grandeza no mês seguinte.”

### “Com horizonte de um mês”

**O trecho quer dizer:** cada previsão tenta acertar apenas o próximo mês. O sistema não tenta prever um ano inteiro de uma só vez.

Exemplo: com os dados disponíveis até janeiro, prevê fevereiro; depois que o valor real de fevereiro fica disponível, ele entra no histórico usado para prever março.

**Como explicar falando:** “O horizonte é de um passo mensal: em cada momento, prevemos somente o mês imediatamente seguinte.”

### “Em dez localidades”

**O trecho quer dizer:** existem dez séries temporais, uma para cada ponto geográfico. Isso permite observar se o modelo funciona de maneira parecida em locais com climas diferentes.

### “Dados da NSRDB de 2019–2024 são agregados por mês”

**O trecho quer dizer:** a fonte original é a National Solar Radiation Database. O projeto preservou médias diárias derivadas de consultas com intervalo de 60 minutos. Depois, essas médias diárias foram reunidas para calcular uma média de cada mês civil.

Os 72 meses são divididos assim:

- 2019: contexto inicial;
- 2020–2023: 48 meses usados como alvos de treinamento;
- 2024: 12 meses usados no teste.

**Como explicar falando:** “Temos seis anos de dados. O primeiro ano fornece o histórico inicial, os quatro seguintes formam o treinamento e 2024 é usado para testar as previsões.”

### “Normalizados e quantizados com parâmetros pré-teste”

**O trecho quer dizer:** antes de treinar os modelos, os valores são colocados em uma escala de 0 a 1 e divididos em 128 níveis. Os limites usados nessa transformação são calculados apenas com dados anteriores ao teste.

Normalizar ajuda os modelos a trabalhar com escalas comparáveis. Quantizar significa trocar valores contínuos por níveis discretos. Por exemplo, números próximos podem ser representados pelo mesmo nível.

**Por que importa:** usar apenas o período pré-teste evita que informações de 2024 sejam usadas para preparar o modelo. Isso reduz vazamento de dados.

**Como explicar falando:** “Os dados foram colocados numa escala comum e divididos em 128 níveis. Essa preparação foi definida sem olhar os alvos do teste.”

### “Comparado a três referências simples e seis modelos aprendidos”

**O trecho quer dizer:** além do DeepNPTS, há nove concorrentes.

As três referências simples são:

- **persistência:** repete o valor do mês anterior;
- **sazonal ingênuo:** usa o valor do mesmo mês do ano anterior;
- **climatologia mensal:** usa o comportamento médio histórico daquele mês.

Os seis modelos aprendidos são XGBoost, MLP, RNN, LSTM, DilatedRNN e DeepAR.

Somando o DeepNPTS, são dez métodos no ranking.

### “48 alvos de treinamento”

**O trecho quer dizer:** o modelo aprende com as previsões correspondentes aos 48 meses entre 2020 e 2023. Para cada alvo, meses anteriores formam a entrada.

Não significa que existam apenas 48 números no projeto. Existem dez localidades e cada exemplo usa uma sequência de meses anteriores. “48 alvos” descreve as 48 posições mensais possíveis em cada série no período de treinamento.

### “12 origens walk-forward por localidade”

**O trecho quer dizer:** o teste simula o avanço real do tempo durante os 12 meses de 2024. Cada origem é o instante em que uma previsão é feita.

1. usa o histórico até dezembro de 2023 e prevê janeiro de 2024;
2. incorpora janeiro real e prevê fevereiro;
3. continua assim até prever dezembro.

Os parâmetros do modelo não são treinados novamente durante esse processo.

### “Cinco sementes”

**O trecho quer dizer:** os modelos aprendidos são executados cinco vezes com inicializações aleatórias diferentes. Isso mede o quanto o resultado depende da sorte da inicialização e do treinamento.

As sementes usadas são 11, 23, 42, 67 e 89.

### “Parâmetros fixos durante o teste”

**O trecho quer dizer:** depois de começar a avaliação de 2024, pesos, hiperparâmetros e configurações não são alterados. Só o histórico observado cresce.

**Por que importa:** se os autores ajustassem o modelo depois de ver os erros do teste, o resultado ficaria artificialmente favorável.

### Resultado principal do resumo

A climatologia obteve MAE de 12,07 W/m² e foi a melhor. O DeepNPTS obteve 17,70 W/m², ficou em nono entre dez métodos e venceu somente a persistência.

**Como explicar falando:** “O resultado principal foi que uma referência simples, a climatologia, apresentou o menor erro. O DeepNPTS ficou em penúltimo, mostrando que maior complexidade não garantiu melhor desempenho nessa janela.”

### Comparação probabilística com o DeepAR

O DeepNPTS teve CRPS maior, portanto sua distribuição probabilística foi pior pela métrica principal. Seus intervalos foram 4,10 vezes mais largos. Apesar disso, sua cobertura ficou próxima dos 90% desejados.

Isso não significa automaticamente que seu intervalo foi melhor. Um intervalo muito largo consegue incluir muitos valores reais, mas oferece pouca precisão.

---

## 3. Introdução

### Primeiro parágrafo: importância do recurso solar

**O trecho quer dizer:** a energia produzida por sistemas fotovoltaicos depende da radiação solar disponível. Prever essa disponibilidade pode ajudar no planejamento e na operação. A utilidade da previsão depende de três escolhas: quanto tempo à frente será previsto, qual será a frequência dos dados e quais informações meteorológicas existem.

**Como explicar falando:** “A motivação é reduzir a incerteza sobre o recurso solar. Mas a previsão muda conforme o horizonte e a resolução; prever o próximo mês é diferente de prever a próxima hora.”

### Segundo parágrafo e fórmula da GHI

A fórmula é:

GHI = DHI + DNI × cos(ângulo zenital)

**O trecho quer dizer:** a radiação em uma superfície horizontal tem duas partes:

- DHI: luz solar espalhada pela atmosfera, que chega de várias direções;
- DNI: luz que vem diretamente do Sol;
- cosseno do ângulo zenital: corrige a parte direta porque a superfície está na horizontal e os raios solares chegam inclinados.

Quando o Sol está alto, a componente direta projetada na horizontal é maior. Quando está perto do horizonte, é menor.

**Atenção:** o artigo prevê irradiância média em W/m², e não energia em kWh nem produção fotovoltaica.

### Terceiro parágrafo: previsão mensal

**O trecho quer dizer:** usar médias mensais reduz variações rápidas, como nuvens passageiras e diferenças entre manhã e tarde. Isso deixa o padrão das estações mais visível. A desvantagem é ter poucos exemplos: somente 12 valores por ano.

**Por que importa:** redes neurais geralmente se beneficiam de muitos exemplos. Com apenas quatro ciclos anuais de alvos de treinamento, métodos simples podem ser mais competitivos.

### Quarto parágrafo: famílias de modelos

**O trecho quer dizer:** o estudo inclui métodos de diferentes níveis de complexidade.

- XGBoost: conjunto de árvores de decisão;
- MLP: rede neural comum, sem memória temporal própria;
- RNN: rede que mantém um estado do passado;
- LSTM: RNN com mecanismos para guardar ou esquecer informações;
- DilatedRNN: RNN que faz conexões com diferentes distâncias no passado;
- referências simples: regras que não precisam de treinamento neural.

### Quinto parágrafo: modelos globais, DeepAR e DeepNPTS

**Modelo global** significa que um único modelo aprende com as dez localidades. Ele não treina uma rede separada para cada fábrica.

O **DeepAR** escolhe uma família matemática contínua para representar a distribuição futura. Neste trabalho, usa uma distribuição Student-t.

O **DeepNPTS** é não paramétrico: em vez de impor uma forma matemática fixa, aprende probabilidades sobre valores presentes em seu contexto histórico.

**Importante:** ser não paramétrico não garante ser melhor. É apenas uma maneira diferente de construir a previsão probabilística.

### Sexto parágrafo: objetivo exato

**O trecho quer dizer:** a pergunta experimental é se o DeepNPTS discreto do GluonTS supera referências sazonais e modelos treinados ao prever o próximo mês.

Todos usam os mesmos meses-alvo e as mesmas datas de previsão, mas recebem entradas compatíveis com suas arquiteturas. Isso é mais justo do que obrigar modelos diferentes a usar exatamente a mesma representação.

### Principais contribuições

1. testar o DeepNPTS globalmente nas dez séries;
2. compará-lo com nove alternativas;
3. aplicar um protocolo que pode ser auditado;
4. reconhecer as limitações e não afirmar superioridade universal.

**Como explicar falando:** “A contribuição não é propor um modelo novo, mas realizar uma comparação controlada e documentada do DeepNPTS nesse problema específico.”

---

## 4. Figura do fluxo do sistema

### Estágio A — séries relacionadas

São as dez séries diárias de GHI. Elas medem a mesma variável, mas cada local tem nível e sazonalidade próprios.

### Estágio B — auditoria e agregação

O código procura:

- datas ausentes;
- registros duplicados;
- valores infinitos ou inválidos;
- GHI negativa;
- inconsistências de cobertura.

Depois calcula uma média para cada mês civil.

### Estágio C — transformação e entradas

Os valores são normalizados e quantizados. Depois cada tipo de modelo recebe a entrada apropriada.

- modelos tabulares recebem 12 defasagens, médias móveis, calendário e localidade;
- redes recorrentes recebem sequências em ordem temporal e covariáveis;
- DeepAR e DeepNPTS recebem séries transformadas e uma categoria que identifica a localidade.

### Estágio D — ajuste

Cada modelo aprendido é global. Para cada semente, é treinado um único modelo usando dados das dez localidades. As referências simples não passam por treinamento conjunto.

### Estágio E — teste retrospectivo

O histórico avança mês a mês, mas o modelo não é reajustado. O valor real de um mês entra no contexto do mês seguinte.

### Estágio F — avaliação

As previsões normalizadas voltam para W/m². Valores negativos são corrigidos para zero por ser um limite físico. Não se aplica um teto superior, de modo que erros altos continuam visíveis.

---

## 5. DeepNPTS e sua fórmula

### Ideia principal

O DeepNPTS observa os últimos C valores da localidade. Neste estudo, C é 12 meses. A rede atribui uma probabilidade a cada posição desse contexto.

Exemplo simplificado:

| Mês do contexto | Valor | Probabilidade de ser escolhido |
|---|---:|---:|
| janeiro anterior | 180 | 10% |
| fevereiro anterior | 190 | 20% |
| ... | ... | ... |
| dezembro anterior | 210 | 30% |

O modelo sorteia posições seguindo essas probabilidades. Repetir o sorteio muitas vezes cria uma distribuição de previsões.

### Explicação da fórmula

- F com chapéu: distribuição prevista;
- l: localidade;
- t: último mês observado;
- C: tamanho do contexto;
- p: probabilidade atribuída a uma posição;
- I: função indicadora, que vale 1 se a condição for verdadeira e 0 caso contrário;
- x: valor usado para consultar a distribuição.

A soma calcula quanta probabilidade foi atribuída a valores menores ou iguais a x. Isso forma a função de distribuição acumulada.

### Limitação estrutural importante

A versão discreta amostra apenas valores existentes em seu contexto. Portanto, ela não cria livremente qualquer novo valor contínuo. Isso pode ser útil para preservar padrões observados, mas pode limitar extrapolações.

### Correção local no GluonTS

O artigo informa que houve uma correção apenas no registro dos embeddings categóricos no PyTorch. Isso significa que foi corrigida a forma como os parâmetros ligados à identificação das localidades eram registrados. A arquitetura e a distribuição oficial do DeepNPTS não foram substituídas.

### Consolidação das sementes

Modelos pontuais: tira-se a média das previsões das cinco execuções.

DeepNPTS e DeepAR: cada semente produz 500 amostras. As cinco sementes são reunidas, resultando em 2.500 amostras por origem. A mediana é usada como previsão pontual; os percentis de 5% e 95% formam o intervalo de 90%.

---

## 6. Algoritmo compacto

### Entrada

O algoritmo recebe as séries, os modelos, as sementes, o contexto, o horizonte, o ponto de corte, os níveis de quantização e as origens de previsão.

### Passo 1

Auditar os dados e calcular a média mensal.

### Passo 2

Ajustar a transformação usando somente o passado e construir entradas que não usem informações futuras.

### Passo 3

Selecionar configurações sem usar o teste e treinar um modelo global para cada combinação de modelo e semente.

### Passo 4

Em cada mês de teste, cortar o histórico na data correta, prever o próximo mês e voltar à escala física.

### Passo 5

Combinar as sementes, calcular as métricas por localidade, tirar médias entre localidades e construir o ranking pelo MAE.

### Como explicar falando

“O algoritmo descreve uma cadeia simples: validar, transformar sem vazamento, treinar globalmente, simular as previsões de 2024 e comparar os erros.”

---

## 7. Configuração experimental

### Fonte e natureza dos dados

O produto usado é o GOES Aggregated PSM v4 da NSRDB. Ele combina informações de satélite e modelos físicos. Portanto, é uma **referência modelada**, não uma medição feita por um sensor instalado em cada fábrica.

### Localidades

As localidades são BYD Camaçari, BMW San Luis Potosí, Ford Rouge, GM Factory Zero, Hyundai Georgia, Lucid Casa Grande, Rivian Normal, Tesla Fremont, Tesla Nevada e Tesla Texas.

### Divisão cronológica

Não se embaralha passado e futuro. O teste sempre vem depois do treinamento:

- contexto inicial: 2019;
- treinamento: 2020–2023;
- teste: 2024.

### Avaliação retrospectiva e exploratória

O texto reconhece que 2024 já foi observado durante o desenvolvimento. Por isso, o teste não deve ser apresentado como uma validação prospectiva totalmente intocada.

**Como explicar falando:** “A avaliação reproduz previsões históricas, mas não é um teste futuro cego, porque a janela de 2024 já foi examinada durante o desenvolvimento.”

### Ambiente computacional

O artigo lista sistema operacional, processador, memória e versões das bibliotecas para permitir reprodução. Os experimentos foram feitos sem GPU, com 2 vCPUs e 7,76 GiB de RAM.

---

## 8. Modelos e hiperparâmetros

### O que são hiperparâmetros?

São configurações escolhidas antes ou durante a etapa de validação, como quantidade de camadas, unidades, taxa de aprendizagem e número máximo de épocas. Não são os pesos aprendidos automaticamente durante o treinamento.

### XGBoost

Constrói várias árvores de decisão em sequência. Cada nova árvore tenta corrigir erros das anteriores. Profundidade, taxa de aprendizagem, regularização e número de árvores controlam sua complexidade.

### MLP

É uma rede neural de camadas densas 64–32. Ela recebe atributos já organizados, como defasagens e calendário. Não possui memória recorrente própria.

### RNN

Processa os meses em sequência e carrega um estado interno. Isso permite usar informações anteriores na previsão.

### LSTM

É uma RNN com portas que controlam o que guardar e esquecer. Foi o melhor modelo aprendido no macro-MAE, embora tenha ficado ligeiramente atrás da climatologia.

### DilatedRNN

Usa saltos de 1, 2 e 4 passos, tentando conectar informações em diferentes distâncias temporais. O artigo deixa claro que é uma implementação customizada e não uma reprodução integral da arquitetura original.

### DeepNPTS

Usa contexto de 12 meses, duas camadas de tamanho 12, embedding de localidade com dimensão 5 e treinamento de 100 épocas. Produz 500 amostras por semente.

### DeepAR

Usa duas camadas de 40 unidades e uma distribuição Student-t. Embora o contexto declarado seja 12, suas defasagens fazem o passado efetivo chegar a 23 meses. Essa diferença arquitetural foi mantida.

---

## 9. Métricas pontuais

### Erro

Erro é a diferença entre valor real e previsão:

erro = real − previsto.

Um erro positivo indica previsão abaixo do real; negativo indica previsão acima.

### MAE

Calcula a média dos valores absolutos dos erros. Não deixa erros positivos e negativos se cancelarem. É a métrica principal porque permanece em W/m² e tem interpretação direta.

### MSE

Eleva os erros ao quadrado antes da média. Erros grandes recebem peso muito maior. Sua unidade fica ao quadrado, W²/m⁴, o que dificulta a interpretação direta.

### RMSE

É a raiz do MSE. Também penaliza erros grandes, mas volta para W/m².

### R²

Mede quanto da variação dos valores o modelo acompanha em comparação com usar uma média. Valores próximos de 1 normalmente indicam bom acompanhamento. Ele não substitui MAE ou RMSE.

### nRMSE

Divide o RMSE pela GHI média da localidade e mostra o resultado em porcentagem. Isso facilita comparar localidades com escalas diferentes.

### Macro-MAE

Primeiro calcula o MAE em cada localidade e depois tira uma média simples dos dez resultados. Cada localidade recebe o mesmo peso.

### DP entre sementes

Mostra o quanto o macro-MAE mudou entre as cinco execuções aleatórias. Não mede diferença entre localidades.

---

## 10. Métricas probabilísticas

### CRPS

Avalia a distribuição completa prevista e o valor realmente observado. Recompensa distribuições concentradas perto do real e penaliza distribuições mal posicionadas ou espalhadas demais. Menor é melhor.

### PICP de 90%

É a porcentagem de valores reais que ficou dentro dos intervalos previstos de 90%. O valor desejado é próximo de 90%.

### MPIW de 90%

É a largura média dos intervalos. Menor é melhor, desde que a cobertura continue adequada.

### Por que analisar PICP e MPIW juntos?

Um intervalo extremamente largo consegue cobrir quase todos os valores, mas não ajuda muito na tomada de decisão. O ideal é obter cobertura próxima de 90% com intervalos tão estreitos quanto possível.

---

## 11. Tabela de comparação média

### Como ler a tabela

Os métodos estão ordenados pelo MAE, do menor erro para o maior.

1. Climatologia: 12,07 W/m²;
2. LSTM: 12,22;
3. RNN: 12,55;
4. DilatedRNN: 13,42;
5. DeepAR: 14,18;
6. XGBoost: 14,57;
7. MLP: 16,06;
8. Sazonal ingênuo: 16,94;
9. DeepNPTS: 17,70;
10. Persistência: 35,09.

### Interpretação principal

A climatologia venceu por uma diferença pequena em relação à LSTM: 0,15 W/m². O DeepNPTS teve erro 5,63 W/m² maior que a climatologia e venceu apenas a persistência.

O DeepNPTS também apresentou DP de 9,22 W/m² entre sementes, muito maior que os outros modelos. Isso indica forte instabilidade em relação à inicialização aleatória.

### Teste estatístico no artigo IEEE

O intervalo de confiança pareado para a diferença DeepNPTS menos climatologia foi de 3,76 a 7,55 W/m². Como todo o intervalo está acima de zero, ele aponta erro maior do DeepNPTS nessa amostra. O teste de Wilcoxon, depois da correção de Holm, produziu p = 0,0176.

Isso fornece evidência de diferença dentro do protocolo estudado, mas não prova que a climatologia vencerá em qualquer base de dados.

---

## 12. DeepNPTS por localidade

### Melhor e pior caso

O menor MAE do DeepNPTS ocorreu em Lucid Casa Grande: 10,79 W/m².

O maior ocorreu em Rivian Normal: 25,61 W/m².

A diferença entre os dois foi 14,82 W/m². Isso mostra que o desempenho variou bastante conforme a localidade.

### Liderança local

- LSTM liderou quatro localidades;
- climatologia liderou três;
- RNN liderou uma;
- DeepAR liderou uma;
- sazonal ingênuo liderou uma;
- DeepNPTS não liderou nenhuma.

Essa contagem é apenas descritiva. O critério principal continua sendo o macro-MAE definido antes da análise.

---

## 13. Gráficos de Camaçari

### Gráfico de previsões pontuais

Compara a referência da NSRDB, a previsão do DeepNPTS e a climatologia durante os meses de 2024.

O DeepNPTS foi melhor em seis meses e a climatologia nos outros seis. Mesmo empatando na contagem de meses, a climatologia teve menor erro total, porque importa também o tamanho de cada erro.

MAE em Camaçari:

- climatologia: 13,14 W/m²;
- DeepNPTS: 15,74 W/m².

### Gráfico do intervalo

A linha central representa a mediana das amostras do DeepNPTS. A faixa mostra o intervalo central de 90%, entre os quantis de 5% e 95%.

Uma faixa larga significa que o modelo admite muitos valores possíveis e demonstra grande incerteza.

---

## 14. DeepNPTS contra DeepAR

### Valores encontrados

DeepNPTS:

- CRPS: 15,90 W/m²;
- cobertura: 90,83%;
- largura média: 145,56 W/m².

DeepAR:

- CRPS: 10,83 W/m²;
- cobertura: 61,67%;
- largura média: 35,50 W/m².

### Explicação fácil

O DeepNPTS alcançou uma cobertura muito próxima de 90%, mas fez isso com intervalos enormes. O DeepAR criou intervalos muito mais estreitos, porém cobriu poucos valores reais. O CRPS favoreceu o DeepAR, indicando melhor equilíbrio global da distribuição.

### Como explicar falando

“O DeepNPTS foi mais bem calibrado em cobertura, mas pouco preciso, porque seus intervalos foram 4,10 vezes mais largos. O DeepAR ficou abaixo da cobertura desejada, mas teve CRPS menor e intervalos muito mais informativos.”

---

## 15. Limitações

### Histórico curto

Embora existam seis anos de dados, apenas quatro ciclos anuais fornecem alvos de treinamento. Isso é pouco para modelos profundos.

### Uma única janela de teste

O estudo avalia apenas 2024. Um ano incomum pode alterar bastante o ranking.

### Janela já examinada

Como 2024 foi visto durante o desenvolvimento, o estudo é retrospectivo e exploratório, não uma avaliação futura totalmente cega.

### Cinco sementes

Cinco execuções ajudam a medir aleatoriedade, mas não capturam todas as variações possíveis.

### Seleção das localidades

Os pontos foram escolhidos por possuírem fábricas, e não por amostragem espacial aleatória. Portanto, não representam automaticamente todas as regiões.

### Tratamento desigual dos valores

Modelos aprendidos recebem dados normalizados e quantizados; as referências simples operam nos valores físicos exatos. A quantização pode causar perda de informação.

### Saturação

Entradas além dos limites do treinamento são cortadas para 0 ou 1 na escala normalizada. Isso pode apagar a magnitude de valores extremos.

### Natureza da NSRDB

Os valores são modelados usando satélite e modelos físicos, e não medidos diretamente no solo.

### Dados horários não preservados

O projeto guardou médias diárias, então não é possível reconstruir exatamente os registros horários originais.

### Sem dados industriais

Não se pode transformar diretamente os resultados em conclusões sobre geração fotovoltaica, consumo elétrico ou operação das fábricas.

---

## 16. Conclusão

### O que o artigo realmente conclui

Na configuração avaliada, a climatologia foi o método com menor macro-MAE. O DeepNPTS ficou em nono e superou somente a persistência. Em comparação ao DeepAR, teve erros pontual e probabilístico maiores e intervalos muito mais largos, apesar da cobertura próxima de 90%.

### O que o artigo não conclui

O artigo não afirma que:

- climatologia sempre vence redes neurais;
- DeepNPTS é um modelo ruim em qualquer problema;
- as fábricas possuem determinado potencial de geração;
- os resultados valem para outras regiões, frequências ou horizontes.

### Trabalhos futuros

As sugestões são usar um histórico maior, reservar um teste futuro realmente não observado, experimentar outros horizontes, incluir variáveis meteorológicas e estudar o efeito da normalização, saturação e quantização.

---

# ARTIGO 2 — VERSÃO III MCSM

## 1. Relação com o artigo IEEE

O artigo MCSM não descreve um segundo experimento. Ele apresenta o mesmo objetivo, dados, modelos, métricas e resultados em uma versão mais curta, adaptada ao formato do evento.

Assim, as explicações das seções anteriores também valem para ele.

## 2. Diferenças no resumo

O resumo do MCSM declara explicitamente a quantização em **128 níveis**. Também informa o resultado da climatologia e do DeepNPTS, mas não detalha ali a comparação completa dos intervalos como o resumo IEEE.

## 3. Diferenças na introdução

A versão MCSM explica de forma mais direta que a média de GHI é calculada sobre as 24 horas do dia e não representa energia gerada. Essa observação evita confundir W/m² com kWh ou produção fotovoltaica.

## 4. Diferenças no método

O método é condensado em cinco blocos:

1. GHI diária da NSRDB;
2. auditoria e agregação mensal;
3. normalização, quantização e entradas causais;
4. modelos globais e referências;
5. teste e métricas.

“Entradas causais” significa que uma previsão só recebe informações existentes antes do mês previsto.

## 5. Diferenças na descrição do DeepNPTS

A versão MCSM mantém a fórmula principal, mas reduz a explicação matemática. Ela ainda deixa claro que:

- o modelo usa um contexto de C valores;
- a rede atribui probabilidades às posições;
- a variante discreta sorteia valores do contexto;
- a correção do embedding não muda a arquitetura oficial;
- as cinco sementes formam uma mistura de 2.500 amostras.

## 6. Diferenças na configuração

A versão MCSM apresenta a divisão 80%/20% dos 60 alvos elegíveis:

- 48 alvos de 2020–2023, ou 80%;
- 12 alvos de 2024, ou 20%.

Essa porcentagem se refere aos alvos elegíveis depois de separar 2019 como contexto inicial, e não aos 72 meses brutos.

## 7. Diferenças nas tabelas

A tabela média do MCSM omite o MSE para economizar espaço, mas mantém MAE, desvio-padrão, RMSE, R² e nRMSE. A ordem e os valores principais permanecem os mesmos.

A tabela por localidade também apresenta os mesmos resultados essenciais do artigo IEEE.

## 8. Diferenças na discussão

A versão MCSM resume a comparação estatística. O artigo IEEE acrescenta o intervalo de confiança e o teste de Wilcoxon com correção de Holm. Por isso, se perguntarem sobre significância estatística, a resposta mais completa está na versão IEEE.

## 9. Diferenças nas limitações e conclusão

O MCSM reúne as limitações em um parágrafo mais curto, mas não muda a mensagem: o histórico é pequeno, o teste é retrospectivo, os dados são modelados, a quantização pode afetar os modelos e não se deve generalizar sem nova validação.

---

# ROTEIRO CURTO PARA EXPLICAR O TRABALHO

“O trabalho avalia se o DeepNPTS consegue prever a GHI média do próximo mês em dez localidades. A GHI representa a potência solar que chega a uma superfície horizontal, e não a energia produzida por painéis.”

“Foram usados dados da NSRDB entre 2019 e 2024. O ano de 2019 forneceu o contexto inicial, os 48 meses de 2020 a 2023 foram usados no treinamento e os 12 meses de 2024 no teste walk-forward.”

“O DeepNPTS foi comparado com três referências simples e seis modelos aprendidos. O principal critério foi o macro-MAE, que dá o mesmo peso às dez localidades.”

“A climatologia apresentou o menor erro, 12,07 W/m². O DeepNPTS obteve 17,70 W/m², ficou em nono entre dez métodos e venceu apenas a persistência.”

“Na previsão probabilística, o DeepNPTS chegou perto da cobertura nominal de 90%, mas criou intervalos 4,10 vezes mais largos que os do DeepAR. O DeepAR teve CRPS menor.”

“A conclusão vale somente para esse período e essa configuração. O histórico curto, a única janela de teste e a quantização impedem afirmar que um método sempre será melhor.”

---

# PERGUNTAS PROVÁVEIS E RESPOSTAS

## Por que a climatologia venceu um modelo profundo?

A GHI mensal possui forte padrão anual, e a climatologia usa diretamente esse padrão. Além disso, havia somente quatro ciclos anuais de alvos de treinamento, uma quantidade pequena para modelos profundos.

## Por que usar fábricas de veículos elétricos?

Elas definem pontos geográficos de interesse. O estudo não usa dados industriais das fábricas.

## Por que prever GHI e não geração fotovoltaica?

Porque a base fornece a disponibilidade do recurso solar. Para prever geração seriam necessários dados adicionais, como potência instalada, orientação dos painéis, eficiência, temperatura e perdas.

## O DeepNPTS foi inútil?

Não. O experimento mostrou seu comportamento e suas limitações nessa aplicação. Ele produziu cobertura probabilística próxima do nível desejado, mas com intervalos largos e desempenho pontual inferior. Um resultado negativo também é cientificamente informativo.

## O que significa global?

Um único modelo aprende com as dez localidades, compartilhando parâmetros. A identidade de cada localidade é informada por um embedding.

## O que é embedding?

É uma representação numérica aprendida para identificar cada localidade. Em vez de tratar o nome como texto, a rede aprende um pequeno vetor associado a cada local.

## Por que usar cinco sementes?

Para verificar se o resultado depende muito da inicialização aleatória. O grande desvio do DeepNPTS mostrou que ele foi instável nesse aspecto.

## Por que o teste é chamado retrospectivo?

Porque simula previsões que teriam sido feitas no passado usando dados históricos. Como 2024 já foi examinado durante o desenvolvimento, não é uma validação futura completamente cega.

## Cobertura maior significa intervalo melhor?

Não necessariamente. Um intervalo enorme cobre quase tudo. É preciso avaliar cobertura, largura e CRPS em conjunto.

## É correto dizer que o DeepNPTS é sempre pior?

Não. Só é correto afirmar que ele foi pior na janela, nas localidades, no horizonte e nas configurações deste experimento.
