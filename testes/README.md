# Testes

Execute a suíte a partir da raiz:

```bash
python -m pytest -q
```

Os testes cobrem preparação de dados, modelos, métricas, retomada,
reprodutibilidade, geração de figuras, integridade dos manuscritos e contratos
da estrutura pública. Use arquivos temporários do `pytest` para novas saídas de
teste; não grave resultados smoke permanentes em `resultados/`.
