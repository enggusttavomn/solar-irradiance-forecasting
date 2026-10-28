# TimesNet: otimização das quatro tarefas de GHI

Revisão de 23/09/2026: o PDF `tabela_resultados_ghi_2024.pdf` compara a TimesNet original com a TimesNet otimizada por hiperparâmetros nas quatro tarefas. A combinação com climatologia foi retirada dessa comparação. A climatologia permanece como modelo de referência independente, como no benchmark original.

## Resultados de teste de 2024

Macro-MAE em W/m², no horizonte completo de cada tarefa, calculado como a média entre dez localidades.

| Tarefa | TimesNet original | TimesNet otimizada | Redução do MAE |
|---|---:|---:|---:|
| Horária - 72 h | 52,48 | 47,91 | 8,70% |
| Diária - 30 dias | 44,08 | 42,17 | 4,33% |
| Mensal - 1 mês | 13,89 | 13,86 | 0,25% |
| Mensal - 6 meses | 14,46 | 14,20 | 1,80% |

Os ganhos mensais são pequenos. A climatologia isolada ainda tem menor MAE nos horizontes completos mensais (12,57 e 13,03). Nenhum dos dois resultados mensais da TimesNet fica abaixo de 13 W/m².

A busca prioriza MAE; isso não implica melhorar todas as métricas. No diário, o RMSE aumenta de 55,16 para 56,02 W/m², e o MSE de 3143,38 para 3247,65 (W/m²)². O PDF apresenta as demais métricas e os horizontes intermediários.

Os valores sem arredondamento estão em [metricas_tabela.csv](../relatorios/tabela_resultados_ghi_pura_20260923/metricas_tabela.csv). A [comparação consolidada](../relatorios/correcao_timesnet_pura_20260923/comparacao_final.json) registra os quatro horizontes completos.

## O que foi corrigido

Foram mantidos os ajustes já concluídos para os casos horário e diário. Para os dois mensais, foram recuperados os experimentos da busca exclusivamente com TimesNet (`busca_timesnet_mensal_20260920`), com seleção pela validação de 2023. As previsões e os checkpoints foram novamente conferidos; não foi necessário retreinar os modelos para corrigir a comparação.

A grade mensal padrão agora contém somente candidatos que preveem diretamente o GHI. O gerador do PDF rejeita uma busca mensal com alvo residual ou combinação com climatologia. Os artefatos da busca híbrida V2 foram preservados como histórico, sem entrar nos novos resultados principais. A versão anterior do PDF e dos documentos está em [antes_correcao](../relatorios/correcao_timesnet_pura_20260923/antes_correcao/).

## Configurações selecionadas

| Tarefa | Perda | Contexto | Dimensão da rede | Taxa de aprendizado | Lote | Sementes |
|---|---|---|---:|---:|---:|---|
| Horária | MAE | 336 horas | 16 | 0,0003 | 64 | 42 |
| Diária | Huber | 365 dias | 8 | 0,001 | 128 | 11, 23, 42, 67, 89 |
| Mensal - 1 mês | MAE | 12 meses | 16 | 0,0003 | 32 | 11, 23, 42, 67, 89 |
| Mensal - 6 meses | Huber | 12 meses | 8 | 0,001 | 32 | 11, 23, 42, 67, 89 |

A escolha usa o macro-MAE físico de 2023, após inversão da escala e pós-processamento. Além dos hiperparâmetros, mudou o critério de seleção das épocas em relação ao MSE normalizado da configuração original; portanto, os ganhos não isolam o efeito de cada ajuste. As épocas de treinamento foram selecionadas por semente. Horária: 30; diária: 7, 6, 7, 7, 7; mensal de um mês: 64, 45, 60, 65, 94; mensal de seis meses: 77, 20, 30, 52, 36. A ordem das cinco sementes é a indicada na tabela. A horária atingiu o limite operacional de 30 épocas e pode não ter convergido.

## Protocolo e limites

As entradas usam min–max por localidade, ajustado antes de 2023 na seleção e antes de 2024 no treinamento final. Não há quantização. As redes usam saída contínua. Na diária e nas mensais, calcula-se a média de cinco treinamentos da mesma TimesNet, com sementes diferentes; não se somam previsões de climatologia a essa média.

Após congelar a escolha em 2023, cada rede foi reinicializada e treinada com dados até 2023 pelo número de épocas selecionado. Os resultados finais usam os mesmos locais, origens e observações do benchmark de 2024. Aplica-se piso zero; no horário, também a máscara de elevação solar do protocolo original. As observações noturnas continuam incluídas nas métricas.

A grade horária/diária compara perdas MAE e Huber, rede de dimensão 16 com taxa 0,0003 e contexto mais curto (168 horas ou 182 dias), além da configuração original. A grade mensal compara MSE/MAE/Huber, taxas 0,001/0,0003, dimensões 8/16, um/dois blocos e contextos de 12/24 meses. O contexto de 36 meses foi descartado por falta de histórico suficiente. Nos mensais, variar o contexto também altera o número de exemplos de treino; não é um experimento que isola apenas o comprimento da janela.

Cada métrica é calculada por localidade e depois agregada pela média dos dez locais; MSE e RMSE são agregados separadamente. Os horizontes intermediários são cumulativos. A seleção pelo horizonte completo não garante melhora em cada subtabela.

O mensal de seis meses possui sete origens de teste por localidade, com alvos sobrepostos, e não equivale a prever cinco anos. O mensal de um mês possui doze origens e não é intercambiável com o primeiro passo da tarefa de seis meses.

A otimização foi motivada por resultados de 2024 já observados. Embora a seleção interna use 2023, a avaliação de 2024 é retrospectiva e precisa de confirmação em outro período. Não houve ampliação do histórico disponível (2019–2024), avaliação da variação entre anos ou comprovação de superioridade sobre o artigo do Luís.

## Reprodução e auditoria

Executar na raiz do projeto com `.venv-baselines-gpu-20260912/Scripts/python.exe`:

```powershell
python relatorios/correcao_timesnet_pura_20260923/auditar_mensal_v1_pura.py
python -m scripts.gerar_tabela_resultados_ghi_otimizada --somente-validar
python -m scripts.gerar_tabela_resultados_ghi_otimizada
```

Fontes: `resultados/busca_timesnet_resolucoes_20260922` para horário/diário e `resultados/busca_timesnet_mensal_20260920` para os mensais puros. A auditoria de horário/diário está em `relatorios/otimizacao_timesnet_quatro_casos_20260922/auditoria_resolucoes.json`; a referência mensal híbrida contida nesse relatório antigo não foi reutilizada nesta revisão. A nova auditoria mensal está em [auditoria_mensal_v1_pura.json](../relatorios/correcao_timesnet_pura_20260923/auditoria_mensal_v1_pura.json).

O PDF, seus valores, hashes e renderizações são conferidos na pasta `relatorios/tabela_resultados_ghi_pura_20260923`. Os contratos históricos continuam intactos. Mudanças de código, configuração ou dados exigem uma nova pasta de busca; não se alteram hashes para forçar retomada. Para reproduzir a inferência, preservar dispositivo, tamanho e ordem dos lotes, pois a escolha de frequências da TimesNet depende do lote.
A [auditoria consolidada desta revisão](../relatorios/correcao_timesnet_pura_20260923/auditoria_quatro_casos_puros.json) reúne somente as quatro tarefas puras e confere 328 artefatos. Passaram 81 testes de busca mensal, checkpoints, locks e geração da tabela. Há uma ressalva histórica de procedência: os contratos canônicos mensais divergem de seus manifestos antigos, embora as previsões, checkpoints e demais 54 arquivos de cada tarefa permaneçam íntegros. Essa divergência foi registrada, sem modificar os contratos; as previsões do benchmark consolidado também foram conferidas contra as canônicas. Os dez checkpoints da busca mensal pura reproduziram exatamente suas previsões em CPU.