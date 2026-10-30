"""Monitor de salvamentos: testes isolados, nunca usa o repositorio real."""

import contextlib
import importlib.util
import json
import logging
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

try:
    from codigo_fonte.publicacoes import sincronizar_automaticamente as sync
except ModuleNotFoundError:
    import sincronizar_automaticamente as sync


class MonitorTests(unittest.TestCase):
    def test_filtra_estado_e_caches_preserva_commits_manuais(self):
        for path in ('.git/auto-sync/status.json', '.git/logs/HEAD',
                     '.git/refs/remotes/origin/main', '.venv/Scripts/python.exe',
                     'codigo/__pycache__/x.pyc', 'node_modules/a/index.js',
                     'tmp/x.txt', 'resultados/logs/treino.log', 'resultados/pdf/a.pdf',
                     '.matplotlib-cache/fontlist.json', '.hypothesis/cache',
                     '.uv-cache/log', '.uv-python/python.exe', '.nox/test/log',
                     '.venv-gpu/lib/x', 'artigo/artigo.aux', '.tools/python/x',
                     'resultados/validacao_hoje/log.txt', 'resultados/test-smoke/a.txt'):
            self.assertFalse(sync.relevant_change(path), path)
        for path in ('codigo/modelo.py', 'novo.txt', 'pasta/arquivo removido.txt',
                     '.git/HEAD', '.git/index', '.git/index.lock',
                     '.git/refs/heads/main', '.git/MERGE_HEAD', '.git/rebase-merge'):
            self.assertTrue(sync.relevant_change(path), path)

    @unittest.skipUnless(os.name == 'nt', 'Notificacoes nativas requerem Windows')
    def test_overflow_windows_reconcilia_em_vez_de_parar(self):
        import ctypes
        watcher = sync.WindowsDirectoryWatcher.__new__(sync.WindowsDirectoryWatcher)
        watcher.signal = sync.ChangeSignal()
        watcher.stopping = threading.Event()
        watcher.handle = 1
        watcher.ctypes = Mock(wraps=ctypes)
        watcher.ctypes.get_last_error.return_value = 1022
        calls = []
        def read(*_args):
            calls.append(1)
            if len(calls) > 1:
                watcher.stopping.set()
            return False
        watcher.kernel = Mock()
        watcher.kernel.ReadDirectoryChangesW.side_effect = read
        watcher._read()
        self.assertEqual(watcher.signal.revision, 1)
        self.assertIsNone(watcher.signal.error)

    def test_decodifica_rename_e_delete_windows(self):
        records = []
        for action, name in ((4, 'antigo.txt'), (5, 'novo.txt'), (2, 'excluido.txt')):
            data = name.encode('utf-16-le')
            size = (12 + len(data) + 3) & ~3
            records.append(bytearray(struct.pack('<III', size, action, len(data))
                                     + data + b'\0' * (size - 12 - len(data))))
        records[-1][:4] = struct.pack('<I', 0)
        self.assertEqual(list(sync.WindowsDirectoryWatcher.changed_paths(b''.join(records))),
                         ['antigo.txt', 'novo.txt', 'excluido.txt'])

    def test_debounce_espera_ultimo_salvamento(self):
        signal = sync.ChangeSignal()
        signal.mark_changed()
        result = []
        started = time.monotonic()
        thread = threading.Thread(target=lambda: result.append(signal.wait_ready(0, .12)))
        thread.start()
        time.sleep(.07)
        signal.mark_changed()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [2])
        self.assertGreaterEqual(time.monotonic() - started, .18)

    def test_parada_acorda_monitor_ocioso(self):
        signal = sync.ChangeSignal()
        stop = threading.Event()
        result = []
        thread = threading.Thread(target=lambda: result.append(
            signal.wait_ready(0, 15, should_stop=stop.is_set)))
        thread.start()
        stop.set()
        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, [None])

    def test_alteracao_durante_sync_gera_outro_ciclo(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            signal = sync.ChangeSignal()
            git = Mock(repo=runtime)
            git.changes.return_value = []
            calls = []

            def run(*args):
                calls.append(1)
                if len(calls) == 1:
                    signal.mark_changed()
                else:
                    (runtime / 'stop-monitor').touch()
                return 'idle', 'teste'

            with patch.object(sync, 'guard', return_value=None), \
                 patch.object(sync, 'pending_locally', return_value=True), \
                 patch.object(sync, 'sync_once', side_effect=run):
                result = sync.watch_project(git, runtime, runtime, 'main', 'origin', .01,
                    logging.getLogger('test'), watcher_factory=lambda *_: contextlib.nullcontext(),
                    signal=signal)
            self.assertEqual(result, 0)
            self.assertEqual(len(calls), 2)
            self.assertFalse(json.loads((runtime / 'monitor.json').read_text())['running'])

    def test_ocioso_nao_chama_fetch(self):
        git = Mock()
        git.text.return_value = 'abc'
        git.run.return_value = subprocess.CompletedProcess([], 0, b'abc\n')
        self.assertFalse(sync.pending_locally(git, 'main', 'origin', []))
        self.assertTrue(sync.pending_locally(git, 'main', 'origin', [(' M', 'x')]))
        self.assertTrue(all(call.args[0] == 'rev-parse' for call in git.run.call_args_list))

    def test_offline_programa_retry_sem_novo_evento(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            signal = sync.ChangeSignal()
            git = Mock(repo=runtime)
            git.changes.return_value = []
            attempts = []

            def ready(handled, quiet_seconds, retry_at=None, should_stop=None):
                attempts.append(retry_at)
                if len(attempts) == 1:
                    return 1
                (runtime / 'stop-monitor').touch()
                return None

            with patch.object(signal, 'wait_ready', side_effect=ready), \
                 patch.object(sync, 'guard', return_value=None), \
                 patch.object(sync, 'pending_locally', return_value=True), \
                 patch.object(sync, 'sync_once', return_value=('offline', 'aguarde')):
                sync.watch_project(git, runtime, runtime, 'main', 'origin', .01,
                    logging.getLogger('test'), watcher_factory=lambda *_: contextlib.nullcontext(),
                    signal=signal)
            self.assertIsNone(attempts[0])
            self.assertIsNotNone(attempts[1])

    def test_sinal_stop_preexistente_nao_e_apagado(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            (runtime / 'stop-monitor').touch()
            watcher = Mock()
            result = sync.watch_project(Mock(repo=runtime), runtime, runtime, 'main', 'origin',
                                        .01, logging.getLogger('test'), watcher_factory=watcher)
            self.assertEqual(result, 0)
            self.assertTrue((runtime / 'stop-monitor').exists())
            watcher.assert_not_called()

    def test_evento_novo_nao_espera_backoff_de_rede(self):
        signal = sync.ChangeSignal()
        signal.mark_changed()
        started = time.monotonic()
        self.assertEqual(signal.wait_ready(0, .01, retry_at=started + 300), 1)
        self.assertLess(time.monotonic() - started, 1)

    @unittest.skipUnless(os.name == 'nt', 'Notificacoes nativas requerem Windows')
    def test_watcher_real_criacao_rename_exclusao_e_parada(self):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            signal = sync.ChangeSignal()
            watcher = sync.WindowsDirectoryWatcher(repo, signal)
            with watcher:
                time.sleep(.1)
                source = repo / 'criado.txt'
                source.write_text('salvo')
                self.wait_revision(signal, 0)
                old_revision = signal.revision
                source.rename(repo / 'renomeado.txt')
                self.wait_revision(signal, old_revision)
                old_revision = signal.revision
                (repo / 'renomeado.txt').unlink()
                self.wait_revision(signal, old_revision)
                (repo / '.git' / 'auto-sync').mkdir(parents=True)
                time.sleep(.1)
                old_revision = signal.revision
                (repo / '.git' / 'auto-sync' / 'status.json').write_text('{}')
                time.sleep(.1)
                self.assertEqual(signal.revision, old_revision)
            self.assertFalse(watcher.thread.is_alive())

    def wait_revision(self, signal, previous):
        deadline = time.monotonic() + 3
        while signal.revision <= previous and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertGreater(signal.revision, previous)


if __name__ == '__main__':
    unittest.main()
