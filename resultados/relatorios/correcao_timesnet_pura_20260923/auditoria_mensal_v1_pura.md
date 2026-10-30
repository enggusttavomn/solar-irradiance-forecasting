# Auditoria da TimesNet mensal pura (V1)

Sem novo treinamento. Dez checkpoints reproduzidos em CPU. A inferencia e a reconstrucao do ranking foram executadas com as funcoes de climatologia residual bloqueadas.

| Tarefa | Validacao original | Validacao otimizada | Teste original | Teste otimizado | Reducao teste |
|---|---:|---:|---:|---:|---:|
| monthly_1 | 15.890690 | 15.436941 | 13.891528 | 13.856143 | 0.25% |
| monthly_6 | 17.272139 | 17.053964 | 14.458230 | 14.197473 | 1.80% |

MAE macro em W/m2; menor e melhor. O conjunto de teste e 2024. Ambos os vencedores tambem superam a TimesNet original em 2023, criterio de selecao.

## monthly_1

Vencedor: `mae_dim16_lr_0003`; alvo GHI bruto; contexto 12; perda mae; taxa 0.0003; d_model=16, d_ff=32, blocos=1, dropout=0.1.

Conferidos 119 hashes/tamanhos, 10 entradas, oito candidatos e quarenta caches/historicos de selecao. As epocas salvas correspondem aos minimos de MAE de 2023; o ranking e o vencedor foram recalculados. Contexto 36 foi descartado por insuficiencia de origens de ajuste.

| Semente | Epocas refit | MAE teste | Erro maximo checkpoint/NPZ |
|---:|---:|---:|---:|
| 11 | 64 | 14.309490 | 0 |
| 23 | 45 | 16.052050 | 0 |
| 42 | 60 | 14.874740 | 0 |
| 67 | 65 | 14.662376 | 0 |
| 89 | 94 | 13.777333 | 0 |

A previsao e a inversao min-max da saida TimesNet; as cinco sementes sao promediadas e aplica-se somente piso zero. Climatologia aparece nos CSVs como comparador independente, sem compor essas previsoes.

## monthly_6

Vencedor: `huber`; alvo GHI bruto; contexto 12; perda huber; taxa 0.001; d_model=8, d_ff=16, blocos=1, dropout=0.1.

Conferidos 119 hashes/tamanhos, 10 entradas, oito candidatos e quarenta caches/historicos de selecao. As epocas salvas correspondem aos minimos de MAE de 2023; o ranking e o vencedor foram recalculados. Contexto 36 foi descartado por insuficiencia de origens de ajuste.

| Semente | Epocas refit | MAE teste | Erro maximo checkpoint/NPZ |
|---:|---:|---:|---:|
| 11 | 77 | 13.457487 | 0 |
| 23 | 20 | 15.323471 | 0 |
| 42 | 30 | 16.071247 | 0 |
| 67 | 52 | 14.678077 | 0 |
| 89 | 36 | 14.843083 | 0 |

A previsao e a inversao min-max da saida TimesNet; as cinco sementes sao promediadas e aplica-se somente piso zero. Climatologia aparece nos CSVs como comparador independente, sem compor essas previsoes.

## Limites

Os hashes atuais de modulos alterados podem divergir dos contratos historicos. A reproducao verifica pesos, entradas, escalas e saidas; nao reconstrui o treinamento nem comprova independentemente a ordem temporal original das gravacoes.

Checkpoints antigos nao incluem escalas; a reproducao depende das entradas originais verificadas por hash.

Os contratos de execucao canonicos divergem de seus manifestos historicos; a auditoria registra os hashes esperados e atuais. Previsoes e checkpoints canonicos permanecem conformes aos hashes dos manifestos. Nenhuma fonte foi alterada.

A TimesNet original selecionava epocas por MSE normalizado; a busca seleciona por macro-MAE fisico. Portanto o ganho inclui essa mudanca no criterio de selecao de epocas, alem dos hiperparametros e da perda de treino; nao e uma ablacao isolada.

A busca foi motivada por resultados de 2024 ja vistos; portanto o teste nao constitui confirmacao externa inteiramente inedita. Epocas e hiperparametros compartilham 2023; ha risco de sobreajuste. Os seis passos mensais usam sete origens sobrepostas por localidade. Os ganhos sao descritivos, sem alegacao de significancia.

Fontes historicas foram somente lidas. Nenhum checkpoint, contrato, manifesto, CSV ou cache original foi alterado.
