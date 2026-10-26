import json
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.json_atomico import salvar_json


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
