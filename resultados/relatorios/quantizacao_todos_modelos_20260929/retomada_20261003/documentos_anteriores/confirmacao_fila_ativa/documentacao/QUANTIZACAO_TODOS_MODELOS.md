# Quantizacao de todos os modelos e ampliacao do historico

## Escopo autorizado em 29/09/2026

O usuario aprovou completar os quatro casos (horario, diario, mensal de um mes e mensal exploratorio de seis meses) com os concorrentes da TimesNet. Em cada caso serao apresentados controles sem quantizacao e variantes de 64, 128 e 256 niveis, mantendo min-max. As tabelas terao todos os modelos agrupados por nivel, com metricas fisicas e deltas contra seus respectivos controles.

Primeiro sera concluida a base 2019-2024, com validacao em 2023 e teste em 2024. Depois sera preparado o periodo 1998-2022 nas mesmas dez localidades, sujeito a cobertura e compatibilidade verificadas. A comparacao entre historicos curto e longo tera as mesmas datas de teste. Os resultados antigos permanecem preservados.

## Situacao

Atualizacao de 03/10, 10h59 local: base atual completa e auditada, 44/44 selecoes e 44/44 refits, com PDF de 34 paginas entregue e integro. As reinicializacoes de 02/10 interromperam a sequencia historica. A auditoria de integridade confirmou 7/44 selecoes congeladas e 97 caches finais integros do historico longo; seus refits e o historico curto pareado ainda estao pendentes. Somente o coordenador historico foi retomado: na observacao inicial, estava verificando os 70 arquivos de origem, sem confirmacao ainda de treinos ativos. Os oito checkpoints parciais do ARIMA horario q256 foram preservados; essa variante sera repetida pelo motor original. Conclusao geral e PDF historico permanecem pendentes.

Evidencias desta retomada: [auditoria dos caches finais](../relatorios/quantizacao_todos_modelos_20260929/retomada_20261003/auditoria_caches_readonly_20261003T135303Z.json), [checkpoints parciais](../relatorios/quantizacao_todos_modelos_20260929/retomada_20261003/auditoria_caches_parciais_readonly_20261003T135445Z.json) e [registro de continuidade](../relatorios/quantizacao_todos_modelos_20260929/CONTINUACAO.md). Os registros datados anteriores permanecem abaixo.

Atualizacao de 02/10, 05h19: base atual concluida, 44/44 selecoes e 44/44 refits. Auditoria completa com replay aprovada, 44 pares e 1.056 linhas de metricas. PDF 2024 entregue com 34 paginas apos revisao visual de todas elas; recibo em pdf_atual/entrega.json. Historico longo ativo: 6/44 selecoes e 0/44 refits; curto pareado: 0/44 selecoes e 0/44 refits. PDF historico e conclusao geral pendentes. Nao abrir filas duplicadas; ver CONTINUACAO.md.

Na base atual, os treinamentos completos das redes, XGBoost e referencias estatisticas foram concluidos e auditados. Os treinamentos historicos continuam em andamento. A TimesNet atual foi importada dos quatro experimentos completos e auditados, sem repetir o treino. A compactacao dos checkpoints ARIMA preservou bit a bit 365.874 previsoes em 89 arquivos testados. A coleta e a auditoria independente da base de 1998-2022 estao concluidas: 2.191.440 registros horarios, 91.310 diarios e 3.000 mensais. Os 32 contextos historicos foram verificados: os dois historicos e os modelos usam as mesmas observacoes de validacao e teste. Os resultados completos da base atual e seu PDF foram entregues; os resultados historicos ainda nao foram concluidos.

Em 30/09, a fila foi retomada dos caches apos uma falha transitoria do Windows ao gravar o arquivo de progresso. A gravacao agora repete bloqueios transitorios por ate dez segundos e preserva o arquivo anterior em caso de falha; 11 testes de regressao passaram. Nenhum hiperparametro foi alterado nessa correcao. As 16 selecoes dos modelos estatisticos foram concluidas, incluindo ARIMA horario com 256 niveis; refits e auditoria final permanecem pendentes.

Transformer e Informer horarios e diarios apresentaram variacao entre retreinamentos CUDA. Os 36 checkpoints antigos/novos foram reproduzidos exatamente na inferencia. Um piloto de treinamento com oito atualizacoes por repeticao, repetido duas vezes nos quatro pares, produziu curvas, pesos e previsoes bitexatos ao exigir algoritmos deterministas. O adaptador versionado preserva arquitetura, dados e hiperparametros e registra um novo controle sem quantizacao sob a mesma politica estrita das variantes. O piloto nao substitui os treinamentos completos nem a auditoria final. Os mensais e as selecoes prontas dos demais modelos continuam preservados.

## Regras do experimento

A integracao do adaptador estrito foi aprovada em 30/09: selecao e refit dos quatro pares em execucao curta, com replay independente dos 32 checkpoints e diferenca maxima de 2,274e-13 W/m2. Os coordenadores atual e historico foram retomados. A base atual conta com 36 de 44 pares com selecao completa; os treinamentos finais e os PDFs ainda estao pendentes. O estudo historico aguarda a base atual auditada.

- Min-max ajustado por localidade apenas sobre a parte de treinamento de cada fase.
- Quantizacao uniforme em [0, 1], com 64, 128 ou 256 valores: rint(clip(x, 0, 1) * (N - 1)) / (N - 1).
- Controle sem arredondamento e sem clipping. O efeito medido inclui clipping e arredondamento; registrar saturacao separadamente.
- Redes e XGBoost: quantizar as entradas de GHI no treino e na previsao; manter os alvos continuos. Nao quantizar identificadores, pesos da rede ou valores reais usados nas metricas.
- ARIMA e referencias simples: documentar especificamente quais observacoes historicas entram quantizadas. ARIMA ajusta uma serie endogena, e nao tem a mesma separacao X/y das redes supervisionadas.
- Preservar configuracoes, sementes e regras de treinamento entre niveis. Escolhas feitas na validacao, nunca pelos menores erros de teste.
- Avaliar nas mesmas origens, alvos e localidades; calcular as metricas em W/m2 apos inverter a escala. Media das previsoes de sementes antes do pos-processamento.
- O teste de 2024 ja foi visto em estudos anteriores. A comparacao nessa base e retrospectiva.
- Testes de execucao curta nao sao resultados publicaveis. O PDF final exige execucoes completas, verificacao das metricas, integridade dos artefatos e revisao visual.

## Divisao historica definida antes dos treinamentos

O teste sera de abril de 2019 a dezembro de 2022: os ultimos 45 dos 300 meses (15%). A validacao sera de abril de 2018 a marco de 2019. O ajuste inicial longo usara janeiro de 1998 a marco de 2018, e o refit longo incluira os dados ate marco de 2019. O historico curto pareado comecara em abril de 2014, com a mesma validacao e o mesmo teste. Todo o horizonte de cada janela devera estar contido na respectiva particao.

Essas datas e os hashes dos 70 arquivos de origem estao registrados nos contratos aprovados, antes dos treinamentos historicos. As localidades continuam as dez do nosso projeto; isso nao reproduz integralmente o estudo do Luis. As configuracoes dos modelos ja foram definidas no projeto, portanto a analise historica tambem e retrospectiva.

As origens e os cortes usam fuso local fixo. No teste horario historico, a disponibilidade das observacoes permite 1.368 origens por localidade: a ultima origem e 28/12/2022, com ultimo alvo em 30/12/2022 as 23h locais. A fonte termina em 31/12/2022 as 23h UTC, portanto nao cobre o horizonte local completo da origem de 29/12. Essa origem e excluida para todos os modelos e para os dois historicos; nao ha imputacao nem incorporacao de dados de 2023.

## Comparabilidade de ambiente

LSTM, GRU e DilatedRNN horarios e diarios usam novos controles na GPU para viabilizar as repeticoes, com o mesmo dispositivo em todos os niveis. A arquitetura, os hiperparametros e os loops de treinamento permanecem os do respectivo controle. A troca de ambiente pode alterar previsoes e epocas selecionadas; o efeito de quantizacao e medido contra o novo controle no mesmo ambiente, sem atribuir essas diferencas a quantizacao. Os checkpoints anteriores sao preservados e sua reproducao e documentada separadamente.

Uma alteracao do MAE entre periodos nao demonstra, por si so, efeito de variacao climatica. A comparacao pareada de historico curto e longo nas mesmas datas ajuda a avaliar o efeito da quantidade de dados, sem estabelecer uma causa climatica.
