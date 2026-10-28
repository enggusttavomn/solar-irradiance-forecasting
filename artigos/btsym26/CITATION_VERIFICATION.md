# Citation verification for the BTSym'26 article

This note records the sources used by `main.tex` and the local
evidence used for experimental claims in the BTSym'26 submission.

## External references

- Chang et al. (2017) supports the definition and motivation of dilated
  recurrent connections. The article explicitly states that the local
  implementation reproduces the skipped-state operation, not the complete
  original architecture.
- Ozoegwu (2019) supports the discussion of monthly solar-resource
  forecasting with lagged observations and calendar information in neural
  autoregressive models.
- Jung et al. (2020) supports the discussion of recurrent modeling across
  multiple sites using monthly irradiation and site-dependent inputs.
- Salinas et al. (2020) supports the global autoregressive and probabilistic
  characterization of DeepAR. The experiment reports only its median point
  forecast, so no probabilistic metric is attributed to that reference.
- Sengupta et al. (2018) supports the modeled, satellite-derived nature of the
  NSRDB data and the physical interpretation of GHI.
- The National Laboratory of the Rockies API documentation identifies the
  GOES Aggregated PSM v4 product and its available temporal resolutions.
- Voyant et al. (2017, 2022) supports the forecasting context and the need for
  comparisons with simple, horizon-appropriate baselines.
- Hyndman and Koehler (2006) supports the forecast-error measures used as the
  primary comparison. The definitions of R² and the adopted nRMSE
  normalization are explicitly given in the article rather than attributed
  solely to that source.
- Hewamalage, Bergmeir, and Bandara (2021) supports the statement that RNN
  forecast performance depends on design and evaluation choices, including
  input construction and the forecasting protocol.
- Montero-Manso and Hyndman (2021) supports the characterization of global
  forecasting methods and the caution that parameter sharing does not require
  identical series or imply an inherent representational advantage over local
  methods.

## Local experimental evidence

- Architecture and training protocol:
  `../../codigo_fonte/dados_mensais_globais.py` and
  `../../codigo_fonte/modelos_neurais_globais.py`.
- Executed hyperparameters and seeds:
  `../../resultados/avaliacao_mensal_canonica/hiperparametros_executados.csv`
  and `manifesto_execucao.json` in the same directory.
- Overall metrics:
  `../../resultados/avaliacao_mensal_canonica/metricas_medias_modelos.csv`.
- Local and seed-level metrics:
  `../../resultados/avaliacao_mensal_canonica/metricas_por_localidade.csv` and
  `metricas_por_localidade_seed.csv`.
- Temporal forecasts and seed variability:
  `../../resultados/avaliacao_mensal_canonica/previsoes_consolidadas.csv` and
  `previsoes_por_modelo_seed.csv`.
- The paired win/loss counts, mean absolute-error gaps, and threshold counts
  were recomputed from
  `../../resultados/avaliacao_mensal_canonica/previsoes_consolidadas.csv`.
- Data-integrity counts:
  `../../resultados/avaliacao_mensal_canonica/auditoria_dados.csv`.
- Factory-to-grid mapping, NSRDB site identifiers, collection metadata, and
  source-file hashes: `../../dados/brutos/localidades_ev/manifesto_nsrdb.csv`.
- Software versions, file hashes, and execution metadata:
  `../../resultados/avaliacao_mensal_canonica/manifesto_execucao.json`.

The paper reports only the models and metrics included in its declared final
comparison and contains no unsupported probabilistic uncertainty claim.
