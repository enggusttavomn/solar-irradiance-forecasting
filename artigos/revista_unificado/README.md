# Artigo de revista unificado

Este diretório contém o novo manuscrito de revista construído exclusivamente a
partir de dois trabalhos-base:

- `../ieee/artigo.tex`: TimesNet para previsão horária de GHI;
- `../btsym26/main.tex`: DilatedRNN para previsão mensal de GHI.

O trabalho do MCSM e a aproximação DeepNPTS estão fora do escopo. Os arquivos
originais não devem ser alterados durante a unificação.

`main.tex` é o manuscrito principal no formato Elsevier 5p, Times e duas
colunas. `main_ieee.tex` oferece uma visualização alternativa no formato IEEE,
reutilizando exatamente as mesmas seções.

Os resultados horários e mensais dos trabalhos-base não são diretamente
comparáveis. Por isso, o manuscrito usa os resultados da avaliação
multirresolução executada com amostras, origens, entradas e pós-processamento
compatíveis dentro de cada tarefa. A matriz em `notes/matriz_do_que_falta.md`
registra o estado final das entregas e as limitações que permanecem explícitas.

## Arquivos principais

- `main.tex`: versão Elsevier usada como manuscrito principal;
- `main_ieee.tex`: visualização alternativa que reutiliza as mesmas seções;
- `supplementary_material.tex`: especificação de reprodutibilidade separada do artigo principal;
- `references.bib`: base bibliográfica compartilhada;
- `sections/`, `tables/`, `figures/` e `appendices/`: conteúdo modular do artigo;
- `../../resultados/avaliacao_multirresolucao_corrigida_v2/`: artefatos completos das quatro
  tarefas;
- `../../resultados/artigo_revista_unificado/`: contexto geográfico,
  meteorológico e consolidações usadas no texto.

## Ativos gráficos

O manuscrito inclui PNGs com assinatura binária válida e um diagrama TikZ.
Arquivos SVG podem ser mantidos como fontes vetoriais editáveis, mas devem ser
convertidos para um formato compatível antes de serem incluídos pelo LaTeX.

## Compilação

Em uma instalação TeX com `latexmk`, execute a partir deste diretório:

```text
latexmk -pdf main.tex
latexmk -pdf main_ieee.tex
latexmk -pdf supplementary_material.tex
```

PDFs compilados não são versionados, pois podem ficar divergentes das fontes.
Use uma instalação local de `latexmk` ou o Overleaf para gerar a versão final e
publique o arquivo aprovado como artefato de release ou submissão.

## Atualização automática

Esta pasta é a fonte oficial do projeto Overleaf. A GitHub Action publica as
alterações da branch `main` e da branch de finalização explicitamente autorizada
no workflow; arquivos removidos daqui também são removidos do projeto remoto.

O monitor local agrupa salvamentos consecutivos, cria commits somente desta
pasta na branch de trabalho e os envia ao GitHub. O GitHub permanece como fonte
oficial e aciona a sincronização com o Overleaf.
## Revisão dos resultados e pseudocódigos (06/09/2026)

A comparação principal identifica o vencedor TimesNet/DilatedRNN por tarefa
e horizonte. O benchmark completo permanece no suplemento, incluindo os
modelos que superam as duas arquiteturas. Os números são derivados de
`../../resultados/avaliacao_multirresolucao_corrigida_v2/`; a consolidação
anterior auditada está em
`../../resultados/artigo_revista_unificado/artefatos_resultados_corrigidos_FINAL/`.

- `sections/04_algorithms.tex`: três pseudocódigos conectados ao diagrama.
- `tables/vencedores_por_horizonte.tex`: comparação principal, com diferenças
  calculadas antes do arredondamento.
- `figures/perfis_sete_dias.png`: três perfis de sete dias, compostos por
  previsões de 24 horas emitidas diariamente.
- `../../resultados/artigo_revista_unificado/auditoria_topico5_20260906/RELATORIO.md`:
  auditoria independente das previsões e métricas.
- `../../resultados/artigo_revista_unificado/revisao_20260906/`:
  CSVs e manifesto dos novos elementos de apresentação.

Para reproduzir as tabelas e figuras focais a partir dos dados locais, execute
na raiz `python scripts/gerar_comparacao_focal_artigo.py`. Esse comando usa
previsões salvas e não treina novamente os modelos. Os três documentos foram
compilados com Tectonic nesta revisão.
