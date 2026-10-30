"""Calendario ME, causalidade, isolamento e gates do adaptador Sazonal mensal."""
import copy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, mock
import unittest

import numpy as np
import pandas as pd

from codigo_fonte.experimentos import experimento_sazonal_mensal_controle_auditado_v1 as a


def contexto(slug="monthly_6", fase="refit", regime="historico_1998_2022", entrada=Path(__file__)):
    p = a.motor.protocolo_padrao(regime)
    t = a.motor.construir_tarefa(slug, p)
    datas = pd.date_range(pd.Timestamp(p["inicio_dados"]) + pd.offsets.MonthEnd(0),
                          p["fim_dados"], freq="ME")
    valores = (1.25 + np.arange(len(datas)) * .271).astype(np.float32)
    s = a.m.SerieResolucao("A", 0, "BR", datas, valores, "ME", entrada)
    partes = (("ajuste", t.ajuste), ("validacao", t.validacao)) if fase == "selecao" else (
        ("refit", t.refit), ("teste", t.teste))
    janelas = {k: a.m.construir_janelas([s], seq_len=t.seq_len, pred_len=t.pred_len,
                                     intervalo=i, particao=k) for k, i in partes}
    escala = pd.DataFrame({"localidade_id": [0], "minimo_treino_wm2": [0.],
                           "amplitude_escala_wm2": [100.]})
    return SimpleNamespace(tarefa=t, fase=fase, protocolo=p, series=(s,), janelas=janelas,
                           escalas={fase: escala}, entradas=[entrada], elevacoes={},
                           config=a.m.ConfiguracaoMultirresolucao(modo_execucao="completa"))


class Calendario(TestCase):
    def test_fevereiro_pos_bissexto_aponta_fim_mes(self):
        self.assertEqual(a.data_ano_anterior(pd.Timestamp("2021-02-28"), mensal=True), pd.Timestamp("2020-02-29"))

    def test_fevereiro_bissexto_aponta_28_ano_anterior(self):
        self.assertEqual(a.data_ano_anterior(pd.Timestamp("2020-02-29"), mensal=True), pd.Timestamp("2019-02-28"))

    def test_todos_meses_validacao_e_teste_atual_preservados(self):
        for inicio, fim in (("2018-04-30", "2019-03-31"), ("2023-01-31", "2024-12-31")):
            for data in pd.date_range(inicio, fim, freq="ME"):
                with self.subTest(data=data):
                    self.assertEqual(a.data_ano_anterior(data, mensal=True), a.DATA_ORIGINAL(data, mensal=True))

    def test_diario_nao_muda_inclusive_29_fevereiro(self):
        for data in pd.date_range("2019-01-01", "2022-12-31", freq="D"):
            self.assertEqual(a.data_ano_anterior(data, mensal=False), a.DATA_ORIGINAL(data, mensal=False))

    def test_mensal_invalido_nao_e_silenciosamente_arredondado(self):
        for data in (pd.NaT, pd.Timestamp("2021-02-27"), pd.Timestamp("2021-02-28 01:00"),
                     pd.Timestamp("2021-02-28", tz="UTC")):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    a.data_ano_anterior(data, mensal=True)

    def test_helper_restaurado_apos_excecao(self):
        original = a.m._data_ano_anterior
        prever = a.m.prever_sazonal_anual
        with self.assertRaises(RuntimeError):
            with a._calendario():
                self.assertIs(a.m._data_ano_anterior, a.data_ano_anterior)
                self.assertIs(a.m.prever_sazonal_anual, prever)
                raise RuntimeError("falha")
        self.assertIs(a.m._data_ano_anterior, original)


class Previsoes(TestCase):
    def test_bug_legado_reproduzido_em_ambos_horizontes(self):
        for slug in a.TAREFAS:
            ctx = contexto(slug)
            with self.subTest(slug=slug):
                with self.assertRaisesRegex(ValueError, "Referencia anual ausente"):
                    a.q.previsoes_referencias(ctx, "teste", None, modelos=[a.MODELO])

    def test_quatro_niveis_preservam_regra_indice_menos12_minmax_e_alvos(self):
        for slug in a.TAREFAS:
            ctx = contexto(slug)
            j, s = ctx.janelas["teste"], ctx.series[0]
            alvos_antes, entradas_antes, serie_antes = j.y_bruto.copy(), j.x_bruto.copy(), s.ghi.copy()
            indices = s.datas.get_indexer(pd.DatetimeIndex(j.datas_alvo.reshape(-1))) - 12
            for _, niveis in a.est.VARIANTES:
                with self.subTest(slug=slug, niveis=niveis):
                    with a._calendario():
                        previsto = a.q.previsoes_referencias(ctx, "teste", niveis, modelos=[a.MODELO])[a.MODELO]
                    historico = a.q.quantizar_historico_bruto(s.ghi, ctx.escalas["refit"], 0, niveis)
                    esperado = historico[indices].reshape(j.y_bruto.shape).astype(float)
                    self.assertEqual(previsto.tobytes(), esperado.tobytes())
                    np.testing.assert_array_equal(j.y_bruto, alvos_antes)
                    np.testing.assert_array_equal(j.x_bruto, entradas_antes)
                    np.testing.assert_array_equal(s.ghi, serie_antes)

    def test_validacao_legada_bitexata_quatro_niveis_ambos_horizontes(self):
        for slug in a.TAREFAS:
            ctx = contexto(slug, "selecao")
            for _, niveis in a.est.VARIANTES:
                with self.subTest(slug=slug, niveis=niveis):
                    legado = a.q.previsoes_referencias(ctx, "validacao", niveis, modelos=[a.MODELO])[a.MODELO]
                    with a._calendario():
                        atual = a.q.previsoes_referencias(ctx, "validacao", niveis, modelos=[a.MODELO])[a.MODELO]
                    self.assertEqual(atual.dtype, legado.dtype)
                    self.assertEqual(atual.shape, legado.shape)
                    self.assertEqual(atual.tobytes(), legado.tobytes())

    def test_nao_usa_y_inclusive_nan_e_futuro_sem_referencia(self):
        for slug in a.TAREFAS:
            ctx = contexto(slug)
            for _, niveis in a.est.VARIANTES:
                with self.subTest(slug=slug, niveis=niveis):
                    with a._calendario():
                        antes = a.q.previsoes_referencias(ctx, "teste", niveis, modelos=[a.MODELO])[a.MODELO]
                        novo = copy.copy(ctx)
                        novo.janelas = dict(ctx.janelas)
                        j = copy.copy(ctx.janelas["teste"])
                        object.__setattr__(j, "y_bruto", np.full_like(j.y_bruto, np.nan))
                        novo.janelas["teste"] = j
                        depois = a.q.previsoes_referencias(novo, "teste", niveis, modelos=[a.MODELO])[a.MODELO]
                    self.assertEqual(antes.tobytes(), depois.tobytes())

    def test_falta_real_de_mes_continua_falhando_sem_imputacao(self):
        ctx = contexto()
        s = ctx.series[0]
        keep = s.datas != pd.Timestamp("2020-02-29")
        # Simula uma referencia ausente depois do carregador; o dataclass
        # original tambem rejeita series ME descontinuas na sua construcao.
        ctx.series = (SimpleNamespace(**{**vars(s), "datas": s.datas[keep], "ghi": s.ghi[keep]}),)
        with a._calendario(), self.assertRaisesRegex(ValueError, "Referencia anual ausente"):
            a.q.previsoes_referencias(ctx, "teste", None, modelos=[a.MODELO])

    def test_origem_nao_causal_continua_falhando(self):
        ctx = contexto()
        j = ctx.janelas["teste"]
        object.__setattr__(j, "origem", pd.DatetimeIndex(["1998-01-01"] * len(j.origem)))
        with a._calendario(), self.assertRaisesRegex(AssertionError, "nao causal"):
            a.q.previsoes_referencias(ctx, "teste", None, modelos=[a.MODELO])


class EscopoContratos(TestCase):
    def test_dois_horizontes_e_regimes_permitidos(self):
        for slug in a.TAREFAS:
            for regime in a.REGIMES:
                for fase in ("selecao", "refit"):
                    a.validar_escopo(contexto(slug, fase, regime))

    def test_outro_modelo_modo_regime_corte_horizonte_rejeitado(self):
        for mutacao in ("modelo", "modo", "regime", "corte", "horizonte"):
            with self.subTest(mutacao=mutacao):
                ctx, modelo = contexto(), a.MODELO
                if mutacao == "modelo": modelo = "Climatologia"
                elif mutacao == "modo": ctx.config = replace(ctx.config, modo_execucao="smoke")
                elif mutacao == "regime": ctx.protocolo["regime"] = "atual"
                elif mutacao == "corte": ctx.protocolo["inicio_teste"] = "2020-01-01"
                else: ctx.tarefa = replace(ctx.tarefa, pred_len=3, horizontes=(1, 3))
                with self.assertRaises(ValueError): a.validar_escopo(ctx, modelo)

    def test_contrato_longo_original_intacto_e_curto_inclui_fonte(self):
        with TemporaryDirectory() as tmp:
            fonte = Path(tmp) / "dados.csv"
            fonte.write_text("fixture", encoding="utf-8")
            longo = contexto(entrada=fonte)
            original = a.CONSTRUIR_ORIGINAL(longo, a.MODELO)
            self.assertEqual(a.construir_contrato(longo), original)
            curto = contexto(regime="historico_curto_pareado", entrada=fonte)
            novo = a.construir_contrato(curto)
            self.assertEqual(novo[a.CAMPO], a.POLITICA)
            self.assertEqual(novo["codigo"][str(Path(a.__file__).resolve())], a.m.sha256_arquivo(a.__file__))
            self.assertEqual(novo["sha256_contrato"], a.motor.hash_obj({k: v for k, v in novo.items() if k != "sha256_contrato"}))

    def test_longo_sem_contrato_complemento_bloqueado_sem_ativar_helper(self):
        with TemporaryDirectory() as tmp:
            original = a.m._data_ano_anterior
            with self.assertRaises(ValueError):
                with a.ativar_adaptador(contexto(), pasta=Path(tmp) / "novo"):
                    self.fail("gate deveria impedir entrada")
            self.assertIs(a.m._data_ano_anterior, original)

    def test_refit_sem_selecao_nao_e_criado_mesmo_curto(self):
        with TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                with a.ativar_adaptador(contexto(regime="historico_curto_pareado"), pasta=Path(tmp) / "novo"):
                    self.fail("refit sem selecao")

    def test_selecao_nova_curta_estampa_metadados_cp_e_restaura(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp) / "novo"
            ctx = contexto(fase="selecao", regime="historico_curto_pareado")
            originals = (a.m._data_ano_anterior, a.est.construir_contrato,
                         a.m.salvar_json_atomico, a.m.salvar_joblib_atomico)
            with mock.patch.object(a.m, "salvar_json_atomico") as salvar, \
                 mock.patch.object(a.m, "salvar_joblib_atomico") as joblib:
                with self.assertRaises(RuntimeError):
                    with a.ativar_adaptador(ctx, pasta=pasta) as provenance:
                        a.m.salvar_json_atomico({"arquivos_sha256": {}}, pasta / "q64/selecao/seed-1.json")
                        obj, path = salvar.call_args.args
                        self.assertEqual(obj[a.CAMPO], provenance)
                        self.assertIn(str(Path(a.__file__).resolve()), obj["arquivos_sha256"])
                        a.m.salvar_json_atomico({"sem_epocas": True}, pasta / "q64/selecao/detalhes.json")
                        self.assertEqual(salvar.call_args.args[0][a.CAMPO], provenance)
                        a.m.salvar_joblib_atomico({"receita_deterministica": True}, pasta / "q64/modelos/referencia_selecao.joblib")
                        self.assertEqual(joblib.call_args.args[0][a.CAMPO], provenance)
                        a.m.salvar_json_atomico({"inalterado": True}, pasta / "q64/refit/seed-1.json")
                        self.assertNotIn(a.CAMPO, salvar.call_args.args[0])
                        raise RuntimeError("interrupcao")
                self.assertIs(a.m.salvar_json_atomico, salvar)
                self.assertIs(a.m.salvar_joblib_atomico, joblib)
            self.assertEqual((a.m._data_ano_anterior, a.est.construir_contrato,
                              a.m.salvar_json_atomico, a.m.salvar_joblib_atomico), originals)

    def test_meta_sem_proveniencia_rejeitada_antes_replay(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            for variante, _ in a.est.VARIANTES:
                (pasta / variante / "refit").mkdir(parents=True)
                (pasta / variante / "refit/seed-1.npz").write_bytes(b"npz")
                (pasta / variante / "refit/seed-1.json").write_text("{}", encoding="utf-8")
            with mock.patch.object(a, "validar_comp", return_value={"tipo": "complemento_legado"}), \
                 self.assertRaisesRegex(ValueError, "proveniencia"):
                a.validar_metadados(pasta, "refit")

    def test_complemento_existente_nao_sobrescrito(self):
        with TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            path = pasta / a.COMPLEMENTO
            path.write_text('{"antigo":true}', encoding="utf-8")
            antes = path.read_bytes()
            with mock.patch.object(a, "construir_contrato_complementar", return_value={"novo": True}), \
                 self.assertRaisesRegex(ValueError, "diverge"):
                a.registrar_contrato_complementar(pasta)
            self.assertEqual(path.read_bytes(), antes)


if __name__ == "__main__":
    unittest.main()
