# Artigo IEEE

O manuscrito IEEE atual é:

```text
artigo.tex
```

Sua única fonte numérica válida é
`../../resultados/avaliacao_mensal_canonica/`, execução completa de 19 de
julho de 2026. O molde parametrizado foi mantido fora do pacote do Overleaf,
em `../../templates_artigos/IEEE/artigo_compacto_canonico.tex`, para evitar
que seja compilado por engano. Seus marcadores são preenchidos por
`../../preencher_artigos_canonicos.py`. Não copie valores manualmente de
outras pastas.

O protocolo compara três referências (persistência, sazonal ingênuo e
climatologia) com sete modelos globais: XGBoost, MLP, RNN, LSTM, DilatedRNN,
DeepAR e o DeepNPTS discreto do GluonTS 0.16.2. Cada modelo aprendido foi
executado com as sementes 11, 23, 42, 67 e 89. O teste retrospectivo contém 12
origens de um mês à frente em 2024, sem reajuste dos modelos.

O DeepNPTS é o estimador neural probabilístico do GluonTS, não o antigo
regressor VHP. A única correção local registra os embeddings categóricos como
`torch.nn.ModuleList`, de modo que sejam otimizados e persistidos. Arquitetura,
função de avanço, distribuição discreta e RPS normalizado permanecem os do
estimador oficial.

## Resultado que deve constar no manuscrito

O ranking final por macro-MAE é:

1. Climatologia: 12,071 W/m²;
2. LSTM: 12,222 W/m²;
3. RNN: 12,554 W/m²;
4. DilatedRNN: 13,422 W/m²;
5. DeepAR: 14,182 W/m²;
6. XGBoost: 14,573 W/m²;
7. MLP: 16,059 W/m²;
8. sazonal ingênuo: 16,943 W/m²;
9. DeepNPTS: 17,701 W/m²;
10. persistência: 35,088 W/m².

O DeepNPTS apresentou desvio-padrão de 9,223 W/m² no MAE entre sementes e não
venceu nenhuma localidade. Em avaliação probabilística, obteve CRPS de 15,904
W/m², cobertura de 90,83% para o intervalo nominal de 90% e largura média de
145,556 W/m². Esses números devem ser discutidos como resultado retrospectivo
do protocolo, sem alegação de superioridade universal.

O artigo IEEE não pertence ao III MCSM e, portanto, não deve incluir o
agradecimento específico à FAPEMIG exigido pelo template desse congresso.

## Figuras

As figuras canônicas ficam em `../figuras/` e são regeneradas por:

```bash
python ../../gerar_figuras_avaliacao_canonica.py \
  --resultados ../../resultados/avaliacao_mensal_canonica
cp ../../resultados/avaliacao_mensal_canonica/figuras/previsao_mensal_byd_camacari.png ../figuras/
cp ../../resultados/avaliacao_mensal_canonica/figuras/intervalo_deepnpts_byd_camacari.png ../figuras/
```

Use os arquivos sem o sufixo `_ieee`: eles vêm do protocolo canônico. Os
arquivos `*_ieee.png` pertencem à rodada VHP e são legados.

## Atualização e compilação

Para preencher novamente o manuscrito a partir dos CSVs finais, execute na
raiz do repositório:

```bash
python preencher_artigos_canonicos.py \
  --resultados resultados/avaliacao_mensal_canonica \
  --ieee-rascunho templates_artigos/IEEE/artigo_compacto_canonico.tex \
  --ieee-saida overlief/IEEE/artigo.tex \
  --mcsm-rascunho templates_artigos/MCSM/artigo_mcsm_canonico.tex \
  --mcsm-saida overlief/MCSM/artigo_mcsm.tex
```

Depois, compile `artigo.tex` duas vezes com pdfLaTeX no Overleaf ou localmente
com uma distribuição que contenha `IEEEtran.cls`. Antes de submeter, confirme
ausência de marcadores `@@...@@`, referências indefinidas e caixas
`Overfull`.

As limitações que não podem ser removidas do texto são: histórico de apenas
seis anos, 48 alvos de treino e 12 de teste por localidade, janela de 2024 já
inspecionada durante o desenvolvimento, dez pontos não aleatórios, NSRDB como
referência modelada, inexistência das respostas horárias brutas e forte
variabilidade do DeepNPTS entre sementes.
