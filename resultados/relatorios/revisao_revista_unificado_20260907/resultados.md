# Auditoria de resultados — revista unificada — 7 de setembro de 2026

## Conclusão

Os resultados apresentados no resumo, nas seções 07–09 e nas tabelas incluídas no artigo principal e no suplemento conferem com as previsões canônicas salvas. A auditoria independente repetida nesta revisão aprovou 276 verificações, sem falhas: 725.700 linhas de previsões de validação/teste, 10.440 linhas de métricas locais e 1.044 linhas macro. A maior diferença absoluta em MAE, RMSE, nRMSE ou R² foi 3,552713678800501e-14, abaixo da tolerância de 1e-8. Nenhum modelo foi treinado.

Foi encontrada e corrigida uma tabela residual: `artigos/revista_unificado/tables/terminal_location_comparison.tex`. Ela continha 29 valores de MAE de TimesNet desatualizados nas colunas horária e mensais. Os valores foram substituídos pelos canônicos; os 40 grupos local/tarefa, incluindo ambas as arquiteturas e o vencedor, foram conferidos após a edição. Não houve alteração dos vencedores. Esse arquivo não é incluído por `main.tex`, `main_ieee.tex` ou `supplementary_material.tex`; por isso, a correção não muda os resultados dos documentos principais. O formato foi preservado.

## Evidências verificadas

- **Vencedores do benchmark completo:** XGBoost em 24/48/72 horas e em 1/3/14 dias; LSTM em 7 dias; DilatedRNN em 30 dias; climatologia em todos os checkpoints mensais. A redação atual corresponde aos resultados.
- **Comparação focal terminal:** TimesNet vence em 72 h (52,48 contra 52,96 W/m²); DilatedRNN vence em 30 d (43,85 contra 44,08), 1 mês (13,01 contra 13,89) e 6 meses (14,37 contra 14,46).
- **Arredondamento:** o ganho mensal relativo é 6,379256543527569%, corretamente publicado como 6,38%. As diferenças horárias de 24/48 h são calculadas antes do arredondamento e corretamente publicadas como −1,35/+0,02 W/m².
- **Métricas:** MAE/RMSE usam W/m²; nRMSE é uma razão nos CSVs e porcentagem na tabela terminal. As métricas macro são médias das métricas calculadas separadamente por localidade; os 10 locais contribuem para os resultados cumulativos.
- **Sementes:** diário/mensais usam 11, 23, 42, 67 e 89; horário usa 42. As estatísticas por semente e os ensembles são distinguidos corretamente. DilatedRNN vence 3/5 sementes no diário terminal e 4/5 em cada tarefa mensal terminal.
- **Horizontes:** os resultados principais são cumulativos. Leads horários exatos 24/48/72 selecionam 23:00, têm MAE/RMSE zero e nRMSE/R² indefinidos. As advertências no texto estão corretas.
- **Origem e cobertura:** as contagens de ajuste/validação/refit/teste em `study_design.tex` correspondem aos protocolos. Conferem os 48 pontos de origem por local no refit mensal primário e as 7 origens de teste no mensal exploratório. O término horário em 30/12/2024 está explicitado no setup.
- **Casos selecionados:** os ganhos/déficits, datas, localidades e campos meteorológicos conferem com os artefatos. O maior ganho é GM Factory Zero, 31/03/2024, 24 h; o maior déficit é Tesla Gigafactory Texas, 28/03/2024, 24 h. O evento meteorológico independente é Hyundai Georgia em 05/08/2024.
- **Perfis de sete dias:** recalculados diretamente das previsões horárias, cada um contém 168 alvos únicos e 7 origens; os MAEs TimesNet/DilatedRNN são 99,73360268/115,06636838 (GM), 91,90038715/89,19018693 (Tesla Texas) e 109,42394245/122,97647813 (Hyundai). Todos os valores publicados conferem. São sete prefixos de 24 h, conforme descrito.
- **Tabelas de apoio:** `metricas_terminais`, `comparacao_timesnet_dilatedrnn_resumo`, `desempenho_macro`, `variabilidade_sementes`, `configuracao_treinamento` e tabelas `caso_*` conferem com os derivados auditados.
- **Integridade:** nenhum hash de entrada ou saída divergiu em `revisao_20260907/manifesto_revisao.json`; os arquivos PNG/SVG dos perfis publicados são idênticos às saídas registradas.

## Artefatos desta verificação

- `resultados/artigo_revista_unificado/auditoria_resultados_20260907/auditoria_numerica.json`: resultado detalhado das 276 verificações.
- No mesmo diretório: vencedores, comparações pareadas/por semente e variabilidade recalculados.
- `terminal_location_corrections.json`: registro completo dos 29 valores anteriores e corrigidos; tarefa 0 = diário, 1 = horário, 2 = mensal primário e 3 = mensal exploratório.
- O auditor executado foi `resultados/artigo_revista_unificado/auditoria_topico5_20260906/auditar_resultados.py`, com apenas o diretório de saída redirecionado em memória para preservar a auditoria anterior. Interpretador: Python 3.14 local.

A revisão comprova consistência entre previsões salvas, agregação, números e interpretação textual. A reconstrução de treinamentos e a auditoria bibliográfica/pseudocódigos são etapas separadas da revisão conjunta.

## Contagem adicional de capacidade neural

Os 12 totais de `model_capacity.tex` foram confirmados instanciando LSTM, TimesNet e DilatedRNN com a configuracao congelada e somando os parametros treinaveis, sem treinamento/inferencia: horario 7.512/27.009/3.096; diario 5.790/13.725/2.382; mensal primario 4.601/2.758/1.889; mensal exploratorio 4.806/2.823/1.974. Evidencia: `resultados/artigo_revista_unificado/auditoria_resultados_20260907/model_capacity_verification.json`; 12 verificacoes, zero divergencias.
