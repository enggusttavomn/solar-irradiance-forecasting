# Relatórios e acompanhamento

Esta pasta reúne painéis, auditorias, revisões e registros datados das
execuções. Para interpretar os números de um estudo, consulte também o
[índice de resultados](../resultados/README.md) e o manifesto da execução.

## Painéis

| Arquivo ou comando | Uso |
|---|---|
| [`painel_treinamentos.html`](painel_treinamentos.html) | painel HTML de acompanhamento disponível no checkout |
| [`panorama_projeto_ghi.html`](panorama_projeto_ghi.html) | panorama visual do projeto |
| [`../Abrir painel de progresso.cmd`](../Abrir%20painel%20de%20progresso.cmd) | atalho Windows para iniciar e abrir o painel local de progresso |
| `python -m scripts.operacao.painel_progresso_quantizacao --help` | opções do servidor do painel de progresso |

Os comandos devem ser executados a partir da raiz do repositório. O atalho
Windows usa o ambiente Python local configurado em
[`scripts/abrir_painel_progresso.ps1`](../scripts/abrir_painel_progresso.ps1).
O monitor acompanha as execuções; não inicia nem encerra treinamentos.

## Organização dos registros

As pastas combinam o assunto com a data de abertura, por exemplo:

| Pasta | Conteúdo |
|---|---|
| [`quantizacao_todos_modelos_20260929/`](quantizacao_todos_modelos_20260929/) | auditorias, acompanhamento e retomadas da quantização dos modelos |
| [`otimizacao_timesnet_quatro_casos_20260922/`](otimizacao_timesnet_quatro_casos_20260922/) | registros da otimização nas quatro tarefas |
| [`revisao_pre_envio_20260907/`](revisao_pre_envio_20260907/) | validação e manifestos do pacote de envio |
| [`tabela_resultados_ghi_20260922/`](tabela_resultados_ghi_20260922/) | fontes, métricas e verificação da tabela de resultados |

Para novos relatórios, use `assunto_AAAAMMDD/` e reúna o resumo, as fontes,
os comandos e as verificações da mesma execução. Resultados científicos
ficam em `resultados/`; documentos finais de entrega ficam em `documentacao/`
ou `artigos/`; prévias descartáveis ficam em `output/`.

Registros existentes podem fazer parte de contratos de auditoria, snapshots
ou retomadas. Preserve seus nomes, caminhos e conteúdo; organize sua
navegação por índices e adicione novos registros em pastas próprias.
Consulte o [guia da estrutura](../documentacao/estrutura_do_projeto.md) para
as convenções completas.
