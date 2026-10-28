# Comandos do projeto

Esta pasta oferece nomes curtos e organizados para as operacoes mais comuns.
Execute os comandos como modulos a partir da raiz do repositorio.

| Objetivo | Comando |
|---|---|
| Executar a avaliacao mensal | `python -m scripts.executar_experimento --help` |
| Gerar as figuras oficiais | `python -m scripts.gerar_figuras --help` |
| Gerar o site de visualizacao | `python site/gerar_site.py` |
| Preencher os artigos | `python -m scripts.preencher_artigos --help` |
| Buscar hiperparametros mensais da TimesNet | `python -m scripts.otimizar_timesnet_mensal --help` |

A busca mensal possui [guia de execu??o e resultados](../documentacao/OTIMIZACAO_TIMESNET_MENSAL.md),
com separa??o entre sele??o em 2023 e avalia??o retrospectiva em 2024.

## Sincronizar uma branch com o GitHub

Depois de revisar o diff, executar os testes e criar o commit, use um dos
atalhos abaixo para atualizar e enviar a branch atual:

- Windows: clique duas vezes em `scripts/sincronizar_projeto.cmd`.
- Linux/macOS: execute `bash scripts/sincronizar_projeto.sh`.

O sincronizador não adiciona arquivos nem cria commits. Ele interrompe a
execução quando há alterações locais, incorpora atualizações remotas com
`pull --rebase` e envia a branch atual. Isso evita que caches, credenciais ou
resultados ainda não revisados sejam publicados por um clique acidental.

Os executaveis antigos da raiz permanecem disponiveis porque seus caminhos
fazem parte do manifesto da execucao canonica.

## Publicar o artigo no Overleaf

No Windows, execute `scripts/sincronizar_overleaf.cmd`. O atalho publica apenas
`artigos/revista_unificado` no projeto Overleaf configurado. No primeiro
uso, informe `git` como usuario e um token de autenticacao do Overleaf como
senha; o Git Credential Manager pode guardar a credencial para os proximos usos.

Arquivos temporarios de compilacao e `main.pdf` nao sao enviados. O espelho
tecnico fica na pasta temporaria do Windows e nao entra no repositorio.

A publicacao e um espelho exato da pasta do artigo: arquivos e imagens removidos
ou renomeados localmente tambem sao removidos do Overleaf. A pasta `.git` do
espelho e protegida e nunca participa dessa limpeza.

O workflow `.github/workflows/sincronizar-overleaf.yml` faz a mesma publicacao
automaticamente quando uma alteracao do artigo chega a branch `main`. Para
ativa-lo, crie no GitHub Actions o secret `OVERLEAF_TOKEN` com um token gerado
nas configuracoes da conta Overleaf.

O GitHub é a fonte oficial. O monitor cria commits apenas em branches de
trabalho e envia a branch ativa; ele se recusa a criar commits automáticos na
`main`. Quando a alteração revisada chega à `main`, a GitHub Action espelha o
manuscrito no Overleaf. Edições realizadas somente no editor web podem ser
substituídas na publicação seguinte.

### Monitor automatico no Windows

`scripts/configurar_monitor_overleaf.ps1` registra o monitor no início da
sessão do usuário e o executa em segundo plano. Ele espera 12 segundos após o
último salvamento, envia somente a pasta do artigo para a branch de trabalho e
continua aguardando. O workflow publica no Overleaf após a integração na
`main`.

Para remover a inicializacao automatica, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/configurar_monitor_overleaf.ps1 -Remover
```

O log fica em `%LOCALAPPDATA%\TCC\OverleafSync\monitor.log`.
