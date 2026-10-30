"""Historical command planning against small synthetic frozen manifests.

No engine import, fit, replay, checkpoint loading or process launch is used.
The fixtures exercise the real orchestration freeze validator and file hashes.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest import mock

from codigo_fonte.acompanhamento import coordenar_quantizacao_historica as coordenador
from codigo_fonte.experimentos import rodar_quantizacao_todos_modelos as runner


class ComandoHistoricoSomenteRefit(unittest.TestCase):
    def setUp(self):
        tmp_parent = Path(__file__).resolve().parents[1] / "tmp"
        tmp_parent.mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=tmp_parent)
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.saida = self.raiz / "resultados"
        self.rel = self.raiz / "resultados/relatorios"
        self.protocolo = self.raiz / "protocolo.json"
        self.protocolo.write_text("{}\n", encoding="utf-8")
        self.args = SimpleNamespace(cpu_workers=3, gpu_workers=2)
        self.pares = [(t, m) for t in runner.TAREFAS for m in runner.MODELOS]
        for nome, valor in (("SAIDA", self.saida), ("REL", self.rel)):
            patch = mock.patch.object(coordenador, nome, valor)
            patch.start()
            self.addCleanup(patch.stop)
        # A command planner must never start children, even on a bad freeze.
        patch = mock.patch("subprocess.Popen", side_effect=AssertionError("Unexpected process launch"))
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch.object(
            coordenador, "ExecutadorCoordenacao",
            side_effect=AssertionError("Unexpected coordinator execution"),
        )
        patch.start()
        self.addCleanup(patch.stop)

    def congelamento(self, regime="historico_1998_2022"):
        for tarefa, modelo in self.pares:
            pasta = self.saida / regime / tarefa / runner.slug(modelo)
            pasta.mkdir(parents=True)
            (pasta / "contrato_execucao.json").write_text(
                json.dumps({"modo": "completa", "modelo": modelo, "tarefa": tarefa}) + "\n",
                encoding="utf-8",
            )
            (pasta / "selecao_congelada.json").write_text(
                json.dumps({"selecao_concluida_antes_refit": True, "modelo": modelo}) + "\n",
                encoding="utf-8",
            )
        args = SimpleNamespace(regime=regime, saida=self.saida, smoke=False)
        path = Path(runner.congelar(args, self.pares))
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["pares"]), 44)
        self.assertEqual(len(data["fontes_sha256"]), 88)
        return path

    def comando(self, regime="historico_1998_2022"):
        return coordenador.comando_fila_historica(self.args, regime, self.protocolo)

    def assert_base(self, cmd, regime):
        self.assertEqual(cmd[:5], [sys.executable, "-X", "utf8", "-m",
                                  "codigo_fonte.experimentos.rodar_quantizacao_todos_modelos"])
        for flag, expected in (
            ("--regime", regime), ("--saida", str(self.saida)),
            ("--relatorios", str(self.rel / "fila_historica")),
            ("--protocolo", str(self.protocolo.resolve())),
            ("--cpu-workers", "3"), ("--gpu-workers", "2"),
        ):
            self.assertEqual(cmd.count(flag), 1)
            self.assertEqual(cmd[cmd.index(flag) + 1], expected)
        self.assertNotIn("--smoke", cmd)
        self.assertNotIn("--somente-selecao", cmd)

    def test_global_valido_44_pares_habilita_refit_sem_reescrever(self):
        global_path = self.congelamento()
        before = global_path.read_bytes()
        stat_before = global_path.stat().st_mtime_ns
        cmd = self.comando()
        self.assert_base(cmd, "historico_1998_2022")
        self.assertEqual(cmd.count("--somente-refit"), 1)
        self.assertEqual(global_path.read_bytes(), before)
        self.assertEqual(global_path.stat().st_mtime_ns, stat_before)

    def test_curto_sem_global_mantem_selecao_e_refit_originais(self):
        regime = "historico_curto_pareado"
        global_path = self.saida / regime / "selecao_global_congelada.json"
        self.assertFalse(global_path.exists())
        cmd = self.comando(regime)
        self.assert_base(cmd, regime)
        self.assertNotIn("--somente-refit", cmd)
        self.assertFalse(global_path.exists())

    def test_curto_com_global_valido_tambem_retoma_somente_refit(self):
        regime = "historico_curto_pareado"
        global_path = self.congelamento(regime)
        before = global_path.read_bytes()
        cmd = self.comando(regime)
        self.assert_base(cmd, regime)
        self.assertEqual(cmd.count("--somente-refit"), 1)
        self.assertEqual(global_path.read_bytes(), before)

    def test_global_corrupto_propaga_erro_sem_fallback_ou_reescrita(self):
        global_path = self.congelamento()
        global_path.write_bytes(b"{invalid-json\n")
        before = global_path.read_bytes()
        with self.assertRaises(json.JSONDecodeError):
            self.comando()
        self.assertEqual(global_path.read_bytes(), before)

    def test_global_nao_objeto_json_bloqueia_sem_reescrever(self):
        global_path = self.congelamento()
        for value in ([], None, False, 0):
            with self.subTest(value=value):
                global_path.write_text(json.dumps(value), encoding="utf-8")
                before = global_path.read_bytes()
                with self.assertRaises(ValueError):
                    self.comando()
                self.assertEqual(global_path.read_bytes(), before)
    def test_regime_modo_pares_e_sha_divergentes_bloqueiam(self):
        global_path = self.congelamento()
        original = json.loads(global_path.read_text(encoding="utf-8"))
        cases = ("regime", "modo", "pares_ausentes", "pares_duplicados",
                 "sha_divergente", "fonte_ausente", "fonte_extra")
        for case in cases:
            with self.subTest(case=case):
                data = json.loads(json.dumps(original))
                if case == "regime":
                    data["regime"] = "historico_curto_pareado"
                elif case == "modo":
                    data["modo"] = "smoke"
                elif case == "pares_ausentes":
                    data["pares"].pop()
                elif case == "pares_duplicados":
                    data["pares"][-1] = data["pares"][0]
                elif case == "sha_divergente":
                    first = next(iter(data["fontes_sha256"]))
                    data["fontes_sha256"][first] = "0" * 64
                elif case == "fonte_ausente":
                    data["fontes_sha256"].pop(next(iter(data["fontes_sha256"])))
                else:
                    data["fontes_sha256"][str(self.raiz / "extra.json")] = "0" * 64
                global_path.write_text(json.dumps(data), encoding="utf-8")
                before = global_path.read_bytes()
                with self.assertRaises(ValueError):
                    self.comando()
                self.assertEqual(global_path.read_bytes(), before)

    def test_fonte_congelada_alterada_bloqueia_sem_recongelar(self):
        global_path = self.congelamento()
        before = global_path.read_bytes()
        tarefa, modelo = self.pares[0]
        source = self.saida / "historico_1998_2022" / tarefa / runner.slug(modelo) / "contrato_execucao.json"
        source.write_text('{"modo":"completa","alterado":true}\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.comando()
        self.assertEqual(global_path.read_bytes(), before)

    def test_selecao_nao_congelada_bloqueia(self):
        global_path = self.congelamento()
        before = global_path.read_bytes()
        tarefa, modelo = self.pares[0]
        source = self.saida / "historico_1998_2022" / tarefa / runner.slug(modelo) / "selecao_congelada.json"
        source.write_text('{"selecao_concluida_antes_refit":false}\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.comando()
        self.assertEqual(global_path.read_bytes(), before)

    def test_fonte_obrigatoria_ausente_bloqueia(self):
        global_path = self.congelamento()
        before = global_path.read_bytes()
        tarefa, modelo = self.pares[-1]
        source = self.saida / "historico_1998_2022" / tarefa / runner.slug(modelo) / "selecao_congelada.json"
        source.unlink()
        with self.assertRaises(FileNotFoundError):
            self.comando()
        self.assertEqual(global_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()