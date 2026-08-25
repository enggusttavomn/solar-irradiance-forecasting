# Comandos do projeto

Esta pasta oferece nomes curtos e organizados para as operacoes mais comuns.
Execute os comandos como modulos a partir da raiz do repositorio.

| Objetivo | Comando |
|---|---|
| Executar a avaliacao mensal | `python -m scripts.executar_experimento --help` |
| Gerar as figuras oficiais | `python -m scripts.gerar_figuras --help` |
| Gerar o site de visualizacao | `python site/gerar_site.py` |
| Preencher os artigos | `python -m scripts.preencher_artigos --help` |

## Salvar alteracoes no GitHub

Depois de clonar o projeto no computador, use um dos atalhos abaixo sempre que
quiser criar um commit e enviar todas as alteracoes para o GitHub:

- Windows: clique duas vezes em `scripts/sincronizar_projeto.cmd`.
- Linux/macOS: execute `bash scripts/sincronizar_projeto.sh`.

O sincronizador registra os arquivos alterados, cria um commit datado, incorpora
eventuais atualizacoes remotas e envia a branch `main`. Revise arquivos com
senhas ou dados privados antes de executar; `.env` ja esta ignorado pelo Git.

Os executaveis antigos da raiz permanecem disponiveis porque seus caminhos
fazem parte do manifesto da execucao canonica.
