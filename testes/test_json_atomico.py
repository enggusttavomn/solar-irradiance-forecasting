import json
from pathlib import Path
from unittest.mock import patch

import pytest

from codigo_fonte.utilitarios.json_atomico import salvar_json


def bloqueio(codigo=32):
    exc = PermissionError('Arquivo ocupado')
    exc.winerror = codigo
    return exc


@pytest.mark.parametrize('codigo', [5, 32, 33])
def test_repete_bloqueio_sem_perder_destino(tmp_path, codigo):
    destino = tmp_path / 'runner.json'
    destino.write_text('{"anterior": true}', encoding='utf-8')
    replace = Path.replace
    chamadas = []
    cargas = []

    def substituir(origem, alvo):
        chamadas.append(origem)
        assert origem.is_file()
        # A mesma carga e o mesmo temporario sobrevivem a cada bloqueio.
        cargas.append(origem.read_bytes())
        assert cargas[-1] == cargas[0]
        assert origem == chamadas[0]
        if len(chamadas) < 3:
            assert json.loads(destino.read_text()) == {'anterior': True}
            raise bloqueio(codigo)
        return replace(origem, alvo)

    with patch.object(Path, 'replace', substituir):
        salvar_json({'etapa': 'seleção'}, destino, intervalo=0)
    assert len(chamadas) == 3
    assert len(set(chamadas)) == 1
    assert json.loads(destino.read_text(encoding='utf-8')) == {'etapa': 'seleção'}
    assert list(tmp_path.glob('*.tmp')) == []


@pytest.mark.parametrize('codigo', [5, 32, 33])
def test_bloqueio_persistente_falha_e_preserva_anterior(tmp_path, codigo):
    destino = tmp_path / 'runner.json'
    destino.write_text('{}')
    erro = bloqueio(codigo)
    with patch.object(Path, 'replace', side_effect=erro) as substituir:
        with patch('scripts.json_atomico.time.sleep') as esperar:
            with pytest.raises(PermissionError) as levantado:
                salvar_json({'novo': 1}, destino, tentativas=3, intervalo=0.25)
    assert levantado.value is erro
    assert substituir.call_count == 3
    assert esperar.call_count == 2
    assert all(chamada.args == (0.25,) for chamada in esperar.call_args_list)
    assert destino.read_text() == '{}'
    assert list(tmp_path.glob('*.tmp')) == []


@pytest.mark.parametrize('codigo', [None, 13, 1314])
def test_nao_repete_outros_erros_de_acesso(tmp_path, codigo):
    erro = PermissionError('negado') if codigo is None else bloqueio(codigo)
    with patch.object(Path, 'replace', side_effect=erro) as mock:
        with patch('scripts.json_atomico.time.sleep') as esperar:
            with pytest.raises(PermissionError) as levantado:
                salvar_json({}, tmp_path / 'runner.json', intervalo=0)
    assert levantado.value is erro
    assert mock.call_count == 1
    esperar.assert_not_called()
    assert list(tmp_path.glob('*.tmp')) == []


def test_winerror5_na_ultima_tentativa_nao_espera_novamente(tmp_path):
    with patch.object(Path, 'replace', side_effect=bloqueio(5)) as substituir:
        with patch('scripts.json_atomico.time.sleep') as esperar:
            with pytest.raises(PermissionError):
                salvar_json({}, tmp_path / 'runner.json', tentativas=1)
    assert substituir.call_count == 1
    esperar.assert_not_called()
    assert list(tmp_path.glob('*.tmp')) == []


def test_nao_repete_erro_antes_da_troca(tmp_path):
    # Falha ao criar o temporario nao e bloqueio da substituicao atomica.
    erro = bloqueio(5)
    with patch('scripts.json_atomico.tempfile.mkstemp', side_effect=erro) as criar:
        with patch('scripts.json_atomico.time.sleep') as esperar:
            with pytest.raises(PermissionError) as levantado:
                salvar_json({}, tmp_path / 'runner.json')
    assert levantado.value is erro
    assert criar.call_count == 1
    esperar.assert_not_called()


"""Durabilidade e propagacao de erros na substituicao dos estados JSON."""
import json
import os
from pathlib import Path

import pytest

from codigo_fonte.utilitarios import json_atomico


def erro_windows(codigo):
    erro = PermissionError('Bloqueio simulado')
    erro.winerror = codigo
    return erro


def test_flush_fsync_e_replace_nessa_ordem(tmp_path, monkeypatch):
    destino = tmp_path / 'estado.json'
    destino.write_bytes(b'{"anterior": true}')
    eventos = []
    fdopen_original, fsync_original, replace_original = os.fdopen, os.fsync, Path.replace

    class StreamObservado:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def write(self, *args):
            return self.stream.write(*args)

        def flush(self):
            eventos.append('flush')
            self.stream.flush()

        def fileno(self):
            return self.stream.fileno()

    def sincronizar(fd):
        eventos.append('fsync')
        assert eventos == ['flush', 'fsync']
        assert destino.read_bytes() == b'{"anterior": true}'
        fsync_original(fd)

    def substituir(temporario, path):
        eventos.append('replace')
        assert eventos == ['flush', 'fsync', 'replace']
        assert json.loads(temporario.read_text(encoding='utf-8')) == {'novo': True}
        return replace_original(temporario, path)

    monkeypatch.setattr(json_atomico.os, 'fdopen', lambda *a, **kw: StreamObservado(fdopen_original(*a, **kw)))
    monkeypatch.setattr(json_atomico.os, 'fsync', sincronizar)
    monkeypatch.setattr(Path, 'replace', substituir)
    json_atomico.salvar_json({'novo': True}, destino)
    assert eventos == ['flush', 'fsync', 'replace']
    assert json.loads(destino.read_text(encoding='utf-8')) == {'novo': True}
    assert not list(tmp_path.glob('*.tmp'))


def test_fsync_falha_preserva_destino_e_limpa_temporario(tmp_path, monkeypatch):
    destino = tmp_path / 'estado.json'
    anterior = b'{"anterior": true}'
    destino.write_bytes(anterior)
    erro = OSError('Falha de sincronizacao')
    substituicoes = []

    def falhar(fd):
        raise erro

    monkeypatch.setattr(json_atomico.os, 'fsync', falhar)
    monkeypatch.setattr(Path, 'replace', lambda *a: substituicoes.append(a))
    with pytest.raises(OSError) as captura:
        json_atomico.salvar_json({'novo': True}, destino)
    assert captura.value is erro
    assert destino.read_bytes() == anterior
    assert substituicoes == [] and not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('codigo', [5, 32, 33])
def test_retries_continuam_apos_uma_sincronizacao(tmp_path, monkeypatch, codigo):
    destino = tmp_path / 'estado.json'
    destino.write_bytes(b'{"anterior": true}')
    tentativas, esperas, sincronizacoes = [], [], []
    replace_original, fsync_original = Path.replace, os.fsync

    def sincronizar(fd):
        sincronizacoes.append(fd)
        fsync_original(fd)

    def substituir(temporario, path):
        assert len(sincronizacoes) == 1
        tentativas.append(temporario)
        if len(tentativas) < 3:
            raise erro_windows(codigo)
        return replace_original(temporario, path)

    monkeypatch.setattr(json_atomico.os, 'fsync', sincronizar)
    monkeypatch.setattr(Path, 'replace', substituir)
    monkeypatch.setattr(json_atomico.time, 'sleep', esperas.append)
    json_atomico.salvar_json({'novo': True}, destino, tentativas=3, intervalo=0.25)
    assert len(tentativas) == 3 and len(set(tentativas)) == 1
    assert esperas == [0.25, 0.25]
    assert json.loads(destino.read_text(encoding='utf-8')) == {'novo': True}
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('codigo', [5, 32, 33, 6])
def test_limite_e_outros_erros_preservam_destino(tmp_path, monkeypatch, codigo):
    destino = tmp_path / 'estado.json'
    anterior = b'{"anterior": true}'
    destino.write_bytes(anterior)
    erro = erro_windows(codigo)
    tentativas, esperas = [], []

    def falhar(temporario, path):
        tentativas.append(temporario)
        raise erro

    monkeypatch.setattr(Path, 'replace', falhar)
    monkeypatch.setattr(json_atomico.time, 'sleep', esperas.append)
    with pytest.raises(PermissionError) as captura:
        json_atomico.salvar_json({'novo': True}, destino, tentativas=3, intervalo=0.25)
    assert captura.value is erro
    assert len(tentativas) == (1 if codigo == 6 else 3)
    assert esperas == ([] if codigo == 6 else [0.25, 0.25])
    assert destino.read_bytes() == anterior and not list(tmp_path.glob('*.tmp'))


def test_bloqueio_liberado_apos_a_janela_anterior(tmp_path, monkeypatch):
    destino = tmp_path / 'estado.json'
    destino.write_bytes(b'{"anterior": true}')
    tentativas, esperas = [], []
    replace_original = Path.replace

    def substituir(temporario, path):
        tentativas.append(temporario)
        if len(tentativas) <= 80:
            raise erro_windows(5)
        return replace_original(temporario, path)

    monkeypatch.setattr(Path, 'replace', substituir)
    monkeypatch.setattr(json_atomico.time, 'sleep', esperas.append)
    json_atomico.salvar_json({'novo': True}, destino)
    assert len(tentativas) == 81 and len(set(tentativas)) == 1
    assert sum(esperas) == 20
    assert json.loads(destino.read_text(encoding='utf-8')) == {'novo': True}
    assert not list(tmp_path.glob('*.tmp'))


@pytest.mark.parametrize('codigo', [5, 32, 33])
def test_janela_padrao_continua_limitada_e_falha_visivel(tmp_path, monkeypatch, codigo):
    destino = tmp_path / 'estado.json'
    anterior = b'{"anterior": true}'
    destino.write_bytes(anterior)
    erro = erro_windows(codigo)
    tentativas, esperas = [], []

    def falhar(temporario, path):
        tentativas.append(temporario)
        raise erro

    monkeypatch.setattr(Path, 'replace', falhar)
    monkeypatch.setattr(json_atomico.time, 'sleep', esperas.append)
    with pytest.raises(PermissionError) as captura:
        json_atomico.salvar_json({'novo': True}, destino)
    assert captura.value is erro
    assert len(tentativas) == 240
    assert len(esperas) == 239 and sum(esperas) == 59.75
    assert len(set(tentativas)) == 1
    assert destino.read_bytes() == anterior
    assert not list(tmp_path.glob('*.tmp'))
