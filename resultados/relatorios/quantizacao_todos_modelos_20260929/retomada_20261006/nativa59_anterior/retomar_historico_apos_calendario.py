"""Espera a fila antiga encerrar e retoma uma vez, mediante manifesto aprovado.

Auxiliar operacional Windows: nao encerra processos, nao altera caches/fontes,
nao muda prioridade e nao cria Job Object. Um LAUNCH_INTENT incompleto bloqueia
novas tentativas: a janela Popen/journal exige reconciliacao humana se houver queda.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import ctypes
from ctypes import wintypes as w
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid

from scripts.json_atomico import salvar_json

RAIZ = Path(__file__).resolve().parents[1]
REL = Path('relatorios/quantizacao_todos_modelos_20260929')
PAPEIS = {'helper', 'tests_helper', 'coordenador', 'dispatcher', 'replay',
          'adapter', 'tests_adapter', 'json', 'processos', 'engine_quantizacao',
          'engine_multirresolucao', 'engine_estatistico', 'global', 'protocolo',
          'aprovacao_sazonal', 'test_receipt'}
COMANDO = ['-X', 'utf8', '-m', 'scripts.coordenar_quantizacao_historica',
           '--cpu-workers', '2', '--gpu-workers', '2']
FALHA_TECNICA = {'fase': 'refit', 'tarefa': 'monthly_1',
                'modelo': 'DilatedRNN', 'returncode': 1}


class Bloqueio(RuntimeError):
    """Evidencia insuficiente ou divergente; nunca autoriza novo Popen."""


def agora():
    return datetime.now(timezone.utc).isoformat()


def filetime_agora():
    return str(time.time_ns() // 100 + 116444736000000000)


def local(path, raiz=RAIZ):
    """Resolve somente o pai: DRM pode redirecionar uma folha PDF/PT/NPZ."""
    p = Path(path)
    if not p.is_absolute():
        p = raiz / p
    p = p.parent.resolve() / p.name
    if not p.is_relative_to(raiz.resolve()) or p.name in ('', '.', '..'):
        raise Bloqueio(f'Caminho fora do projeto: {path}')
    return p


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def ler(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@dataclass(frozen=True)
class Instancia:
    pid: int
    creation_time: str

    @classmethod
    def de(cls, valor):
        if not isinstance(valor, dict):
            raise Bloqueio('Identidade ausente.')
        pid, stamp = valor.get('pid'), valor.get('creation_time')
        if type(pid) is not int or pid <= 0 or not isinstance(stamp, str) or not stamp.isdigit() or int(stamp) <= 0:
            raise Bloqueio('PID e FILETIME exatos e positivos obrigatorios.')
        return cls(pid, stamp)


class Manifesto:
    def __init__(self, dados, sha, raiz=RAIZ):
        self.dados, self.sha, self.raiz = dados, sha, raiz.resolve()
        if dados.get('versao') != 1 or dados.get('aprovado') is not True:
            raise Bloqueio('Manifesto v1 explicitamente aprovado obrigatorio.')
        if dados.get('cpu_workers') != 2 or dados.get('gpu_workers') != 2:
            raise Bloqueio('Retomada autorizada somente com 2 CPU / 2 GPU.')
        self.roots = {k: Instancia.de(dados.get('antigos', {}).get(k)) for k in ('coordenador', 'runner')}
        if self.roots['coordenador'].pid == self.roots['runner'].pid or int(self.roots['runner'].creation_time) < int(self.roots['coordenador'].creation_time):
            raise Bloqueio('Coordenador e runner devem ser instancias distintas.')
        self.coord_status = local(dados['coord_status'], self.raiz)
        self.runner_status = local(dados['runner_status'], self.raiz)
        self.global_path = local(dados['global'], self.raiz)
        self.parada = local(dados['parada'], self.raiz) if dados.get('parada') else None
        cmd = dados.get('comando')
        if not isinstance(cmd, list) or len(cmd) != len(COMANDO) + 1 or cmd[1:] != COMANDO:
            raise Bloqueio('Comando do coordenador deve ser estatico e exato.')
        self.comando = [str(local(cmd[0], self.raiz)), *COMANDO]
        if Path(self.comando[0]).name.lower() != 'python.exe':
            raise Bloqueio('Executavel deve ser python.exe local aprovado.')
        self.hashes = {}
        self.papeis = {}
        for fonte in dados.get('hashes', []):
            p, sha_fonte, papel = local(fonte['path'], self.raiz), fonte['sha256'], fonte['papel']
            if p in self.hashes or not isinstance(sha_fonte, str) or not re.fullmatch('[0-9a-f]{64}', sha_fonte):
                raise Bloqueio('Fonte duplicada ou SHA256 invalido.')
            self.hashes[p] = sha_fonte
            self.papeis.setdefault(papel, []).append(p)
        if not PAPEIS <= self.papeis.keys() or len(self.papeis.get('global_fonte', [])) != 88:
            raise Bloqueio('Manifesto nao cobre todos os papeis obrigatorios e as 88 fontes globais.')
        if self.papeis['global'] != [self.global_path]:
            raise Bloqueio('Fonte global ambigua.')
        if type(dados.get('global_mtime_ns')) is not int or dados['global_mtime_ns'] <= 0:
            raise Bloqueio('mtime original do global obrigatorio.')
        for papel, rel in (('helper', 'scripts/retomar_historico_apos_calendario.py'),
                           ('tests_helper', 'tests/test_retomar_historico_apos_calendario.py')):
            if self.papeis[papel] != [self.raiz / rel]:
                raise Bloqueio('Hash do helper ou de seus testes nao corresponde a fonte real.')
        coord = self.raiz / 'scripts/coordenar_quantizacao_historica.py'
        if self.papeis['coordenador'] != [coord]:
            raise Bloqueio('Fonte do coordenador nao corresponde ao modulo fixo.')
        self.codigo_coord_sha = self.hashes[coord]
        aprovadas = dados.get('falhas_tecnicas_aprovadas', [])
        if not isinstance(aprovadas, list) or len(aprovadas) > 1:
            raise Bloqueio('Somente uma falha tecnica explicita pode ser aprovada.')
        self.falhas_tecnicas = []
        for f in aprovadas:
            if (not isinstance(f, dict) or set(f) != set(FALHA_TECNICA) | {'log', 'log_sha256', 'auditoria_caches'}
                    or any(f.get(k) != v for k, v in FALHA_TECNICA.items())
                    or type(f.get('returncode')) is not int):
                raise Bloqueio('Falha tecnica aprovada fora de monthly_1/DilatedRNN/refit/1.')
            log = local(f['log'], self.raiz)
            if log != self.runner_status.parent / 'refit_monthly_1_dilatedrnn.log':
                raise Bloqueio('Log tecnico fora da fila original.')
            auditoria = f['auditoria_caches']
            if (not isinstance(auditoria, dict) or set(auditoria) != {'path', 'sha256'}
                    or not isinstance(f['log_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', f['log_sha256'])
                    or not isinstance(auditoria.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', auditoria['sha256'])):
                raise Bloqueio('Log e recibo tecnico devem ter SHA256 exatos.')
            self.falhas_tecnicas.append({**f, 'log': str(log), 'auditoria_caches': {
                'path': str(local(auditoria['path'], self.raiz)), 'sha256': auditoria['sha256']}})
        if bool(self.falhas_tecnicas) != bool(self.papeis.get('auditoria_tecnica_fonte')):
            raise Bloqueio('Fontes da auditoria tecnica exigem uma falha explicitamente aprovada.')
        self.locks = [local(p, self.raiz) for p in dados.get('locks', [])]
        if len(self.locks) < 5 or len(set(self.locks)) != len(self.locks) or any(p.name != '.execucao.lock' for p in self.locks):
            raise Bloqueio('Travas originais explicitas e distintas obrigatorias.')
        for p in (self.coord_status.parent / '.execucao.lock', self.runner_status.parent / '.execucao.lock'):
            if p not in self.locks:
                raise Bloqueio('Trava do coordenador ou runner ausente.')
        i = self.roots['coordenador']
        # Mesma identidade => mesmo lock/journal, mesmo usando outra saida/manifesto.
        self.canonico = self.raiz / REL / 'retomadas_apos_calendario' / f'{i.pid}_{i.creation_time}'
        if not self.canonico.resolve().is_relative_to(self.raiz):
            raise Bloqueio('Diretorio canonico redirecionado para fora do projeto.')

    @classmethod
    def carregar(cls, path, esperado, raiz=RAIZ):
        p = local(path, raiz)
        bruto = p.read_bytes()
        sha = hashlib.sha256(bruto).hexdigest()
        if not re.fullmatch('[0-9a-f]{64}', esperado) or sha != esperado:
            raise Bloqueio('SHA256 do manifesto divergiu do aprovado.')
        return cls(json.loads(bruto), sha, raiz)

    def conferir_fontes(self):
        for p, sha in self.hashes.items():
            if digest(p) != sha:
                raise Bloqueio(f'Fonte divergiu: {p}')
        g = ler(self.global_path)
        pares = g.get('pares', [])
        if (g.get('regime') != 'historico_1998_2022' or len(pares) != 44
                or any(not isinstance(p, list) or len(p) != 2 or not all(isinstance(x, str) for x in p) for p in pares)
                or len({tuple(p) for p in pares}) != 44 or len(g.get('fontes_sha256', {})) != 88):
            raise Bloqueio('Selecao global nao cobre 44 pares / 88 fontes.')
        fontes = {local(p, self.raiz): sha for p, sha in g['fontes_sha256'].items()}
        declaradas = {p: self.hashes[p] for p in self.papeis['global_fonte']}
        if fontes != declaradas:
            raise Bloqueio('As 88 fontes do manifesto nao correspondem ao global congelado.')
        if 'global_mtime_ns' in self.dados and self.global_path.stat().st_mtime_ns != self.dados['global_mtime_ns']:
            raise Bloqueio('mtime do global congelado divergiu.')

    def conferir_falha_tecnica(self, falha):
        if len(self.falhas_tecnicas) != 1:
            raise Bloqueio('Falha adicional sem aprovacao tecnica explicita.')
        aprovada = self.falhas_tecnicas[0]
        if (any(falha.get(k) != v for k, v in FALHA_TECNICA.items())
                or type(falha.get('returncode')) is not int
                or str(local(falha.get('log', ''), self.raiz)) != aprovada['log']):
            raise Bloqueio('Falha adicional difere da falha tecnica aprovada.')
        log, recibo = Path(aprovada['log']), Path(aprovada['auditoria_caches']['path'])
        try:
            if digest(log) != aprovada['log_sha256']:
                raise Bloqueio('SHA256 do log tecnico divergiu.')
            bruto = recibo.read_bytes()
            if hashlib.sha256(bruto).hexdigest() != aprovada['auditoria_caches']['sha256']:
                raise Bloqueio('SHA256 do recibo tecnico divergiu.')
            r = json.loads(bruto)
        except (OSError, ValueError) as exc:
            raise Bloqueio('Recibo de auditoria tecnica ausente ou ilegivel.') from exc
        if (not isinstance(r, dict) or r.get('versao') != 1 or r.get('aprovado') is not True
                or r.get('regime') != 'historico_1998_2022'
                or any(r.get(k) != v for k, v in FALHA_TECNICA.items())
                or type(r.get('returncode')) is not int
                or r.get('log') != aprovada['log'] or r.get('log_sha256') != aprovada['log_sha256']
                or type(r.get('caches_completos_verificados')) is not int
                or r['caches_completos_verificados'] != 7):
            raise Bloqueio('Recibo tecnico nao cobre a falha exata e os sete caches.')
        fontes = r.get('fontes_sha256')
        if (not isinstance(fontes, dict) or not fontes
                or any(not isinstance(p, str) or not isinstance(s, str) or not re.fullmatch('[0-9a-f]{64}', s)
                       for p, s in fontes.items())):
            raise Bloqueio('Recibo tecnico sem fontes SHA256 explicitas.')
        normalizadas = {local(p, self.raiz): s for p, s in fontes.items()}
        declaradas = {p: self.hashes[p] for p in self.papeis.get('auditoria_tecnica_fonte', [])}
        if len(normalizadas) != len(fontes) or normalizadas != declaradas:
            raise Bloqueio('Fontes da auditoria tecnica divergem do manifesto.')
        npzs = [p for p in normalizadas if p.suffix == '.npz']
        raiz_caches = self.global_path.parent / 'monthly_1/dilatedrnn'
        if len(npzs) != 7:
            raise Bloqueio('Recibo tecnico deve vincular exatamente sete caches NPZ.')
        for p in npzs:
            if (not p.is_relative_to(raiz_caches) or p.parent.name != 'refit'
                    or p.parent.parent.parent != raiz_caches
                    or p.parent.parent.name not in ('sem_quantizacao', 'q64', 'q128', 'q256')
                    or not re.fullmatch(r'seed[0-9]+\.npz', p.name)):
                raise Bloqueio('Cache tecnico fora do refit monthly_1/DilatedRNN.')
            checkpoint = p.parent.parent / 'modelos' / f'{p.stem}_refit.pt'
            if not {p.with_suffix('.json'), p.with_suffix('.csv'), checkpoint} <= normalizadas.keys():
                raise Bloqueio('Cache tecnico sem metadados, curva ou checkpoint vinculados.')
        for p, sha in normalizadas.items():
            if digest(p) != sha:
                raise Bloqueio(f'Fonte da auditoria tecnica divergiu: {p}')


class _UnicodeStringSistema(ctypes.Structure):
    _fields_ = [('length', w.USHORT), ('maximum_length', w.USHORT),
                ('buffer', ctypes.c_void_p)]


class Windows:
    """Consultas exatas por handle; erro de acesso nunca significa processo morto."""
    class ProcessoSistemaPrefixo(ctypes.Structure):
        # SYSTEM_PROCESS_INFORMATION: mesmo ABI certificado de processos_quantizacao.
        _fields_ = [('next_offset', w.ULONG), ('threads', w.ULONG),
                    ('reserved', ctypes.c_int64 * 3), ('creation_time', ctypes.c_int64),
                    ('user_time', ctypes.c_int64), ('kernel_time', ctypes.c_int64),
                    ('image', _UnicodeStringSistema), ('priority', w.LONG),
                    ('pid', w.HANDLE), ('ppid', w.HANDLE)]

    class ProcessoBasico(ctypes.Structure):
        # https://learn.microsoft.com/windows/win32/api/winternl/nf-winternl-ntqueryinformationprocess
        _fields_ = [('exit_status', w.LONG), ('peb', ctypes.c_void_p),
                    ('affinity', ctypes.c_size_t), ('priority', w.LONG),
                    ('pid', ctypes.c_size_t), ('ppid', ctypes.c_size_t)]

    class Overlapped(ctypes.Structure):
        # Layout estavel: probes aninhados compartilham os mesmos argtypes.
        _fields_ = [('internal', ctypes.c_size_t), ('internal_high', ctypes.c_size_t),
                    ('offset', w.DWORD), ('offset_high', w.DWORD), ('event', w.HANDLE)]
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Auxiliar requer Windows.')
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.nt = ctypes.WinDLL('ntdll')
        self.handles = {}
        self.k.GetCurrentProcess.argtypes = []
        self.k.GetCurrentProcess.restype = w.HANDLE
        self.k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.k.OpenProcess.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
        self.k.GetProcessTimes.restype = w.BOOL
        self.k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.k.WaitForSingleObject.restype = w.DWORD
        self.nt.NtQuerySystemInformation.argtypes = [w.ULONG, ctypes.c_void_p, w.ULONG, ctypes.POINTER(w.ULONG)]
        self.nt.NtQuerySystemInformation.restype = w.LONG
        self.nt.NtQueryInformationProcess.argtypes = [w.HANDLE, w.ULONG, ctypes.c_void_p, w.ULONG, ctypes.POINTER(w.ULONG)]
        self.nt.NtQueryInformationProcess.restype = w.LONG
        self.k.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.k.QueryFullProcessImageNameW.restype = w.BOOL

    def _stamp(self, handle):
        ts = [w.FILETIME() for _ in range(4)]
        if not self.k.GetProcessTimes(handle, *(ctypes.byref(t) for t in ts)):
            raise ctypes.WinError(ctypes.get_last_error())
        return str((ts[0].dwHighDateTime << 32) | ts[0].dwLowDateTime)

    def _vivo(self, handle):
        r = self.k.WaitForSingleObject(handle, 0)
        if r not in (0, 258):
            raise ctypes.WinError(ctypes.get_last_error())
        return r == 258

    def identificar(self, pid):
        h = self.k.OpenProcess(0x1000 | 0x100000, False, pid)
        if not h:
            error = ctypes.get_last_error()
            if error == 87:
                return None
            raise ctypes.WinError(error)
        try:
            i = Instancia(pid, self._stamp(h))
            if not self._vivo(h):
                return None
            if i not in self.handles:
                self.handles[i] = h
                h = None
            return i
        finally:
            if h:
                self.k.CloseHandle(h)

    def vivo(self, i):
        h = self.handles.get(i)
        if h is None:
            atual = self.identificar(i.pid)
            if atual != i:
                return False
            h = self.handles[i]
        if self._stamp(h) != i.creation_time:
            raise Bloqueio('Handle mudou de identidade.')
        return self._vivo(h)

    def mapa(self):
        # Uma captura pode abranger duas instancias de um PID reutilizado.
        # FILETIME preserva ambas; somente o handle vivo exato decide seu PPID.
        # NtQuerySystemInformation evita perder essa evidencia no Toolhelp.
        registros = self._snapshot_nt()
        resultado = {}
        for pid, instancias in registros.items():
            if len(instancias) == 1:
                resultado[pid] = instancias[0]['ppid']
                continue
            atual = self.identificar(pid)  # WinError5 e outros erros continuam bloqueando.
            if atual is None:
                continue  # Snapshot integral certificado; nenhum PID vivo a omitir.
            matches = [r for r in instancias if r['creation_time'] == atual.creation_time]
            if len(matches) != 1 or not self.vivo(atual):
                raise Bloqueio('PID reutilizado mudou durante snapshot; identidade inconclusiva.')
            resultado[pid] = matches[0]['ppid']
        return resultado

    @classmethod
    def _analisar_snapshot_nt(cls, bruto, tamanho):
        prefixo = cls.ProcessoSistemaPrefixo
        n = ctypes.sizeof(prefixo)
        if not n <= tamanho <= len(bruto):
            raise Bloqueio('Snapshot NT vazio/truncado; tamanho invalido.')
        x64 = ctypes.sizeof(ctypes.c_void_p) == 8
        if (prefixo.creation_time.offset != 32 or prefixo.image.offset != 56
                or prefixo.pid.offset != (80 if x64 else 68)
                or prefixo.ppid.offset != (88 if x64 else 72)):
            raise Bloqueio('ABI do snapshot NT nao reconhecida.')
        offset, resultado, identidades = 0, {}, set()
        while True:
            if offset + n > tamanho:
                raise Bloqueio('Snapshot NT truncado.')
            r = prefixo.from_buffer_copy(bruto, offset)
            pid, ppid, stamp = int(r.pid or 0), int(r.ppid or 0), int(r.creation_time)
            if pid > 0xffffffff or ppid > 0xffffffff or stamp < 0:
                raise Bloqueio('Identidade invalida no snapshot NT.')
            i = (pid, stamp)
            if i in identidades:
                raise Bloqueio('Identidade PID/FILETIME duplicada no snapshot NT.')
            identidades.add(i)
            resultado.setdefault(pid, []).append({'ppid':ppid, 'creation_time':str(stamp)})
            passo = int(r.next_offset)
            if passo == 0:
                return resultado
            if passo < n or passo % ctypes.alignment(prefixo) or offset + passo + n > tamanho:
                raise Bloqueio('Deslocamento invalido no snapshot NT.')
            offset += passo

    def _snapshot_nt(self):
        tamanho, limite = 256 * 1024, 32 * 1024 * 1024
        for _ in range(8):
            if tamanho > limite:
                raise Bloqueio('Snapshot NT excedeu limite de 32 MiB.')
            buffer = ctypes.create_string_buffer(tamanho)
            retorno = w.ULONG()
            status = int(self.nt.NtQuerySystemInformation(5, buffer, tamanho, ctypes.byref(retorno))) & 0xffffffff
            if status in (0xc0000004, 0xc0000023, 0x80000005):
                tamanho = max(tamanho * 2, int(retorno.value))
                continue
            if status != 0:
                raise Bloqueio(f'NtQuerySystemInformation falhou: NTSTATUS 0x{status:08x}.')
            registros = self._analisar_snapshot_nt(buffer.raw, int(retorno.value))
            self._certificar_snapshot_nt(registros)
            return registros
        raise Bloqueio('Snapshot NT mudou de tamanho oito vezes; estado indeterminado.')

    def _certificar_snapshot_nt(self, registros):
        basico = self.ProcessoBasico()
        x64 = ctypes.sizeof(ctypes.c_void_p) == 8
        if self.ProcessoBasico.pid.offset != (32 if x64 else 16):
            raise Bloqueio('ABI da certificacao NT nao reconhecida.')
        if self.ProcessoBasico.ppid.offset != (40 if x64 else 20):
            raise Bloqueio('ABI do PPID da certificacao NT nao reconhecida.')
        handle = self.k.GetCurrentProcess()
        retorno = w.ULONG()
        status = int(self.nt.NtQueryInformationProcess(handle, 0, ctypes.byref(basico), ctypes.sizeof(basico), ctypes.byref(retorno))) & 0xffffffff
        if status != 0 or retorno.value != ctypes.sizeof(basico) or basico.pid != os.getpid():
            raise Bloqueio('Consulta do proprio PID/PPID NT nao certificou o layout.')
        stamp = self._stamp(handle)
        proprio = registros.get(os.getpid())
        if int(stamp) <= 0 or proprio != [{'ppid':int(basico.ppid), 'creation_time':stamp}]:
            raise Bloqueio('Snapshot NT nao reproduziu PID/FILETIME/PPID do proprio processo.')

    def programa(self, i):
        if not self.vivo(i):
            raise Bloqueio('Novo coordenador encerrou antes da confirmacao.')
        b = ctypes.create_unicode_buffer(32768); n = w.DWORD(len(b))
        if not self.k.QueryFullProcessImageNameW(self.handles[i], 0, b, ctypes.byref(n)):
            raise ctypes.WinError(ctypes.get_last_error())
        return b.value

    def lancar(self, comando, saida, erro, raiz):
        # Popen simples: nenhum job KILL_ON_JOB_CLOSE e nenhum terminate/kill.
        with saida.open('xb') as out, erro.open('xb') as err:
            return subprocess.Popen(comando, cwd=raiz, stdin=subprocess.DEVNULL,
                                    stdout=out, stderr=err, close_fds=True,
                                    creationflags=subprocess.CREATE_NO_WINDOW)

    def fechar(self):
        for h in self.handles.values():
            self.k.CloseHandle(h)
        self.handles.clear()

    @contextmanager
    def lock_observador(self, pasta):
        pasta.mkdir(parents=True, exist_ok=True)
        p = pasta / '.observador.lock'
        k = self.k
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        k.CreateFileW.restype = w.HANDLE
        h = k.CreateFileW(str(p), 0x80000000 | 0x40000000, 0, None, 4, 0x80, None)
        if h == ctypes.c_void_p(-1).value:
            raise Bloqueio(f'Lock exclusivo do observador indisponivel: {ctypes.WinError(ctypes.get_last_error())}')
        try:
            yield
        finally:
            k.CloseHandle(h)

    @contextmanager
    def trava_original(self, path):
        Overlapped = self.Overlapped
        k = self.k
        k.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ctypes.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
        k.CreateFileW.restype = w.HANDLE
        k.LockFileEx.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, w.DWORD, ctypes.POINTER(Overlapped)]
        k.LockFileEx.restype = w.BOOL
        k.UnlockFileEx.argtypes = [w.HANDLE, w.DWORD, w.DWORD, w.DWORD, ctypes.POINTER(Overlapped)]
        k.UnlockFileEx.restype = w.BOOL
        # OPEN_EXISTING + READ: sem escrever bytes, truncar ou excluir travas antigas.
        h = k.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x80, None)
        if h == ctypes.c_void_p(-1).value:
            raise Bloqueio(f'Trava original nao verificavel: {ctypes.WinError(ctypes.get_last_error())}')
        ov = Overlapped(); travada = False
        try:
            if not k.LockFileEx(h, 3, 0, 1, 0, ctypes.byref(ov)):
                raise Bloqueio(f'Trava original ocupada/inconclusiva: {path}')
            travada = True
            yield
        finally:
            try:
                if travada and not k.UnlockFileEx(h, 0, 1, 0, ctypes.byref(ov)):
                    raise ctypes.WinError(ctypes.get_last_error())
            finally:
                k.CloseHandle(h)


class Journal:
    def __init__(self, path):
        self.path = path

    def ler(self):
        return ler(self.path) if self.path.exists() else None

    def gravar(self, dados):
        salvar_json(dados, self.path)


class Retomada:
    def __init__(self, manifesto, saida, backend, journal=None):
        self.m, self.backend = manifesto, backend
        self.saida = local(saida, manifesto.raiz).resolve()
        if not self.saida.is_relative_to(manifesto.raiz / REL):
            raise Bloqueio('Saida operacional deve ficar nos relatorios da quantizacao.')
        self.journal = journal or Journal(manifesto.canonico / 'journal.json')
        self.estado = self.journal.ler()
        if self.estado:
            if self.estado.get('manifesto_sha256') != self.m.sha:
                raise Bloqueio('Journal pertence a outro manifesto; reconciliacao obrigatoria.')
            if self.estado.get('etapa') in ('LAUNCH_INTENT', 'BLOCKED'):
                raise Bloqueio('Journal inconclusivo/bloqueado; novo lançamento proibido.')
            if self.estado.get('etapa') not in ('WAITING', 'PRECHECK', 'CONFIRMED'):
                raise Bloqueio('Estado do journal nao reconhecido.')
        else:
            self.estado = {'versao': 1, 'manifesto_sha256': self.m.sha, 'etapa': 'WAITING',
                           'antigos': {k: asdict(v) for k, v in self.m.roots.items()},
                           'conhecidos': [], 'iniciado_em_utc': agora(), 'tentativas_popen': 0}
        self.conhecidos = {Instancia.de(i) for i in self.estado['conhecidos']} | set(self.m.roots.values())
        self.launcher = None
        self.confirmacao_limite = None

    def registrar(self, etapa, **campos):
        novo = {**self.estado, **campos, 'etapa': etapa, 'atualizado_em_utc': agora(),
                'conhecidos': [asdict(i) for i in sorted(self.conhecidos, key=lambda x:(x.pid, x.creation_time))]}
        self.journal.gravar(novo)  # Intento precisa estar duravel ANTES de Popen.
        self.estado = novo

    def estados_antigos(self):
        c, r = ler(self.m.coord_status), ler(self.m.runner_status)
        for d, key, i in ((c, 'identidade_coordenador', self.m.roots['coordenador']),
                          (r, 'identidade_runner', self.m.roots['runner'])):
            if Instancia.de(d.get(key)) != i:
                raise Bloqueio('Status antigo mudou de identidade.')
            for reg in d.get('processos_historico', []) + d.get('processos', []):
                self.conhecidos.add(Instancia.de(reg))
            if isinstance(d.get('processo_filho'), dict):
                self.conhecidos.add(Instancia.de(d['processo_filho']))
        return c, r

    def observar(self):
        self.estados_antigos()
        for i in self.m.roots.values():
            atual = self.backend.identificar(i.pid)
            if atual is not None and atual != i:
                raise Bloqueio('PID da raiz antiga foi reutilizado; reconciliacao obrigatoria.')
        mapa = self.backend.mapa()
        vivos = {i for i in self.conhecidos if self.backend.vivo(i)}
        fila = [(i,) for i in vivos]
        visitados = {i.pid for i in vivos}
        for cadeia in fila:
            pai = cadeia[-1]
            for pid, ppid in mapa.items():
                if ppid != pai.pid or pid in visitados:
                    continue
                filho = self.backend.identificar(pid)
                if filho is None:
                    continue
                if int(filho.creation_time) < int(pai.creation_time):
                    raise Bloqueio('Parentesco temporal invalido.')
                nova = cadeia + (filho,)
                # Handles retidos; revalidar todos os edges e instancias ainda vivas.
                fresco = self.backend.mapa()
                if not all(self.backend.vivo(i) for i in nova) or any(fresco.get(b.pid) != a.pid for a,b in zip(nova,nova[1:])):
                    raise Bloqueio('Arvore mudou durante a captura; nenhuma retomada permitida.')
                self.conhecidos.add(filho); vivos.add(filho); visitados.add(pid); fila.append(nova)
        return vivos

    def conferir_erro(self):
        c, r = self.estados_antigos()
        if c.get('etapa') != 'erro' or r.get('etapa') != 'erro' or r.get('regime') != 'historico_1998_2022':
            raise Bloqueio('Coordenador/runner devem encerrar naturalmente em erro historico.')
        log_coord = self.m.coord_status.parent / 'fila_historico_1998_2022.log'
        if c.get('erro') != f'RuntimeError: Falha fila_historico_1998_2022; consultar {log_coord}':
            raise Bloqueio('Erro do coordenador nao corresponde a fila historica.')
        eventos = c.get('eventos', [])
        if not eventos or eventos[-1].get('etapa') != 'fila_historico_1998_2022' or eventos[-1].get('retorno') != 1:
            raise Bloqueio('Saida natural da fila com retorno 1 nao foi registrada.')
        falhas = r.get('falhas', [])
        jobs = [f for f in falhas if 'modelo' in f]
        agregados = [f for f in falhas if 'modelo' not in f]
        sazonais = [f for f in jobs if f.get('modelo') == 'Sazonal ingenuo']
        tecnicas = [f for f in jobs if f.get('modelo') != 'Sazonal ingenuo']
        if len(tecnicas) != len(self.m.falhas_tecnicas):
            raise Bloqueio('Falha adicional ou aprovacao tecnica nao corresponde ao runner.')
        if not 1 <= len(sazonais) <= 2 or len({f.get('tarefa') for f in sazonais}) != len(sazonais):
            raise Bloqueio('Quantidade de falhas sazonais nao autorizada.')
        for f in jobs:
            if f.get('modelo') != 'Sazonal ingenuo':
                self.m.conferir_falha_tecnica(f)
                continue
            if (f.get('fase') != 'refit' or f.get('modelo') != 'Sazonal ingenuo'
                    or f.get('tarefa') not in ('monthly_1', 'monthly_6') or f.get('returncode') != 1):
                raise Bloqueio('Falha adicional ou fora dos dois Sazonais mensais.')
            p = local(f.get('log', ''), self.m.raiz)
            esperado = self.m.runner_status.parent / f"refit_{f['tarefa']}_sazonal_ingenuo.log"
            if p != esperado:
                raise Bloqueio('Log sazonal fora da fila original.')
            with p.open('rb') as stream:
                stream.seek(max(0, p.stat().st_size - 128 * 1024)); tail = stream.read().decode('utf-8', errors='replace')
            linhas = [s.strip() for s in tail.splitlines() if s.strip()]
            if not linhas or not re.fullmatch(r'ValueError: Referencia anual ausente em [^\r\n]+\.', linhas[-1]):
                raise Bloqueio('Erro sazonal difere de referencia anual ausente.')
        # O runner acrescenta um resumo RuntimeError depois dos jobs que falharam.
        esperado_resumo = f'{len(jobs)} execucoes falharam; outras selecoes foram preservadas. Consulte {self.m.runner_status}'
        if len(agregados) != 1 or agregados[0].get('tipo') != 'RuntimeError' or agregados[0].get('mensagem') != esperado_resumo:
            raise Bloqueio('Resumo de erro do runner inesperado.')
        if r.get('processos') or r.get('pendentes'):
            raise Bloqueio('Runner encerrou com processos/pendentes nao resolvidos.')
        return jobs

    def conferir_sem_orfaos(self):
        if any(self.backend.vivo(i) for i in self.conhecidos):
            raise Bloqueio('Instancia antiga ainda viva.')
        mapa = self.backend.mapa()
        pids = {i.pid for i in self.conhecidos}
        # Mesmo com pai morto, um PPID ligado a qualquer instancia conhecida bloqueia.
        if any(pid != ppid and ppid in pids and self.backend.identificar(pid) is not None
               for pid, ppid in mapa.items()):
            raise Bloqueio('Possivel descendente nao identificado; reconciliacao obrigatoria.')

    def preservar_final(self, token, falhas):
        """Copias exclusivas e duraveis antes de o novo runner reabrir seus logs."""
        pasta = self.saida / f'{token}_antes'
        pasta.mkdir(parents=True, exist_ok=False)
        fontes = {self.m.coord_status, self.m.runner_status,
                  self.m.coord_status.parent / 'fila_historico_1998_2022.log'}
        fontes.update(self.m.runner_status.parent.glob('*.log'))
        fontes.update(local(f['log'], self.m.raiz) for f in falhas)
        fontes.update(Path(f['auditoria_caches']['path']) for f in self.m.falhas_tecnicas)
        preservados = []
        for indice, p in enumerate(sorted(fontes, key=str)):
            p = local(p, self.m.raiz)
            stat = p.stat(); bruto = p.read_bytes(); sha = hashlib.sha256(bruto).hexdigest()
            copia = pasta / f'{indice:03d}_{p.name}'
            with copia.open('xb') as stream:
                stream.write(bruto); stream.flush(); os.fsync(stream.fileno())
            if (digest(copia) != sha or digest(p) != sha
                    or p.stat().st_mtime_ns != stat.st_mtime_ns):
                raise Bloqueio('Estado/log mudou durante a preservacao; nenhuma retomada.')
            preservados.append({'origem':str(p),'copia':str(copia),'sha256':sha,
                                'mtime_ns_original':stat.st_mtime_ns})
        return preservados

    def precheck_e_lancar(self):
        self.registrar('PRECHECK', instancias_vivas=[])
        self.conferir_sem_orfaos()
        falhas = self.conferir_erro()
        self.m.conferir_fontes()
        with ExitStack() as stack:
            for path in self.m.locks:
                stack.enter_context(self.backend.trava_original(path))
            self.conferir_sem_orfaos()
            self.conferir_erro()
            self.m.conferir_fontes()
        if self.m.parada and self.m.parada.exists():
            raise Bloqueio('Arquivo de parada solicitado.')
        token = uuid.uuid4().hex
        self.saida.mkdir(parents=True, exist_ok=True)
        out, err = self.saida / f'{token}_coordenador.log', self.saida / f'{token}_coordenador.erro.log'
        preservados = self.preservar_final(token, falhas)
        self.registrar('LAUNCH_INTENT', token=token, intent_filetime=filetime_agora(),
                       comando=self.m.comando, stdout=str(out), stderr=str(err),
                       falhas_aceitas=falhas, tentativas_popen=1, preservados=preservados,
                       precheck_aprovado_em_utc=agora(), travas_verificadas=[str(p) for p in self.m.locks])
        self.m.conferir_fontes()
        self.conferir_sem_orfaos()
        self.conferir_erro()
        p = self.backend.lancar(self.m.comando, out, err, self.m.raiz)
        launcher = self.backend.identificar(p.pid)
        if launcher is None or int(launcher.creation_time) < int(self.estado['intent_filetime']):
            raise Bloqueio('Identidade do launcher novo inconclusiva.')
        self.launcher = launcher
        self.registrar('LAUNCH_INTENT', launcher=asdict(launcher))
        self.confirmacao_limite = time.monotonic() + 300

    def confirmar(self):
        if not self.backend.vivo(self.launcher):
            raise Bloqueio('Launcher encerrou antes da confirmacao; nao relancar.')
        c = ler(self.m.coord_status)
        i = Instancia.de(c.get('identidade_coordenador'))
        if i == self.m.roots['coordenador']:
            if time.monotonic() > self.confirmacao_limite:
                raise Bloqueio('Novo coordenador nao confirmou em 300s; nao relancar.')
            return False
        if (int(i.creation_time) < int(self.estado['intent_filetime'])
                or c.get('codigo_sha256') != self.m.codigo_coord_sha or c.get('etapa') == 'erro'):
            raise Bloqueio('Status novo tem timestamp/codigo/etapa inesperados.')
        if not self.backend.vivo(i) or Path(self.backend.programa(i)).name.lower() != 'python.exe':
            raise Bloqueio('Novo coordenador nao e interpretador vivo identificado.')
        # Trilha do real interpretador ate o launcher; todos os handles retidos.
        mapa = self.backend.mapa(); cadeia = [i]; vistos = {i.pid}
        while cadeia[-1] != self.launcher:
            pid = mapa.get(cadeia[-1].pid)
            if not pid or pid in vistos:
                raise Bloqueio('Novo coordenador nao descende do launcher desta tentativa.')
            pai = self.backend.identificar(pid)
            if pai is None or int(pai.creation_time) > int(cadeia[-1].creation_time):
                raise Bloqueio('Ancestral do novo coordenador inconclusivo.')
            cadeia.append(pai); vistos.add(pid)
        fresco = self.backend.mapa()
        if not all(self.backend.vivo(x) for x in cadeia) or any(fresco.get(filho.pid) != pai.pid for filho,pai in zip(cadeia,cadeia[1:])):
            raise Bloqueio('Arvore nova mudou durante confirmacao.')
        self.registrar('CONFIRMED', coordenador_novo=asdict(i), confirmado_em_utc=agora(),
                       prioridade='nao alterada por este helper')
        salvar_json(self.estado, self.saida / f"{self.estado['token']}_retomada_confirmada.json")
        return True

    def ciclo(self):
        if self.estado['etapa'] == 'CONFIRMED':
            return True
        if self.m.parada and self.m.parada.exists():
            raise Bloqueio('Arquivo de parada solicitado; nenhum processo sera encerrado.')
        if self.launcher is not None:
            return self.confirmar()
        vivos = self.observar()
        if vivos:
            self.registrar('WAITING', instancias_vivas=[asdict(i) for i in vivos])
            return False
        self.precheck_e_lancar()
        return self.confirmar()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--manifesto', type=Path, required=True)
    ap.add_argument('--manifesto-sha256', required=True)
    ap.add_argument('--saida-localdir', type=Path, required=True)
    args = ap.parse_args()
    m = Manifesto.carregar(args.manifesto, args.manifesto_sha256)
    backend = Windows()
    try:
        with backend.lock_observador(m.canonico):
            r = Retomada(m, args.saida_localdir, backend)
            try:
                while not r.ciclo():
                    print(json.dumps({'utc': agora(), 'etapa': r.estado['etapa'],
                                      'conhecidos': len(r.conhecidos)}), flush=True)
                    time.sleep(15)
            except Exception as exc:
                r.registrar('BLOCKED', erro=f'{type(exc).__name__}: {exc}',
                            lancamento_pode_ter_ocorrido=r.estado.get('tentativas_popen', 0) != 0)
                raise
    finally:
        backend.fechar()  # Fecha SOMENTE handles de consulta; nunca processos.


if __name__ == '__main__':
    main()
