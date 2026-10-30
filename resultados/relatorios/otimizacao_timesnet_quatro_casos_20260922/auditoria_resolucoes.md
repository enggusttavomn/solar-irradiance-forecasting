# Auditoria consolidada TimesNet: quatro casos

Integridade, selecao, metricas e reproducao das tarefas diaria e horaria: aprovadas.

| Tarefa | Vencedor | MAE validacao (W/m2) | MAE teste (W/m2) | Artefatos | Checkpoints reproduzidos |
|---|---|---:|---:|---:|---:|
| daily_30 | huber | 43.946971131149 | 42.170768863742 | 67 | 5 |
| hourly_72_extension | mae_dim16_lr0003 | 48.948507181347 | 47.914462038846 | 23 | 1 |

Os seis checkpoints foram reproduzidos na GPU com erro maximo 0.0 W/m2. A maior diferenca numerica nas verificacoes foi 3.637978807091713e-12, abaixo da tolerancia absoluta de 1e-7. Alinhamento, escalas, pos-processamento, metricas e cronologia dos artefatos foram conferidos.

## Evidencia mensal preservada

Os 334 artefatos mensais foram revalidados. A reproducao dos dez checkpoints esta documentada na auditoria mensal anterior e nao foi reexecutada nesta etapa.

| Tarefa | Metodo | MAE teste (W/m2) |
|---|---|---:|
| monthly_1 | TimesNet + climatologia | 13.236257093299 |
| monthly_6 | TimesNet + climatologia | 13.167131839566 |

Auditoria mensal: `C:\Users\gm.nascimento\Documents\Meus Projetos\TCC\relatorios\otimizacao_timesnet_20260922\auditoria.json`; SHA-256 `fa9778fc6fe4f76af2857a58f12a5af2495fe9033455100d38c239485ed1f352`. A evidencia mensal e identica nos dois relatorios parciais.

A divergencia historica declarada em otimizacao_timesnet_mensal.py permanece registrada na auditoria anterior; os artefatos mensais e suas entradas preservadas conferem.

## Proveniencia dos relatorios

- daily_30: `relatorios/otimizacao_timesnet_quatro_casos_20260922/auditoria_diaria/auditoria_resolucoes.json`; gerado em 2026-09-23T02:32:29.740852+00:00; SHA-256 `9b8a04b8078e2ab82c1340df57e48c044ccceaf8d3a03ff66f44c0d5ade8f63c`.
- hourly_72_extension: `relatorios/otimizacao_timesnet_quatro_casos_20260922/auditoria_horaria/auditoria_resolucoes.json`; gerado em 2026-09-23T02:40:15.785765+00:00; SHA-256 `d2715d178beee2e57553f5f9cdebe463594ad732679b0b6be62d618510df91ff`.

Os relatorios parciais, seus arquivos Markdown, hashes e horarios foram preservados. Os caminhos absolutos e hashes dos arquivos-fonte constam no JSON consolidado.

A busca foi motivada por resultados de 2024 ja observados: a avaliacao e retrospectiva e requer confirmacao futura. A tarefa horaria usa uma semente; a diaria usa cinco. As demais limitacoes originais estao preservadas no JSON.
