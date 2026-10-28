# Continuidade dos experimentos

## Painel local de acompanhamento

Disponivel em http://127.0.0.1:8767, com atualizacao a cada dez segundos. O servidor `scripts/painel_progresso_quantizacao.py` le apenas status, metadados pequenos e caudas de logs; nao importa motores nem altera resultados. Mostra selecao/refit de cada base, repeticoes salvas dos jobs ativos, erros/interrupcoes e a entrega separada da revisao visual. Os percentuais sao contagens de pares modelo/caso, separados das estimativas de tempo.

A estimativa usa ate oito duracoes recentes do mesmo contrato/fase/modelo/caso, sem transferir medidas de CPU, pilotos ou outros historicos. Faixa heuristica ampliada quando ha menos de tres amostras; desconta somente a unidade atual e exclui pausas anteriores a retomada. A fase de selecao atual combina as duas filas GPU iniciais em paralelo, marcando previsao parcial quando faltam modelos com medicao. Nas outras filas, a estimativa individual continua disponivel, sem inferir capacidade de trabalhadores nao registrada. Datas previstas sao aproximadas; a entrega completa depende de refits, historicos, auditorias e revisao. Arquivos: `scripts/estimativa_tempo_quantizacao.py`, `tests/test_estimativa_tempo_quantizacao.py` e `tests/test_painel_eta_integracao.py`.

Para abrir ou religar somente o monitor: executar `Abrir painel de progresso.cmd` na raiz, ou `scripts/abrir_painel_progresso.ps1`. O launcher reaproveita o servidor existente na porta 8767 e abre o navegador. Fechar a aba nao para os treinos. Reiniciar o computador encerra servidor e treinos; o launcher NAO retoma treinamentos. Testes do painel em `tests/test_painel_progresso_quantizacao.py`.

## Estado mais recente: 44 refits concluidos e ponte retomada em 02/10, 01h04 local

Base atual: 44/44 selecoes e 44/44 refits completos. RNN concluiu em 02/10 as 03:58:55 UTC (00:58:55 local), sem falhas; XGBoost concluiu em 01/10 as 23:26:15 UTC. Conferencia explicita dos 44 status completos registrada em `retomada_ponte_20261002/revisao_pre_entrega.json`. Isso ainda nao e auditoria cientifica final nem entrega do PDF.

A ponte anterior parou em 01/10 as 23:43 UTC com WinError5 na inspecao OpenProcess; nenhum treino foi encerrado por ela. O PID que causou aquela falha nao foi registrado e a ocorrencia nao foi reproduzida posteriormente. Estado e consoles anteriores preservados em `retomada_ponte_20261002`. Nao afirmar que PID4 ou reutilizacao de PID causou a falha original.

`scripts/processos_quantizacao.py` agora consulta um snapshot NT somente no ramo WinError5, mantendo PID e horario de criacao exatos em 100 ns. O snapshot e certificado pelo proprio processo; dados invalidos/indeterminados continuam propagando o erro, sem presumir encerramento. Nenhuma rotina de encerramento ou motor cientifico foi alterada. SHA guard: 3f5409846652efbdfc893cf85ee8b51eee51905d1c9b4e9f497456c7f24e1468. Revisao independente com prova real de processo protegido e falha indeterminada: `diagnostico_processos_guard_20261002/revisao_independente_v1.json`. Passaram 119 testes + 6 subtestes; XML `painel/testes_snapshot_orquestracao_20261002.xml`.

Preflight confirmou ambas as recuperacoes concluidas e sem arvores ativas, sem coordenadores ou ponte anterior vivos. Somente a ponte foi retomada, por Start-Process oculto as 04:01 UTC: launcher 6032 / runner 6260, identidade exata no status. Helper `tmp/recuperacao_20261001/finalizar_sequencia.py` manteve SHA 24ea810f381cbe7437e76dd55d5df620522d3b956561c9c04560437e1f2abf06. Logs novos e recibo de lancamento em `retomada_ponte_20261002`. Nao relancar filas, ponte ou coordenadores enquanto esta instancia estiver ativa.

A ponte confirmou zero refits pendentes e iniciou o coordenador atual, que revalida os caches antes de auditar os 44 pares. Depois segue historico longo, historico curto pareado, auditorias e preparacao dos dois PDFs. Os 70 arquivos historicos existem e seus tamanhos foram conferidos; o preflight historico ainda exige a verificacao integral dos hashes. Ambos os historicos ainda estavam com zero treinos nesta atualizacao. O monitor foi reiniciado separadamente para recarregar a correcao e permanece em http://127.0.0.1:8767.

Auditorias finais, treinamentos historicos e PDFs novos ainda pendentes. Apos a preparacao, inspecionar todas as paginas, registrar parecer visual, publicar pelo entregador e atualizar o feedback a partir das metricas auditadas. O PDF antigo da TimesNet permanece publicado; 100% se refere apenas aos refits atuais, nao a todo o estudo.

## Registro anterior: recuperacoes e sequencia automatica ativas em 01/10, 20h05 local

Progresso confirmado: 44/44 selecoes e 39/44 refits (88,6%) na base atual. Os seis controles GPU de teste foram aprovados pela politica v2; os seis refits restantes sao executados sequencialmente por `recuperacao_20261001/runner.json`. GRU diario ja terminou. Conferir status atual para saber quais outros ja concluiram.

O XGBoost horario foi investigado sem mudar dados, parametros ou selecao. A repeticao integral do novo controle CPU foi bitexata (boosters e previsoes), e a revisao independente conferiu dados normalizados, origens, replays e hashes. O gate real sobre o cache foi aprovado sem novo ajuste. Contrato principal, selecao individual/global, CP e NPZ sem quantizacao permaneceram identicos. A comparacao com a execucao antiga continua reprovada; a causa nao foi identificada e as matrizes originais de treinamento nao estavam preservadas. Nao atribuir essa divergencia a quantizacao ou a uma causa numerica especifica. Comparar q64/q128/q256 ao controle reexecutado desta rodada.

Evidencias: `diagnostico_xgboost_horario_v1/controle_reexecutado_auditado_v1.json`, `revisao_independente_v1.json`, `integracao_controle_teste_aprovada_v1.json`. Adapter `codigo_fonte/experimento_xgboost_horario_controle_auditado_v1.py`, SHA ce4b46cfaf9345bdeacb2279756087558d956a5fa1386a5821e81e8f47e8e28c. Motor original segue SHA ca56d2040cc7c0bb1ec353464b861bf75c690a9330e543272eb58ca26450769a. O runner usa adapter somente no refit horario atual completo; selecoes e historicos seguem o motor original. Auditor/PDF/feedback verificam as fontes do suplemento e explicitam essa limitacao.

Fila CPU XGBoost: `recuperacao_xgboost_20261001/runner.json`, helper `tmp/recuperacao_20261001/retomar_xgboost.py`, launcher 4284 / runner 796 / filho inicial 27384, iniciado as 22:58 UTC. Esses PIDs podem ser reutilizados: confirmar sempre identidades e status. Variantes foram iniciadas; q64 estava ativo na ultima verificacao.

A ponte `tmp/recuperacao_20261001/finalizar_sequencia.py` foi iniciada as 22:59 UTC (launcher 17056 / runner 14308). Status em `finalizacao_20261001/status.json`. Aguarda ambas as recuperacoes concluidas, sem falhas ou arvores ativas, e todos os 44 status completos. Usa locks das recuperacoes, fonte imutavel preservada, identidade/heartbeat e revisao do adapter antes de iniciar qualquer coordenador. Em seguida executa atual -> historico longo -> historico curto pareado -> auditorias -> PDFs preparados. Historico usa 2 workers CPU e 2 GPU; nenhum hiperparametro foi alterado por isso. Nao abrir filas ou coordenadores duplicados enquanto essa ponte estiver ativa.

O caminho do marcador PDF foi corrigido para `pdf/26.923.10815/skills/pdf/container_tools/mark_artifact_operation_started.mjs`, conforme o SKILL.md instalado. O marcador nao foi executado ainda; o coordenador executara exatamente uma vez imediatamente antes da primeira autoria dos dois PDFs. Nao inventar o recibo `marcador_operacao_pdf.json`.

Validacao desta recuperacao: 18 testes + 38 subtestes do adapter; revisao/gate reais; 7 testes de integracao do runner/auditor/PDF (PDF sintetico nao escrito); 93 testes + 6 subtestes de monitor, ETA e ponte. Snapshot API em `painel/estado_api_duas_recuperacoes_20261001.json`, XML `painel/testes_finalizador_xgboost_20261001.xml`. A API real mostrou filas RNN/CPU simultaneas sem falhas atuais. Dashboard foi reiniciado para carregar as mudancas.

Ainda nao ha auditoria final atual, treinamento historico ou PDF novo publicado. Quando a ponte terminar em `pronto_para_revisao_visual`, inspecionar todas as paginas de ambos os PDFs, registrar parecer visual com SHA/paginas, usar o entregador, atualizar feedback com resultados reais e entregar os dois PDFs. As barras do painel sao por fase, nao uma estimativa temporal de todo o estudo. Uma nova interrupcao requer inspecao das identidades e dos caches antes de retomar.

## Recuperacao anterior: iniciada em 01/10/2026, 22:22 UTC (19h22 local)

As 44 selecoes terminaram. O refit concluiu 37/44 pares (84,1%): quatro TimesNet importados e 33 concorrentes novos. A fila integral encerrou em 01/10 as 07:38 UTC com sete pendencias. Seis sao solicitacoes explicitas de verificacao dos controles CPU/CUDA de GRU, LSTM e DilatedRNN horario/diario; a setima e divergencia CPU do controle XGBoost horario (97,88775587081909 W/m2). Por isso o coordenador atual bloqueou a sequencia, e o historico nao iniciou. Nenhum PDF novo foi preparado ou publicado.

Os tres estados anteriores foram preservados, com hashes, em `recuperacao_20261001/estados_anteriores`. A fila isolada `recuperacao_20261001/runner.json` verifica os seis controles de teste pela politica v2 ja revisada e depois executa seus seis refits, em uma GPU por vez, aproveitando caches integros. Seu helper esta em `tmp/recuperacao_20261001/retomar_rnn.py`; o escopo explicito esta em `recuperacao_20261001/escopo.json`. A falha XGBoost nao e aceita por essa politica e continua em diagnostico independente, sem relaxar tolerancia ou modificar o motor congelado. Nao iniciar outra fila GPU sobre esses seis pares.

O painel foi religado na porta 8767. A contagem 84,1% refere-se apenas aos refits da base atual; nao e o percentual de todo o estudo. Ainda faltam auditoria completa com replay, historicos longo e curto pareado, ambos os PDFs e revisao visual. Atualizar este registro apos resolver o XGBoost e confirmar a recuperacao antes de relancar coordenadores.

## Retomada anterior: 30/09/2026, 23:45 UTC

O usuario pediu continuidade novamente. Nenhum processo Python dos experimentos estava ativo. O Windows registra reinicio em 30/09 as 18:13:17 UTC (15:13 local); os runners tinham ultima atualizacao as 17:58 UTC. Antes desse reinicio, o coordenador atual havia parado as 17:37 UTC por heartbeat de fila mais antigo que dez minutos, e o historico parou pela dependencia. Esses estados foram preservados em `retomada_20260930_2343` antes de relancar qualquer processo. Nao houve novo erro cientifico nas caudas examinadas.

Progresso confirmado: 37/44 selecoes (84,1%): mensais 22/22, diario 9/11, horario 6/11. Os quatro refits concluidos sao TimesNet importados; refits novos, historicos e PDFs continuam pendentes. A verificacao independente dos oito pares inspecionados encontrou 55 caches e seus 165 artefatos integros. DilatedRNN diario preservou 19/20 sementes (pendente q256/89); Informer diario 13/20 (proxima q128/67). Transformer diario terminou e sera somente revalidado.

As duas filas foram relancadas com Start-Process oculto as 23:45 UTC; logs de console em `retomada_20260930_2343`. O coordenador atual iniciou as 23:46 UTC e confirmou as duas filas frescas; o historico foi relancado em seguida, mantendo a mesma politica, revisao e dependencia. O monitor da porta 8767 tambem foi religado. Conferir status e identidades antes de executar novamente, evitando filas duplicadas. As sementes incompletas recomecam, as completas sao verificadas/reutilizadas; nao ha retomada por epoca.

## Retomada anterior: 30/09/2026, 14:14 UTC

O usuario autorizou a retomada. As filas RNN e Transformer/Informer foram reiniciadas as 14:14 e 14:15 UTC, usando os caches salvos. GRU e LSTM diarios concluiram suas verificacoes sem novo treino; o Transformer diario retomou a semente 42, preservando as sementes 11 e 23 completas. O coordenador atual foi iniciado as 14:16 UTC e confirmou que aguarda as duas filas novas. O coordenador historico tambem foi reiniciado para aguardar o atual auditado. Nenhum PDF novo foi publicado. Conferir os estados e as identidades dos processos antes de qualquer nova execucao; nao abrir filas duplicadas.

## Registro anterior: interrupcao para desligamento do computador

Em 30/09/2026, o usuario informou que precisava desligar o computador. As duas filas e os dois coordenadores foram encerrados; nenhuma arvore de treinamento registrada permaneceu ativa. Os estados estao marcados como `interrompida`, com `interrupcao_solicitada_pelo_usuario=true`. O registro `pausa_desligamento_20260930/retomada.json` confirma a integridade dos 11 caches de sementes concluidos nos dois pares que estavam treinando. Os demais resultados anteriores permanecem preservados. Nenhum PDF novo foi publicado.

Quando o usuario pedir para retomar, verificar processos e estados antes de executar. Reiniciar primeiro estas duas filas, usando o Python `.venv-baselines-gpu-20260912/Scripts/python.exe -X utf8`:

1. `-m scripts.rodar_quantizacao_todos_modelos --regime atual --somente-selecao --tarefas daily_30 hourly_72_extension --modelos GRU LSTM DilatedRNN --relatorios relatorios/quantizacao_todos_modelos_20260929/fila_aprendidos --cpu-workers 2 --gpu-workers 1`
2. `-m scripts.rodar_quantizacao_todos_modelos --regime atual --somente-selecao --tarefas daily_30 hourly_72_extension --modelos Transformer Informer --relatorios relatorios/quantizacao_todos_modelos_20260929/fila_atencao --cpu-workers 1 --gpu-workers 1`

Os caches completos sao verificados e reutilizados automaticamente. A execucao da semente que estava incompleta e refeita; nao ha checkpoint do otimizador por epoca. Nao apagar `.execucao.lock`: a trava do sistema operacional e liberada quando o processo encerra.

Depois de confirmar que ambas as filas iniciaram, reiniciar o coordenador atual:

`-m scripts.coordenar_quantizacao_atual --politica relatorios/quantizacao_todos_modelos_20260929/politica_migracao_cpu_cuda/proposta_politica_v2.json --revisao relatorios/quantizacao_todos_modelos_20260929/politica_migracao_cpu_cuda/revisao_root_v2.json --fila-estatisticos relatorios/quantizacao_todos_modelos_20260929/fila_atencao/atual/completa/runner.json`

Confirmar que o status atual esta aguardando as duas filas novas e so entao iniciar `-m scripts.coordenar_quantizacao_historica`. Nao iniciar coordenadores sobre estados antigos `interrompida`, nem executar novamente os scripts pontuais de encerramento. Abaixo permanece o historico do trabalho anterior a essa interrupcao.

Atualizado em 30/09/2026. Os treinamentos ainda estavam em andamento ao criar este registro. Nenhum dos dois PDFs novos foi publicado.

## Execucoes ativas

- Fila dos concorrentes aprendidos: `fila_aprendidos/atual/completa/runner.json`.
- Fila paralela Transformer/Informer: `fila_atencao/atual/completa/runner.json`, iniciada em 30/09 as 11:57 UTC. Nao relancar os mesmos pares em outra fila.
- Retomada isolada do ARIMA horario: `fila_estatisticos/atual/completa/runner.json`. As outras 15 selecoes estatisticas ja estavam concluidas e preservadas.
- Coordenador atual: `coordenacao_atual/status.json`.
- Coordenador historico: `coordenacao_historica/status.json`.

Os coordenadores foram retomados em 30/09 por volta de 11:50 UTC, apos validar o adaptador de atencao. O atual aguarda a fila ativa de RNN; o historico aguarda o atual auditado. Conferir estados e processos antes de relancar qualquer comando. A fila ativa de RNN foi retomada as 10:45 UTC e continua executando selecao; nao a interromper. O ARIMA horario terminou q256 as 10:55 UTC e sua fila esta concluida. As selecoes completas da base atual somam 36 de 44 pares; os novos refits completos continuam pendentes.

Atualizacao 11:58 UTC: somente os coordenadores em espera foram encerrados e reiniciados para incluir a fila paralela de atencao. Nenhum treinamento foi interrompido. O coordenador atual recebeu `--fila-estatisticos relatorios/quantizacao_todos_modelos_20260929/fila_atencao/atual/completa/runner.json`: esse argumento agora aponta para a segunda fila ativa, pois a estatistica ja concluiu. Ele aguarda RNN e atencao antes de abrir a fila integral, evitando duplicacao. O historico continua aguardando o atual. A GPU passou de uma amostra de 32% para 95% de utilizacao, com 1.356 MiB usados de 4.096 MiB; isso e monitoramento de recurso, nao resultado cientifico. As snapshots e identidades dos coordenadores encerrados estao em `retomada_paralela_atencao_20260930`.

Em 30/09, os quatro controles Transformer/Informer horario/diario foram investigados: 36 checkpoints tiveram replay bitexato; a variacao entre retreinamentos foi localizada no backward permissivo da atencao. O piloto estrito repetiu dois treinos com oito updates para cada par e produziu curvas, pesos e previsoes bitexatos. Evidencia: `investigacao_atencao/piloto_treinamento_estrito.json`. Os quatro diretorios inacabados foram arquivados, 72 arquivos intactos, em `tmp/quantizacao_todos_modelos_20260929/antes_atencao_deterministica_v1`; manifesto `investigacao_atencao/preservacao_antes_adaptador_v1.json`.

O adaptador `codigo_fonte/experimento_atencao_deterministica_v1.py` e usado somente nesses quatro pares, nas tres bases. A politica CPU/CUDA dos seis pares RNN continua separada. A integracao curta v1 encontrou uma comparacao incorreta dos metadados de proveniencia; foi corrigida com teste de regressao. A execucao curta v2 concluiu selecao/refit e replay dos 32 checkpoints, com maior diferenca de 2,274e-13 W/m2, abaixo da tolerancia de 1e-6. O registro `investigacao_atencao/integracao_aprovada_v1.json` liga piloto, preservacao, auditoria e fontes. Passaram 15 testes do piloto, 32 do adaptador/integracao apos a correcao e 39 de historicos. Fontes cientificas originais permanecem congeladas. Esses testes curtos nao sao resultados publicaveis.

O coordenador atual espera as filas existentes, registra somente controles que passam pela politica revisada, completa selecao e treinamento final dos 44 pares, audita todos os resultados e prepara PDF e feedback. O historico espera o atual auditado, verifica novamente os 70 arquivos de coleta e executa os perfis longo e curto com as mesmas datas de avaliacao. Falhas tecnicas param a sequencia para investigacao, sem ampliar tolerancias.

## Evidencias principais

- `politica_migracao_cpu_cuda/proposta_politica_v2.json` e `revisao_root_v2.json`: politica revisada para seis migracoes CPU/CUDA. Integracao real GRU diario reproduziu 5 checkpoints exatamente. Aceites antigos do GRU e LSTM diarios preservados.
- `diagnostico_arima_horario/controle_reexecutado_auditado_v1.json`: 10 checkpoints e 261.360 previsoes reproduzidas exatamente. Adaptador versionado importa explicitamente o novo controle de validacao; a divergencia historica e preservada e o refit permanece estrito.
- `historico/auditoria_contextos_historicos_aprovada.json`: 32 contextos aprovados, hashes dos 70 arquivos e cobertura das janelas.
- `historico/validacao_extensao_auditor_pareamento.json`: 33 testes e introspeccao real das entradas dos quatro casos.
- `historico/preflight_coordenador_verificado.json`: releitura real dos 70 arquivos antes de liberar a sequencia historica.
- `testes_guardas_execucao.xml` e `testes_guardas_historico_aninhado.xml`: 31 testes de retomada, concorrencia e processos Windows.
- `preservacao_antes_pdf_revisada_20260930.json`: 1.674 arquivos anteriores inalterados; unica alteracao prevista no documento de acompanhamento.

## Conclusao pendente

O feedback aberto foi atualizado somente para identificar os numeros antigos como TimesNet e registrar que a coleta historica ja esta pronta, com os novos treinos ainda pendentes. Seu conteudo anterior esta preservado em `retomada_paralela_atencao_20260930/FEEDBACK_THALES_QUANTIZACAO_anterior.md`. Assim, uma nova auditoria do snapshot anterior deve reconhecer duas alteracoes documentais autorizadas: `documentacao/QUANTIZACAO_TODOS_MODELOS.md` e `documentacao/FEEDBACK_THALES_QUANTIZACAO.md`. Nao tratar o antigo parecer de preservacao, que enumerava somente a primeira, como auditoria atualizada dessas edicoes. Nenhuma metrica antiga foi alterada.

1. Verificar que os coordenadores terminaram em `pronto_para_revisao_visual`, sem falhas, e que as auditorias completas sao publicaveis.
2. Inspecionar todas as imagens em `pdf_atual/paginas` e `pdf_historico/paginas`. A geracao automatica nao equivale a aprovacao visual.
3. Se necessario, corrigir o gerador, regenerar e renderizar. O marcador da operacao PDF e executado pelo coordenador atual e fica registrado em `marcador_operacao_pdf.json`; nao repetir o marcador depois de registrado.
4. Registrar a revisao visual com `aprovado`, `pdf_sha256` e `paginas_verificadas` e usar `scripts.entregar_pdf_quantizacao_todos_modelos` para entregar em `documentacao/tabela_resultados_ghi_2024.pdf` e `documentacao/tabela_resultados_ghi_1998_2022.pdf`.
5. Atualizar `documentacao/FEEDBACK_THALES_QUANTIZACAO.md` a partir dos feedbacks auditados gerados nesta pasta, sem enviar mensagem externa. Entregar os PDFs e um texto curto dos resultados reais.

Nao apresentar selecoes parciais, testes curtos ou dados sinteticos dos testes unitarios como resultados finais. As configuracoes e a ciencia do motor permanecem congeladas; nao remover validacoes para fazer uma fila terminar.
