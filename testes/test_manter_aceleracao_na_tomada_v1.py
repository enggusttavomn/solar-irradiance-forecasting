"""Lifecycle do supervisor com processos e energia falsos, sem APIs Windows."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch

from codigo_fonte.acompanhamento import manter_aceleracao_na_tomada_v1 as m


def escrever_json(path, dados):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dados), encoding='utf-8')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class JournalFake:
    def __init__(self):
        self.gravados = []
        self.tentativas = []
        self.falhar = None
        self.apos_gravar = None

    def gravar(self, dados):
        copia = deepcopy(dados)
        self.tentativas.append(copia)
        if self.falhar is not None and self.falhar(copia):
            raise OSError('Gravacao duravel indisponivel no fake.')
        self.gravados.append(copia)
        if self.apos_gravar is not None:
            self.apos_gravar(copia)


class EnergiaFake:
    def __init__(self):
        self.ac = True

    def na_tomada(self):
        if self.ac is None:
            raise m.Bloqueio('Alimentacao indeterminada no fake.')
        return self.ac


@dataclass
class RegistroFake:
    instancia: m.Instancia
    ppid: int
    comando: list
    vivo: bool = True


class PopenFake:
    def __init__(self, backend, instancia):
        self.backend, self.instancia = backend, instancia
        self.pid = instancia.pid

    def poll(self):
        return None if self.backend.vivo(self.instancia) else 0

    def terminate(self):
        raise AssertionError('Supervisor nao deve encerrar processos por API.')

    def kill(self):
        raise AssertionError('Supervisor nao deve encerrar processos por API.')


class BackendFake:
    """Identidades exatas e lancamento registrado; nunca chama Popen real."""

    def __init__(self, root, child_sha, journal):
        self.root, self.child_sha, self.journal = root, child_sha, journal
        self.programa_base = None
        self.registros = {}
        self.guard_ids = set()
        self.lancamentos = []
        self.falha_launch = None
        self.emitir_estado = True
        self.ultimo_child = self.ultimo_launcher = None

    def adicionar(self, instancia, ppid=0, comando=(), guard=False):
        self.registros[instancia.pid] = RegistroFake(instancia, ppid, list(comando))
        if guard:
            self.guard_ids.add(instancia)
        return instancia

    def identificar(self, pid):
        registro = self.registros.get(pid)
        return registro.instancia if registro and registro.vivo else None

    def vivo(self, instancia):
        if instancia is None:
            return False
        return self.identificar(instancia.pid) == instancia

    def mapa(self):
        return {pid: r.ppid for pid, r in self.registros.items() if r.vivo}

    def comando(self, instancia):
        if not self.vivo(instancia):
            raise m.Bloqueio('Consulta de CLI sem identidade viva no fake.')
        return list(self.registros[instancia.pid].comando)

    def programa(self, instancia):
        if not self.vivo(instancia):
            raise m.Bloqueio('Consulta de imagem sem identidade viva no fake.')
        registro = self.registros[instancia.pid]
        if instancia == self.root or registro.ppid:
            return self.programa_base
        return Path(registro.comando[0]).resolve()

    def guardas(self):
        return {i for i in self.guard_ids if self.vivo(i)}

    def morrer(self, instancia):
        self.registros[instancia.pid].vivo = False

    def lancar(self, comando, out, err, raiz):
        if self.journal is not None:
            ultimo = self.journal.gravados[-1]
            if ultimo['etapa'] != 'LAUNCH_INTENT' or ultimo['comando'] != comando:
                raise AssertionError('LAUNCH_INTENT duravel deve preceder Popen.')
        self.lancamentos.append((list(comando), out, err, raiz))
        if self.falha_launch is not None:
            raise self.falha_launch
        n = len(self.lancamentos)
        launcher = self.adicionar(m.Instancia(1000 + n * 2, str(10000 + n * 2)),
                                  comando=comando, guard=True)
        child = self.adicionar(m.Instancia(1001 + n * 2, str(10001 + n * 2)),
                               ppid=launcher.pid, comando=comando, guard=True)
        self.ultimo_launcher, self.ultimo_child = launcher, child
        out.write_text('', encoding='utf-8')
        err.write_text('', encoding='utf-8')
        if self.emitir_estado:
            controle = Path(comando[comando.index('--saida') + 1])
            escrever_json(controle / 'estado.json', {
                'etapa': 'ATIVA', 'coordenador': asdict(self.root),
                'observador': asdict(child), 'fonte_sha256': self.child_sha,
                'prioridade_solicitada': 'High', 'ultimo_ciclo': {'erros': []},
            })
        return PopenFake(self, launcher)


class TestManterAceleracaoNaTomada(unittest.TestCase):
    def setUp(self):
        (m.RAIZ / 'tmp').mkdir(parents=True, exist_ok=True)
        self.tmp = TemporaryDirectory(prefix='supervisor-tomada-', dir=m.RAIZ / 'tmp')
        self.addCleanup(self.limpar_tmp)
        self.raiz = Path(self.tmp.name).resolve()
        self.root = m.Instancia(101, '100')
        self.launcher = m.Instancia(201, '200')
        self.child = m.Instancia(202, '201')
        rel = self.raiz / m.REL
        own = self.raiz / 'codigo_fonte/acompanhamento/manter_aceleracao_na_tomada_v1.py'
        source = self.raiz / 'codigo_fonte/acompanhamento/acelerar_cpu_local_temporariamente.py'
        own.parent.mkdir(parents=True)
        own.write_text('# fonte operacional fake\n', encoding='utf-8')
        source.write_text('# guard operacional fake\n', encoding='utf-8')
        recibo, root_recibo = rel / 'recibo.json', rel / 'root_recibo.json'
        self.parada = rel / 'parada_manual'
        escrever_json(recibo, {'aprovado': True, 'parada': str(self.parada)})
        escrever_json(root_recibo, {
            'aprovado': True, 'parada': str(self.parada),
            'recibo_anterior': {'path': str(recibo), 'sha256': sha(recibo)},
        })
        self.c = m.Config(
            raiz=self.raiz, own_source=own, own_sha=sha(own),
            child_source=source, child_sha=sha(source), recibo=recibo,
            recibo_sha=sha(recibo), root_recibo=root_recibo,
            root_recibo_sha=sha(root_recibo), root=self.root,
            saida=rel / 'supervisor_teste', adotar=rel / 'guard_anterior/controle',
            adotar_child=self.child, adotar_launcher=self.launcher,
        )
        self.c.python.parent.mkdir(parents=True)
        self.c.python.touch()
        escrever_json(self.c.coord_status, {
            'etapa': 'fila_historico_curto_pareado',
            'identidade_coordenador': asdict(self.root),
            'coordenador_complementar': {
                'recibo': str(recibo), 'recibo_sha256': self.c.recibo_sha},
            'retomada_apos_reinicio': {
                'recibo': str(root_recibo), 'recibo_sha256': self.c.root_recibo_sha},
        })
        escrever_json(self.c.adotar.parent / 'lancamento.json', {
            'etapa': 'LAUNCH_CONFIRMED', 'tentativas_popen': 1,
            'coordenador': asdict(self.root), 'comando': self.c.comando(self.c.adotar),
            'fonte_sha256': self.c.child_sha, 'launcher': asdict(self.launcher),
        })
        self.child_state = {
            'etapa': 'ATIVA', 'coordenador': asdict(self.root),
            'observador': asdict(self.child), 'fonte_sha256': self.c.child_sha,
            'prioridade_solicitada': 'High', 'ultimo_ciclo': {'erros': []},
        }
        self.escrever_child()
        (self.c.adotar.parent / 'observador.erro.log').write_text('', encoding='utf-8')
        self.journal = JournalFake()
        self.energia = EnergiaFake()
        self.backend = BackendFake(self.root, self.c.child_sha, self.journal)
        self.backend.programa_base = self.raiz / 'python_base.exe'
        self.backend.adicionar(self.root)
        self.backend.adicionar(self.launcher, comando=self.c.comando(self.c.adotar), guard=True)
        self.backend.adicionar(self.child, self.launcher.pid,
                               self.c.comando(self.c.adotar), guard=True)
        self.supervisor = m.Supervisor(self.c, self.backend, self.energia, self.journal)
        proibido = patch('subprocess.Popen', side_effect=AssertionError('Popen real proibido.'))
        proibido.start()
        self.addCleanup(proibido.stop)

    def limpar_tmp(self):
        """Compartilhamento transitorio do Windows nao deve falsear o teste."""
        destino = Path(self.tmp.name).resolve()
        raiz_tmp = (m.RAIZ / 'tmp').resolve()
        if destino == raiz_tmp or not destino.is_relative_to(raiz_tmp):
            raise AssertionError('Cleanup restrito a fixture unica dentro de tmp.')
        for tentativa in range(40):
            try:
                self.tmp.cleanup()
                return
            except PermissionError as erro:
                if getattr(erro, 'winerror', None) not in (5, 32, 33) or tentativa == 39:
                    raise
                time.sleep(0.1)

    def escrever_child(self):
        escrever_json(self.c.adotar / 'estado.json', self.child_state)

    def iniciar(self):
        self.assertTrue(self.supervisor.iniciar())
        self.assertEqual(self.backend.lancamentos, [])

    def preparar_retorno_ac(self):
        self.iniciar()
        self.energia.ac = False
        self.assertTrue(self.supervisor.passo())
        self.assertTrue(self.supervisor.bateria_observada)
        self.child_state.update(etapa='ENCERRADA', restauracao_prioridades={'erros': []})
        self.escrever_child()
        self.backend.morrer(self.child)
        self.backend.morrer(self.launcher)
        self.assertTrue(self.supervisor.passo())
        self.assertEqual(self.backend.lancamentos, [])
        self.energia.ac = True

    def assert_bloqueado_sem_retry(self, esperado=0):
        self.assertTrue(self.supervisor.falhou)
        for ac in (False, True, True):
            self.energia.ac = ac
            with self.assertRaises(m.Bloqueio):
                self.supervisor.passo()
        self.assertEqual(len(self.backend.lancamentos), esperado)

    def mudar_apos_intent(self, callback):
        self.preparar_retorno_ac()

        def apos_gravar(dados):
            if dados['etapa'] == 'LAUNCH_INTENT':
                callback()

        self.journal.apos_gravar = apos_gravar
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assertEqual(self.journal.gravados[-1]['etapa'], 'LAUNCH_INTENT')
        self.assert_bloqueado_sem_retry()

    def test_adota_identidades_conhecidas_sem_popen(self):
        self.iniciar()
        for _ in range(3):
            self.assertTrue(self.supervisor.passo())
        self.assertEqual(self.supervisor.child, self.child)
        self.assertEqual(self.supervisor.launcher, self.launcher)
        self.assertEqual(self.supervisor.estado['tentativas_popen'], 0)
        self.assertEqual(self.backend.lancamentos, [])

    def test_bateria_restore_morte_e_ac_lancam_um_unico_guard(self):
        self.preparar_retorno_ac()
        self.assertTrue(self.supervisor.passo())
        self.assertEqual(len(self.backend.lancamentos), 1)
        self.assertEqual(self.journal.gravados[-2]['etapa'], 'LAUNCH_INTENT')
        self.assertTrue(self.supervisor.passo())
        self.assertEqual(self.supervisor.child, self.backend.ultimo_child)
        self.assertFalse(self.supervisor.bateria_observada)
        for _ in range(3):
            self.assertTrue(self.supervisor.passo())
        self.assertEqual(len(self.backend.lancamentos), 1)

    def test_aguarda_launcher_anterior_morrer_antes_de_relancar(self):
        self.iniciar()
        self.energia.ac = False
        self.supervisor.passo()
        self.child_state.update(etapa='ENCERRADA', restauracao_prioridades={'erros': []})
        self.escrever_child()
        self.backend.morrer(self.child)
        self.energia.ac = True
        self.assertTrue(self.supervisor.passo())
        self.assertEqual(self.backend.lancamentos, [])
        self.backend.morrer(self.launcher)
        self.assertTrue(self.supervisor.passo())
        self.assertEqual(len(self.backend.lancamentos), 1)

    def test_morte_sem_bateria_observada_bloqueia_mesmo_com_encerrada(self):
        self.iniciar()
        self.child_state.update(etapa='ENCERRADA', restauracao_prioridades={'erros': []})
        self.escrever_child()
        self.backend.morrer(self.child)
        self.backend.morrer(self.launcher)
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_bateria_observada_sem_restore_confirmado_bloqueia(self):
        self.preparar_retorno_ac()
        self.child_state.pop('restauracao_prioridades')
        self.escrever_child()
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_erro_de_restore_sem_identidade_bloqueia(self):
        self.preparar_retorno_ac()
        self.child_state['restauracao_prioridades']['erros'] = [{'erro': 'Nao restaurado'}]
        self.escrever_child()
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_erro_de_restore_de_instancia_morta_permite_retomada(self):
        self.preparar_retorno_ac()
        trabalhador = self.backend.adicionar(m.Instancia(401, '400'))
        self.backend.morrer(trabalhador)
        self.child_state['restauracao_prioridades']['erros'] = [{
            **asdict(trabalhador), 'erro': 'Processo encerrou antes de restaurar.'}]
        self.escrever_child()
        self.assertTrue(self.supervisor.passo())
        self.assertEqual(len(self.backend.lancamentos), 1)

    def test_erro_de_restore_de_instancia_viva_bloqueia(self):
        self.preparar_retorno_ac()
        trabalhador = self.backend.adicionar(m.Instancia(401, '400'))
        self.child_state['restauracao_prioridades']['erros'] = [{
            **asdict(trabalhador), 'erro': 'Acesso negado durante restauracao.'}]
        self.escrever_child()
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_alimentacao_indeterminada_bloqueia_zero_launch(self):
        self.iniciar()
        self.energia.ac = None
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_guard_desconhecido_antes_da_adocao_bloqueia(self):
        self.backend.adicionar(m.Instancia(301, '300'), guard=True)
        with self.assertRaises(m.Bloqueio):
            self.supervisor.iniciar()
        self.assert_bloqueado_sem_retry()

    def test_guard_desconhecido_antes_do_novo_launch_bloqueia(self):
        self.preparar_retorno_ac()
        self.backend.adicionar(m.Instancia(301, '300'), guard=True)
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_cli_divergente_na_adocao_nao_lanca(self):
        self.backend.registros[self.child.pid].comando.append('--extra')
        with self.assertRaises(m.Bloqueio):
            self.supervisor.iniciar()
        self.assert_bloqueado_sem_retry()

    def test_fonte_alterada_antes_da_retomada_nao_lanca(self):
        self.preparar_retorno_ac()
        self.c.child_source.write_text('# fonte alterada\n', encoding='utf-8')
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_identidade_root_reutilizada_nao_lanca(self):
        self.preparar_retorno_ac()
        self.backend.adicionar(m.Instancia(self.root.pid, '500'))
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry()

    def test_falha_duravel_antes_de_popen_bloqueia_retry(self):
        self.preparar_retorno_ac()
        self.journal.falhar = lambda s: s['etapa'] == 'LAUNCH_INTENT'
        with self.assertRaises(OSError):
            self.supervisor.passo()
        self.assertFalse(any(s['etapa'] == 'LAUNCH_INTENT' for s in self.journal.gravados))
        self.assert_bloqueado_sem_retry()

    def test_falha_duravel_depois_de_popen_preserva_intent_e_bloqueia_retry(self):
        self.preparar_retorno_ac()
        self.journal.falhar = lambda s: s['etapa'] == 'CONFIRMANDO'
        with self.assertRaises(OSError):
            self.supervisor.passo()
        self.assertEqual(self.journal.gravados[-1]['etapa'], 'LAUNCH_INTENT')
        self.assert_bloqueado_sem_retry(esperado=1)

    def test_popen_inconclusivo_nao_ganha_segunda_tentativa(self):
        self.preparar_retorno_ac()
        self.backend.falha_launch = OSError('Popen inconclusivo no fake.')
        with self.assertRaises(OSError):
            self.supervisor.passo()
        self.assertEqual(self.journal.gravados[-1]['etapa'], 'LAUNCH_INTENT')
        self.assert_bloqueado_sem_retry(esperado=1)

    def test_root_muda_apos_intent_e_impede_popen(self):
        self.mudar_apos_intent(lambda: self.backend.morrer(self.root))

    def test_ac_muda_apos_intent_e_impede_popen(self):
        self.mudar_apos_intent(lambda: setattr(self.energia, 'ac', False))

    def test_marker_manual_apos_intent_impede_popen(self):
        self.mudar_apos_intent(self.parada.touch)

    def test_sinal_de_parada_apos_intent_impede_popen(self):
        self.mudar_apos_intent(lambda: setattr(self.supervisor, 'sinal_parada', True))

    def test_bateria_durante_confirmacao_nao_auto_repete(self):
        self.preparar_retorno_ac()
        self.supervisor.passo()
        self.energia.ac = False
        with self.assertRaises(m.Bloqueio):
            self.supervisor.passo()
        self.assert_bloqueado_sem_retry(esperado=1)

    def test_guard_novo_sem_estado_ate_o_prazo_nao_auto_repete(self):
        self.preparar_retorno_ac()
        self.backend.emitir_estado = False
        self.supervisor.passo()
        with patch.object(m.time, 'monotonic', return_value=self.supervisor.confirmacao_limite + 1):
            with self.assertRaises(m.Bloqueio):
                self.supervisor.passo()
        self.assert_bloqueado_sem_retry(esperado=1)

    def test_guard_novo_persistindo_preparado_apos_prazo_bloqueia(self):
        self.preparar_retorno_ac()
        self.supervisor.passo()
        path = self.supervisor.controle / 'estado.json'
        estado = json.loads(path.read_text(encoding='utf-8'))
        estado['etapa'] = 'PREPARADO'
        escrever_json(path, estado)
        with patch.object(m.time, 'monotonic', return_value=self.supervisor.confirmacao_limite + 1):
            with self.assertRaises(m.Bloqueio):
                self.supervisor.passo()
        self.assert_bloqueado_sem_retry(esperado=1)

    def test_parada_manual_do_guard_impede_auto_retomada(self):
        self.preparar_retorno_ac()
        (self.c.adotar / 'parar_aceleracao').touch()
        self.assertFalse(self.supervisor.passo())
        (self.c.adotar / 'parar_aceleracao').unlink()
        self.assertFalse(self.supervisor.passo())
        self.assertEqual(self.backend.lancamentos, [])

    def test_parada_manual_do_recibo_impede_auto_retomada(self):
        self.preparar_retorno_ac()
        self.parada.touch()
        self.assertFalse(self.supervisor.passo())
        self.parada.unlink()
        self.assertFalse(self.supervisor.passo())
        self.assertEqual(self.backend.lancamentos, [])

    def test_encerrar_usa_apenas_marker_da_pasta_conhecida(self):
        self.iniciar()
        self.supervisor.encerrar('Parada de teste')
        self.assertTrue((self.c.adotar / 'parar_aceleracao').is_file())
        self.assertTrue(self.backend.vivo(self.child))
        self.assertTrue(self.backend.vivo(self.launcher))
        self.assertFalse(self.supervisor.passo())
        self.assertEqual(self.backend.lancamentos, [])

    def test_claim_persistente_proibe_novo_supervisor_com_outra_saida(self):
        self.iniciar()
        outra = replace(self.c, saida=self.c.rel / 'outra_saida')
        novo = m.Supervisor(outra, self.backend, self.energia, JournalFake())
        with self.assertRaises(FileExistsError):
            novo.iniciar()
        self.assertTrue(novo.falhou)
        self.assertEqual(self.backend.lancamentos, [])

    def test_precheck_falha_e_cleanup_preserva_saida_e_guard_existentes(self):
        self.c.saida.mkdir()
        path = self.c.saida / 'journal.json'
        anterior = '{"estado": "preservar"}\n'
        path.write_text(anterior, encoding='utf-8')
        with self.assertRaises(FileExistsError):
            self.supervisor.iniciar()
        self.supervisor.encerrar('Falha antes da adocao')
        self.assertEqual(path.read_text(encoding='utf-8'), anterior)
        self.assertFalse((self.c.adotar / 'parar_aceleracao').exists())
        self.assertEqual(self.journal.gravados, [])
        self.assertEqual(self.backend.lancamentos, [])

    def test_journal_padrao_grava_adocao_em_json_local(self):
        self.backend.journal = None
        novo = m.Supervisor(self.c, self.backend, self.energia)
        self.assertTrue(novo.iniciar())
        gravado = json.loads((self.c.saida / 'journal.json').read_text(encoding='utf-8'))
        self.assertEqual(gravado['etapa'], 'ADOTADO')
        self.assertEqual(gravado['tentativas_popen'], 0)
        self.assertEqual(gravado['child'], asdict(self.child))
        self.assertEqual(self.backend.lancamentos, [])


if __name__ == '__main__':
    unittest.main()
