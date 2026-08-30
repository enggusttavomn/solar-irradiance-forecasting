# Uso de Cabral et al. (2026) como referência estrutural

O artigo de Cabral, Fraidenraich e Capretz
([doi:10.1016/j.solener.2026.114964](https://doi.org/10.1016/j.solener.2026.114964))
é uma referência de organização, profundidade
da revisão, rastreabilidade metodológica e apresentação de resultados. Ele não
é fonte dos resultados de TimesNet ou DilatedRNN do novo estudo. Seu texto, suas
figuras e seus dados não devem ser copiados. Qualquer adaptação efetiva de um
elemento visual deve ser identificada e citada; a opção preferencial é produzir
diagramas e gráficos originais a partir do pipeline e dos artefatos deste
projeto.

## Mapeamento verificado

| Elemento em Cabral et al. (2026) | Conteúdo real | Aplicação no artigo unificado |
|---|---|---|
| Introdução e contribuições | Motivação, taxonomia de horizontes, pergunta de pesquisa, delimitação do escopo e contribuições explícitas | Apresentar a extensão dos dois trabalhos-base, definir resolução e horizonte conjuntamente e declarar contribuições verificáveis |
| Seção 2 | Revisão crítica e comparativa dos trabalhos relacionados | Construir uma revisão robusta, com fontes verificadas e uma síntese crítica própria |
| Tabelas 1--3 | Três partes de uma matriz da literatura: entradas, limpeza, transformação, engenharia de atributos, modelo, horizonte e avaliação de robustez | Criar uma matriz factual de estudos relacionados; não reutilizar os textos nem copiar classificações subjetivas como “fraco”, “alto” ou “superior” |
| Seção 3 | Fundamentação sobre clima e arquiteturas avaliadas no artigo de referência | Criar fundamentação específica para GHI, horizontes, TimesNet, DilatedRNN, modelos globais e variabilidade climática |
| Tabela 4 | Significado dos códigos da classificação climática de Köppen--Geiger | Explicar somente as classes presentes nas dez localidades, com uma fonte única e documentada |
| Tabela 5 | Lista de localidades com latitude, longitude e classe climática | Informar fábrica/localidade, cidade, país, latitude, longitude, célula NSRDB, fuso e classe climática quando verificados |
| Figura 1, página 6 | Pipeline dividido nos painéis (a) aquisição, (b) integridade e reamostragem e (c) preparação, modelo e previsão | Inspirar um diagrama original em blocos A, B e C, incluindo as ramificações horária, diária e mensal do novo estudo |
| Algoritmo 1, página 6 | Aquisição de GHI por localização | Inspirar o pseudocódigo de coleta, metadados e alinhamento temporal |
| Algoritmo 2, página 6 | Verificação de integridade e reamostragem | Inspirar o pseudocódigo de auditoria, tratamento e agregação, sem reproduzir decisões que não correspondam ao código deste projeto |
| Algoritmo 3, página 7 | Quantização e normalização | Documentar somente transformações realmente usadas, ajustadas exclusivamente em dados pré-teste |
| Algoritmo 4, página 7 | Treinamento e geração das previsões | Detalhar separadamente o fluxo de TimesNet, DilatedRNN, sementes, seleção, reajuste e inferência |
| Algoritmo 5, página 10 | Divisão cronológica de treino, validação e teste | Inspirar a descrição reprodutível das partições e origens, respeitando o protocolo específico de cada resolução |
| Figuras 3--4, página 9 | Mapa mundial e ampliações de regiões com pontos próximos | Produzir um mapa original das dez localidades, com ampliações somente onde melhorarem a legibilidade |
| Tabela 6 | Configurações e hiperparâmetros do experimento de longo prazo | Manter no corpo apenas parâmetros essenciais; colocar grades, épocas por semente e configurações secundárias no apêndice |
| Tabelas 7--8 | Resultados de um caso difícil, Recife, e de um caso favorável, Reno | Apresentar casos contrastantes sob uma regra transparente e não tendenciosa, além dos resultados completos |
| Tabela 9 | Desempenho médio nas 40 localidades do estudo de referência | Apresentar primeiro o desempenho agregado do novo estudo por resolução e horizonte |
| Tabelas 10--12 | Tempo de treinamento, tempo de teste e quantidade de parâmetros | Consolidar custo computacional, capacidade dos modelos, ambiente e tempo de inferência em uma tabela comparável |
| Figura 5, página 11 | Comparação visual das previsões no horizonte de cinco anos | Inspirar gráficos próprios com referência observada, modelos comparados e horizonte claramente identificado |
| Tabela 13 | Configuração do estudo denominado “daily prediction” | Não tratar esse protocolo como resolução diária; ver a ressalva abaixo |
| Tabela 14 e Figura 6 | Resultados e curvas do caso de Manaus em período chuvoso | Inspirar uma análise de período adverso apenas quando uma fonte meteorológica independente confirmar a condição |
| Conclusão e declarações finais | Síntese, limitações, conflito de interesses, agradecimentos e disponibilidade dos dados | Incluir conclusões sustentadas pelos testes completos e as declarações exigidas pela revista |

## Ressalva sobre o experimento denominado diário

Em Cabral et al. (2026), a Tabela 13 utiliza uma amostra por hora, 120 amostras
de entrada e 120 amostras de saída. Portanto, trata-se de uma previsão horária
de cinco dias à frente (`120 h -> 120 h`), e não de uma série com resolução
diária. No artigo unificado, devem ser distinguidos explicitamente:

1. previsão horária de vários dias à frente; e
2. previsão de séries efetivamente agregadas por dia.

Resultados, hiperparâmetros e conclusões do primeiro protocolo não podem ser
transferidos automaticamente para o segundo.

## Regras de integridade para a adaptação

- Usar o artigo somente como referência de estrutura e nível de detalhamento.
- Reescrever todo o conteúdo a partir dos dados, códigos e resultados deste
  projeto.
- Não reproduzir figuras, pseudocódigos, tabelas ou frases sem atribuição.
- Não importar valores do artigo de referência como resultados de TimesNet ou
  DilatedRNN.
- Não chamar a previsão mensal de um passo de previsão multimensal.
- Definir os casos favoráveis e desfavoráveis por regra declarada, apresentar
  também o resultado agregado e não omitir perdas do método analisado.
- Tratar zonas climáticas como contexto descritivo; dez localidades não
  sustentam, isoladamente, inferência causal sobre o efeito do clima.
- Rotular chuva ou nebulosidade somente com confirmação meteorológica
  independente, nunca apenas por baixa GHI.

## Estrutura proposta para o manuscrito unificado

1. Introduction
2. Related Work
3. Theoretical Background
4. Data and Preprocessing
5. Unified Methodology
6. Experimental Design
7. Evaluation Metrics
8. Results and Discussion
9. Threats to Validity and Limitations
10. Conclusion
11. Appendices and required declarations
