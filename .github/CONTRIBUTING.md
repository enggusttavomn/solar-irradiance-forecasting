# Como contribuir

Contribuições que melhorem a correção, a reprodutibilidade ou a documentação
são bem-vindas. Como este repositório também preserva artefatos científicos,
mudanças em dados e resultados exigem rastreabilidade adicional.

## Preparar o ambiente

1. Crie uma branch a partir de `main`.
2. Use CPython 3.12 e um ambiente virtual.
3. Instale `requirements.txt` para o ambiente completo ou
   `requirements-test.txt` para a suíte de CI.
4. Execute `python -m pytest -q` antes de abrir o pull request.

## Diretrizes

- Mantenha credenciais apenas em `.env`; nunca versione chaves da NREL, tokens
  do Overleaf ou dados pessoais.
- Consulte o [guia da estrutura](../documentacao/estrutura_do_projeto.md)
  antes de criar ou mover arquivos. Use `codigo_fonte/` para lógica
  reutilizável e a subpasta adequada de `scripts/` para comandos e automações de coleta, treinamento,
  auditoria, operação, relatórios ou apresentações.
- Chame os comandos agrupados com `python -m scripts.<grupo>.<comando>` a
  partir da raiz. As implementações existentes continuam disponíveis nos
  caminhos originais para preservar manifestos, hashes e retomadas.
- Preserve os quatro executáveis científicos da raiz e os arquivos
  registrados por manifestos e auditorias. Uma nova implementação deve ter
  seu próprio caminho; uma alteração deliberada do contrato exige atualizar
  a proveniência e validar os artefatos afetados.
- Não altere manualmente tabelas e figuras derivadas. Atualize o gerador e
  regenere os artefatos a partir das fontes versionadas.
- Uma nova execução publicável deve registrar configuração, sementes, versão
  do ambiente, status e hashes dos insumos relevantes.
- Guarde resultados científicos e sua proveniência em `resultados/`,
  auditorias e revisões datadas em `relatorios/` e guias em `documentacao/`.
  Use uma pasta nova para cada execução que produza evidência.
- Use `output/` para prévias e saídas temporárias locais. Não versione caches,
  logs novos sem valor de auditoria, ambientes virtuais ou saídas
  intermediárias; preserve os registros científicos existentes.
- Adicione testes científicos em `testes/` e testes dos scripts e
  supervisores em `testes/operacao/`. Os testes históricos em `tests/` mantêm
  seus caminhos por contratos de auditoria; novos testes seguem `testes/`.
- Evite adicionar binários grandes quando um script e uma fonte verificável
  puderem reproduzi-los.
- Documente limitações metodológicas junto com qualquer novo resultado.

## Pull request

Explique o problema, a solução e como a mudança foi validada. Se houver
alteração numérica, identifique exatamente os arquivos de entrada, o comando de
execução e os artefatos afetados. Pull requests devem manter a suíte verde e
não podem misturar uma reorganização ampla com mudanças científicas não
relacionadas.
