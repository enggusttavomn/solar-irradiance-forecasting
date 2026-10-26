"""Identidade Windows protegida: testes de guardas, sem encerrar processos reais."""
import ctypes
import os
from types import SimpleNamespace
import pytest
from scripts import processos_quantizacao as p

pytestmark = pytest.mark.skipif(os.name != 'nt', reason='ABI Windows')


def montar_snapshot(registros):
    dados = []
    for indice, (pid, criacao) in enumerate(registros):
        item = p.ProcessoSistemaPrefixo()
        item.pid = pid
        item.creation_time = criacao
        item.next_offset = ctypes.sizeof(item) if indice + 1 < len(registros) else 0
        dados.append(bytes(item))
    return b''.join(dados)


def acesso_negado(monkeypatch):
    monkeypatch.setattr(p.k, 'OpenProcess', lambda *args: 0)
    monkeypatch.setattr(p.ctypes, 'get_last_error', lambda: 5)


def consulta_fake(monkeypatch, dados, *, status=0, criacao_propria=123, retorno=None):
    def consulta(classe, buffer, tamanho, out):
        assert classe == 5
        out._obj.value = len(dados) if retorno is None else retorno
        if status == 0 and len(dados) <= tamanho:
            ctypes.memmove(buffer, dados, len(dados))
        return status
    monkeypatch.setattr(p.ctypes, 'WinDLL', lambda nome: SimpleNamespace(
        NtQuerySystemInformation=consulta))
    def tempos(handle, criacao, *outros):
        criacao._obj.dwHighDateTime = criacao_propria >> 32
        criacao._obj.dwLowDateTime = criacao_propria & 0xffffffff
        return True
    monkeypatch.setattr(p.k, 'GetProcessTimes', tempos)


def test_parser_preserva_filetime_100ns_e_pids():
    criacao = 134353691704237191
    dados = montar_snapshot([(os.getpid(), criacao), (9876, criacao + 1)])
    registros = p.analisar_snapshot_identidades(dados, len(dados))
    assert registros[9876] == {'pid': 9876, 'creation_time': str(criacao + 1)}
    assert registros[os.getpid()]['creation_time'] == str(criacao)


@pytest.mark.parametrize('alteracao', ['truncado', 'sem_terminal', 'passo_pequeno',
                                      'passo_desalinhado', 'pid_duplicado'])
def test_parser_inconsistente_nao_confirma_ausencia(alteracao):
    tam = ctypes.sizeof(p.ProcessoSistemaPrefixo)
    dados = montar_snapshot([(123, 10), (456, 20)])
    item = p.ProcessoSistemaPrefixo.from_buffer_copy(dados)
    if alteracao == 'truncado':
        dados = dados[:tam - 1]
    elif alteracao == 'sem_terminal':
        ultimo = p.ProcessoSistemaPrefixo.from_buffer_copy(dados, tam)
        ultimo.next_offset = tam
        dados = dados[:tam] + bytes(ultimo)
    elif alteracao == 'passo_pequeno':
        item.next_offset = 8
        dados = bytes(item) + dados[tam:]
    elif alteracao == 'passo_desalinhado':
        item.next_offset = tam + 1
        dados = bytes(item) + dados[tam:]
    else:
        dados = montar_snapshot([(123, 10), (123, 20)])
    with pytest.raises(ValueError):
        p.analisar_snapshot_identidades(dados, len(dados))


@pytest.mark.parametrize('retorno', [0, 1, 1_000_000])
def test_returnlength_invalido_bloqueia(monkeypatch, retorno):
    dados = montar_snapshot([(os.getpid(), 123)])
    consulta_fake(monkeypatch, dados, retorno=retorno)
    with pytest.raises(ValueError):
        p.snapshot_identidades_windows()


def test_snapshot_se_certifica_por_pid_filetime_proprio(monkeypatch):
    dados = montar_snapshot([(os.getpid(), 123), (456, 124)])
    consulta_fake(monkeypatch, dados)
    assert p.snapshot_identidades_windows()[456]['creation_time'] == '124'


@pytest.mark.parametrize('registros', [[(456, 123)], [(os.getpid(), 124)]])
def test_layout_nao_certificado_nao_vira_fila_vazia(monkeypatch, registros):
    consulta_fake(monkeypatch, montar_snapshot(registros))
    with pytest.raises(ValueError, match='nao reproduziu PID/FILETIME'):
        p.snapshot_identidades_windows()


@pytest.mark.parametrize('status', [0xc0000001, -1073741823])
def test_status_nt_erro_bloqueia(monkeypatch, status):
    consulta_fake(monkeypatch, b'', status=status)
    with pytest.raises(OSError, match='NTSTATUS'):
        p.snapshot_identidades_windows()


def test_snapshot_cresce_em_length_mismatch_assinado(monkeypatch):
    dados = montar_snapshot([(os.getpid(), 123)])
    chamadas = []
    def consulta(classe, buffer, tamanho, retorno):
        chamadas.append(tamanho)
        if len(chamadas) == 1:
            retorno._obj.value = tamanho + 1
            return -1073741820  # STATUS_INFO_LENGTH_MISMATCH0xC0000004
        retorno._obj.value = len(dados)
        ctypes.memmove(buffer, dados, len(dados))
        return 0
    consulta_fake(monkeypatch, dados)
    monkeypatch.setattr(p.ctypes, 'WinDLL', lambda nome: SimpleNamespace(
        NtQuerySystemInformation=consulta))
    assert p.snapshot_identidades_windows()[os.getpid()]['creation_time'] == '123'
    assert chamadas == [256 * 1024, 512 * 1024]


def test_snapshot_rejeita_cap_excedido(monkeypatch):
    consulta_fake(monkeypatch, b'', status=0xc0000004, retorno=64 * 1024 * 1024)
    with pytest.raises(ValueError, match='limite de 32 MiB'):
        p.snapshot_identidades_windows()


def test_access_denied_com_mesma_identidade_continua_ativo(monkeypatch):
    acesso_negado(monkeypatch)
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: {
        123: {'pid': 123, 'creation_time': '111'}})
    assert p.mesma_instancia({'pid': 123, 'creation_time': '111'}) is True
    monkeypatch.setattr(p, 'mapa_processos', lambda: {123: 0, 456: 123})
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: {
        123: {'pid': 123, 'creation_time': '111'},
        456: {'pid': 456, 'creation_time': '112'}})
    ativos = p.processos_da_fila_ativos({
        'identidade_runner': {'pid': 123, 'creation_time': '111'}})
    assert {r['pid'] for r in ativos} == {123, 456}


def test_access_denied_pid_reutilizado_nao_e_processo_original(monkeypatch):
    acesso_negado(monkeypatch)
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: {
        123: {'pid': 123, 'creation_time': '112'}})
    assert p.mesma_instancia({'pid': 123, 'creation_time': '111'}) is False
    monkeypatch.setattr(p, 'mapa_processos', lambda: {123: 0, 456: 123})
    assert not p.processos_da_fila_ativos({
        'identidade_runner': {'pid': 123, 'creation_time': '111'}})


def test_access_denied_snapshot_integral_ausente_confirma_encerrado(monkeypatch):
    acesso_negado(monkeypatch)
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: {})
    assert p.identidade(123) is None


@pytest.mark.parametrize('causa', [ValueError('malformado'), OSError('API ausente'),
                                  RuntimeError('resize excedido'), AttributeError('simbolo ausente')])
def test_access_denied_snapshot_indeterminado_preserva_bloqueio(monkeypatch, causa):
    acesso_negado(monkeypatch)
    def falhar():
        raise causa
    monkeypatch.setattr(p, 'snapshot_identidades_windows', falhar)
    with pytest.raises(PermissionError) as erro:
        p.identidade(123)
    assert erro.value.winerror == 5
    assert erro.value.__cause__ is causa


def test_filetime_zero_do_pid_protegido_nao_e_ausencia(monkeypatch):
    acesso_negado(monkeypatch)
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: {
        123: {'pid': 123, 'creation_time': '0'}})
    with pytest.raises(PermissionError):
        p.identidade(123)


def test_outro_erro_openprocess_nao_usa_fallback(monkeypatch):
    monkeypatch.setattr(p.k, 'OpenProcess', lambda *args: 0)
    monkeypatch.setattr(p.ctypes, 'get_last_error', lambda: 6)
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: pytest.fail('fallback indevido'))
    with pytest.raises(OSError) as erro:
        p.identidade(123)
    assert erro.value.winerror == 6


def test_winerror87_preserva_caminho_encerrado(monkeypatch):
    monkeypatch.setattr(p.k, 'OpenProcess', lambda *args: 0)
    monkeypatch.setattr(p.ctypes, 'get_last_error', lambda: 87)
    monkeypatch.setattr(p, 'snapshot_identidades_windows', lambda: pytest.fail('fallback indevido'))
    assert p.identidade(123) is None
