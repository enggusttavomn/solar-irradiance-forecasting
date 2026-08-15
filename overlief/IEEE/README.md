# Artigo IEEE — previsão horária com TimesNet

O manuscrito autoritativo é `artigo.tex`. Ele não pertence ao MCSM e usa
exclusivamente os artefatos de:

```text
../../resultados/avaliacao_horaria_timesnet/
```

As duas imagens usadas pelo manuscrito ficam exclusivamente em `figuras/`:
`previsao_horaria_timesnet_72h.png`, com o exemplo temporal, e
`comparacao_rmse_modelos.png`, com a evolução do RMSE e a comparação por
localidade. As figuras do MCSM permanecem em `../MCSM/figuras/`.

`artigoexemplo1.pdf`, `artigoexemplo2.pdf` e `artigoexemplo3.pdf` são
referências editoriais de estrutura, densidade, argumentação e paginação
fornecidas pelo orientador e devem ser preservadas nesta pasta. O terceiro
exemplo também é citado como trabalho complementar de previsão de GHI em longo
prazo, sem transferir seus dados, modelos ou resultados para este experimento
horário. Os PDFs de exemplo não são dependências da compilação: para enviar ao
Overleaf, bastam `artigo.tex` e a pasta `figuras/`.

O manuscrito compara quatro métodos: persistência diária, sazonal ingênuo
anual, LSTM e TimesNet. A entrada contém 336 horas, a saída contém 72 horas e
os prefixos de 24, 48 e 72 horas são avaliados. A divisão
cronológica é 2019–2022 para treino, 2023 para escolher o número de épocas das
redes, 2019–2023 para reajuste e 2024 para teste. A execução canônica usa uma
semente, 42.

No recorte publicado, o TimesNet apresenta o menor RMSE macro nos três
horizontes, seguido por LSTM, persistência e sazonal ingênuo. Em 72 horas, os
RMSEs das duas redes são 101,04 e 104,68 W/m², respectivamente. O experimento
bruto preserva comparadores adicionais para auditoria, mas o sincronizador do
artigo filtra deliberadamente apenas os quatro métodos pertencentes ao escopo
editorial e nunca reescreve os CSVs científicos.

## Reprodução

Instale a extensão de dependências do experimento horário:

```bash
pip install -r requirements_horario_timesnet.txt
```

Na raiz do repositório, a coleta horária pode ser reproduzida com:

```bash
python coletar_dados_horarios_nsrdb.py --inicio 2019 --fim 2024
```

A avaliação completa é executada com:

```bash
python executar_avaliacao_horaria_timesnet.py \
  --modo completa \
  --confirmar-execucao-longa \
  --saida resultados/avaliacao_horaria_timesnet
```

O experimento exporta métricas gerais e diurnas, previsões brutas e
pós-processadas, checkpoints e manifesto. Para atualizar automaticamente os
blocos numéricos do manuscrito e regenerar as duas figuras publicadas no pacote
do Overleaf:

```bash
python atualizar_artigo_ieee_timesnet.py
```

Para apenas conferir se o artigo está sincronizado, sem escrever:

```bash
python atualizar_artigo_ieee_timesnet.py --verificar
```

Compile `artigo.tex` duas vezes com pdfLaTeX no Overleaf ou localmente com uma
distribuição que contenha `IEEEtran.cls`.

## Cuidado com o gerador legado

`../../preencher_artigos_canonicos.py` e
`../../templates_artigos/IEEE/artigo_compacto_canonico.tex` ainda descrevem o
experimento mensal antigo. Não execute esse gerador apontando para
`overlief/IEEE/artigo.tex`, pois ele sobrescreverá o manuscrito horário. Os
arquivos do MCSM e suas figuras também são independentes e não devem ser
alterados por este fluxo.
