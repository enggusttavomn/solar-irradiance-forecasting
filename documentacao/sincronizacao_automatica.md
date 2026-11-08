# Sincronização do EA019 com o GitHub pelo VS Code

A sincronização está vinculada ao salvamento no VS Code, somente neste projeto.
Após 15 segundos sem novos salvamentos, a extensão local **EA019: GitHub ao salvar**
executa um ciclo de commit e envio para `origin/main`. O processo Python encerra
quando o envio termina. Em repouso, não há monitor externo nem consulta periódica
ao GitHub; a integração utiliza os eventos do VS Code já aberto.

A tarefa antiga `EA019-GitHub-AutoSync` do Windows permanece desabilitada.
Não use o instalador antigo de monitor para configurar este modo.

## Uso diário

Abra esta pasta no VS Code, edite e salve normalmente. Arquivos novos,
renomeações e exclusões feitos pelo explorador do VS Code também acionam o envio.
O ciclo considera todas as alterações elegíveis pendentes no repositório,
respeitando o `.gitignore`, e não apenas o último arquivo salvo.

Aguarde os 15 segundos e a conclusão do envio antes de fechar o editor ou desligar
o computador. Fechar o VS Code cancela um envio que ainda estava apenas agendado;
um envio já iniciado pode terminar normalmente. Alterações feitas fora do VS Code
serão consideradas no próximo salvamento pelo editor ou no comando manual abaixo.

Para iniciar um envio pelo editor, abra a paleta de comandos (`Ctrl+Shift+P`) e
selecione **EA019: Enviar alteracoes ao GitHub agora**.

Sem rede, os commits permanecem locais. Um novo salvamento ou o comando acima
tenta enviá-los novamente. Não há tentativas periódicas em segundo plano.

## Consultar o resultado

No VS Code, abra **Exibir > Saída** e escolha **EA019: GitHub ao salvar**.
O sincronizador também registra o resultado em `.git/auto-sync/status.json` e
`.git/auto-sync/sync.log`. Esses arquivos não entram nos commits.

O envio aguarda se a branch atual não for `main`, houver alterações preparadas
manualmente para commit, conflito, merge/rebase ou bloqueio Git. Conclua essa
operação e salve novamente ou use o comando de envio para retomar.

Se o GitHub tiver commits que a cópia local ainda não recebeu, o envio é
interrompido. Atualize e integre a cópia local manualmente. A automação não executa
pull, reset ou push forçado. Arquivos de 100 MiB ou mais exigem tratamento manual.

## Configuração vinculada à pasta

A habilitação e os caminhos ficam em `.vscode/settings.json`, apenas neste projeto:

```json
{
  "ea019GitHubSync.enabled": true,
  "ea019GitHubSync.delaySeconds": 15,
  "ea019GitHubSync.pythonPath": ".tools/python/cpython-3.12.16-windows-x86_64-none/python.exe",
  "ea019GitHubSync.gitPath": "C:/Program Files/Git/cmd/git.exe"
}
```

Outras preferências existentes desse arquivo devem ser preservadas. Para desligar,
defina `ea019GitHubSync.enabled` como `false`. O padrão da extensão é desabilitado
em todas as outras pastas. A extensão exige uma pasta de trabalho confiável.

O caminho do Python é relativo ao projeto e não depende do nome da pasta. Se esse
Python for substituído, ajuste o caminho na configuração. A sincronização utiliza
somente a biblioteca padrão do Python e as credenciais Git já configuradas.

## Reinstalar a extensão

O código da extensão está em `codigo_fonte/publicacoes/vscode_github_sync/`.
Para gerar um pacote instalável, execute a partir da raiz do projeto:

```powershell
& .\.tools\python\cpython-3.12.16-windows-x86_64-none\python.exe .\codigo_fonte\publicacoes\empacotar_extensao_vscode.py
```

No VS Code, selecione **Extensions: Install from VSIX...** e escolha o pacote
gerado em `.git/auto-sync/vscode/`. Preserve também as configurações acima ao
preparar outra cópia do projeto. O `.vscode` é uma configuração local e já é
ignorado pelo Git neste repositório.

Os comandos manuais de sincronização existentes continuam disponíveis. O modo
`--watch` do sincronizador é legado e não é iniciado por esta integração.
