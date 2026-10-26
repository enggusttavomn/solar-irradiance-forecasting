# Dados

Os conjuntos versionados permitem reproduzir as análises sem uma nova coleta.
Cada fonte mantém metadados, cobertura temporal e hashes junto aos arquivos.

```text
dados/
├── brutos/
│   ├── localidades_ev/          médias diárias da NSRDB, 2019–2024
│   └── localidades_ev_horario/  séries horárias compactadas, 2019–2024
├── externos/
│   ├── koppen_geiger/           classes climáticas e confiança espacial
│   └── nasa_power/              contexto meteorológico independente
└── processados/localidades_ev/  atributos de fluxos mensais anteriores
```

## Fonte principal

A GHI vem do NLR/NSRDB, produto GOES Aggregated PSM v4. Os CSVs diários e o
manifesto horário registram produto, coordenadas do ponto de grade, intervalo,
agregação, unidade e proveniência. São estimativas modeladas em W/m², não
leituras de sensores instalados nas fábricas.

Os arquivos em `processados/` pertencem a protocolos anteriores. A avaliação
atual reconstrói as entradas a partir dos dados brutos sempre que o contrato da
tarefa assim exige.

## Nova coleta

Uma nova consulta à API é opcional. Copie `.env.example` para `.env`, configure
`NREL_API_KEY` e `NREL_EMAIL` e nunca versione o arquivo com credenciais.

Consulte os READMEs de cada conjunto antes de alterar dados. Mudanças devem
atualizar manifestos e hashes e podem exigir a repetição completa das
avaliações; não substitua silenciosamente os arquivos usados em resultados já
publicados.
