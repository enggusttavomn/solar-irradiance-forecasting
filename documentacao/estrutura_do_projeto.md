# Onde encontrar e salvar cada coisa

Use o [mapa do projeto](../MAPA_DO_PROJETO.md) para navegar e o
[catálogo de comandos](../codigo_fonte/COMANDOS.md) para executar uma tarefa.

## As pastas principais

| Pasta | Responsabilidade |
|---|---|
| `codigo_fonte/` | todo o código e todos os comandos, agrupados pela tarefa |
| `dados/` | entradas brutas, externas e preparadas |
| `resultados/` | previsões, modelos treinados, métricas e manifestos |
| `resultados/relatorios/` | auditorias, análises e painéis gerados |
| `resultados/pdf/` | PDFs exportados para consulta e entrega |
| `artigos/` | manuscritos e seus materiais de publicação |
| `documentacao/` | guias, protocolos, plano, referências e entregas |
| `testes/` | todos os testes automatizados |
| `tmp/` | trabalho provisório e recuperação operacional local |

## Código agrupado pela tarefa

```text
codigo_fonte/
  coleta_e_preparacao/      coleta, limpeza e montagem das bases
  modelos/                 modelos por família
  experimentos/            treinamento, avaliação, otimização e quantização
  analises_e_relatorios/   métricas, auditorias, gráficos e PDFs
  acompanhamento/         filas, processos, painéis e retomadas
  publicacoes/            artigos, apresentações e sincronização
  utilitarios/            configuração e funções comuns
```

Uma função reutilizável e o comando que a chama pertencem à mesma área.
Novos comandos devem ter nome claro e podem ser executados como módulo:

```bash
python -m codigo_fonte.experimentos.rodar_quantizacao_todos_modelos --help
python -m codigo_fonte.analises_e_relatorios.auditar_quantizacao_todos_modelos --help
python -m codigo_fonte.acompanhamento.painel_progresso_quantizacao --help
```

## Como escolher o destino de um arquivo novo

| Arquivo | Destino |
|---|---|
| Programa, função ou comando | `codigo_fonte/<tarefa>/` |
| Teste automatizado | `testes/`; testes de operação em `testes/operacao/` |
| Insumo original | `dados/brutos/` ou `dados/externos/` |
| Base preparada | `dados/processados/` |
| Evidência de uma execução | `resultados/<assunto>_<AAAAMMDD>/` |
| Análise ou auditoria gerada | `resultados/relatorios/<assunto>_<AAAAMMDD>/` |
| PDF exportado | `resultados/pdf/` |
| Manuscrito e figuras da publicação | `artigos/<publicacao>/` |
| Instrução ou protocolo | `documentacao/` |
| Pacote entregue | `documentacao/entregas_aos_orientadores/<assunto>_<AAAAMMDD>/` |
| Prévia descartável | `tmp/<assunto>_<AAAAMMDD>/` |

Use nomes que descrevam assunto e finalidade. Prefira uma pasta nova por
execução a sobrescrever evidências anteriores.

## Fontes antigas e auditoria

Os caminhos anteriores estão registrados em
[`organizacao/reorganizacao_codigo_20261027.json`](organizacao/reorganizacao_codigo_20261027.json).
O ZIP de fontes originais preserva o código usado nos registros históricos;
os manifestos dessas execuções não foram reescritos para simular uma execução
com a estrutura nova.

Os resultados de uma nova execução devem registrar seus próprios caminhos,
configuração, sementes e hashes. Execute `python -m pytest -q` na raiz antes
de versionar mudanças. Configurações, dependências e metadados das ferramentas
continuam na raiz.
