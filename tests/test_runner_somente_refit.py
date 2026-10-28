"""Gate e agenda somente-refit, com processos fake e contratos sinteticos."""
import argparse
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from scripts import rodar_quantizacao_todos_modelos as runner


class TestRunnerSomenteRefit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='teste_somente_refit_')
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.args = argparse.Namespace(
            regime='historico_1998_2022', saida=self.base / 'resultados',
            relatorios=self.base / 'relatorios', tarefas=['daily_30'], modelos=['XGBoost'],
            cpu_workers=2, gpu_workers=2, gpu_modelos=['GRU', 'LSTM'],
            protocolo=None, smoke=False, somente_selecao=False, somente_refit=True,
        )
        self.pares = [('daily_30', 'XGBoost')]
        self.pasta = self.args.saida / self.args.regime / 'daily_30' / 'xgboost'
        self.pasta.mkdir(parents=True)
        self.selecao = self.pasta / 'selecao_congelada.json'
        self.contrato = self.pasta / 'contrato_execucao.json'
        self.selecao.write_text(json.dumps({'selecao_concluida_antes_refit': True}), encoding='utf-8')
        self.contrato.write_text(json.dumps({'modo': 'completa', 'parametros': {'sementes': [42]}}), encoding='utf-8')
        self.global_path = self.args.saida / self.args.regime / 'selecao_global_congelada.json'
        self.rel = self.args.relatorios / self.args.regime / 'completa'
        self.rel.mkdir(parents=True)
        self.children = []
        self.estados = []

    def congelamento_valido(self):
        self.args.somente_refit = False
        try:
            runner.congelar(self.args, self.pares)
        finally:
            self.args.somente_refit = True
        return self.global_path.read_bytes()

    def executar_fake(self):
        children = self.children
        class ProcessoFake:
            def __init__(self, cmd, **kwargs):
                children.append(cmd)
                self.pid = 900 + len(children)
                self.registro = {'pid': self.pid, 'creation_time': str(10000 + self.pid)}
            def poll(self):
                return 0
            def fechar(self):
                pass
            def encerrar(self):
                raise AssertionError('Processo ja completo nao deve ser encerrado.')
        api_fake = types.SimpleNamespace(windll=types.SimpleNamespace(
            kernel32=types.SimpleNamespace(SetThreadExecutionState=lambda _: 1)))
        with ExitStack() as mocks, redirect_stdout(io.StringIO()):
            mocks.enter_context(patch.object(runner, 'ProcessoProprio', ProcessoFake))
            mocks.enter_context(patch.object(runner, 'identidade', return_value={'pid': 1, 'creation_time': '10'}))
            mocks.enter_context(patch.object(runner, 'ctypes', api_fake))
            mocks.enter_context(patch.object(runner.time, 'sleep'))
            mocks.enter_context(patch.object(runner, 'salvar', side_effect=lambda dados, _: self.estados.append(deepcopy(dados))))
            runner.executar_fila(self.args, self.rel, self.pares, self.pares)

    def argv(self, *flags):
        return ['runner', '--regime', self.args.regime, '--saida', str(self.args.saida),
                '--relatorios', str(self.args.relatorios), '--tarefas', 'daily_30',
                '--modelos', 'XGBoost', *flags]

    def plano(self, *flags):
        texto = io.StringIO()
        with patch.object(runner.sys, 'argv', self.argv('--dry-run', *flags)), redirect_stdout(texto), patch.object(runner, 'ProcessoProprio') as children:
            runner.main()
            children.assert_not_called()
        return json.loads(texto.getvalue())

    def test_fases_correspondem_as_flags(self):
        self.assertEqual(runner.fases(self.args), ('refit',))
        self.args.somente_refit = False
        self.assertEqual(runner.fases(self.args), ('selecao', 'refit'))
        self.args.somente_selecao = True
        self.assertEqual(runner.fases(self.args), ('selecao',))

    def test_sem_global_bloqueia_antes_de_qualquer_child(self):
        with self.assertRaises(ValueError):
            self.executar_fake()
        self.assertEqual(self.children, [])
        self.assertFalse(self.global_path.exists())
        self.assertEqual(self.estados[-1]['etapa'], 'erro')

    def test_global_valido_agenda_apenas_refit(self):
        anterior = self.congelamento_valido()
        self.executar_fake()
        self.assertEqual(len(self.children), 1)
        cmd = self.children[0]
        self.assertEqual(cmd[cmd.index('--fase') + 1], 'refit')
        self.assertEqual(self.estados[-1]['etapa'], 'concluida')
        self.assertEqual([x['fase'] for x in self.estados[-1]['concluidos']], ['refit'])
        self.assertEqual(self.global_path.read_bytes(), anterior)

    def test_global_divergente_bloqueia_sem_children(self):
        self.congelamento_valido()
        original = json.loads(self.global_path.read_text(encoding='utf-8'))
        mudancas = {
            'regime': 'historico_curto_pareado', 'modo': 'smoke',
            'pares': [['monthly_1', 'XGBoost']], 'fontes_sha256': {},
        }
        for chave, valor in mudancas.items():
            with self.subTest(chave=chave):
                alterado = deepcopy(original)
                alterado[chave] = valor
                self.global_path.write_text(json.dumps(alterado), encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.executar_fake()
                self.assertEqual(self.children, [])
                self.assertEqual(json.loads(self.global_path.read_text(encoding='utf-8')), alterado)

    def test_global_json_corrompido_bloqueia_sem_children(self):
        self.global_path.write_text('{corrompido', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.executar_fake()
        self.assertEqual(self.children, [])
        self.assertEqual(self.global_path.read_text(encoding='utf-8'), '{corrompido')

    def test_global_nao_objeto_bloqueia_sem_children(self):
        self.global_path.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.executar_fake()
        self.assertEqual(self.children, [])

    def test_selecao_alterada_apos_congelamento_bloqueia(self):
        self.congelamento_valido()
        self.selecao.write_text(json.dumps({'selecao_concluida_antes_refit': True, 'mudou': True}), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.executar_fake()
        self.assertEqual(self.children, [])

    def test_contrato_alterado_apos_congelamento_bloqueia(self):
        self.congelamento_valido()
        self.contrato.write_text(json.dumps({'modo': 'completa', 'parametros': {'sementes': [67]}}), encoding='utf-8')
        with self.assertRaises(ValueError):
            self.executar_fake()
        self.assertEqual(self.children, [])

    def test_global_valido_nao_e_reescrito(self):
        anterior = self.congelamento_valido()
        mtime = self.global_path.stat().st_mtime_ns
        with patch.object(runner, 'salvar') as salvar:
            self.assertEqual(runner.congelar(self.args, self.pares), str(self.global_path))
            salvar.assert_not_called()
        self.assertEqual(self.global_path.read_bytes(), anterior)
        self.assertEqual(self.global_path.stat().st_mtime_ns, mtime)

    def test_flag_selecao_e_refit_sao_mutuamente_exclusivas(self):
        with patch.object(runner.sys, 'argv', self.argv('--somente-selecao', '--somente-refit')), redirect_stderr(io.StringIO()), patch.object(runner, 'ProcessoProprio') as children:
            with self.assertRaises(SystemExit) as exc:
                runner.main()
            self.assertEqual(exc.exception.code, 2)
            children.assert_not_called()
        self.assertFalse(self.global_path.exists())

    def test_dry_run_refit_mostra_somente_comandos_refit(self):
        anterior = self.congelamento_valido()
        plano = self.plano('--somente-refit')
        self.assertEqual(len(plano), 1)
        self.assertEqual(plano[0]['fase'], 'refit')
        cmd = plano[0]['comando']
        self.assertEqual(cmd[cmd.index('--fase') + 1], 'refit')
        self.assertEqual(self.global_path.read_bytes(), anterior)
        self.assertFalse((self.rel / 'runner.json').exists())

    def test_dry_run_refit_sem_global_bloqueia_sem_criar(self):
        texto = io.StringIO()
        with patch.object(runner.sys, 'argv', self.argv('--dry-run', '--somente-refit')), redirect_stdout(texto), patch.object(runner, 'ProcessoProprio') as children:
            with self.assertRaises(ValueError):
                runner.main()
            children.assert_not_called()
        self.assertEqual(texto.getvalue(), '')
        self.assertFalse(self.global_path.exists())

    def test_dry_run_normal_preserva_plano_selecao_original(self):
        plano = self.plano()
        self.assertEqual([p['fase'] for p in plano], ['selecao'])
        self.assertFalse(self.global_path.exists())

    def test_dry_run_somente_selecao_nao_exige_global(self):
        plano = self.plano('--somente-selecao')
        self.assertEqual([p['fase'] for p in plano], ['selecao'])
        self.assertFalse(self.global_path.exists())

    def test_global_que_desaparece_durante_gate_nao_e_recriado(self):
        self.congelamento_valido()
        hash_original = runner.hash_arquivo
        def hash_com_corrida(path):
            if path == self.selecao:
                self.global_path.unlink()
            return hash_original(path)
        with patch.object(runner, 'hash_arquivo', side_effect=hash_com_corrida):
            with self.assertRaises(ValueError):
                self.executar_fake()
        self.assertEqual(self.children, [])
        self.assertFalse(self.global_path.exists())


if __name__ == '__main__':
    unittest.main()