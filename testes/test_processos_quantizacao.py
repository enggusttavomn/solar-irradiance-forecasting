import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

import pytest

from scripts.processos_quantizacao import (TravaDiretorio, ExecucaoOcupada, ProcessoProprio,
                                           identidade, mesma_instancia, processos_da_fila_ativos)
from scripts.coordenacao_quantizacao import auditoria_publicavel, controles_solicitados, aguardar_filas


def esperar(fn, segundos=40):
    limite = time.monotonic() + segundos
    while not fn():
        if time.monotonic() >= limite:
            raise AssertionError('Prazo do processo auxiliar excedido')
        time.sleep(.05)


def test_trava_exclusiva_por_diretorio_e_recuperavel(tmp_path):
    with TravaDiretorio(tmp_path):
        with pytest.raises(ExecucaoOcupada):
            with TravaDiretorio(tmp_path):
                pass
        with TravaDiretorio(tmp_path / 'outra_fila'):
            pass
    with TravaDiretorio(tmp_path):
        pass
    assert (tmp_path / '.execucao.lock').exists()


def test_pid_reciclado_nao_e_instancia_original():
    real = identidade(os.getpid())
    assert mesma_instancia(real)
    assert not mesma_instancia({**real, 'creation_time': '0'})


def test_job_encerra_somente_arvore_criada(tmp_path):
    alvo = tmp_path / 'neto.json'
    neto = "import os,time,json;from pathlib import Path;Path(" + repr(str(alvo)) + ").write_text(json.dumps({'pid':os.getpid()}));time.sleep(120)"
    pai = "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c'," + repr(neto) + "]);time.sleep(120)"
    proprio = ProcessoProprio([sys.executable, '-c', pai])
    try:
        esperar(alvo.exists)
        pid_neto = json.loads(alvo.read_text())['pid']
        recibo_neto = identidade(pid_neto)
        assert proprio.ativos() >= 2
        proprio.encerrar()
        assert proprio.poll() is not None
        assert not mesma_instancia(recibo_neto)
        assert identidade(os.getpid()) is not None
    finally:
        proprio.fechar()


def test_saida_pai_nao_significa_fim_da_arvore(tmp_path):
    alvo = tmp_path / 'neto.json'
    neto = "import os,time;from pathlib import Path;Path(" + repr(str(alvo)) + ").write_text(str(os.getpid()));time.sleep(120)"
    pai = "import subprocess,sys;subprocess.Popen([sys.executable,'-c'," + repr(neto) + "])"
    proprio = ProcessoProprio([sys.executable, '-c', pai])
    try:
        esperar(alvo.exists)
        esperar(lambda: proprio.processo.poll() is not None)
        assert proprio.poll() is None
        proprio.encerrar()
        assert identidade(int(alvo.read_text())) is None
    finally:
        proprio.fechar()


def test_identidade_de_fila_reciclada_nao_bloqueia():
    real = identidade(os.getpid())
    assert processos_da_fila_ativos({'identidade_runner': {**real, 'creation_time': '0'}}) == []


def test_fila_terminal_ainda_ativa_e_aguardada(tmp_path):
    path = tmp_path / 'runner.json'
    fila = {'regime': 'atual', 'modo': 'completa', 'etapa': 'concluida', 'pid_runner': 999999,
            'atualizado_em_utc': '2026-09-30T00:00:00+00:00', 'falhas': []}
    path.write_text(json.dumps(fila))
    with patch('scripts.coordenacao_quantizacao.processos_da_fila_ativos', side_effect=[[{'pid':1}], [], []]), \
         patch('scripts.coordenacao_quantizacao.time.sleep') as dormir:
        locks, estados = aguardar_filas([path], lambda *a, **k: None, intervalo=.01)
        try:
            assert dormir.call_count == 1
            with pytest.raises(ExecucaoOcupada):
                with TravaDiretorio(path.parent):
                    pass
        finally:
            locks.close()


def fixture_falha(tmp_path):
    pasta = tmp_path / 'atual/daily_30/gru'
    pasta.mkdir(parents=True)
    aceite = pasta / 'aceite_controle_gpu_validacao.json'
    (pasta / 'controle_validacao_divergencia.json').write_text(json.dumps({
        'novo_controle_por_dispositivo': True, 'dispositivo': 'cuda', 'dispositivo_original': 'cpu',
        'alvos_primarios_bitexatos': True}))
    log = tmp_path / 'job.log'
    log.write_text(f'ValueError: Controle GPU exige auditoria independente registrada em {aceite}\n')
    return {'etapa': 'erro', 'falhas': [{'modelo': 'GRU', 'tarefa': 'daily_30', 'fase': 'selecao',
                                       'returncode': 1, 'log': str(log)}]}, pasta


def test_controle_explicitamente_solicitado(tmp_path):
    fila, pasta = fixture_falha(tmp_path)
    assert controles_solicitados(fila, tmp_path) == [(pasta, 'validacao')]


@pytest.mark.parametrize('alteracao', ['erro_tecnico', 'fora_escopo', 'sem_divergencia', 'aceite_previo', 'cpu', 'sumario'])
def test_controles_nao_aprovam_falha_tecnica(tmp_path, alteracao):
    fila, pasta = fixture_falha(tmp_path)
    if alteracao == 'erro_tecnico':
        Path(fila['falhas'][0]['log']).write_text('RuntimeError: CUDA out of memory\n')
    elif alteracao == 'fora_escopo':
        fila['falhas'][0]['modelo'] = 'Transformer'
    elif alteracao == 'sem_divergencia':
        (pasta / 'controle_validacao_divergencia.json').unlink()
    elif alteracao == 'aceite_previo':
        (pasta / 'aceite_controle_gpu_validacao.json').write_text('{}')
    elif alteracao == 'cpu':
        (pasta / 'controle_validacao_divergencia.json').write_text('{}')
    else:
        fila['falhas'].append({'tipo': 'OSError', 'mensagem': 'disk full'})
    with pytest.raises(ValueError):
        controles_solicitados(fila, tmp_path)


def test_todas_falhas_devem_ser_elegiveis(tmp_path):
    fila, pasta = fixture_falha(tmp_path)
    outro = tmp_path / 'outro.log'
    outro.write_text('RuntimeError: CUDA out of memory\n')
    fila['falhas'].append({**fila['falhas'][0], 'modelo': 'LSTM', 'log': str(outro)})
    with pytest.raises(ValueError):
        controles_solicitados(fila, tmp_path)


def test_auditoria_completa_exige_44_pares_e_replay():
    a = {'ok': True, 'publicavel': True, 'modo': 'completa', 'regime': 'atual',
         'escopo_completo': True, 'replay_novo_executado': True, 'pares_verificados': 44}
    assert auditoria_publicavel(a, 'atual')
    for key, valor in [('modo', 'smoke'), ('pares_verificados', 43), ('regime', 'historico_1998_2022'),
                       ('replay_novo_executado', False)]:
        assert not auditoria_publicavel({**a, key: valor}, 'atual')


def test_runner_dispatch_arima_restrito():
    from types import SimpleNamespace
    from scripts.rodar_quantizacao_todos_modelos import comando
    args = SimpleNamespace(regime='atual', smoke=False, saida=Path('tmp'), protocolo=None)
    assert 'codigo_fonte.experimento_arima_horario_controle_auditado_v1' in comando(args, 'hourly_72_extension', 'ARIMA', 'selecao')
    for regime, tarefa, smoke in [('atual', 'daily_30', False), ('atual', 'hourly_72_extension', True),
                                  ('historico_1998_2022', 'hourly_72_extension', False)]:
        args.regime, args.smoke = regime, smoke
        assert 'codigo_fonte.experimento_quantizacao_estatisticos' in comando(args, tarefa, 'ARIMA', 'selecao')
