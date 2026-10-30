# Otimização mensal da TimesNet

Revisão de 23/09/2026: a comparação principal usa somente a TimesNet com previsão direta do GHI. A variante residual que combina climatologia e TimesNet foi retirada do PDF principal, pois acrescentava um método que não fazia parte do pedido de ajustar hiperparâmetros.

## Resultados da TimesNet pura

Fonte: `resultados/busca_timesnet_mensal_20260920/`. Macro-MAE em W/m², no teste de 2024, média entre dez localidades.

| Configuração | 1 mês | Até 6 meses, cumulativo |
|---|---:|---:|
| TimesNet original | 13,8915 | 14,4582 |
| TimesNet otimizada | 13,8561 | 14,1975 |
| Climatologia, referência independente | 12,5747 | 13,0272 |

A redução de MAE da TimesNet é de 0,25% e 1,80%, respectivamente. Os ganhos são pequenos; a climatologia isolada continua melhor nessas duas tarefas e os dois MAEs da TimesNet permanecem acima de 13.

| Tarefa | Candidato | Perda | Dimensão | Taxa | Contexto |
|---|---|---|---:|---:|---|
| 1 mês | mae_dim16_lr_0003 | MAE | 16 | 0,0003 | 12 meses |
| 6 meses | huber | Huber | 8 | 0,001 | 12 meses |

Ambos usam um bloco, dropout 0,1 e lote 32. As épocas finais para as sementes 11, 23, 42, 67 e 89 são 64/45/60/65/94 (um mês) e 77/20/30/52/36 (seis meses).

## Busca e validação

A grade padrão de `codigo_fonte/experimentos/otimizacao_timesnet_mensal.py` contém apenas candidatos de alvo bruto. Compara perdas MSE, MAE e Huber (delta 0,1 na escala normalizada), taxas 0,001/0,0003, dimensões 8/16, um/dois blocos e janelas de 12/24/36 meses. O máximo é 300 épocas, com paciência de 30. No histórico disponível (2019–2024), a janela de 36 meses é descartada pelo mínimo de 18 origens de ajuste por localidade.

A seleção das épocas e do candidato usa macro-MAE físico em 2023. A configuração canônica escolhia épocas por MSE normalizado; essa mudança também integra a otimização, além dos hiperparâmetros. A classificação dos candidatos utiliza as previsões médias das cinco sementes, antes do piso zero, e não a média dos seus erros individuais. Essa média reúne treinamentos da mesma TimesNet; não combina a rede com climatologia.

A normalização min–max por localidade permanece ativa, ajustada somente antes do corte temporal de cada fase. A saída é contínua, sem quantização. Após congelar a seleção, o vencedor é reinicializado e treinado até 2023 pelas épocas selecionadas; só então se calcula o teste de 2024.

A auditoria de 23/09/2026 confere os rankings, caches de validação, escolhas de épocas e previsões, e reproduz os dez checkpoints mensais em CPU. Ela permite reutilizar os experimentos puros já existentes sem refazer o treinamento. Ver [auditoria_mensal_v1_pura.json](../resultados/relatorios/correcao_timesnet_pura_20260923/auditoria_mensal_v1_pura.json).

## Limites de interpretação

A janela de 24 meses reduz o número de exemplos de ajuste; variar a janela nesta grade não isola apenas o efeito do contexto. O histórico disponível não foi ampliado. A tarefa de seis meses tem sete origens de teste por localidade e alvos sobrepostos; a de um mês tem doze origens. Nenhuma representa uma previsão de cinco anos.

Como 2024 já havia sido examinado quando a otimização foi proposta, essa avaliação é retrospectiva. A confirmação precisa de outro período. Os resultados não comprovam superioridade sobre o artigo do Luís, que utiliza outros dados e histórico.

## Executar uma nova busca

Na raiz do projeto, usando o ambiente `.venv-baselines-gpu-20260912`:

```powershell
# Nova pasta: seleção somente em 2023.
python -m codigo_fonte.experimentos.otimizacao_timesnet_mensal --pasta-saida resultados/timesnet_pura_nova_busca

# Mesma configuração: refit e teste apenas do candidato congelado.
python -m codigo_fonte.experimentos.otimizacao_timesnet_mensal --pasta-saida resultados/timesnet_pura_nova_busca --avaliar-teste
```

O padrão contém somente a TimesNet pura. `--candidatos`, `--sementes`, `--max-epocas`, `--paciencia` e `--minimo-origens` delimitam a busca. `--pasta-csv` aceita histórico diário ampliado, e `--inicio-ajuste` define a primeira origem. Dados, código ou configuração diferentes exigem outra pasta: os contratos históricos e seus hashes devem ser preservados. O treinamento mensal usa CPU e uma thread.

Para contextos de 12/24 meses com as mesmas origens de treino, usar `--inicio-ajuste 2021-01-31`. Para manter origens a partir de janeiro de 2020, contextos de 24/36 meses exigem histórico desde janeiro de 2018/2017, respectivamente. Não foi feita nova coleta nesta revisão.

## Histórico da variante retirada

`resultados/busca_timesnet_mensal_v2_20260920` contém o experimento adicional com alvo de desvio da climatologia. Seus MAEs 13,2363 e 13,1671 pertencem a outro procedimento e não substituem os valores da TimesNet pura acima. Os artefatos e a auditoria antiga em `resultados/relatorios/otimizacao_timesnet_20260922` permanecem preservados para rastreabilidade. As rotinas que leem esses checkpoints continuam disponíveis, mas seus candidatos saíram da grade padrão e o gerador do PDF principal recusa essa busca híbrida.

A versão anterior desta documentação e do PDF está em `resultados/relatorios/correcao_timesnet_pura_20260923/antes_correcao/`. O [protocolo das quatro tarefas](OTIMIZACAO_TIMESNET_QUATRO_CASOS.md) reúne os resultados corrigidos.
