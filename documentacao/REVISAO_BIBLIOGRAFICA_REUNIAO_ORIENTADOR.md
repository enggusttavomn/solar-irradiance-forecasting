# Revisão bibliográfica e posicionamento do TCC

## 1. Parecer sobre o mérito científico

**O projeto tem uma base defensável para um TCC empírico, mas a evidência atual não basta para classificá-lo como uma nova solução superior à literatura.** Este é um julgamento técnico, não uma garantia de aprovação ou publicação. A principal força é a comparação rastreável entre configurações sob informação restrita; as principais fragilidades são a novidade ainda limitada, a pequena amostra mensal e a ausência de vantagem sobre os melhores baselines em parte importante dos casos.

A pesquisa bibliográfica deve responder se a pergunta vale ser investigada, e não apenas fornecer citações para um vencedor escolhido. GHI-only e avaliação em diversas localidades já têm precedentes. O texto completo de Cabral et al. confirma, inclusive, previsão direta de 60 médias mensais, cinco anos à frente, em 40 localidades. Portanto, nem a ausência de meteorologia nem o longo horizonte mensal, isoladamente, distinguem o projeto.[^R6][^R9]

**Recomendação: manter DilatedRNN como modelo focal a ser defendido pela relação entre erro e tamanho da configuração, com TimesNet como comparador principal e os demais modelos como controles indispensáveis.** A pergunta relevante é:

> Uma rede recorrente dilatada compacta pode oferecer uma alternativa competitiva à modelagem periódica da TimesNet para previsão de GHI sem meteorologia auxiliar, e em quais resoluções e horizontes essa escolha é sustentada?

O resultado favorável já observado é específico: DilatedRNN supera TimesNet no macro-MAE cumulativo terminal de três das quatro tarefas, usando menos parâmetros em todas as configurações. O contraste mensal de um passo é o mais convincente dentro desse par; as vantagens diária e de seis meses são inferiores a 1%. Isso sustenta uma preferência delimitada, não uma vitória geral nem uma explicação causal de que as dilatações produziram os ganhos.

Os controles acrescentam uma restrição decisiva. Nas tarefas mensais concluídas, Informer obtém menor MAE que DilatedRNN, e a climatologia supera ambas. A conclusão sobre o conjunto completo ainda depende das execuções diária e horária dos novos modelos. Não se deve retirar esses concorrentes, trocar a métrica ou redefinir os quatro casos para preservar uma maioria favorável. A seção 6 reúne a avaliação crítica e as condições para fortalecer ou restringir a defesa.

Nesta formulação, GHI é a única variável dinâmica preditora dos modelos neurais, mas permanecem o identificador estático de localidade e o pós-processamento astronômico horário. A simplicidade das entradas é uma característica do cenário de uso; ainda não demonstra menor custo operacional, transferência para localidades novas ou independência do dataset.

## 2. Como a revisão foi feita e seus limites

Data de consulta e atualização deste parecer: 12 de setembro de 2026.

A busca dirigida combinou nomes das arquiteturas com `solar irradiance`, `GHI`, `solar radiation`, `solar forecasting`, `photovoltaic`, `short-term`, `long-term`, `univariate` e `GHI only`. Foram pesquisados os títulos exatos dos três trabalhos indicados pelo orientador e consultados registros de editoras, artigos originais e repositórios de autores. Buscas com variantes `DilatedRNN`, `Dilated RNN` e `dilated recurrent neural network` permitiram separar recorrência dilatada de convoluções dilatadas e de trabalhos que apenas citam a arquitetura.

Na primeira rodada, pela manhã de 12/09, o acesso direto ao **Google Acadêmico não funcionou**: a abertura pelo navegador falhou e a consulta direta pelo mecanismo de pesquisa não pôde ser aberta. Essas buscas foram feitas pela pesquisa web e pelas fontes primárias listadas abaixo.

Na segunda rodada, à tarde de 12/09, o Google Acadêmico respondeu às consultas por palavra-chave. As consultas, o número de resultados e os trabalhos incorporados estão na seção 4.1. A navegação por "Citado por" não funcionou no acesso automatizado, porque as entradas principais da DilatedRNN e da TimesNet não apareceram e surgiram versões duplicadas. A busca de citações foi feita, então, pelo grafo de citações da Semantic Scholar.

Assim, este documento continua sendo uma **revisão dirigida e rastreável, não uma revisão sistemática exaustiva**. A ausência de um resultado nas consultas realizadas não comprova inexistência de literatura.

Critérios de inclusão: relação experimental com irradiância/GHI ou potência solar; artigos originais das arquiteturas; estudos autoregressivos comparáveis; descrição suficiente para identificar alvo e informação disponível. Potência fotovoltaica foi mantida como evidência adjacente, nunca confundida com GHI. Trabalhos de carga elétrica, simples citações a DilatedRNN e convoluções dilatadas sem recorrência dilatada não contam como aplicação direta.

Convenções da matriz:

- **P**: registro oficial, resumo e/ou trechos de seções disponíveis; **FULL TEXT PENDENTE** para os detalhes não examinados.
- **A**: texto aberto com seções metodológicas consultadas; não significa auditoria de reprodução do artigo.
- **M**: somente metadados primários confirmados; **FULL TEXT PENDENTE**.
- **NC**: não confirmado no material consultado. Não significa que o artigo não informa o campo.
- Curto, médio e longo prazo são descrições contextuais. Os números de horas, dias ou meses têm prioridade sobre esses rótulos.

## 3. Diagnóstico do repositório antes das alterações

### 3.1 Fonte de verdade e preservação

O manuscrito atual está em `artigos/revista_unificado/`, com `main.tex` e `supplementary_material.tex`. A base experimental canônica é `resultados/avaliacao_multirresolucao_corrigida_v2/`; a extensão horária referencia, em modo somente leitura, `resultados/avaliacao_horaria_timesnet_corrigida_retomavel/`.

A inspeção encontrou as quatro tarefas concluídas. A tarefa diária já possui os vinte caches de quatro modelos × cinco sementes: não precisa ser repetida simplesmente porque um texto anterior a descrevia como pendente. Os hashes dos arquivos de entrada referenciados nos contratos das quatro tarefas foram conferidos e coincidem. O commit observado no diagnóstico foi `936d6970aece9175ac0d072456652ef05f531e8f`. Há alterações preexistentes e uma reorganização ampla preparada no índice; elas não pertencem a esta revisão e devem ser preservadas.

A compilação atual confirma que a **Figura 6** é o painel de sete dias: rótulo `fig:seven_day_profiles` e arquivo `figures/perfis_sete_dias.png`. Uma compilação antiga numerava como Figura 6 os casos contrastantes, hoje Figura 5: rótulo `fig:contrasting_cases` e arquivo `figures/previsoes_casos_contrastantes.png`. Os dois arquivos foram preservados, evitando redesenhar a figura elogiada por causa de uma divergência de numeração entre versões. O plano antigo aberto na IDE trata de publicação no Overleaf e não substitui o pedido atual de pesquisa e desenvolvimento local. Nenhum comando de commit ou push foi executado nesta revisão; uma automação preexistente foi observada criando commits do artigo durante as edições.

### 3.2 Matriz experimental encontrada

| Tarefa | Alvo e resolução | Histórico | Saída e checkpoints | Sementes de modelos aprendidos |
|---|---|---:|---|---|
| `hourly_72_extension` | GHI horário | 336 horas | 72 horas; 24, 48 e 72 h | 42 |
| `daily_30` | Média diária de GHI | 365 dias | 30 dias; 1, 3, 7, 14 e 30 d | 11, 23, 42, 67 e 89 |
| `monthly_1` | Média mensal de GHI | 12 meses | 1 mês | 11, 23, 42, 67 e 89 |
| `monthly_6` | Média mensal de GHI | 12 meses | 6 meses; checkpoints em 1, 3 e 6 meses | 11, 23, 42, 67 e 89 |

Dez localidades aparecem em todas as tarefas: BYD Camaçari; Tesla Gigafactory Nevada; Tesla Gigafactory Texas; Hyundai Metaplant Georgia; Rivian Normal; Tesla Fremont Factory; Lucid AMP 1 Casa Grande; GM Factory Zero; Ford Rouge Electric Vehicle Center; BMW San Luis Potosí. São pontos NSRDB associados geograficamente a instalações industriais, não medições de sensores das fábricas, consumo industrial ou potência fotovoltaica.

O treino horário usa origens de 2019–2022; as tarefas agregadas usam origens de 2020–2022, com histórico anterior para formar as janelas. A validação é 2023. Após a seleção, há refit com os dados admissíveis até 2023 e teste em 2024. As origens são cortadas para não deixar alvos atravessarem a fronteira de cada partição. Por localidade, o teste tem 363 origens horárias, 337 diárias, 12 mensais de um passo e sete mensais de seis passos. Estas últimas geram 42 previsões por localidade com alvos sobrepostos, e não 42 meses independentes.

A normalização min–max é ajustada por localidade somente nos dados anteriores ao corte pertinente. Não há clipping superior na saída física; aplica-se piso zero. O horário também usa máscara noturna astronômica. Meteorologia independente adicionada aos casos ilustrativos é descritiva e posterior à seleção dos casos; não é entrada do preditor.

### 3.3 Resultados já disponíveis

Macro-MAE cumulativo no horizonte completo, em W/m². Horário: semente 42; demais: média das previsões das cinco sementes para modelos aprendidos. A média das métricas entre sementes é outra estatística e não deve ser confundida com o erro do ensemble.

| Modelo | 72 horas | 30 dias | 1 mês | 6 meses |
|---|---:|---:|---:|---:|
| TimesNet | 52,48 | 44,08 | 13,89 | 14,46 |
| DilatedRNN | 52,96 | 43,85 | 13,01 | 14,37 |
| LSTM | 53,39 | 44,18 | 14,27 | 14,76 |
| XGBoost | 50,50 | 43,93 | 14,82 | 14,72 |
| Climatologia | Não consta na extensão horária | 45,51 | 12,57 | 13,03 |
| Persistência | 58,11 | 60,28 | 35,09 | 91,89 |
| Sazonal ingênuo | 65,90 | 58,78 | 16,94 | 18,00 |

Rastreabilidade: cada coluna corresponde a `<tarefa>/metricas_macro.csv`, filtrando `particao=teste_2024`, `tipo_horizonte=cumulativo` e o horizonte terminal. O detalhamento está em `metricas_por_localidade.csv`; previsões são preservadas em `previsoes_teste.csv.gz`. Os valores não apresentados nesta síntese não estão ausentes do experimento.

DilatedRNN vence TimesNet em três das quatro tarefas terminais por macro-MAE. O ganho relativo de um mês é 6,38%. Esse placar é descritivo, não um teste estatístico nem uma média de desempenho de problemas equivalentes. XGBoost vence o horizonte horário completo; a climatologia vence os dois horizontes mensais completos. A classificação também depende da métrica: no diário, XGBoost tem RMSE ligeiramente menor que DilatedRNN, apesar de MAE ligeiramente maior.

As métricas canônicas atuais são MAE, RMSE, nRMSE = RMSE/média observada e R², calculadas por localidade e depois promediadas com pesos iguais. MSE deverá ser calculado das mesmas previsões e registrado em (W/m²)², sem redefinir as demais métricas. **Média dos RMSEs ao quadrado não é o macro-MSE**. Nos leads horários exatos 24, 48 e 72, o alinhamento atual seleciona horários noturnos; erro zero ali não demonstra habilidade meteorológica, e nRMSE/R² permanecem indefinidos quando seus denominadores são nulos.

## 4. Matriz bibliográfica: alvo, tempo e informação

Os identificadores levam às referências completas na seção 8. A tabela deve ser lida junto das pendências da seção 5; NC nunca foi preenchido por inferência.

| ID / estudo | Modelo e alvo | Horizonte / resolução | GHI-only e variáveis externas | Imagens / decomposição | Abrangência e acesso |
|---|---|---|---|---|---|
| R1 Chang, 2017 | DilatedRNN; tarefas gerais | Não é estudo solar | Não aplicável | Não aplicável | Artigo fundador; P |
| R2 Wu, 2023 | TimesNet; tarefas gerais | Curto/longo nas bases do artigo; não equivale a horizonte solar | Depende da tarefa | Representação 2D periódica interna; não é por si uma decomposição ICEEMDAN | Artigo fundador; P |
| R3 Li, 2025 | TimesNet + T2T-ViT + fusão; GHI | Seis passos de 10 min, até 1 h | Não: histórico de irradiância + imagens | Sim / decomposição externa NC | Número de locais NC; P |
| R4 Zhao, 2024 | ICEEMDAN–TimesNet; irradiância solar | 24, 48, 96 e 168 h; horário; histórico de 48 h | Não: sequências decompostas + meteorologia | Imagens NC / ICEEMDAN | Denver, Clark e Folsom; P |
| R5 Gong, 2024 | TimesNet; GHI | 4 dias à frente; dados horários | Não: GHI mais temperatura, umidade, pressão atmosférica, velocidade do vento e cobertura de nuvens | NC / NC | Locais NC; P (resumo) |
| R6 Guariso, 2020 | FF e LSTM; irradiância global | 1–12 h; horário; histórico de 24 h | Sim, formulação puramente autoregressiva | Não / não na formulação consultada | Como e transferência a outras estações; A |
| R7 Cheng, 2021 | Convolução 1D + LSTM; irradiância | Dia seguinte até uma semana; horário diurno | Não: irradiância e meteorologia, inclusive previsões | Imagens NC / NC | Taiwan; número de estações NC; P |
| R8 Zhu, 2024 | TimesNet, Informer, Transformer, Pyraformer; fatores ITI, IDA, STA e WC | Nove horizontes entre 10 min e 24 h; coleta nativa a cada minuto | Não no desenho multiparâmetro: 18 fatores ambientais/solares e combinações de entradas | NC / NC | Base experimental em Kunming, para estufa fotovoltaica; A, detalhes ainda pendentes |
| R9 Cabral, 2026 | GPT-Neo e competidores; GHI | Histórico de 60 médias mensais → 60 meses, cinco anos, em saída direta | Sim, GHI quantizado em 128 níveis e normalizado; condicionamento da tarefa no LLM | Não no pipeline proposto / quantização, não decomposição empírica | 40 localidades; A, PDF publicado conferido |
| R10 Smyl, 2026 | AQ-RNN com células recorrentes dilatadas; geração FV normalizada | 48 h; horário | Não é GHI: histórico FV + semana do ano + contexto entre regiões; sem meteorologia externa | Não / não na formulação descrita | 259 regiões europeias; preprint A |
| R11 Yu, 2025 | TimesNet modificada; potência FV | 1, 3, 6 e 12 h; resolução NC | Não: parâmetros meteorológicos | NC / extração modificada, não equiparar a ICEEMDAN | Três datasets; P |
| R12 Shi, 2026 | 2DTFM; irradiância | Modelagem multiescala; horizontes numéricos NC | Lista completa de entradas NC | NC / funções B-spline, não equiparar a decomposição empírica | Locais NC; P |

### Matriz complementar: avaliação e relação com o TCC

| ID | Partição, métricas e baselines confirmados | Contribuição / diferença relevante |
|---|---|---|
| R3 | Detalhamento de split, métricas e baselines: pendente | Combina duas modalidades para o intra-horário; não isola TimesNet sob a nossa entrada restrita. |
| R4 | Comparações incluem Autoformer, DLinear e Informer; split e valores exatos pendentes | Demonstra uso solar anterior de TimesNet, mas acopla decomposição e meteorologia. |
| R5 | O resumo informa MSE 0,198, MAE 0,259, RMSE 0,445 e R² 0,787, sem indicar a escala, e comparação com três modelos de longo prazo não nomeados; split pendente | Precedente de TimesNet para GHI em vários dias, com meteorologia. Não comparar esses erros com os nossos em W/m². |
| R6 | Treino 2014–2017, validação 2018, teste 2019; persistência, persistência de 24 h e céu claro; lista completa de métricas NC | Precedente GHI-only e de transferência sem retreino. Impede novidade baseada apenas em entrada univariada ou múltiplos locais. |
| R7 | Split e métricas completos pendentes | Semana à frente não é equivalente à média mensal; previsões meteorológicas mudam a informação disponível. |
| R8 | MAE, MSE, RMSE, R²; cinco volumes de treino e quatro estações; coleta de 17/08/2021 a 16/08/2023; split e escala dos erros ainda não esclarecidos nos trechos examinados | Compara as quatro arquiteturas e condições sazonais. ITI é descrito como combinação de componentes de irradiância; não o equiparar automaticamente a GHI nem reutilizar os erros como ranking no nosso NSRDB. |
| R9 | Algoritmo 5: sequência de 240 médias mensais, 120 treino + 60 validação + 60 teste. Tabela 6: contexto 60, saída 60, SMAPE/Adam, 500 épocas, seed 1. MAE, RMSE, R², JSD, OVC; inclui persistência, smart persistence, SARIMA e redes | Precedente muito próximo de GHI-only, NSRDB e longo prazo. GPT-Neo lidera MAE/RMSE/R² agregados; outro modelo lidera JSD/OVC. Não comparar esses erros numericamente com nossos horizontes de 1/6 meses. |
| R10 | Treino anterior a 2010; validação 2010–2012; teste 2013–2015; CRPS e medidas quantílicas; ARIMA e Transformer entre baselines | Evidência solar de recorrência dilatada, mas célula, alvo probabilístico, dados e contexto diferem da DilatedRNN clássica usada aqui. |
| R11 | RMSE e MAPE no material consultado; comparação com TimesNet original; split pendente | Avalia uma modificação em potência FV, não TimesNet compacta para GHI mensal. |
| R12 | Split, métricas e protocolos detalhados pendentes | Já existe investigação explícita multiescala em irradiância. Não afirmar que multirresolução, genericamente, nunca foi estudada. |

### 4.1 Busca complementar no Google Acadêmico (12/09/2026, tarde)

| Consulta no Google Acadêmico | Filtro | Resultados | O que se aproveitou |
|---|---|---:|---|
| `"dilated recurrent" OR "dilated RNN" solar irradiance forecasting` | desde 2017 | 20 | Só R10 é previsão solar com recorrência dilatada |
| `"dilated RNN" OR "DilatedRNN" photovoltaic OR GHI forecasting` | desde 2017 | 3 | Nenhuma aplicação direta; um caso descartado (seção 5) |
| `"dilated LSTM" OR "dilated GRU" OR "dilated recurrent neural network" solar OR photovoltaic forecasting` | desde 2017 | cerca de 36 | Nenhuma aplicação direta à irradiância |
| `"Attention-Dilated LSTM"` | sem filtro | 4 | Leva a Molu et al. (2024), que usa convolução dilatada |
| `TimesNet "solar irradiance" OR "global horizontal irradiance" forecasting` | desde 2023 | cerca de 123 | Confirma R4 e R5; acrescenta R13 |
| `TimesNet photovoltaic power forecasting` | desde 2023 | cerca de 511 | Maioria em potência FV, com decomposição ou fusão |
| `univariate "global horizontal irradiance" deep learning forecasting "without meteorological"` | desde 2020 | 6 | Nenhum precedente GHI-only novo com desenho comparável |

Busca de citações na Semantic Scholar, 12/09:

- **Chang et al. (2017), R1:** 355 citações indexadas. Só dois títulos tratam de potência FV. Izadi et al. (2026, Energy and AI, DOI 10.1016/j.egyai.2026.100890) usam CNN–GRU com imagens do céu, sem recorrência dilatada no resumo. Julaiti et al. (2026, ICCMS, DOI 10.1109/ICCMS69991.2026.11642670) não têm resumo indexado; o título descreve fusão XGBoost–Transformer.
- **Zhao et al. (2024), R4:** 62 citações, das quais 28 com solar ou FV no título. Daí vieram R14 a R18.
- **Li et al. (2025), R3:** 6 citações, entre elas Cabral et al. (R9). Nenhum novo trabalho de TimesNet em GHI.
- **Gong et al. (2024), R5:** 3 citações, nenhuma sobre irradiância.

Novos trabalhos incorporados, nas mesmas colunas da matriz principal:

| ID / estudo | Modelo e alvo | Horizonte / resolução | GHI-only e variáveis externas | Imagens / decomposição | Abrangência e acesso |
|---|---|---|---|---|---|
| R13 Wei, 2026 | Fusão multimodal em dois ramos; GHI | Curto prazo; valores NC | Não: GHI histórico, imagens de satélite e camada de irradiância extraterrestre | Sim / NC | Locais NC; P (resumo via Google Acadêmico). Apareceu na busca por TimesNet, mas o resumo não cita TimesNet |
| R14 Umar, 2026 | CSI-DECOB-Ensemble, com 15 submodelos e atenção cruzada com céu claro; irradiância | 1 a 15 dias; diária | NC: o resumo cita dinâmica atmosférica histórica e potencial futuro de céu claro | Não / não | Abu Dhabi, Aswan, Islamabad e Longreach; comparação com boosting e PatchTST; P (periódico aberto, texto não examinado) |
| R15 Li, 2026 | Árvore de decisão, RF, GBRT, Naive Bayes, regressão linear e média do conjunto; GHI | Mensal; antecedência NC | Não: previsões do modelo climático JMA/MRI-CPS3 e reanálise ERA5 | Não / EOF para escolher preditores | Estações na China; validação de 02/2022 a 01/2024; P |
| R16 Ayata, 2026 | ARIMA, SARIMA, SES e Holt-Winters; irradiação global horizontal | Resolução e horizonte NC | NC: o resumo cita parâmetros meteorológicos históricos e sazonais | Não / não | Hakkâri, Türkiye, 2019–2022; grid search e validação K-fold; P |
| R17 Chen, 2025 | Informer modificado e interpretável; GHI | NC | NC | NC / NC | M; FULL TEXT PENDENTE |
| R18 Yu W., 2025 | TimesNet e AT-Informer-AT em paralelo; potência FV | Curto prazo; valores NC | NC | NC / NC | M; FULL TEXT PENDENTE |
| R19 Zhang, 2026 | Cross-Unet, Transformer codificador–decodificador; potência FV | 4 h a 7 dias; 15 min | Não: histórico de geração com NWP, irradiância de satélite ou previsão de modelo meteorológico de IA | Não / não | Cinco usinas no norte da China e na Austrália central; dez redes e referências operacionais como baselines; P |

**Consequências para o TCC:**

- **DilatedRNN:** depois das duas rodadas, continua sem registro de aplicação da DilatedRNN clássica à previsão de GHI. A comparação DilatedRNN × TimesNet com entrada restrita ao GHI não foi encontrada no material examinado. Deve ser descrita como "não encontrada nas buscas", nunca como inédita.
- **TimesNet:** é precedente solar consolidado, quase sempre com meteorologia, decomposição, imagens ou combinada a Informer (R4, R5, R18). Usá-la como comparadora compacta, só com GHI, é diferença de desenho, não novidade de aplicação.
- **GHI-only:** não surgiram precedentes além de R6 e R9. R19 funde o histórico de geração FV com previsões meteorológicas numéricas, de satélite ou de modelo de IA e supera dez redes de referência, mas o resumo não isola quanto do ganho vem das previsões. Isso reforça tratar o GHI-only como cenário de uso com menos dados, e não como vantagem de acurácia.
- **Baselines:** R16 mostra ARIMA e SARIMA ainda em uso para irradiação, o que apoia incluir ARIMA. R14 e R15 são precedentes diário e mensal, ambos com entradas externas e comparados com modelos mais simples.

## 5. O que já podemos afirmar — e o que falta ler

### TimesNet e os três artigos do orientador

Os três registros foram localizados com DOI. R3 comprova fusão com imagens; R4 confirma que as sequências de irradiância decompostas são combinadas com meteorologia. **R4 não deve ser descrito como GHI-only.** Em R5, o resumo indexado na Semantic Scholar (CorpusId 271246471), consultado em 12/09, confirma previsão de GHI quatro dias à frente a partir de dados horários. As entradas incluem temperatura, umidade, pressão atmosférica, velocidade do vento e cobertura de nuvens, e há comparação com três modelos. O horizonte de quatro dias e a lista de variáveis, antes não adotados, passam a ter fonte. Localidades, split e nomes dos modelos comparados continuam dependentes do texto completo. [R3](https://www.sciencedirect.com/science/article/pii/S0960148124022602), [R4](https://www.sciencedirect.com/science/article/pii/S096014812301621X), [anais de R5](https://www.proceedings.com/content/075/075354webtoc.pdf).

Esses precedentes descartam a narrativa de primeira aplicação solar da TimesNet. A busca de 12/09 à tarde ampliou esse quadro com TimesNet combinada a Informer em potência FV e com Informer modificado para GHI (seção 4.1). Ainda permitem investigar a comparação controlada com recorrência dilatada sem acrescentar os módulos e entradas utilizados nesses estudos. Trata-se de uma diferença de desenho experimental; não é uma demonstração de que entradas restritas sejam mais precisas.

### DilatedRNN: resposta por tipo de aplicação

Não foi confirmado, nas buscas realizadas, um artigo experimental que aplique inequivocamente a **DilatedRNN clássica de Chang** à previsão direta de GHI e cubra o nosso conjunto de tarefas. A resposta para curto, médio, longo prazo, multi-step e múltiplos locais permanece “não confirmado nesta busca”, e não “não existe”. Na rodada de 12/09 à tarde, os 20 resultados do Google Acadêmico para recorrência dilatada e irradiância solar e os 36 para LSTM/GRU dilatadas em solar ou FV não trouxeram aplicação direta além de R10. Na Semantic Scholar, as 355 citações indexadas do artigo de Chang incluem só dois trabalhos de potência FV. O resumo disponível de um deles não usa recorrência dilatada, e o do outro não está indexado (seção 4.1). [Artigo original R1](https://proceedings.neurips.cc/paper_files/paper/2017/hash/32bb90e8976aab5298d5da10fe66f21d-Abstract.html).

Há, entretanto, evidência próxima e importante em R10: recorrência dilatada para previsões probabilísticas de geração fotovoltaica em múltiplas regiões, 48 horas à frente. O trabalho é um **preprint**, não uma publicação de periódico confirmada. A célula modificada, o contexto entre regiões e o alvo FV impedem classificá-lo como uma reprodução da nossa DilatedRNN, mas tornam incorreto dizer que recorrência dilatada nunca foi utilizada em energia solar. A lista do autor o identifica como submetido; o nome de periódico no template não comprova aceite. [Preprint R10](https://arxiv.org/html/2602.05660v1), [lista do autor](https://gdudek.el.pcz.pl/publications).

Dois controles negativos ilustram a triagem: o artigo de Castillo-Rojas et al. sobre previsão FV com redes recorrentes e rasas cita DilatedRNN, mas a formulação experimental consultada usa LSTM/GRU e MLP; o trabalho de Choi sobre redes de atenção recorrente dilatada prevê **carga elétrica**, não GHI. Não contam como aplicações diretas. [Castillo-Rojas et al., DOI 10.3390/en16135093](https://www.mdpi.com/1996-1073/16/13/5093), [Choi, DOI 10.7557/18.5136](https://septentrio.uit.no/index.php/nldl/article/view/5136).

A rodada de 12/09 à tarde acrescentou três casos da mesma natureza. Molu et al. (2024) chamam o modelo de "Attention-Dilated LSTM", mas o resumo descreve LSTM com atenção e **convoluções** dilatadas para irradiância em Douala. Um artigo da Applied Sciences sobre detecção de ataques em comunicação FV aparece na busca por Dilated RNN, mas propõe um Transformer. Chen et al. (2024) combinam LSTM e CNN–BiLSTM com atenção para potência FV. Nenhum deles aplica recorrência dilatada à previsão de irradiância. [Molu et al., DOI 10.1016/j.rineng.2024.102461](https://doi.org/10.1016/j.rineng.2024.102461), [Applied Sciences, DOI 10.3390/app14219820](https://doi.org/10.3390/app14219820), [Chen et al., DOI 10.11930/j.issn.1004-9649.202406005](https://doi.org/10.11930/j.issn.1004-9649.202406005).

### GHI-only já tem precedentes

Guariso et al. declaram uma abordagem autoregressiva e avaliam transferência para outras estações. Cabral et al. apresentam uma abordagem GHI-only em diversas localidades. Logo, menor necessidade de sensores e covariáveis é uma característica de implantação a estudar, **não uma novidade exclusiva deste projeto**. [R6](https://www.mdpi.com/1996-1073/13/15/3987), [R9](https://www.sciencedirect.com/science/article/pii/S0038092X26006535).

Redação adequada: “menor dependência de variáveis meteorológicas auxiliares”. Evitar “independente do dataset”, “dispensa dados externos em qualquer etapa”, “generaliza automaticamente” e “mais robusto por ser univariado”. O modelo continua dependente da qualidade e representatividade do histórico, da resolução, dos locais de treinamento e do regime climático.

### Pendências para consulta pela biblioteca/VPN

| Prioridade | Texto | O que confirmar antes de acrescentar detalhes ao artigo |
|---|---|---|
| Alta | R5 Gong — FULL TEXT PENDENTE | Horizonte de 4 dias, resolução horária, variáveis e métricas já confirmados pelo resumo. Faltam histórico, localidades, se as variáveis são observadas ou previstas, split, nomes dos três modelos comparados e escala dos erros. |
| Alta | R3 Li — FULL TEXT PENDENTE | Dataset/localidades, alinhamento GHI–imagens, demais entradas, split e comparação isolando os módulos. |
| Alta | R4 Zhao — FULL TEXT PENDENTE | Lista de covariáveis; observadas versus previstas; execução causal da decomposição; fronteiras do split; métricas e comparação sem ICEEMDAN. |
| Esclarecimento, não falta de PDF | R9 Cabral — texto publicado disponível localmente | Confirmados cinco anos, resolução mensal e split 120/60/60. Confirmar com os autores os extremos do período descrito como 1998–2018 versus 240 meses e o ajuste de normalização por partição antes de uma reprodução. |
| Esclarecimento, não falta de PDF | R8 Zhu — cópia completa disponível em repositório institucional de autor | Confirmados Kunming, coleta minuto a minuto e período 2021–2023. Ainda esclarecer split por tarefa, escala/normalização dos erros, definição operacional de ITI e disponibilidade temporal de cada covariável. |
| Média | R11 e R12 — FULL TEXT PENDENTE | Entradas, cortes temporais, horizontes/resoluções, papel exato da TimesNet e disponibilidade de dados/código. |

Em R10, confirmar a convenção de corte do refit antes de reproduzir o experimento; a redação é ambígua, não prova vazamento.

### Textos completos que refinaram a comparação

Em R9, a cópia de `documentacao/materiais_de_referencia/article_thales.pdf` contém título, autores, DOI, identificação do periódico e aceite em 26/07/2026 compatíveis com o registro publicado. As páginas 9–10 e o Algoritmo 5 confirmam horizonte de **cinco anos**, não cinco dias, e amostragem mensal. A Tabela 6 informa contexto e saída de 60 meses; a Tabela 9 compara os resultados em 40 localidades. Trata-se de um precedente próximo o suficiente para exigir uma contribuição além de GHI-only e longo prazo. A aparente diferença entre o intervalo civil citado e a contagem de meses permanece como dúvida de reprodução, não como acusação de erro experimental.[^R9]

Em R8, as seções 2.1–2.2, páginas 4–5, confirmam uma base experimental em Kunming, com coleta a cada minuto por dois anos. O estudo mistura variáveis ambientais e fatores solares e não equivale a nossa previsão direta de GHI. O texto está disponível, mas acesso ao PDF não significa que todas as ambiguidades metodológicas estejam resolvidas. As unidades e a escala dos erros precisam ser esclarecidas antes de qualquer comparação quantitativa.[^R8]

## 6. Comparação científica e escolha do foco

| Dimensão | DilatedRNN neste projeto | TimesNet neste projeto |
|---|---|---|
| Ideia central | Recorrência com ligações dilatadas | Periodicidade e transformação temporal 2D |
| Literatura solar | Aplicação clássica direta não confirmada nesta busca; há recorrência dilatada FV adjacente | Aplicações solares confirmadas, inclusive multimodais e com decomposição |
| Evidência atual | Menor MAE terminal diário e mensal que TimesNet; destaque em um mês | Menor MAE terminal horário que DilatedRNN; também vence alguns checkpoints intermediários |
| Limitação da preferência | Climatologia melhor no mensal; diferenças pequenas em duas tarefas | XGBoost melhor no horário; não há vantagem geral do backbone |
| Complexidade | Menos parâmetros nas configurações atuais | Mais parâmetros nas configurações atuais; implementação compacta, não reprodução literal de todos os detalhes oficiais |
| Custo computacional | Menos parâmetros não prova menor tempo/energia | FFT e convoluções não provam maior ou menor custo sem medição |
| Dependência de entrada | Histórico GHI + identidade estática de localidade | Mesmo conjunto informacional admissível |
| Novidade defensável | Evidência comparativa no desenho específico, não invenção da arquitetura | Avaliação sob restrição informacional e comparação comum, não primeira aplicação solar |

A hipótese de trabalho é que **uma configuração recorrente dilatada compacta pode preservar ou melhorar o desempenho frente à TimesNet sem ampliar as entradas dinâmicas**. Essa hipótese dá um modelo focal à investigação, mas admite refutação. Os resultados não isolam causalmente o efeito da dilatação: resolução, horizonte, tamanho amostral, normalização e capacidade variam entre tarefas ou configurações.

### 6.1 Avaliação do projeto diante da literatura

As avaliações abaixo são juízos técnicos apoiados nos artigos citados e no protocolo auditado, não notas de uma banca nem previsões de aceite editorial.

| Critério | Evidência relevante | Parecer e consequência |
|---|---|---|
| Relevância da pergunta | Previsão autoregressiva e seleção entre alternativas simples e complexas já são problemas tratados por Guariso; entradas adicionais aparecem nos trabalhos TimesNet indicados.[^R6][^R3][^R4][^R5] | Pergunta pertinente: esclarecer quando uma configuração compacta é suficiente em um cenário sem meteorologia auxiliar. Não demonstramos benefício econômico industrial. |
| Novidade de entrada | Guariso e Cabral já utilizam histórico de irradiância sem outras variáveis meteorológicas.[^R6][^R9] | GHI-only não é novidade isolada. Sua relevância é delimitar disponibilidade de informação, não estabelecer superioridade. |
| Novidade de horizonte e geografia | Cabral já avalia 60 passos mensais em 40 localidades; Shi investiga explicitamente modelagem multiescala.[^R9][^R12] | Dez localidades e quatro tarefas não bastam como lacuna. Nossos horizontes não são mais longos que todos os precedentes. |
| Novidade da arquitetura | Chang já propõe DilatedRNN; Smyl usa recorrência dilatada modificada em FV.[^R1][^R10] | Arquitetura não é nova. A aplicação clássica direta ao GHI ainda não foi confirmada nesta busca, mas isso não autoriza ineditismo. |
| Qualidade da comparação | Mesmas chaves de origem/alvo, cortes, pós-processamento e métricas; cinco sementes diárias/mensais e controles simples preservados. | Ponto forte do trabalho. A auditabilidade torna diferenças verificáveis; a busca de hiperparâmetros e a capacidade não foram equalizadas. |
| Tamanho e estabilidade do ganho | Três vitórias terminais contra TimesNet, mas duas margens menores que 1%; vantagem mensal de um passo mais consistente entre sementes. | Há evidência para uma preferência específica. A maioria numérica não prova uma vantagem ampla ou estatisticamente estabelecida. |
| Utilidade frente às melhores alternativas | Climatologia lidera os casos mensais; Informer tem menor MAE mensal que DilatedRNN. | Impede recomendar DilatedRNN como melhor opção geral por acurácia. A relação erro–tamanho precisa ser discutida contra esses controles, não somente contra TimesNet. |
| Validade externa | Um ano de teste, mesmos locais no treino/teste, alvos NSRDB, poucas origens mensais e sobreposição de alvos. | Não demonstramos desempenho em sensores, anos futuros ou localidades inéditas. Essas limitações afetam a força da contribuição. |

**Síntese:** o mérito mais sólido é empírico e incremental. Há um problema pertinente e um protocolo aproveitável; ainda não há comprovação de avanço de estado da arte. O resultado pode sustentar um TCC consistente e motivar um artigo, mas a suficiência para um periódico depende do recorte, da evidência adicional e da avaliação editorial.

### 6.2 O que os trabalhos mais próximos deixam em aberto

Não encontrar a combinação exata de dois nomes de modelos, dez cidades e quatro horizontes não é, por si só, uma lacuna relevante. O contraste com a literatura deve mostrar qual decisão fica mais bem informada.

| Precedente | Sobreposição com o projeto | Diferença que merece investigar, sem transformar diferença em prova de novidade |
|---|---|---|
| Guariso, R6 | Histórico de irradiância, múltiplos passos, redes recorrentes e baselines; há transferência entre estações. | Avaliar se outra estrutura de memória oferece vantagem nas nossas tarefas agregadas e configurações compactas. Não reivindicar primeiro estudo autoregressivo ou multissítio. |
| Li, Zhao e Gong, R3–R5 | TimesNet em previsão solar. | Investigar o comparador TimesNet sob entrada restrita, sem atribuir ao backbone isolado ganhos publicados com fusão, meteorologia ou decomposição. Não concluímos que a restrição de entrada melhora o erro. |
| Zhu, R8 | Comparação TimesNet, Informer e Transformer; horizontes e condições variadas. | Verificar robustez em outros locais e tarefas diárias/mensais, distinguindo nosso GHI dos fatores ITI/IDA/STA/WC do estudo. Comparar vários modelos já é precedente, não contribuição suficiente por si só. |
| Cabral, R9 | GHI-only, NSRDB, múltiplos climas, concorrentes fortes e previsão mensal. | Examinar uma alternativa com configuração pequena e uma comparação focada em recorrência versus periodicidade. Não usar menor contagem de parâmetros entre artigos como prova de menor tempo ou de melhor compromisso global. |
| Smyl, R10 | Recorrência dilatada sem meteorologia externa em um problema solar. | Avaliar a versão clássica compacta em GHI determinístico, distinguindo-a do alvo FV probabilístico e da arquitetura com contexto regional. |
| Shi, R12 | Estrutura temporal multiescala e representação de padrões. | Separar uma comparação empírica de configurações de uma proposta arquitetural com representação funcional. Quatro tarefas não demonstram, sozinhas, um mecanismo multiescala melhor. |

### 6.3 Força real da defesa da DilatedRNN

O critério mantido é o macro-MAE cumulativo no horizonte completo de cada tarefa, sem média de erros entre resoluções. Os percentuais são calculados a partir dos valores não arredondados em `metricas_macro.csv`; a contagem de parâmetros está em `artigos/revista_unificado/tables/model_capacity.tex`.

| Tarefa terminal | TimesNet / DilatedRNN, MAE em W/m² | Vantagem relativa da DilatedRNN frente à TimesNet | Parâmetros TimesNet / DilatedRNN | Interpretação |
|---|---:|---:|---:|---|
| 72 horas | 52,48 / 52,96 | −0,91% | 27.009 / 3.096 | A configuração dilatada é menor, mas perde por MAE. Horário tem só uma semente. |
| 30 dias | 44,08 / 43,85 | +0,51% | 13.725 / 2.382 | Vantagem pequena; vence três de cinco pares de sementes. TimesNet vence os checkpoints diários anteriores. |
| 1 mês | 13,89 / 13,01 | +6,38% | 2.758 / 1.889 | Evidência mais forte dentro do par: quatro de cinco sementes e seis de dez locais favoráveis. |
| 6 meses | 14,46 / 14,37 | +0,62% | 2.823 / 1.974 | Vantagem pequena e exploratória; quatro de cinco sementes e sete de dez locais favoráveis. |

Os dois casos mensais usam a mesma família de dados agregados e alvos sobrepostos em 2024; não são duas demonstrações independentes de generalização. O resultado “três de quatro” é descritivo e não equivale a probabilidade de vitória de 75% em aplicações futuras.

No mensal de um passo, a DilatedRNN tem aproximadamente 31,51% menos parâmetros treináveis que TimesNet. Esse é um argumento mensurado de tamanho, não de rapidez, energia ou memória de execução. Também não prova equivalência a modelos com outras capacidades ou resultados de outros datasets.

Nos controles mensais concluídos, os macro-MAEs são:

| Modelo | 1 mês | 6 meses |
|---|---:|---:|
| Climatologia | 12,57 | 13,03 |
| Informer | 12,85 | 13,88 |
| DilatedRNN | 13,01 | 14,37 |
| TimesNet | 13,89 | 14,46 |

Esses resultados são das previsões finais dos casos mensais, não de testes rápidos. Fonte: previsões canônicas e `resultados/avaliacao_baselines_revisao_20260912/{monthly_1,monthly_6}/informer/`, verificadas por contratos, manifestos e igualdade dos alvos. A superioridade do Informer aqui é por **MAE**; no mensal de um passo, DilatedRNN ainda apresenta RMSE menor que Informer. Nenhum dos dois supera a climatologia nesse resumo mensal.

**Conclusão defendível hoje:** entre as duas configurações focais, a DilatedRNN é preferível pelo macro-MAE terminal diário/mensal e pelo menor número de parâmetros, sobretudo no mensal de um passo. **Conclusão não defendível hoje:** a DilatedRNN é o melhor modelo do estudo ou a solução mais eficiente disponível para GHI.

### 6.4 O que falta para fortalecer a contribuição

| Prioridade | Evidência necessária | Por que altera o julgamento | Situação |
|---|---|---|---|
| Imediata | Completar e consolidar os modelos já solicitados em todas as tarefas. | Verifica se o vencedor focal continua competitivo com alternativas reais. | ARIMA completo; novas redes mensais completas; redes diária/horária ainda não consolidadas. |
| Imediata | Apresentar magnitude dos ganhos, locais, sementes e baselines no texto principal. | Evita transformar margens pequenas ou um subconjunto de comparadores em superioridade geral. | Resultados focais disponíveis; extensão em andamento. |
| Bibliográfica | Conferir Li, Zhao e principalmente Gong em texto completo. | Fecha a comparação de informação disponível e protocolo; delimita a possível novidade de aplicação. | FULL TEXT PENDENTE. Não impede os juízos já sustentados pelos demais precedentes. |
| Alta para uma alegação de eficiência | Medir treino, inferência e pico de memória em condições comparáveis. | Permite testar o compromisso erro–custo além do número de parâmetros. | Ainda não medido de forma comum. Não usar duração de execuções concorrentes como ranking justo. |
| Alta para robustez | Avaliar outros períodos por backtesting temporal e, idealmente, um teste futuro ainda não utilizado nas decisões. | Verifica se a vantagem persiste fora de 2024. | Extensão proposta, não executada. Um backtest retrospectivo não se torna teste cego novo. |
| Alta para explicar o mecanismo | Ablação com e sem dilatação, controlando capacidade, normalização e seleção na validação. | Testa se as conexões dilatadas contribuem, em vez de apenas o nome da rede. | Extensão proposta, não executada; manter o experimento atual intacto. |
| Condicional à alegação | GHI-only versus covariáveis disponíveis na emissão; avaliação em locais não vistos; desempenho diurno. | Necessários para alegar vantagem de entradas, transferência ou qualidade durante horas de geração. | Não demonstrados pelo protocolo atual. |

Não é necessário transformar todas essas extensões em requisitos para concluir o TCC. O texto deve corresponder ao nível de evidência: aplicação comparativa incremental pode ser defendida com limites claros; eficiência, superioridade robusta e mecanismo causal exigem verificações adicionais.

### 6.5 Rumo recomendado e condições de revisão

Manter o projeto e a DilatedRNN como foco científico **provisório**, com a pergunta erro–tamanho acima, sem alterar dados ou hiperparâmetros para produzir um vencedor. As quatro tarefas permanecem no relato; eventual ênfase no mensal de um passo será justificada como o resultado mais forte observado, não como um novo teste confirmatório escolhido depois de ver os erros.

Se o conjunto completo confirmar que a DilatedRNN é competitiva e sua menor configuração for útil, a escrita poderá defender essa escolha nas condições delimitadas. Se outros modelos a dominarem nos critérios relevantes, a recomendação de uso precisa mudar: ela poderá continuar como objeto de estudo, mas não como vencedora principal. Nesse caso, o projeto ainda produz conhecimento sobre os limites da arquitetura e da previsão baseada somente no histórico.

Essa avaliação combina novidade, literatura, desempenho, estabilidade, tamanho e relevância. Uma maioria favorável ajuda a defesa, mas não substitui a demonstração de que a pergunta acrescenta conhecimento.

## 7. Continuação prática autorizada

### Experimentos e rastreabilidade

Persistência, sazonal ingênuo e LSTM já existem e serão mantidos; XGBoost e climatologia não serão retirados. Faltam **ARIMA, GRU, Transformer vanilla e Informer** na matriz canônica. A extensão deverá abranger dez localidades e todos os checkpoints das quatro tarefas; modelos neurais usarão a semente 42 no horário e as cinco sementes nas demais tarefas. ARIMA é determinístico para uma configuração e não receberá desvio padrão artificial de sementes.

Os novos resultados deverão ficar em um diretório separado. As previsões antigas serão lidas e alinhadas pelas chaves, sem treinamento redundante ou sobrescrita dos arquivos canônicos. Contratos registrarão configurações, sementes, hashes de entradas/código, cortes, versões e seleção por validação. Testes rápidos serão marcados como não publicáveis. Informer deverá incluir atenção ProbSparse, distilação e decodificação em uma passagem; um Transformer com outro nome não atende ao pedido.

O protocolo de dados e avaliação permanece igual. Hiperparâmetros novos deverão ser declarados antes de examinar seus erros de teste. Seleção e early stopping usarão somente 2023; refit usará o número de épocas selecionado. Nenhuma previsão meteorológica ou alvo futuro será acrescentado às entradas. Falhas de ajuste serão registradas, não substituídas silenciosamente por resultados de outro método.

### Escrita do artigo

Depois deste diagnóstico, atualizar `sections/01_introduction.tex`, `sections/02_related_work.tex`, `references.bib` e a matriz em `tables/literature_review.tex`, com as alegações limitadas ao material efetivamente confirmado. Ajustar a pergunta de pesquisa e as contribuições para a comparação sob informação restrita. Não utilizar resultados de outros artigos como se fossem ensaios neste dataset.

Depois das execuções verificadas, atualizar protocolo, modelos, métricas, tabelas, resumo, resultados, limitações e conclusão. Incluir melhores e segundos melhores apenas entre valores realmente comparáveis. A Figura 6 será preservada; eventuais novas tabelas não exigem redesenhá-la. Compilar o artigo e o suplemento e inspecionar a diagramação. Não mexer no material EA019/da disciplina, excluído do escopo pelo pedido posterior do usuário.

Trabalhos futuros que continuam pertinentes: teste em anos adicionais e localidades não vistas; maior diversidade climática e bases independentes; comparação controlada GHI-only versus meteorologia disponível na emissão; medição de tempo e memória; ablações de capacidade e normalização; análise diurna. Não chamar de “futuro” um baseline já executado nesta continuação.

## 8. Referências rastreáveis

**R1.** Chang, S.; Zhang, Y.; Han, W.; Yu, M.; Guo, X.; Tan, W.; Cui, X.; Witbrock, M.; Hasegawa-Johnson, M.; Huang, T. S. (2017). *Dilated Recurrent Neural Networks*. Advances in Neural Information Processing Systems 30. DOI não identificado; [anais oficiais](https://proceedings.neurips.cc/paper_files/paper/2017/hash/32bb90e8976aab5298d5da10fe66f21d-Abstract.html); [versão dos autores](https://arxiv.org/abs/1710.02224).

**R2.** Wu, H.; Hu, T.; Liu, Y.; Zhou, H.; Wang, J.; Long, M. (2023). *TimesNet: Temporal 2D-Variation Modeling for General Time Series Analysis*. ICLR. DOI da conferência não identificado; [registro oficial](https://openreview.net/forum?id=ju_Uqw384Oq); [texto dos autores](https://arxiv.org/abs/2210.02186).

**R3.** Li, H.; Ma, G.; Wang, B.; Wang, S.; Li, W.; Meng, Y. (2025). *Multi-modal feature fusion model based on TimesNet and T2T-ViT for ultra-short-term solar irradiance forecasting*. Renewable Energy 240, 122192. DOI [10.1016/j.renene.2024.122192](https://doi.org/10.1016/j.renene.2024.122192). [Editora](https://www.sciencedirect.com/science/article/pii/S0960148124022602). FULL TEXT PENDENTE.

**R4.** Zhao, H.; Huang, X.; Xiao, Z.; Shi, H.; Li, C.; Tai, Y. (2024). *Week-ahead hourly solar irradiation forecasting method based on ICEEMDAN and TimesNet networks*. Renewable Energy 220, 119706. DOI [10.1016/j.renene.2023.119706](https://doi.org/10.1016/j.renene.2023.119706). [Editora](https://www.sciencedirect.com/science/article/pii/S096014812301621X). FULL TEXT PENDENTE.

**R5.** Gong, F.; Shan, S.; Wei, H.; Zhang, K. (2024). *Long-term Solar Irradiance Forecasting Based on TimesNet with Multiple Weather Parameters*. 36th Chinese Control and Decision Conference, pp. 6286–6291. DOI [10.1109/CCDC62350.2024.10587733](https://doi.org/10.1109/CCDC62350.2024.10587733). [IEEE](https://ieeexplore.ieee.org/document/10587733); [sumário dos anais](https://www.proceedings.com/content/075/075354webtoc.pdf). FULL TEXT PENDENTE.

**R6.** Guariso, G.; Nunnari, G.; Sangiorgio, M. (2020). *Multi-Step Solar Irradiance Forecasting and Domain Adaptation of Deep Neural Networks*. Energies 13(15), 3987. DOI [10.3390/en13153987](https://doi.org/10.3390/en13153987). [Texto da editora](https://www.mdpi.com/1996-1073/13/15/3987).

**R7.** Cheng, H.-Y.; Yu, C.-C.; Lin, C.-L. (2021). *Day-ahead to week-ahead solar irradiance prediction using convolutional long short-term memory networks*. Renewable Energy 179, 2300–2308. DOI [10.1016/j.renene.2021.08.038](https://doi.org/10.1016/j.renene.2021.08.038). [Editora](https://www.sciencedirect.com/science/article/abs/pii/S096014812101199X). FULL TEXT PENDENTE.

**R8.** Zhu, Y.; Li, M.; Ma, X.; Wang, Y.; Li, G.; Zhang, Y.; Liu, Y.; Hassanien, R. H. E. (2024). *Solar irradiance prediction with variable time lengths and multi-parameters in full climate conditions based on photovoltaic greenhouse*. Energy Conversion and Management 315, 118758. DOI [10.1016/j.enconman.2024.118758](https://doi.org/10.1016/j.enconman.2024.118758). [Editora](https://www.sciencedirect.com/science/article/abs/pii/S019689042400699X); [preprint dos autores](https://ssrn.com/abstract=4823038); [PDF em página institucional de autor](https://scholar.cu.edu.eg/sites/default/files/redagreen/files/energy_conversion_and_management__q1_single_solar_irradiance_prediction_with_variable_time_lengths_and_multi-parameters_in_full_climate_conditions_based_on_photovoltaic_greenhouse.pdf). Texto completo disponível; seções 2.1–2.2 e tabelas de avaliação examinadas, com pendências específicas na seção 5.

**R9.** Cabral, T. W.; Fraidenraich, G.; Capretz, M. A. M. (2026). *Can large language models predict solar irradiance in the long term?* Solar Energy 317, 114964. DOI [10.1016/j.solener.2026.114964](https://doi.org/10.1016/j.solener.2026.114964). [Editora](https://www.sciencedirect.com/science/article/pii/S0038092X26006535). Registro online consultado; fascículo datado de outubro de 2026. Texto publicado em `documentacao/materiais_de_referencia/article_thales.pdf`; páginas 5–11, Algoritmos 2–5 e Tabelas 6 e 9–12 consultados. Horizonte de cinco anos e split mensal confirmados; dúvidas específicas de reprodução estão na seção 5.

**R10.** Smyl, S.; Pełka, P.; Dudek, G. (2026). *Probabilistic Multi-Regional Solar Power Forecasting with Any-Quantile Recurrent Neural Networks*. Preprint arXiv:2602.05660, v1, 5 de fevereiro. DOI [10.48550/arXiv.2602.05660](https://doi.org/10.48550/arXiv.2602.05660). [Texto completo](https://arxiv.org/html/2602.05660v1). Não atribuir DOI nem aceite de periódico.

**R11.** Yu, S.; He, B.; Fang, L. (2025). *Multi-step short-term forecasting of photovoltaic power utilizing TimesNet with enhanced feature extraction and a novel loss function*. Applied Energy 388, 125645. DOI [10.1016/j.apenergy.2025.125645](https://doi.org/10.1016/j.apenergy.2025.125645). [Editora](https://www.sciencedirect.com/science/article/pii/S0306261925003757). FULL TEXT PENDENTE.

**R12.** Shi, C.; Zhao, W.; Zeng, X.-J.; Tseng, C.-H.; Chang, Y. (2026). *2D Time-varying functional modeling framework for multi-scale solar irradiance forecasting*. Neural Networks 196, 108443. DOI [10.1016/j.neunet.2025.108443](https://doi.org/10.1016/j.neunet.2025.108443). [Editora](https://www.sciencedirect.com/science/article/pii/S0893608025013243). FULL TEXT PENDENTE.

**R13.** Wei, X.; Yue, D.; Teng, X.; Hancke, G. P.; Chen, J. (2026). *Multimodal Fusion for Short-Term Solar Irradiance Forecast With Satellite and Extraterrestrial Irradiance Data*. IEEE Transactions on Industrial Informatics. DOI [10.1109/TII.2026.3722536](https://doi.org/10.1109/TII.2026.3722536). [IEEE](https://ieeexplore.ieee.org/abstract/document/11664903/). Resumo via Google Acadêmico; FULL TEXT PENDENTE.

**R14.** Umar, S.; El-Fouly, T. H. M.; Al-Durra, A. (2026). *Multi-horizon daily solar irradiance forecasting with clear-sky cross attention and decorrelated bagging*. Energy Conversion and Management: X 30, 101861. DOI [10.1016/j.ecmx.2026.101861](https://doi.org/10.1016/j.ecmx.2026.101861). Resumo via OpenAlex; periódico aberto, texto não examinado.

**R15.** Li, M.; Wang, C.; Li, J.; Yang, W.; Shen, Y. (2026). *An enhanced monthly GHI prediction framework for China using a hybrid dynamical—machine learning approach*. Theoretical and Applied Climatology. DOI [10.1007/s00704-026-06060-x](https://doi.org/10.1007/s00704-026-06060-x). Resumo da editora.

**R16.** Ayata, F.; Seyyarer, E.; Yüzer, E. Ö. (2026). *Solar Irradiation Prediction Using Time Series Models: Performance Evaluation with Hyperparameter Optimization and K-Fold Cross-Validation*. Journal of Electrical Engineering & Technology. DOI [10.1007/s42835-026-02687-y](https://doi.org/10.1007/s42835-026-02687-y). Resumo da editora.

**R17.** Chen, W.; Zhou, G. (2025). *An interpretable prediction model for global horizontal irradiance based on Improved-Informer*. Measurement 258, 119449. DOI [10.1016/j.measurement.2025.119449](https://doi.org/10.1016/j.measurement.2025.119449). Somente metadados; FULL TEXT PENDENTE.

**R18.** Yu, W.; Dai, Y.; Wang, W.; Ren, T.; Leng, M. (2025). *Short-term photovoltaic forecasting: A parallel TimesNet and AT-Informer-AT method*. Renewable Energy 258, 125012. DOI [10.1016/j.renene.2025.125012](https://doi.org/10.1016/j.renene.2025.125012). Somente metadados; FULL TEXT PENDENTE.

**R19.** Zhang, Y.; Zhang, Y.; Dai, Z.; Zhang, R. (2026). *Rethinking the use of deep learning methods for photovoltaic power forecasting*. Nature Communications. DOI [10.1038/s41467-026-73817-3](https://doi.org/10.1038/s41467-026-73817-3). Resumo registrado na Crossref.

### Roteiro curto para a próxima reunião

1. Discutir o parecer: base defensável para TCC empírico; novidade e vantagem prática ainda precisam ser delimitadas.
2. Mostrar por que GHI-only, longo prazo e várias localidades já têm precedentes, principalmente Guariso e Cabral.
3. Apresentar a hipótese da DilatedRNN compacta, os três resultados terminais favoráveis contra TimesNet e o tamanho real dos ganhos.
4. Mostrar os controles desfavoráveis: Informer e climatologia nos casos mensais, sem esconder vencedores.
5. Definir com o orientador se a contribuição incremental é suficiente ou se a publicação requer custo medido, ablação e validação temporal adicional; solicitar os textos pendentes de Gong, Li e Zhao.

### Notas de fonte do parecer

[^R1]: Chang et al. (2017), *Dilated Recurrent Neural Networks*, [anais oficiais](https://proceedings.neurips.cc/paper_files/paper/2017/hash/32bb90e8976aab5298d5da10fe66f21d-Abstract.html). Arquitetura geral, não um experimento solar.
[^R3]: Li et al. (2025), *Multi-modal feature fusion model based on TimesNet and T2T-ViT for ultra-short-term solar irradiance forecasting*, [DOI](https://doi.org/10.1016/j.renene.2024.122192). Resumo e trechos da editora; texto integral pendente.
[^R4]: Zhao et al. (2024), *Week-ahead hourly solar irradiation forecasting method based on ICEEMDAN and TimesNet networks*, [DOI](https://doi.org/10.1016/j.renene.2023.119706). Resumo e trechos da editora; texto integral pendente.
[^R5]: Gong et al. (2024), *Long-term Solar Irradiance Forecasting Based on TimesNet with Multiple Weather Parameters*, [DOI](https://doi.org/10.1109/CCDC62350.2024.10587733) e [anais](https://www.proceedings.com/content/075/075354webtoc.pdf). Metadados, não protocolo completo.
[^R6]: Guariso et al. (2020), *Multi-Step Solar Irradiance Forecasting and Domain Adaptation of Deep Neural Networks*, [texto primário](https://www.mdpi.com/1996-1073/13/15/3987), seções 2, 3 e 5.
[^R8]: Zhu et al. (2024), *Solar irradiance prediction with variable time lengths and multi-parameters in full climate conditions based on photovoltaic greenhouse*, [DOI](https://doi.org/10.1016/j.enconman.2024.118758), seções 2.1–2.2, páginas 4–5. PDF institucional indicado na referência R8.
[^R9]: Cabral et al. (2026), *Can large language models predict solar irradiance in the long term?*, [DOI](https://doi.org/10.1016/j.solener.2026.114964), páginas 9–11, Algoritmo 5 e Tabelas 6 e 9–12. Cópia publicada local: `documentacao/materiais_de_referencia/article_thales.pdf`.
[^R10]: Smyl et al. (2026), *Probabilistic Multi-Regional Solar Power Forecasting with Any-Quantile Recurrent Neural Networks*, [preprint v1](https://arxiv.org/html/2602.05660v1), seções 2–4. Alvo FV e célula modificada, não DilatedRNN clássica em GHI.
[^R12]: Shi et al. (2026), *2D Time-varying functional modeling framework for multi-scale solar irradiance forecasting*, [DOI](https://doi.org/10.1016/j.neunet.2025.108443). Resumo e trechos metodológicos primários; protocolo completo pendente.

<!-- RESULTADOS_ADICIONAIS_INICIO -->

## 9. Resultados da extensão experimental

Execuções completas e consolidação verificadas. A tentativa ARIMA inicial que falhou foi preservada; a versão final aplica L-BFGS e, somente em caso de não convergência, Powell, sem escolher otimizador por erro de validação ou teste.

Macro-MAE cumulativo terminal (W/m²):

| Modelo | 72 h | 30 d | 1 mês | 6 meses |
|---|---:|---:|---:|---:|
| Persistencia | 58,11 | 60,28 | 35,09 | 91,89 |
| Sazonal ingenuo | 65,90 | 58,78 | 16,94 | 18,00 |
| Climatologia | Não avaliada | 45,51 | 12,57 | 13,03 |
| ARIMA | 134,65 | 50,69 | 16,26 | 19,17 |
| XGBoost | 50,50 | 43,93 | 14,82 | 14,72 |
| GRU | 51,52 | 44,23 | 13,86 | 14,40 |
| LSTM | 53,39 | 44,18 | 14,27 | 14,76 |
| Transformer | 53,22 | 43,88 | 13,12 | 14,43 |
| Informer | 137,72 | 45,47 | 12,85 | 13,88 |
| DilatedRNN | 52,96 | 43,85 | 13,01 | 14,37 |
| TimesNet | 52,48 | 44,08 | 13,89 | 14,46 |

Menor macro-MAE terminal por tarefa:

- hourly_72_extension: XGBoost, 50.5025 W/m².
- daily_30: DilatedRNN, 43.8520 W/m².
- monthly_1: Climatologia, 12.5747 W/m².
- monthly_6: Climatologia, 13.0272 W/m².

Os valores são do protocolo local, não uma comparação de números publicados em datasets diferentes. A interpretação deve considerar também RMSE, MSE, nRMSE, R², sementes e diferenças por localidade.

Rastreabilidade da extensão:

- `resultados/avaliacao_baselines_revisao_20260912/consolidado/metricas_macro.csv`: todas as métricas e checkpoints, cumulativos e leads exatos.
- `consolidado/metricas_por_localidade.csv`: dez localidades, modelos, checkpoints e estimativas individuais/ensemble.
- `consolidado/variabilidade_sementes.csv`: média e desvio padrão amostral por métrica e checkpoint; uma semente não recebe desvio padrão zero artificial.
- Pastas por tarefa/modelo: contratos, hashes, modelos reajustados, históricos, previsões brutas/pós-processadas e status.
- `consolidado/auditoria_consolidacao.json`: preservação dos resultados anteriores e definição da nova coluna MSE.
