# Experimentos avançados — legado, não publicável

> **Não use nenhum arquivo desta pasta no TCC, em artigo, congresso, resumo,
> apresentação ou comparação principal.** A única fonte numérica publicável
> atual é `resultados/avaliacao_mensal_corrigida/`.

Esta pasta preserva uma rodada exploratória executada em 2026-06-29. Ela foi
produzida antes da correção integrada do alvo contínuo, das 12 defasagens, das
baselines, das sementes e da inferência estatística. Seus resultados não são
metodologicamente intercambiáveis com a avaliação mensal corrigida.

Os arquivos históricos usam os rótulos:

- `DilatedRNN`: rede recorrente multiescala experimental;
- `DeepAR_exp`: aproximação local com LSTM e perda Gaussiana, não o DeepAR
  canônico;
- `DeepNPTS_aprox`: rótulo histórico incorreto para um suavizador por vizinhos
  ponderados. Ele **não implementa DeepNPTS** e deve ser lido como
  `VizinhosHistoricos_aprox`.

Os CSVs existentes não foram renomeados nem recalculados para preservar a
trilha histórica. As antigas tabelas
`comparacao_com_modelos_oficiais.csv` também são legado: elas liam pastas do
pipeline anterior e não constituem comparação válida com os resultados
corrigidos.

O script `experimentos_redes_avancadas.py` agora:

- bloqueia a execução sem `--aceitar-experimento-legado`;
- usa o nome `VizinhosHistoricos_aprox` para novas saídas;
- não cria comparação diária rotulada como oficial;
- quando solicitado no mensal, lê somente
  `resultados/avaliacao_mensal_corrigida/metricas_geral.csv` e rotula a junção
  como diagnóstica.

Mesmo uma nova execução continua proibida como fonte de publicação. A flag
serve apenas para evitar execução acidental:

```bash
python experimentos_redes_avancadas.py \
  --aceitar-experimento-legado \
  --frequencia mensal
```

DeepAR e DeepNPTS canônicos do GluonTS pertencem ao pipeline global opcional
`executar_avaliacao_mensal_canonica.py`. Esse pipeline ainda não possui uma
execução completa validada para publicação; saídas de smoke test não devem ser
citadas.

Para análise, reprodução e redação atuais, use:

```text
resultados/avaliacao_mensal_corrigida/
cadernos_jupyter/04_avaliacao_mensal_corrigida.ipynb
```
