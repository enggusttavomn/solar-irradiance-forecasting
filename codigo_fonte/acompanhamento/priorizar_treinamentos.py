"""Prioridade AboveNormal somente na arvore identificada de um coordenador.

Nao altera treino, dados, determinismo, threads, afinidade, plano de energia ou
processos externos. PID e FILETIME sao conferidos no mesmo handle da mutacao.
Fonte: https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-setpriorityclass
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes as w
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import time

from codigo_fonte.utilitarios.json_atomico import salvar_json
from codigo_fonte.acompanhamento.processos_quantizacao import TravaDiretorio, identidade, mapa_processos

ABOVE_NORMAL = 0x8000
NORMAL = 0x20
BELOW_NORMAL = 0x4000
IDLE = 0x40
HIGH = 0x80
REALTIME = 0x100
PRIORIDADES_INFERIORES = {NORMAL, BELOW_NORMAL, IDLE}
RAIZ = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Instancia:
    pid: int
    creation_time: str

    def __post_init__(self):
        if self.pid <= 0 or int(self.creation_time) <= 0:
            raise ValueError('PID e FILETIME positivos obrigatorios.')


class Windows:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Este auxiliar operacional requer Windows.')
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.k.OpenProcess.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
        self.k.GetProcessTimes.restype = w.BOOL
        self.k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.k.WaitForSingleObject.restype = w.DWORD
        self.k.GetPriorityClass.argtypes = [w.HANDLE]
        self.k.GetPriorityClass.restype = w.DWORD
        self.k.SetPriorityClass.argtypes = [w.HANDLE, w.DWORD]
        self.k.SetPriorityClass.restype = w.BOOL

    def mapa(self):
        return mapa_processos()

    def identidade(self, pid):
        dados = identidade(pid)
        return Instancia(int(dados['pid']), str(dados['creation_time'])) if dados else None

    def vivo(self, handle):
        resultado = self.k.WaitForSingleObject(handle, 0)
        if resultado == 0xffffffff:
            raise ctypes.WinError(ctypes.get_last_error())
        return resultado == 258

    @contextmanager
    def abrir(self, instancia):
        handle = self.k.OpenProcess(0x1000 | 0x200 | 0x100000, False, instancia.pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.vivo(handle):
                raise ProcessLookupError('Instancia encerrada.')
            tempos = [w.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in tempos)):
                raise ctypes.WinError(ctypes.get_last_error())
            criado = (tempos[0].dwHighDateTime << 32) | tempos[0].dwLowDateTime
            if str(criado) != instancia.creation_time:
                raise ProcessLookupError('PID reutilizado; nenhuma mutacao permitida.')
            yield handle
        finally:
            self.k.CloseHandle(handle)

    def prioridade(self, handle):
        resultado = int(self.k.GetPriorityClass(handle))
        if not resultado:
            raise ctypes.WinError(ctypes.get_last_error())
        return resultado

    def definir(self, handle, prioridade):
        if not self.k.SetPriorityClass(handle, prioridade):
            raise ctypes.WinError(ctypes.get_last_error())


class Controlador:
    def __init__(self, raiz, backend):
        self.raiz = raiz
        self.backend = backend
        self.alterados = {}

    def _arvore(self, erros):
        if self.backend.identidade(self.raiz.pid) != self.raiz:
            raise RuntimeError('Coordenador encerrou ou PID foi reutilizado.')
        mapa = self.backend.mapa()
        filhos = {}
        for pid, pai in mapa.items():
            if pid != pai:
                filhos.setdefault(pai, []).append(pid)
        cadeias = [(self.raiz,)]
        visitados = {self.raiz.pid}
        for cadeia in cadeias:
            for pid in filhos.get(cadeia[-1].pid, []):
                if pid in visitados:
                    continue
                visitados.add(pid)
                try:
                    atual = self.backend.identidade(pid)
                    # Reutilizacao do PID de um pai nao cria parentesco com filhos antigos.
                    if atual and int(atual.creation_time) >= int(cadeia[-1].creation_time):
                        cadeias.append(cadeia + (atual,))
                except (OSError, RuntimeError, ValueError) as exc:
                    erros.append({'pid': pid, 'erro': str(exc)})
        return cadeias

    def ciclo(self):
        resultado = {'alterados': [], 'erros': []}
        cadeias = self._arvore(resultado['erros'])
        resultado['instancias_observadas'] = [asdict(c[-1]) for c in cadeias]
        for cadeia in cadeias:
            alvo = cadeia[-1]
            try:
                # Todos os ancestrais permanecem abertos e identificados ate a mutacao.
                with ExitStack() as stack:
                    handles = [stack.enter_context(self.backend.abrir(i)) for i in cadeia]
                    if not all(self.backend.vivo(h) for h in handles):
                        raise ProcessLookupError('Ancestral/alvo encerrou antes da mutacao.')
                    # O PID de um filho pode ter sido reutilizado entre o primeiro
                    # snapshot e a consulta da identidade. Confirmar o PPID NOVAMENTE,
                    # com todas as instancias da cadeia abertas e ainda vivas.
                    mapa_fresco = self.backend.mapa()
                    if any(mapa_fresco.get(filho.pid) != pai.pid
                           for pai, filho in zip(cadeia, cadeia[1:])):
                        raise ProcessLookupError('Parentesco mudou; alvo fora da arvore.')
                    anterior = self.backend.prioridade(handles[-1])
                    if not all(self.backend.vivo(h) for h in handles):
                        raise ProcessLookupError('Ancestral/alvo encerrou antes de SetPriorityClass.')
                    if anterior in PRIORIDADES_INFERIORES:
                        self.backend.definir(handles[-1], ABOVE_NORMAL)
                        # A API confirmou a mutacao; registrar antes do readback.
                        self.alterados.setdefault(alvo, anterior)
                        if self.backend.prioridade(handles[-1]) != ABOVE_NORMAL:
                            raise RuntimeError('Windows nao confirmou a prioridade solicitada.')
                        resultado['alterados'].append({**asdict(alvo), 'anterior': anterior,
                                                       'atual': ABOVE_NORMAL})
            except (OSError, RuntimeError, ValueError) as exc:
                resultado['erros'].append({**asdict(alvo), 'erro': str(exc)})
        return resultado

    def restaurar(self):
        resultado = {'restaurados': [], 'erros': []}
        for alvo, anterior in self.alterados.items():
            try:
                with self.backend.abrir(alvo) as handle:
                    if self.backend.vivo(handle) and self.backend.prioridade(handle) == ABOVE_NORMAL:
                        self.backend.definir(handle, anterior)
                        resultado['restaurados'].append({**asdict(alvo), 'atual': anterior})
            except (OSError, RuntimeError, ValueError) as exc:
                resultado['erros'].append({**asdict(alvo), 'erro': str(exc)})
        return resultado


def agora():
    return datetime.now(timezone.utc).isoformat()


def pasta_local(path):
    pasta = Path(path).resolve()
    if not pasta.is_relative_to(RAIZ):
        raise ValueError('Registros operacionais devem ficar no projeto.')
    return pasta


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pid', required=True, type=int)
    ap.add_argument('--creation-time', required=True)
    ap.add_argument('--saida', required=True, type=Path)
    ap.add_argument('--coordenacao', type=Path, default=RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929/coordenacao_historica/status.json')
    ap.add_argument('--intervalo', type=float, default=30)
    args = ap.parse_args()
    if not 5 <= args.intervalo <= 60:
        ap.error('Intervalo deve ficar entre 5 e 60 segundos.')
    raiz = Instancia(args.pid, args.creation_time)
    status_coord = json.loads(args.coordenacao.read_text(encoding='utf-8'))
    if status_coord.get('identidade_coordenador') != asdict(raiz):
        raise RuntimeError('A identidade solicitada nao corresponde ao coordenador registrado.')
    pasta = pasta_local(args.saida)
    controlador = Controlador(raiz, Windows())
    parar = False

    def pedir_parada(*_):
        nonlocal parar
        parar = True

    for sig in (signal.SIGINT, signal.SIGTERM, getattr(signal, 'SIGBREAK', signal.SIGINT)):
        signal.signal(sig, pedir_parada)
    eventos = []
    iniciado = agora()
    estado = {'coordenador': asdict(raiz), 'observador': identidade(os.getpid()),
              'iniciado_em_utc': iniciado, 'classe_solicitada': ABOVE_NORMAL,
              'intervalo_segundos': args.intervalo, 'eventos': eventos,
              'fontes_cientificas_modificadas': False}
    with TravaDiretorio(pasta):
        try:
            while not parar and not (pasta / 'parar_prioridade').exists():
                try:
                    ciclo = controlador.ciclo()
                except RuntimeError as exc:
                    estado['motivo_fim'] = str(exc)
                    break
                estado['ultimo_ciclo'] = ciclo
                if ciclo['alterados'] or ciclo['erros']:
                    eventos.append({'utc': agora(), **ciclo})
                estado.update(etapa='ativa', atualizado_em_utc=agora(),
                              total_instancias_alteradas=len(controlador.alterados))
                salvar_json(estado, pasta / 'prioridade.json')
                print(json.dumps({'utc': estado['atualizado_em_utc'], **ciclo}), flush=True)
                limite = time.monotonic() + args.intervalo
                while not parar and time.monotonic() < limite and not (pasta / 'parar_prioridade').exists():
                    time.sleep(min(1, max(0, limite - time.monotonic())))
        finally:
            estado['restauracao'] = controlador.restaurar()
            estado.update(etapa='encerrada', atualizado_em_utc=agora())
            salvar_json(estado, pasta / 'prioridade.json')


if __name__ == '__main__':
    main()