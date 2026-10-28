'''Travas de execucao e processos filhos contidos, sem encerrar processos encontrados.'''
from __future__ import annotations

from contextlib import AbstractContextManager
import ctypes
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import signal
import subprocess
import time


class ExecucaoOcupada(RuntimeError):
    pass


if os.name == 'nt':
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenProcess.restype = w.HANDLE
    k.GetCurrentProcess.argtypes = []
    k.GetCurrentProcess.restype = w.HANDLE
    k.CloseHandle.argtypes = [w.HANDLE]
    k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
    k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
    k.CreateToolhelp32Snapshot.argtypes = [w.DWORD, w.DWORD]
    k.CreateToolhelp32Snapshot.restype = w.HANDLE
    k.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD]
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.TerminateJobObject.argtypes = [w.HANDLE, w.UINT]
    k.QueryInformationJobObject.argtypes = [w.HANDLE, ctypes.c_int, ctypes.c_void_p, w.DWORD, ctypes.c_void_p]
    k.OpenThread.argtypes = [w.DWORD, w.BOOL, w.DWORD]
    k.OpenThread.restype = w.HANDLE
    k.ResumeThread.argtypes = [w.HANDLE]
    k.ResumeThread.restype = w.DWORD

    class UnicodeStringSistema(ctypes.Structure):
        _fields_ = [('length', w.USHORT), ('maximum_length', w.USHORT),
                    ('buffer', ctypes.c_void_p)]

    class ProcessoSistemaPrefixo(ctypes.Structure):
        # SYSTEM_PROCESS_INFORMATION, prefixo ate ParentProcessId.
        # ABI documentada pelo LLVM: CreateTime32, ImageName56, PID80(x64)/68(x86).
        _fields_ = [('next_offset', w.ULONG), ('threads', w.ULONG),
                    ('reserved', ctypes.c_int64 * 3), ('creation_time', ctypes.c_int64),
                    ('user_time', ctypes.c_int64), ('kernel_time', ctypes.c_int64),
                    ('image', UnicodeStringSistema), ('priority', w.LONG),
                    ('pid', w.HANDLE), ('ppid', w.HANDLE)]

    class ProcessoEntrada(ctypes.Structure):
        _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('pid', w.DWORD),
                    ('heap', ctypes.c_size_t), ('module', w.DWORD), ('threads', w.DWORD),
                    ('ppid', w.DWORD), ('priority', w.LONG), ('flags', w.DWORD), ('exe', w.WCHAR * 260)]

    class ThreadEntrada(ctypes.Structure):
        _fields_ = [('dwSize', w.DWORD), ('cntUsage', w.DWORD), ('tid', w.DWORD),
                    ('pid', w.DWORD), ('priority', w.LONG), ('delta', w.LONG), ('flags', w.DWORD)]

    class Limites(ctypes.Structure):
        _fields_ = [('process_time', ctypes.c_int64), ('job_time', ctypes.c_int64), ('flags', w.DWORD),
                    ('min_ws', ctypes.c_size_t), ('max_ws', ctypes.c_size_t), ('active', w.DWORD),
                    ('affinity', ctypes.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]

    class LimitesEstendidos(ctypes.Structure):
        _fields_ = [('basic', Limites), ('io', ctypes.c_uint64 * 6), ('process_memory', ctypes.c_size_t),
                    ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]

    class Contabilidade(ctypes.Structure):
        _fields_ = [('user', ctypes.c_int64), ('kernel', ctypes.c_int64), ('period_user', ctypes.c_int64),
                    ('period_kernel', ctypes.c_int64), ('faults', w.DWORD), ('total', w.DWORD),
                    ('active', w.DWORD), ('terminated', w.DWORD)]


def analisar_snapshot_identidades(buffer, tamanho):
    '''Parser fechado: buffer truncado/inconsistente nunca significa fila inativa.'''
    prefixo = ctypes.sizeof(ProcessoSistemaPrefixo)
    if not prefixo <= tamanho <= len(buffer):
        raise ValueError('Tamanho invalido do snapshot de processos.')
    esperado_pid = 80 if ctypes.sizeof(ctypes.c_void_p) == 8 else 68
    if (ProcessoSistemaPrefixo.creation_time.offset != 32
            or ProcessoSistemaPrefixo.image.offset != 56
            or ProcessoSistemaPrefixo.pid.offset != esperado_pid):
        raise ValueError('ABI do snapshot de processos nao reconhecida.')
    offset, resultado = 0, {}
    while True:
        if offset + prefixo > tamanho:
            raise ValueError('Snapshot de processos truncado.')
        registro = ProcessoSistemaPrefixo.from_buffer_copy(buffer, offset)
        pid = int(registro.pid or 0)
        if pid in resultado:
            raise ValueError('PID duplicado no snapshot de processos.')
        resultado[pid] = {'pid': pid, 'creation_time': str(registro.creation_time)}
        passo = int(registro.next_offset)
        if passo == 0:
            return resultado
        if (passo < prefixo or passo % ctypes.alignment(ProcessoSistemaPrefixo)
                or offset + passo + prefixo > tamanho):
            raise ValueError('Deslocamento invalido no snapshot de processos.')
        offset += passo


def snapshot_identidades_windows():
    '''FILETIME exato sem OpenProcess; consulta somente usada depois de WinError5.

    Fontes primarias (consulta somente leitura):
    https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntquerysysteminformation
    https://openmp.llvm.org/doxygen/z__Windows__NT__util_8cpp_source.html
    O proprio processo certifica PID/FILETIME do layout.
    '''
    if os.name != 'nt':
        raise OSError('Snapshot NT disponivel somente no Windows.')
    nt = ctypes.WinDLL('ntdll')
    consulta = nt.NtQuerySystemInformation
    consulta.argtypes = [w.ULONG, ctypes.c_void_p, w.ULONG, ctypes.POINTER(w.ULONG)]
    consulta.restype = w.LONG
    tamanho, limite = 256 * 1024, 32 * 1024 * 1024
    for _ in range(8):
        if tamanho > limite:
            raise ValueError('Snapshot de processos excedeu o limite de 32 MiB.')
        buffer = ctypes.create_string_buffer(tamanho)
        retorno = w.ULONG()
        status = int(consulta(5, buffer, tamanho, ctypes.byref(retorno))) & 0xffffffff
        if status in (0xc0000004, 0xc0000023, 0x80000005):
            tamanho = max(tamanho * 2, int(retorno.value))
            continue
        if status != 0:
            raise OSError(f'NtQuerySystemInformation falhou: NTSTATUS 0x{status:08x}')
        dados = analisar_snapshot_identidades(buffer.raw, int(retorno.value))
        tempos = [w.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(k.GetCurrentProcess(), *(ctypes.byref(t) for t in tempos)):
            raise ctypes.WinError(ctypes.get_last_error())
        criado = (tempos[0].dwHighDateTime << 32) | tempos[0].dwLowDateTime
        proprio = dados.get(os.getpid())
        if criado <= 0 or not proprio or proprio['creation_time'] != str(criado):
            raise ValueError('Snapshot NT nao reproduziu PID/FILETIME do proprio processo.')
        return dados
    raise RuntimeError('Snapshot de processos mudou de tamanho oito vezes; inspecao indeterminada.')


def identidade_snapshot_windows(pid):
    dados = snapshot_identidades_windows()
    registro = dados.get(int(pid))
    if registro is not None and int(registro['creation_time']) <= 0:
        raise ValueError(f'FILETIME indeterminado para o PID {pid}.')
    return registro


def _estatistica_posix(pid):
    try:
        fields = Path(f'/proc/{int(pid)}/stat').read_text().rsplit(') ', 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    return {'pid': int(pid), 'creation_time': fields[19], 'estado': fields[0], 'ppid': int(fields[1]),
            'grupo': int(fields[2]), 'sessao': int(fields[3])}


def _snapshot_posix():
    resultado = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        registro = _estatistica_posix(int(path.parent.name))
        if registro is not None:
            resultado[registro['pid']] = registro
    return resultado


def _sinalizar_instancia_posix(registro, sinal):
    abrir = getattr(os, 'pidfd_open', None)
    enviar = getattr(signal, 'pidfd_send_signal', None)
    if abrir is None or enviar is None:
        raise OSError('Encerramento seguro exige suporte a pidfd no Linux.')
    try:
        descritor = abrir(registro['pid'])
    except ProcessLookupError:
        return
    try:
        atual = _estatistica_posix(registro['pid'])
        if (atual is not None and atual['creation_time'] == registro['creation_time']
                and atual['estado'] not in ('Z', 'X')):
            # O descritor continua referindo-se a esta instancia mesmo que seu
            # numero PID seja reutilizado entre a verificacao e o sinal.
            try:
                enviar(descritor, sinal)
            except ProcessLookupError:
                pass
    finally:
        os.close(descritor)


def identidade(pid):
    '''Identifica uma instancia; PID reutilizado nao equivale ao processo original.'''
    pid = int(pid)
    if os.name != 'nt':
        registro = _estatistica_posix(pid)
        if registro is None or registro['estado'] in ('Z', 'X'):
            return None
        return {'pid': pid, 'creation_time': registro['creation_time']}
    handle = k.OpenProcess(0x1000 | 0x100000, False, pid)
    if not handle:
        codigo = ctypes.get_last_error()
        if codigo == 87:
            return None
        erro = ctypes.WinError(codigo)
        if codigo == 5:
            try:
                return identidade_snapshot_windows(pid)
            except (OSError, ValueError, AttributeError, RuntimeError) as fallback:
                erro.add_note(f'PID {pid}: snapshot sem OpenProcess nao confirmou sua identidade.')
                raise erro from fallback
        raise erro
    try:
        if k.WaitForSingleObject(handle, 0) == 0:
            return None
        times = [w.FILETIME() for _ in range(4)]
        if not k.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        return {'pid': pid, 'creation_time': str(created)}
    finally:
        k.CloseHandle(handle)


def mesma_instancia(registro):
    atual = identidade(registro['pid'])
    return atual is not None and (registro.get('creation_time') is None
                                  or str(atual['creation_time']) == str(registro['creation_time']))


def mapa_processos():
    if os.name != 'nt':
        resultado = {}
        for path in Path('/proc').glob('[0-9]*/stat'):
            try:
                fields = path.read_text().split(') ', 1)[1].split()
                resultado[int(path.parent.name)] = int(fields[1])
            except (FileNotFoundError, ProcessLookupError):
                pass
        return resultado
    snapshot = k.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    entrada = ProcessoEntrada()
    entrada.dwSize = ctypes.sizeof(entrada)
    resultado = {}
    try:
        for fn in (k.Process32FirstW, k.Process32NextW):
            fn.argtypes = [w.HANDLE, ctypes.POINTER(ProcessoEntrada)]
        ok = k.Process32FirstW(snapshot, ctypes.byref(entrada))
        while ok:
            resultado[int(entrada.pid)] = int(entrada.ppid)
            ok = k.Process32NextW(snapshot, ctypes.byref(entrada))
    finally:
        k.CloseHandle(snapshot)
    return resultado


def processos_da_fila_ativos(fila):
    '''Inspecao somente: inclui descendentes legados mesmo se o pai encerrou.'''
    raiz = fila.get('identidade_runner') or fila.get('identidade_coordenador')
    if raiz is None:
        raiz = {'pid': fila.get('pid_runner', fila.get('pid'))}
    registros = [raiz] + list(fila.get('processos', [])) + list(fila.get('processos_historico', []))
    if isinstance(fila.get('processo_filho'), dict):
        registros.append(fila['processo_filho'])
    mapa, ativos, visitados = mapa_processos(), {}, set()
    for registro in registros:
        if not registro.get('pid'):
            continue
        pid = int(registro['pid'])
        atual = identidade(pid)
        if atual and registro.get('creation_time') and str(atual['creation_time']) != str(registro['creation_time']):
            continue
        fila_pids = [pid]
        while fila_pids:
            p = fila_pids.pop()
            if p in visitados:
                continue
            visitados.add(p)
            existente = identidade(p)
            if existente:
                ativos[p] = existente
            fila_pids.extend(c for c, pai in mapa.items() if pai == p)
    return list(ativos.values())


class TravaDiretorio(AbstractContextManager):
    '''Lock persistente do sistema operacional; nunca excluir o arquivo de lock.'''
    def __init__(self, pasta):
        self.path = Path(pasta) / '.execucao.lock'
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        stream = self.path.open('a+b')
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            stream.close()
            raise ExecucaoOcupada(f'Outra execucao usa {self.path.parent}') from exc
        self.stream = stream
        stream.seek(1)
        stream.truncate()
        stream.write(json.dumps(identidade(os.getpid())).encode())
        stream.flush()
        return self

    def __exit__(self, *args):
        if self.stream is not None:
            self.stream.close()
            self.stream = None


class ProcessoProprio:
    '''Encerra apenas a arvore de instancias confirmadas; Windows usa um Job.'''
    def __init__(self, cmd, **kwargs):
        self.job = None
        self.processo = None
        if os.name != 'nt':
            self.processo = subprocess.Popen(cmd, start_new_session=True, **kwargs)
            # /proc ainda identifica um lider que saiu, mas nao foi reaproveitado
            # por poll/wait. Guarde a identidade antes de colher seu retorno.
            registro = _estatistica_posix(self.processo.pid)
            self._criacao_sessao_posix = registro['creation_time'] if registro else None
            self._instancias_posix = {self.processo.pid: self._criacao_sessao_posix}
            self._sessao_posix_encerrada = False
        else:
            self.job = k.CreateJobObjectW(None, None)
            if not self.job:
                raise ctypes.WinError(ctypes.get_last_error())
            limite = LimitesEstendidos()
            limite.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            try:
                if not k.SetInformationJobObject(self.job, 9, ctypes.byref(limite), ctypes.sizeof(limite)):
                    raise ctypes.WinError(ctypes.get_last_error())
                # Suspenso ate entrar no Job: nenhum filho pode escapar antes da associacao.
                self.processo = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW | 4, **kwargs)
                if not k.AssignProcessToJobObject(self.job, w.HANDLE(int(self.processo._handle))):
                    raise ctypes.WinError(ctypes.get_last_error())
                self._retomar_thread_inicial()
            except BaseException:
                if self.processo is not None:
                    self.processo.kill()
                    self.processo.wait(timeout=30)
                k.CloseHandle(self.job)
                self.job = None
                raise
        self.registro = identidade(self.processo.pid) or {
            'pid': self.processo.pid,
            'creation_time': self._criacao_sessao_posix if os.name != 'nt' else None}

    def _retomar_thread_inicial(self):
        snapshot = k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        entrada = ThreadEntrada()
        entrada.dwSize = ctypes.sizeof(entrada)
        tids = []
        try:
            for fn in (k.Thread32First, k.Thread32Next):
                fn.argtypes = [w.HANDLE, ctypes.POINTER(ThreadEntrada)]
            ok = k.Thread32First(snapshot, ctypes.byref(entrada))
            while ok:
                if entrada.pid == self.processo.pid:
                    tids.append(entrada.tid)
                ok = k.Thread32Next(snapshot, ctypes.byref(entrada))
        finally:
            k.CloseHandle(snapshot)
        if len(tids) != 1:
            raise RuntimeError('Processo recem-criado nao possui uma unica thread suspensa.')
        thread = k.OpenThread(2, False, tids[0])
        if not thread:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if k.ResumeThread(thread) == 0xffffffff:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            k.CloseHandle(thread)

    @property
    def pid(self):
        return self.processo.pid

    @property
    def returncode(self):
        return self.processo.returncode

    def _membros_posix(self, _confirmar_vazio=True):
        if self._sessao_posix_encerrada:
            return []
        if self._criacao_sessao_posix is None:
            raise RuntimeError('Identidade da sessao propria nao foi confirmada.')
        snapshot = _snapshot_posix()
        proprios = {pid: snapshot[pid] for pid, criado in self._instancias_posix.items()
                    if pid in snapshot and snapshot[pid]['creation_time'] == criado}
        while True:
            tamanho = len(proprios)
            sessoes_ancoradas = {r['sessao'] for r in proprios.values()}
            for pid, registro in snapshot.items():
                if pid in proprios or registro['grupo'] <= 0:
                    continue
                pai = proprios.get(registro['ppid'])
                filho_confirmado = (pai is not None and int(registro['creation_time'])
                                    >= int(pai['creation_time']))
                # Um PID+inicio proprio ainda presente (inclusive zombie) ancora
                # a identidade da sessao. So o numero SID nao prova propriedade:
                # ele pode ter sido reciclado entre consultas.
                mesma_sessao_ancorada = (registro['sessao'] in sessoes_ancoradas
                                        and int(registro['creation_time'])
                                        >= int(self._criacao_sessao_posix))
                if filho_confirmado or mesma_sessao_ancorada:
                    proprios[pid] = registro
            if len(proprios) == tamanho:
                break
        self._instancias_posix.update({pid: r['creation_time'] for pid, r in proprios.items()})
        membros = [r for r in proprios.values() if r['estado'] not in ('Z', 'X')]
        if not membros and proprios and _confirmar_vazio:
            # A enumeracao de /proc pode anteceder o ultimo fork do lider. Ele
            # agora esta zombie e ainda ancora a sessao: observe outra vez antes
            # de declarar que nao deixou descendentes vivos.
            return self._membros_posix(_confirmar_vazio=False)
        if not membros:
            # Depois de vazia, a sessao nunca volta a ser considerada nossa.
            self._sessao_posix_encerrada = True
        return membros

    def ativos(self):
        if os.name == 'nt':
            if self.job is None:
                return 0
            conta = Contabilidade()
            if not k.QueryInformationJobObject(self.job, 1, ctypes.byref(conta), ctypes.sizeof(conta), None):
                raise ctypes.WinError(ctypes.get_last_error())
            return int(conta.active)
        return len(self._membros_posix())

    def poll(self):
        if os.name != 'nt':
            if self.processo.returncode is None:
                if not all(hasattr(os, nome) for nome in ('waitid', 'WNOWAIT')):
                    raise OSError('Inspecao segura exige waitid/WNOWAIT no Linux.')
                try:
                    saida = os.waitid(os.P_PID, self.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
                except ChildProcessError as exc:
                    raise RuntimeError('Lider proprio foi colhido fora de ProcessoProprio.') from exc
                if saida is None:
                    self._membros_posix()
                    return None
            # Descubra orfaos enquanto o lider, mesmo zombie, ainda ancora seu
            # PID/SID. Popen.poll colhe o lider e pode liberar esses numeros.
            membros = self._membros_posix()
            retorno = self.processo.poll()
            return retorno if retorno is not None and not membros else None
        retorno = self.processo.poll()
        return retorno if retorno is not None and self.ativos() == 0 else None

    def encerrar(self):
        if os.name == 'nt':
            if self.job is not None:
                # O contador do Job pode zerar antes do sinal de saida do ultimo processo.
                # Guardamos suas identidades ANTES de pedir o encerramento e esperamos ambos.
                class ListaPids(ctypes.Structure):
                    _fields_ = [('assigned', w.DWORD), ('count', w.DWORD), ('pids', ctypes.c_size_t * 4096)]
                lista = ListaPids()
                if not k.QueryInformationJobObject(self.job, 3, ctypes.byref(lista), ctypes.sizeof(lista), None):
                    raise ctypes.WinError(ctypes.get_last_error())
                recibos = [identidade(pid) for pid in lista.pids[:lista.count]]
                recibos = [r for r in recibos if r is not None]
                if self.ativos() and not k.TerminateJobObject(self.job, 1):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.processo.wait(timeout=30)
                limite = time.monotonic() + 30
                while (self.ativos() or any(mesma_instancia(r) for r in recibos)) and time.monotonic() < limite:
                    time.sleep(.05)
                if self.ativos() or any(mesma_instancia(r) for r in recibos):
                    raise RuntimeError('Arvore propria nao encerrou dentro de 30 segundos.')
                k.CloseHandle(self.job)
                self.job = None
        else:
            limite = time.monotonic() + 30
            membros = self._membros_posix()
            while membros:
                # Primeiro os descendentes mais novos. O lider so e colhido
                # depois da arvore vazia, conservando sua ancora de identidade.
                for registro in sorted(membros, key=lambda r: int(r['creation_time']), reverse=True):
                    _sinalizar_instancia_posix(registro, signal.SIGKILL)
                if time.monotonic() >= limite:
                    raise RuntimeError('Arvore propria nao encerrou dentro de 30 segundos.')
                time.sleep(.05)
                membros = self._membros_posix()
            self.processo.wait(timeout=max(0, limite - time.monotonic()))

    def fechar(self):
        self.encerrar()
