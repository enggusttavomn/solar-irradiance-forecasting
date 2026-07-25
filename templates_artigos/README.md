# Moldes parametrizados dos artigos

Estes arquivos são fontes internas do gerador
`preencher_artigos_canonicos.py`. Eles contêm marcadores `@@...@@` de forma
intencional e **não devem ser compilados nem enviados ao Overleaf**.

Os arquivos prontos para edição e compilação são exclusivamente:

- `overlief/IEEE/artigo.tex`;
- `overlief/MCSM/artigo_mcsm.tex`.

Para atualizar ambos a partir da execução canônica, execute na raiz:

```bash
python preencher_artigos_canonicos.py \
  --resultados resultados/avaliacao_mensal_canonica \
  --ieee-rascunho templates_artigos/IEEE/artigo_compacto_canonico.tex \
  --ieee-saida overlief/IEEE/artigo.tex \
  --mcsm-rascunho templates_artigos/MCSM/artigo_mcsm_canonico.tex \
  --mcsm-saida overlief/MCSM/artigo_mcsm.tex
```
