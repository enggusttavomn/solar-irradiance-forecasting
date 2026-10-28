# Testes operacionais

Esta pasta reúne testes de monitoramento, estimativas de tempo, integração de
controles, dados históricos e proteções de processos. Os testes usam fixtures e
simulações para verificar a operação sem iniciar treinamentos reais.

A suíte do projeto está organizada assim:

| Pasta | Responsabilidade |
| --- | --- |
| `testes/` | Dados, modelos, métricas, experimentos e integridade dos artigos. |
| `testes/operacao/` | Testes operacionais novos e testes que podem ser reorganizados sem alterar contratos históricos. |
| `tests/` | Testes cujos caminhos ou hashes aparecem em manifestos e recibos de auditoria preservados. |

Execute todos os testes a partir da raiz do projeto:

```powershell
python -m pytest -q
```

Para verificar somente a operação e os contratos históricos:

```powershell
python -m pytest testes/operacao tests -q
```

Para executar um módulo específico:

```powershell
python -m pytest testes/operacao/test_painel_progresso_quantizacao.py -q
```

O `pyproject.toml` descobre as duas pastas e usa o modo de importação `importlib`
para permitir os arquivos `test_json_atomico.py` existentes em ambas, mantendo
seus nomes e conteúdos auditados.

Adicione novos testes operacionais aqui. Prefira fixtures temporárias do `pytest`
e mocks para subprocessos; saídas de testes não devem ir para `resultados/`.

Como exceção histórica, `test_finalizar_sequencia_recuperacao.py` depende do
auxiliar local `tmp/recuperacao_20261001/finalizar_sequencia.py`. Essa referência
foi preservada durante a organização; o módulo é ignorado quando o auxiliar não
está disponível, como em um clone que não inclui os arquivos locais de `tmp/`.
