'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { execFile } = require('node:child_process');

const NAMESPACE = 'ea019GitHubSync';
const DEFAULT_RUNNER = 'codigo_fonte/publicacoes/sincronizar_automaticamente.py';

function inside(root, target, paths = path) {
  const relative = paths.relative(root, target);
  return relative === '' || (!paths.isAbsolute(relative) && relative !== '..'
    && !relative.startsWith(`..${paths.sep}`));
}

function ignored(relative) {
  const parts = relative.replace(/\\/g, '/').toLowerCase().split('/').filter(Boolean);
  if (!parts.length) return false;
  const caches = new Set(['.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', '.tox', '.nox', '.hypothesis', '.matplotlib-cache',
    '.uv-cache', '.uv-python', '.ipynb_checkpoints', '.notebook_check',
    'node_modules', 'htmlcov', '.idea']);
  if (parts.some(part => caches.has(part) || part.startsWith('.venv-'))) return true;
  if (['tmp', '.tools', '.aws', '.ssh', '.consolidacao', '.overleaf-sync'].includes(parts[0])) return true;
  if (parts[0].startsWith('.codex_')) return true;
  if (parts[0] === 'resultados') {
    if (['logs', 'rascunhos_artigos'].includes(parts[1])) return true;
    if (parts[1] === 'pdf' && parts.slice(2).join('/') !== 'readme.md') return true;
    if (/smoke|^validacao_|^avaliacao_horaria_timesnet_corrigida|^avaliacao_multirresolucao_corrigida/.test(parts[1] || '')) return true;
  }
  const leaf = parts[parts.length - 1];
  return /\.(py[cod]|aux|bbl|bcf|blg|fdb_latexmk|fls|lof|lot|out|toc|swp|orig|rej)$/.test(leaf)
    || /\.(run\.xml|synctex\.gz)$/.test(leaf) || leaf.endsWith('~')
    || leaf.startsWith('~$') || leaf === '.ds_store';
}

function createController(vscode, overrides = {}) {
  const deps = {
    execFile, existsSync: fs.existsSync, path, now: Date.now,
    setTimeout, clearTimeout, ...overrides,
  };
  const states = new Map();
  const subscriptions = [];
  const output = vscode.window.createOutputChannel('EA019: GitHub ao salvar');
  let disposed = false;

  function log(message) {
    if (!disposed) output.appendLine(`[${new Date(deps.now()).toISOString()}] ${message}`);
  }

  function folderKey(folder) { return folder.uri.toString(); }

  function configuration(folder) {
    if (disposed || !vscode.workspace.isTrusted || folder?.uri.scheme !== 'file') return null;
    const current = vscode.workspace.getWorkspaceFolder(folder.uri);
    if (!current || folderKey(current) !== folderKey(folder)) return null;
    const config = vscode.workspace.getConfiguration(NAMESPACE, folder.uri);
    const inspection = config.inspect('enabled');
    const explicitEnabled = inspection?.workspaceFolderValue !== undefined
      ? inspection.workspaceFolderValue : inspection?.workspaceValue;
    if (explicitEnabled !== true) return null;
    if (config.get('enabled', false) !== true) return null;
    const root = folder.uri.fsPath;
    const configuredRunner = config.get('runner', DEFAULT_RUNNER);
    if (typeof configuredRunner !== 'string' || !configuredRunner.trim()) return null;
    const runner = deps.path.resolve(root, configuredRunner);
    if (!inside(root, runner, deps.path) || !deps.existsSync(runner)) return null;
    const configuredPython = config.get('pythonPath', '.venv/Scripts/python.exe');
    if (typeof configuredPython !== 'string' || !configuredPython.trim()) return null;
    const python = deps.path.resolve(root, configuredPython);
    const configuredDelay = Number(config.get('delaySeconds', 15));
    const delayMs = Number.isFinite(configuredDelay) && configuredDelay >= 0 && configuredDelay <= 3600
      ? configuredDelay * 1000 : 15000;
    const git = config.get('gitPath', 'git');
    if (typeof git !== 'string' || !git.trim()) return null;
    return { root, runner, python, git, delayMs };
  }

  function cancelTimer(state) {
    if (state.timer !== null) deps.clearTimeout(state.timer);
    state.timer = null;
  }

  function schedule(state) {
    cancelTimer(state);
    if (disposed || state.running || !state.pending) return;
    const config = configuration(state.folder);
    if (!config) { state.pending = false; return; }
    const remaining = Math.max(0, state.lastSave + config.delayMs - deps.now());
    state.timer = deps.setTimeout(() => { state.timer = null; run(state); }, remaining);
  }

  function resultFromOutput(stdout) {
    for (const line of String(stdout || '').trim().split(/\r?\n/).reverse()) {
      try {
        const result = JSON.parse(line);
        if (typeof result.state === 'string') return result;
      } catch { /* O worker de um ciclo escreve um resultado JSON. */ }
    }
    return null;
  }

  function run(state) {
    const config = configuration(state.folder);
    if (disposed || state.running || !state.pending || !config) return;
    state.pending = false;
    state.running = true;
    log(`${state.folder.name}: iniciando sincronizacao.`);
    const finished = (error, stdout) => {
      state.running = false;
      if (disposed) return;
      const result = resultFromOutput(stdout);
      if (result) log(`${state.folder.name}: ${result.state}: ${String(result.message || '')}`);
      else if (error) log(`${state.folder.name}: envio nao concluido (codigo ${error.code || 'desconhecido'}). Consulte .git/auto-sync/sync.log; um novo salvamento tenta novamente.`);
      else log(`${state.folder.name}: ciclo encerrado.`);
      if (result?.state === 'waiting' && !state.pending) {
        state.pending = true;
        state.lastSave = deps.now();
      }
      // Falhas/rede nao criam ciclos periodicos: o proximo salvamento retoma.
      if (state.pending) schedule(state);
    };
    try {
      deps.execFile(config.python,
        [config.runner, '--repo', config.root, '--branch', 'main', '--remote', 'origin',
          '--quiet-seconds', String(config.delayMs / 1000), '--git', config.git],
        { cwd: config.root, windowsHide: true, shell: false, maxBuffer: 1024 * 1024 },
        finished);
    } catch (error) { finished(error, ''); }
  }

  function queue(folder, immediate = false) {
    const config = configuration(folder);
    if (!config) return;
    const key = folderKey(folder);
    let state = states.get(key);
    if (!state) {
      state = { folder, running: false, pending: false, lastSave: 0, timer: null };
      states.set(key, state);
    }
    state.pending = true;
    state.lastSave = deps.now() - (immediate ? config.delayMs : 0);
    schedule(state);
  }

  function changed(uri) {
    if (disposed || !uri || uri.scheme !== 'file' || !vscode.workspace.isTrusted) return;
    const folder = vscode.workspace.getWorkspaceFolder(uri);
    if (!folder || !inside(folder.uri.fsPath, uri.fsPath, deps.path)) return;
    if (ignored(deps.path.relative(folder.uri.fsPath, uri.fsPath))) return;
    queue(folder);
  }

  subscriptions.push(vscode.workspace.onDidSaveTextDocument(document => changed(document.uri)));
  subscriptions.push(vscode.workspace.onDidSaveNotebookDocument(document => changed(document.uri)));
  subscriptions.push(vscode.workspace.onDidCreateFiles(event => event.files.forEach(changed)));
  subscriptions.push(vscode.workspace.onDidDeleteFiles(event => event.files.forEach(changed)));
  subscriptions.push(vscode.workspace.onDidRenameFiles(event => event.files.forEach(file => {
    changed(file.oldUri);
    changed(file.newUri);
  })));
  subscriptions.push(vscode.commands.registerCommand('ea019GitHubSync.syncNow', uri => {
    const selected = uri || vscode.window.activeTextEditor?.document.uri;
    const folder = selected ? vscode.workspace.getWorkspaceFolder(selected)
      : vscode.workspace.workspaceFolders?.find(candidate => configuration(candidate));
    if (folder) queue(folder, true);
  }));
  subscriptions.push(vscode.workspace.onDidChangeConfiguration(event => {
    if (!event.affectsConfiguration(NAMESPACE)) return;
    for (const state of states.values()) {
      if (!configuration(state.folder)) {
        cancelTimer(state);
        state.pending = false;
      } else if (state.pending) schedule(state);
    }
  }));

  return {
    dispose() {
      if (disposed) return;
      disposed = true;
      for (const state of states.values()) cancelTimer(state);
      for (const subscription of subscriptions) subscription.dispose();
      states.clear();
      output.dispose();
      // Nunca interromper um Git em andamento ao fechar o editor.
    },
  };
}

function activate(context) {
  context.subscriptions.push(createController(require('vscode')));
}

module.exports = { activate, createController, ignored, inside };
