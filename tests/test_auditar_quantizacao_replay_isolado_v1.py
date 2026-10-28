"""Testes isolados do wrapper; nao importam torch nem executam replay real."""
from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import auditar_quantizacao_replay_isolado_v1 as a


class TestIsolamento(unittest.TestCase):
    def setUp(self):
        self.cudnn = SimpleNamespace(benchmark=False, deterministic=False, allow_tf32=True)

    def test_timesnet_nao_contamina_atencao_seguinte(self):
        vistos = []

        def original(modelo):
            vistos.append((modelo, self.cudnn.benchmark, self.cudnn.deterministic))
            if modelo == 'TimesNet':
                self.cudnn.deterministic = True
                self.cudnn.benchmark = False
                self.assertTrue(self.cudnn.deterministic)
            else:
                if self.cudnn.deterministic:
                    raise ValueError('Politica numerica/ambiente/piloto diverge do contrato.')
            return modelo

        auditor = SimpleNamespace(replay_aprendido=original)
        with a.ativar_isolamento(auditor, self.cudnn):
            self.assertEqual(auditor.replay_aprendido('TimesNet'), 'TimesNet')
            self.assertFalse(self.cudnn.deterministic)
            self.assertEqual(auditor.replay_aprendido('Transformer'), 'Transformer')
        self.assertEqual(vistos, [('TimesNet', False, False), ('Transformer', False, False)])
        self.assertIs(auditor.replay_aprendido, original)

    def test_estado_inicial_divergente_continua_reprovado(self):
        self.cudnn.deterministic = True

        def original():
            if self.cudnn.deterministic:
                raise ValueError('Politica numerica/ambiente/piloto diverge do contrato.')
            return 'aprovado'

        auditor = SimpleNamespace(replay_aprendido=original)
        with a.ativar_isolamento(auditor, self.cudnn):
            with self.assertRaisesRegex(ValueError, 'Politica numerica'):
                auditor.replay_aprendido()
        self.assertTrue(self.cudnn.deterministic)

    def test_excecao_original_e_flags_sao_preservadas(self):
        erro = ValueError('Replay divergente: checkpoint alterado')

        def original():
            self.cudnn.benchmark = True
            self.cudnn.deterministic = True
            raise erro

        auditor = SimpleNamespace(replay_aprendido=original)
        with a.ativar_isolamento(auditor, self.cudnn):
            with self.assertRaises(ValueError) as caught:
                auditor.replay_aprendido()
            self.assertIs(caught.exception, erro)
        self.assertEqual((self.cudnn.benchmark, self.cudnn.deterministic), (False, False))
        self.assertIs(auditor.replay_aprendido, original)

    def test_argumentos_resultado_e_outros_flags_nao_sao_modificados(self):
        self.cudnn.benchmark = True
        recebido = []
        resultado = object()

        def original(*args, **kwargs):
            recebido.append((args, kwargs, self.cudnn.benchmark, self.cudnn.deterministic))
            self.cudnn.benchmark = False
            self.cudnn.deterministic = True
            self.cudnn.allow_tf32 = False
            return resultado

        auditor = SimpleNamespace(replay_aprendido=original)
        contrato = {'sha256_contrato': 'valor congelado'}
        with a.ativar_isolamento(auditor, self.cudnn):
            self.assertIs(auditor.replay_aprendido(1, 2, contrato=contrato), resultado)
        self.assertEqual(recebido, [((1, 2), {'contrato': contrato}, True, False)])
        self.assertEqual(contrato, {'sha256_contrato': 'valor congelado'})
        self.assertEqual((self.cudnn.benchmark, self.cudnn.deterministic), (True, False))
        self.assertFalse(self.cudnn.allow_tf32)

    def test_contexto_restaurado_quando_main_falha(self):
        original = lambda: None
        auditor = SimpleNamespace(replay_aprendido=original)
        with self.assertRaisesRegex(RuntimeError, 'falha auditoria'):
            with a.ativar_isolamento(auditor, self.cudnn):
                raise RuntimeError('falha auditoria')
        self.assertIs(auditor.replay_aprendido, original)
        self.assertFalse(a._ativo)

    def test_contexto_aninhado_bloqueia_sem_remover_primeiro(self):
        original = lambda: None
        auditor = SimpleNamespace(replay_aprendido=original)
        with a.ativar_isolamento(auditor, self.cudnn):
            primeiro = auditor.replay_aprendido
            with self.assertRaisesRegex(RuntimeError, 'aninhados'):
                with a.ativar_isolamento(auditor, self.cudnn):
                    pass
            self.assertIs(auditor.replay_aprendido, primeiro)
        self.assertIs(auditor.replay_aprendido, original)

    def test_segunda_flag_restaurada_mesmo_se_primeira_falhar(self):
        class Backend:
            deterministic = False
            valor = False
            falhar = False

            @property
            def benchmark(self):
                return self.valor

            @benchmark.setter
            def benchmark(self, value):
                if self.falhar:
                    raise RuntimeError('restauracao benchmark falhou')
                self.valor = value

        backend = Backend()

        def original():
            backend.deterministic = True
            backend.falhar = True

        auditor = SimpleNamespace(replay_aprendido=original)
        with a.ativar_isolamento(auditor, backend):
            with self.assertRaisesRegex(RuntimeError, 'restauracao benchmark'):
                auditor.replay_aprendido()
        self.assertFalse(backend.deterministic)
        self.assertIs(auditor.replay_aprendido, original)


class TestGates(unittest.TestCase):
    def test_fonte_alterada_bloqueia_antes_importar_auditor(self):
        with tempfile.TemporaryDirectory(prefix='auditoria_replay_isolado_') as folder:
            path = Path(folder) / 'auditor.py'
            path.write_text('fonte alterada', encoding='utf-8')
            with patch.object(a, 'FONTE_ORIGINAL', path), patch.object(a.importlib, 'import_module') as importer:
                with self.assertRaisesRegex(RuntimeError, 'SHA256 congelado'):
                    a.carregar_auditor()
                importer.assert_not_called()

    def test_modulo_vindo_de_outro_caminho_bloqueia(self):
        with tempfile.TemporaryDirectory(prefix='auditoria_replay_isolado_') as folder:
            path = Path(folder) / 'auditor.py'
            path.write_bytes(b'fonte auditada')
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            modulo = SimpleNamespace(__file__=str(path.parent / 'outro.py'))
            with patch.object(a, 'FONTE_ORIGINAL', path), patch.object(a, 'SHA_ORIGINAL', sha), \
                    patch.object(a.importlib, 'import_module', return_value=modulo):
                with self.assertRaisesRegex(RuntimeError, 'outro caminho'):
                    a.carregar_auditor()

    def test_regimes_historicos_e_argumentos_originais_sao_aceitos(self):
        for regime in a.REGIMES:
            with self.subTest(regime=regime):
                self.assertTrue(a.validar_regime(['--regime', regime, '--replay', '--tarefas', 'daily_30', '--relatorio', 'audit.json']))

    def test_regime_atual_ou_desconhecido_e_ausencia_sao_rejeitados(self):
        for argv in ([], ['--regime', 'atual'], ['--regime', 'outro']):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                a.validar_regime(argv)

    def test_help_preserva_cli_original_sem_torch(self):
        auditor = SimpleNamespace(main=lambda: None)
        with patch.object(a.sys, 'argv', ['wrapper', '--help']), \
                patch.object(a, 'carregar_auditor', return_value=auditor), \
                patch.object(a.importlib, 'import_module') as importer:
            a.main()
            importer.assert_not_called()

    def test_main_delega_e_restaura_funcao_apos_excecao(self):
        backend = SimpleNamespace(benchmark=False, deterministic=False)
        original = lambda: None
        auditor = SimpleNamespace(replay_aprendido=original)

        def main_original():
            self.assertIsNot(auditor.replay_aprendido, original)
            raise ValueError('gate cientifico original')

        auditor.main = main_original
        torch = SimpleNamespace(backends=SimpleNamespace(cudnn=backend))
        with patch.object(a.sys, 'argv', ['wrapper', '--regime', a.REGIMES[0], '--replay']), \
                patch.object(a, 'carregar_auditor', return_value=auditor), \
                patch.object(a.importlib, 'import_module', return_value=torch):
            with self.assertRaisesRegex(ValueError, 'gate cientifico original'):
                a.main()
        self.assertIs(auditor.replay_aprendido, original)
        self.assertFalse(a._ativo)


if __name__ == '__main__':
    unittest.main()
