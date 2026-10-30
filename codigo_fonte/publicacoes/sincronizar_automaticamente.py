"""Salva e envia alteracoes do projeto; pode monitorar salvamentos no Windows.

Usa apenas a biblioteca padrao. Nunca faz pull, rebase, reset ou push forcado.
O indice que o usuario ja preparou e operacoes Git em andamento sao preservados.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone


MAX_FILE_BYTES = 100 * 1024 * 1024


def relevant_change(relative: str) -> bool:
    """Descarta estado do monitor/caches, mas observa commits e operacoes Git."""
    parts = relative.replace("\\", "/").strip("/").casefold().split("/")
    if not parts or not parts[0]:
        return False
    if parts[0] == ".git":
        name = "/".join(parts[1:])
        return (name in {"head", "index", "packed-refs", "config", "index.lock",
                         "merge_head", "cherry_pick_head", "revert_head", "bisect_log",
                         "rebase-merge", "rebase-apply", "sequencer"}
                or name.startswith(("refs/heads/", "rebase-merge/", "rebase-apply/", "sequencer/")))
    if any(part in {".git", ".venv", "venv", "__pycache__", ".pytest_cache",
                    ".mypy_cache", ".ruff_cache", ".tox", ".nox", ".hypothesis",
                    ".matplotlib-cache", ".uv-cache", ".uv-python", ".ipynb_checkpoints",
                    ".notebook_check", "node_modules", "htmlcov", ".idea", ".vscode"}
           or part.startswith(".venv-") for part in parts):
        return False
    path = "/".join(parts)
    # Saidas locais ignoradas pelo .gitignore deste projeto. Um log de treino
    # atualizado continuamente nao deve adiar o envio de um arquivo-fonte.
    if parts[0] in {"tmp", ".tools", ".aws", ".ssh", ".consolidacao", ".overleaf-sync"}:
        return False
    if parts[0].startswith(".codex_"):
        return False
    ignored = ("resultados/logs", "resultados/rascunhos_artigos",
               "documentacao/materiais_de_referencia/artigo_revista_unificado")
    if any(path == prefix or path.startswith(prefix + "/") for prefix in ignored):
        return False
    if path.startswith("resultados/pdf/") and path != "resultados/pdf/readme.md":
        return False
    if len(parts) > 1 and parts[0] == "resultados":
        patterns = ("*smoke*", "validacao_*", "avaliacao_horaria_timesnet_corrigida*",
                    "avaliacao_multirresolucao_corrigida*")
        if any(fnmatch.fnmatchcase(parts[1], pattern) for pattern in patterns):
            return False
        if (len(parts) > 2 and parts[1] == "artigo_revista_unificado"
                and any(fnmatch.fnmatchcase(parts[2], pattern)
                        for pattern in ("*revisao_visual*", "*corrigidos*"))):
            return False
    if path in {"dados/processados/ghi_features.csv", "debug.log",
                "resultados/avaliacao_multirresolucao/daily_30/previsoes_teste.csv.gz",
                "resultados/avaliacao_multirresolucao/daily_30/previsoes_validacao.csv.gz"}:
        return False
    leaf = parts[-1]
    return not any(fnmatch.fnmatchcase(leaf, pattern) for pattern in
        ("*.py[cod]", "*.pyo", "*.aux", "*.bbl", "*.bcf", "*.blg", "*.fdb_latexmk",
         "*.fls", "*.lof", "*.lot", "*.out", "*.run.xml", "*.synctex.gz", "*.toc",
         "*.orig", "*.rej", "*.swp", "*~", "~$*", "~wrl*.tmp", ".ds_store",
         "thumbs.db", "desktop.ini", ".coverage", ".coverage.*", "coverage.xml"))


class ChangeSignal:
    """Contador persistente: eventos durante fetch/commit/push nao se perdem."""

    def __init__(self, clock=time.monotonic):
        self.condition = threading.Condition()
        self.clock = clock
        self.revision = 0
        self.last_change = clock()
        self.error: OSError | None = None
        self.closed = False

    def mark_changed(self):
        with self.condition:
            self.revision += 1
            self.last_change = self.clock()
            self.condition.notify_all()

    def fail(self, error: OSError):
        with self.condition:
            self.error = error
            self.condition.notify_all()

    def wait_ready(self, handled: int, quiet_seconds: float,
                   retry_at: float | None = None, should_stop=None) -> int | None:
        with self.condition:
            while not self.closed:
                if should_stop is not None and should_stop():
                    return None
                if self.error:
                    raise self.error
                now = self.clock()
                due = self.last_change + quiet_seconds if self.revision != handled else None
                if retry_at is not None and due is None:
                    due = retry_at
                if due is not None and due <= now:
                    return self.revision
                timeout = None if due is None else max(0, due - now)
                if should_stop is not None:
                    timeout = min(1, timeout) if timeout is not None else 1
                self.condition.wait(timeout)
            return None

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class WindowsDirectoryWatcher:
    """Notificacoes nativas, sem varrer pastas nem consultar Git em repouso."""

    def __init__(self, repo: Path, signal: ChangeSignal):
        if os.name != "nt":
            raise SyncError("O modo --watch requer Windows.")
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.signal = signal
        self.stopping = threading.Event()
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD,
                                            wintypes.HANDLE]
        self.kernel.CreateFileW.restype = wintypes.HANDLE
        self.kernel.ReadDirectoryChangesW.argtypes = [wintypes.HANDLE, wintypes.LPVOID,
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID, wintypes.LPVOID]
        self.kernel.ReadDirectoryChangesW.restype = wintypes.BOOL
        self.kernel.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
        self.kernel.CancelIoEx.restype = wintypes.BOOL
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.CloseHandle.restype = wintypes.BOOL
        self.handle = self.kernel.CreateFileW(str(repo), 0x0001, 0x00000007,
                                              None, 3, 0x02000000, None)
        if self.handle == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        self.thread = threading.Thread(target=self._read, name="auto-sync-files", daemon=True)

    @staticmethod
    def changed_paths(data: bytes):
        import struct
        offset = 0
        while offset + 12 <= len(data):
            following, _action, length = struct.unpack_from("<III", data, offset)
            end = offset + 12 + length
            if end > len(data):
                raise ValueError("Notificacao de arquivo truncada.")
            yield data[offset + 12:end].decode("utf-16-le")
            if not following:
                return
            offset += following

    def _read(self):
        from ctypes import wintypes
        buffer = self.ctypes.create_string_buffer(65536)
        count = wintypes.DWORD()
        # FILE_NAME | DIR_NAME | SIZE | LAST_WRITE. LastAccess nao interessa.
        flags = 0x00000001 | 0x00000002 | 0x00000008 | 0x00000010
        try:
            while not self.stopping.is_set():
                ok = self.kernel.ReadDirectoryChangesW(self.handle, buffer, len(buffer),
                                                       True, flags, self.ctypes.byref(count),
                                                       None, None)
                if not ok:
                    if self.stopping.is_set():
                        return
                    error = self.ctypes.get_last_error()
                    if error == 1022:  # ERROR_NOTIFY_ENUM_DIR: reconciliar apos overflow.
                        self.signal.mark_changed()
                        continue
                    raise self.ctypes.WinError(error)
                if not count.value:
                    self.signal.mark_changed()  # Overflow: reconciliar com git status.
                    continue
                try:
                    if any(relevant_change(path) for path in self.changed_paths(buffer.raw[:count.value])):
                        self.signal.mark_changed()
                except (ValueError, UnicodeError):
                    self.signal.mark_changed()
        except OSError as exc:
            self.signal.fail(exc)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.stopping.set()
        self.kernel.CancelIoEx(self.handle, None)
        self.thread.join(timeout=5)
        self.kernel.CloseHandle(self.handle)
        self.signal.close()


class SyncError(RuntimeError):
    """Falha cuja mensagem pode ser gravada sem revelar credenciais."""


class Git:
    def __init__(self, repo: Path, executable: str):
        self.repo = repo
        self.executable = executable
        self.env = os.environ.copy()
        self.env.update({"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
        # Nao herdar um indice temporario ou um repositorio de outro comando Git.
        for name in ("GIT_INDEX_FILE", "GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"):
            self.env.pop(name, None)

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        try:
            result = subprocess.run(
                [self.executable, "--no-optional-locks", "-C", str(self.repo), *args],
                env=self.env, capture_output=True, timeout=90, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as exc:
            raise SyncError(f"Tempo limite ao executar git {args[0]}.") from exc
        if check and result.returncode:
            # Nao persistir stderr: hooks, URLs e helpers podem expor segredos.
            raise SyncError(f"Falha em git {args[0]} (codigo {result.returncode}).")
        return result

    def text(self, *args: str) -> str:
        return self.run(*args).stdout.decode("utf-8", errors="replace").strip()

    def changes(self) -> list[tuple[str, str]]:
        raw = self.run("status", "--porcelain=v1", "-z", "--no-renames",
                       "--untracked-files=all").stdout
        return [(os.fsdecode(item[:2]), os.fsdecode(item[3:]))
                for item in raw.split(b"\0") if item]


@contextlib.contextmanager
def exclusive_lock(path: Path):
    """Lock de processo liberado pelo sistema mesmo se o Python for encerrado."""
    stream = path.open("a+b")
    if stream.tell() == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    acquired = False
    try:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError:
            pass
        yield acquired
    finally:
        if acquired:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        stream.close()


def guard(git: Git, git_dir: Path, branch: str, remote: str,
          changes: list[tuple[str, str]]) -> str | None:
    actual = git.text("branch", "--show-current")
    if actual != branch:
        return f"Branch atual diferente de {branch}; sincronizacao suspensa."
    for marker in ("index.lock", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD",
                   "rebase-merge", "rebase-apply", "sequencer", "BISECT_LOG"):
        if (git_dir / marker).exists():
            return "Ha uma operacao Git em andamento; aguarde sua conclusao."
    if any(code[0] not in (" ", "?") for code, _ in changes):
        return "Ha alteracoes staged ou conflitos; conclua o commit manual antes de retomar."
    upstream = git.run("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}",
                       check=False)
    if upstream.returncode or upstream.stdout.decode().strip() != f"{remote}/{branch}":
        return f"A branch deve acompanhar {remote}/{branch}; confira o upstream."
    return None


def inspect_files(repo: Path, changes: list[tuple[str, str]], quiet_seconds: float) -> str | None:
    now = time.time()
    for _, relative in changes:
        path = repo / relative
        if path.is_dir() and path != repo and (path / ".git").exists():
            raise SyncError("Ha repositorio aninhado alterado; sincronize-o separadamente.")
        try:
            info = path.lstat()
        except FileNotFoundError:
            # A exclusao altera a data da pasta; aguarde tambem esse salvamento.
            path = path.parent
            while not path.exists() and path != repo:
                path = path.parent
            info = path.stat()
        if path.is_file() and info.st_size >= MAX_FILE_BYTES:
            raise SyncError("Ha arquivo alterado com 100 MiB ou mais; use Git LFS ou .gitignore.")
        if quiet_seconds > 0 and now - info.st_mtime < quiet_seconds:
            return "Arquivos alterados recentemente; aguardando o proximo ciclo."
    return None


def sync_once(git: Git, git_dir: Path, branch: str, remote: str,
              quiet_seconds: float, check_only: bool = False) -> tuple[str, str]:
    changes = git.changes()
    reason = guard(git, git_dir, branch, remote, changes)
    if reason:
        return "blocked", reason
    reason = inspect_files(git.repo, changes, quiet_seconds)
    if reason:
        return "waiting", reason
    if check_only:
        return "checked", f"Verificacao concluida: {len(changes)} arquivos pendentes; nenhum envio realizado."

    head_before = git.text("rev-parse", "HEAD")
    fetched = git.run("fetch", "--no-tags", remote,
                      f"refs/heads/{branch}:refs/remotes/{remote}/{branch}", check=False)
    remote_ref = f"refs/remotes/{remote}/{branch}"
    # A rede pode levar tempo. Verifique mesmo quando o ciclo comecou limpo.
    current = git.changes()
    reason = guard(git, git_dir, branch, remote, current)
    if reason:
        return "blocked", reason
    if git.text("rev-parse", "HEAD") != head_before:
        return "waiting", "HEAD mudou durante o ciclo; aguardando nova verificacao."
    if fetched.returncode == 0:
        ancestor = git.run("merge-base", "--is-ancestor", remote_ref, head_before, check=False)
        if ancestor.returncode:
            return "blocked", "O remoto tem commits ausentes aqui; integre-os manualmente antes de enviar."
    if current:
        reason = inspect_files(git.repo, current, quiet_seconds)
        if reason:
            return "waiting", reason
        git.run("add", "--all", "--", ".")
        if (git.text("branch", "--show-current") != branch
                or git.text("rev-parse", "HEAD") != head_before):
            raise SyncError("Branch ou HEAD mudou durante git add; revise os arquivos staged antes de retomar.")
        if git.run("diff", "--cached", "--quiet", "--exit-code", check=False).returncode:
            stamp = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
            try:
                git.run("commit", "--quiet", "-m", f"Sincronizacao automatica - {stamp}")
            except SyncError as exc:
                raise SyncError("Commit automatico falhou; arquivos permanecem staged. "
                                "Confira identidade, hooks e conclua o commit manual para retomar.") from exc

    # Enviar um OID fixo impede publicar outra branch se houver checkout em paralelo.
    intended_commit = git.text("rev-parse", f"refs/heads/{branch}")
    reason = guard(git, git_dir, branch, remote, git.changes())
    if reason:
        return "blocked", reason
    if git.text("rev-parse", "HEAD") != intended_commit:
        return "waiting", "HEAD mudou antes do envio; aguardando nova verificacao."
    if fetched.returncode == 0 and intended_commit == git.text("rev-parse", remote_ref):
        return "idle", "Projeto ja esta atualizado no remoto."
    pushed = git.run("push", "--porcelain", remote,
                     f"{intended_commit}:refs/heads/{branch}", check=False)
    if pushed.returncode:
        return "offline", "Envio pendente: falha de rede, autenticacao ou rejeicao; nova tentativa no proximo ciclo."
    return "synced", "Alteracoes salvas em commit e enviadas ao repositorio remoto."


def emit_result(result: dict):
    # pythonw.exe nao tem console e pode expor sys.stdout=None.
    if sys.stdout is not None:
        print(json.dumps(result, ensure_ascii=True), flush=True)


def write_json(path: Path, result: dict):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def record_result(runtime: Path, logger, branch: str, remote: str,
                  state: str, message: str):
    result = {"state": state, "message": message,
              "checked_at": datetime.now(timezone.utc).isoformat(),
              "branch": branch, "remote": remote}
    write_json(runtime / "status.json", result)
    logger.info("%s: %s", state, message)
    emit_result(result)


def pending_locally(git: Git, branch: str, remote: str,
                    changes: list[tuple[str, str]]) -> bool:
    """Somente consultas locais. Ociosidade nao gera fetch/push de minuto em minuto."""
    if changes:
        return True
    local = git.text("rev-parse", f"refs/heads/{branch}")
    upstream = git.run("rev-parse", "--verify", f"refs/remotes/{remote}/{branch}", check=False)
    return bool(upstream.returncode or upstream.stdout.decode().strip() != local)


def watch_project(git: Git, git_dir: Path, runtime: Path, branch: str,
                  remote: str, quiet_seconds: float, logger,
                  watcher_factory=WindowsDirectoryWatcher, signal: ChangeSignal | None = None) -> int:
    with exclusive_lock(runtime / "monitor.lock") as acquired:
        if not acquired:
            return 0
        stop_file = runtime / "stop-monitor"
        monitor = {"pid": os.getpid(), "running": True,
                   "started_at": datetime.now(timezone.utc).isoformat(),
                   "mode": "filesystem-events", "quiet_seconds": quiet_seconds}
        write_json(runtime / "monitor.json", monitor)
        signal = signal if signal is not None else ChangeSignal()
        handled = 0
        retry_at = None
        retry_delay = 30.0
        try:
            if stop_file.exists():
                return 0
            with watcher_factory(git.repo, signal):
                # Reconciliar tambem salvamentos feitos enquanto o computador estava desligado.
                signal.mark_changed()
                logger.info("Monitor iniciado: eventos de arquivos, pausa de %ss.", quiet_seconds)
                while not stop_file.exists():
                    revision = signal.wait_ready(handled, quiet_seconds, retry_at,
                                                 should_stop=stop_file.exists)
                    if revision is None or stop_file.exists():
                        break
                    handled = revision
                    with exclusive_lock(runtime / "sync.lock") as sync_acquired:
                        if not sync_acquired:
                            retry_at = time.monotonic() + max(1, quiet_seconds)
                            continue
                        try:
                            changes = git.changes()
                            reason = guard(git, git_dir, branch, remote, changes)
                            if reason:
                                state, message = "blocked", reason
                            elif pending_locally(git, branch, remote, changes):
                                state, message = sync_once(git, git_dir, branch, remote, quiet_seconds)
                            else:
                                state, message = "idle", "Projeto ja esta atualizado no remoto; aguardando alteracoes."
                        except (SyncError, OSError) as exc:
                            state, message = "error", str(exc)
                        record_result(runtime, logger, branch, remote, state, message)
                    if state == "waiting":
                        retry_at = time.monotonic() + max(1, quiet_seconds)
                    elif state in {"offline", "error"}:
                        retry_at = time.monotonic() + retry_delay
                        retry_delay = min(300, retry_delay * 2)
                    else:
                        retry_at = None
                        retry_delay = 30.0
                    # A revisao capturada antes de sync continua antiga se chegaram
                    # novos salvamentos durante os comandos Git.
            return 0
        except (SyncError, OSError) as exc:
            record_result(runtime, logger, branch, remote, "error", str(exc))
            return 1
        finally:
            monitor["running"] = False
            monitor["stopped_at"] = datetime.now(timezone.utc).isoformat()
            write_json(runtime / "monitor.json", monitor)
            logger.info("Monitor encerrado apos concluir o ciclo em andamento.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--quiet-seconds", type=float, default=15)
    parser.add_argument("--git", default=shutil.which("git"))
    parser.add_argument("--check", action="store_true", help="Verifica sem commit, fetch ou push.")
    parser.add_argument("--watch", action="store_true", help="Monitora salvamentos sem janela (Windows).")
    args = parser.parse_args(argv)
    if not args.git:
        parser.error("Git nao encontrado; informe --git com o caminho do executavel.")
    if args.quiet_seconds < 0:
        parser.error("--quiet-seconds deve ser zero ou positivo.")
    if args.check and args.watch:
        parser.error("Use apenas um modo entre --check e --watch.")
    repo = args.repo.resolve()
    git = Git(repo, args.git)
    try:
        top = Path(git.text("rev-parse", "--show-toplevel")).resolve()
        if top != repo:
            raise SyncError("--repo deve indicar a raiz exata do repositorio.")
        git_dir = Path(git.text("rev-parse", "--absolute-git-dir"))
        common = Path(git.text("rev-parse", "--git-common-dir"))
        if not common.is_absolute():
            common = repo / common
        runtime = common.resolve() / "auto-sync"
        if args.check:
            state, message = sync_once(git, git_dir, args.branch, args.remote,
                                       args.quiet_seconds, check_only=True)
            emit_result({"state": state, "message": message})
            return 1 if state == "blocked" else 0
        runtime.mkdir(parents=True, exist_ok=True)
        if args.watch:
            logger = logging.getLogger("auto-sync")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(runtime / "sync.log", maxBytes=1024 * 1024,
                                          backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            try:
                return watch_project(git, git_dir, runtime, args.branch, args.remote,
                                     args.quiet_seconds, logger)
            finally:
                logger.removeHandler(handler)
                handler.close()
        with exclusive_lock(runtime / "sync.lock") as acquired:
            if not acquired:
                return 0
            logger = logging.getLogger("auto-sync")
            logger.setLevel(logging.INFO)
            handler = RotatingFileHandler(runtime / "sync.log", maxBytes=1024 * 1024,
                                          backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            try:
                try:
                    state, message = sync_once(git, git_dir, args.branch, args.remote,
                                               args.quiet_seconds)
                except (SyncError, OSError) as exc:
                    state = "error"
                    # OSError so traz o caminho local; nunca incluir stdout/stderr Git.
                    message = str(exc)
                record_result(runtime, logger, args.branch, args.remote, state, message)
                return 1 if state in ("error", "blocked", "offline") else 0
            finally:
                logger.removeHandler(handler)
                handler.close()
    except (SyncError, OSError) as exc:
        emit_result({"state": "error", "message": str(exc)})
        return 1


if __name__ == "__main__":
    sys.exit(main())
