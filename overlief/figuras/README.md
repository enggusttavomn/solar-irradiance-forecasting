# Figuras dos artigos

A fonte atual das figuras é exclusivamente:

```text
resultados/avaliacao_mensal_canonica/
```

O gerador canônico produz quatro gráficos na pasta de resultados:

- `mae_medio_modelos.png`: ranking por macro-MAE com IC95% bootstrap entre as
  dez localidades;
- `mae_deepnpts_por_localidade.png`: MAE do DeepNPTS e do melhor concorrente em
  cada localidade;
- `previsao_mensal_byd_camacari.png`: GHI de referência da NSRDB e previsões
  consolidadas no teste de Camaçari;
- `intervalo_deepnpts_byd_camacari.png`: distribuição e intervalo preditivo de
  90% do DeepNPTS em Camaçari.

Para respeitar os limites de páginas, os dois manuscritos citam somente
`previsao_mensal_byd_camacari.png` e
`intervalo_deepnpts_byd_camacari.png`; por isso, apenas esses dois PNGs são
mantidos neste pacote do Overleaf. Os gráficos de ranqueamento e de desempenho
local permanecem preservados em
`../../resultados/avaliacao_mensal_canonica/figuras/`.

Para regenerar e exportar as imagens, execute na raiz do repositório:

```bash
python gerar_figuras_avaliacao_canonica.py \
  --resultados resultados/avaliacao_mensal_canonica
cp resultados/avaliacao_mensal_canonica/figuras/previsao_mensal_byd_camacari.png overlief/figuras/
cp resultados/avaliacao_mensal_canonica/figuras/intervalo_deepnpts_byd_camacari.png overlief/figuras/
```

O gerador lê as previsões, métricas e amostras probabilísticas da execução
concluída; ele não treina modelos nem recalcula resultados científicos. Nos
gráficos, use “GHI de referência” ou “referência NSRDB”, pois os dados são
estimativas modeladas, não medições de solo nas fábricas.

## Arquivos legados

Todos os arquivos com sufixo `_ieee.png` pertencem ao protocolo anterior em
`resultados/avaliacao_mensal_corrigida/`, que avaliava Vizinhos Históricos
Ponderados (VHP). Eles foram retirados do pacote do Overleaf e arquivados em
`../../resultados/avaliacao_mensal_corrigida/figuras_legadas_overleaf/`:

- `mae_medio_modelos_ieee.png`;
- `delta_mae_climatologia_ieee.png`;
- `mae_deepnpts_por_localidade_ieee.png`;
- `previsao_mensal_byd_camacari_ieee.png`.

Esses arquivos não devem ser usados nos artigos atuais, pois seus modelos,
números e conclusões não correspondem ao protocolo canônico com DeepNPTS do
GluonTS e cinco sementes. A pasta
`resultados/avaliacao_mensal_canonica_legado_sem_embeddings/` também é
histórica: nela, os embeddings categóricos do DeepNPTS não eram registrados
corretamente pelo PyTorch.
