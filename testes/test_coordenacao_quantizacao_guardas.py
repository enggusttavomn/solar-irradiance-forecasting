import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

import pytest

from scripts.json_atomico import salvar_json
from scripts.processos_quantizacao import TravaDiretorio, ProcessoProprio, ExecucaoOcupada
from scripts.coordenar_quantizacao_historica import conferir_porta_atual, aguardar_atual
from scripts.metricas_quantizacao_todos import sha256


@pytest.mark.parametrize('tentativas', [0, -1, 1.5, True])
def test_json_tentativas_invalidas_nao_criam_arquivos(tmp_path, tentativas):
    with pytest.raises(ValueError):
        salvar_json({}, tmp_path / 'novo.json', tentativas=tentativas)
    assert not list(tmp_path.iterdir())


def test_json_cleanup_nao_mascara_erro_original(tmp_path):
    with patch.object(Path, 'replace', side_effect=PermissionError('erro original')), \
         patch.object(Path, 'unlink', side_effect=OSError('erro cleanup')):
        with pytest.raises(PermissionError, match='erro original'):
            salvar_json({}, tmp_path / 'novo.json')


def test_lock_entre_processos_e_liberado_no_encerramento(tmp_path):
    pronto = tmp_path / 'pronto'
    pasta = tmp_path / 'trava'
    codigo = ('from scripts.processos_quantizacao import TravaDiretorio;from pathlib import Path;import time\n'
              + 'with TravaDiretorio(' + repr(str(pasta)) + '):\n'
              + ' Path(' + repr(str(pronto)) + ').write_text(\'pronto\')\n time.sleep(120)\n')
    p = ProcessoProprio([sys.executable, '-c', codigo])
    try:
        limite = time.monotonic() + 40
        while not pronto.exists() and time.monotonic() < limite:
            time.sleep(.05)
        assert pronto.exists()
        with pytest.raises(ExecucaoOcupada):
            with TravaDiretorio(pasta):
                pass
        with TravaDiretorio(tmp_path / 'outra_fila'):
            pass
        p.encerrar()
        with TravaDiretorio(pasta):
            pass
    finally:
        p.fechar()


def porta(tmp_path):
    metricas = tmp_path / 'metricas.csv'
    metricas.write_text('teste')
    auditoria = {'ok': True, 'publicavel': True, 'modo': 'completa', 'regime': 'atual',
                 'escopo_completo': True, 'replay_novo_executado': True, 'pares_verificados': 44,
                 'metricas': {'path': str(metricas), 'sha256': sha256(metricas)}}
    path = tmp_path / 'auditoria.json'
    path.write_text(json.dumps(auditoria))
    status = {'etapa': 'pronto_para_revisao_visual', 'auditoria_sha256': sha256(path)}
    return status, auditoria, path


def test_porta_historica_exige_mesma_auditoria_publicavel(tmp_path):
    s, a, path = porta(tmp_path)
    conferir_porta_atual(s, a, path)
    for key, valor in [('publicavel', False), ('modo', 'smoke'), ('pares_verificados', 43)]:
        with pytest.raises(ValueError):
            conferir_porta_atual(s, {**a, key: valor}, path)
    with pytest.raises(ValueError):
        conferir_porta_atual({**s, 'auditoria_sha256': 'alterado'}, a, path)
    Path(a['metricas']['path']).write_text('alterado')
    with pytest.raises(ValueError):
        conferir_porta_atual(s, a, path)


def test_historico_falha_sem_iniciar_se_atual_falhou(tmp_path):
    path = tmp_path / 'status.json'
    path.write_text(json.dumps({'etapa': 'erro'}))
    with pytest.raises(RuntimeError, match='nao sera iniciado'):
        aguardar_atual(path, tmp_path / 'auditoria.json', lambda *a, **k: None, intervalo=0)


def test_historico_retencao_da_trava_atual(tmp_path):
    s, a, path = porta(tmp_path)
    sp = tmp_path / 'atual/status.json'
    sp.parent.mkdir()
    sp.write_text(json.dumps(s))
    with patch('scripts.coordenar_quantizacao_historica.processos_da_fila_ativos', return_value=[]):
        trava = aguardar_atual(sp, path, lambda *a, **k: None, intervalo=0)
        try:
            with pytest.raises(ExecucaoOcupada):
                with TravaDiretorio(sp.parent):
                    pass
        finally:
            trava.__exit__(None, None, None)
