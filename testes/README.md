# Testes do projeto

Todos os testes automatizados ficam nesta pasta. Execute a suíte a partir da
raiz do repositório:

```bash
python -m pytest -q
```

Os arquivos cobrem dados, modelos, métricas, previsões, geração de arquivos,
integridade dos manuscritos, contratos de auditoria e retomadas. Os testes de
acompanhamento e operação local ficam em [`operacao/`](operacao/).

Os testes antes separados em `tests/` foram incorporados aqui. Quando dois
arquivos tinham o mesmo nome, os testes foram preservados com nomes distintos
ou reunidos conforme o assunto. O registro da reorganização identifica suas
origens.

Use dados sintéticos e diretórios temporários do pytest para novas verificações.
Não grave resultados permanentes de testes rápidos entre as evidências científicas.
