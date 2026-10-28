# Auditoria numérica do tópico 5 — 6 de setembro de 2026

As métricas publicadas são reproduzíveis a partir das previsões salvas. A revisão encontrou problemas na interpretação textual e no arredondamento de duas diferenças, sem encontrar erro no cálculo das métricas.

Foram recalculadas 725.700 linhas de previsões de validação e teste, 10.440 linhas de métricas por localidade e 1.044 linhas macro. O script independente concluiu 276 verificações, com zero falhas. Não importou o módulo experimental nem o gerador do artigo. A tolerância para MAE, RMSE, nRMSE e R² foi 1e-8; a maior diferença absoluta encontrada nessas métricas foi 3,55e-14.

Fonte canônica auditada: `resultados/avaliacao_multirresolucao_corrigida_v2/`. Derivados confrontados: `resultados/artigo_revista_unificado/artefatos_resultados_corrigidos_FINAL/` e cópias das tabelas do artigo existentes no momento da auditoria. Foram também verificados hashes dos contratos canônicos, dos manifestos, dos arquivos de previsões/métricas e dos 33 derivados. Os quatro hashes de contrato são hashes do conteúdo JSON canônico, excluindo o próprio campo `sha256_contrato`, e conferem; não devem ser comparados ao hash dos bytes do arquivo.

## Vencedores entre TimesNet e DilatedRNN

O critério é macro-MAE calculado separadamente em cada tarefa e horizonte cumulativo. Delta negativo favorece TimesNet; positivo favorece DilatedRNN. Os valores absolutos de resoluções diferentes não devem ser somados ou promediados para criar um vencedor global.

| Tarefa | Horizonte | Vencedor | Delta TimesNet − DilatedRNN (W/m²) | Locais TimesNet / DilatedRNN |
|---|---:|---|---:|---:|
| daily_30 | 1 | TimesNet | -0,074795 | 5 / 5 |
| daily_30 | 3 | TimesNet | -0,172237 | 5 / 5 |
| daily_30 | 7 | TimesNet | -0,127772 | 6 / 4 |
| daily_30 | 14 | TimesNet | -0,020002 | 6 / 4 |
| daily_30 | 30 | DilatedRNN | +0,225602 | 4 / 6 |
| hourly_72_extension | 24 | TimesNet | -1,346819 | 7 / 3 |
| hourly_72_extension | 48 | DilatedRNN | +0,015366 | 4 / 6 |
| hourly_72_extension | 72 | TimesNet | -0,478312 | 4 / 6 |
| monthly_1 | 1 | DilatedRNN | +0,886176 | 4 / 6 |
| monthly_6 | 1 | TimesNet | -0,027861 | 4 / 6 |
| monthly_6 | 3 | DilatedRNN | +0,163408 | 6 / 4 |
| monthly_6 | 6 | DilatedRNN | +0,089007 | 3 / 7 |

Nos quatro horizontes terminais, DilatedRNN vence em 30 dias, 1 mês e 6 meses; TimesNet vence em 72 horas. A contagem de três vitórias terminais favorece descritivamente DilatedRNN, mas não substitui uma função de custo operacional ou um critério global predefinido.

| Tarefa terminal | Sementes vencidas por TimesNet | Sementes vencidas por DilatedRNN |
|---|---|---|
| daily_30 (30) | 11, 89 | 23, 42, 67 |
| monthly_1 (1) | 42 | 11, 23, 67, 89 |
| monthly_6 (6) | 11 | 23, 42, 67, 89 |
| hourly_72_extension (72) | 42 | — |

## Correções textuais necessárias na versão recebida

- A afirmação de que XGBoost venceu todos os horizontes diários é incorreta: XGBoost vence em 1, 3 e 14 dias; LSTM vence em 7 dias (43,694639 W/m²); DilatedRNN vence em 30 dias (43,852006 W/m²). XGBoost efetivamente vence os três horizontes horários. A climatologia vence todas as comparações mensais.
- A vantagem horária de TimesNet em 24 horas é 1,346819 W/m², que arredonda para 1,35, não 1,34. A vantagem de DilatedRNN em 48 horas é 0,015366 W/m², que arredonda para 0,02, não 0,01. É necessário subtrair valores completos antes de arredondar.
- A média macro de 72 horas favorece TimesNet apesar de DilatedRNN vencer seis dos dez locais. No prefixo de três meses da tarefa de seis meses ocorre o inverso: a média favorece DilatedRNN, mas TimesNet vence seis locais. Contagem de vitórias e magnitude da melhora respondem a perguntas diferentes.
- As três tarefas diárias/mensais têm cinco sementes. No horizonte terminal, DilatedRNN vence 3/5 sementes no diário e 4/5 em cada tarefa mensal. O horário tem apenas a semente 42. Isso não constitui uma estimativa de variabilidade horária.
- Os leads horários exatos 24, 48 e 72 correspondem a alvos noturnos; todos os modelos têm MAE e RMSE zero, enquanto nRMSE e R² são indefinidos. As conclusões de desempenho horário devem usar o escopo cumulativo publicado.

## Casos e limites verificados

Os 28.070 contrastes por localidade, origem e horizonte foram recalculados. O maior ganho de TimesNet é GM Factory Zero, origem 31/03/2024, 24 horas: MAE 45,429023 contra 109,902271 W/m² (ganho 64,473248). O maior déficit é Tesla Gigafactory Texas, origem 28/03/2024, 24 horas: 150,016122 contra 73,915241 W/m² (déficit 76,100881). As anotações meteorológicas conferem com o CSV NASA POWER arquivado: ganho com 99,64% de nuvens e 0,80 mm de precipitação; déficit com 2,14% e 0,06 mm. O caso meteorológico independente também confere: Hyundai Metaplant Georgia, 05/08/2024, 82,66 mm e 99,47%.

Foram verificados também as chaves únicas das previsões, os dez locais, os anos de validação/teste, a sequência completa de leads, as contagens de origens contratuais, as previsões finitas/não negativas e a composição dos ensembles. Esta auditoria valida a consistência entre previsões, resultados e derivados; não representa um novo treinamento nem comprova que os dados meteorológicos de referência sejam medições locais de estação.

## Arquivos reproduzíveis

- `auditar_resultados.py`: auditor independente; executar a partir da raiz do repositório com Python, NumPy e pandas.
- `auditoria_numerica.json`: resultados das verificações e detalhes por tarefa.
- `comparacao_pareada_recalculada.csv`: todos os horizontes cumulativos e exatos, deltas e vitórias locais.
- `comparacao_por_semente.csv`: comparação por semente e horizonte.
- `variabilidade_recalculada.csv`: média, desvio-padrão amostral e extremos por semente.
- `vencedores_recalculados.csv`: melhor método do benchmark completo por horizonte cumulativo.


## Conferência final das tabelas revisadas

A auditoria foi repetida após a revisão de apresentação e concluiu 276 verificações, todas aprovadas. Na tabela `desempenho_macro.tex`, a validação confere equivalência numérica das 12 linhas cumulativas, as chaves de tarefa e horizonte, os cabeçalhos e a ordem dos sete modelos, todos os MAEs, valores NA e contagens de sementes. A comparação permite negritos, unidades no horizonte e mudanças de legenda ou ambiente LaTeX; nenhuma dessas mudanças dispensa a conferência dos números.

A tabela nova `vencedores_por_horizonte.tex` também foi confrontada diretamente com as métricas recalculadas das previsões. Suas 12 linhas conferem para MAE de TimesNet, MAE de DilatedRNN, delta obtido antes do arredondamento, identificação do vencedor e destaque em negrito do modelo correto. As diferenças de 24 e 48 horas aparecem corretamente como -1,35 e +0,02 W/m², respectivamente.
