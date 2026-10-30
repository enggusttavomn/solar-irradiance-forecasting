from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from codigo_fonte.analises_e_relatorios import auditar_quantizacao_todos_modelos as auditor
from codigo_fonte.experimentos.rodar_quantizacao_todos_modelos import comando


@pytest.mark.parametrize('regime', ['atual', 'historico_1998_2022', 'historico_curto_pareado'])
@pytest.mark.parametrize('tarefa', ['daily_30', 'hourly_72_extension'])
@pytest.mark.parametrize('modelo', ['Transformer', 'Informer'])
def test_atencao_mesma_politica_nos_tres_regimes(tmp_path, regime, tarefa, modelo):
    args = SimpleNamespace(regime=regime, saida=tmp_path, smoke=False, protocolo=None)
    for fase in ('selecao', 'refit'):
        cmd = comando(args, tarefa, modelo, fase)
        assert cmd[cmd.index('-m')+1] == 'codigo_fonte.experimentos.experimento_atencao_deterministica_v1'
        assert '--dispositivo' not in cmd


@pytest.mark.parametrize('tarefa,modelo', [('monthly_1','Transformer'), ('monthly_6','Informer'),
                                         ('daily_30','GRU'), ('hourly_72_extension','LSTM'),
                                         ('daily_30','TimesNet'), ('daily_30','XGBoost')])
def test_fora_do_escopo_preserva_motor(tmp_path, tarefa, modelo):
    args = SimpleNamespace(regime='atual', saida=tmp_path, smoke=False, protocolo=None)
    cmd = comando(args, tarefa, modelo, 'selecao')
    assert cmd[cmd.index('-m')+1] == 'codigo_fonte.experimentos.experimento_quantizacao_concorrentes'


def test_replay_legado_preserva_execucao_existente(monkeypatch):
    monkeypatch.setattr(auditor, '_replay_aprendido', lambda *args: 'legado')
    assert auditor.replay_aprendido(None, None, 'Transformer', 'q64', 'selecao', {}) == 'legado'


def test_replay_estrito_recusa_politica_desconhecida():
    with pytest.raises(AssertionError, match='Politica numerica desconhecida'):
        auditor.replay_aprendido(None, None, 'Transformer', 'q64', 'selecao',
                                {'execucao_numerica': {'id':'desconhecida'}})


def test_replay_recusa_contrato_estrito_divergente_e_restaura(monkeypatch):
    from codigo_fonte.experimentos import experimento_atencao_deterministica_v1 as estrito
    eventos = []
    @contextmanager
    def contexto(**kwargs):
        eventos.append('entrou')
        try:
            yield
        finally:
            eventos.append('saiu')
    monkeypatch.setattr(estrito, 'ativar_adaptador', contexto)
    monkeypatch.setattr(estrito, 'construir_contrato', lambda *args: {'outro':'contrato'})
    monkeypatch.setattr(auditor, '_replay_aprendido', lambda *args: pytest.fail('Replay indevido'))
    contrato = {'execucao_numerica': {'id':'atencao_cuda_deterministica_v1'}, 'codigo':{}}
    with pytest.raises(AssertionError, match='Contrato estrito difere'):
        auditor.replay_aprendido(None, None, 'Transformer', 'q64', 'selecao', contrato)
    assert eventos == ['entrou', 'saiu']
