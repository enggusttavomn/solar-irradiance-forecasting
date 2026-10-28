import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts import processos_quantizacao as processos
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
        # Observe a saida sem colher o lider fora da API de ProcessoProprio.
        esperar(lambda: identidade(proprio.pid) is None)
        assert proprio.ativos() >= 1
        assert proprio.poll() is None
        proprio.encerrar()
        assert identidade(int(alvo.read_text())) is None
    finally:
        proprio.fechar()


def test_identidade_de_fila_reciclada_nao_bloqueia():
    real = identidade(os.getpid())
    assert processos_da_fila_ativos({'identidade_runner': {**real, 'creation_time': '0'}}) == []


def processo_posix_simulado():
    proprio = ProcessoProprio.__new__(ProcessoProprio)
    proprio.processo = SimpleNamespace(pid=77)
    proprio._criacao_sessao_posix = '100'
    proprio._instancias_posix = {77: '100'}
    proprio._sessao_posix_encerrada = False
    return proprio


def registro_posix(pid, *, estado='S', grupo=77, sessao=77, criacao='110', ppid=1):
    return {'pid': pid, 'creation_time': criacao, 'estado': estado,
            'grupo': grupo, 'sessao': sessao, 'ppid': ppid}


def test_sessao_posix_inclui_orfao_e_outro_grupo_mas_nao_zumbi_ou_estranho():
    proprio = processo_posix_simulado()
    snapshot = {77: registro_posix(77, estado='Z', criacao='100'),
                88: registro_posix(88, grupo=88),
                89: registro_posix(89, estado='Z'),
                90: registro_posix(90, sessao=90, grupo=90)}
    with patch.object(processos, '_snapshot_posix', return_value=snapshot):
        assert [p['pid'] for p in proprio._membros_posix()] == [88]
    snapshot.pop(77)
    with patch.object(processos, '_snapshot_posix', return_value=snapshot):
        assert [p['pid'] for p in proprio._membros_posix()] == [88]


def test_sessao_posix_reciclada_nao_passa_a_ser_propria():
    proprio = processo_posix_simulado()
    snapshot = {77: registro_posix(77, criacao='200'),
                88: registro_posix(88, criacao='210')}
    with patch.object(processos, '_snapshot_posix', return_value=snapshot):
        assert proprio._membros_posix() == []
    assert proprio._sessao_posix_encerrada


def test_sessao_posix_vazia_nao_e_reativada_por_reuso_posterior():
    proprio = processo_posix_simulado()
    with patch.object(processos, '_snapshot_posix', side_effect=[{}, {
            88: registro_posix(88, criacao='210')}]) as snapshot:
        assert proprio._membros_posix() == []
        assert proprio._membros_posix() == []
    snapshot.assert_called_once()


def test_sid_reciclado_sem_lider_nao_adota_orfao_desconhecido():
    proprio = processo_posix_simulado()
    # A sessao original acabou entre consultas. Um novo lider usou 77, saiu e
    # deixou seu proprio filho: nem o SID nem a data mais recente o tornam nosso.
    snapshot = {88: registro_posix(88, criacao='210')}
    with patch.object(processos, '_snapshot_posix', return_value=snapshot):
        assert proprio._membros_posix() == []
    assert 88 not in proprio._instancias_posix


def test_descendente_em_nova_sessao_e_acompanhado_por_identidade():
    proprio = processo_posix_simulado()
    pai = registro_posix(77, criacao='100')
    filho = registro_posix(88, ppid=77, grupo=88, sessao=88)
    with patch.object(processos, '_snapshot_posix', return_value={77: pai, 88: filho}):
        assert {p['pid'] for p in proprio._membros_posix()} == {77, 88}
    orfao = registro_posix(99, ppid=1, grupo=88, sessao=88, criacao='120')
    with patch.object(processos, '_snapshot_posix', return_value={88: filho, 99: orfao}):
        assert {p['pid'] for p in proprio._membros_posix()} == {88, 99}


def test_sessao_posix_sem_identidade_nao_assume_que_esta_vazia():
    proprio = processo_posix_simulado()
    proprio._criacao_sessao_posix = None
    with patch.object(processos, '_snapshot_posix', return_value={}):
        with pytest.raises(RuntimeError, match='Identidade da sessao'):
            proprio._membros_posix()


def test_sessao_posix_confirma_vazio_depois_do_ultimo_fork():
    proprio = processo_posix_simulado()
    lider = registro_posix(77, estado='Z', criacao='100')
    filho = registro_posix(88)
    with patch.object(processos, '_snapshot_posix', side_effect=[{77: lider},
                                                               {77: lider, 88: filho}]):
        assert [p['pid'] for p in proprio._membros_posix()] == [88]
    assert not proprio._sessao_posix_encerrada


@pytest.mark.parametrize('terminou', [False, True])
def test_poll_posix_observa_saida_sem_colher_antes_do_snapshot(terminou):
    proprio = processo_posix_simulado()
    ordem = []
    proprio.processo.returncode = None
    proprio.processo.poll = lambda: ordem.append('colher') or 0
    def observar(*args):
        ordem.append('observar')
        return object() if terminou else None
    with patch.object(processos.os, 'name', 'posix'), \
         patch.object(processos.os, 'P_PID', 1, create=True), \
         patch.object(processos.os, 'WEXITED', 4, create=True), \
         patch.object(processos.os, 'WNOHANG', 1, create=True), \
         patch.object(processos.os, 'WNOWAIT', 16, create=True), \
         patch.object(processos.os, 'waitid', side_effect=observar, create=True), \
         patch.object(proprio, '_membros_posix', side_effect=lambda: ordem.append('snapshot') or []):
        assert proprio.poll() == (0 if terminou else None)
    assert ordem == (['observar', 'snapshot', 'colher'] if terminou
                     else ['observar', 'snapshot'])


@pytest.mark.parametrize('atual', [None, registro_posix(88, criacao='200'),
                                  registro_posix(88, estado='Z')])
def test_sinal_posix_nao_atinge_pid_reciclado_ou_morto(atual):
    with patch.object(processos.os, 'pidfd_open', return_value=35, create=True), \
         patch.object(processos.signal, 'pidfd_send_signal', create=True) as enviar, \
         patch.object(processos.os, 'close') as fechar, \
         patch.object(processos, '_estatistica_posix', return_value=atual):
        processos._sinalizar_instancia_posix(registro_posix(88), 9)
    enviar.assert_not_called()
    fechar.assert_called_once_with(35)


def test_sinal_posix_usa_descritor_da_instancia_confirmada():
    with patch.object(processos.os, 'pidfd_open', return_value=35, create=True), \
         patch.object(processos.signal, 'pidfd_send_signal', create=True) as enviar, \
         patch.object(processos.os, 'close') as fechar, \
         patch.object(processos, '_estatistica_posix', return_value=registro_posix(88)):
        processos._sinalizar_instancia_posix(registro_posix(88), 9)
    enviar.assert_called_once_with(35, 9)
    fechar.assert_called_once_with(35)


def test_sinal_posix_sem_pidfd_falha_fechado():
    with patch.object(processos.os, 'pidfd_open', None, create=True), \
         patch.object(processos.signal, 'pidfd_send_signal', create=True) as enviar:
        with pytest.raises(OSError, match='pidfd'):
            processos._sinalizar_instancia_posix(registro_posix(88), 9)
    enviar.assert_not_called()


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
