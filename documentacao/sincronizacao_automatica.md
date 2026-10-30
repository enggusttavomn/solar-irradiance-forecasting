# Sincronização automática com o GitHub

A tarefa do Windows `EA019-GitHub-AutoSync` inicia um monitor ao entrar na
conta do Windows. Ele observa as alterações salvas neste projeto e, após
15 segundos sem novos salvamentos, cria um commit e faz push para `origin/main`.
Arquivos novos, alterações, renomeações e exclusões entram no commit.
Não há verificação de envio a cada minuto: o monitor é acionado por alterações.

O monitor utiliza `pythonw.exe`, sem abrir PowerShell ou Terminal. O computador
precisa estar ligado, com sua conta conectada e acesso à internet. O ChatGPT
não precisa ficar aberto. Ao iniciar, o monitor também verifica alterações
pendentes feitas enquanto estava desligado. Sem internet, os commits permanecem
locais e o monitor tenta novamente com intervalos progressivos enquanto houver
envio pendente. Salve e aguarde o envio antes de desligar o computador.

## Instalar ou reativar

Na raiz do projeto, execute no PowerShell:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\codigo_fonte\publicacoes\configurar_sincronizacao_automatica.ps1
```

O instalador utiliza o Python de `.venv\Scripts\python.exe`, quando disponível,
ou um Python 3.10 ou superior no PATH, além do Git for Windows. É necessário
ter `pythonw.exe` junto ao Python selecionado. A tarefa guarda os caminhos
completos dos executáveis e usa as credenciais Git existentes da sua conta,
sem salvar senha no script. Executa com os privilégios normais da sua conta.
Instale-a na sua conta do Windows depois de conseguir fazer um push manual.

O Git precisa ter sua identidade configurada para criar commits. Se ainda
estiver ausente, configure-a somente neste repositório:

```powershell
git config user.name "Seu nome"
git config user.email "seu-email-do-github"
```

Reinstale se mover a pasta do projeto ou substituir o Python utilizado. A
instalação migra a tarefa antiga que executava PowerShell a cada minuto e
recusa substituir uma tarefa de outro projeto ou usuário. Ao reinstalar,
aguarda o monitor anterior concluir um eventual envio antes de substituí-lo.

## Consultar o envio

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\codigo_fonte\publicacoes\configurar_sincronizacao_automatica.ps1 -Status
```

O comando mostra a tarefa, a última execução e o resultado do sincronizador.
No modo por alteração, a tarefa permanece `Running` enquanto o monitor está
ativo; o código `267009` (`0x41301`) significa tarefa em execução.
Também é possível consultar `.git/auto-sync/status.json`,
`.git/auto-sync/monitor.json` e `.git/auto-sync/sync.log`. Esses arquivos são
locais e não entram nos commits. O log mantém um histórico limitado.

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
Os próprios logs do monitor não disparam novos envios.

## Desativar

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\codigo_fonte\publicacoes\configurar_sincronizacao_automatica.ps1 -Desativar
```

O comando impede o início no próximo login e solicita que o monitor encerre.
Se houver um envio em andamento, ele pode terminar normalmente antes da saída.
Para reativar, execute novamente o comando de instalação. Os sincronizadores
manuais `sincronizar_projeto.cmd` e `sincronizar_projeto.sh` continuam disponíveis.
