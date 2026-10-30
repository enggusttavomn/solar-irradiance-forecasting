"""Integracao com remotos Git locais: nunca envia ao repositorio do projeto."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from codigo_fonte.publicacoes import sincronizar_automaticamente as sincronizador


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "codigo_fonte" / "publicacoes" / "sincronizar_automaticamente.py"
GIT = shutil.which("git")


@unittest.skipUnless(GIT, "Git necessario para os testes de integracao")
class SincronizacaoAutomaticaTests(unittest.TestCase):
    def setUp(self):
        # Temp dentro do workspace para funcionar tambem no sandbox Windows.
        (ROOT / "tmp").mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="test-auto-sync-", dir=ROOT / "tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.origin = self.root / "origin.git"
        self.repo = self.root / "trabalho"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.origin))
        self.git(self.root, "clone", str(self.origin), str(self.repo))
        self.git(self.repo, "config", "user.name", "Teste")
        self.git(self.repo, "config", "user.email", "teste@example.invalid")
        self.git(self.repo, "config", "commit.gpgsign", "false")
        self.write("README.md", "inicio\n")
        self.git(self.repo, "add", ".")
        self.git(self.repo, "commit", "-m", "Inicial")
        self.git(self.repo, "push", "-u", "origin", "main")

    def git(self, cwd, *args):
        result = subprocess.run([GIT, "-C", str(cwd), *args], capture_output=True,
                                encoding="utf-8", errors="replace", check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def write(self, name, contents):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
        return path

    def run_sync(self, *extra):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), "--git", GIT,
             "--quiet-seconds", "0", *extra], capture_output=True, text=True, check=False,
        )
        self.assertTrue(result.stdout.strip(), result.stderr)
        return json.loads(result.stdout), result.returncode

    def remote_head(self):
        return self.git(self.origin, "rev-parse", "main")

    def test_envia_modificados_novos_excluidos_e_respeita_gitignore(self):
        self.write(".gitignore", "segredo.env\n")
        self.write("segredo.env", "ignorado\n")
        self.write("novo.txt", "novo\n")
        (self.repo / "README.md").unlink()
        state, code = self.run_sync()
        self.assertEqual((state["state"], code), ("synced", 0))
        self.assertEqual(self.remote_head(), self.git(self.repo, "rev-parse", "HEAD"))
        tree = self.git(self.origin, "ls-tree", "--name-only", "-r", "main")
        self.assertIn("novo.txt", tree)
        self.assertNotIn("README.md", tree)
        self.assertNotIn("segredo.env", tree)
        self.assertEqual(self.git(self.repo, "status", "--porcelain"), "")
        before = self.remote_head()
        self.assertEqual(self.run_sync()[0]["state"], "idle")
        self.assertEqual(before, self.remote_head())

    def test_staged_preservado_sem_commit_automatico(self):
        before = self.remote_head()
        self.write("README.md", "versao staged\n")
        self.git(self.repo, "add", "README.md")
        self.write("README.md", "outra versao nao staged\n")
        index_before = self.git(self.repo, "diff", "--cached")
        state, code = self.run_sync()
        self.assertEqual((state["state"], code), ("blocked", 1))
        self.assertEqual(index_before, self.git(self.repo, "diff", "--cached"))
        self.assertEqual(before, self.remote_head())

    def test_check_nao_modifica_git_nem_cria_estado(self):
        before = self.remote_head()
        self.write("novo.txt", "pendente\n")
        state, code = self.run_sync("--check")
        self.assertEqual((state["state"], code), ("checked", 0))
        self.assertEqual(before, self.git(self.repo, "rev-parse", "HEAD"))
        self.assertFalse((self.repo / ".git" / "auto-sync").exists())

    def test_branch_incorreta_e_operacao_git_bloqueiam(self):
        self.git(self.repo, "checkout", "-b", "experimento")
        self.write("novo.txt", "pendente\n")
        self.assertEqual(self.run_sync()[0]["state"], "blocked")
        self.git(self.repo, "checkout", "main")
        (self.repo / ".git" / "MERGE_HEAD").write_text("0" * 40 + "\n")
        self.assertEqual(self.run_sync()[0]["state"], "blocked")

    def test_remoto_divergente_preserva_arquivos_e_historico(self):
        other = self.root / "outro"
        self.git(self.root, "clone", str(self.origin), str(other))
        self.git(other, "config", "user.name", "Outro")
        self.git(other, "config", "user.email", "outro@example.invalid")
        self.git(other, "config", "commit.gpgsign", "false")
        (other / "remoto.txt").write_text("no outro PC\n")
        self.git(other, "add", ".")
        self.git(other, "commit", "-m", "Outro computador")
        self.git(other, "push")
        remote_before = self.remote_head()
        local_before = self.git(self.repo, "rev-parse", "HEAD")
        self.write("local.txt", "neste computador\n")
        state, code = self.run_sync()
        self.assertEqual((state["state"], code), ("blocked", 1))
        self.assertEqual(remote_before, self.remote_head())
        self.assertEqual(local_before, self.git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual((self.repo / "local.txt").read_text(), "neste computador\n")

    def test_sem_rede_salva_commit_e_envia_na_tentativa_seguinte(self):
        before = self.remote_head()
        missing = self.root / "sem-rede.git"
        self.git(self.repo, "remote", "set-url", "origin", str(missing))
        self.write("offline.txt", "salvo sem rede\n")
        state, code = self.run_sync()
        self.assertEqual((state["state"], code), ("offline", 1))
        local = self.git(self.repo, "rev-parse", "HEAD")
        self.assertNotEqual(before, local)
        self.assertEqual(before, self.remote_head())
        self.git(self.repo, "remote", "set-url", "origin", str(self.origin))
        self.assertEqual(self.run_sync()[0]["state"], "synced")
        self.assertEqual(local, self.remote_head())

    def test_arquivo_grande_nao_e_adicionado_ao_indice(self):
        with (self.repo / "enorme.bin").open("wb") as stream:
            stream.truncate(100 * 1024 * 1024)
        state, code = self.run_sync()
        self.assertEqual((state["state"], code), ("error", 1))
        self.assertIn("100 MiB", state["message"])
        self.assertEqual(self.git(self.repo, "diff", "--cached"), "")

    def test_aguarda_arquivo_recem_salvo(self):
        self.write("novo.txt", "ainda sendo editado\n")
        state, code = self.run_sync("--quiet-seconds", "60")
        self.assertEqual((state["state"], code), ("waiting", 0))

    def test_checkout_durante_fetch_nao_publica_outra_branch(self):
        before = self.remote_head()
        worker = sincronizador.Git(self.repo, GIT)
        original_run = worker.run

        def switch_after_fetch(*args, **kwargs):
            result = original_run(*args, **kwargs)
            if args[0] == "fetch":
                self.git(self.repo, "checkout", "-b", "outra-branch")
                self.write("outro-trabalho.txt", "nao publicar em main\n")
                self.git(self.repo, "add", ".")
                self.git(self.repo, "commit", "-m", "Trabalho em outra branch")
            return result

        worker.run = switch_after_fetch
        state, _ = sincronizador.sync_once(worker, self.repo / ".git", "main", "origin", 0)
        self.assertEqual(state, "blocked")
        self.assertEqual(before, self.remote_head())
        self.assertEqual(self.git(self.repo, "branch", "--show-current"), "outra-branch")


if __name__ == "__main__":
    unittest.main()
