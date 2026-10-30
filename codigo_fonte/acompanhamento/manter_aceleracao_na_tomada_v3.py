"""Supervisiona um guard High conhecido; relanca apenas apos bateria observada.

Somente stdlib e consultas nativas. Nao altera o guard, os motores ou contratos.
Qualquer evidencia ambigua encerra a supervisao sem repetir um Popen.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import ctypes
from ctypes import wintypes as w
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import re
import signal
import sys
import time
import uuid

from codigo_fonte.utilitarios.json_atomico import salvar_json
from codigo_fonte.acompanhamento.retomar_historico_apos_calendario import Windows as Consulta, Instancia, Bloqueio, local, digest, ler, agora

RAIZ = Path(__file__).resolve().parents[2]
REL = Path('resultados/relatorios/quantizacao_todos_modelos_20260929')
CHILD_SHA = '02b597a9a13e5f15a3f62c0b46b8d0da4766fa8778331fcada02e6ee2b706446'
OLD_SHA = '54433ab91daf50faed29f985046e8b4f4dad2af27035fa4b738d368e33e12810'
ROOT_SHA = '9bd045a68da175b1dacddb1ddd806e3f739d52203f02ab477ad4802dd68b5aea'
MODULO = 'codigo_fonte.acompanhamento.acelerar_cpu_local_temporariamente'
TERMINAIS = {'erro', 'pronto_para_revisao_visual', 'concluida', 'encerrada', 'interrompida'}


def exclusivo(path, dados):
    """Reserva persistente: nunca sobrescreve nem reaproveita uma ativacao."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(dados, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


class Journal:
    def __init__(self, path):
        self.path = Path(path)

    def gravar(self, dados):
        salvar_json(dados, self.path, tentativas=40, intervalo=0.25)


@dataclass(frozen=True)
class Config:
    raiz: Path
    own_source: Path
    own_sha: str
    child_source: Path
    child_sha: str
    recibo: Path
    recibo_sha: str
    root_recibo: Path
    root_recibo_sha: str
    root: Instancia
    saida: Path
    adotar: Path
    adotar_child: Instancia
    adotar_launcher: Instancia

    @property
    def rel(self):
        return self.raiz / REL

    @property
    def python(self):
        return self.raiz / '.venv-baselines-gpu-20260912/Scripts/python.exe'

    @property
    def coord_status(self):
        return self.rel / 'coordenacao_historica/status.json'

    @property
    def canonico(self):
        return self.rel / 'supervisao_na_tomada_v3' / f'{self.root.pid}_{self.root.creation_time}'

    def comando(self, controle):
        return [str(self.python), '-B', '-X', 'utf8', '-m', MODULO,
                '--recibo', str(self.recibo), '--recibo-sha256', self.recibo_sha,
                '--saida', str(controle), '--source-sha256', self.child_sha,
                '--pid', str(self.root.pid), '--creation-time', self.root.creation_time]

    def conferir_fontes(self):
        for path, sha in ((self.own_source, self.own_sha), (self.child_source, self.child_sha),
                          (self.recibo, self.recibo_sha), (self.root_recibo, self.root_recibo_sha)):
            if not re.fullmatch('[0-9a-f]{64}', sha) or digest(path) != sha:
                raise Bloqueio(f'Fonte ou recibo alterado: {path}')

    def conferir_caminhos(self):
        for path in (self.own_source, self.child_source, self.recibo, self.root_recibo,
                     self.saida, self.adotar, self.python):
            if local(path, self.raiz) != path:
                raise Bloqueio('Caminho deve ser local, absoluto e canonico.')
        if (not self.saida.is_relative_to(self.rel) or not self.adotar.is_relative_to(self.rel)
                or self.saida == self.adotar or self.saida.is_relative_to(self.adotar)
                or self.adotar.is_relative_to(self.saida)):
            raise Bloqueio('Saida e adocao devem ser pastas distintas nos relatorios.')
        for pasta in (self.rel, self.saida, self.adotar, self.canonico):
            resolvida = pasta.resolve()
            if (resolvida != pasta or not resolvida.is_relative_to(self.raiz.resolve())
                    or not resolvida.is_relative_to(self.rel.resolve())):
                raise Bloqueio('Diretorio operacional redirecionado ou fora dos relatorios.')
        if not self.python.is_file():
            raise Bloqueio('Python local aprovado ausente.')
        for i in (self.root, self.adotar_child, self.adotar_launcher):
            Instancia.de(asdict(i))
        if len({self.root.pid, self.adotar_child.pid, self.adotar_launcher.pid}) != 3:
            raise Bloqueio('Coordenador, guard e launcher devem ser distintos.')


class Energia:
    class Estado(ctypes.Structure):
        _fields_ = [('ac', w.BYTE), ('flags', w.BYTE), ('percent', w.BYTE),
                    ('economia', w.BYTE), ('vida', w.DWORD), ('total', w.DWORD)]

    def __init__(self):
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.k.GetSystemPowerStatus.argtypes = [ctypes.POINTER(self.Estado)]
        self.k.GetSystemPowerStatus.restype = w.BOOL

    def na_tomada(self):
        status = self.Estado()
        if not self.k.GetSystemPowerStatus(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        if status.ac not in (0, 1):
            raise Bloqueio('Alimentacao indeterminada; nao relancar.')
        return bool(status.ac)


class Windows(Consulta):
    class Unicode(ctypes.Structure):
        _fields_ = [('length', w.USHORT), ('maximum_length', w.USHORT), ('buffer', ctypes.c_void_p)]

    class Entrada(ctypes.Structure):
        _fields_ = [('size', w.DWORD), ('usage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('ppid', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD),
                    ('exe', w.WCHAR * 260)]

    def comando(self, i):
        if self.identificar(i.pid) != i or not self.vivo(i):
            raise Bloqueio('Processo mudou durante consulta de CLI.')
        buffer = ctypes.create_string_buffer(131072)
        n = w.ULONG()
        code = int(self.nt.NtQueryInformationProcess(
            self.handles[i], 60, buffer, len(buffer), ctypes.byref(n))) & 0xffffffff
        if code or not ctypes.sizeof(self.Unicode) <= n.value <= len(buffer):
            raise Bloqueio(f'CLI nativa nao consultavel: NTSTATUS 0x{code:08x}.')
        valor = self.Unicode.from_buffer_copy(buffer)
        base = ctypes.addressof(buffer)
        if (valor.length % 2 or not valor.length or not valor.buffer
                or valor.length > valor.maximum_length
                or not base <= valor.buffer <= base + n.value - valor.length):
            raise Bloqueio('Buffer de CLI nativa invalido.')
        cmd = ctypes.wstring_at(valor.buffer, valor.length // 2)
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.CommandLineToArgvW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(w.LPWSTR)
        self.k.LocalFree.argtypes = [w.HLOCAL]
        self.k.LocalFree.restype = w.HLOCAL
        count = ctypes.c_int()
        argv = shell.CommandLineToArgvW(cmd, ctypes.byref(count))
        if not argv:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            tokens = [argv[j] for j in range(count.value)]
        finally:
            self.k.LocalFree(ctypes.cast(argv, w.HLOCAL))
        if not self.vivo(i):
            raise Bloqueio('Processo encerrou durante consulta de CLI.')
        return tokens

    def guardas(self):
        """Scan apenas pre-adocao/prelaunch; consultas fortes filtradas por python."""
        k = self.k
        k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
        k.CreateToolhelp32Snapshot.restype = w.HANDLE
        for name in ('Process32FirstW', 'Process32NextW'):
            f = getattr(k, name)
            f.argtypes = [w.HANDLE, ctypes.POINTER(self.Entrada)]
            f.restype = w.BOOL
        handle = k.CreateToolhelp32Snapshot(2, 0)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        resultado = set()
        try:
            entry = self.Entrada(); entry.size = ctypes.sizeof(entry)
            ok = k.Process32FirstW(handle, ctypes.byref(entry))
            while ok:
                if str(entry.exe).lower() in ('python.exe', 'pythonw.exe'):
                    i = self.identificar(int(entry.pid))
                    if i is not None:
                        tokens = self.comando(i)
                        if any(t == MODULO or Path(t).name.lower() == 'acelerar_cpu_local_temporariamente.py'
                               for t in tokens):
                            resultado.add(i)
                ok = k.Process32NextW(handle, ctypes.byref(entry))
            if ctypes.get_last_error() != 18:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            k.CloseHandle(handle)
        return resultado

    def below_normal(self):
        self.k.SetPriorityClass.argtypes = [w.HANDLE, w.DWORD]
        self.k.SetPriorityClass.restype = w.BOOL
        if not self.k.SetPriorityClass(self.k.GetCurrentProcess(), 0x4000):
            raise ctypes.WinError(ctypes.get_last_error())


class Supervisor:
    def __init__(self, config, backend, energia, journal=None, observador=None):
        self.c, self.backend, self.energia = config, backend, energia
        self.journal = journal or Journal(config.saida / 'journal.json')
        self.estado = {'versao': 1, 'etapa': 'PRECHECK', 'root': asdict(config.root),
                       'fonte_sha256': config.own_sha, 'child_source_sha256': config.child_sha,
                       'tentativas_popen': 0, 'iniciado_em_utc': agora()}
        if observador is not None:
            self.estado['observador'] = asdict(Instancia.de(asdict(observador)))
        self.child = self.launcher = self.controle = self.stderr = None
        self.bateria_observada = False
        self.falhou = self.terminou = False
        self.processo = None
        self.confirmacao_limite = None
        self.paradas = []
        self.controles = []
        self.owned = False
        self.journal_started = False
        self.ultimo_heartbeat = time.monotonic()
        self.sinal_parada = False

    def registrar(self, etapa, **campos):
        novo = {**self.estado, **campos, 'etapa': etapa, 'atualizado_em_utc': agora()}
        self.journal.gravar(novo)
        self.estado = novo
        self.journal_started = True

    def conferir_root(self):
        if self.backend.identificar(self.c.root.pid) != self.c.root or not self.backend.vivo(self.c.root):
            raise Bloqueio('Coordenador encerrou ou mudou de identidade.')
        s = ler(self.c.coord_status)
        if Instancia.de(s.get('identidade_coordenador')) != self.c.root or s.get('etapa') in TERMINAIS:
            raise Bloqueio('Coordenador mudou, encerrou, falhou ou chegou a revisao visual.')
        for key, path, sha in (('coordenador_complementar', self.c.recibo, self.c.recibo_sha),
                               ('retomada_apos_reinicio', self.c.root_recibo, self.c.root_recibo_sha)):
            m = s.get(key, {})
            if m.get('recibo_sha256') != sha or local(m.get('recibo', ''), self.c.raiz) != path:
                raise Bloqueio('Metadados dos recibos do coordenador divergiram.')
        return s

    def parada_manual(self):
        if self.sinal_parada:
            return True
        paths = [*self.paradas, self.c.saida / 'parar_supervisao']
        paths.extend(p / 'parar_aceleracao' for p in self.controles)
        if self.controle is not None and self.controle not in self.controles:
            paths.append(self.controle / 'parar_aceleracao')
        return any(p.exists() for p in paths)

    def conferir_guardas(self, permitidos):
        guardas = self.backend.guardas()
        if guardas != set(permitidos):
            raise Bloqueio('Guard High desconhecido/ausente; novo lancamento proibido.')

    def estado_child(self):
        s = ler(self.controle / 'estado.json')
        if (Instancia.de(s.get('observador')) != self.child
                or Instancia.de(s.get('coordenador')) != self.c.root
                or s.get('fonte_sha256') != self.c.child_sha
                or s.get('prioridade_solicitada') != 'High'):
            raise Bloqueio('Estado do guard nao corresponde a instancia conhecida.')
        ciclo = s.get('ultimo_ciclo', {})
        if not isinstance(ciclo, dict):
            raise Bloqueio('Relatorio do ciclo de prioridade malformado.')
        erros = ciclo.get('erros', [])
        if not isinstance(erros, list):
            raise Bloqueio('Lista de erros do ciclo de prioridade malformada.')
        ignorados = list(getattr(self, 'erros_ciclo_mortos_ignorados', []))
        identidades = {Instancia.de(r) for r in ignorados}
        for erro in erros:
            alvo = Instancia.de(erro)
            if self.backend.vivo(alvo) is not False:
                raise Bloqueio('Guard informou erro em instancia viva ou indeterminada.')
            if alvo not in identidades:
                ignorados.append(dict(erro))
                identidades.add(alvo)
        # Somente memoria aqui; a evidência sai no heartbeat regular ja existente.
        self.erros_ciclo_mortos_ignorados = ignorados
        if not self.stderr.is_file() or self.stderr.stat().st_size:
            raise Bloqueio('Stderr do guard nao esta vazio.')
        return s

    def conferir_parentesco(self, child, launcher, controle):
        if (self.backend.identificar(child.pid) != child or self.backend.identificar(launcher.pid) != launcher
                or not self.backend.vivo(child) or not self.backend.vivo(launcher)
                or int(child.creation_time) <= int(launcher.creation_time)
                or self.backend.mapa().get(child.pid) != launcher.pid):
            raise Bloqueio('Guard/launcher sem identidade viva e parentesco confirmado.')
        esperado = self.c.comando(controle)
        root_program = Path(self.backend.programa(self.c.root)).resolve()
        for alvo in (child, launcher):
            argv = self.backend.comando(alvo)
            if argv != esperado:
                raise Bloqueio('CLI do guard/launcher divergente do comando fixo.')
        if (Path(self.backend.programa(launcher)).resolve() != self.c.python.resolve()
                or Path(self.backend.programa(child)).resolve()
                != root_program):
            raise Bloqueio('Executavel nativo do guard/launcher divergente.')
        if (self.backend.identificar(child.pid) != child or self.backend.identificar(launcher.pid) != launcher
                or not self.backend.vivo(child) or not self.backend.vivo(launcher)
                or self.backend.mapa().get(child.pid) != launcher.pid):
            raise Bloqueio('Parentesco/identidades mudaram depois das consultas de CLI.')

    def iniciar(self):
        try:
            self.c.conferir_caminhos(); self.c.conferir_fontes()
            old, new = ler(self.c.recibo), ler(self.c.root_recibo)
            if (old.get('aprovado') is not True or new.get('aprovado') is not True
                    or new.get('recibo_anterior', {}).get('sha256') != self.c.recibo_sha
                    or local(new.get('recibo_anterior', {}).get('path', ''), self.c.raiz) != self.c.recibo):
                raise Bloqueio('Recibos nao aprovados ou vinculo antigo divergente.')
            self.paradas = [local(r['parada'], self.c.raiz) for r in (old, new)]
            self.conferir_root()
            if (self.parada_manual() or (self.c.adotar / 'parar_aceleracao').exists()):
                raise Bloqueio('Pedido manual de parada vigente.')
            j = ler(self.c.adotar.parent / 'lancamento.json')
            if (j.get('etapa') != 'LAUNCH_CONFIRMED' or j.get('tentativas_popen') != 1
                    or j.get('fonte_sha256') != self.c.child_sha
                    or Instancia.de(j.get('coordenador')) != self.c.root
                    or Instancia.de(j.get('launcher')) != self.c.adotar_launcher
                    or j.get('comando') != self.c.comando(self.c.adotar)):
                raise Bloqueio('Journal de adocao divergente ou inconclusivo.')
            self.conferir_parentesco(self.c.adotar_child, self.c.adotar_launcher, self.c.adotar)
            self.conferir_guardas({self.c.adotar_child, self.c.adotar_launcher})
            self.child, self.launcher = self.c.adotar_child, self.c.adotar_launcher
            self.controle = self.c.adotar
            self.stderr = self.c.adotar.parent / 'observador.erro.log'
            s = self.estado_child()
            if s.get('etapa') != 'ATIVA':
                raise Bloqueio('Guard adotado nao esta ATIVA com stderr conhecido.')
            # Reservas persistentes + locks externos impedem outra saida/restart.
            self.c.saida.mkdir(parents=True, exist_ok=False)
            claim = {'root': asdict(self.c.root), 'saida': str(self.c.saida), 'utc': agora()}
            exclusivo(self.c.canonico / 'ativacao.json', claim)
            exclusivo(self.c.adotar / '.supervisor_adocao.json', claim)
            self.owned = True
            self.controles.append(self.controle)
            self.registrar('ADOTADO', child=asdict(self.child), launcher=asdict(self.launcher),
                           controle=str(self.controle), bateria_observada=False,
                           energia_ac=self.energia.na_tomada())
            return self.passo()
        except BaseException:
            self.falhou = True
            raise

    def confirmar_novo(self):
        if self.processo.poll() is not None:
            raise Bloqueio('Launcher encerrou antes da confirmacao; nao repetir.')
        if self.backend.identificar(self.launcher.pid) != self.launcher:
            raise Bloqueio('Launcher mudou antes da confirmacao.')
        if self.stderr.exists() and self.stderr.stat().st_size:
            raise Bloqueio('Novo guard informou erro; nao repetir.')
        p = self.controle / 'estado.json'
        if not p.exists():
            if time.monotonic() >= self.confirmacao_limite:
                raise Bloqueio('Guard nao confirmou estado no prazo; nao repetir.')
            return
        s = ler(p)
        if s.get('etapa') not in ('PREPARADO', 'ENERGIA_WRITE_INTENT', 'ATIVA', 'ENCERRADA'):
            raise Bloqueio('Novo guard informou etapa desconhecida.')
        if s.get('etapa') != 'ATIVA' and time.monotonic() >= self.confirmacao_limite:
            raise Bloqueio('Guard nao confirmou ATIVA no prazo; nao repetir.')
        i = Instancia.de(s.get('observador'))
        self.conferir_parentesco(i, self.launcher, self.controle)
        self.child = i
        s = self.estado_child()
        if s.get('etapa') == 'ENCERRADA':
            raise Bloqueio('Novo guard encerrou antes da confirmacao; nao repetir.')
        if s.get('etapa') == 'ATIVA':
            self.conferir_guardas({self.child, self.launcher})
            self.registrar('ATIVA', child=asdict(self.child), launcher=asdict(self.launcher), energia_ac=True)
            self.confirmacao_limite = None

    def lancar(self):
        self.c.conferir_fontes(); self.conferir_root()
        if self.parada_manual() or not self.energia.na_tomada():
            raise Bloqueio('Parada ou energia mudou antes do lancamento.')
        if self.backend.vivo(self.child) or self.backend.vivo(self.launcher):
            raise Bloqueio('Guard/launcher anterior ainda vivo; nao relancar.')
        self.conferir_guardas(set())
        epoch = self.c.saida / f'epoch_{self.estado["tentativas_popen"] + 1:04d}_{uuid.uuid4().hex}'
        epoch.mkdir(exist_ok=False)
        controle, out, err = epoch / 'controle', epoch / 'stdout.log', epoch / 'stderr.log'
        # Nunca tentar novamente se gravacao ou Popen for inconclusivo.
        self.registrar('LAUNCH_INTENT', comando=self.c.comando(controle), controle=str(controle),
                       stdout=str(out), stderr=str(err),
                       tentativas_popen=self.estado['tentativas_popen'] + 1, bateria_observada=False)
        self.controle, self.stderr = controle, err
        self.controles.append(controle)
        self.child = None
        # O journal pode ter levado tempo; rever sinais antes do unico Popen.
        self.conferir_root(); self.c.conferir_fontes()
        if self.parada_manual() or not self.energia.na_tomada():
            raise Bloqueio('Parada/root/energia mudou apos LAUNCH_INTENT; nao repetir.')
        self.conferir_guardas(set())
        self.processo = self.backend.lancar(self.c.comando(controle), out, err, self.c.raiz)
        self.launcher = self.backend.identificar(self.processo.pid)
        if self.launcher is None:
            raise Bloqueio('Popen sem identidade viva confirmada; nao repetir.')
        self.bateria_observada = False
        self.confirmacao_limite = time.monotonic() + 120
        self.registrar('CONFIRMANDO', launcher=asdict(self.launcher))

    def passo(self):
        if self.falhou:
            raise Bloqueio('Supervisor bloqueado; retry proibido.')
        if self.terminou:
            return False
        try:
            self.conferir_root()
            if self.parada_manual():
                self.terminou = True
                self.registrar('PARADA_MANUAL')
                return False
            ac = self.energia.na_tomada()
            if self.confirmacao_limite is not None:
                # Uma queda durante startup e ambigua: parar, nunca auto repetir.
                if not ac:
                    raise Bloqueio('Bateria durante confirmacao; nao repetir.')
                self.confirmar_novo()
                return True
            s = self.estado_child()
            alive = self.backend.vivo(self.child)
            if not ac and alive:
                self.bateria_observada = True
                self.registrar('AGUARDANDO_RESTAURACAO', bateria_observada=True, energia_ac=False)
                return True
            if alive:
                if s.get('etapa') not in ('ATIVA', 'ENCERRADA'):
                    raise Bloqueio('Estado inesperado no guard vivo.')
                if time.monotonic() - self.ultimo_heartbeat >= 15:
                    self.registrar(self.estado['etapa'], energia_ac=ac,
                                   bateria_observada=self.bateria_observada,
                                   erros_ciclo_mortos_ignorados=getattr(
                                       self, 'erros_ciclo_mortos_ignorados', []))
                    self.ultimo_heartbeat = time.monotonic()
                return True
            if (not self.bateria_observada or s.get('etapa') != 'ENCERRADA'
                    or not isinstance(s.get('restauracao_prioridades'), dict)
                    or s.get('epp_restaurado') not in (None, True)):
                raise Bloqueio('Morte/restore sem bateria observada e ENCERRADA confirmado.')
            erros = s['restauracao_prioridades'].get('erros')
            if not isinstance(erros, list):
                raise Bloqueio('Relatorio de restauracao sem erros explicitos.')
            mortos = []
            for erro in erros:
                alvo = Instancia.de(erro)
                if self.backend.vivo(alvo):
                    raise Bloqueio('Restauracao falhou em processo ainda vivo.')
                mortos.append(asdict(alvo))
            if mortos:
                self.registrar('RESTAURACAO_ALVOS_MORTOS', erros_restauracao_mortos=mortos)
            if self.backend.vivo(self.launcher):
                self.registrar('AGUARDANDO_LAUNCHER', bateria_observada=True, energia_ac=ac)
                return True
            if not ac:
                self.registrar('AGUARDANDO_TOMADA', bateria_observada=True, energia_ac=False)
                return True
            self.lancar()
            return True
        except BaseException:
            self.falhou = True
            raise

    def encerrar(self, motivo='Saida do supervisor'):
        """Somente stopfile da pasta conhecida; nenhum terminate/kill."""
        self.terminou = True
        if self.owned and self.controle is not None:
            self.controle.mkdir(parents=True, exist_ok=True)
            marker = self.controle / 'parar_aceleracao'
            if not marker.exists():
                exclusivo(marker, {'supervisor': str(self.c.saida), 'motivo': motivo, 'utc': agora()})
        if self.journal_started:
            self.registrar('BLOQUEADO' if self.falhou else 'ENCERRANDO', motivo=motivo)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for name in ('source-sha256', 'child-source-sha256', 'recibo-sha256', 'root-recibo-sha256',
                 'creation-time', 'adotar-creation-time', 'adotar-launcher-creation-time'):
        ap.add_argument('--' + name, required=True)
    for name in ('recibo', 'root-recibo', 'saida', 'adotar'):
        ap.add_argument('--' + name, type=Path, required=True)
    for name in ('pid', 'adotar-pid', 'adotar-launcher-pid'):
        ap.add_argument('--' + name, type=int, required=True)
    ap.add_argument('--below-normal', action='store_true')
    args = ap.parse_args()
    if (args.child_source_sha256 != CHILD_SHA or args.recibo_sha256 != OLD_SHA
            or args.root_recibo_sha256 != ROOT_SHA):
        raise Bloqueio('Somente fonte e recibos explicitamente congelados sao permitidos.')
    c = Config(RAIZ, Path(__file__).resolve(), args.source_sha256,
               RAIZ / 'codigo_fonte/acompanhamento/acelerar_cpu_local_temporariamente.py', args.child_source_sha256,
               local(args.recibo), args.recibo_sha256, local(args.root_recibo), args.root_recibo_sha256,
               Instancia.de({'pid': args.pid, 'creation_time': args.creation_time}),
               local(args.saida), local(args.adotar),
               Instancia.de({'pid': args.adotar_pid, 'creation_time': args.adotar_creation_time}),
               Instancia.de({'pid': args.adotar_launcher_pid, 'creation_time': args.adotar_launcher_creation_time}))
    # Validar junctions antes de qualquer lock/criacao de pasta operacional.
    c.conferir_caminhos()
    backend = Windows()
    proprio = backend.identificar(os.getpid())
    if proprio is None:
        backend.fechar()
        raise Bloqueio('Supervisor sem identidade nativa viva.')
    supervisor = Supervisor(c, backend, Energia(), observador=proprio)
    stopping = False

    def parar(*_):
        nonlocal stopping
        stopping = True
        supervisor.sinal_parada = True

    for sig in {signal.SIGINT, signal.SIGTERM, getattr(signal, 'SIGBREAK', signal.SIGINT)}:
        signal.signal(sig, parar)
    motivo = 'Coordenador/usuario encerrou supervisao'
    try:
        if args.below_normal:
            backend.below_normal()
        with ExitStack() as stack:
            stack.enter_context(backend.lock_observador(c.canonico))
            stack.enter_context(backend.lock_observador(c.adotar))
            try:
                ativo = supervisor.iniciar()
                while ativo and not stopping:
                    print({'etapa': supervisor.estado['etapa'], 'utc': agora()}, flush=True)
                    for _ in range(3):
                        if stopping:
                            break
                        time.sleep(1)
                    if not stopping:
                        ativo = supervisor.passo()
            except BaseException as exc:
                supervisor.falhou = True
                motivo = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                supervisor.encerrar(motivo)
                # Aguardar restauracao natural do guard, sem forcar nenhum PID.
                limite = time.monotonic() + 45
                while (supervisor.owned and supervisor.child is not None
                       and backend.vivo(supervisor.child)):
                    if time.monotonic() >= limite:
                        supervisor.registrar('RESTAURACAO_PENDENTE', motivo=motivo)
                        break
                    time.sleep(1)
    finally:
        backend.fechar()


if __name__ == '__main__':
    main()
