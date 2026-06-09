"""Pacote principal do projeto de previsao diaria de GHI.

Os modulos deste pacote separam as responsabilidades do pipeline:

* ``preprocessamento`` le, limpa e transforma a serie;
* ``features`` converte a serie em uma base supervisionada;
* ``modelos`` treina XGBoost e MLP;
* ``avaliacao`` calcula metricas e salva previsoes;
* ``graficos`` gera as figuras de avaliacao.

Manter a logica nos modulos, em vez de somente nos notebooks, permite testar e
reutilizar o mesmo comportamento nos dois scripts de treinamento.
"""
