# TCC — previsão mensal de GHI em dez localidades

Este repositório avalia a previsão da média mensal de Irradiância Global
Horizontal (GHI) em dez localidades associadas a fábricas de veículos
elétricos. A fonte numérica atual dos artigos é exclusivamente:

```text
resultados/avaliacao_mensal_canonica/
```

## Mapa de pastas

```text
dados/          dados brutos e processados
codigo_fonte/   coleta, preparacao, modelos, experimento e visualizacao
scripts/        comandos curtos para executar as etapas
resultados/     saidas oficiais e registros legados
artigos/        indice para manuscritos, templates e figuras
site/           panorama web e tabelas interativas
documentacao/   guias e orientacoes de escrita
testes/         verificacoes automatizadas
```

Para entender cada modelo individualmente, comece em
`codigo_fonte/modelos/README.md`. Para navegar visualmente por todo o projeto,
gere `site/index.html` com `python site/gerar_site.py`.

Os modulos historicos mantidos diretamente em `codigo_fonte/` e alguns
executaveis da raiz fazem parte do manifesto da execucao canonica. Eles foram
preservados para que a reorganizacao nao invalide a rastreabilidade dos
resultados publicados.

O status registrado em `status_execucao.json` é `concluido`. A pasta contém a
execução completa, os modelos persistidos, as previsões por semente, as
amostras probabilísticas, as métricas consolidadas, o manifesto do ambiente e
os hashes SHA-256 dos arquivos usados.

`resultados/avaliacao_mensal_corrigida/` documenta a rodada anterior baseada
em Vizinhos Históricos Ponderados (VHP). Ela permanece no repositório apenas
como **legado metodológico** e não deve fornecer números, tabelas, figuras ou
conclusões aos manuscritos atuais.

## Escopo e protocolo canônico

Os resultados constituem uma avaliação retrospectiva e exploratória, não uma
previsão operacional. Em cada origem de 2024, o sistema prevê somente o mês
seguinte, usando o histórico disponível até então e sem reajustar os modelos.
Assim, não se trata de uma previsão recursiva dos doze meses de 2024 emitida em
dezembro de 2023.

| Item | Configuração registrada |
|---|---|
| Fonte | NLR/NSRDB, produto modelado GOES Aggregated PSM v4 |
| Localidades | 10 séries relacionadas |
| Dados preservados | médias diárias de GHI, 2.192 dias por localidade, de 2019 a 2024 |
| Alvo | média mensal de GHI em W/m²; não é energia nem geração fotovoltaica |
| Contexto | 12 meses; 2019 fornece o histórico inicial |
| Treino final | 48 alvos por localidade, de jan./2020 a dez./2023 |
| Teste | 12 origens por localidade, de jan. a dez./2024 |
| Horizonte | um mês, em esquema *walk-forward*, com parâmetros fixos no teste |
| Transformação | min–max por localidade, saturação e quantização uniforme em 128 níveis, ajustados sem usar alvos de teste |
| Modelos aprendidos | XGBoost, MLP, RNN, LSTM, DilatedRNN, DeepAR e DeepNPTS |
| Referências | persistência, sazonal ingênuo e climatologia mensal |
| Ajuste | um modelo global por arquitetura e semente, compartilhado pelas dez séries |
| Sementes | 11, 23, 42, 67 e 89 para os sete modelos aprendidos |
| Probabilidade | 500 amostras por semente e origem para DeepAR e DeepNPTS; 2.500 valores na mistura final |
| Métrica pontual principal | macro-MAE: média não ponderada dos MAEs das dez localidades |
| Métricas probabilísticas | CRPS, PICP de 90% e MPIW |

Na seleção interna, transformações e complexidade são determinadas sem usar
2024. Quando aplicável, o modelo é reinicializado e reajustado em todo o
período pré-teste após essa seleção. As previsões pontuais dos modelos
aprendidos são consolidadas entre as cinco sementes; em DeepAR e DeepNPTS, as
amostras das sementes são reunidas e a mediana da mistura é usada como previsão
pontual.

Os CSVs diários preservados derivam de estimativas modeladas da NSRDB, e não de
sensores instalados nas fábricas. A consulta de origem possui intervalo de 60
minutos, mas as respostas horárias brutas não foram preservadas. Os pontos das
fábricas são apenas referências geográficas; não há dados de carga, produção,
geração fotovoltaica ou processo industrial.

## Implementação do DeepNPTS

O experimento usa o estimador **DeepNPTS discreto do GluonTS 0.16.2**, treinado
globalmente nas dez séries e com o RPS normalizado da implementação oficial. Ele não
é o antigo VHP e não pondera vizinhos por uma fórmula manual de similaridade e
recência.

Foi necessária uma correção local, restrita ao registro dos embeddings
categóricos no PyTorch. A lista já criada pelo estimador é registrada como
`torch.nn.ModuleList`, para que seus parâmetros sejam otimizados, incluídos no
`state_dict` e restaurados ao recarregar o preditor. A correção não modifica a
arquitetura do DeepNPTS, sua função de avanço, sua distribuição discreta ou o
RPS normalizado. A implementação está em
`codigo_fonte/redes_deepnpts_registradas.py`, e o manifesto inclui seu hash.

A quantização em 128 níveis é uma decisão do protocolo deste projeto, não um
requisito geral do DeepNPTS.

## Ranking final

Médias das métricas pontuais nas dez localidades, calculadas diretamente de
`resultados/avaliacao_mensal_canonica/metricas_medias_modelos.csv`:

| Pos. | Modelo | MAE (W/m²) | RMSE (W/m²) | R² médio | nRMSE (%) | DP do MAE entre sementes |
|---:|---|---:|---:|---:|---:|---:|
| 1 | Climatologia | 12,071 | 15,320 | 0,931 | 7,640 | 0,000 |
| 2 | LSTM | 12,222 | 15,057 | 0,919 | 7,393 | 0,203 |
| 3 | RNN | 12,554 | 15,591 | 0,910 | 7,701 | 0,493 |
| 4 | DilatedRNN | 13,422 | 16,198 | 0,898 | 7,930 | 0,831 |
| 5 | DeepAR | 14,182 | 17,936 | 0,892 | 8,779 | 0,900 |
| 6 | XGBoost | 14,573 | 17,930 | 0,892 | 8,778 | 0,136 |
| 7 | MLP | 16,059 | 19,769 | 0,875 | 9,697 | 0,456 |
| 8 | Sazonal ingênuo | 16,943 | 21,373 | 0,829 | 10,376 | 0,000 |
| 9 | DeepNPTS | 17,701 | 22,808 | 0,847 | 11,330 | 9,223 |
| 10 | Persistência | 35,088 | 42,167 | 0,576 | 20,887 | 0,000 |

A climatologia apresentou o menor macro-MAE. A diferença média do DeepNPTS em
relação a ela foi de +5,630 W/m²; o IC95% pareado foi [3,762; 7,546] W/m² e o
valor de Wilcoxon após correção de Holm foi 0,0176. Valores positivos nessa
comparação favorecem a climatologia. O desvio de 9,223 W/m² entre sementes do
DeepNPTS também evidencia instabilidade relevante nesta amostra curta. Esses
resultados caracterizam a configuração e o recorte avaliados, e não uma
inferioridade universal da arquitetura.

Nos modelos probabilísticos, o DeepAR obteve CRPS médio de 10,830 W/m², PICP
de 61,67% e MPIW de 35,496 W/m². O DeepNPTS obteve CRPS de 15,904 W/m², PICP
de 90,83% e MPIW de 145,556 W/m². A cobertura próxima de 90% do DeepNPTS veio,
portanto, acompanhada de intervalos muito mais largos.

Por menor MAE local, a climatologia venceu em BMW San Luis Potosí, BYD
Camaçari e Hyundai Georgia; a LSTM em Ford Rouge, GM Factory Zero, Rivian
Normal e Tesla Nevada; o sazonal ingênuo em Lucid Casa Grande; a RNN em Tesla
Fremont; e o DeepAR em Tesla Texas. O DeepNPTS não venceu nenhuma das dez
localidades.

## Reprodução

Foi usado CPython 3.12.1. As versões completas estão em `requirements.txt` e
no `manifesto_execucao.json`. Crie o ambiente e valide a suíte antes da rodada
longa:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest -q
```

Reproduza a execução completa em uma pasta nova:

```bash
python executar_avaliacao_mensal_canonica.py \
  --confirmar-execucao-longa \
  --modo completa \
  --sementes 11,23,42,67,89 \
  --saida resultados/avaliacao_mensal_canonica_reproducao
```

Uma execução interrompida pode ser retomada apenas se o contrato de hashes e a
configuração forem idênticos:

```bash
python executar_avaliacao_mensal_canonica.py \
  --confirmar-execucao-longa \
  --modo completa \
  --sementes 11,23,42,67,89 \
  --saida resultados/avaliacao_mensal_canonica_reproducao \
  --retomar
```

Não use o modo `smoke` como evidência científica. Ele verifica somente o fluxo
de execução.

Gere novamente as figuras a partir dos CSVs e das amostras canônicas:

```bash
python gerar_figuras_avaliacao_canonica.py \
  --resultados resultados/avaliacao_mensal_canonica
cp resultados/avaliacao_mensal_canonica/figuras/previsao_mensal_byd_camacari.png overlief/figuras/
cp resultados/avaliacao_mensal_canonica/figuras/intervalo_deepnpts_byd_camacari.png overlief/figuras/
```

Os artigos são preenchidos diretamente a partir dos artefatos finais por
`preencher_artigos_canonicos.py`; números não devem ser transcritos de pastas
legadas.

## Artefatos de auditoria

| Caminho | Conteúdo |
|---|---|
| `resultados/avaliacao_mensal_canonica/status_execucao.json` | conclusão e modelo de menor macro-MAE |
| `resultados/avaliacao_mensal_canonica/configuracao_execucao.json` | sementes e hiperparâmetros globais da rodada |
| `resultados/avaliacao_mensal_canonica/manifesto_execucao.json` | ambiente, hardware, hashes e metadados do protocolo |
| `resultados/avaliacao_mensal_canonica/auditoria_dados.csv` | cobertura e integridade das dez séries |
| `resultados/avaliacao_mensal_canonica/metricas_medias_modelos.csv` | ranking e métricas pontuais macro |
| `resultados/avaliacao_mensal_canonica/metricas_por_localidade.csv` | métricas consolidadas por localidade |
| `resultados/avaliacao_mensal_canonica/metricas_por_localidade_seed.csv` | variabilidade por semente |
| `resultados/avaliacao_mensal_canonica/comparacoes_mae_climatologia.csv` | diferenças pareadas, bootstrap, Wilcoxon e Holm |
| `resultados/avaliacao_mensal_canonica/metricas_probabilisticas_*.csv` | CRPS e propriedades dos intervalos |
| `resultados/avaliacao_mensal_canonica/amostras_probabilisticas.npz` | amostras de DeepAR e DeepNPTS |
| `resultados/avaliacao_mensal_canonica/modelos/` | modelos e metadados persistidos por arquitetura e semente |

## Limitações

- O histórico cobre somente seis anos, com quatro ciclos anuais entre os 48
  alvos de treinamento de cada localidade.
- O teste contém apenas 12 meses e a janela de 2024 já havia sido observada
  durante o desenvolvimento; a análise não é confirmação prospectiva.
- As dez localidades não constituem amostra aleatória de todos os climas e
  podem apresentar dependência espacial.
- A NSRDB é uma referência modelada; não há medições de solo nas fábricas nem
  respostas horárias brutas preservadas no repositório.
- Não foram usadas variáveis meteorológicas exógenas, e a média mensal oculta
  extremos e variabilidade intradiária.
- O DeepNPTS apresentou forte variabilidade entre sementes neste protocolo;
  cinco sementes não eliminam a incerteza associada ao histórico curto.
- A busca de hiperparâmetros foi limitada para reduzir o risco de ajuste à
  pequena janela disponível.

## Estado dos fluxos anteriores

As pastas abaixo são preservadas para rastreabilidade, mas não são fontes dos
artigos atuais:

- `resultados/avaliacao_mensal_corrigida/`: protocolo anterior com VHP, alvo
  contínuo e três sementes;
- `resultados/avaliacao_mensal_canonica_legado_sem_embeddings/`: primeira
  execução do protocolo global em que os embeddings categóricos do DeepNPTS
  não eram registrados corretamente pelo PyTorch;
- `resultados/todas_localidades/`, `resultados/todas_localidades_mensal/` e
  `resultados/experimentos_redes_avancadas/`: fluxos exploratórios anteriores;
- figuras com sufixo `_ieee.png` em `overlief/figuras/`: exportações da rodada
  VHP, incompatíveis com os números canônicos atuais.

O material atual dos manuscritos está em `overlief/IEEE/` e `overlief/MCSM/`.
Antes de atualizar tabelas ou conclusões, confirme `status_execucao.json`, o
manifesto, os testes e os CSVs da pasta canônica.
