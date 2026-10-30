from datetime import datetime, timedelta, timezone
import math
import unittest

from codigo_fonte.acompanhamento.estimativa_tempo_quantizacao import estimar_restante


AGORA = datetime(2026, 9, 30, 17, tzinfo=timezone.utc)


def meta(duracao, atraso=0):
    return {'duracao_s': duracao,
            'concluido_em_utc': (AGORA - timedelta(seconds=atraso)).isoformat()}


class EstimativaTempoTests(unittest.TestCase):
    def test_sem_amostras_nao_inventa_duracao(self):
        e = estimar_restante([], 20, AGORA, executando=True)
        self.assertEqual(e['status'], 'sem_base')
        self.assertEqual(e['restantes'], 20)
        self.assertIsNone(e['min_s'])
        self.assertIsNone(e['max_s'])

    def test_duracoes_invalidas_contam_conclusao_mas_nao_amostra(self):
        registros = [meta(x) for x in (None, 0, -2, math.nan, math.inf, True, '12')]
        e = estimar_restante(registros, 10, AGORA)
        self.assertEqual(e['restantes'], 3)
        self.assertEqual(e['amostras'], 0)
        self.assertEqual(e['status'], 'sem_base')

    def test_ultimas_oito_por_data_sem_depender_da_ordem_recebida(self):
        registros = [meta(100, atraso=i) for i in range(8)]
        registros += [meta(10000, atraso=100), meta(20000, atraso=200)]
        e = estimar_restante(registros, 11, AGORA)
        self.assertEqual(e['amostras'], 8)
        self.assertEqual(e['min_s'], 65)
        self.assertEqual(e['max_s'], 150)

    def test_amostra_pequena_tem_margem_maior(self):
        pequena = estimar_restante([meta(100)], 2, AGORA)
        maior = estimar_restante([meta(100)] * 3, 4, AGORA)
        self.assertLess(pequena['min_s'], maior['min_s'])
        self.assertGreater(pequena['max_s'], maior['max_s'])

    def test_parado_nao_desconta_tempo(self):
        e = estimar_restante([meta(100, 500)], 2, AGORA,
                            inicio=AGORA - timedelta(seconds=100))
        self.assertEqual(e['min_s'], 50)
        self.assertEqual(e['max_s'], 200)

    def test_retomada_nao_conta_pausa_como_treino(self):
        e = estimar_restante([meta(100, 3600)], 2, AGORA,
                            inicio=AGORA - timedelta(seconds=10), executando=True)
        self.assertEqual(e['min_s'], 40)
        self.assertEqual(e['max_s'], 190)
        self.assertFalse(e['recalibrado'])

    def test_ultima_conclusao_ancora_seed_em_execucao(self):
        e = estimar_restante([meta(100, 100), meta(100, 10)], 4, AGORA,
                            inicio=AGORA - timedelta(seconds=500), executando=True)
        self.assertEqual(e['min_s'], 90)
        self.assertEqual(e['max_s'], 390)

    def test_decorrido_afeta_apenas_seed_atual(self):
        e = estimar_restante([meta(100, 200)], 4, AGORA,
                            inicio=AGORA - timedelta(seconds=150), executando=True)
        self.assertGreaterEqual(e['min_s'], 100)
        self.assertGreaterEqual(e['max_s'], 400)

    def test_extrapolacao_recalibra_sem_zero_ou_prazo_passado(self):
        e = estimar_restante([meta(100, 1000)], 2, AGORA,
                            inicio=AGORA - timedelta(seconds=900), executando=True)
        self.assertEqual(e['status'], 'estimado')
        self.assertTrue(e['recalibrado'])
        self.assertGreater(e['min_s'], 0)
        self.assertGreaterEqual(e['max_s'], e['min_s'])

    def test_ativo_com_todas_sementes_esta_finalizando(self):
        e = estimar_restante([meta(100)], 1, AGORA, executando=True)
        self.assertEqual(e['status'], 'finalizando')
        self.assertIsNone(e['min_s'])
        self.assertIsNone(e['max_s'])

    def test_encerramento_nao_da_eta_de_treino(self):
        e = estimar_restante([], 0, AGORA, encerrando=True)
        self.assertEqual(e['status'], 'finalizando')
        self.assertIsNone(e['min_s'])

    def test_terminado_inativo(self):
        e = estimar_restante([meta(100)], 1, AGORA)
        self.assertEqual(e['status'], 'concluido')
        self.assertEqual(e['restantes'], 0)
        self.assertEqual(e['min_s'], 0)

    def test_datas_invalidas_ou_sem_fuso_nao_subtraem(self):
        for inicio in ('invalida', AGORA.replace(tzinfo=None), None):
            with self.subTest(inicio=inicio):
                e = estimar_restante([meta(100)], 2, AGORA,
                                    inicio=inicio, executando=True)
                self.assertEqual(e['min_s'], 50)
                self.assertEqual(e['max_s'], 200)

    def test_inicio_futuro_e_ignorando(self):
        e = estimar_restante([meta(100, 500)], 2, AGORA,
                            inicio=AGORA + timedelta(seconds=10), executando=True)
        self.assertEqual(e['min_s'], 50)
        self.assertEqual(e['max_s'], 200)

    def test_registros_nao_sao_mutados(self):
        registros = [meta(100)]
        copia = [dict(x) for x in registros]
        estimar_restante(registros, 2, AGORA, executando=True)
        self.assertEqual(registros, copia)

    def test_total_invalido(self):
        for total in (-1, 2.5, True):
            with self.subTest(total=total):
                with self.assertRaises(ValueError):
                    estimar_restante([], total, AGORA)


if __name__ == '__main__':
    unittest.main()