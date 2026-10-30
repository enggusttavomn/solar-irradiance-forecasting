# Como contribuir

O projeto preserva código e evidências científicas. Mudanças devem deixar
claro o que foi alterado e como o comportamento foi conferido.

## Preparar o ambiente

1. Crie uma branch a partir de `main`.
2. Use CPython 3.12 e um ambiente virtual.
3. Instale `requirements.txt` ou `requirements-test.txt` para a suíte de CI.
4. Execute `python -m pytest -q` antes de abrir o pull request.

## Onde trabalhar

- Use `codigo_fonte/<tarefa>/` para funções, programas e comandos da mesma área.
  O [catálogo](../codigo_fonte/COMANDOS.md) mostra as entradas disponíveis.
- Execute módulos a partir da raiz: `python -m codigo_fonte.<area>.<modulo>`.
- Guarde previsões, métricas, modelos treinados e manifestos em `resultados/`.
  Análises e auditorias vão em `resultados/relatorios/`; PDFs exportados em
  `resultados/pdf/`. Use uma pasta nova por execução.
- Coloque guias e protocolos em `documentacao/`, manuscritos em `artigos/`,
  entradas em `dados/` e testes em `testes/`. Os testes de operação local
  ficam em `testes/operacao/`.
- Use `tmp/` para prévias provisórias. Não versione ambientes, caches ou
  arquivos intermediários sem valor de evidência.

Consulte o [guia da estrutura](../documentacao/estrutura_do_projeto.md) antes
de criar ou mover arquivos. A
[migração registrada](../documentacao/organizacao/reorganizacao_codigo_20261027.json)
preserva fontes originais de auditorias; os manifestos históricos mantêm
seus dados da época.

## Cuidados com a pesquisa

- Mantenha credenciais somente em `.env` ou nos mecanismos locais configurados.
- Regere tabelas e figuras pelo código em vez de editar derivados manualmente.
- Registre configuração, sementes, ambiente, status e hashes das entradas de
  uma nova execução publicável.
- Preserve evidências anteriores e documente limitações metodológicas.
- Evite binários grandes quando fontes e geradores verificáveis forem suficientes.

## Pull request

Explique o problema, a mudança e a validação. Se houver alteração numérica,
identifique entradas, comando e artefatos afetados. Separe mudanças científicas
sem relação de uma reorganização do código e mantenha a suíte de testes verde.
