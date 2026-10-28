# Auditoria da otimizacao mensal da TimesNet

As previsoes historicas foram recalculadas a partir dos CSVs e reproduzidas pela recarga dos dez checkpoints, sem novo treinamento. Fontes historicas foram somente lidas.

| Horizonte | MAE anterior | MAE otimizado | Reducao | Climatologia |
|---|---:|---:|---:|---:|
| monthly_1 | 13.891528 | 13.236257 | 4.72% | 12.574705 |
| monthly_6 | 14.458230 | 13.167132 | 8.93% | 13.027174 |

MAE em W/m2: media dos erros absolutos de cada localidade, seguida de media entre dez localidades. O horizonte de seis meses agrega os seis passos de cada uma das sete origens por localidade; nao e previsao de cinco anos.

## monthly_1

Vencedor por validacao: `anomalia_mae_lr_0003`. Contexto 12 meses; alvo anomalia em relacao a climatologia mensal pre-corte; perda mae; taxa 0.0003; d_model=8; d_ff=16; blocos=1.

Validacao: TimesNet 14.711143; climatologia 13.761380 W/m2. A climatologia ainda e melhor na validacao e no teste.

Foram conferidos 167 hashes/tamanhos de artefatos e 10 hashes de entradas. 12 candidatos foram avaliados com cinco sementes; contexto 36 foi descartado por falta de origens de treino.

| Semente | Epocas refit | MAE teste | Erro maximo checkpoint vs NPZ |
|---:|---:|---:|---:|
| 11 | 3 | 13.676042 | 0 |
| 23 | 25 | 13.041721 | 0 |
| 42 | 7 | 13.424115 | 0 |
| 67 | 5 | 13.182372 | 0 |
| 89 | 23 | 13.383500 | 0 |

Os checkpoints historicos nao incorporam escalas/climatologia. A recarga auditada reconstruiu essas transformacoes exclusivamente dos insumos originais anteriores a 2024 e reproduziu previsoes NPZ/CSV. O pipeline atual passou a persistir preprocessamento nos novos checkpoints; os historicos nao foram regravados.

## monthly_6

Vencedor por validacao: `anomalia_mae_dim16`. Contexto 12 meses; alvo anomalia em relacao a climatologia mensal pre-corte; perda mae; taxa 0.001; d_model=16; d_ff=32; blocos=1.

Validacao: TimesNet 15.685734; climatologia 14.926675 W/m2. A climatologia ainda e melhor na validacao e no teste.

Foram conferidos 167 hashes/tamanhos de artefatos e 10 hashes de entradas. 12 candidatos foram avaliados com cinco sementes; contexto 36 foi descartado por falta de origens de treino.

| Semente | Epocas refit | MAE teste | Erro maximo checkpoint vs NPZ |
|---:|---:|---:|---:|
| 11 | 1 | 13.114947 | 0 |
| 23 | 1 | 13.256693 | 0 |
| 42 | 3 | 13.330528 | 0 |
| 67 | 2 | 13.261856 | 0 |
| 89 | 1 | 13.186441 | 0 |

Os checkpoints historicos nao incorporam escalas/climatologia. A recarga auditada reconstruiu essas transformacoes exclusivamente dos insumos originais anteriores a 2024 e reproduziu previsoes NPZ/CSV. O pipeline atual passou a persistir preprocessamento nos novos checkpoints; os historicos nao foram regravados.

## Proveniencia e limites

A auditoria inicial desta sessao confirmou igualdade dos quatro hashes de codigo com os contratos historicos, antes das correcoes posteriores de persistencia e retomada. `auditoria_inicial_sha256.json` registra essa observacao; `auditoria.json` registra separadamente os hashes atuais, que podem diferir apos as correcoes.

A variante vencedora e um pipeline residual (climatologia + TimesNet da anomalia), nao uma melhora atribuivel somente aos hiperparametros da TimesNet bruta. A arquitetura canonica nao foi substituida.

A busca foi motivada por resultados de 2024 ja observados. A selecao interna usou 2023 e congelou o vencedor antes de avaliar 2024, mas 2024 nao pode ser apresentado como confirmacao externa inteiramente inedita. Requer avaliacao futura ou outro periodo independente.

O mesmo ano seleciona epocas e hiperparametros; ha risco de sobreajuste da validacao. As origens de seis meses se sobrepoem. Os resultados sao descritivos, sem teste de significancia que trate janelas como independentes. Janelas maiores tambem mudam a quantidade de treino. O historico nao foi ampliado nesta busca.

Reexecutar: `.\.venv-baselines-gpu-20260912\Scripts\python.exe scripts/auditar_busca_timesnet_mensal.py --fonte resultados/busca_timesnet_mensal_v2_20260920 --saida relatorios/otimizacao_timesnet_20260922`
