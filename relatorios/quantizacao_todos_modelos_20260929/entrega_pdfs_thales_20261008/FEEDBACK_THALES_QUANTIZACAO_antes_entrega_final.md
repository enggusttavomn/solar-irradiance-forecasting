# Feedback ao Thales: quantização e tamanho do histórico

> **Painel de progresso:** [abrir acompanhamento ao vivo](http://127.0.0.1:8767). Atualiza a cada 10 segundos, com barras por etapa, modelos em execução e faixas de tempo estimado. A previsão informa quais treinos estão incluídos; o prazo de todo o estudo ainda depende de medições das próximas etapas. Depois de reiniciar o computador, abra `Abrir painel de progresso.cmd` na pasta do projeto para ligar o monitor. Esse atalho abre apenas o painel; a retomada dos treinos continua sendo feita separadamente.

> **Andamento em 04/10, às 19h33:** a base 2019–2024 e seu PDF de 34 páginas permanecem concluídos e íntegros. No histórico longo, terminaram **44/44 seleções e 6/44 treinamentos finais**. Após o reinício do Windows às 18h14, conferimos 574 caches finais íntegros e retomamos somente a sequência histórica. A fila está ativa e revalida as seleções já congeladas antes de continuar os refits, sem escolher novos níveis. A contagem geral está em **138/264 etapas de seleção/refit (52,3%)**; esse percentual não representa tempo nem a conclusão dos PDFs. O histórico curto pareado, as auditorias finais e o PDF histórico continuam pendentes. [Registro de continuidade](../relatorios/quantizacao_todos_modelos_20260929/CONTINUACAO.md).

> **Andamento em 03/10, às 11h01:** a base 2019–2024 permanece concluída e auditada, com o PDF de 34 páginas entregue e íntegro. As reinicializações do computador em 02/10 interromperam a sequência histórica. A conferência encontrou **7/44 seleções completas e 97 caches finais íntegros** no histórico longo; seus refits e o histórico curto pareado ainda estão pendentes. Somente a sequência histórica foi retomada: a verificação dos 70 arquivos de origem foi aprovada e a nova fila está revalidando os caches antes de continuar os treinamentos, sem falhas registradas. Os oito checkpoints parciais do ARIMA horário com 256 níveis foram preservados antes da retomada. O estudo completo e o PDF histórico continuam pendentes. [Registro de continuidade](../relatorios/quantizacao_todos_modelos_20260929/CONTINUACAO.md).

> **Andamento em 02/10, às 05h19:** base atual concluída: **44/44 seleções e 44/44 treinamentos finais**, auditoria completa aprovada e [PDF atualizado com 34 páginas](tabela_resultados_ghi_2024.pdf) entregue após revisão visual de todas as páginas. As tabelas reúnem os 11 modelos por nível de quantização nos quatro casos. O histórico longo está em treinamento (6/44 seleções, 0/44 refits); o curto pareado ainda não concluiu (0/44 seleções, 0/44 refits). O estudo inteiro e o PDF histórico permanecem pendentes. [Registro de continuidade](../relatorios/quantizacao_todos_modelos_20260929/CONTINUACAO.md).

> **Andamento em 30/09/2026:** os resultados abaixo pertencem ao estudo anterior da **TimesNet**. A extensão para os 11 modelos, com 64, 128 e 256 níveis nos quatro casos, está em treinamento. A coleta de 1998–2022 já foi concluída e auditada; os treinamentos históricos aguardam a conclusão da base atual. O feedback geral e os novos PDFs ainda não estão prontos. [Acompanhamento da extensão](QUANTIZACAO_TODOS_MODELOS.md).

## Feedback atual: todos os modelos na base 2019-2024

A auditoria completa aprovou os 44 pares de modelo/caso, com recálculo independente das 1.056 linhas de métricas de validação/teste e reprodução dos checkpoints novos. Os quatro casos da TimesNet já auditados foram reaproveitados; os 40 pares concorrentes foram concluídos nesta extensão. O PDF tem tabelas individuais por nível, incluindo o controle sem quantização, e marca as escolhas feitas na validação.

> Bom dia Thales, finalizei os testes de todos os modelos na base 2019-2024, mantendo o min-max e comparando 64, 128 e 256 níveis. As tabelas estão no PDF atualizado, separadas por nível.
>
> Pelas escolhas da validação, 13 combinações de modelo e caso tiveram MAE menor no teste e 21 tiveram MAE maior. Em outras 10, a validação manteve a opção sem quantização. Não apareceu um ganho uniforme. A maior redução entre as escolhas quantizadas foi no ARIMA mensal de seis meses: 2,63%. Esses são resultados observados, sem teste de significância.
>
> Os treinamentos de 1998-2022 e a comparação com o histórico curto ainda estão em andamento; mando essa parte depois que terminar.

O [resumo auditado completo](../relatorios/quantizacao_todos_modelos_20260929/feedback_resultados_atual.md) traz os 44 pares, os MAEs e os deltas. O XGBoost horário usa o novo controle de refit repetido integralmente e auditado; a divergência com a execução antiga permanece documentada com causa não identificada. Nenhuma diferença entre ambientes ou controles antigos é atribuída à quantização.

Os registros abaixo preservam a análise anterior, restrita à TimesNet; não representam o resultado geral dos 11 modelos.

## Observação preservada sobre o histórico

O projeto utiliza dados de 2019–2024. Na escolha dos modelos, os dados anteriores a 2023 alimentam o ajuste e 2023 é a validação. Depois, o treinamento final usa dados até 2023 e a avaliação usa 2024. Os primeiros registros também compõem as janelas de entrada.

Na análise anterior da TimesNet, esse recorte veio da coleta existente. A ampliação para 1998-2022 foi coletada e auditada depois; seus treinamentos estão em andamento. Não foi encontrada uma justificativa técnica que obrigue a TimesNet a começar em 2019. No mensal, seis anos correspondem a aproximadamente 72 valores por localidade antes de separar treino, validação, teste e contexto.

O artigo do Luís enviado como `1692342.pdf` usa 1998–2022, totalizando 25 anos, em 16 estádios, com divisão cronológica 85%/15%. O nosso conjunto contém dez outras localidades. O artigo relata MAE médio de 12,76 W/m² e descreve min-max, mas não informa uso nem níveis de quantização. O PDF tampouco permite confirmar uma previsão direta de 60 meses.

O histórico curto pode limitar o aprendizado da variação entre anos, mas essa hipótese ainda não foi testada. Mais épocas ou quantização não acrescentam anos de informação. Para comparar o efeito do histórico, é necessário verificar cobertura e compatibilidade dos dados antigos, ampliar a coleta e definir um novo experimento. Mesmo períodos iguais não tornam os estudos idênticos, pois as localidades e os protocolos diferem. Não é possível atribuir a diferença de MAE ao histórico sem esse experimento, nem garantir que ampliar a base melhorará o resultado.

## Complementação concluída: quatro casos

Os treinamentos de quantização dos casos horário (até 72 horas) e diário (até 30 dias) foram concluídos, complementando os mensais de um e seis meses. A [auditoria independente](../relatorios/quantizacao_timesnet_quatro_casos_20260927/auditoria_quantizacao_resolucoes.json) foi aprovada: 48 de 48 checkpoints novos de horário/diário reproduziram exatamente as previsões em CUDA, inclusive com alvos substituídos por NaN. Foram verificados 788 arquivos anteriores, com os resultados históricos preservados; a única atualização autorizada nesse conjunto foi o PDF, cuja [versão anterior de seis páginas está preservada em backup](../relatorios/quantizacao_timesnet_quatro_casos_20260927/fonte_6_paginas.pdf). O [PDF atualizado foi entregue com oito páginas](tabela_resultados_ghi_2024.pdf), após a aprovação da verificação visual.

Em cada caso foram comparadas entradas sem quantização e com 64, 128 e 256 níveis, mantendo min-max e as configurações da TimesNet pura selecionadas anteriormente. A quantização foi aplicada somente a X, depois do min-max, no treino e na inferência. Alvos, pesos e previsões continuam contínuos. As épocas foram novamente escolhidas pela validação de 2023.

O horário preservou uma semente, 42. Diário e mensais usaram cinco sementes, 11/23/42/67/89, com média das previsões brutas antes do piso zero. O horário também mantém a máscara solar no pós-processamento. Na complementação, os controles horário e diário reproduziram exatamente as previsões anteriores: diferença máxima zero, tanto na validação quanto no teste.

As escolhas de níveis foram feitas em 2023, antes dos novos refits e da avaliação de 2024. A coleta de 2019–2024 permanece nesta comparação. A ampliação do histórico é uma investigação posterior.

## Resultados após a quantização

Macro-MAE em W/m², no teste de 2024 e no horizonte cumulativo completo de cada caso:

| Caso | Sem quantização | 64 níveis | 128 níveis | 256 níveis | Escolha pela validação de 2023 |
|---|---:|---:|---:|---:|---|
| Horário — 72 horas | 47,9144620 | 47,9255831 | 47,9044259 | 47,9178679 | 256 níveis |
| Diário — 30 dias | 42,1707689 | 42,1655261 | 42,1674680 | 42,1742573 | 64 níveis |
| Mensal — 1 mês | 13,8561432 | 13,7922178 | 13,9435512 | 13,9215176 | 256 níveis |
| Mensal — 6 meses | 14,1974734 | 14,0761808 | 14,2175925 | 14,2058211 | 128 níveis |

As casas adicionais tornam as pequenas diferenças visíveis; não representam uma afirmação de precisão estatística. Os deltas abaixo foram calculados com os valores completos dos arquivos.

| Caso | Delta em 2024 da escolha feita em 2023 | Menor MAE observado entre as variantes em 2024 | Redução observada contra o controle |
|---|---:|---|---:|
| Horário | +0,0034058 W/m² (+0,00711%) | 128 níveis: 47,9044259 | 0,0100361 W/m² (0,02095%) |
| Diário | −0,0052427 W/m² (−0,01243%) | 64 níveis: 42,1655261 | 0,0052427 W/m² (0,01243%) |
| Mensal 1 | +0,0653744 W/m² (+0,47181%) | 64 níveis: 13,7922178 | 0,0639254 W/m² (0,46135%) |
| Mensal 6 | +0,0201191 W/m² (+0,14171%) | 64 níveis: 14,0761808 | 0,1212926 W/m² (0,85433%) |

Delta positivo significa aumento do erro. A coluna com o menor MAE observado no teste é descritiva e não redefine a escolha de 2023. Somente no diário a escolha feita na validação também foi a melhor observada no teste; nos outros três casos, a opção selecionada ficou ligeiramente pior que o controle em 2024.

A quantização produziu alterações pequenas no horário e no diário, e ganhos abaixo de 1% mesmo nas melhores variantes mensais observadas retrospectivamente. Não houve ganho consistente entre as escolhas de validação e o teste. Não foi feito teste estatístico de significância, e os resultados não demonstram que a quantização removeu ruído ou que o histórico curto causou as diferenças.

## Clipping e outros limites da comparação

As entradas quantizadas são limitadas à faixa `[0, 1]`, enquanto o controle sem quantização preserva valores fora dessa faixa. A comparação inclui arredondamento e clipping. A saturação foi a mesma nos três números de níveis:

| Caso | Entradas saturadas na validação | Entradas saturadas no teste |
|---|---:|---:|
| Horário | 14/1.219.680 (0,001148%) | 14/1.219.680 (0,001148%) |
| Diário | 0/1.226.400 | 328/1.230.050 (0,026666%) |
| Mensal 1 | 24/1.440 (1,666667%) | 0/1.440 |
| Mensal 6 | 9/840 (1,071429%) | 0/840 |

Nos quatro casos, os diagnósticos indicam saturação zero nas entradas do ajuste e do refit. As contagens se referem a posições nas janelas sobrepostas, não a observações independentes. Sem uma variante adicional com apenas clipping, não se pode separar completamente seus efeitos dos efeitos do arredondamento na avaliação.

O ano de 2024 já havia sido observado antes destes novos experimentos, portanto a análise permanece retrospectiva. As localidades e os protocolos do artigo do Luís diferem dos nossos. Seu MAE não é uma meta diretamente comparável sob condições idênticas, e o artigo não documenta quantização nem confirma um horizonte direto de 60 meses.

## Mensagem anterior sobre a TimesNet — ainda não enviada

> Thales, terminei os testes de quantização da TimesNet nos quatro casos, com 64, 128 e 256 níveis, mantendo o min-max. No geral, o MAE mudou muito pouco.
>
> No teste de 2024, o menor MAE no horário foi com 128 níveis: passou de 47,9145 pra 47,9044. No diário, foi com 64: de 42,1708 pra 42,1655. Nos mensais, 64 também teve o menor erro: 13,7922 no de um mês e 14,0762 no de seis meses, com reduções de 0,46% e 0,85%.
>
> Só que esses são os melhores valores observados no teste. Os níveis foram escolhidos pela validação de 2023, e só no diário essa escolha também foi a melhor em 2024. Nos outros três casos, a configuração escolhida ficou um pouco pior que sem quantização. Então não apareceu uma melhora consistente.
>
> Também conferi o histórico: nossa base vai de 2019 a 2024, com 2024 reservado pro teste, enquanto o artigo do Luís usa 1998–2022. É uma diferença pra investigar, mas os locais e a divisão dos dados também mudam. Ainda não dá pra afirmar que o histórico mais curto explica a diferença no MAE.

## Referências locais

- `Downloads/1692342.pdf`: artigo do Luís, páginas 2–4 (método, dados e métricas).
- `documentacao/OTIMIZACAO_TIMESNET_QUATRO_CASOS.md`: otimização anterior, sem quantização.
- `documentacao/QUANTIZACAO_TIMESNET_MENSAL.md`: resultados mensais de quantização.
- `executaveis/coletar_dados_horarios_nsrdb.py`: período padrão da coleta.
- [Protocolo e resultados de horário/diário](QUANTIZACAO_TIMESNET_HORARIO_DIARIO.md).
- [Comparação horária](../resultados/quantizacao_timesnet_resolucoes_20260927/hourly_72_extension/comparacao.csv).
- [Comparação diária](../resultados/quantizacao_timesnet_resolucoes_20260927/daily_30/comparacao.csv).
- [Comparação mensal de um mês](../resultados/quantizacao_timesnet_mensal_20260923/monthly_1/comparacao.csv).
- [Comparação mensal de seis meses](../resultados/quantizacao_timesnet_mensal_20260923/monthly_6/comparacao.csv).
- Os rankings, épocas e escolhas estão em `selecao_congelada.json` de cada uma das pastas acima. Os diagnósticos são `variantes/q64/diagnostico_selecao.json` e `diagnostico_refit.json`, com correspondentes arquivos em `q128` e `q256`.
