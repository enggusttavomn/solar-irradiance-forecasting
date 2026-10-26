"""Fixtures pequenas: painel observa registros, sem carregar modelos ou dados."""
from datetime import datetime, timedelta, timezone
import json
import pytest
from scripts import painel_progresso_quantizacao as p

AGORA = datetime(2026, 9, 30, 15, 0, tzinfo=timezone.utc)

def gravar(path, dados):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dados), encoding='utf-8')
    return path

def par(raiz, regime='atual', tarefa='daily_30', modelo='GRU', *,
        modo='completa', etapa='selecao_concluida', importado=False):
    pasta = raiz / p.RESULTADOS / regime / tarefa / p.slug(modelo)
    gravar(pasta / 'status.json', {'modo': modo, 'etapa': etapa, 'reutilizado': importado})
    gravar(pasta / ('contrato.json' if importado else 'contrato_execucao.json'),
           {'modo': modo, 'regime': regime, 'tarefa': tarefa, 'modelo': modelo,
            'sha256_contrato': 'hash-fixture'})
    flag = 'selecao_concluida_antes_do_teste' if importado else 'selecao_concluida_antes_refit'
    gravar(pasta / 'selecao_congelada.json', {flag: True, 'contrato_sha256': 'hash-fixture'})
    return pasta

def estado(raiz, checar=lambda registro: True):
    return p.montar_estado(raiz, agora=AGORA, checar=checar)

def audit(regime):
    return {'ok': True, 'publicavel': True, 'escopo_completo': True,
            'replay_novo_executado': True, 'modo': 'completa',
            'regime': regime, 'pares_verificados': 44}

def test_denominadores_fixos_e_nao_percentual_de_tempo(tmp_path):
    e = estado(tmp_path)
    assert len(e['regimes']) == 3
    for grupo in e['regimes']:
        assert grupo['total'] == 44
        assert len(grupo['pares']) == 44
        assert len({(x['tarefa'], x['modelo']) for x in grupo['pares']}) == 44
        assert grupo['selecao'] == grupo['refit'] == 0
    assert e['foco']['feito'] == 0
    assert e['foco']['total'] == 44
    assert not e['concluido']

def test_conta_44_pares_uma_vez_mesmo_com_arquivos_extras(tmp_path):
    for tarefa in p.TAREFAS:
        for modelo in p.MODELOS:
            par(tmp_path, tarefa=tarefa, modelo=modelo, etapa='concluida')
    par(tmp_path, modelo='modelo_estranho')
    par(tmp_path, tarefa='smoke_extra')
    g = estado(tmp_path)['regimes'][0]
    assert g['selecao'] == g['refit'] == 44
    assert not g['auditoria']

def test_quatro_timesnet_importadas_contam_selecao_e_refit(tmp_path):
    for tarefa in p.TAREFAS:
        par(tmp_path, tarefa=tarefa, modelo='TimesNet', etapa='concluida', importado=True)
    e = estado(tmp_path)
    atual = e['regimes'][0]
    assert atual['selecao'] == atual['refit'] == 4
    assert sum(x['reutilizado'] for x in atual['pares']) == 4
    assert not atual['auditoria']
    assert not e['concluido']

def test_nao_conta_smoke(tmp_path):
    par(tmp_path, modo='smoke', etapa='concluida')
    g = estado(tmp_path)['regimes'][0]
    assert g['selecao'] == g['refit'] == 0

def test_contrato_smoke_nao_aceita_status_completa(tmp_path):
    pasta = par(tmp_path, modo='smoke', etapa='concluida')
    gravar(pasta / 'status.json', {'modo': 'completa', 'etapa': 'concluida'})
    g = estado(tmp_path)['regimes'][0]
    assert g['selecao'] == g['refit'] == 0

def test_selecao_parcial_nao_incrementa_par(tmp_path):
    pasta = par(tmp_path, etapa='selecao')
    (pasta / 'selecao_congelada.json').unlink()
    gravar(pasta / 'q64/selecao/seed11.json', {'concluido_em_utc': AGORA.isoformat()})
    g = estado(tmp_path)['regimes'][0]
    assert g['selecao'] == g['refit'] == 0

def test_selecao_congelada_preservada_durante_refit(tmp_path):
    par(tmp_path, etapa='refit')
    g = estado(tmp_path)['regimes'][0]
    assert g['selecao'] == 1
    assert g['refit'] == 0

def test_refit_estatistico_sem_campo_publicavel_nao_e_auditoria(tmp_path):
    par(tmp_path, modelo='ARIMA', etapa='concluida')
    e = estado(tmp_path)
    assert e['regimes'][0]['refit'] == 1
    assert not e['regimes'][0]['auditoria']
    assert not e['concluido']

@pytest.mark.parametrize('campo,valor', [
    ('ok', False), ('publicavel', False), ('escopo_completo', False),
    ('replay_novo_executado', False), ('modo', 'smoke'),
    ('pares_verificados', 43), ('regime', 'historico_curto_pareado'),
])
def test_auditoria_incompleta_rejeitada(campo, valor):
    a = audit('atual')
    a[campo] = valor
    assert not p.auditoria_pronta(a, 'atual')

def test_auditoria_completa_reconhecida(tmp_path):
    gravar(tmp_path / p.BASE / 'auditoria_final_atual/auditoria.json', audit('atual'))
    assert estado(tmp_path)['regimes'][0]['auditoria']

def test_processo_morto_com_heartbeat_recente(tmp_path):
    gravar(tmp_path / p.BASE / p.RUNNERS[0], {
        'modo': 'completa', 'regime': 'atual', 'etapa': 'selecao',
        'identidade_runner': {'pid': 123, 'creation_time': '456'},
        'atualizado_em_utc': AGORA.isoformat(),
        'processos': [{'modelo': 'GRU', 'tarefa': 'daily_30'}],
    })
    e = estado(tmp_path, checar=lambda registro: False)
    assert e['filas'][0]['situacao'] == 'parado'
    assert not e['ativos']
    assert e['alertas']

def test_heartbeat_antigo_nao_e_atividade_confirmada():
    e = {'etapa': 'selecao', 'identidade_runner': {'pid': 123, 'creation_time': '456'},
         'atualizado_em_utc': (AGORA - timedelta(minutes=10)).isoformat()}
    assert p.situacao_processo(e, AGORA, lambda registro: True) == 'sem_atualizacao'

def test_erro_terminal_nao_se_confunde_com_processo_ativo():
    assert p.situacao_processo({'etapa': 'erro'}, AGORA, lambda r: True) == 'erro'

def test_erro_na_verificacao_processo_e_explicito():
    def falhar(registro):
        raise OSError('fixture')
    e = {'etapa': 'selecao', 'identidade_runner': {'pid': 123},
         'atualizado_em_utc': AGORA.isoformat()}
    assert p.situacao_processo(e, AGORA, falhar) == 'processo_nao_confirmado'

@pytest.mark.parametrize('conteudo', ['{', '[]', 'null'])
def test_json_invalido_nao_reutiliza_leitura_anterior(tmp_path, conteudo):
    path = gravar(tmp_path / 'registro.json', {'etapa': 'concluida'})
    leitor = p.Leitor()
    assert leitor.json(path)['etapa'] == 'concluida'
    path.write_text(conteudo, encoding='utf-8')
    assert leitor.json(path) == {}
    assert leitor.avisos

def test_json_excluido_limpa_cache(tmp_path):
    path = gravar(tmp_path / 'registro.json', {'etapa': 'concluida'})
    leitor = p.Leitor()
    leitor.json(path)
    path.unlink()
    assert leitor.json(path) == {}

def test_pdf_antigo_nao_significa_entrega(tmp_path):
    doc = tmp_path / 'documentacao'
    doc.mkdir()
    (doc / 'tabela_resultados_ghi_2024.pdf').write_bytes(b'pdf antigo fixture')
    e = estado(tmp_path)
    assert all(x['etapa'] == 'aguardando' for x in e['entregas'])
    assert not e['concluido']

def test_pdf_gerado_ainda_exige_revisao_e_entrega(tmp_path):
    gravar(tmp_path / p.BASE / 'pdf_atual/manifesto.json', {'pdf': {'sha256': 'novo', 'paginas': 10}})
    e = estado(tmp_path)
    assert e['entregas'][0]['etapa'] == 'revisao_pendente'
    assert not e['concluido']

def test_recibo_antigo_com_hash_diferente_nao_e_entrega_nova(tmp_path):
    gravar(tmp_path / p.BASE / 'pdf_atual/manifesto.json', {'pdf': {'sha256': 'novo', 'paginas': 10}})
    gravar(tmp_path / p.BASE / 'entrega_atual.json', {
        'entregue_em_utc': AGORA.isoformat(), 'evidencias': {'visual': 'hash'},
        'pdf': {'sha256': 'antigo', 'path': str(tmp_path / 'documentacao/tabela_resultados_ghi_2024.pdf')},
    })
    assert estado(tmp_path)['entregas'][0]['etapa'] == 'revisao_pendente'

def test_recibos_sozinhos_nao_concluem_experimentos(tmp_path):
    for pasta, nome in [('pdf_atual', 'tabela_resultados_ghi_2024.pdf'),
                        ('pdf_historico', 'tabela_resultados_ghi_1998_2022.pdf')]:
        gravar(tmp_path / p.BASE / pasta / 'manifesto.json', {'pdf': {'sha256': nome, 'paginas': 10}})
        gravar(tmp_path / p.BASE / pasta / 'entrega.json', {
            'entregue_em_utc': AGORA.isoformat(), 'evidencias': {'visual': 'hash'},
            'pdf': {'sha256': nome, 'path': str(tmp_path / 'documentacao' / nome)},
        })
    assert not estado(tmp_path)['concluido']

def test_log_append_mostra_so_execucao_atual_e_cache_de_semente(tmp_path):
    pasta = par(tmp_path, etapa='selecao')
    gravar(pasta / 'contrato_execucao.json', {'modo': 'completa',
           'sha256_contrato': 'hash-fixture', 'parametros': {'sementes': [11, 23]}})
    cache = pasta / 'q64/selecao/seed11.npz'
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b'fixture sem arrays')
    gravar(cache.with_suffix('.json'), {'concluido_em_utc': AGORA.isoformat(),
           'fase': 'selecao', 'seed': 11, 'variante': 'q64', 'contrato_sha256': 'hash-fixture'})
    log = tmp_path / 'execucao.log'
    log.write_text('\nInicio antigo\ndaily_30/GRU/q256/selecao seed=23 inicio\n'
                   '\nInicio novo\ndaily_30/GRU/q64/selecao seed=23 inicio\n', encoding='utf-8')
    detalhe = p.detalhe_job(tmp_path, {'regime': 'atual', 'etapa': 'selecao'},
              {'tarefa': 'daily_30', 'modelo': 'GRU', 'log': str(log), 'inicio': AGORA.isoformat()}, p.Leitor(), AGORA)
    assert detalhe['sementes_concluidas'] == 1
    assert detalhe['sementes_total'] == 8
    assert '/q64/' in detalhe['atividade']
    assert '/q256/' not in detalhe['atividade']

def runner(raiz, path, *, etapa='refit', atualizado=AGORA, inicio=None,
           processos=(), falhas=()):
    return gravar(raiz / p.BASE / path, {
        'modo': 'completa', 'regime': 'atual', 'etapa': etapa,
        'iniciado_em_utc': (inicio or atualizado).isoformat(),
        'atualizado_em_utc': atualizado.isoformat(),
        'identidade_runner': {'pid': 123, 'creation_time': '456'},
        'processos': list(processos), 'falhas': list(falhas),
    })


def test_falha_individual_visivel_enquanto_outro_job_executa(tmp_path):
    runner(tmp_path, p.RUNNERS[3],
           processos=[{'modelo': 'GRU', 'tarefa': 'daily_30'}],
           falhas=[{'modelo': 'XGBoost', 'tarefa': 'hourly_72_extension',
                    'fase': 'refit', 'returncode': 1}])
    e = estado(tmp_path)
    assert e['filas'][0]['situacao'] == 'ativo'
    assert len(e['ativos']) == 1
    assert e['falhas'][0]['modelo'] == 'XGBoost'
    assert any('XGBoost' in alerta and 'pendente' in alerta for alerta in e['alertas'])


def test_recuperacao_ativa_substitui_erro_antigo_sem_ocultar_xgboost(tmp_path):
    antigo = AGORA - timedelta(hours=1)
    runner(tmp_path, p.RUNNERS[3], etapa='erro', atualizado=antigo,
           falhas=[{'modelo': modelo, 'tarefa': tarefa, 'fase': 'refit'}
                   for tarefa, modelo in [('daily_30', 'GRU'),
                                          ('hourly_72_extension', 'XGBoost')]])
    gravar(tmp_path / p.BASE / 'coordenacao_atual/status.json', {
        'etapa': 'erro', 'atualizado_em_utc': antigo.isoformat(),
        'erro': 'Falha fora da politica de migracao CPU/CUDA.'})
    gravar(tmp_path / p.BASE / 'recuperacao_20261001/escopo.json', {
        'pares': [['daily_30', 'GRU']],
        'outras_falhas_em_investigacao': ['hourly_72_extension/XGBoost']})
    runner(tmp_path, p.RECUPERACAO, etapa='verificacao_controle',
           processos=[{'modelo': 'GRU', 'tarefa': 'daily_30'}])
    e = estado(tmp_path)
    assert e['filas'][0]['arquivo'] == p.RECUPERACAO
    assert e['filas'][0]['situacao'] == 'ativo'
    assert e['filas'][1]['situacao'] == 'substituida_pela_recuperacao'
    assert e['coordenadores'][0]['situacao'] == 'em_recuperacao'
    assert [f['modelo'] for f in e['falhas']] == ['XGBoost']
    assert all('GRU' not in alerta for alerta in e['alertas'])
    assert any('XGBoost' in alerta for alerta in e['alertas'])
    assert e['ativos'][0]['fase'] == 'verificacao_controle'
    assert e['ativos'][0]['sementes_total'] == 0
    assert e['ativos'][0]['estimativa']['min_s'] is None
    assert not e['concluido']


def test_recuperacao_parada_nao_oculta_falhas_anteriores(tmp_path):
    antigo = AGORA - timedelta(hours=1)
    runner(tmp_path, p.RUNNERS[3], etapa='erro', atualizado=antigo,
           falhas=[{'modelo': 'GRU', 'tarefa': 'daily_30', 'fase': 'refit'}])
    gravar(tmp_path / p.BASE / 'recuperacao_20261001/escopo.json', {
        'pares': [['daily_30', 'GRU']]})
    runner(tmp_path, p.RECUPERACAO,
           processos=[{'modelo': 'GRU', 'tarefa': 'daily_30'}])
    e = estado(tmp_path, checar=lambda registro: False)
    assert not e['ativos']
    assert e['filas'][0]['situacao'] == 'parado'
    assert e['filas'][1]['situacao'] == 'erro'
    assert e['falhas'][0]['modelo'] == 'GRU'


def test_recuperacao_antiga_nao_substitui_fila_integral_nova(tmp_path):
    antigo = AGORA - timedelta(hours=1)
    runner(tmp_path, p.RECUPERACAO, inicio=antigo)
    runner(tmp_path, p.RUNNERS[3], etapa='erro',
           falhas=[{'modelo': 'XGBoost', 'tarefa': 'hourly_72_extension',
                    'fase': 'refit'}])
    e = estado(tmp_path)
    assert e['filas'][1]['situacao'] == 'erro'
    assert any('erro' in alerta for alerta in e['alertas'])


def test_falha_antiga_resolvida_nao_continua_no_aviso(tmp_path):
    par(tmp_path, etapa='concluida')
    runner(tmp_path, p.RUNNERS[3],
           falhas=[{'modelo': 'GRU', 'tarefa': 'daily_30', 'fase': 'refit'}])
    e = estado(tmp_path)
    assert not e['falhas']
    assert not e['alertas']


def test_falha_da_recuperacao_ainda_aparece_no_proprio_escopo(tmp_path):
    antigo = AGORA - timedelta(hours=1)
    falha = {'modelo': 'GRU', 'tarefa': 'daily_30', 'fase': 'refit'}
    runner(tmp_path, p.RUNNERS[3], etapa='erro', atualizado=antigo, falhas=[falha])
    gravar(tmp_path / p.BASE / 'recuperacao_20261001/escopo.json', {
        'pares': [['daily_30', 'GRU']]})
    runner(tmp_path, p.RECUPERACAO, falhas=[falha],
           processos=[{'modelo': 'LSTM', 'tarefa': 'daily_30'}])
    e = estado(tmp_path)
    assert len(e['ativos']) == 1
    assert len(e['falhas']) == 1
    assert any('GRU' in alerta for alerta in e['alertas'])

def test_recuperacao_xgboost_ativa_usa_refit_e_metadados_do_proprio_contrato(tmp_path):
    antigo = AGORA - timedelta(hours=1)
    falha = {'modelo': 'XGBoost', 'tarefa': 'hourly_72_extension', 'fase': 'refit'}
    runner(tmp_path, p.RUNNERS[3], etapa='erro', atualizado=antigo, falhas=[falha])
    runner(tmp_path, p.RECUPERACAO, etapa='concluida', atualizado=antigo)
    pasta = par(tmp_path, tarefa='hourly_72_extension', modelo='XGBoost', etapa='refit')
    gravar(pasta / 'contrato_execucao.json', {
        'modo': 'completa', 'sha256_contrato': 'contrato-xgb',
        'parametros': {'sementes': [42]}})
    cache = pasta / 'sem_quantizacao/refit/seed42.npz'
    cache.parent.mkdir(parents=True)
    cache.write_bytes(b'fixture sem arrays')
    gravar(cache.with_suffix('.json'), {
        'concluido_em_utc': AGORA.isoformat(), 'fase': 'refit', 'seed': 42,
        'variante': 'sem_quantizacao', 'contrato_sha256': 'contrato-xgb', 'duracao_s': 100})
    runner(tmp_path, p.RECUPERACAO_XGBOOST,
           processos=[{'modelo': 'XGBoost', 'tarefa': 'hourly_72_extension', 'fase': 'refit'}])
    e = estado(tmp_path)
    assert len(e['ativos']) == 1
    job = e['ativos'][0]
    assert job['modelo'] == 'XGBoost' and job['fase'] == 'refit'
    assert job['sementes_total'] == 4 and job['sementes_concluidas'] == 1
    assert job['estimativa']['min_s'] is not None
    assert not e['falhas']
    assert e['filas'][-1]['situacao'] == 'substituida_pela_recuperacao'


def test_duas_recuperacoes_ativas_preservam_nova_falha_xgboost(tmp_path):
    antigo = AGORA - timedelta(hours=1)
    falha = {'modelo': 'XGBoost', 'tarefa': 'hourly_72_extension', 'fase': 'refit'}
    runner(tmp_path, p.RUNNERS[3], etapa='erro', atualizado=antigo, falhas=[falha])
    runner(tmp_path, p.RECUPERACAO,
           processos=[{'modelo': 'GRU', 'tarefa': 'daily_30'}])
    runner(tmp_path, p.RECUPERACAO_XGBOOST, falhas=[falha],
           processos=[{'modelo': 'XGBoost', 'tarefa': 'hourly_72_extension'}])
    e = estado(tmp_path)
    assert len(e['ativos']) == 2
    assert len(e['falhas']) == 1
    assert e['falhas'][0]['modelo'] == 'XGBoost'
    assert any('XGBoost' in a and 'pendente' in a for a in e['alertas'])