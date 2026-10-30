# Código do projeto

Esta é a única área para programas e comandos. Os arquivos ficam juntos pela
tarefa que realizam, sem separar implementações em outras pastas da raiz.

| Pasta | O que faz |
|---|---|
| [`coleta_e_preparacao/`](coleta_e_preparacao/) | consulta fontes, limpa dados e monta as bases |
| [`modelos/`](modelos/) | implementa os modelos de previsão, separados por família |
| [`experimentos/`](experimentos/) | treina, avalia, otimiza e quantiza os modelos |
| [`analises_e_relatorios/`](analises_e_relatorios/) | calcula métricas, audita e gera gráficos e PDFs |
| [`acompanhamento/`](acompanhamento/) | acompanha filas, processos, painéis e retomadas |
| [`publicacoes/`](publicacoes/) | prepara artigos e apresentações e sincroniza publicações |
| [`utilitarios/`](utilitarios/) | reúne configuração e funções usadas em várias áreas |

Consulte o [catálogo de comandos](COMANDOS.md) e execute os módulos a partir
da raiz do repositório:

```bash
python -m codigo_fonte.experimentos.experimento_multirresolucao --help
python -m codigo_fonte.acompanhamento.painel_progresso_quantizacao --help
```

Exemplos de implementação:

- `coleta_e_preparacao/base_mensal.py`: prepara a base mensal das localidades.
- `modelos/timesnet_horario.py`: implementa os componentes da TimesNet.
- `experimentos/experimento_multirresolucao.py`: coordena as tarefas horária, diária e mensais.
- `analises_e_relatorios/metricas.py`: calcula e salva métricas de avaliação.
- `publicacoes/artefatos_artigo_unificado.py`: prepara os artefatos do manuscrito.

Arquivos produzidos ficam em [`../resultados/`](../resultados/), inclusive
PDFs e relatórios. Entradas ficam em [`../dados/`](../dados/) e instruções em
[`../documentacao/`](../documentacao/).

As fontes anteriores à reorganização estão preservadas em um ZIP identificado
no [registro de migração](../documentacao/organizacao/reorganizacao_codigo_20261027.json).
