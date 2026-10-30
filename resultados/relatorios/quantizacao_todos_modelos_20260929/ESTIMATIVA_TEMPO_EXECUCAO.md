# Estimativa operacional da execução

Leitura realizada em 30/09/2026, aproximadamente 04:14 UTC. Estimativa de planejamento, não prazo garantido. Nenhum treinamento, configuração científica ou processo em execução foi alterado nesta análise.

## Ordem de grandeza

Para os seis modelos aprendidos na base atual, incluindo quatro variantes, todas as sementes, seleção e refit, a faixa preliminar é **24–48 horas** de execução no notebook. A seleção sozinha pode ocupar **12–24 horas**. A primeira semente completa da DilatedRNN diária ainda não terminou; portanto a faixa não constitui um limite superior validado. Essa medição deve atualizar a previsão assim que estiver disponível. Auditoria, possíveis falhas de convergência e espera por revisão de controles acrescentam tempo.

A TimesNet atual foi importada de resultados previamente auditados e não acrescenta treinamento a essa fila. ARIMA e referências simples devem ser contabilizados à parte, embora as medições antigas indiquem custo menor que o das redes e do XGBoost. Os tempos abaixo são horas de um recurso ocupado; **não podem ser todos somados como tempo de calendário**, pois CPU e GPU trabalham parcialmente em paralelo.

| Bloco | Evidência observada | Projeção das quatro variantes, seleção + refit |
|---|---|---|
| XGBoost diário | 765,93 e 710,55 s por semente na seleção; cinco sementes por variante | Aproximadamente 8–12 h de CPU, incluindo refit com mais janelas |
| XGBoost horário | 1.543,32 s na seleção da semente 42 | Aproximadamente 3,5–6 h de CPU |
| GRU diário em CUDA | Cinco sementes somaram 304,97 s na seleção | Aproximadamente 0,7–1 h de GPU |
| LSTM diário em CUDA | Cinco sementes somaram 495,95 s na seleção | Aproximadamente 1–1,5 h de GPU |
| DilatedRNN diário em CUDA | Primeira semente ainda em execução após aproximadamente 20 min | Gargalo principal ainda sem taxa confirmada; se 20–30 min por semente, aproximadamente 13–22 h incluindo refit |
| Transformer + Informer, diário e horário | Tempos originais, que já incluem seleção e refit, multiplicados por quatro: 4,42 + 2,80 + 0,85 + 0,34 h | Cerca de 8,4 h de GPU como referência central; competição por CPU e épocas selecionadas podem mudar esse total |
| GRU/LSTM/DilatedRNN horários | Uma semente por variante; CUDA novo ainda sem medição completa | Não extrapolar diretamente os cinco treinamentos diários; reservar incerteza adicional de algumas horas, sobretudo para DilatedRNN |
| GRU/Transformer/Informer mensais, ambos os horizontes | Soma dos tempos originais seleção + refit, multiplicada por quatro | Cerca de 4,42 h de CPU agregadas; LSTM, DilatedRNN e XGBoost mensais são adicionais |
| ARIMA, quatro tarefas | Antigo: mensal1 41,19 s; mensal6 37,56 s; diário 619,94 s; horário 1.825,33 s | Aproximadamente 42 min foi a execução original completa. A contagem de ajustes antiga (sete ordens + refit) é igual à nova (seleção + refit em quatro variantes), mas ordens e tentativas de convergência têm custos diferentes. Ainda não atribuir prazo firme |

Os controles já concluídos serão retomados por seus caches e não precisam ser treinados novamente após o aceite. As falhas de controle registradas no runner não significam perda desses checkpoints.

## Recursos e gargalos

- Máquina: Intel Core i7-8565U, quatro núcleos físicos e oito threads; aproximadamente 24 GiB de RAM; GTX 1650 Max-Q com 4 GiB de VRAM.
- Leituras pontuais: CPU total 100%; aproximadamente 4,2 GiB de RAM disponível; GPU entre 22% e 28%, VRAM aproximadamente 1,41 GiB, temperatura 66 °C. São snapshots, não médias de toda a execução.
- O XGBoost usa um worker interno. Multiplicam seu custo os 30 ou 72 alvos previstos e as cinco sementes do caso diário.
- A DilatedRNN diária processa sequências de 365 pontos, com recorrências dilatadas e reconstrução cronológica por muitas operações pequenas de indexação e empilhamento. A combinação de CPU ocupada e GPU pouco utilizada é compatível com custo de preparação/lançamento das operações; não há perfil de execução suficiente para atribuir causalidade exclusiva.
- GPU com espaço livre não significa que outro treinamento vá acelerar o conjunto: novos processos também disputam CPU, RAM e largura de banda. Os processos Python pesados disputavam aproximadamente meio núcleo de tempo de CPU cada nos snapshots de 3–4 segundos.
- Plano de energia observado: Balanced. Não foi alterado. O notebook deve permanecer ligado e alimentado durante a fila; o runner já inibe suspensão enquanto está ativo.

## Ajustes de agendamento que preservam o experimento

1. **Usar limite global de concorrência**, considerando juntos os runners de aprendidos, estatísticos e auditorias. Manter inicialmente uma GPU e até dois trabalhos pesados de CPU; evitar que um segundo runner crie mais dois workers sem contabilizar os existentes.
2. **Priorizar trabalhos mensais e GRU/LSTM em oportunidades de agenda**, pois fornecem pares completos cedo. Reordenar somente lançamentos futuros ou depois dos checkpoints naturais; não interromper uma semente em andamento, já que seu cache só é salvo ao final.
3. **Aproveitar integralmente o cache após os aceites**. Retomar a seleção continua do primeiro nível ainda não concluído. Uma nova rodada de treinamento do controle já auditado só acrescentaria custo.
4. **Executar replay pesado e leitura de todas as fontes fora dos picos de treino**, quando possível. Auditorias consomem CPU e RAM e podem aumentar os tempos dos modelos mesmo sem treinar.
5. **Não aumentar globalmente o número de jobs de GPU neste estado de CPU100%**. Uma concorrência adicional pode ser considerada futuramente para trabalhos pequenos, após medir tempo total e memória, mas não existe ganho demonstrado que a justifique agora.
6. **Atualizar a previsão pela taxa real de cada variante**. Quantização pode mudar a época selecionada; não multiplicar o tempo de uma semente como se todas fossem idênticas. As épocas, sementes e dados devem permanecer exatamente como contratados.

Esses ajustes não alteram arquitetura, precisão numérica, lotes, sementes, épocas, dados ou critérios de seleção. Não se propõem AMP, troca de backend, compilação, redução de amostras ou aumento de threads internos, pois exigiriam nova validação científica.

## Etapas históricas

A previsão de 24–48 h refere-se somente aos aprendidos da base atual. O histórico longo terá aproximadamente cinco a sete vezes mais janelas de treinamento/refit, dependendo da resolução e da janela de entrada. O teste de 45 meses também aumenta o custo de inferência. Com este hardware, **o conjunto atual + longo + curto pareado tem ordem de dias, não de horas**. Sem uma primeira semente histórica medida, uma data de término mais precisa seria especulativa. Convém concluir e entregar a base atual antes de ocupar a máquina com as etapas históricas, como definido no protocolo.

## Evidências

- `resultados/quantizacao_todos_modelos_20260929/atual/*/*/sem_quantizacao/selecao/seed*.json`: durações reais dos novos controles.
- `relatorios/quantizacao_todos_modelos_20260929/tempos_antigos.json`: status originais com tempos de GRU, Transformer e Informer. Nesses arquivos, `segundos` inclui seleção e refit juntos.
- `relatorios/quantizacao_todos_modelos_20260929/carga_cpu_snapshot.json`: utilização e memória dos processos Python em uma janela de amostragem.
- `relatorios/quantizacao_todos_modelos_20260929/fila_aprendidos/atual/completa/runner.json` e logs: ordem, início e estado dos jobs.
- Tempos ARIMA fornecidos pela auditoria dos `metadados_json` dos caches robustos originais pelo agente estatístico.
