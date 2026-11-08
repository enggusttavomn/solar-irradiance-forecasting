'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path').win32;
const { createController, ignored } = require('../extension');

class Clock {
  constructor() { this.time = 0; this.next = 1; this.tasks = new Map(); }
  set(callback, delay) {
    const id = this.next++;
    this.tasks.set(id, { due: this.time + delay, callback });
    return id;
  }
  advance(ms) {
    const end = this.time + ms;
    let iterations = 0;
    while (true) {
      const next = [...this.tasks.entries()].filter(([, value]) => value.due <= end)
        .sort((a, b) => a[1].due - b[1].due)[0];
      if (!next) break;
      assert.ok(++iterations < 100, 'Possivel repeticao de timer sem trabalho pendente');
      this.time = next[1].due;
      this.tasks.delete(next[0]);
      next[1].callback();
    }
    this.time = end;
  }
}

function uri(fsPath, scheme = 'file') {
  return { fsPath: path.resolve(fsPath), scheme, toString() { return `${scheme}://${this.fsPath}`; } };
}

function setup() {
  const clock = new Clock();
  const handlers = {};
  const commands = {};
  const children = [];
  const messages = [];
  let killed = 0;
  const folders = [
    { name: 'EA019', uri: uri('C:\\Projetos\\1) EA019 & projeto $com espacos') },
    { name: 'Outro', uri: uri('C:\\Projetos\\Outro') },
  ];
  const config = new Map([
    [folders[0].uri.fsPath, { enabled: true, delaySeconds: 15,
      pythonPath: '.tools/python/python.exe', gitPath: 'C:\\Program Files\\Git\\cmd\\git.exe' }],
    [folders[1].uri.fsPath, { enabled: false }],
  ]);
  function subscribe(name) {
    return callback => { handlers[name] = callback; return { dispose() { delete handlers[name]; } }; };
  }
  const vscode = {
    workspace: {
      isTrusted: true,
      workspaceFolders: folders,
      getWorkspaceFolder(selected) {
        return folders.find(folder => selected.fsPath === folder.uri.fsPath
          || selected.fsPath.startsWith(folder.uri.fsPath + '\\'));
      },
      getConfiguration(namespace, selected) {
        assert.equal(namespace, 'ea019GitHubSync');
        const settings = config.get(selected.fsPath) || {};
        return {
          get(key, fallback) { return settings[key] ?? fallback; },
          inspect(key) { return { workspaceFolderValue: settings[key] }; },
        };
      },
      onDidSaveTextDocument: subscribe('save'),
      onDidSaveNotebookDocument: subscribe('notebook'),
      onDidCreateFiles: subscribe('create'),
      onDidDeleteFiles: subscribe('delete'),
      onDidRenameFiles: subscribe('rename'),
      onDidChangeConfiguration: subscribe('config'),
    },
    window: {
      createOutputChannel() { return { appendLine: message => messages.push(message), dispose() {} }; },
    },
    commands: {
      registerCommand(name, callback) {
        commands[name] = callback;
        return { dispose() { delete commands[name]; } };
      },
    },
  };
  const controller = createController(vscode, {
    path, existsSync: () => true, now: () => clock.time,
    setTimeout: (callback, delay) => clock.set(callback, delay),
    clearTimeout: id => clock.tasks.delete(id),
    execFile(file, args, options, callback) {
      children.push({ file, args, options, callback });
      return { kill() { killed++; } };
    },
  });
  return {
    clock, handlers, commands, children, messages, folders, config, vscode, controller,
    source: name => uri(path.join(folders[0].uri.fsPath, name || 'codigo_fonte/modelo.py')),
    save(name) { handlers.save({ uri: this.source(name) }); },
    complete(index, state = 'synced', error = null) {
      children[index].callback(error, JSON.stringify({ state, message: 'resultado' }));
    },
    get killed() { return killed; },
  };
}

test('ativacao e repouso nao iniciam processos nem timers; escopo e confianca respeitados', () => {
  const f = setup();
  f.clock.advance(600000);
  assert.equal(f.children.length, 0);
  assert.equal(f.clock.tasks.size, 0);
  f.handlers.save({ uri: uri(path.join(f.folders[1].uri.fsPath, 'outro.py')) });
  f.handlers.save({ uri: uri('C:\\fora\\arquivo.py') });
  f.handlers.save({ uri: uri('C:\\fora\\arquivo.py', 'untitled') });
  f.vscode.workspace.isTrusted = false;
  f.save();
  f.clock.advance(60000);
  assert.equal(f.children.length, 0);
  assert.equal(f.clock.tasks.size, 0);
  f.controller.dispose();
});

test('enabled apenas global nao habilita envio neste projeto', () => {
  const f = setup();
  const original = f.vscode.workspace.getConfiguration;
  f.vscode.workspace.getConfiguration = (namespace, selected) => {
    const config = original(namespace, selected);
    return {
      get(key, fallback) { return key === 'enabled' ? true : config.get(key, fallback); },
      inspect(key) { return key === 'enabled' ? { globalValue: true } : config.inspect(key); },
    };
  };
  f.save();
  f.commands['ea019GitHubSync.syncNow'](f.source());
  f.clock.advance(600000);
  assert.equal(f.children.length, 0);
  assert.equal(f.clock.tasks.size, 0);
  f.controller.dispose();
});

test('salvamentos agrupados executam um ciclo depois do ultimo save, sem shell e sem janela', () => {
  const f = setup();
  f.save();
  f.clock.advance(10000);
  f.save('novo arquivo.py');
  f.clock.advance(14999);
  assert.equal(f.children.length, 0);
  f.clock.advance(1);
  assert.equal(f.children.length, 1);
  const child = f.children[0];
  assert.equal(child.file, path.join(f.folders[0].uri.fsPath, '.tools/python/python.exe'));
  assert.deepEqual(child.args, [
    path.join(f.folders[0].uri.fsPath, 'codigo_fonte/publicacoes/sincronizar_automaticamente.py'),
    '--repo', f.folders[0].uri.fsPath, '--branch', 'main', '--remote', 'origin',
    '--quiet-seconds', '15', '--git', 'C:\\Program Files\\Git\\cmd\\git.exe',
  ]);
  assert.equal(child.options.windowsHide, true);
  assert.equal(child.options.shell, false);
  assert.equal(child.options.cwd, f.folders[0].uri.fsPath);
  assert.ok(!child.args.includes('--watch'));
  f.complete(0);
  f.clock.advance(600000);
  assert.equal(f.children.length, 1);
  assert.equal(f.clock.tasks.size, 0);
  f.controller.dispose();
});

test('logs e caches ignorados nao adiam salvamento de fonte', () => {
  const f = setup();
  f.save();
  f.clock.advance(10000);
  for (const relative of ['.git/index', '.venv/Scripts/python.exe', '__pycache__/a.pyc',
    'tmp/a.txt', 'resultados/logs/treino.log', 'resultados/pdf/a.pdf', '.tools/python/x',
    'node_modules/a.js', '.venv-gpu/a', 'artigo/a.aux']) f.save(relative);
  f.clock.advance(5000);
  assert.equal(f.children.length, 1);
  f.complete(0);
  f.controller.dispose();
});

test('alteracao durante envio entra na fila sem concorrencia e aguarda ultima pausa', () => {
  const f = setup();
  f.save();
  f.clock.advance(15000);
  f.clock.advance(1000);
  f.save('outro.py');
  f.clock.advance(10000);
  assert.equal(f.children.length, 1);
  f.complete(0);
  f.clock.advance(4999);
  assert.equal(f.children.length, 1);
  f.clock.advance(1);
  assert.equal(f.children.length, 2);
  f.complete(1);
  assert.equal(f.clock.tasks.size, 0);
  assert.equal(f.killed, 0);
  f.controller.dispose();
});

test('novo arquivo, rename, delete e notebook usam os eventos do proprio editor', () => {
  const f = setup();
  f.handlers.create({ files: [f.source('novo.py')] });
  f.clock.advance(5000);
  f.handlers.rename({ files: [{ oldUri: f.source('novo.py'), newUri: f.source('renomeado.py') }] });
  f.clock.advance(5000);
  f.handlers.delete({ files: [f.source('renomeado.py')] });
  f.clock.advance(5000);
  f.handlers.notebook({ uri: f.source('notebooks/teste.ipynb') });
  f.clock.advance(14999);
  assert.equal(f.children.length, 0);
  f.clock.advance(1);
  assert.equal(f.children.length, 1);
  f.complete(0);
  f.controller.dispose();
});

test('desabilitar ou perder confianca antes do envio impede a execucao', () => {
  const f = setup();
  f.save();
  f.config.get(f.folders[0].uri.fsPath).enabled = false;
  f.handlers.config({ affectsConfiguration: () => true });
  f.clock.advance(60000);
  assert.equal(f.children.length, 0);
  assert.equal(f.clock.tasks.size, 0);
  f.config.get(f.folders[0].uri.fsPath).enabled = true;
  f.handlers.config({ affectsConfiguration: () => true });
  assert.equal(f.clock.tasks.size, 0);
  f.save();
  f.vscode.workspace.isTrusted = false;
  f.clock.advance(60000);
  assert.equal(f.children.length, 0);
  f.controller.dispose();
});

test('offline/error aguardam novo save; waiting faz apenas continuacao do trabalho pendente', () => {
  const f = setup();
  f.save();
  f.clock.advance(15000);
  f.complete(0, 'offline', { code: 1 });
  f.clock.advance(600000);
  assert.equal(f.children.length, 1);
  assert.equal(f.clock.tasks.size, 0);
  f.save();
  f.clock.advance(15000);
  f.complete(1, 'waiting');
  f.clock.advance(14999);
  assert.equal(f.children.length, 2);
  f.clock.advance(1);
  assert.equal(f.children.length, 3);
  f.complete(2);
  assert.equal(f.clock.tasks.size, 0);
  f.controller.dispose();
});

test('dispose cancela debounce e nunca encerra Git em andamento', () => {
  const f = setup();
  f.save();
  f.clock.advance(15000);
  f.save();
  f.controller.dispose();
  f.complete(0);
  f.clock.advance(600000);
  assert.equal(f.children.length, 1);
  assert.equal(f.killed, 0);
  assert.equal(f.clock.tasks.size, 0);
  assert.equal(Object.keys(f.handlers).length, 0);
  const pending = setup();
  pending.save();
  pending.controller.dispose();
  pending.clock.advance(60000);
  assert.equal(pending.children.length, 0);
});

test('comando manual executa de imediato, mantem escopo e permite Python absoluto', () => {
  const f = setup();
  f.config.get(f.folders[0].uri.fsPath).pythonPath = 'C:\\Python\\python.exe';
  f.commands['ea019GitHubSync.syncNow'](f.source());
  f.clock.advance(0);
  assert.equal(f.children.length, 1);
  assert.equal(f.children[0].file, 'C:\\Python\\python.exe');
  f.complete(0);
  f.commands['ea019GitHubSync.syncNow'](uri(path.join(f.folders[1].uri.fsPath, 'a.py')));
  f.clock.advance(60000);
  assert.equal(f.children.length, 1);
  f.controller.dispose();
});

test('runner fora do workspace e workspace removida nao executam', () => {
  const f = setup();
  f.config.get(f.folders[0].uri.fsPath).runner = '../outro/worker.py';
  f.save();
  f.clock.advance(60000);
  assert.equal(f.children.length, 0);
  f.config.get(f.folders[0].uri.fsPath).runner = 'codigo_fonte/publicacoes/sincronizar_automaticamente.py';
  f.save();
  f.folders.shift();
  f.clock.advance(60000);
  assert.equal(f.children.length, 0);
  f.controller.dispose();
});

test('filtro nao ignora arquivos-fonte comuns nem README de PDFs', () => {
  for (const relative of ['codigo/modelo.py', 'README.md', 'resultados/pdf/README.md',
    'notebooks/estudo.ipynb']) assert.equal(ignored(relative), false, relative);
});
