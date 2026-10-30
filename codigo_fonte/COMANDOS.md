# Comandos do projeto

Execute os módulos a partir da raiz com o Python do ambiente virtual.
A forma geral é `python -m codigo_fonte.<area>.<modulo>`.
No PowerShell, use `.\.venv\Scripts\python.exe` no lugar de `python`.

## Consultar a ajuda

Acrescente `--help` para consultar argumentos antes de iniciar uma execução.

| Tarefa | Módulo depois de `python -m` |
|---|---|
| Coletar dados horários NSRDB | `codigo_fonte.coleta_e_preparacao.coletar_dados_horarios_nsrdb` |
| Coletar contexto meteorológico | `codigo_fonte.coleta_e_preparacao.coletar_contexto_meteorologico` |
| Avaliar as quatro tarefas | `codigo_fonte.experimentos.experimento_multirresolucao` |
| Avaliar o protocolo mensal | `codigo_fonte.experimentos.experimento_mensal_canonico` |
| Avaliar a TimesNet horária | `codigo_fonte.experimentos.experimento_horario_timesnet` |
| Buscar hiperparâmetros mensais | `codigo_fonte.experimentos.otimizacao_timesnet_mensal` |
| Quantizar tarefas horária e diária | `codigo_fonte.experimentos.rodar_quantizacao_resolucoes` |
| Quantizar os modelos concorrentes | `codigo_fonte.experimentos.rodar_quantizacao_todos_modelos` |
| Auditar a quantização mensal | `codigo_fonte.analises_e_relatorios.auditar_quantizacao_timesnet` |
| Auditar a quantização horária e diária | `codigo_fonte.analises_e_relatorios.auditar_quantizacao_resolucoes` |
| Auditar os modelos concorrentes | `codigo_fonte.analises_e_relatorios.auditar_quantizacao_todos_modelos` |
| Auditar o pareamento dos históricos | `codigo_fonte.analises_e_relatorios.auditar_pareamento_historicos` |
| Gerar figuras da avaliação mensal | `codigo_fonte.analises_e_relatorios.gerar_figuras_avaliacao_canonica` |
| Gerar PDF das quatro tarefas | `codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_quatro_casos` |
| Gerar PDF dos modelos concorrentes | `codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos` |
| Gerar artefatos do artigo principal | `codigo_fonte.publicacoes.gerar_artefatos_artigo_unificado` |
| Consultar o painel de progresso | `codigo_fonte.acompanhamento.painel_progresso_quantizacao` |
| Corrigir imagens de uma apresentação | `codigo_fonte.publicacoes.corrigir_apresentacao_imagens` |

Exemplo:

```powershell
.\.venv\Scripts\python.exe -m codigo_fonte.experimentos.rodar_quantizacao_todos_modelos --help
```

## Ferramentas especializadas

Leia os argumentos e caminhos no arquivo antes de executar estas ferramentas:
algumas iniciam o trabalho imediatamente, sem implementar `--help`.

| Módulo ou arquivo | Uso |
|---|---|
| [`coleta_e_preparacao/preparar_historico_nsrdb_1998_2022.py`](coleta_e_preparacao/preparar_historico_nsrdb_1998_2022.py) | prepara o histórico NSRDB |
| [`acompanhamento/finalizar_sequencia_recuperacao.py`](acompanhamento/finalizar_sequencia_recuperacao.py) | finaliza a recuperação local e confere as filas; inicia a operação imediatamente, sem `--help` |
| [`publicacoes/gerar_apresentacao_modelos_ml.py`](publicacoes/gerar_apresentacao_modelos_ml.py) | gera apresentação dos modelos |
| [`publicacoes/gerar_figura_dilatedrnn_btsym.py`](publicacoes/gerar_figura_dilatedrnn_btsym.py) | recria a figura mensal do artigo BTSym a partir dos CSVs canônicos |
| [`publicacoes/gerar_apresentacao_modelos_ml_template_sidi.py`](publicacoes/gerar_apresentacao_modelos_ml_template_sidi.py) | requer o template SiDi configurado |
| [`publicacoes/corrigir_ppt_share_knowledge.py`](publicacoes/corrigir_ppt_share_knowledge.py) | requer a apresentação original configurada |
| [`publicacoes/renderizar_preview_pptx.py`](publicacoes/renderizar_preview_pptx.py) | recebe o PPTX como argumento posicional |

Alguns arquivos de apresentação usados por essas ferramentas não integram o
checkout. Os geradores PPTX usam `python-pptx`; imagens também usam Pillow.

## Painel e sincronização

- [`publicacoes/configurar_sincronizacao_automatica.ps1`](publicacoes/configurar_sincronizacao_automatica.ps1)
  instala a tarefa do Windows que cria commits e envia as alterações salvas ao
  GitHub a cada minuto. Consulte o [guia de sincronização automática](../documentacao/sincronizacao_automatica.md)
  para ver o status, desativar ou configurar outro computador.
- O atalho [`Abrir painel de progresso.cmd`](../Abrir%20painel%20de%20progresso.cmd)
  inicia o painel local pelo ambiente Python disponível.
- [`acompanhamento/abrir_painel_progresso.ps1`](acompanhamento/abrir_painel_progresso.ps1)
  implementa esse atalho.
- [`publicacoes/sincronizar_projeto.cmd`](publicacoes/sincronizar_projeto.cmd) e
  [`publicacoes/sincronizar_projeto.sh`](publicacoes/sincronizar_projeto.sh)
  sincronizam a branch após revisão, testes e commit.
- [`publicacoes/sincronizar_overleaf.cmd`](publicacoes/sincronizar_overleaf.cmd)
  sincroniza o manuscrito configurado com o Overleaf.
- [`publicacoes/configurar_monitor_overleaf.ps1`](publicacoes/configurar_monitor_overleaf.ps1)
  configura o monitor de publicações no Windows.

O monitor e os sincronizadores usam as configurações e credenciais locais já
estabelecidas. Consulte cada arquivo antes de alterar o fluxo de publicação.

As saídas são salvas em [`../resultados/`](../resultados/): PDFs em `pdf/`,
auditorias e painéis em `relatorios/`, experimentos em suas pastas identificadas.
O [mapa do projeto](../MAPA_DO_PROJETO.md) explica todos os destinos.
