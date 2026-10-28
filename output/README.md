# Saídas temporárias locais

Use esta pasta para prévias, renderizações de conferência, exportações
provisórias e arquivos intermediários que podem ser gerados novamente.
Seu conteúdo é local e ignorado pelo Git, com exceção deste guia.

Organize novas saídas em uma subpasta como `assunto_AAAAMMDD/` e registre no
código ou no relatório o comando necessário para recriá-las. Antes de
remover arquivos, confirme que não são fontes únicas nem evidências usadas
por um manifesto ou por uma retomada.

Quando um artefato precisar ser preservado, coloque-o na pasta adequada:

| Finalidade | Destino |
|---|---|
| Resultado científico e proveniência | [`resultados/`](../resultados/) |
| Auditoria ou revisão de uma execução | [`relatorios/`](../relatorios/) |
| Guia ou documento de entrega | [`documentacao/`](../documentacao/) |
| Manuscrito e suas figuras finais | [`artigos/`](../artigos/) |

As saídas já existentes mantêm seus caminhos para evitar alterações em
rotinas locais. Consulte o [guia da estrutura](../documentacao/estrutura_do_projeto.md)
antes de reorganizar artefatos usados pelo estudo.
