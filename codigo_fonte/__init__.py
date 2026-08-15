"""Pacote principal do projeto de previsao diaria e mensal de GHI.

Os modulos deste pacote separam as responsabilidades do pipeline:

* ``preprocessamento`` le, limpa e transforma a serie;
* ``features`` converte a serie em uma base supervisionada;
* ``modelos`` treina XGBoost, MLP, RNN, LSTM e vizinhos historicos;
* ``baselines`` implementa persistencia, sazonal ingenuo e climatologia;
* ``avaliacao`` calcula metricas pontuais/probabilisticas e salva previsoes;
* ``graficos`` gera as figuras de avaliacao.

Manter a logica nos modulos, em vez de somente nos notebooks, permite testar e
reutilizar o mesmo comportamento nos dois scripts de treinamento.
"""
