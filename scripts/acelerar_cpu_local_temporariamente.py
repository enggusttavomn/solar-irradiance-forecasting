"""Preferencia por desempenho na tomada e prioridade High na arvore local.

Restaura ajustes ao encerrar, pausar ou desconectar da tomada. Nenhuma fonte,
thread de calculo, afinidade, precisao, GPU ou processo externo e alterado.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import ctypes
from ctypes import wintypes as w
from pathlib import Path
import signal
import time
import uuid

from scripts import priorizar_treinamentos as prioridade
from scripts.json_atomico import salvar_json
from scripts.retomar_historico_apos_calendario import (
    Windows as Consulta, Instancia as Identidade, ler, digest, local, Bloqueio, agora,
)
from scripts.coordenar_quantizacao_historica_replay_isolado_v1 import conferir_recibo

RAIZ = Path(__file__).resolve().parents[1]
REL = RAIZ / 'relatorios/quantizacao_todos_modelos_20260929'
SUB = '54533251-82be-4824-96c1-47b60b740d00'
EPP = '36687f9e-e3a5-4dbf-b1dc-15eb381c6863'


class GUID(ctypes.Structure):
    _fields_ = [('a', w.DWORD), ('b', w.WORD), ('c', w.WORD), ('d', w.BYTE * 8)]

    @classmethod
    def de(cls, s):
        return cls.from_buffer_copy(uuid.UUID(s).bytes_le)

    def texto(self):
        return str(uuid.UUID(bytes_le=bytes(self)))


class Energia:
    class Estado(ctypes.Structure):
        _fields_ = [('ac', w.BYTE), ('flags', w.BYTE), ('percent', w.BYTE),
                    ('economia', w.BYTE), ('vida', w.DWORD), ('total', w.DWORD)]

    def __init__(self):
        self.p = ctypes.WinDLL('powrprof')
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.p.PowerGetActiveScheme.argtypes = [w.HKEY, ctypes.POINTER(ctypes.POINTER(GUID))]
        self.p.PowerGetActiveScheme.restype = w.DWORD
        self.k.LocalFree.argtypes = [w.HLOCAL]
        self.k.LocalFree.restype = w.HLOCAL
        self.k.GetSystemPowerStatus.argtypes = [ctypes.POINTER(self.Estado)]
        self.k.GetSystemPowerStatus.restype = w.BOOL
        for nome in ('PowerReadACValueIndex', 'PowerReadDCValueIndex'):
            f = getattr(self.p, nome)
            f.argtypes = [w.HKEY, ctypes.POINTER(GUID), ctypes.POINTER(GUID),
                          ctypes.POINTER(GUID), ctypes.POINTER(w.DWORD)]
            f.restype = w.DWORD
        self.p.PowerWriteACValueIndex.argtypes = [w.HKEY, ctypes.POINTER(GUID),
            ctypes.POINTER(GUID), ctypes.POINTER(GUID), w.DWORD]
        self.p.PowerWriteACValueIndex.restype = w.DWORD
        self.p.PowerSetActiveScheme.argtypes = [w.HKEY, ctypes.POINTER(GUID)]
        self.p.PowerSetActiveScheme.restype = w.DWORD

    @staticmethod
    def exigir(code):
        if code:
            raise ctypes.WinError(code)

    def na_tomada(self):
        status = self.Estado()
        if not self.k.GetSystemPowerStatus(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        if status.ac not in (0, 1):
            raise Bloqueio('Alimentacao eletrica indeterminada.')
        return bool(status.ac)

    def ativo(self):
        ponteiro = ctypes.POINTER(GUID)()
        self.exigir(self.p.PowerGetActiveScheme(None, ctypes.byref(ponteiro)))
        try:
            return ponteiro.contents.texto()
        finally:
            self.k.LocalFree(ctypes.cast(ponteiro, w.HLOCAL))

    def ler(self, scheme, *, bateria=False):
        plano, sub, setting, valor = GUID.de(scheme), GUID.de(SUB), GUID.de(EPP), w.DWORD()
        f = self.p.PowerReadDCValueIndex if bateria else self.p.PowerReadACValueIndex
        self.exigir(f(None, ctypes.byref(plano), ctypes.byref(sub), ctypes.byref(setting), ctypes.byref(valor)))
        return int(valor.value)

    def escrever(self, scheme, valor):
        plano, sub, setting = GUID.de(scheme), GUID.de(SUB), GUID.de(EPP)
        self.exigir(self.p.PowerWriteACValueIndex(None, ctypes.byref(plano),
            ctypes.byref(sub), ctypes.byref(setting), valor))

    def reaplicar(self, scheme):
        self.exigir(self.p.PowerSetActiveScheme(None, ctypes.byref(GUID.de(scheme))))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--recibo', type=Path, required=True)
    ap.add_argument('--recibo-sha256', required=True)
    ap.add_argument('--saida', type=Path, required=True)
    ap.add_argument('--source-sha256', required=True)
    ap.add_argument('--pid', type=int, required=True)
    ap.add_argument('--creation-time', required=True)
    ap.add_argument('--somente-conferir', action='store_true')
    args = ap.parse_args()
    if digest(__file__) != args.source_sha256:
        raise Bloqueio('Fonte operacional alterada.')
    r = conferir_recibo(args.recibo, args.recibo_sha256)
    fonte = Path(prioridade.__file__).resolve()
    if r['fontes_sha256'].get(str(fonte)) != digest(fonte):
        raise Bloqueio('Controlador de prioridade diferente do validado.')
    c = ler(REL / 'coordenacao_historica/status.json')
    if (c.get('etapa') in ('erro', 'pronto_para_revisao_visual')
            or c.get('coordenador_complementar', {}).get('recibo_sha256') != args.recibo_sha256):
        raise Bloqueio('Coordenador confirmado nao esta em execucao.')
    root = Identidade.de(c['identidade_coordenador'])
    solicitado = Identidade.de({'pid': args.pid, 'creation_time': args.creation_time})
    if root != solicitado:
        raise Bloqueio('Coordenador difere da identidade explicitamente autorizada.')
    consulta = Consulta()
    energia = Energia()
    out = local(args.saida)
    if not out.is_relative_to(REL):
        raise Bloqueio('Saida operacional fora dos relatorios.')
    try:
        if not consulta.vivo(root):
            raise Bloqueio('Coordenador nao esta vivo.')
        scheme = energia.ativo()
        ac, dc = energia.ler(scheme), energia.ler(scheme, bateria=True)
        if not energia.na_tomada() or not 0 <= ac <= 100:
            raise Bloqueio('Aceleracao exige alimentacao pela tomada e EPP valido.')
        if args.somente_conferir:
            print({'coordenador': asdict(root), 'plano': scheme, 'epp_ac': ac,
                   'epp_dc': dc, 'tomada': True, 'fonte': digest(__file__)}, flush=True)
            return

        class Backend(prioridade.Windows):
            def __init__(self):
                super().__init__()
                self.k.GetProcessId.argtypes = [w.HANDLE]
                self.k.GetProcessId.restype = w.DWORD

            def mapa(self):
                return consulta.mapa()

            def definir(self, handle, valor):
                if valor == prioridade.HIGH:
                    pid = int(self.k.GetProcessId(handle))
                    tempos = [w.FILETIME() for _ in range(4)]
                    if not pid or not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in tempos)):
                        raise ctypes.WinError(ctypes.get_last_error())
                    stamp = str((tempos[0].dwHighDateTime << 32) | tempos[0].dwLowDateTime)
                    state.setdefault('prioridades_antes_da_api', {}).setdefault(
                        f'{pid}_{stamp}', {'pid': pid, 'creation_time': stamp,
                                         'classe_original': self.prioridade(handle)})
                    state['intencao_prioridade'] = {'pid': pid, 'creation_time': stamp,
                                                   'classe_solicitada': valor}
                    salvar_json(state, out / 'estado.json')
                super().definir(handle, valor)

        # Somente constantes deste processo; arquivo original permanece intacto.
        anterior_classe = prioridade.ABOVE_NORMAL
        prioridade.ABOVE_NORMAL = prioridade.HIGH
        prioridade.PRIORIDADES_INFERIORES = {*prioridade.PRIORIDADES_INFERIORES, anterior_classe}
        controller = prioridade.Controlador(prioridade.Instancia(root.pid, root.creation_time), Backend())
        parar = False

        def solicitar_parada(*_):
            nonlocal parar
            parar = True

        for sig in {signal.SIGINT, signal.SIGTERM, getattr(signal, 'SIGBREAK', signal.SIGINT)}:
            signal.signal(sig, solicitar_parada)
        out.mkdir(parents=True, exist_ok=False)
        state = {'etapa': 'PREPARADO', 'utc': agora(), 'coordenador': asdict(root),
                 'observador': asdict(consulta.identificar(__import__('os').getpid())),
                 'plano_original': scheme, 'epp_ac_original': ac, 'epp_dc_original': dc,
                 'epp_ac_solicitado': 0, 'prioridade_solicitada': 'High',
                 'fonte_sha256': digest(__file__), 'fontes_cientificas_alteradas': False}
        salvar_json(state, out / 'estado.json')
        mudou = False
        try:
            if (not consulta.vivo(root) or not energia.na_tomada()
                    or energia.ativo() != scheme or energia.ler(scheme) != ac):
                raise Bloqueio('Energia mudou antes da ativacao.')
            if ac:
                # Registrar intencao antes da API para permitir recuperacao apos queda.
                state.update(etapa='ENERGIA_WRITE_INTENT', atualizado_em_utc=agora())
                salvar_json(state, out / 'estado.json')
                energia.escrever(scheme, 0)
                mudou = True
                energia.reaplicar(scheme)
            if energia.ler(scheme) != 0 or energia.ler(scheme, bateria=True) != dc:
                raise Bloqueio('Windows nao confirmou a preferencia por desempenho.')
            while not parar and not (out / 'parar_aceleracao').exists():
                if not energia.na_tomada() or not consulta.vivo(root):
                    break
                current = ler(REL / 'coordenacao_historica/status.json')
                if (Identidade.de(current['identidade_coordenador']) != root
                        or current.get('etapa') in ('erro', 'pronto_para_revisao_visual')
                        or local(r['parada']).exists()):
                    break
                state.update(etapa='ATIVA', atualizado_em_utc=agora(),
                             ultimo_ciclo=controller.ciclo(), epp_ac_efetivo=energia.ler(scheme))
                state['prioridades_originais'] = [
                    {**asdict(i), 'classe': valor}
                    for i, valor in controller.alterados.items()]
                salvar_json(state, out / 'estado.json')
                print({'etapa': 'ATIVA', 'utc': state['atualizado_em_utc'],
                       'epp_ac': state['epp_ac_efetivo'], 'ciclo': state['ultimo_ciclo']}, flush=True)
                for _ in range(10):
                    if parar or (out / 'parar_aceleracao').exists():
                        break
                    time.sleep(1)
        finally:
            try:
                state['restauracao_prioridades'] = controller.restaurar()
            finally:
                if mudou:
                    if energia.ler(scheme) == 0:
                        energia.escrever(scheme, ac)
                        if energia.ativo() == scheme:
                            energia.reaplicar(scheme)
                        state['epp_restaurado'] = energia.ler(scheme) == ac
                    else:
                        state['epp_restaurado'] = 'Alteracao externa preservada.'
                state.update(etapa='ENCERRADA', atualizado_em_utc=agora())
                salvar_json(state, out / 'estado.json')
    finally:
        consulta.fechar()


if __name__ == '__main__':
    main()
