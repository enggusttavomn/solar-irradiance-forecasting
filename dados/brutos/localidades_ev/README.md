# Dados das Localidades EV

Os CSVs desta pasta precisam ter proveniencia NLR/NSRDB validada antes de serem usados no treinamento.

A serie oficial usada atualmente cobre de 2019-01-01 a 2024-12-31. Em junho de
2026, o produto GOES Aggregated PSM v4 ainda nao publicou o ano de 2025.

Formato esperado:

```csv
data,ghi,localidade,pais,lat,lon,ano,fonte_dados,produto_dados,versao_dados,endpoint_api,intervalo_minutos,agregacao,unidade_ghi,lat_grade_nsrdb,lon_grade_nsrdb
2019-01-01,304.98,BYD Camacari,Brasil,-12.6977,-38.324,2019,NLR/NSRDB,GOES Aggregated PSM v4,4.1.2,https://developer.nlr.gov/api/nsrdb/v2/solar/nsrdb-GOES-aggregated-v4-0-0-download.csv,60,media_diaria,W/m2,-12.7,-38.32
```

Arquivos com `localidade` no formato `lat_*_lon_*`, cobertura incompleta, GHI
fora da unidade declarada ou sem os metadados NLR/NSRDB devem ser considerados
invalidos.

Comandos:

```bash
python treinar_todas_localidades.py --validar-dados
python treinar_todas_localidades.py --somente-download --forcar-download
```
