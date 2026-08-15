# Avaliação mensal canônica

Esta pasta é a fonte numérica atual dos artigos IEEE e MCSM. Ela registra a
execução **completa**, concluída em 19 de julho de 2026, do protocolo global de
previsão de GHI média mensal. O estado oficial pode ser verificado em
`status_execucao.json`; os campos científicos ficam em `detalhes`:

```text
etapa: concluido
detalhes.protocolo_canonico: true
detalhes.fonte_artigos_atuais: true
detalhes.modelo_menor_macro_mae: Climatologia
```

Não edite CSVs, modelos, amostras ou JSONs manualmente. O
`manifesto_execucao.json` preserva versões, hardware e hashes SHA-256 dos
arquivos científicos usados. Uma reprodução deve ser gravada em outra pasta e
comparada a estes artefatos.

## Protocolo registrado

- Dez séries relacionadas da NSRDB, produto GOES Aggregated PSM v4.
- Médias diárias preservadas de 2019 a 2024, agregadas por mês civil.
- GHI média mensal em W/m², não energia nem geração fotovoltaica.
- Contexto de 12 meses; 48 alvos de treino em 2020--2023 e 12 origens de teste
  em 2024 por localidade.
- Horizonte de um mês, avaliação *walk-forward* retrospectiva e modelo fixo no
  teste.
- Min--max, saturação e quantização uniforme em 128 níveis ajustados sem usar
  os alvos de teste.
- Modelos aprendidos globais: XGBoost, MLP, RNN, LSTM, DilatedRNN, DeepAR e
  DeepNPTS.
- Referências: persistência, sazonal ingênuo e climatologia mensal.
- Sementes 11, 23, 42, 67 e 89 para cada modelo aprendido.
- DeepAR e DeepNPTS: 500 amostras por semente e origem, totalizando 2.500 na
  mistura final; a mediana da mistura fornece a previsão pontual.
- Critério principal: macro-MAE, média não ponderada dos MAEs das dez
  localidades.

## DeepNPTS avaliado

O modelo é o estimador discreto oficial `DeepNPTSEstimator` do GluonTS 0.16.2,
com treinamento global, distribuição sobre os valores do contexto e RPS
normalizado. Uma correção local registra a lista de embeddings categóricos como
`torch.nn.ModuleList`, garantindo otimização e persistência no `state_dict`.
Essa correção não altera a arquitetura, a função de avanço, a distribuição
discreta ou o RPS normalizado do estimador. O arquivo corrigido e seu hash aparecem no
manifesto como `codigo_fonte/redes_deepnpts_registradas.py`.

Esta execução substitui
`resultados/avaliacao_mensal_canonica_legado_sem_embeddings/`, na qual os
embeddings não eram registrados corretamente, e
`resultados/avaliacao_mensal_corrigida/`, que avaliava o VHP em vez do
DeepNPTS.

## Ranking final por macro-MAE

| Pos. | Modelo | MAE (W/m²) | RMSE (W/m²) | R² médio | nRMSE (%) |
|---:|---|---:|---:|---:|---:|
| 1 | Climatologia | 12,071 | 15,320 | 0,931 | 7,640 |
| 2 | LSTM | 12,222 | 15,057 | 0,919 | 7,393 |
| 3 | RNN | 12,554 | 15,591 | 0,910 | 7,701 |
| 4 | DilatedRNN | 13,422 | 16,198 | 0,898 | 7,930 |
| 5 | DeepAR | 14,182 | 17,936 | 0,892 | 8,779 |
| 6 | XGBoost | 14,573 | 17,930 | 0,892 | 8,778 |
| 7 | MLP | 16,059 | 19,769 | 0,875 | 9,697 |
| 8 | Sazonal ingênuo | 16,943 | 21,373 | 0,829 | 10,376 |
| 9 | DeepNPTS | 17,701 | 22,808 | 0,847 | 11,330 |
| 10 | Persistência | 35,088 | 42,167 | 0,576 | 20,887 |

O DeepNPTS apresentou desvio-padrão de 9,223 W/m² no MAE entre as cinco
sementes. Em relação à climatologia, sua diferença média pareada foi +5,630
W/m², com IC95% [3,762; 7,546] e `p=0,0176` após correção de Holm. O DeepNPTS
não obteve o menor MAE em nenhuma localidade.

Nas métricas probabilísticas, DeepAR e DeepNPTS obtiveram, respectivamente:

| Modelo | CRPS (W/m²) | PICP 90% (%) | MPIW (W/m²) |
|---|---:|---:|---:|
| DeepAR | 10,830 | 61,67 | 35,496 |
| DeepNPTS | 15,904 | 90,83 | 145,556 |

A cobertura do DeepNPTS próxima do nível nominal deve ser interpretada junto à
grande largura de seus intervalos.

## Conteúdo da pasta

| Arquivo ou diretório | Finalidade |
|---|---|
| `status_execucao.json` | estado final e menor macro-MAE |
| `configuracao_execucao.json` | sementes, épocas, lotes, contexto e quantização |
| `contrato_retomada.json` | contrato que impede retomada com código ou configuração divergente |
| `manifesto_execucao.json` | ambiente, hardware, metadados e hashes dos insumos |
| `auditoria_dados.csv` | cobertura, lacunas, duplicidades, sinais e metadados das séries |
| `hiperparametros_executados.csv` | complexidade efetiva por modelo e semente |
| `previsoes_por_modelo_seed.csv` | previsões individuais das cinco sementes |
| `previsoes_consolidadas.csv` | previsões finais usadas nas métricas |
| `metricas_por_localidade_seed.csv` | métricas pontuais por semente e localidade |
| `metricas_por_localidade.csv` | métricas pontuais consolidadas por localidade |
| `metricas_medias_modelos.csv` | ranking macro final |
| `intervalos_bootstrap_mae.csv` | IC95% bootstrap entre localidades |
| `comparacoes_mae_climatologia.csv` | diferenças pareadas, Wilcoxon e correção de Holm |
| `vencedores_por_localidade.csv` | menor MAE descritivo por localidade |
| `amostras_probabilisticas.npz` | amostras de DeepAR e DeepNPTS |
| `metricas_probabilisticas_*.csv` | CRPS, PICP e MPIW globais e locais |
| `modelos/` | modelos e metadados persistidos por arquitetura e semente |
| `figuras/` | PNGs e PDFs derivados da execução |

## Reprodução

Na raiz do repositório, após instalar `requirements.txt` e executar os testes,
use uma pasta de saída nova:

```bash
python executar_avaliacao_mensal_canonica.py \
  --confirmar-execucao-longa \
  --modo completa \
  --sementes 11,23,42,67,89 \
  --saida resultados/avaliacao_mensal_canonica_reproducao
```

Se uma rodada for interrompida, acrescente `--retomar` sem mudar código,
dependências, configuração ou arquivos de dados. O contrato rejeita uma
retomada incompatível. O modo `smoke` serve apenas para verificar o pipeline e
não produz evidência científica.

Regere as figuras oficiais com:

```bash
python gerar_figuras_avaliacao_canonica.py \
  --resultados resultados/avaliacao_mensal_canonica
```

Essas figuras mensais permanecem como artefatos desta execução. Os
manuscritos atuais mantêm apenas suas imagens efetivamente usadas em
`overlief/IEEE/figuras/` e `overlief/MCSM/figuras/`.

## Limitações obrigatórias na interpretação

- São apenas seis anos de dados, quatro ciclos anuais de alvos no treino e um
  ano de teste.
- A janela de 2024 foi inspecionada durante o desenvolvimento; a análise é
  retrospectiva e exploratória.
- Os dez pontos não são uma amostra aleatória de climas e podem ser
  espacialmente dependentes.
- A NSRDB fornece estimativas modeladas; as respostas horárias brutas e
  medições de solo nas fábricas não estão disponíveis neste repositório.
- A média mensal não representa extremos intradiários, irradiação mensal ou
  energia fotovoltaica produzida.
- Não foram incluídas variáveis meteorológicas exógenas.
- A variabilidade do DeepNPTS entre sementes foi alta; seu resultado não deve
  ser generalizado para outras bases ou configurações.
