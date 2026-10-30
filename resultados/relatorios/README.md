# Relatórios, auditorias e acompanhamento

Esta pasta reúne as análises, verificações e painéis produzidos pelas execuções.
Ela faz parte de [`resultados/`](../), junto das previsões, métricas, modelos
treinados e [PDFs exportados](../pdf/).

## Painéis

| Arquivo ou comando | Uso |
|---|---|
| [`painel_treinamentos.html`](painel_treinamentos.html) | interface de acompanhamento dos treinamentos |
| [`panorama_projeto_ghi.html`](panorama_projeto_ghi.html) | mapa visual do projeto |
| [`Abrir painel de progresso.cmd`](../../Abrir%20painel%20de%20progresso.cmd) | atalho Windows para iniciar o painel local |
| `python -m codigo_fonte.acompanhamento.painel_progresso_quantizacao --help` | argumentos do servidor do painel |

Execute os comandos a partir da raiz. O atalho usa
[`codigo_fonte/acompanhamento/abrir_painel_progresso.ps1`](../../codigo_fonte/acompanhamento/abrir_painel_progresso.ps1).
O painel acompanha as execuções, sem iniciar ou encerrar treinamentos.

## Registros por assunto e data

| Pasta | Conteúdo |
|---|---|
| [`quantizacao_todos_modelos_20260929/`](quantizacao_todos_modelos_20260929/) | auditorias, acompanhamento e retomadas da quantização dos modelos |
| [`otimizacao_timesnet_quatro_casos_20260922/`](otimizacao_timesnet_quatro_casos_20260922/) | registros da otimização nas quatro tarefas |
| [`revisao_pre_envio_20260907/`](revisao_pre_envio_20260907/) | validação do pacote entregue |
| [`tabela_resultados_ghi_20260922/`](tabela_resultados_ghi_20260922/) | fontes e verificações da tabela de resultados |

Para novas análises, use `<assunto>_<AAAAMMDD>/` e reúna o resumo, as fontes,
os comandos e as verificações da execução. O programa gerador pertence a
`codigo_fonte/analises_e_relatorios/`; o arquivo gerado pertence a esta área
ou a `resultados/pdf/`.

Os registros históricos preservam caminhos e hashes da época. Consulte o
[registro da reorganização](../../documentacao/organizacao/reorganizacao_codigo_20261027.json)
para localizar materiais transferidos. O [índice de resultados](../README.md)
identifica as fontes científicas atuais.
