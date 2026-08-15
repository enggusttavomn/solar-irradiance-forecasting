# Dados

```text
dados/
├── brutos/localidades_ev/       # medias diarias preservadas da NSRDB
└── processados/localidades_ev/  # atributos derivados de fluxos anteriores
```

A avaliacao mensal canonica le os CSVs diarios de `brutos/localidades_ev/` e
constroi a base mensal em memoria. A proveniencia, o produto, a unidade, o
intervalo da consulta e as coordenadas do ponto de grade permanecem registrados
nos proprios CSVs.

Os arquivos com sufixo `_v2` e outras tabelas processadas pertencem a fluxos
anteriores e nao substituem os CSVs brutos usados pelo protocolo canonico.
