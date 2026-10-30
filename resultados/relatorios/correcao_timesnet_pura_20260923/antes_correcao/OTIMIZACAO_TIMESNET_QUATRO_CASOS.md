# TimesNet: otimização das quatro tarefas de GHI

A avaliação usa os mesmos locais, origens e alvos do benchmark de 2024. As previsões e tabelas canônicas foram preservadas. O PDF `tabela_resultados_ghi_2024.pdf` compara as configurações originais com as selecionadas nesta busca.

## Resultados de teste de 2024

MAE em W/m², no horizonte completo de cada tarefa; valores agregados entre dez localidades.

| Tarefa | TimesNet anterior | Variante selecionada | Redução do MAE |
|---|---:|---:|---:|
| Horário - 72 h | 52,48 | 47,91 | 8,70% |
| Diário - 30 dias | 44,08 | 42,17 | 4,33% |
| Mensal - 1 mês | 13,89 | 13,24 | 4,72% |
| Mensal - 6 meses | 14,46 | 13,17 | 8,93% |

A seleção prioriza MAE. No diário de 30 dias, a redução do MAE veio com aumento do RMSE, de 55,16 para 56,02 W/m², e do MSE, de 3143,38 para 3247,65 (W/m²)². Portanto, não houve melhora em todas as métricas.

Nos mensais, a variante selecionada combina climatologia e TimesNet. A climatologia isolada continua com menor MAE nos horizontes completos de um e seis meses.

Os dados sem arredondamento estão em [`comparacao_final.json`](../relatorios/otimizacao_timesnet_quatro_casos_20260922/comparacao_final.json). As métricas restantes e todos os horizontes cumulativos constam no PDF.

## Protocolo

| Tarefa | Contexto original | Horizonte direto | Sementes |
|---|---|---|---|
| Horária | 336 horas | 72 horas | 42 |
| Diária | 365 dias | 30 dias | 11, 23, 42, 67, 89 |
| Mensal | 12 meses | 1 mês | 11, 23, 42, 67, 89 |
| Mensal exploratória | 12 meses | 6 meses | 11, 23, 42, 67, 89 |

As entradas usam escala min–max por localidade, ajustada antes de 2023 na seleção e antes de 2024 no refit. A saída é contínua, sem quantização. A escolha de épocas e hiperparâmetros usa o macro-MAE físico da validação de 2023. Após congelar a escolha, cada rede é inicializada novamente com sua semente e treinada até 2023 pelo número de épocas escolhido. Só então são calculadas as métricas finais de 2024.

No horário e no diário, a grade contém perda MAE, perda Huber (delta 0,1 na escala normalizada), rede de dimensão 16 com taxa 0,0003 e contexto mais curto (168 horas ou 182 dias). Os outros candidatos usam dimensão 8 e taxa 0,001. O lote é 128, exceto na rede de dimensão 16, que usa 64 para caber na GPU. O teto é 30 épocas e a parada ocorre após cinco épocas sem melhora. A TimesNet original também é candidata, usando sua previsão de validação já salva. Dimensão, lote, contexto e taxa são registrados no contrato de cada execução.

A janela curta recorta somente a entrada e mantém os mesmos exemplos de treino e avaliação. O diário combina as previsões brutas das cinco sementes antes do pós-processamento. Aplica-se piso zero; no horário, também se usa a máscara de elevação solar do protocolo original. As observações noturnas continuam incluídas nas métricas.

As buscas mensais são as execuções `busca_timesnet_mensal_v2_20260920`, cujos artefatos e dez checkpoints foram auditados. Os vencedores usam climatologia mensal mais uma TimesNet que aprende a anomalia. Esse método recebe um rótulo próprio na tabela. Não se atribui toda a melhora apenas à capacidade da rede.

## Configurações selecionadas

| Tarefa | Perda | Contexto | Dimensão | Taxa de aprendizado | Lote |
|---|---|---|---|---|---|
| Horária | mae | 336 horas | 16 | 0.0003 | 64 |
| Diária | huber | 365 dias | 8 | 0.001 | 128 |

No horário, a época selecionada foi 30, igual ao limite operacional; o modelo pode não ter convergido. No diário, as épocas finais são 7, 6, 7, 7 e 7 para as sementes 11, 23, 42, 67 e 89, respectivamente.

As escolhas mensais e seus parâmetros estão documentados em [`OTIMIZACAO_TIMESNET_MENSAL.md`](OTIMIZACAO_TIMESNET_MENSAL.md).

## Leitura dos resultados

Cada métrica é calculada por localidade e depois agregada pela média dos dez locais. MSE e RMSE são agregados separadamente. Os horizontes intermediários são cumulativos; a seleção considera o horizonte completo, portanto não garante melhora em cada subtabela.

Na tarefa mensal de seis meses, há sete origens de teste por localidade, com alvos sobrepostos. Essa tarefa não equivale a prever cinco anos. A tarefa mensal de um mês usa outro conjunto de origens e não é intercambiável com o primeiro passo da tarefa de seis meses.

A busca foi motivada por resultados de 2024 já observados. Embora a seleção interna use 2023, a avaliação de 2024 é retrospectiva e precisa de confirmação em outro período. O mesmo ano seleciona épocas e hiperparâmetros; não há avaliação da variação entre anos nem teste de significância que trate as janelas como independentes.

## Reprodução

Executar na raiz do repositório com o ambiente `.venv-baselines-gpu-20260912`:

```powershell
python -m codigo_fonte.otimizacao_timesnet_resolucoes --tarefa hourly_72_extension --dispositivo cuda
python -m codigo_fonte.otimizacao_timesnet_resolucoes --tarefa daily_30 --dispositivo cuda
python scripts/auditar_timesnet_resolucoes.py --saida relatorios/otimizacao_timesnet_quatro_casos_20260922 --reproduzir-modelos
python -m scripts.gerar_tabela_resultados_ghi_otimizada --somente-validar
```

As buscas novas ficam em `resultados/busca_timesnet_resolucoes_20260922`. Os checkpoints preservam escalas, semente, épocas, arquitetura, dispositivo e lote de inferência. Na TimesNet, a escolha de frequências depende do lote; mantenha o dispositivo, o tamanho e a ordem dos lotes para reproduzir as previsões salvas.

A pasta `relatorios/otimizacao_timesnet_quatro_casos_20260922` registra o ambiente e a cópia anterior do PDF. A pasta `relatorios/tabela_resultados_ghi_20260922` reúne a tabela sem arredondamento e os hashes usados na geração. A auditoria mensal anterior está em `relatorios/otimizacao_timesnet_20260922`.