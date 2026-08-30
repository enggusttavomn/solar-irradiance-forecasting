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