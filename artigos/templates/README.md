# Templates parametrizados

Os arquivos desta pasta são fontes internas de
`executaveis/preencher_artigos_canonicos.py`. Eles contêm marcadores `@@...@@` de forma
intencional e não devem ser compilados nem enviados diretamente ao Overleaf.

O gerador pertence ao fluxo mensal histórico. Para validá-lo sem sobrescrever
os manuscritos atuais, escreva as saídas em uma pasta temporária:

```bash
python executaveis/preencher_artigos_canonicos.py \
  --resultados resultados/avaliacao_mensal_canonica \
  --ieee-rascunho artigos/templates/IEEE/artigo_compacto_canonico.tex \
  --ieee-saida resultados/rascunhos_artigos/artigo_ieee.tex \
  --mcsm-rascunho artigos/templates/MCSM/artigo_mcsm_canonico.tex \
  --mcsm-saida resultados/rascunhos_artigos/artigo_mcsm.tex
```

Não aponte esse comando para `artigos/ieee/artigo.tex`: o arquivo atual contém
o manuscrito horário e não corresponde ao template mensal legado.
