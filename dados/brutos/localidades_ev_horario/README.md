# GHI horário das localidades EV

Esta pasta contém a nova base horária usada exclusivamente pelo experimento
TimesNet do artigo IEEE. Ela não substitui os CSVs diários do protocolo
anterior.

- Fonte: bucket público NLR/NSRDB no AWS Open Data.
- Produto: GOES Aggregated PSM v4, versão HDF5 4.0.0.
- Cobertura: 2019-01-01 00:00 UTC a 2024-12-31 23:00 UTC.
- Pontos: os mesmos dez `site_id_nsrdb` já auditados nos CSVs diários.
- Resolução nativa: 30 minutos.
- Resolução de modelagem: média de cada par de observações em uma hora.
- Unidade: W/m².
- Total: 526.080 valores, 52.608 por localidade.

Os arquivos anuais comprimidos permitem retomada e evitam baixar novamente
dados já validados. O `manifesto_horario.json` registra hashes SHA-256.

Para reproduzir a coleta:

```bash
python coletar_dados_horarios_nsrdb.py --inicio 2019 --fim 2024
```

O coletor lê somente os blocos HDF5 correspondentes às dez localidades; os
arquivos anuais completos, com aproximadamente 1,6 TB cada, não são baixados.
