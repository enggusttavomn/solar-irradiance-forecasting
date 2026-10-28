# Comandos por área

Execute os módulos a partir da raiz do repositório com o Python do ambiente
virtual. A forma geral é `python -m scripts.<área>.<comando>`.
Os módulos organizados reutilizam as implementações existentes.

## Comandos com ajuda

Acrescente `--help` aos módulos abaixo para consultar os argumentos sem
iniciar a operação.

| Área | Módulo depois de `python -m` | Finalidade |
|---|---|---|
| Coleta | `scripts.coleta.coletar_dados_horarios_nsrdb` | coleta horária da NSRDB |
| Coleta | `scripts.coleta.coletar_contexto_meteorologico` | contexto meteorológico das localidades |
| Treinamento | `scripts.treinamento.executar_experimento` | avaliação mensal canônica |
| Treinamento | `scripts.treinamento.otimizar_timesnet_mensal` | busca de hiperparâmetros mensais |
| Treinamento | `scripts.treinamento.rodar_quantizacao_resolucoes` | quantização horária e diária |
| Treinamento | `scripts.treinamento.rodar_quantizacao_todos_modelos` | quantização dos modelos concorrentes |
| Auditoria | `scripts.auditoria.auditar_quantizacao_timesnet` | verificação da quantização mensal |
| Auditoria | `scripts.auditoria.auditar_quantizacao_resolucoes` | verificação da quantização horária e diária |
| Auditoria | `scripts.auditoria.auditar_quantizacao_todos_modelos` | integridade da comparação dos modelos |
| Auditoria | `scripts.auditoria.auditar_pareamento_historicos` | pareamento entre os históricos |
| Relatórios | `scripts.relatorios.gerar_pdf_quantizacao_quatro_casos` | PDF das quatro tarefas |
| Relatórios | `scripts.relatorios.gerar_pdf_quantizacao_todos_modelos` | PDF da comparação dos modelos |
| Relatórios | `scripts.relatorios.gerar_figuras` | figuras oficiais do estudo mensal |
| Operação | `scripts.operacao.painel_progresso_quantizacao` | painel local de acompanhamento |
| Apresentações | `scripts.apresentacoes.corrigir_apresentacao_imagens` | correção de imagens com entrada e saída explícitas |

Exemplo:

```bash
python -m scripts.treinamento.rodar_quantizacao_todos_modelos --help
```

## Utilitários com interface histórica

Estes comandos conservam a interface do script original. Leia o arquivo
indicado antes de executá-los: alguns iniciam o trabalho imediatamente e
não implementam `--help`.

| Módulo depois de `python -m` | Implementação e insumos |
|---|---|
| `scripts.coleta.preparar_historico_nsrdb_1998_2022` | [`preparar_historico_nsrdb_1998_2022.py`](preparar_historico_nsrdb_1998_2022.py); histórico NSRDB e fontes de preservação |
| `scripts.apresentacoes.gerar_apresentacao_modelos_ml` | [`gerar_apresentacao_modelos_ml.py`](gerar_apresentacao_modelos_ml.py); gerador independente |
| `scripts.apresentacoes.gerar_apresentacao_modelos_ml_template_sidi` | [`gerar_apresentacao_modelos_ml_template_sidi.py`](gerar_apresentacao_modelos_ml_template_sidi.py); requer o template SiDi nos caminhos configurados |
| `scripts.apresentacoes.corrigir_ppt_share_knowledge` | [`corrigir_ppt_share_knowledge.py`](corrigir_ppt_share_knowledge.py); requer o deck original nos caminhos configurados |
| `scripts.apresentacoes.renderizar_preview_pptx` | [`renderizar_preview_pptx.py`](renderizar_preview_pptx.py); recebe o caminho do PPTX como argumento posicional |

Os arquivos de apresentação usados por algumas dessas ferramentas não estão
neste checkout. Os pontos de entrada preservam os caminhos de entrada e
saída dos geradores históricos.

As ferramentas PPTX requerem `python-pptx`; o tratamento de imagens também
usa Pillow. Algumas ferramentas de inspeção configuram fontes em caminhos
Linux, que precisam estar disponíveis no ambiente onde forem executadas.

## Outros comandos existentes

Os executáveis completos permanecem em [`../executaveis/`](../executaveis/).
As automações de sincronização e os comandos especializados continuam nos
caminhos existentes em `scripts/`. O índice antigo
[`README.md`](README.md) também descreve sincronização com GitHub e Overleaf.

O atalho Windows [`abrir_painel_progresso.ps1`](abrir_painel_progresso.ps1)
abre o acompanhamento local usando o ambiente configurado. A interface
do painel está em [`../relatorios/painel_treinamentos.html`](../relatorios/painel_treinamentos.html).

Para criar ou localizar outros arquivos, consulte o
[mapa completo do projeto](../documentacao/estrutura_do_projeto.md).
