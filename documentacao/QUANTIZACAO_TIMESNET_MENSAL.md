# TimesNet mensal: testes de quantização com min-max

O experimento compara a TimesNet mensal com entradas contínuas e com quantização uniforme de 64, 128 e 256 níveis. O min-max por localidade permanece em todos os casos. A quantização atua somente nas entradas após a normalização; os alvos de treinamento, as saídas e as observações usadas nas métricas permanecem contínuos. Os pesos da rede não são quantizados.

## Protocolo fixado antes dos novos testes

- Tarefas: mensal de um mês e mensal exploratória de seis meses, nas mesmas dez localidades.
- Entrada: 12 meses. Um valor por mês e por localidade, média dos valores diários de GHI.
- Um mês: perda MAE, dimensão 16, dimensão interna 32 e taxa de aprendizado 0,0003.
- Seis meses: perda Huber (delta 0,1 na escala normalizada), dimensão 8, dimensão interna 16 e taxa 0,001.
- Ambas: um bloco, dropout 0,1, lote 32, sementes 11/23/42/67/89, CPU com uma thread por processo, máximo de 300 épocas e paciência de 30.
- Controle sem quantização treinado novamente com as mesmas configurações e sementes. As versões de 64, 128 e 256 alteram apenas o processamento das entradas.

A seleção usa dados de ajuste anteriores a 2023 e validação de 2023. Cada semente seleciona a época pelo macro-MAE físico. O nível selecionado é o de menor macro-MAE das previsões médias das cinco sementes, no horizonte completo. Em empate, a ordem predefinida é controle, 64, 128 e 256.

As escolhas de ambas as tarefas são congeladas juntas antes de construir as janelas do novo teste de 2024. Depois, todas as quatro variantes são reinicializadas e treinadas com dados até 2023 pelas épocas selecionadas. O teste apresenta todas as variantes predefinidas para transparência; não escolhe novamente o nível pelo resultado de 2024.

## Transformação e saturação

Para N níveis, a entrada normalizada é transformada por `rint(clip(x, 0, 1) * (N - 1)) / (N - 1)`. Os empates de arredondamento usam o inteiro par mais próximo, conforme `numpy.rint`. A transformação é calculada em float64 e entregue à rede em float32. A inferência usa a mesma transformação e não consulta os alvos.

As escalas min-max são ajustadas com dados anteriores a 2023 na seleção e anteriores a 2024 no treinamento final. Valores novos podem cair fora de [0, 1]; nas versões quantizadas são limitados aos extremos. O controle mantém o comportamento anterior, sem essa limitação. Portanto, a comparação mede o efeito conjunto do arredondamento e da saturação, e não isola apenas o arredondamento.

Os diagnósticos registram entradas abaixo de zero e acima de um, quantas foram saturadas e os erros de entrada gerados pelo processamento. Os denominadores contam posições nas janelas, que podem repetir um mesmo mês em origens diferentes. A tabela não deve interpretá-los como meses independentes.

O piso zero continua aplicado às previsões depois de inverter o min-max. As cinco previsões brutas são promediadas antes desse piso. As métricas são calculadas contra GHI real em W/m², primeiro por localidade e depois pela média entre os dez locais.

## Execução e rastreabilidade

O novo código fica em `codigo_fonte/experimentos/quantizacao_timesnet.py` e `codigo_fonte/experimentos/experimento_quantizacao_timesnet.py`. Os módulos históricos de treinamento e os resultados anteriores foram preservados. Os novos artefatos ficam em `resultados/quantizacao_timesnet_mensal_20260923`.

Na raiz do projeto, usando `.venv-baselines-gpu-20260912/Scripts/python.exe`:

```powershell
python -m codigo_fonte.experimentos.experimento_quantizacao_timesnet --tarefa monthly_1 --fase selecao --workers 2
python -m codigo_fonte.experimentos.experimento_quantizacao_timesnet --tarefa monthly_6 --fase selecao --workers 2
python -m codigo_fonte.experimentos.experimento_quantizacao_timesnet --fase congelar
python -m codigo_fonte.experimentos.experimento_quantizacao_timesnet --tarefa monthly_1 --fase refit --workers 2
python -m codigo_fonte.experimentos.experimento_quantizacao_timesnet --tarefa monthly_6 --fase refit --workers 2
```

Cada checkpoint inclui os níveis, as escalas, as identidades das localidades, os parâmetros da rede, a semente e as referências às seleções congeladas. Cada semente possui histórico de épocas, previsão e duração. Contratos vinculam código, dados e configurações por hashes; retomadas incompatíveis são recusadas. Uma mudança de configuração exige outra pasta de saída.

O PDF mantém as quatro páginas anteriores e acrescenta duas páginas de comparação mensal. O relatório e a cópia do PDF anterior ficam em `resultados/relatorios/quantizacao_timesnet_20260923`.

## Resultado da seleção em 2023

MAE em W/m², no horizonte completo de cada tarefa:

| Entrada | Um mês | Seis meses |
|---|---:|---:|
| Sem quantização | 15,4369 | 17,0540 |
| 64 níveis | 15,4543 | 16,9798 |
| 128 níveis | 15,4269 | **16,9724** |
| 256 níveis | **15,3957** | 17,0350 |

As escolhas congeladas foram 256 níveis para um mês e 128 níveis para seis meses. Os valores em negrito indicam a seleção pela validação; não são resultados de teste.

## Resultado do teste de 2024

MAE em W/m². Todos os níveis foram definidos antes do teste:

| Entrada | Um mês | Seis meses |
|---|---:|---:|
| Sem quantização | 13,8561 | 14,1975 |
| 64 níveis | 13,7922 | 14,0762 |
| 128 níveis | 13,9436 | 14,2176 |
| 256 níveis | 13,9215 | 14,2058 |

Os 64 níveis apresentaram o menor MAE observado no teste: redução de 0,0639 W/m² (0,46%) em um mês e 0,1213 W/m² (0,85%) em seis meses. Entretanto, essa variante não venceu a validação de 2023. As escolhas congeladas (256 e 128, respectivamente) tiveram MAE um pouco maior que o controle em 2024. Portanto, o experimento não demonstra melhora consistente da quantização pelo protocolo de seleção; não se promoveu 64 com base no teste.

Os controles reproduziram exatamente as previsões do experimento puro anterior, nas cinco sementes e na média. O PDF apresenta as quatro variantes, destaca a seleção de 2023 e mantém os resultados das quatro tarefas anteriores.

A implementação e o gerador passaram em 84 testes automatizados. Os registros de testes, reprodução dos controles, auditoria dos modelos e verificação do PDF ficam em `resultados/relatorios/quantizacao_timesnet_20260923`.

## Limites da comparação

O ano de 2024 já havia sido analisado antes desta proposta. Mesmo usando 2023 para selecionar as épocas e os níveis, a avaliação é retrospectiva e precisa de confirmação em outro período. A dispersão entre cinco sementes não representa um intervalo de confiança para outros anos.

A tarefa mensal de seis meses usa sete origens de teste por localidade, com alvos sobrepostos. Seus horizontes de 1, 3 e 6 meses são cumulativos. A tarefa de um mês usa doze origens e não é intercambiável com o primeiro passo da tarefa de seis meses. Não houve ampliação do histórico ou previsão de cinco anos.
