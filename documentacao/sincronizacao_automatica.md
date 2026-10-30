# Sincronização automática com o GitHub

A tarefa do Windows `EA019-GitHub-AutoSync` verifica este projeto a cada minuto
e ao entrar na conta do Windows. Quando as alterações salvas ficam pelo menos
15 segundos sem mudanças, o sincronizador cria um commit e faz push para
`origin/main`. Arquivos novos, alterações e exclusões entram no commit.

O computador precisa estar ligado, com sua conta conectada e acesso à internet.
O ChatGPT não precisa ficar aberto. Sem internet, os commits permanecem locais
e o envio é tentado novamente nas próximas verificações. Salve e aguarde o
envio antes de desligar o computador.

## Instalar ou reativar

Na raiz do projeto, execute no PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\codigo_fonte\publicacoes\configurar_sincronizacao_automatica.ps1
```

O instalador utiliza o Python de `.venv\Scripts\python.exe`, quando disponível,
ou um Python 3.10 ou superior no PATH, além do Git for Windows. A tarefa guarda
os caminhos completos dos executáveis e funciona em segundo plano. Ela usa
as credenciais Git existentes da sua conta, sem salvar senha no script, e
executa com os privilégios normais da sua conta. Instale-a na sua conta do
Windows depois de conseguir fazer um push manual.

O Git precisa ter sua identidade configurada para criar commits. Se ainda
estiver ausente, configure-a somente neste repositório:

```powershell
git config user.name "Seu nome"
git config user.email "seu-email-do-github"
```

Reinstale se mover a pasta do projeto ou substituir o Python utilizado. A
instalação recusa substituir uma tarefa com o mesmo nome que pertença a outro
projeto ou usuário.

## Consultar o envio

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\codigo_fonte\publicacoes\configurar_sincronizacao_automatica.ps1 -Status
```

O comando mostra a tarefa, a última execução e o resultado do sincronizador.
Também é possível consultar `.git/auto-sync/status.json` e
`.git/auto-sync/sync.log`. Esses arquivos são locais e não entram nos commits.
O log mantém um histórico limitado para não crescer indefinidamente.

Para verificar o projeto sem criar commit ou fazer push:

```powershell
.\.venv\Scripts\python.exe .\codigo_fonte\publicacoes\sincronizar_automaticamente.py --check
```

## Trabalhar em outro computador

Antes de editar no outro computador, atualize sua cópia:

```powershell
git pull --ff-only
```

A tarefa funciona neste computador. Para também enviar automaticamente
alterações feitas em outro Windows, instale-a na cópia daquele computador.
Os computadores precisam receber as alterações do GitHub antes de continuar
o trabalho local. O sincronizador faz fetch e push; ele não altera seus
arquivos com pull automático.

## Quando a automação aguarda

O envio aguarda se você estiver em outra branch, com arquivos já preparados
manualmente para commit, durante merge/rebase ou enquanto houver conflito ou
bloqueio do Git. Conclua essa operação para retomar a sincronização.

Se `origin/main` tiver commits que a cópia local ainda não recebeu, a automação
interrompe o envio e registra o motivo. Atualize a cópia local e resolva os
conflitos normalmente; a automação não faz push forçado nem substitui o
histórico remoto. Arquivos com 100 MiB ou mais precisam de tratamento manual,
pois impedem um push comum para o GitHub.

O `.gitignore` continua valendo: credenciais, ambientes, caches e as saídas
locais já ignoradas, incluindo os PDFs exportados em `resultados/pdf/`, não
são enviados. O GitHub recebe as mudanças dos arquivos que fazem parte do
repositório. Mudanças ainda não salvas no editor ficam fora do envio.

## Desativar

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\codigo_fonte\publicacoes\configurar_sincronizacao_automatica.ps1 -Desativar
```

Para reativar, execute novamente o comando de instalação. Os sincronizadores
manuais `sincronizar_projeto.cmd` e `sincronizar_projeto.sh` continuam
disponíveis para o fluxo com commit manual.

Se houver um envio em andamento ao desativar, ele pode terminar normalmente;
as próximas execuções ficam desabilitadas.
