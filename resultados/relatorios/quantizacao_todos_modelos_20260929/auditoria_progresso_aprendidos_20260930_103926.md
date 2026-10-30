# Progresso dos modelos aprendidos

Observado de 2026-09-30T10:39:26.613415+00:00 a 2026-09-30T10:40:30.328721+00:00.

Leitura de arquivos e hashes; nenhum treino/replay iniciado. O retrato pode mudar enquanto os processos avan?am.

| Tarefa | Modelo | Sele??o ?ntegra | Variantes prontas | Caches de sementes | Refit |
|---|---|---:|---:|---:|---:|
| hourly_72_extension | XGBoost | True | 4/4 | 4/4 | 0/4 |
| hourly_72_extension | LSTM | False | 0/4 | 1/4 | 0/4 |
| hourly_72_extension | DilatedRNN | False | 0/4 | 1/4 | 0/4 |
| hourly_72_extension | GRU | False | 0/4 | 1/4 | 0/4 |
| hourly_72_extension | Transformer | False | 0/4 | 1/4 | 0/4 |
| hourly_72_extension | Informer | False | 0/4 | 1/4 | 0/4 |
| daily_30 | XGBoost | True | 4/4 | 20/20 | 0/4 |
| daily_30 | LSTM | True | 4/4 | 20/20 | 0/4 |
| daily_30 | DilatedRNN | False | 0/4 | 5/20 | 0/4 |
| daily_30 | GRU | True | 4/4 | 20/20 | 0/4 |
| daily_30 | Transformer | False | 0/4 | 5/20 | 0/4 |
| daily_30 | Informer | False | 0/4 | 5/20 | 0/4 |
| monthly_1 | XGBoost | True | 4/4 | 20/20 | 0/4 |
| monthly_1 | LSTM | True | 4/4 | 20/20 | 0/4 |
| monthly_1 | DilatedRNN | True | 4/4 | 20/20 | 0/4 |
| monthly_1 | GRU | True | 4/4 | 20/20 | 0/4 |
| monthly_1 | Transformer | True | 4/4 | 20/20 | 0/4 |
| monthly_1 | Informer | True | 4/4 | 20/20 | 0/4 |
| monthly_6 | XGBoost | True | 4/4 | 20/20 | 0/4 |
| monthly_6 | LSTM | True | 4/4 | 20/20 | 0/4 |
| monthly_6 | DilatedRNN | True | 4/4 | 20/20 | 0/4 |
| monthly_6 | GRU | True | 4/4 | 20/20 | 0/4 |
| monthly_6 | Transformer | True | 4/4 | 20/20 | 0/4 |
| monthly_6 | Informer | True | 4/4 | 20/20 | 0/4 |

## O que falta

- hourly_72_extension/LSTM: sem_quantizacao: 1/1 caches, agrega??o=False; q64: 0/1 caches, agrega??o=False; q128: 0/1 caches, agrega??o=False; q256: 0/1 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/hourly_72_extension/lstm/status.json`.
- hourly_72_extension/DilatedRNN: sem_quantizacao: 1/1 caches, agrega??o=False; q64: 0/1 caches, agrega??o=False; q128: 0/1 caches, agrega??o=False; q256: 0/1 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/hourly_72_extension/dilatedrnn/status.json`.
- hourly_72_extension/GRU: sem_quantizacao: 1/1 caches, agrega??o=False; q64: 0/1 caches, agrega??o=False; q128: 0/1 caches, agrega??o=False; q256: 0/1 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/hourly_72_extension/gru/status.json`.
- hourly_72_extension/Transformer: sem_quantizacao: 1/1 caches, agrega??o=False; q64: 0/1 caches, agrega??o=False; q128: 0/1 caches, agrega??o=False; q256: 0/1 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/hourly_72_extension/transformer/status.json`.
- hourly_72_extension/Informer: sem_quantizacao: 1/1 caches, agrega??o=False; q64: 0/1 caches, agrega??o=False; q128: 0/1 caches, agrega??o=False; q256: 0/1 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/hourly_72_extension/informer/status.json`.
- daily_30/DilatedRNN: sem_quantizacao: 5/5 caches, agrega??o=False; q64: 0/5 caches, agrega??o=False; q128: 0/5 caches, agrega??o=False; q256: 0/5 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=True. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/daily_30/dilatedrnn/status.json`.
- daily_30/Transformer: sem_quantizacao: 5/5 caches, agrega??o=False; q64: 0/5 caches, agrega??o=False; q128: 0/5 caches, agrega??o=False; q256: 0/5 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/daily_30/transformer/status.json`.
- daily_30/Informer: sem_quantizacao: 5/5 caches, agrega??o=False; q64: 0/5 caches, agrega??o=False; q128: 0/5 caches, agrega??o=False; q256: 0/5 caches, agrega??o=False. Controle aprovado=False; aceite GPU presente=False. Fonte: `resultados/quantizacao_todos_modelos_20260929/atual/daily_30/informer/status.json`.

Os refits dos modelos novos ainda dependem da conclus?o e congelamento das sele??es globais. Caches prontos n?o tornam uma variante pronta sem o controle e as tabelas agregadas.

## TimesNet importada

- hourly_72_extension: integridade=True; quatro variantes de valida??o e teste j? importadas. Fontes: `resultados/quantizacao_todos_modelos_20260929/atual/hourly_72_extension/timesnet/contrato.json` e `manifesto_artefatos.json`. Checkpoints n?o reexecutados.
- daily_30: integridade=True; quatro variantes de valida??o e teste j? importadas. Fontes: `resultados/quantizacao_todos_modelos_20260929/atual/daily_30/timesnet/contrato.json` e `manifesto_artefatos.json`. Checkpoints n?o reexecutados.
- monthly_1: integridade=True; quatro variantes de valida??o e teste j? importadas. Fontes: `resultados/quantizacao_todos_modelos_20260929/atual/monthly_1/timesnet/contrato.json` e `manifesto_artefatos.json`. Checkpoints n?o reexecutados.
- monthly_6: integridade=True; quatro variantes de valida??o e teste j? importadas. Fontes: `resultados/quantizacao_todos_modelos_20260929/atual/monthly_6/timesnet/contrato.json` e `manifesto_artefatos.json`. Checkpoints n?o reexecutados.

Evid?ncias completas, variantes, sementes e hashes em `auditoria_progresso_aprendidos_20260930_103926.json`.
