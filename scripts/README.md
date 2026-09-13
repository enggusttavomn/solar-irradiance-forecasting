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

## Publicar o artigo no Overleaf

No Windows, execute `scripts/sincronizar_overleaf.cmd`. O atalho publica apenas
`overlief/artigo_revista_unificado` no projeto Overleaf configurado. No primeiro
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

O GitHub e a fonte oficial. O monitor cria um commit da pasta do artigo e envia
a branch ativa; a GitHub Action entao espelha esse commit no Overleaf. Edicoes
realizadas somente no editor web podem ser substituidas na publicacao seguinte;
comentarios e o acompanhamento do orientador continuam disponiveis no Overleaf.

### Monitor automatico no Windows

`scripts/configurar_monitor_overleaf.ps1` registra o monitor no inicio da sessao
do usuario e o executa em segundo plano. Ele espera 12 segundos apos o ultimo
salvamento, publica a pasta no GitHub e continua aguardando novas alteracoes. O
workflow do GitHub e responsavel pela publicacao subsequente no Overleaf.

Para remover a inicializacao automatica, execute:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/configurar_monitor_overleaf.ps1 -Remover
```

O log fica em `%LOCALAPPDATA%\TCC\OverleafSync\monitor.log`.
