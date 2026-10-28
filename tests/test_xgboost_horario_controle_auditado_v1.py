import copy
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, mock
import unittest
import numpy as np
from codigo_fonte import experimento_xgboost_horario_controle_auditado_v1 as a


def relatorios_validos():
    replay = {"old_config": {"seed": 42}, "new_config": {"seed": 42},
              "dados": {k: True for k in ("x_bruto", "y_bruto", "localidade_id", "localidade", "origem_utc", "origem_local")},
              "replay": {"old_cache_max": 2.27e-13, "new_cache_max": 0.0, "old_new_max": 97.88775587081909}}
    piloto = [{"label": l, "new_tree0_exata": True, "old_tree0_exata": False}
              for l in ("m_primeiro", "m_repeticao", "h_sequencial", "m_repeticao2")]
    repeticao = {"schema": 1, "id": "xgboost_hourly_refit_repeticao_v1", "ok": True,
                 "arvores_booster_json_bitexatas": True, "previsoes_bitexatas": True,
                 "max_delta_previsao_wm2": 0.0, "cpu_threads": 1, "dispositivo": "cpu",
                 "random_state": 42, "quantizacao": None, "metricas_usadas_como_criterio": False,
                 "controle_legado_reproduzido": False, "booster_original_sha256": "a" * 64,
                 "booster_repeticao_sha256": "a" * 64}
    return replay, piloto, repeticao


class Relatorios(TestCase):
    def test_relatorios_validos(self):
        a.validar_relatorios(*relatorios_validos())

    def test_repeticao_incompleta_divergente_ou_com_metricas_rejeitada(self):
        mutacoes = {"ok": False, "arvores_booster_json_bitexatas": False, "previsoes_bitexatas": False,
                    "max_delta_previsao_wm2": 1e-9, "cpu_threads": 2, "dispositivo": "cuda",
                    "random_state": 23, "quantizacao": 64, "metricas_usadas_como_criterio": True,
                    "controle_legado_reproduzido": True, "booster_repeticao_sha256": "b" * 64}
        for key, val in mutacoes.items():
            with self.subTest(key=key):
                replay, piloto, repeticao = relatorios_validos()
                repeticao[key] = val
                with self.assertRaises(ValueError): a.validar_relatorios(replay, piloto, repeticao)

    def test_configuracao_e_dados_divergentes_rejeitados(self):
        for key in ("config", "x_bruto", "origem_utc"):
            with self.subTest(key=key):
                replay, piloto, repeticao = relatorios_validos()
                if key == "config": replay["new_config"] = {"seed": 23}
                else: replay["dados"][key] = False
                with self.assertRaises(ValueError): a.validar_relatorios(replay, piloto, repeticao)

    def test_replay_antigo_nao_certificado_e_novo_nao_exato_rejeitados(self):
        for key, val in (("old_cache_max", 1e-3), ("old_cache_max", np.nan),
                         ("new_cache_max", 1e-9), ("old_new_max", 0.0)):
            with self.subTest(key=key, val=val):
                replay, piloto, repeticao = relatorios_validos()
                replay["replay"][key] = val
                with self.assertRaises(ValueError): a.validar_relatorios(replay, piloto, repeticao)

    def test_piloto_faltante_ou_divergente_rejeitado(self):
        replay, piloto, repeticao = relatorios_validos()
        with self.assertRaises(ValueError): a.validar_relatorios(replay, piloto[:-1], repeticao)
        piloto[0]["new_tree0_exata"] = False
        with self.assertRaises(ValueError): a.validar_relatorios(replay, piloto, repeticao)


class Escopo(TestCase):
    def setUp(self):
        self.ctx = SimpleNamespace(tarefa=SimpleNamespace(slug="hourly_72_extension"),
                                   protocolo=a.base.protocolo_padrao("atual"), fase="refit",
                                   config=SimpleNamespace(modo_execucao="completa"))
        self.params = {"dispositivo": "cpu", "dispositivo_original": "cpu",
                       "novo_controle_por_dispositivo": False, "sementes": [42]}

    def test_escopo_valido(self):
        with mock.patch.object(a.base, "parametros", return_value=self.params):
            a.validar_escopo(self.ctx, "XGBoost")

    def test_outros_modelos_tarefas_fases_modos_protocolos_rejeitados(self):
        for categoria in ("modelo", "tarefa", "fase", "modo", "regime", "protocolo"):
            with self.subTest(categoria=categoria):
                ctx = copy.deepcopy(self.ctx); modelo = "XGBoost"
                if categoria == "modelo": modelo = "GRU"
                elif categoria == "tarefa": ctx.tarefa.slug = "daily_30"
                elif categoria == "fase": ctx.fase = "selecao"
                elif categoria == "modo": ctx.config.modo_execucao = "smoke"
                elif categoria == "regime": ctx.protocolo["regime"] = "historico_1998_2022"
                else: ctx.protocolo["inicio_dados"] = "2018-01-01"
                with mock.patch.object(a.base, "parametros", return_value=self.params):
                    with self.assertRaises(ValueError): a.validar_escopo(ctx, modelo)

    def test_dispositivo_ou_semente_alterados_rejeitados(self):
        for key, val in (("dispositivo", "cuda"), ("dispositivo_original", "cuda"),
                         ("novo_controle_por_dispositivo", True), ("sementes", [23])):
            with self.subTest(key=key):
                par = dict(self.params); par[key] = val
                with mock.patch.object(a.base, "parametros", return_value=par):
                    with self.assertRaises(ValueError): a.validar_escopo(self.ctx, "XGBoost")


class Revisao(TestCase):
    def setUp(self):
        self.ev = {"contrato_original_sha256": "c", "selecao_original_sha256": "s",
                   "congelamento_global_sha256": "g"}
        self.rev = {"schema": 1, "id": a.ID, "aprovado": True, "escopo": a.ESCOPO,
                    "metricas_usadas_como_criterio": False, "evidencia_sha256": "digest",
                    "codigo_adaptador_sha256": "digest", **self.ev,
                    "justificativa": "Repeticao integral auditada sem escolher via MAE.",
                    "fontes_sha256": {"fonte": "digest"}}

    def ler(self, ev=None, rev=None, conferir=None):
        with mock.patch.object(a, "preparar_evidencia", return_value=self.ev), \
             mock.patch.object(a.base, "ler_json", side_effect=[ev or self.ev, rev or self.rev]), \
             mock.patch.object(a.base.m, "sha256_arquivo", return_value="digest"), \
             mock.patch.object(a.base, "conferir_hashes", side_effect=conferir):
            return a.ler_evidencia(Path("pasta"))

    def test_revisao_valida(self):
        self.assertEqual(self.ler(), self.ev)

    def test_revisao_fora_do_escopo_ou_desvinculada_rejeitada(self):
        for key, value in (("aprovado", False), ("escopo", {}), ("evidencia_sha256", "alterado"),
                           ("codigo_adaptador_sha256", "alterado"), ("contrato_original_sha256", "alterado"),
                           ("selecao_original_sha256", "alterado"), ("congelamento_global_sha256", "alterado"),
                           ("metricas_usadas_como_criterio", True), ("justificativa", ""),
                           ("fontes_sha256", {})):
            with self.subTest(key=key):
                rev = copy.deepcopy(self.rev); rev[key] = value
                with self.assertRaises(ValueError): self.ler(rev=rev)

    def test_evidencia_divergente_rejeitada(self):
        with self.assertRaises(ValueError): self.ler(ev={"contrato_original_sha256": "alterado"})

    def test_fonte_alterada_rejeitada(self):
        with self.assertRaises(ValueError): self.ler(conferir=ValueError("Fonte alterada"))


class Isolamento(TestCase):
    def test_contexto_restaurado_apos_falha(self):
        original = a.base.conferir_controle
        treinar = a.base.treinar_seed
        executar = a.base.executar_fase
        with self.assertRaises(RuntimeError):
            with a.ativar_adaptador():
                self.assertIs(a.base.conferir_controle, a.conferir_controle)
                self.assertIs(a.base.treinar_seed, treinar)
                self.assertIs(a.base.executar_fase, executar)
                raise RuntimeError("falha")
        self.assertIs(a.base.conferir_controle, original)

    def conferir(self, pred, erro=None):
        esperado = np.arange(4, dtype=np.float64).reshape(2, 2)
        with mock.patch.object(a, "validar_escopo"), \
             mock.patch.object(a, "registrar_contrato_complementar", return_value={"sha256_complemento": "c"}), \
             mock.patch.object(a, "ler_evidencia", return_value={"fonte_referencia": "cache.npz"}), \
             mock.patch.object(a.np, "load") as load, \
             mock.patch.object(a, "CONFERIR_ORIGINAL", side_effect=erro) as original:
            load.return_value.__enter__.return_value = {"previsao": esperado}
            with self.assertRaises(ValueError):
                a.conferir_controle(None, "XGBoost", "teste", [pred], [42], Path("pasta"))
            return original.call_count

    def test_controle_alterado_rejeitado_antes_comparacao(self):
        self.assertEqual(self.conferir(np.arange(4, dtype=np.float64).reshape(2, 2) + 1), 0)

    def test_dtype_alterado_rejeitado_antes_comparacao(self):
        self.assertEqual(self.conferir(np.arange(4, dtype=np.float32).reshape(2, 2)), 0)

    def test_sinal_de_zero_diferente_rejeitado(self):
        arr = np.arange(4, dtype=np.float64).reshape(2, 2)
        arr[0, 0] = -0.0
        self.assertEqual(self.conferir(arr), 0)

    def test_falha_de_grade_nao_aceita_como_controle_novo(self):
        self.assertEqual(self.conferir(np.arange(4, dtype=np.float64).reshape(2, 2), ValueError("Grade diferente")), 1)

    def test_recibo_falso_rejeitado(self):
        complemento = {"sha256_complemento": "c", "contrato_original_sha256": "o",
                       "selecao_original_sha256": "s"}
        with mock.patch.object(a, "construir_contrato_complementar", return_value=complemento), \
             mock.patch.object(a, "ler_evidencia", return_value={"diferenca_legada_maxima_wm2": 97.88775587081909}), \
             mock.patch.object(a.base, "hashes", return_value={"fonte": "digest"}), \
             mock.patch.object(a.base, "ler_json", side_effect=[complemento, {"aprovado": True}]), \
             mock.patch.object(a.base, "conferir_hashes") as check:
            with self.assertRaises(ValueError): a.validar_controle_adaptado(Path("pasta"))
            check.assert_not_called()


if __name__ == "__main__":
    unittest.main()