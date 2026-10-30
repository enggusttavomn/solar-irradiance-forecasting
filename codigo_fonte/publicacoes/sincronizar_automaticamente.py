"""Salva e envia alteracoes do projeto; chamado periodicamente pelo Windows.

Usa apenas a biblioteca padrao. Nunca faz pull, rebase, reset ou push forcado.
O indice que o usuario ja preparou e operacoes Git em andamento sao preservados.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone


MAX_FILE_BYTES = 100 * 1024 * 1024


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--branch", default="main")
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--quiet-seconds", type=float, default=15)
    parser.add_argument("--git", default=shutil.which("git"))
    parser.add_argument("--check", action="store_true", help="Verifica sem commit, fetch ou push.")
    args = parser.parse_args(argv)
    if not args.git:
        parser.error("Git nao encontrado; informe --git com o caminho do executavel.")
    if args.quiet_seconds < 0:
        parser.error("--quiet-seconds deve ser zero ou positivo.")
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
            print(json.dumps({"state": state, "message": message}, ensure_ascii=True))
            return 1 if state == "blocked" else 0
        runtime.mkdir(parents=True, exist_ok=True)
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
                result = {"state": state, "message": message,
                          "checked_at": datetime.now(timezone.utc).isoformat(),
                          "branch": args.branch, "remote": args.remote}
                temporary = runtime / "status.json.tmp"
                temporary.write_text(json.dumps(result, ensure_ascii=True, indent=2) + "\n",
                                     encoding="utf-8")
                os.replace(temporary, runtime / "status.json")
                logger.info("%s: %s", state, message)
                print(json.dumps(result, ensure_ascii=True))
                return 1 if state in ("error", "blocked", "offline") else 0
            finally:
                logger.removeHandler(handler)
                handler.close()
    except (SyncError, OSError) as exc:
        print(json.dumps({"state": "error", "message": str(exc)}, ensure_ascii=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
