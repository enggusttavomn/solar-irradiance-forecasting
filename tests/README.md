# Testes de contratos históricos

Os testes Python desta pasta mantêm caminhos e conteúdos registrados em
manifestos, snapshots ou recibos de auditoria. Esses registros permitem conferir
as fontes usadas nas execuções históricas.

Os novos testes operacionais ficam em [`testes/operacao/`](../testes/operacao/README.md).
A configuração do `pytest` inclui esta pasta na execução padrão:

```powershell
python -m pytest -q
```

Para executar somente os testes históricos:

```powershell
python -m pytest tests -q
```

Antes de mover, renomear ou alterar um teste registrado em uma auditoria,
verifique os caminhos e hashes que o referenciam nos artefatos de execução.
