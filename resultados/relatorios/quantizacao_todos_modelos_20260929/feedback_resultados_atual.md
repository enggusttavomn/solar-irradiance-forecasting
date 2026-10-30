# Resultados da quantização de todos os modelos

Fonte: auditoria completa das previsões e dos checkpoints. Contagem no horizonte completo de cada caso.

> Bom dia, Thales! Concluí os testes de todos os modelos nos quatro casos, mantendo o min-max e comparando 64, 128 e 256 níveis com o controle sem quantização. As tabelas do PDF estão separadas por nível, com todos os modelos juntos.
>
> Considerando as escolhas feitas pela validação, 13 combinações de modelo e caso melhoraram no teste, 21 pioraram e 0 ficaram praticamente iguais. Em outras 10, a validação manteve a opção sem quantização. Esses números descrevem os erros observados; não foi realizado teste de significância estatística.

| Caso | Modelo | Escolha na validação | MAE sem quantização | MAE da escolha | Diferença (%) |
|---|---|---|---:|---:|---:|
| Diário | ARIMA | 256 níveis | 50,6903 | 50,6819 | -0,0167 |
| Diário | Climatologia | 64 níveis | 45,5125 | 45,5265 | 0,0308 |
| Diário | DilatedRNN | 256 níveis | 44,0686 | 44,1353 | 0,1514 |
| Diário | GRU | 64 níveis | 44,2309 | 44,2369 | 0,0135 |
| Diário | Informer | 64 níveis | 45,4674 | 45,4603 | -0,0158 |
| Diário | LSTM | Sem quantização | 44,1842 | 44,1842 | 0,0000 |
| Diário | Persistencia | 128 níveis | 60,2759 | 60,2787 | 0,0047 |
| Diário | Sazonal ingenuo | 64 níveis | 58,7765 | 58,8458 | 0,1180 |
| Diário | TimesNet | 64 níveis | 42,1708 | 42,1655 | -0,0124 |
| Diário | Transformer | 256 níveis | 43,8807 | 43,8869 | 0,0141 |
| Diário | XGBoost | Sem quantização | 43,9335 | 43,9335 | 0,0000 |
| Horário | ARIMA | 128 níveis | 134,6525 | 134,6937 | 0,0306 |
| Horário | Climatologia | Sem quantização | 52,8731 | 52,8731 | 0,0000 |
| Horário | DilatedRNN | Sem quantização | 55,6725 | 55,6725 | 0,0000 |
| Horário | GRU | 256 níveis | 51,5246 | 51,5279 | 0,0064 |
| Horário | Informer | Sem quantização | 137,6798 | 137,6798 | 0,0000 |
| Horário | LSTM | 64 níveis | 54,0947 | 53,5241 | -1,0548 |
| Horário | Persistencia | Sem quantização | 58,1088 | 58,1088 | 0,0000 |
| Horário | Sazonal ingenuo | Sem quantização | 65,8965 | 65,8965 | 0,0000 |
| Horário | TimesNet | 256 níveis | 47,9145 | 47,9179 | 0,0071 |
| Horário | Transformer | Sem quantização | 53,2061 | 53,2061 | 0,0000 |
| Horário | XGBoost | Sem quantização | 50,3955 | 50,3955 | 0,0000 |
| Mensal de um mês | ARIMA | 64 níveis | 16,2555 | 16,2463 | -0,0565 |
| Mensal de um mês | Climatologia | 256 níveis | 12,5747 | 12,5668 | -0,0627 |
| Mensal de um mês | DilatedRNN | 128 níveis | 13,0054 | 13,1694 | 1,2611 |
| Mensal de um mês | GRU | Sem quantização | 13,8648 | 13,8648 | 0,0000 |
| Mensal de um mês | Informer | 128 níveis | 12,8481 | 12,7266 | -0,9461 |
| Mensal de um mês | LSTM | 128 níveis | 14,2711 | 14,2883 | 0,1202 |
| Mensal de um mês | Persistencia | 256 níveis | 35,0877 | 35,0555 | -0,0916 |
| Mensal de um mês | Sazonal ingenuo | 128 níveis | 16,9428 | 17,0002 | 0,3383 |
| Mensal de um mês | TimesNet | 256 níveis | 13,8561 | 13,9215 | 0,4718 |
| Mensal de um mês | Transformer | 128 níveis | 13,1196 | 13,1467 | 0,2059 |
| Mensal de um mês | XGBoost | 64 níveis | 14,8171 | 14,8154 | -0,0113 |
| Mensal exploratório de seis meses | ARIMA | 64 níveis | 19,1673 | 18,6639 | -2,6263 |
| Mensal exploratório de seis meses | Climatologia | 128 níveis | 13,0272 | 13,0300 | 0,0219 |
| Mensal exploratório de seis meses | DilatedRNN | 128 níveis | 14,3692 | 14,3525 | -0,1164 |
| Mensal exploratório de seis meses | GRU | 128 níveis | 14,3988 | 14,4006 | 0,0127 |
| Mensal exploratório de seis meses | Informer | 128 níveis | 13,8803 | 13,6679 | -1,5305 |
| Mensal exploratório de seis meses | LSTM | 128 níveis | 14,7565 | 14,7623 | 0,0387 |
| Mensal exploratório de seis meses | Persistencia | 64 níveis | 91,8868 | 91,9732 | 0,0940 |
| Mensal exploratório de seis meses | Sazonal ingenuo | 256 níveis | 18,0012 | 18,0286 | 0,1523 |
| Mensal exploratório de seis meses | TimesNet | 128 níveis | 14,1975 | 14,2176 | 0,1417 |
| Mensal exploratório de seis meses | Transformer | 64 níveis | 14,4302 | 14,3965 | -0,2335 |
| Mensal exploratório de seis meses | XGBoost | 256 níveis | 14,7222 | 14,7663 | 0,2998 |

Diferença negativa indica menor MAE. Resultados de 2024 e experimentos históricos são retrospectivos. A comparação com o artigo do Luís continua limitada pelas diferenças de locais, agregação e divisão dos dados.

Empate numérico neste resumo: diferença absoluta de MAE até 0,0000001 W/m². Esse critério não é um teste de significância.

O XGBoost horário usa um novo controle de treinamento final, repetido integralmente e auditado. A execução antiga apresentou divergência de causa ainda não identificada. As escolhas da validação foram preservadas; os efeitos da quantização são comparados ao controle desta rodada.
