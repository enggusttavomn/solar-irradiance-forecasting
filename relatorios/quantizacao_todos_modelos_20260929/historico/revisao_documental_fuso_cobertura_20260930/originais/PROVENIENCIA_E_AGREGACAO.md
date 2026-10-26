# Base NSRDB ampliada: proveniencia e agregacao

Estado: coleta, agregacao e auditoria independente concluidas e aprovadas.
`status_coleta.json` registra `status: concluido` e
`auditoria_historico_independente.json` registra `ok: true`. O contrato principal
`contrato_historico_pareado.json` registra `ok: true` e `aprovado: true`, os cortes
temporais e hashes de todas as entradas. Nenhum treinamento historico foi
iniciado nesta preparacao; a primeira entrega dos modelos na base atual precede
a execucao historica.

Foram conferidos 2.191.440 registros horarios, 91.310 diarios e 3.000 mensais.
Por localidade: 219.144 horas, 9.131 dias e 300 meses. Os 17 arquivos originais
verificados permaneceram inalterados.

## Fonte e cobertura

- Mesmo cadastro das dez localidades do projeto, com os mesmos IDs NSRDB,
  coordenadas da grade e fusos horarios fixos (UTC-8 a UTC-3).
- Produto GOES Aggregated PSM v4, pasta publica `GOES/aggregated/v4.0.0`.
- Periodo solicitado: 1998--2022, inclusive (25 anos).
- A sondagem dos 25 arquivos retornou HTTP 200, e os 25 testes de leitura
  parcial retornaram HTTP 206 e a assinatura HDF5 esperada.
- A fonte completa totaliza aproximadamente 40 TB. Nenhum HDF5 anual completo
  e baixado: sao lidos apenas os blocos que contem os dez pontos.
- O primeiro smoke levou 159 segundos e transferiu 283 MB. O cache otimizado
  reduziu isso para aproximadamente 80 segundos e 194 MB por ano.
- Horario de 2019--2022 e referenciado na pasta original, com hashes verificados;
  nao ha copia nem substituicao desses quatro arquivos anuais.

Fontes oficiais:

- [Documentacao GOES Aggregated PSM v4](https://developer.nlr.gov/docs/solar/nsrdb/nsrdb-GOES-aggregated-v4-0-0-download/):
  cobertura desde 1998, grade de 4 km e amostras de 30 minutos.
- [Registro publico NSRDB no AWS](https://registry.opendata.aws/nrel-pds-nsrdb/):
  bucket publico e acesso sem conta AWS.

## Horario, diario e mensal usam definicoes preservadas

**Horario:** media das amostras dos minutos 00 e 30, para cada hora UTC.
Inclui as horas noturnas. Esse e o contrato horario que ja existia no projeto.

**Diario:** a API original foi chamada com `intervalo_minutos=60` e `utc=False`.
Na sobreposicao de 2019, os dados originais foram reproduzidos pela media de
24 amostras no minuto 30, em horario local fixo. Usar a media de 48 amostras
ou selecionar o minuto 00 nao reproduziu o diario original. A verificacao de
2019--2022 foi aprovada em 14.610 observacoes: diferenca maxima de
2,84e-14 W/m2 em float64 e igualdade exata em float32, a precisao usada nos
modelos.

Por isso, o diario historico e reconstruido diretamente das amostras de
30 minutos, selecionando o minuto 30 de cada hora. Ele **nao** e calculado a
partir da media horaria 00/30. Mantem-se a definicao anterior de cada estudo,
sem juntar series que usam amostragens distintas.

**Mensal:** media aritmetica dos dias completos de cada mes civil, a partir
desse diario compativel com a API. Sao 300 meses por localidade.

## Fronteira anual da API e fuso fixo

O deslocamento de UTC para hora local no contrato observado da API e circular
dentro de cada ano. Com fuso UTC-8, por exemplo, as amostras UTC de 1/janeiro,
00:30--07:30, sao reutilizadas no rotulo local de 31/dezembro do mesmo ano,
16:30--23:30. Para UTC-3, sao tres amostras, rotuladas como 21:30--23:30.

Essa convencao replica a fonte diaria ja usada; **nao representa uma media
local continua entre arquivos de anos consecutivos**. Nao se usa horario de
verao. O relatorio registra as 250 fronteiras (25 anos x 10 localidades), seus
horarios de origem e, quando existe o ano seguinte, a diferenca para a media
continua. Entre as 240 fronteiras comparaveis de 1998--2021, 49 tiveram alguma
diferenca; a maior foi 1,5833 W/m2 na media diaria de 31/dezembro. As dez
fronteiras de 31/dezembro/2022 foram marcadas explicitamente como nao
comparaveis: a fonte 30min de 2023 nao foi incorporada ao periodo solicitado.

Como todos os fusos sao negativos, o preenchimento circular de dezembro usa
amostras de janeiro do mesmo ano, anteriores ao alvo. Isso nao introduz
observacoes do ano seguinte. Nao ha interpolacao ou criacao de valores GHI.

## Integridade e correcao de metadado do cache inicial

- Fonte de 30 minutos e serie horaria conferidas por ano: datas exatas,
  bissextos, continuidade, duplicatas, GHI finita e nao negativa, grade e fuso.
- Cache e arquivos originais conferidos por SHA-256; qualquer divergencia
  interrompe a coleta em vez de sobrescrever silenciosamente.
- O primeiro teste de retomada detectou que o pandas 3 havia serializado
  microssegundos em um campo do cache nomeado `timestamp_ns`. Corrigiu-se a
  serializacao para nanossegundos explicitos. Os tres caches iniciais foram
  preservados em `cache_inicial_microsegundos/`; o relatorio
  `correcao_unidade_temporal_cache.json` comprova que todos os valores GHI
  permaneceram identicos bit a bit. Nenhum arquivo original foi modificado.
- A suite possui 14 testes, incluindo regressao com precisao ms/us/ns.
- A auditoria final independente reconstruiu as agregacoes com indices UTC
  modulares e somas por dia, sem chamar o agregador de producao. Diferencas
  maximas: zero no horario, 2,84e-14 W/m2 no diario e 5,68e-14 W/m2 no mensal.
  A faixa das amostras GHI de 30 minutos foi de 0 a 1157 W/m2, sem sentinelas
  uint16, valores ausentes ou negativos.

## Uso na comparacao de historicos

O protocolo combinado com a execucao dos modelos reserva abril/2019 a
dezembro/2022 para teste: 45 dos 300 meses, ou 15% da base. A validacao fica
em abril/2018 a marco/2019, dentro dos 85% anteriores ao teste.

O treino longo comeca em janeiro/1998; a comparacao curta comeca em abril/2014,
mantendo as mesmas datas de validacao e teste. Essa comparacao permite estudar
o efeito de disponibilizar mais historico sem trocar os alvos de avaliacao.
A quantidade de exemplos efetivos ainda depende das janelas e horizontes de
cada modelo. A comparacao nao demonstra, sozinha, uma causa climatica.
