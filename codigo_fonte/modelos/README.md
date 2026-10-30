# Modelos de previsão

Os modelos ficam juntos nesta área. As famílias organizam as implementações
e suas funções de construção, treinamento e previsão.

| Pasta ou arquivo | Conteúdo |
|---|---|
| [`referencias_simples/`](referencias_simples/) | persistência, sazonal ingênuo, climatologia e suporte aos modelos estatísticos |
| [`tabulares/`](tabulares/) | XGBoost e MLP |
| [`recorrentes/`](recorrentes/) | RNN, LSTM e DilatedRNN |
| [`probabilisticos/`](probabilisticos/) | DeepAR e DeepNPTS |
| [`timesnet_horario.py`](timesnet_horario.py) | componentes e arquitetura TimesNet |
| [`modelos_baselines_adicionais.py`](modelos_baselines_adicionais.py) | modelos de referência adicionais |

As funções públicas por modelo reutilizam as implementações da própria
família. Os experimentos que coordenam treinamento e avaliação ficam em
[`../experimentos/`](../experimentos/); os modelos treinados e as métricas
produzidas ficam em [`../../resultados/`](../../resultados/).

O código anterior à reorganização está preservado no
[arquivo de fontes originais](../../documentacao/organizacao/fontes_antes_reorganizacao_20261027.zip),
identificado pelo registro de migração para conferir auditorias históricas.
