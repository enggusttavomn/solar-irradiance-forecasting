# Experimentos com redes avancadas

Rodada executada em 2026-06-29 para comparar modelos experimentais com o
pipeline oficial, sem alterar os resultados oficiais ja existentes.

Modelos avaliados:

- `DilatedRNN`: rede recorrente multiescala com subamostragens dilatadas.
- `DeepAR_exp`: aproximacao experimental do DeepAR com LSTM probabilistica.
- `DeepNPTS_aprox`: baseline nao parametrico inspirado em NPTS.

Arquivos principais:

- `metricas_experimentos_todas.csv`: metricas dos 3 modelos experimentais em
  frequencia diaria e mensal.
- `status_execucao.csv`: status de cada treino.
- `diaria/comparacao_com_modelos_oficiais.csv`: modelos oficiais e
  experimentais na frequencia diaria.
- `mensal/comparacao_com_modelos_oficiais.csv`: modelos oficiais e
  experimentais na frequencia mensal.

## Status da execucao

| Frequencia | Treinos ok | Erros |
| --- | ---: | ---: |
| diaria | 30 | 0 |
| mensal | 30 | 0 |

## Media dos modelos experimentais

| Frequencia | Modelo | MAE W/m2 | RMSE W/m2 | R2 | nRMSE (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| diaria | DilatedRNN | 37.70 | 49.71 | 0.657 | 26.86 |
| diaria | DeepNPTS_aprox | 39.32 | 51.65 | 0.629 | 27.86 |
| diaria | DeepAR_exp | 41.44 | 54.40 | 0.586 | 29.33 |
| mensal | DeepNPTS_aprox | 12.96 | 16.39 | 0.916 | 8.10 |
| mensal | DilatedRNN | 15.25 | 18.73 | 0.878 | 9.29 |
| mensal | DeepAR_exp | 61.02 | 68.57 | 0.010 | 34.21 |

## Melhor modelo geral por localidade

Na frequencia diaria, os modelos experimentais foram melhores em 5 das 10
localidades, sempre com `DilatedRNN`. Os outros 5 melhores resultados
continuaram nos modelos oficiais.

Na frequencia mensal, os modelos experimentais foram melhores em 6 das 10
localidades: `DeepNPTS_aprox` venceu em 5 e `DilatedRNN` venceu em 1. Os
modelos oficiais continuaram melhores nas outras 4 localidades.

## Leitura tecnica

Os resultados indicam que `DilatedRNN` e `DeepNPTS_aprox` merecem ser mantidos
como candidatos experimentais para discussao. A `DilatedRNN` e competitiva na
escala diaria, enquanto o `DeepNPTS_aprox` apresentou bons resultados na escala
mensal. A aproximacao `DeepAR_exp`, nesta configuracao inicial, nao superou os
demais modelos e teve desempenho especialmente fraco no fluxo mensal.

Como esses modelos ainda sao uma rodada paralela, os resultados nao substituem
automaticamente as tabelas oficiais do artigo. Para entrar no texto principal,
o ideal e repetir a rodada, revisar hiperparametros e documentar claramente que
`DeepAR_exp` e `DeepNPTS_aprox` sao aproximacoes experimentais, nao
implementacoes canonicas das bibliotecas originais.
