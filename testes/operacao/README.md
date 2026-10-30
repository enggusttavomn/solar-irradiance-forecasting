# Testes operacionais

Esta pasta reúne testes de monitoramento, estimativas de tempo, integração de
controles, dados históricos e proteções de processos. Os testes usam fixtures e
simulações para verificar a operação sem iniciar treinamentos reais.

A suíte do projeto está organizada assim:

| Pasta | Responsabilidade |
| --- | --- |
| `testes/` | Dados, modelos, métricas, experimentos e integridade dos artigos. |
| `testes/operacao/` | Painéis, filas, processos, retomadas e integração dos controles. |

Execute todos os testes a partir da raiz do projeto:

```powershell
python -m pytest -q
```

Para verificar somente a operação e os contratos históricos:

```powershell
python -m pytest testes/operacao -q
```

Para executar um módulo específico:

```powershell
python -m pytest testes/operacao/test_painel_progresso_quantizacao.py -q
```

O `pyproject.toml` descobre apenas `testes/`, incluindo esta subpasta, e usa o
modo de importação `importlib`. Os testes complementares de durabilidade JSON
foram reunidos no mesmo arquivo.

Adicione novos testes operacionais aqui. Prefira fixtures temporárias do `pytest`
e mocks para subprocessos; saídas de testes não devem ir para `resultados/`.

O finalizador de recuperação agora faz parte do código em
[`codigo_fonte/acompanhamento/finalizar_sequencia_recuperacao.py`](../../codigo_fonte/acompanhamento/finalizar_sequencia_recuperacao.py).
Seu teste não depende mais de um programa local em `tmp/` e também pode rodar
em um clone do projeto.
