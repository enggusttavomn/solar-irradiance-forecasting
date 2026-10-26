# Quantização da TimesNet: horário e diário

## Objetivo e situação

Este experimento completa os dois casos que ainda não tinham comparação de quantização: previsão horária até 72 horas e diária até 30 dias. Ele mantém o min-max e testa as entradas da TimesNet com 64, 128 e 256 níveis, além de um controle sem quantização.

**Situação deste registro:** os treinamentos completos do horário e do diário foram concluídos, complementando os dois casos mensais. Os resultados estão registrados abaixo. A [auditoria independente](../relatorios/quantizacao_timesnet_quatro_casos_20260927/auditoria_quantizacao_resolucoes.json) foi aprovada, com 48 de 48 checkpoints verificados. Foram conferidos 788 arquivos anteriores, com os resultados históricos preservados e somente a atualização autorizada do PDF; sua [versão anterior de seis páginas permanece em backup](../relatorios/quantizacao_timesnet_quatro_casos_20260927/fonte_6_paginas.pdf). O [PDF atualizado foi entregue com oito páginas](tabela_resultados_ghi_2024.pdf), após a aprovação da verificação visual. Os resultados mensais já existentes pertencem a outro experimento e não são substituídos por este.

O recorte de dados continua sendo **2019–2024**, nas dez localidades do projeto. A ampliação do histórico, discutida para o feedback ao Thales, não faz parte desta execução.

## Visão dos quatro casos

Macro-MAE do teste de 2024, em W/m², no horizonte cumulativo completo:

| Caso | Sem quantização | 64 níveis | 128 níveis | 256 níveis | Escolha de 2023 |
|---|---:|---:|---:|---:|---|
| Horário — 72 horas | 47,9144620 | 47,9255831 | 47,9044259 | 47,9178679 | 256 níveis |
| Diário — 30 dias | 42,1707689 | 42,1655261 | 42,1674680 | 42,1742573 | 64 níveis |
| Mensal — 1 mês | 13,8561432 | 13,7922178 | 13,9435512 | 13,9215176 | 256 níveis |
| Mensal — 6 meses | 14,1974734 | 14,0761808 | 14,2175925 | 14,2058211 | 128 níveis |

O menor erro observado em 2024 não substitui o nível escolhido em 2023. Somente no diário a escolha da validação manteve uma pequena vantagem no teste. Nos demais casos, a variante escolhida ficou ligeiramente pior que o controle. Não foi demonstrado ganho consistente nem realizada análise de significância estatística. O [feedback consolidado ao Thales](FEEDBACK_THALES_QUANTIZACAO.md) reúne deltas, a mensagem sugerida e a observação preservada sobre o histórico.

## Resultado horário concluído

| Variante | MAE validação 2023 (W/m²) | MAE teste 2024 (W/m²) | Delta do teste contra controle (W/m²) | Delta relativo |
|---|---:|---:|---:|---:|
| Sem quantização | 48,9485072 | 47,9144620 | 0 | 0% |
| 64 níveis | 48,9476248 | 47,9255831 | +0,0111211 | +0,02321% |
| 128 níveis | 48,9521889 | 47,9044259 | −0,0100361 | −0,02095% |
| 256 níveis — selecionada | 48,9442952 | 47,9178679 | +0,0034058 | +0,00711% |

Os 256 níveis foram escolhidos por 2023, mas ficaram 0,0034058 W/m² acima do controle no teste. O nível 128 teve o menor erro observado em 2024, com redução de somente 0,02095%; ele não foi a escolha feita pela validação. As quatro variantes selecionaram 30 épocas para a semente 42, atingindo o limite operacional de épocas. Isso não prova que treinar além do limite produziria melhora.

O controle horário reproduziu exatamente as previsões da otimização anterior, com diferença máxima zero na validação e no teste. Houve saturação de 14 em 1.219.680 posições de entrada tanto na validação quanto no teste, aproximadamente 0,001148%, em cada variante quantizada. Ajuste e refit tiveram saturação zero. A contagem corresponde às janelas sobrepostas.

Fontes:

- [Comparação horária completa](../resultados/quantizacao_timesnet_resolucoes_20260927/hourly_72_extension/comparacao.csv)
- [Ranking horário de validação](../resultados/quantizacao_timesnet_resolucoes_20260927/hourly_72_extension/ranking_validacao.csv)
- [Seleção horária congelada e épocas](../resultados/quantizacao_timesnet_resolucoes_20260927/hourly_72_extension/selecao_congelada.json)
- [Diagnóstico do teste horário com 256 níveis](../resultados/quantizacao_timesnet_resolucoes_20260927/hourly_72_extension/variantes/q256/diagnostico_refit.json)
- [Reprodução do controle horário no teste](../resultados/quantizacao_timesnet_resolucoes_20260927/hourly_72_extension/variantes/sem_quantizacao/reproducao_controle_refit.json)

## Resultado diário concluído

O macro-MAE do horizonte cumulativo de 30 dias ficou praticamente estável. O nível 64 foi escolhido na validação de 2023 e também apresentou o menor MAE entre as quatro variantes avaliadas em 2024, mas a redução em relação ao controle foi de apenas **0,0052427 W/m², ou 0,01243%**.

| Variante | MAE validação 2023 (W/m²) | MAE teste 2024 (W/m²) | Delta do teste contra controle (W/m²) | Delta relativo |
|---|---:|---:|---:|---:|
| Sem quantização | 43,9469711 | 42,1707689 | 0 | 0% |
| 64 níveis — selecionada | 43,9375182 | 42,1655261 | −0,0052427 | −0,01243% |
| 128 níveis | 43,9501466 | 42,1674680 | −0,0033009 | −0,00783% |
| 256 níveis | 43,9507062 | 42,1742573 | +0,0034884 | +0,00827% |

Delta negativo significa MAE menor. As diferenças foram calculadas com os valores completos dos arquivos, antes do arredondamento para a tabela. Com duas casas decimais, todas as variantes têm MAE 42,17; por isso são exibidas mais casas para tornar a dimensão da diferença verificável, sem sugerir que seja uma melhoria relevante.

As épocas selecionadas, na ordem das sementes 11/23/42/67/89, foram `7/6/7/7/7` no controle e em 256 níveis, e `7/8/7/7/7` em 64 e 128 níveis. A variante de controle reproduziu exatamente as previsões salvas da otimização anterior, com diferença máxima zero na validação e no teste.

Os diagnósticos diários mostram saturação zero nas entradas de ajuste, validação e refit. No teste, as três variantes quantizadas limitaram 328 de 1.230.050 posições de entrada, aproximadamente **0,026666%**, todas abaixo do mínimo de treino. Essas contagens são de posições em janelas sobrepostas; não representam 328 dias independentes. O erro médio causado somente pelo clipping nessas entradas foi `9,145009180771752e-7` na escala normalizada.

O resultado sustenta a conclusão de que a quantização teve impacto muito pequeno no caso diário observado. Não houve teste estatístico para declarar significância e o resultado não permite atribuir uma causa única ao pequeno delta.

Fontes:

- [Comparação diária completa](../resultados/quantizacao_timesnet_resolucoes_20260927/daily_30/comparacao.csv)
- [Ranking diário de validação](../resultados/quantizacao_timesnet_resolucoes_20260927/daily_30/ranking_validacao.csv)
- [Seleção diária congelada e épocas](../resultados/quantizacao_timesnet_resolucoes_20260927/daily_30/selecao_congelada.json)
- [Diagnóstico de quantização/clipping do teste diário com 64 níveis](../resultados/quantizacao_timesnet_resolucoes_20260927/daily_30/variantes/q64/diagnostico_refit.json)
- [Reprodução do controle diário no teste](../resultados/quantizacao_timesnet_resolucoes_20260927/daily_30/variantes/sem_quantizacao/reproducao_controle_refit.json)

## Configurações mantidas

Os hiperparâmetros vêm das seleções da TimesNet pura em `resultados/busca_timesnet_resolucoes_20260922`. A busca atual altera somente a quantização e seleciona novamente as épocas; não refaz a busca de arquitetura ou taxa de aprendizado.

| Item | Horário | Diário |
|---|---|---|
| Identificador | `hourly_72_extension` | `daily_30` |
| Unidade de cada observação | Uma hora | Um dia |
| Histórico de entrada | 336 horas, equivalentes a 14 dias | 365 dias |
| Saída de cada janela | 72 valores horários | 30 valores diários |
| Horizontes avaliados | 24, 48 e 72 horas | 1, 3, 7, 14 e 30 dias |
| Frequência de origem das previsões | Uma origem diária por localidade | Uma origem diária por localidade |
| Candidato herdado | `mae_dim16_lr0003` | `huber` |
| Função de perda no treino | MAE na escala normalizada | Huber na escala normalizada, delta 0,1 |
| Taxa de aprendizado | 0,0003 | 0,001 |
| Dimensão interna / dimensão feed-forward | 16 / 32 | 8 / 16 |
| Tamanho do lote | 64 | 128 |
| Sementes efetivas | 42 | 11, 23, 42, 67 e 89 |
| Limite de épocas por seleção | 30 | 30 |
| Paciência da parada antecipada | 5 épocas sem melhora | 5 épocas sem melhora |
| Dispositivo herdado | CUDA | CUDA |

Ambos mantêm um bloco TimesNet, `top_k=3`, dois kernels, dropout 0,1, Adam e weight decay de 0,00001. A configuração mantém uma thread de Torch no lado CPU.

A execução horária preserva **uma semente**, como a comparação de origem. A diária preserva cinco e faz a média das previsões brutas dessas cinco redes. Portanto, não se deve descrever o horário como um ensemble de cinco sementes. Os números de épocas da otimização anterior não são impostos às variantes quantizadas: cada semente tem sua melhor época novamente selecionada em 2023.

## O que é quantizado

O min-max é ajustado separadamente para cada localidade, usando somente o período anterior ao corte da fase. As entradas normalizadas são transformadas pela fórmula:

```text
x_minmax = (GHI - mínimo_do_treino) / amplitude_do_treino
x_quantizado = rint(clip(x_minmax, 0, 1) * (N - 1)) / (N - 1)
```

`N` assume 64, 128 ou 256. Os níveis são uniformes, incluem 0 e 1, e os empates usam o arredondamento para o inteiro par de `numpy.rint`. A transformação é calculada com a precisão definida no módulo comum de quantização e entregue à rede em float32.

As quatro variantes, sempre nesta ordem, são:

1. `sem_quantizacao`: min-max sem quantização e sem limitar a faixa;
2. `q64`: min-max seguido de quantização em 64 níveis;
3. `q128`: min-max seguido de quantização em 128 níveis;
4. `q256`: min-max seguido de quantização em 256 níveis.

A mesma transformação de X é aplicada no ajuste, validação, refit e inferência de teste. Os alvos são normalizados para treinamento, mas **não são quantizados**. Os pesos e a saída da rede continuam contínuos; a previsão é convertida de volta para W/m² antes das métricas. Não se trata de quantização dos pesos para INT8.

O min-max pode produzir entradas fora de `[0, 1]` quando um valor futuro ultrapassa os extremos vistos no treino. As variantes quantizadas limitam esses valores aos extremos, enquanto o controle preserva os valores fora da faixa. Assim, a comparação mede o efeito conjunto do arredondamento e dessa limitação, chamada clipping ou saturação. Os diagnósticos registram separadamente a frequência de saturação e a distorção causada apenas pelo clipping; não há uma quinta variante com somente clipping.

## Separação temporal e escolha

Na seleção, as séries são recortadas para excluir 2024 antes da construção das janelas. As escalas min-max são ajustadas com dados anteriores a 1º de janeiro de 2023. As redes aprendem com os alvos até 2022 e usam 2023 exclusivamente como validação.

| Fase | Horário: origens por localidade | Diário: origens por localidade | Corte dos alvos |
|---|---:|---:|---|
| Ajuste | 1.445 | 1.067 | Até 31/12/2022 |
| Validação | 363 | 336 | Dentro de 2023 |
| Refit | 1.810 | 1.432 | Até 31/12/2023 |
| Teste | 363 | 337 | Dentro de 2024 |

As origens e os alvos devem coincidir com a comparação anterior. As janelas usam o histórico necessário antes da origem; por isso o início dos dados brutos não coincide com a primeira origem de previsão. No diário, os dados de 2019 fornecem contexto para as primeiras origens de 2020. No horário, a primeira origem de ajuste é 15/01/2019. As janelas com horizontes sobrepostos permanecem sobrepostas, como no experimento de origem.

Para cada variante e semente, escolhe-se a época com menor macro-MAE físico na validação. Na diária, as previsões brutas das cinco redes selecionadas são então promediadas. O nível é escolhido pelo macro-MAE dessa previsão final no horizonte completo: 72 horas ou 30 dias. Empates seguem a ordem predefinida: sem quantização, 64, 128, 256.

As seleções dos **dois casos** precisam terminar e ser registradas em `selecao_global_congelada.json` antes de construir as novas janelas de refit/teste. O programa verifica essa exigência antes de ler a configuração e os dados para a fase de refit.

Depois do congelamento, cada rede é inicializada novamente com a mesma semente e treinada usando dados até 2023, pelo número de épocas já selecionado. O min-max é reajustado com dados anteriores a 1º de janeiro de 2024. As quatro variantes predefinidas são avaliadas em 2024 para mostrar a comparação completa; o menor erro de 2024 não redefine o vencedor escolhido em 2023.

## Previsões e métricas

A ordem de cálculo é: previsões brutas por semente, média das previsões brutas, pós-processamento físico e métricas. Aplicar o piso antes de calcular a média produziria outro resultado e não é o protocolo usado.

- Em ambos os casos, previsões negativas recebem piso zero.
- No horário, previsões em instantes com elevação solar menor ou igual a zero recebem zero, mantendo todas as observações na avaliação. A elevação usa o centro do intervalo horário, com deslocamento de 30 minutos.
- O MAE é calculado por localidade e depois promediado entre as localidades, com peso igual por local. Ele está em W/m².
- Os arquivos de métricas também contêm MSE, RMSE, nRMSE e R², para horizontes cumulativos e para o passo exato de cada horizonte.
- A previsão usa somente X, identificação da localidade e escalas salvas. Ela não lê os valores reais futuros para calcular sua saída.

O controle sem quantização é novamente executado e comparado às previsões brutas da TimesNet otimizada de origem, na validação e no teste. A execução completa exige diferença máxima de no máximo `0,000001 W/m²`; uma divergência maior interrompe a fase para investigação.

## Execução e retomada

Execute a partir da raiz do projeto, usando o ambiente que contém as dependências e CUDA:

```powershell
.\.venv-baselines-gpu-20260912\Scripts\python.exe -X utf8 scripts/rodar_quantizacao_resolucoes.py --smoke
.\.venv-baselines-gpu-20260912\Scripts\python.exe -X utf8 scripts/rodar_quantizacao_resolucoes.py
```

O primeiro comando faz uma integração reduzida: duas localidades, três origens por localidade, uma semente por caso e uma época. Seus números não são resultados científicos. O segundo executa todas as amostras. O executor inicia horário e diário em paralelo, com um worker por caso; termina as duas seleções, congela-as e somente então inicia os refits.

O executor registra o andamento e mantém o computador ativo durante o processo, restabelecendo a preferência normal de suspensão ao terminar ou encontrar um erro. Os logs ficam em `relatorios/quantizacao_timesnet_quatro_casos_20260927/`, junto de `runner_smoke.json` ou `runner_completo.json`.

Também é possível executar as fases individualmente:

```powershell
.\.venv-baselines-gpu-20260912\Scripts\python.exe -m codigo_fonte.experimento_quantizacao_resolucoes --tarefa hourly_72_extension --fase selecao --workers 1
.\.venv-baselines-gpu-20260912\Scripts\python.exe -m codigo_fonte.experimento_quantizacao_resolucoes --tarefa daily_30 --fase selecao --workers 1
.\.venv-baselines-gpu-20260912\Scripts\python.exe -m codigo_fonte.experimento_quantizacao_resolucoes --fase congelar
.\.venv-baselines-gpu-20260912\Scripts\python.exe -m codigo_fonte.experimento_quantizacao_resolucoes --tarefa hourly_72_extension --fase refit --workers 1
.\.venv-baselines-gpu-20260912\Scripts\python.exe -m codigo_fonte.experimento_quantizacao_resolucoes --tarefa daily_30 --fase refit --workers 1
```

Para retomar após uma interrupção, use o mesmo comando, ambiente, saída e número de workers. O cache concluído por semente é reaproveitado apenas quando contrato, fase, nível, variante, semente, épocas e hashes coincidem. Uma semente interrompida antes de gravar todos os artefatos é treinada novamente. O programa não retoma no meio de uma época.

Não execute dois processos para a mesma tarefa e pasta de saída. Um arquivo de lock protege essa situação. Se uma interrupção abrupta deixar um lock, é necessário verificar que o processo registrado nele terminou antes de remover somente esse lock. Alterações de código, dados ou configuração requerem investigar o contrato e usar uma execução separada, preservando os resultados anteriores.

## Artefatos e integridade

Saída completa: `resultados/quantizacao_timesnet_resolucoes_20260927/`.

Saída reduzida: `tmp/quantizacao_resolucoes_smoke_20260927/`.

Cada tarefa registra contrato, escalas de seleção/refit, seleção congelada, ranking de validação, comparação final, status e manifesto de arquivos. Cada variante registra checkpoints por semente, previsões, histórico de treinamento, métricas por localidade, métricas macro e diagnósticos de quantização. Os checkpoints guardam escalas, níveis, nomes das localidades, dispositivo e tamanho de lote para reconstruir a inferência.

Os contratos vinculam versões de código, dados e configurações aos respectivos hashes. O congelamento verifica as duas tarefas, quatro variantes sem duplicatas, sementes completas, níveis corretos, épocas válidas e o vencedor determinado pela validação. Os arquivos históricos não são sobrescritos.

Os novos testes unitários aprovados foram 38 para o treinador e 53 para o orquestrador. Eles verificam equivalência exata do controle com o treinador anterior em pequenas execuções CPU, preservação dos alvos, uso dos níveis no treino e inferência, pós-processamento, independência dos alvos na previsão, congelamento e rejeição de alterações nos contratos/caches. Na execução completa CUDA, os controles horário e diário reproduziram as previsões anteriores com diferença máxima zero na comparação entre os CSVs de validação e teste. A auditoria independente foi aprovada: os 48 checkpoints reproduziram exatamente suas previsões em CUDA, inclusive com alvos substituídos por NaN. Os 788 arquivos anteriores foram conferidos; os resultados históricos foram preservados, e a única atualização autorizada nesse conjunto foi o PDF, com sua versão anterior de seis páginas mantida em backup.

## Limitações para interpretar os resultados

- O histórico permanece em 2019–2024; a questão sobre ampliar a base continua pendente para discussão com o Thales.
- Os resultados de 2024 já foram observados em etapas anteriores. Esta é uma avaliação retrospectiva, mesmo com as novas escolhas restritas a 2023.
- O horário mantém apenas uma semente e não estima a variação entre inicializações nessa tarefa.
- A comparação de quantização inclui clipping, enquanto o controle não o aplica.
- Os hiperparâmetros são mantidos da busca anterior. A quantização não adiciona observações nem amplia o histórico.
- As janelas sobrepostas tornam observações da avaliação dependentes; uma pequena diferença de MAE não prova significância estatística. Este protocolo não inclui teste de significância.
- O resultado final deve informar tanto a escolha de 2023 quanto os quatro resultados de 2024, sem apresentar retroativamente a menor pontuação de teste como se tivesse sido a escolha da validação.

## Implementação de referência

- [Orquestrador](../codigo_fonte/experimento_quantizacao_resolucoes.py)
- [Treinador com quantização de entradas](../codigo_fonte/treinamento_timesnet_quantizado_resolucoes.py)
- [Definição comum da quantização](../codigo_fonte/quantizacao_timesnet.py)
- [Executor das duas tarefas](../scripts/rodar_quantizacao_resolucoes.py)
- [Testes do treinador](../testes/test_treinamento_timesnet_quantizado_resolucoes.py)
- [Testes do orquestrador](../testes/test_experimento_quantizacao_resolucoes.py)
- [Documentação da quantização mensal](QUANTIZACAO_TIMESNET_MENSAL.md)
