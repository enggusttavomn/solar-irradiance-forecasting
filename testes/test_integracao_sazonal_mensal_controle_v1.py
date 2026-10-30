"""Independent dispatcher/replay guards using synthetic arrays and fake modules.

No engine, dataset, checkpoint or training process is imported or executed.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib
import json
from tempfile import TemporaryDirectory
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest import mock

import numpy as np
from numpy.testing import assert_array_equal
import pandas as pd

from codigo_fonte.analises_e_relatorios import auditar_quantizacao_todos_modelos as auditor
from codigo_fonte.experimentos import rodar_quantizacao_todos_modelos as runner
from codigo_fonte.analises_e_relatorios import gerar_pdf_quantizacao_todos_modelos as pdf


CALENDAR = "codigo_fonte.experimentos.experimento_sazonal_mensal_controle_auditado_v1"


class EncaminhamentoCalendario(unittest.TestCase):
    def args(self, regime="historico_1998_2022", smoke=False):
        return SimpleNamespace(regime=regime, smoke=smoke,
                               saida=Path("tmp/teste_calendario_dispatch_fake"), protocolo=None)

    def test_apenas_hist_mensal_sazonal_completo_usam_adapter(self):
        for regime in ("historico_1998_2022", "historico_curto_pareado"):
            for tarefa in ("monthly_1", "monthly_6"):
                for fase in ("selecao", "refit"):
                    with self.subTest(regime=regime, tarefa=tarefa, fase=fase):
                        cmd = runner.comando(self.args(regime), tarefa, "Sazonal ingenuo", fase)
                        self.assertEqual(cmd[cmd.index("-m") + 1], CALENDAR)
                        self.assertEqual(cmd[cmd.index("--fase") + 1], fase)
                        self.assertNotIn("--smoke", cmd)
                        self.assertNotIn("--dispositivo", cmd)

    def test_atual_diario_horario_arima_smoke_preservados(self):
        casos = [
            ("atual", "monthly_1", "Sazonal ingenuo", False),
            ("atual", "monthly_6", "Sazonal ingenuo", False),
            ("historico_1998_2022", "daily_30", "Sazonal ingenuo", False),
            ("historico_1998_2022", "hourly_72_extension", "Sazonal ingenuo", False),
            ("historico_curto_pareado", "daily_30", "Sazonal ingenuo", False),
            ("historico_curto_pareado", "hourly_72_extension", "Sazonal ingenuo", False),
        ]
        for regime in ("historico_1998_2022", "historico_curto_pareado"):
            for tarefa in ("monthly_1", "monthly_6"):
                casos.extend([(regime, tarefa, "ARIMA", False),
                              (regime, tarefa, "Persistencia", False),
                              (regime, tarefa, "Climatologia", False),
                              (regime, tarefa, "Sazonal ingenuo", True)])
        for regime, tarefa, modelo, smoke in casos:
            for fase in ("selecao", "refit"):
                with self.subTest(regime=regime, tarefa=tarefa, modelo=modelo, smoke=smoke, fase=fase):
                    cmd = runner.comando(self.args(regime, smoke), tarefa, modelo, fase)
                    self.assertEqual(cmd[cmd.index("-m") + 1],
                                     "codigo_fonte.experimentos.experimento_quantizacao_estatisticos")
                    self.assertEqual("--smoke" in cmd, smoke)
                    self.assertNotIn(CALENDAR, cmd)

    def test_outros_adapters_e_cuda_preservados(self):
        exemplos = [
            (self.args("atual"), "hourly_72_extension", "XGBoost", "refit",
             "codigo_fonte.experimentos.experimento_xgboost_horario_controle_auditado_v1"),
            (self.args("atual"), "hourly_72_extension", "ARIMA", "refit",
             "codigo_fonte.experimentos.experimento_arima_horario_controle_auditado_v1"),
            (self.args(), "daily_30", "Transformer", "refit",
             "codigo_fonte.experimentos.experimento_atencao_deterministica_v1"),
            (self.args(), "daily_30", "GRU", "refit",
             "codigo_fonte.experimentos.experimento_quantizacao_concorrentes"),
        ]
        for args, tarefa, modelo, fase, modulo in exemplos:
            with self.subTest(modelo=modelo):
                cmd = runner.comando(args, tarefa, modelo, fase)
                self.assertEqual(cmd[cmd.index("-m") + 1], modulo)
                if modelo == "GRU":
                    self.assertEqual(cmd[cmd.index("--dispositivo") + 1], "cuda")


class ReplayCalendario(unittest.TestCase):
    def setUp(self):
        self.pasta = Path("tmp/teste_replay_calendario_fake")
        self.eventos = []
        self.adapter_ativo = False
        self.exige_adapter = True
        self.comp = {"id": "calendario_mensal_fim_mes_v1", "aprovado": True,
                     "fontes_sha256": {"adapter_fake.py": "a" * 64},
                     "sha256_complemento": "b" * 64}
        self.fakepkg = ModuleType("codigo_fonte")
        self.fakepkg.__path__ = []
        self.fakeexperimentos = ModuleType("codigo_fonte.experimentos")
        self.fakeexperimentos.__path__ = []
        self.fakepkg.experimentos = self.fakeexperimentos
        self.e = ModuleType("codigo_fonte.experimentos.experimento_baselines_adicionais")
        self.e.tabela_chaves = mock.Mock(side_effect=lambda ctx, part: self.tabela.copy())
        self.q = ModuleType("codigo_fonte.experimentos.quantizacao_referencias")
        self.q.previsoes_referencias = mock.Mock(side_effect=self.inferir)
        self.cal = ModuleType(CALENDAR)
        self.cal.validar_comp = mock.Mock(side_effect=self.validar_comp)
        self.cal.validar_metadados = mock.Mock(side_effect=self.validar_metadados)
        self.cal.ativar_adaptador = mock.Mock(side_effect=self.ativar_adaptador)
        self.joblib = ModuleType("joblib")
        self.joblib.load = mock.Mock(side_effect=AssertionError("Checkpoint deserialization prohibited"))
        for short, child in (("experimento_baselines_adicionais", self.e),
                             ("quantizacao_referencias", self.q),
                             ("experimento_sazonal_mensal_controle_auditado_v1", self.cal)):
            setattr(self.fakeexperimentos, short, child)
        modules = {"codigo_fonte": self.fakepkg,
                   "codigo_fonte.experimentos": self.fakeexperimentos,
                   "joblib": self.joblib,
                   self.e.__name__: self.e, self.q.__name__: self.q, self.cal.__name__: self.cal}
        patch = mock.patch.dict(sys.modules, modules)
        patch.start()
        self.addCleanup(patch.stop)
        patch = mock.patch("subprocess.Popen", side_effect=AssertionError("Process launch prohibited"))
        patch.start()
        self.addCleanup(patch.stop)
        self.preparar()

    def preparar(self, regime="historico_1998_2022", tarefa="monthly_6",
                 modelo="Sazonal ingenuo", fase="refit"):
        self.eventos.clear()
        self.modelo = modelo
        self.fase = fase
        self.part = "validacao" if fase == "selecao" else "teste"
        n = 1 if tarefa == "monthly_1" else 6
        y = np.arange(20.0, 20.0 + n).reshape(1, n)
        self.bruto = np.arange(2.0, 2.0 + n).reshape(1, n)
        janela = SimpleNamespace(x_bruto=np.zeros((1, 12)), y_bruto=y)
        self.ctx = SimpleNamespace(tarefa=SimpleNamespace(slug=tarefa, resolucao="mensal"),
                                   protocolo={"regime": regime},
                                   janelas={self.part: janela}, series=())
        if tarefa == "daily_30":
            self.ctx.tarefa.resolucao = "diaria"
        elif tarefa == "hourly_72_extension":
            self.ctx.tarefa.resolucao = "horaria"
        self.contrato = {"modelo": modelo, "tarefa": {"slug": tarefa},
                         "protocolo": self.ctx.protocolo, "sha256_contrato": "c" * 64}
        self.tabela = pd.DataFrame({"localidade": ["Local sintetic"] * n,
                                   "origem": ["2021-01-31"] * n,
                                   "data_alvo": pd.date_range("2021-01-31", periods=n, freq="ME"),
                                   "passo": range(1, n + 1), "ghi_real_wm2": y.reshape(-1)})
        self.salva = self.tabela.copy()
        self.salva[f"{modelo}_bruta_wm2"] = self.bruto.reshape(-1)
        self.exige_adapter = (modelo == "Sazonal ingenuo"
                              and self.ctx.tarefa.resolucao == "mensal"
                              and regime in ("historico_1998_2022", "historico_curto_pareado"))
        for mocked in (self.q.previsoes_referencias, self.cal.validar_comp,
                       self.cal.validar_metadados, self.cal.ativar_adaptador, self.joblib.load):
            mocked.reset_mock()

    def validar_comp(self, pasta, *, contrato):
        self.eventos.append("comp")
        self.assertEqual(pasta, self.pasta)
        self.assertIs(contrato, self.contrato)
        return self.comp

    def validar_metadados(self, pasta, fase, *, contrato):
        # Signature intentionally rejects exigir_todos=False: production must be strict.
        self.eventos.append("metadados")
        self.assertEqual(fase, self.fase)
        return self.cal.validar_comp(pasta, contrato=contrato)

    @contextmanager
    def ativar_adaptador(self, ctx, *, modelo, pasta, contrato):
        self.assertFalse(self.adapter_ativo)
        self.assertEqual(modelo, "Sazonal ingenuo")
        self.assertEqual(pasta, self.pasta)
        self.assertIs(contrato, self.contrato)
        self.assertTrue(np.isnan(ctx.janelas[self.part].y_bruto).all())
        self.eventos.append("enter")
        self.adapter_ativo = True
        try:
            yield
        finally:
            self.adapter_ativo = False
            self.eventos.append("exit")

    def inferir(self, ctx, part, niveis, *, fase, modelos):
        self.assertEqual(self.adapter_ativo, self.exige_adapter)
        self.assertTrue(np.isnan(ctx.janelas[part].y_bruto).all())
        self.assertIsNot(ctx, self.ctx)
        self.assertIsNot(ctx.janelas[part], self.ctx.janelas[part])
        self.assertTrue(np.isfinite(self.ctx.janelas[part].y_bruto).all())
        self.assertEqual((part, fase, modelos), (self.part, self.fase, [self.modelo]))
        self.assertEqual(niveis, self.niveis_esperados)
        self.eventos.append("infer")
        return {self.modelo: self.bruto.copy()}

    def executar(self, variante="q128"):
        self.niveis_esperados = {"sem_quantizacao": None, "q64": 64, "q128": 128, "q256": 256}[variante]
        def ler(path):
            self.assertEqual(path, self.pasta / "contrato_execucao.json")
            return self.contrato
        with mock.patch.object(auditor, "ler", side_effect=ler), \
             mock.patch.object(auditor.pd, "read_csv", return_value=self.salva.copy()) as read_csv:
            try:
                return auditor.replay_estatistico(self.ctx, self.pasta, self.modelo, variante, self.fase)
            finally:
                self.read_csv_calls = read_csv.call_count

    def test_metadados_comp_antes_q_adapter_nan_e_provenance(self):
        for regime in ("historico_1998_2022", "historico_curto_pareado"):
            for tarefa in ("monthly_1", "monthly_6"):
                for fase in ("selecao", "refit"):
                    for variante in ("sem_quantizacao", "q64", "q128", "q256"):
                        with self.subTest(regime=regime, tarefa=tarefa, fase=fase, variante=variante):
                            self.preparar(regime, tarefa, fase=fase)
                            original_y = self.ctx.janelas[self.part].y_bruto.copy()
                            resultado = self.executar(variante)
                            self.assertEqual(self.eventos, ["metadados", "comp", "enter", "infer", "exit"])
                            self.cal.validar_metadados.assert_called_once_with(self.pasta, fase, contrato=self.contrato)
                            self.assertEqual(resultado[0]["adaptacao_calendario"], self.comp)
                            self.assertEqual(resultado[0]["adaptacao_calendario"]["fontes_sha256"], self.comp["fontes_sha256"])
                            self.assertTrue(resultado[0]["alvos_substituidos_por_nan"])
                            self.assertTrue(resultado[0]["referencia_recalculada"])
                            self.assertEqual(resultado[0]["diferenca_maxima"], 0.0)
                            assert_array_equal(self.ctx.janelas[self.part].y_bruto, original_y)
                            self.assertFalse(self.adapter_ativo)
                            self.joblib.load.assert_not_called()

    def test_metadados_hash_invalido_bloqueiam_antes_inferencia(self):
        self.cal.validar_metadados.side_effect = ValueError("Metadata source hash mismatch")
        with self.assertRaisesRegex(ValueError, "Metadata source hash mismatch"):
            self.executar()
        self.q.previsoes_referencias.assert_not_called()
        self.cal.ativar_adaptador.assert_not_called()
        self.cal.validar_comp.assert_not_called()
        self.assertEqual(self.read_csv_calls, 0)
        self.assertFalse(self.adapter_ativo)

    def test_complemento_invalido_propaga_sem_fallback(self):
        self.cal.validar_comp.side_effect = ValueError("Complement invalid")
        with self.assertRaisesRegex(ValueError, "Complement invalid"):
            self.executar()
        self.assertEqual(self.eventos, ["metadados"])
        self.q.previsoes_referencias.assert_not_called()
        self.cal.ativar_adaptador.assert_not_called()
        self.assertEqual(self.read_csv_calls, 0)

    def test_contexto_rejeitado_nao_chama_q(self):
        self.cal.ativar_adaptador.side_effect = ValueError("Context rejected")
        with self.assertRaisesRegex(ValueError, "Context rejected"):
            self.executar()
        self.q.previsoes_referencias.assert_not_called()
        self.assertEqual(self.read_csv_calls, 0)
        self.assertFalse(self.adapter_ativo)

    def test_inferencia_erro_restaura_contexto_sem_fallback(self):
        def falhar(*args, **kwargs):
            self.assertTrue(self.adapter_ativo)
            self.eventos.append("infer")
            raise ValueError("Inference failed")
        self.q.previsoes_referencias.side_effect = falhar
        with self.assertRaisesRegex(ValueError, "Inference failed"):
            self.executar()
        self.assertEqual(self.eventos, ["metadados", "comp", "enter", "infer", "exit"])
        self.assertEqual(self.q.previsoes_referencias.call_count, 1)
        self.assertFalse(self.adapter_ativo)
        self.assertEqual(self.read_csv_calls, 0)

    def test_previsao_divergente_ainda_bloqueia_auditoria(self):
        self.salva[f"{self.modelo}_bruta_wm2"] += 1.0
        with self.assertRaisesRegex(AssertionError, "Replay estatistico divergente"):
            self.executar()
        self.assertFalse(self.adapter_ativo)
        self.assertEqual(self.q.previsoes_referencias.call_count, 1)

    def test_fora_escopo_nao_ativa_adapter_nem_inclui_provenance(self):
        casos = [("atual", "monthly_6", "Sazonal ingenuo"),
                 ("historico_1998_2022", "daily_30", "Sazonal ingenuo"),
                 ("historico_1998_2022", "hourly_72_extension", "Sazonal ingenuo"),
                 ("historico_1998_2022", "monthly_6", "Persistencia"),
                 ("historico_curto_pareado", "monthly_1", "Climatologia")]
        for regime, tarefa, modelo in casos:
            with self.subTest(regime=regime, tarefa=tarefa, modelo=modelo):
                self.preparar(regime, tarefa, modelo)
                resultado = self.executar()
                self.assertEqual(self.eventos, ["infer"])
                self.cal.validar_metadados.assert_not_called()
                self.cal.validar_comp.assert_not_called()
                self.cal.ativar_adaptador.assert_not_called()
                self.assertNotIn("adaptacao_calendario", resultado[0])
                self.assertTrue(resultado[0]["alvos_substituidos_por_nan"])
                self.joblib.load.assert_not_called()



class FontesCalendarioSuplementar(unittest.TestCase):
    def setUp(self):
        tmp_parent = Path(__file__).resolve().parents[1] / "tmp"
        tmp_parent.mkdir(exist_ok=True)
        self.temp = TemporaryDirectory(dir=tmp_parent)
        self.addCleanup(self.temp.cleanup)
        self.raiz = Path(self.temp.name)
        self.pasta = self.raiz / "historico_1998_2022" / "monthly_6" / "sazonal_ingenuo"
        self.pasta.mkdir(parents=True)
        self.baseline = self.gravar_bytes("baseline_original.py", b"original frozen source")
        self.fonte_adapter = self.gravar_bytes("adapter_fake.py", b"reviewed scoped adapter")
        self.contrato = {"codigo": {str(self.baseline): self.sha(self.baseline)}}
        self.provenance = {"tipo": "contrato_nativo", "id": "calendario_mensal_fim_mes_v1"}
        self.cal = ModuleType(CALENDAR)
        self.cal.__file__ = str(self.fonte_adapter)
        self.cal.validar_metadados = mock.Mock(side_effect=lambda *args, **kw: self.provenance)
        pkg = ModuleType("codigo_fonte")
        pkg.__path__ = []
        experimentos = ModuleType("codigo_fonte.experimentos")
        experimentos.__path__ = []
        experimentos.experimento_sazonal_mensal_controle_auditado_v1 = self.cal
        pkg.experimentos = experimentos
        patch = mock.patch.dict(sys.modules, {
            "codigo_fonte": pkg, "codigo_fonte.experimentos": experimentos,
            CALENDAR: self.cal,
        })
        patch.start()
        self.addCleanup(patch.stop)
        self.esperadas = {str(self.baseline), str(self.fonte_adapter)}
        for variante in ("sem_quantizacao", "q64", "q128", "q256"):
            for fase in ("selecao", "refit"):
                directory = self.pasta / variante / fase
                directory.mkdir(parents=True)
                cache = directory / "seed-1.npz"
                cp = directory / "referencia.joblib"
                cache.write_bytes(b"opaque synthetic bytes; never load this as an NPZ")
                cp.write_bytes(b"opaque synthetic bytes; never deserialize")
                meta = directory / "seed-1.json"
                meta.write_text(json.dumps({"arquivos_sha256": {
                    str(cache): self.sha(cache), str(cp): self.sha(cp)}}), encoding="utf-8")
                self.esperadas.update((str(meta), str(cache), str(cp)))

    @staticmethod
    def sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def gravar_bytes(self, nome, conteudo):
        path = self.raiz / nome
        path.write_bytes(conteudo)
        return path

    def gravar_json(self, path, conteudo):
        path.write_text(json.dumps(conteudo), encoding="utf-8")
        return path

    def auditar(self, **overrides):
        args = dict(pasta=self.pasta, regime="historico_1998_2022", tarefa="monthly_6",
                    modelo="Sazonal ingenuo", modo="completa", contrato=self.contrato)
        args.update(overrides)
        return auditor.auditar_calendario_suplementar(**args)

    def gate_pdf_deve_bloquear(self, suplemento, fonte):
        # The actual PDF loader checks supplemental hashes before reading metrics.
        path = self.raiz / "auditoria_sintetica.json"
        self.gravar_json(path, {"ok": True, "modo": "completa", "publicavel": True,
            "escopo_completo": True, "replay_novo_executado": True, "pares_verificados": 44,
            "regime": "historico_1998_2022", "fontes_controles_suplementares_sha256": suplemento["fontes_sha256"],
            "metricas": {"path": str(self.raiz / "never-read-metrics.csv"), "sha256": "0" * 64}})
        fonte.write_bytes(fonte.read_bytes() + b"adulterated after audit")
        with self.assertRaisesRegex(ValueError, "Fonte do controle complementar alterada"):
            pdf.carregar_auditoria(path)

    def test_native_fontes_completas_e_pdf_bloqueia_adapter_adulterado(self):
        suplemento = self.auditar()
        self.assertEqual(set(suplemento["fontes_sha256"]), self.esperadas)
        self.cal.validar_metadados.assert_has_calls([
            mock.call(self.pasta, "selecao", contrato=self.contrato),
            mock.call(self.pasta, "refit", contrato=self.contrato)])
        self.assertEqual(self.cal.validar_metadados.call_count, 2)
        self.assertEqual(suplemento["tipo"], "contrato_nativo")
        self.gate_pdf_deve_bloquear(suplemento, self.fonte_adapter)

    def test_legacy_fontes_transitivas_completas_e_pdf_bloqueia_evidencia(self):
        self.provenance = {"tipo": "complemento_legado", "id": "calendario_mensal_fim_mes_v1"}
        origem_ev = self.gravar_bytes("paridade_validacao_original.bin", b"eight exact validation checks")
        origem_rev = self.gravar_bytes("revisao_independente.bin", b"approved bound review")
        evidencia = self.gravar_json(self.raiz / "evidencia.json", {
            "fontes_sha256": {str(origem_ev): self.sha(origem_ev)}})
        revisao = self.gravar_json(self.raiz / "revisao.json", {
            "fontes_sha256": {str(origem_rev): self.sha(origem_rev)}})
        comp = self.gravar_json(self.pasta / "contrato_complementar_sazonal_mensal_v1.json", {
            "evidencia": str(evidencia), "revisao": str(revisao),
            "fontes_sha256": {str(evidencia): self.sha(evidencia), str(revisao): self.sha(revisao)}})
        self.esperadas.update(map(str, (origem_ev, origem_rev, evidencia, revisao, comp)))
        suplemento = self.auditar()
        self.assertEqual(set(suplemento["fontes_sha256"]), self.esperadas)
        self.assertEqual(suplemento["tipo"], "complemento_legado")
        self.gate_pdf_deve_bloquear(suplemento, origem_ev)

    def test_escopo_e_metadata_invalidos_nao_ignoram_suplemento(self):
        comp = self.pasta / "contrato_complementar_sazonal_mensal_v1.json"
        for kw in ({"regime": "atual"}, {"tarefa": "daily_30"}, {"modelo": "ARIMA"}, {"modo": "smoke"}):
            with self.subTest(overrides=kw):
                self.assertIsNone(self.auditar(**kw))
                self.gravar_json(comp, {"wrong_scope": True})
                with self.assertRaisesRegex(AssertionError, "fora do escopo"):
                    self.auditar(**kw)
                comp.unlink()
        self.cal.validar_metadados.assert_not_called()
        self.cal.validar_metadados.side_effect = ValueError("Production metadata provenance absent")
        with self.assertRaisesRegex(ValueError, "Production metadata provenance absent"):
            self.auditar()
        self.assertEqual(self.cal.validar_metadados.call_count, 1)


if __name__ == "__main__":
    unittest.main()
