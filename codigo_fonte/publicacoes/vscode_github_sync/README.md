# EA019: GitHub ao salvar

Extensão local do VS Code que chama o sincronizador do projeto após salvar.
Utiliza os eventos do próprio editor e executa Python/Git somente durante o envio.
Não cria monitor externo, tarefa do Windows, varredura da pasta ou timer periódico.
Sua ativação não dispara um envio.

Habilite apenas na configuração da pasta desejada, em `.vscode/settings.json`:

```json
{
  "ea019GitHubSync.enabled": true,
  "ea019GitHubSync.delaySeconds": 15,
  "ea019GitHubSync.runner": "codigo_fonte/publicacoes/sincronizar_automaticamente.py",
  "ea019GitHubSync.pythonPath": ".venv/Scripts/python.exe",
  "ea019GitHubSync.gitPath": "git"
}
```

O Python pode ser informado com caminho absoluto ou relativo ao projeto.
O runner precisa estar dentro da pasta e executa apenas um ciclo, sem `--watch`.
O workspace deve ser confiável. O comportamento permanece desabilitado por padrão.

Salvamentos de textos e notebooks, além de criação, renomeação e exclusão feitas
pelo próprio VS Code, agrupam alterações e iniciam o envio após 15 segundos.
Alterações durante um envio geram um novo ciclo quando houver pausa nos salvamentos.
Caches, ambientes, arquivos temporários e logs locais não adiam o envio.

Alterações feitas por programas externos não acionam a extensão. Elas podem entrar
no próximo envio iniciado por um salvamento no VS Code. Quando o editor está fechado,
nenhum monitor desta extensão continua executando. Um envio já iniciado pode concluir.
Aguarde a pausa configurada e a conclusão do envio antes de fechar o editor.

A extensão preserva as guardas do sincronizador existente: não faz pull, push forçado
ou mudanças nos arquivos staged. Se rede, autenticação ou guardas impedirem o envio,
consulte o painel de saída **EA019: GitHub ao salvar**. Um novo salvamento tenta novamente.
O comando **EA019: Enviar alteracoes ao GitHub agora** também inicia um ciclo manual.

Para instalar um pacote local: `code --install-extension ea019-github-sync-1.0.0.vsix`.
Para testar o núcleo: `node --test test/extension.test.js`.
