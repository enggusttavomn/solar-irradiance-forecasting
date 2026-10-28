"""Guards operacionais de prioridade, sem Win32 ou processos reais."""
from contextlib import contextmanager
from dataclasses import dataclass
import unittest

from scripts.priorizar_treinamentos import (
    ABOVE_NORMAL, BELOW_NORMAL, HIGH, IDLE, NORMAL, REALTIME,
    Controlador, Instancia,
)


@dataclass
class ProcessoFake:
    instancia: Instancia
    ppid: int
    prioridade: int = NORMAL
    vivo: bool = True


@dataclass
class HandleFake:
    processo: ProcessoFake
    aberto: bool = True


class BackendFake:
    """Handles pertencem a uma instancia, mesmo quando o PID e reutilizado."""

    def __init__(self):
        self.processos = {}
        self.handles = []
        self.ganchos = {}
        self.tentativas = []
        self.mutacoes = []

    def adicionar(self, pid, criado, ppid=0, prioridade=NORMAL):
        instancia = Instancia(pid, str(criado))
        self.processos[pid] = ProcessoFake(instancia, ppid, prioridade)
        return instancia

    def reusar(self, pid, criado, ppid=0, prioridade=NORMAL):
        self.processos[pid].vivo = False
        return self.adicionar(pid, criado, ppid, prioridade)

    def uma_vez(self, evento, pid, callback):
        self.ganchos.setdefault((evento, pid), []).append(callback)

    def _evento(self, evento, pid, *args):
        fila = self.ganchos.get((evento, pid))
        if fila:
            callback = fila.pop(0)
            callback(*args)

    def mapa(self):
        # Permite que o snapshot seja antigo, mas identidade posterior seja nova.
        resultado = {pid: p.ppid for pid, p in self.processos.items() if p.vivo}
        self._evento('apos_mapa', None)
        return resultado

    def identidade(self, pid):
        self._evento('antes_identidade', pid)
        processo = self.processos.get(pid)
        return processo.instancia if processo and processo.vivo else None

    @contextmanager
    def abrir(self, instancia):
        self._evento('antes_abrir', instancia.pid, instancia)
        processo = self.processos.get(instancia.pid)
        if not processo or not processo.vivo or processo.instancia != instancia:
            raise ProcessLookupError('Instancia mudou antes de abrir o handle.')
        handle = HandleFake(processo)
        self.handles.append(handle)
        try:
            self._evento('apos_abrir', instancia.pid, handle)
            yield handle
        finally:
            handle.aberto = False
            self.handles.remove(handle)

    def vivo(self, handle):
        return handle.aberto and handle.processo.vivo

    def prioridade(self, handle):
        if not handle.aberto:
            raise OSError('Handle fechado.')
        self._evento('ler_prioridade', handle.processo.instancia.pid, handle)
        return handle.processo.prioridade

    def definir(self, handle, classe):
        instancia = handle.processo.instancia
        self.tentativas.append((instancia, classe))
        self._evento('antes_definir', instancia.pid, handle, classe)
        if not self.vivo(handle):
            raise ProcessLookupError('Handle pertence a processo encerrado.')
        handle.processo.prioridade = classe
        self.mutacoes.append({
            'instancia': instancia,
            'classe': classe,
            'cadeia_aberta': tuple(h.processo.instancia for h in self.handles),
            'cadeia_viva': all(self.vivo(h) for h in self.handles),
        })
        self._evento('apos_definir', instancia.pid, handle, classe)


class TestPriorizarTreinamentos(unittest.TestCase):
    def setUp(self):
        self.backend = BackendFake()
        self.raiz = self.backend.adicionar(10, 100)
        self.controle = Controlador(self.raiz, self.backend)

    def assertNaoTentou(self, instancia):
        self.assertFalse(any(i == instancia for i, _ in self.backend.tentativas))

    def assertErroAlvo(self, resultado, instancia):
        self.assertTrue(any(e['pid'] == instancia.pid for e in resultado['erros']))

    def test_arvore_mantem_cadeia_aberta_e_nao_altera_outras_arvores(self):
        filho = self.backend.adicionar(11, 110, 10)
        neto = self.backend.adicionar(12, 120, 11)
        externo = self.backend.adicionar(20, 130)
        filho_externo = self.backend.adicionar(21, 140, 20)
        resultado = self.controle.ciclo()
        self.assertEqual({x['pid'] for x in resultado['alterados']}, {10, 11, 12})
        self.assertEqual(resultado['erros'], [])
        for mutacao, esperada in zip(self.backend.mutacoes, (
                (self.raiz,), (self.raiz, filho), (self.raiz, filho, neto))):
            self.assertEqual(mutacao['cadeia_aberta'], esperada)
            self.assertTrue(mutacao['cadeia_viva'])
        for instancia in (externo, filho_externo):
            self.assertNaoTentou(instancia)
            self.assertEqual(self.backend.processos[instancia.pid].prioridade, NORMAL)
        self.assertEqual(self.controle.alterados, {
            self.raiz: NORMAL, filho: NORMAL, neto: NORMAL,
        })
        self.assertEqual(self.backend.handles, [])

    def test_reuso_de_pid_da_raiz_aborta_sem_mutacao(self):
        filho = self.backend.adicionar(11, 110, 10)
        nova_raiz = self.backend.reusar(10, 200)
        with self.assertRaises(RuntimeError):
            self.controle.ciclo()
        self.assertEqual(self.backend.tentativas, [])
        self.assertEqual(self.controle.alterados, {})
        self.assertEqual(self.backend.processos[nova_raiz.pid].prioridade, NORMAL)
        self.assertNaoTentou(filho)

    def test_raiz_encerrada_aborta_sem_mutacao(self):
        self.backend.processos[10].vivo = False
        with self.assertRaises(RuntimeError):
            self.controle.ciclo()
        self.assertEqual(self.backend.tentativas, [])

    def test_filho_anterior_ao_pai_e_seu_descendente_sao_ignorados(self):
        antigo = self.backend.adicionar(11, 99, 10)
        neto = self.backend.adicionar(12, 120, 11)
        resultado = self.controle.ciclo()
        self.assertEqual({x['pid'] for x in resultado['alterados']}, {10})
        self.assertNaoTentou(antigo)
        self.assertNaoTentou(neto)

    def test_filetime_igual_ao_pai_permite_filho(self):
        filho = self.backend.adicionar(11, 100, 10)
        resultado = self.controle.ciclo()
        self.assertEqual({x['pid'] for x in resultado['alterados']}, {10, 11})
        self.assertEqual(self.controle.alterados[filho], NORMAL)

    def test_filho_reutilizado_antes_de_abrir_nao_recebe_prioridade(self):
        filho = self.backend.adicionar(11, 110, 10)
        self.backend.uma_vez('antes_abrir', 11, lambda _: self.backend.reusar(11, 300, 20))
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, filho)
        self.assertNaoTentou(filho)
        self.assertNaoTentou(self.backend.processos[11].instancia)
        self.assertEqual(self.backend.processos[11].prioridade, NORMAL)
        self.assertNotIn(filho, self.controle.alterados)

    def test_snapshot_antigo_identidade_nova_externa_e_rejeitada(self):
        self.backend.adicionar(11, 110, 10)
        self.backend.adicionar(20, 130)
        self.backend.uma_vez('apos_mapa', None, lambda: self.backend.reusar(11, 300, 20))
        resultado = self.controle.ciclo()
        novo = self.backend.processos[11].instancia
        self.assertErroAlvo(resultado, novo)
        self.assertNaoTentou(novo)
        self.assertEqual(self.backend.processos[11].prioridade, NORMAL)
        self.assertNotIn(novo, self.controle.alterados)

    def test_parentesco_de_ancestral_tambem_e_revalidado(self):
        filho = self.backend.adicionar(11, 110, 10)
        neto = self.backend.adicionar(12, 120, 11)
        self.backend.uma_vez('apos_abrir', 12,
            lambda _: setattr(self.backend.processos[11], 'ppid', 20))
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, neto)
        self.assertNaoTentou(neto)
        self.assertIn(filho, self.controle.alterados)

    def test_pai_reutilizado_durante_transacao_rejeita_neto(self):
        self.backend.adicionar(11, 110, 10)
        neto = self.backend.adicionar(12, 120, 11)
        self.backend.uma_vez('apos_abrir', 12,
            lambda _: self.backend.reusar(11, 300, 20))
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, neto)
        self.assertNaoTentou(neto)
        self.assertEqual(self.backend.processos[11].prioridade, NORMAL)
        self.assertEqual(self.backend.handles, [])

    def test_pai_encerra_ao_ler_prioridade_e_impede_set_no_filho(self):
        filho = self.backend.adicionar(11, 110, 10)
        self.backend.uma_vez('ler_prioridade', 11,
            lambda _: setattr(self.backend.processos[10], 'vivo', False))
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, filho)
        self.assertNaoTentou(filho)
        self.assertNotIn(filho, self.controle.alterados)
        self.assertEqual(self.backend.processos[11].prioridade, NORMAL)

    def test_alvo_encerra_apos_abrir_e_impede_set(self):
        filho = self.backend.adicionar(11, 110, 10)
        self.backend.uma_vez('apos_abrir', 11,
            lambda h: setattr(h.processo, 'vivo', False))
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, filho)
        self.assertNaoTentou(filho)
        self.assertNotIn(filho, self.controle.alterados)

    def test_alvo_encerra_ao_ler_prioridade_e_impede_set(self):
        filho = self.backend.adicionar(11, 110, 10)
        self.backend.uma_vez('ler_prioridade', 11,
            lambda h: setattr(h.processo, 'vivo', False))
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, filho)
        self.assertNaoTentou(filho)
        self.assertNotIn(filho, self.controle.alterados)

    def test_classes_superiores_preservadas_e_inferiores_elevadas(self):
        self.backend.processos[10].prioridade = ABOVE_NORMAL
        classes = [ABOVE_NORMAL, HIGH, REALTIME, NORMAL, BELOW_NORMAL, IDLE]
        instancias = [self.backend.adicionar(11 + n, 110 + n, 10, classe)
                      for n, classe in enumerate(classes)]
        resultado = self.controle.ciclo()
        self.assertEqual(resultado['erros'], [])
        self.assertNaoTentou(self.raiz)
        for instancia, classe in zip(instancias, classes):
            with self.subTest(classe=classe):
                if classe in (ABOVE_NORMAL, HIGH, REALTIME):
                    self.assertNaoTentou(instancia)
                    self.assertNotIn(instancia, self.controle.alterados)
                    self.assertEqual(self.backend.processos[instancia.pid].prioridade, classe)
                else:
                    self.assertEqual(self.controle.alterados[instancia], classe)
                    self.assertEqual(self.backend.processos[instancia.pid].prioridade, ABOVE_NORMAL)

    def test_novo_filho_e_priorizado_no_proximo_ciclo(self):
        primeiro = self.controle.ciclo()
        filho = self.backend.adicionar(11, 110, 10)
        segundo = self.controle.ciclo()
        terceiro = self.controle.ciclo()
        self.assertEqual([x['pid'] for x in primeiro['alterados']], [10])
        self.assertEqual([x['pid'] for x in segundo['alterados']], [11])
        self.assertEqual(terceiro['alterados'], [])
        self.assertEqual(self.controle.alterados, {self.raiz: NORMAL, filho: NORMAL})
        self.assertEqual(len(self.backend.mutacoes), 2)

    def test_falha_em_um_alvo_nao_impede_outro(self):
        negado = self.backend.adicionar(11, 110, 10)
        outro = self.backend.adicionar(12, 120, 10)
        def negar(_):
            raise PermissionError('Acesso negado no alvo fake.')
        self.backend.uma_vez('antes_abrir', 11, negar)
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, negado)
        self.assertNaoTentou(negado)
        self.assertIn(outro, self.controle.alterados)
        self.assertEqual(self.backend.processos[12].prioridade, ABOVE_NORMAL)

    def test_set_falhou_nao_e_registrado_para_restauracao(self):
        filho = self.backend.adicionar(11, 110, 10)
        def negar(_, __):
            raise PermissionError('SetPriorityClass negado.')
        self.backend.uma_vez('antes_definir', 11, negar)
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, filho)
        self.assertNotIn(filho, self.controle.alterados)
        self.assertEqual(self.backend.processos[11].prioridade, NORMAL)
        self.controle.restaurar()
        self.assertEqual([i for i, _ in self.backend.tentativas].count(filho), 1)

    def test_readback_falhou_depois_de_set_preserva_original_para_restore(self):
        filho = self.backend.adicionar(11, 110, 10, BELOW_NORMAL)
        def apos_set(_, __):
            def falhar_readback(_):
                raise OSError('Leitura posterior indisponivel.')
            self.backend.uma_vez('ler_prioridade', 11, falhar_readback)
        self.backend.uma_vez('apos_definir', 11, apos_set)
        resultado = self.controle.ciclo()
        self.assertErroAlvo(resultado, filho)
        self.assertEqual(self.backend.processos[11].prioridade, ABOVE_NORMAL)
        self.assertEqual(self.controle.alterados[filho], BELOW_NORMAL)
        restaurado = self.controle.restaurar()
        self.assertEqual(restaurado['erros'], [])
        self.assertEqual(self.backend.processos[11].prioridade, BELOW_NORMAL)
        self.assertIn(11, {x['pid'] for x in restaurado['restaurados']})

    def test_restore_so_mesma_instancia_alterada_e_ainda_above_normal(self):
        reutilizado = self.backend.adicionar(11, 110, 10)
        alterado_usuario = self.backend.adicionar(12, 120, 10)
        ja_normal = self.backend.adicionar(13, 130, 10)
        elegivel = self.backend.adicionar(14, 140, 10, BELOW_NORMAL)
        externo = self.backend.adicionar(20, 150, 0, ABOVE_NORMAL)
        self.controle.ciclo()
        novo = self.backend.reusar(11, 300, 20, ABOVE_NORMAL)
        self.backend.processos[12].prioridade = HIGH
        self.backend.processos[13].prioridade = NORMAL
        antes = len(self.backend.tentativas)
        resultado = self.controle.restaurar()
        self.assertEqual({x['pid'] for x in resultado['restaurados']}, {10, 14})
        self.assertErroAlvo(resultado, reutilizado)
        self.assertEqual(self.backend.processos[14].prioridade, BELOW_NORMAL)
        self.assertEqual(self.backend.processos[12].prioridade, HIGH)
        self.assertEqual(self.backend.processos[13].prioridade, NORMAL)
        self.assertEqual(self.backend.processos[11].prioridade, ABOVE_NORMAL)
        restauracoes = self.backend.tentativas[antes:]
        self.assertEqual({i for i, _ in restauracoes}, {self.raiz, elegivel})
        for instancia in (novo, externo):
            self.assertNaoTentou(instancia)
        self.assertFalse(any(i in (alterado_usuario, ja_normal) for i, _ in restauracoes))

    def test_restore_apos_raiz_encerrar_recupera_filho_identificado(self):
        filho = self.backend.adicionar(11, 110, 10, IDLE)
        self.controle.ciclo()
        self.backend.processos[10].vivo = False
        resultado = self.controle.restaurar()
        self.assertErroAlvo(resultado, self.raiz)
        self.assertEqual([x['pid'] for x in resultado['restaurados']], [11])
        self.assertEqual(self.backend.processos[11].prioridade, IDLE)
        self.assertIn(filho, self.controle.alterados)

    def test_restore_repetido_nao_altera_classes_ja_restauradas(self):
        self.backend.adicionar(11, 110, 10, BELOW_NORMAL)
        self.controle.ciclo()
        primeiro = self.controle.restaurar()
        antes = len(self.backend.tentativas)
        segundo = self.controle.restaurar()
        self.assertEqual(len(primeiro['restaurados']), 2)
        self.assertEqual(segundo['restaurados'], [])
        self.assertEqual(segundo['erros'], [])
        self.assertEqual(len(self.backend.tentativas), antes)
        self.assertEqual(self.backend.handles, [])


if __name__ == '__main__':
    unittest.main()