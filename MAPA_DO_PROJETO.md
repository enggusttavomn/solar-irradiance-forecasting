# Mapa do projeto de previsão solar

O projeto tem um lugar para o código e um lugar para tudo o que ele gera.
Abra o [panorama visual](resultados/relatorios/panorama_projeto_ghi.html) para navegar.

| Pasta | O que guardar aqui | Exemplo |
|---|---|---|
| [codigo_fonte/](codigo_fonte/) | programas, modelos e comandos, agrupados pela tarefa | coletar dados, treinar TimesNet, gerar PDF |
| [dados/](dados/) | entradas usadas na pesquisa | séries de irradiância e dados meteorológicos |
| [resultados/](resultados/) | tudo o que uma execução produziu | previsões, modelos treinados, métricas, gráficos, PDFs e auditorias |
| [artigos/](artigos/) | textos científicos e materiais da publicação | manuscrito, tabelas, figuras e suplemento |
| [documentacao/](documentacao/) | instruções, protocolos e materiais do TCC | guia de execução, plano de trabalho, referências e entregas |
| [testes/](testes/) | verificações automáticas do programa | testes de modelos, métricas, arquivos e retomadas |
| `tmp/` | trabalho provisório e estados locais de recuperação | prévias e testes rápidos |

## Código: cada tarefa fica junta

```text
codigo_fonte/
  coleta_e_preparacao/      obter dados, limpar e montar as bases
  modelos/                 implementar os modelos de previsão
  experimentos/            treinar, avaliar, otimizar e quantizar
  analises_e_relatorios/   calcular métricas, auditar, gerar gráficos e PDFs
  acompanhamento/         acompanhar filas, processos e retomadas
  publicacoes/            preparar artigos, apresentações e sincronização
  utilitarios/            configurações e funções comuns
```

Funções e comandos da mesma tarefa ficam na mesma área. O catálogo de
[comandos](codigo_fonte/COMANDOS.md) mostra o módulo a executar. Por exemplo:

```powershell
.\.venv\Scripts\python.exe -m codigo_fonte.experimentos.rodar_quantizacao_todos_modelos --help
```

## Resultados: arquivos gerados ficam juntos

```text
resultados/
  <nome_do_experimento>/    previsões, métricas, configurações e manifestos
  modelos/                 modelos treinados já preservados no projeto
  relatorios/              análises, auditorias e painéis por assunto/data
  pdf/                     PDFs exportados para leitura e entrega
```

A diferença agora é simples: o programa que gera um PDF fica em
`codigo_fonte/analises_e_relatorios/`; o PDF pronto fica em `resultados/pdf/`.
Uma instrução para repetir esse trabalho fica em `documentacao/`.

A fonte atual local do artigo principal é
[`resultados/avaliacao_multirresolucao_corrigida_v2/`](resultados/avaliacao_multirresolucao_corrigida_v2/).
O [índice de resultados](resultados/README.md) distingue essa fonte das
execuções anteriores. Mantenha os arquivos de cada experimento juntos.

## Documentos e pesquisa

- [Artigo principal](artigos/revista_unificado/): manuscrito e suplemento.
- [Plano do TCC](documentacao/plano_de_trabalho/): plano EA019.
- [Entregas aos orientadores](documentacao/entregas_aos_orientadores/): pacotes por data.
- [Materiais de referência](documentacao/materiais_de_referencia/): artigos, imagens e modelos de consulta.
- [Guias e protocolos](documentacao/README.md): como executar e interpretar o projeto.

Os dados diários, horários e mensais de `dados/brutos/` representam resoluções
ou períodos diferentes; não são cópias para apagar.

## O que foi unificado

| Antes | Agora |
|---|---|
| `codigo_fonte/`, `scripts/`, `executaveis/` e programas soltos na raiz | `codigo_fonte/`, organizado pela tarefa |
| `relatorios/` | `resultados/relatorios/` |
| `output/pdf/` | `resultados/pdf/` |
| `testes/` e `tests/` | `testes/` |

O [registro da reorganização](documentacao/organizacao/reorganizacao_codigo_20261027.json)
mapeia os caminhos antigos. As
[fontes originais arquivadas](documentacao/organizacao/fontes_antes_reorganizacao_20261027.zip)
preservam os bytes usados pelas auditorias anteriores. Os manifestos históricos
continuam descrevendo a execução da época.

O [inventário de pastas](documentacao/organizacao/inventario_de_pastas.csv)
mostra quantidade de arquivos e tamanho por pasta. As linhas das pastas maiores
incluem suas subpastas; não some todas as linhas. Git, ambientes, ferramentas,
caches e `tmp/` ficam fora do inventário.

`.venv/`, `.tools/` e `.git/` são pastas técnicas do ambiente e do histórico.
`tmp/` ainda contém estados importantes de recuperação; a limpeza deve considerar
o conteúdo de cada arquivo.
