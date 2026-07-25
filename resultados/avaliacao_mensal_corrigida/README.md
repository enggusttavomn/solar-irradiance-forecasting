# Avaliação mensal corrigida

Esta é a única pasta de resultados mensais atualmente autorizada como fonte
para o TCC e para os artigos. As pastas `todas_localidades_mensal/` e
`experimentos_redes_avancadas/` são registros legados e não devem fornecer
números ou conclusões para publicação.

## Protocolo

- variável: média mensal da GHI em W/m², incluindo as 24 horas do dia;
- histórico para atributos: janeiro a dezembro de 2019;
- treino: 48 alvos, janeiro de 2020 a dezembro de 2023;
- teste: 12 alvos, janeiro a dezembro de 2024;
- horizonte: um mês à frente;
- avaliação: `walk-forward`, modelo fixo, usando a observação real do mês
  anterior; não é uma previsão recursiva dos 12 meses feita em dezembro de
  2023;
- alvo: contínuo, com min--max ajustado somente no trecho pré-teste disponível
  até dezembro de 2023, incluindo o contexto de 2019;
- atributos: 12 defasagens consecutivas, médias de 3, 6 e 12 meses e calendário
  circular do mês-alvo;
- referência primária: climatologia mensal ajustada somente em 2020--2023;
- métrica primária: MAE em W/m² por localidade;
- inferência: retrospectiva e exploratória, pois 2024 já havia sido inspecionado
  durante o desenvolvimento.

Os modelos MLP, RNN e LSTM foram executados com as sementes 42, 43 e 44. A
previsão principal é a média das três previsões. XGBoost e Vizinhos Históricos
Ponderados (VHP) usam uma semente/configuração determinística. O VHP é um
suavizador local e não é uma implementação do DeepNPTS.

## Resultado principal

| Modelo | MAE (W/m²) | RMSE (W/m²) | R² | nRMSE (%) |
|---|---:|---:|---:|---:|
| Climatologia | 12,071 | 15,320 | 0,931 | 7,640 |
| MLP | 12,832 | 15,757 | 0,908 | 7,738 |
| XGBoost | 13,833 | 17,194 | 0,908 | 8,549 |
| VHP | 15,494 | 18,712 | 0,903 | 9,280 |
| Sazonal ingênuo | 16,943 | 21,373 | 0,829 | 10,376 |
| Persistência | 35,088 | 42,167 | 0,576 | 20,887 |
| RNN | 43,130 | 50,790 | 0,438 | 25,155 |
| LSTM | 59,079 | 66,939 | 0,077 | 33,483 |

A climatologia teve o menor MAE médio. A diferença MLP menos climatologia foi
+0,760 W/m², com IC95% bootstrap de -0,737 a 2,378 W/m² e Wilcoxon--Holm
`p=0,4922`; portanto, foi inconclusiva. O VHP ficou +3,423 W/m² acima da
climatologia, IC95% de 1,753 a 5,083 e `p=0,0234` após Holm. Esses resultados
não sustentam a alegação de que uma rede neural ou o VHP superou a referência
climatológica de forma geral.

Vencedores locais por MAE: MLP em quatro localidades, climatologia em três,
XGBoost em duas e VHP em uma (BYD Camaçari). Essa contagem é descritiva e não
autoriza escolher retrospectivamente um modelo por localidade.

## Arquivos de auditoria

- `metricas_geral.csv`: métricas explícitas nas escalas normalizada e física;
- `resumo_modelos_mae.csv`: média e IC bootstrap do MAE entre localidades;
- `comparacao_climatologia.csv`: diferenças pareadas, Wilcoxon e ajuste de Holm;
- `metricas_por_seed.csv` e `variabilidade_sementes.csv`: sensibilidade às
  sementes;
- `protocolo_temporal.csv`: datas, tamanhos, transformação e atributos;
- `previsoes/`: valores observados e previstos para cada localidade;
- `previsoes_seeds/`: previsões reobtidas de cada modelo persistido;
- `manifesto_execucao.json`: versões, configuração e SHA-256 dos insumos;
- `estatisticas_horarias.csv`: registra explicitamente a indisponibilidade das
  séries horárias brutas. Somente os agregados diários e seus metadados foram
  preservados, portanto estatísticas intradiárias não são publicáveis.

## Reprodução

No ambiente fixado por `requirements.txt`, a execução completa é:

```bash
python treinar_todas_localidades.py \
  --frequencia mensal \
  --repeticoes-redes 3 \
  --seed 42 \
  --sem-figuras
```

Para comprovar que os arquivos de modelos reproduzem as previsões publicadas:

```bash
python reavaliar_modelos_salvos.py --repeticoes 3 --seed 42
```

Para revalidar e reconstruir apenas as tabelas a partir das previsões já
salvas, sem novo ajuste:

```bash
python treinar_todas_localidades.py \
  --frequencia mensal \
  --repeticoes-redes 3 \
  --seed 42 \
  --somente-consolidar
```

O caderno de leitura é
`cadernos_jupyter/04_avaliacao_mensal_corrigida.ipynb`.
