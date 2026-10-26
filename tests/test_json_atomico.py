"""Durabilidade e propagacao de erros na substituicao dos estados JSON."""
import json
import os
from pathlib import Path

import pytest

from scripts import json_atomico


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
