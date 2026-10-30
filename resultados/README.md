# Resultados

Tudo o que o código produz fica nesta área: previsões, métricas, modelos
treinados, gráficos, PDFs, análises e auditorias.

| Conteúdo | Onde encontrar |
|---|---|
| Evidências de um experimento | pasta identificada pela execução |
| Modelos treinados preservados | [`modelos/`](modelos/) |
| Análises, auditorias e painéis | [`relatorios/`](relatorios/) |
| PDFs exportados | [`pdf/`](pdf/) |

O programa que gera um arquivo fica em [`../codigo_fonte/`](../codigo_fonte/).
As instruções para executar ficam em [`../documentacao/`](../documentacao/).

Este diretório separa evidência científica atual de execuções históricas. Uma
pasta só deve ser tratada como publicável quando seu `status_execucao.json`
declara conclusão e resultado publicável, e quando o manifesto e os hashes são
compatíveis com o código utilizado.

## Fontes atuais

| Caminho | Conteúdo |
|---|---|
| `avaliacao_multirresolucao_corrigida_v2/` | fonte atual local do artigo unificado: tarefas horária de 72 h, diária de 30 dias e mensais de 1 e 6 meses |
| `artigo_revista_unificado/revisao_20260907/` | derivados de apresentação da revisão atual, incluindo comparações focais, perfis de sete dias e manifesto |
| `artigo_revista_unificado/auditoria_resultados_20260907/` | auditoria numérica das previsões e métricas atuais |
| `avaliacao_mensal_canonica/` | avaliação mensal canônica preservada para os artigos anteriores e para o site |
| `avaliacao_horaria_timesnet/` | execução horária original do artigo IEEE, usada como referência pela extensão horária |

A fonte atual e seus derivados completos estão disponíveis no ambiente local.
O pacote de previsões de `avaliacao_multirresolucao_corrigida_v2/` não integra o
snapshot público do repositório; clonar o código não fornece todos os arquivos
necessários para recalcular as métricas do manuscrito a partir das previsões
individuais. O suplemento identifica esse arquivo e seus artefatos. Os nomes de
pastas acima indicam sua função científica, sem garantir que seu conteúdo
completo esteja versionado.

## Resultados históricos

`avaliacao_multirresolucao/` e
`artigo_revista_unificado/artefatos_resultados/` preservam versões anteriores
da avaliação e de suas consolidações. A consolidação auditada
`artigo_revista_unificado/artefatos_resultados_corrigidos_FINAL/` também é
preservada como antecedente da revisão de 07/09/2026.

Diretórios como `avaliacao_mensal_corrigida/`,
`avaliacao_mensal_canonica_legado_sem_embeddings/`,
`experimentos_redes_avancadas/`, `todas_localidades/` e
`todas_localidades_mensal/` documentam etapas anteriores. Use as fontes atuais
identificadas acima para conferir os números do artigo unificado.

Pastas locais de `smoke`, `validacao`, correção ou revisão visual são
intermediárias até que uma execução seja validada e identificada
explicitamente como fonte atual. O nome `corrigida` ou a exclusão pelo Git não
definem seu papel científico: `avaliacao_multirresolucao_corrigida_v2/` é a
fonte atual mesmo sem integrar o snapshot público.

## Regras de publicação

- Não edite CSVs, JSONs, tabelas ou figuras derivados manualmente.
- Preserve configuração, sementes, ambiente, status e hashes dos insumos.
- Use `smoke` apenas para verificar o fluxo de software.
- Registre limitações e falhas junto aos artefatos; não promova silenciosamente
  uma execução parcial.
- Atualize o índice e os testes quando uma nova execução substituir a fonte
  oficial.
