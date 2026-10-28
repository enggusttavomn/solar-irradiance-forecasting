# Comparacao dos historicos nas mesmas datas

> Thales, concluí também os testes com o histórico de 1998–2022 e as tabelas por nível estão no PDF histórico. Comparei com um histórico mais curto, começando em abril de 2014, usando as mesmas datas de validação e teste.
>
> Nos controles sem quantização, o histórico longo teve menor MAE em 34 das 44 combinações de modelo e caso, maior em 2 e diferença praticamente nula em 8. Essa comparação ajuda a avaliar o efeito do histórico, mas não demonstra que a causa seja variação climática nem reproduz integralmente o estudo do Luís.

Contagens descritivas no horizonte completo de cada caso; sem teste de significância. Empate numérico: diferença absoluta de MAE até 0,0000001 W/m². Os níveis de quantização permanecem detalhados no PDF.

| Caso | Modelo | MAE curto | MAE longo | Diferença W/m² |
|---|---|---:|---:|---:|
| Diário | ARIMA | 50,3377 | 50,0599 | -0,2779 |
| Diário | Climatologia | 46,6632 | 44,1234 | -2,5398 |
| Diário | DilatedRNN | 44,9736 | 44,0460 | -0,9275 |
| Diário | GRU | 44,5292 | 43,7646 | -0,7646 |
| Diário | Informer | 46,0223 | 43,5925 | -2,4297 |
| Diário | LSTM | 44,2693 | 43,2834 | -0,9860 |
| Diário | Persistencia | 59,6428 | 59,6428 | 0,0000 |
| Diário | Sazonal ingenuo | 56,8612 | 56,8612 | 0,0000 |
| Diário | TimesNet | 42,7122 | 42,3306 | -0,3816 |
| Diário | Transformer | 44,6667 | 44,4850 | -0,1817 |
| Diário | XGBoost | 44,1016 | 43,9268 | -0,1747 |
| Horário | ARIMA | 137,8963 | 138,1525 | 0,2562 |
| Horário | Climatologia | 55,0566 | 52,2497 | -2,8070 |
| Horário | DilatedRNN | 56,4941 | 55,8311 | -0,6630 |
| Horário | GRU | 52,2633 | 51,4303 | -0,8330 |
| Horário | Informer | 136,2112 | 60,8980 | -75,3132 |
| Horário | LSTM | 53,7187 | 61,6058 | 7,8871 |
| Horário | Persistencia | 59,1608 | 59,1608 | 0,0000 |
| Horário | Sazonal ingenuo | 65,3341 | 65,3341 | 0,0000 |
| Horário | TimesNet | 48,4050 | 47,8749 | -0,5301 |
| Horário | Transformer | 55,4797 | 52,3673 | -3,1124 |
| Horário | XGBoost | 51,3435 | 50,6888 | -0,6547 |
| Mensal de um mês | ARIMA | 20,5531 | 16,6368 | -3,9163 |
| Mensal de um mês | Climatologia | 13,9241 | 13,6444 | -0,2797 |
| Mensal de um mês | DilatedRNN | 15,2153 | 13,4320 | -1,7834 |
| Mensal de um mês | GRU | 16,0544 | 15,0455 | -1,0090 |
| Mensal de um mês | Informer | 16,2183 | 13,8831 | -2,3352 |
| Mensal de um mês | LSTM | 15,4460 | 14,6593 | -0,7867 |
| Mensal de um mês | Persistencia | 35,4874 | 35,4874 | 0,0000 |
| Mensal de um mês | Sazonal ingenuo | 16,9889 | 16,9889 | 0,0000 |
| Mensal de um mês | TimesNet | 14,9431 | 14,1121 | -0,8310 |
| Mensal de um mês | Transformer | 16,3974 | 14,0825 | -2,3150 |
| Mensal de um mês | XGBoost | 14,9807 | 14,7338 | -0,2470 |
| Mensal exploratório de seis meses | ARIMA | 20,6923 | 16,2717 | -4,4206 |
| Mensal exploratório de seis meses | Climatologia | 14,0615 | 13,6813 | -0,3802 |
| Mensal exploratório de seis meses | DilatedRNN | 15,0680 | 14,2795 | -0,7885 |
| Mensal exploratório de seis meses | GRU | 15,4633 | 14,7668 | -0,6965 |
| Mensal exploratório de seis meses | Informer | 16,2222 | 14,7247 | -1,4975 |
| Mensal exploratório de seis meses | LSTM | 15,3925 | 15,0537 | -0,3388 |
| Mensal exploratório de seis meses | Persistencia | 85,8955 | 85,8955 | 0,0000 |
| Mensal exploratório de seis meses | Sazonal ingenuo | 17,4737 | 17,4737 | 0,0000 |
| Mensal exploratório de seis meses | TimesNet | 15,9145 | 14,8686 | -1,0459 |
| Mensal exploratório de seis meses | Transformer | 17,1950 | 14,9112 | -2,2838 |
| Mensal exploratório de seis meses | XGBoost | 15,7094 | 15,2320 | -0,4774 |
