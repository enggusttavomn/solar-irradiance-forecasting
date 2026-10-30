"""Guardas da retomada: fixtures locais, sem modelos, treinos ou coordenadores reais."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import pytest

from codigo_fonte.acompanhamento import finalizar_sequencia_recuperacao as f
AGORA = datetime(2026, 10, 1, 23, tzinfo=timezone.utc)


def gravar(path, registro):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registro), encoding='utf-8')
    return path


def preencher_refits(saida, *, modo='completa'):
    for tarefa in f.TAREFAS:
        for modelo in f.MODELOS:
            gravar(saida / 'atual' / tarefa / f.slug(modelo) / 'status.json',
                   {'etapa': 'concluida', 'modo': modo})


def fila(**campos):
    return {'regime': 'atual', 'modo': 'completa', 'etapa': 'refit',
            'identidade_runner': {'pid': 123, 'creation_time': 'original'},
            'atualizado_em_utc': AGORA.isoformat(), 'falhas': [], **campos}


def conferir(registro, nome='RNN', *, vivo=True, ativos=()):
    return f.conferir_fila(registro, nome, instante=AGORA,
                          checar=lambda r: vivo, arvore=lambda r: list(ativos))


def test_44_arquivos_ausentes_continuam_como_pendencias(tmp_path):
    pendentes = f.pendencias_refit(tmp_path)
    assert len(pendentes) == 44
    assert len({p['par'] for p in pendentes}) == 44
    assert all(p['motivo'] == 'status ausente' for p in pendentes)


def test_43_concluidos_nao_viram_44_por_glob(tmp_path):
    preencher_refits(tmp_path)
    ausente = tmp_path / 'atual/hourly_72_extension/xgboost/status.json'
    ausente.unlink()
    extra = tmp_path / 'atual/extra/modelo_extra/status.json'
    gravar(extra, {'etapa': 'concluida', 'modo': 'completa'})
    assert f.pendencias_refit(tmp_path) == [
        {'par': 'hourly_72_extension/XGBoost', 'motivo': 'status ausente'}]


def test_todos_44_refits_completos_passam(tmp_path):
    preencher_refits(tmp_path)
    assert not f.pendencias_refit(tmp_path)


@pytest.mark.parametrize('modo', ['smoke', 'outro', None])
def test_modo_errado_impede_porta_completa(tmp_path, modo):
    preencher_refits(tmp_path)
    gravar(tmp_path / 'atual/monthly_1/timesnet/status.json',
           {'modo': modo, 'etapa': 'concluida'})
    with pytest.raises(ValueError, match='Modo invalido'):
        f.pendencias_refit(tmp_path)


@pytest.mark.parametrize('nome', ['RNN', 'XGBoost'])
def test_recuperacao_morta_nao_espera_para_sempre(nome):
    with pytest.raises(RuntimeError, match='parou sem concluir'):
        conferir(fila(), nome, vivo=False)


def test_heartbeat_velho_interrompe_espera():
    registro = fila(atualizado_em_utc=(AGORA - timedelta(seconds=601)).isoformat())
    with pytest.raises(RuntimeError, match='sem atualizacao'):
        conferir(registro)


def test_heartbeat_recente_confirma_espera():
    registro = fila(atualizado_em_utc=(AGORA - timedelta(seconds=599)).isoformat())
    estado = conferir(registro, ativos=[{'pid': 123}])
    assert not estado['pronta']
    assert estado['processos_ativos'] == [{'pid': 123}]


@pytest.mark.parametrize('instante', [None, 'invalido', AGORA.replace(tzinfo=None).isoformat()])
def test_heartbeat_invalido_nao_e_execucao_confiavel(instante):
    with pytest.raises(RuntimeError, match='heartbeat invalido'):
        conferir(fila(atualizado_em_utc=instante))


@pytest.mark.parametrize('nome', ['RNN', 'XGBoost'])
@pytest.mark.parametrize('etapa', ['refit', 'concluida'])
def test_falhas_nao_vazias_impedem_conclusao(nome, etapa):
    with pytest.raises(RuntimeError, match='falhou ou foi interrompida'):
        conferir(fila(etapa=etapa, falhas=[{'returncode': 1}]), nome)


@pytest.mark.parametrize('etapa', ['erro', 'interrompida'])
def test_erro_da_fila_xgboost_interrompe_espera(etapa):
    with pytest.raises(RuntimeError, match='XGBoost falhou'):
        conferir(fila(etapa=etapa), 'XGBoost')


def test_concluida_exige_arvore_vazia():
    assert not conferir(fila(etapa='concluida'), ativos=[{'pid': 123}])['pronta']
    assert conferir(fila(etapa='concluida'), vivo=False)['pronta']


@pytest.mark.parametrize('campos', [{'modo': 'smoke'}, {'regime': 'historico_1998_2022'}])
def test_fila_de_outro_regime_ou_smoke_rejeitada(campos):
    with pytest.raises(ValueError, match='regime atual completo'):
        conferir(fila(**campos))


def escopo_fixture(rel):
    origem = gravar(rel / 'fila_integral_atual/atual/completa/runner.json', {'etapa': 'erro'})
    preservada = (rel / 'recuperacao_20261001/estados_anteriores'
                  / 'fila_integral_atual/atual/completa/runner.json')
    preservada.parent.mkdir(parents=True, exist_ok=True)
    preservada.write_bytes(origem.read_bytes())
    politica = gravar(rel / 'politica_migracao_cpu_cuda/proposta_politica_v2.json', {'politica': 'v2'})
    revisao = gravar(rel / 'politica_migracao_cpu_cuda/revisao_root_v2.json', {'aprovado': True})
    return gravar(rel / 'recuperacao_20261001/escopo.json', {
        'pares': [list(p) for p in sorted(f.PARES_RNN)], 'origem': str(origem),
        'origem_sha256': f.sha256(origem), 'politica_sha256': f.sha256(politica),
        'revisao_sha256': f.sha256(revisao)})


def test_escopo_rnn_fecha_seis_pares_e_fontes(tmp_path):
    path = escopo_fixture(tmp_path)
    assert f.conferir_escopo_rnn(tmp_path) == f.sha256(path)


@pytest.mark.parametrize('chave', ['origem', 'politica', 'revisao'])
def test_fonte_de_escopo_alterada_interrompe(tmp_path, chave):
    path = escopo_fixture(tmp_path)
    dados = json.loads(path.read_text())
    dados[chave + '_sha256'] = 'divergente'
    gravar(path, dados)
    with pytest.raises(ValueError, match='Fonte da recuperacao RNN alterada'):
        f.conferir_escopo_rnn(tmp_path)


def test_escopo_rnn_nao_pode_ampliar_modelos(tmp_path):
    path = escopo_fixture(tmp_path)
    dados = json.loads(path.read_text())
    dados['pares'][0] = ['daily_30', 'XGBoost']
    gravar(path, dados)
    with pytest.raises(ValueError, match='seis pares autorizados'):
        f.conferir_escopo_rnn(tmp_path)


def test_snapshot_da_origem_mutado_interrompe_espera(tmp_path):
    escopo_fixture(tmp_path)
    snapshot = (tmp_path / 'recuperacao_20261001/estados_anteriores'
                / 'fila_integral_atual/atual/completa/runner.json')
    gravar(snapshot, {'etapa': 'concluida'})
    with pytest.raises(ValueError, match='origem preservada'):
        f.conferir_escopo_rnn(tmp_path)


def test_refresh_do_runner_live_nao_invalida_origem_preservada(tmp_path):
    path = escopo_fixture(tmp_path)
    esperado = f.conferir_escopo_rnn(tmp_path)
    gravar(tmp_path / 'fila_integral_atual/atual/completa/runner.json',
           {'etapa': 'concluida', 'modo': 'completa', 'regime': 'atual'})
    assert f.conferir_escopo_rnn(tmp_path) == esperado == f.sha256(path)


def test_fila_integral_ativa_bloqueia_coordenacao_duplicada(tmp_path):
    gravar(tmp_path / 'fila_integral_atual/atual/completa/runner.json', fila())
    with pytest.raises(RuntimeError, match='anterior ainda ativa'):
        f.conferir_sem_filas_ativas(tmp_path, arvore=lambda r: [{'pid': 123}])


def preparar_main(tmp_path, monkeypatch, *, xgb_etapa='concluida'):
    rel, saida = tmp_path / 'resultados/relatorios', tmp_path / 'resultados'
    preencher_refits(saida)
    paths = {'RNN': rel / 'recuperacao_20261001/runner.json',
             'XGBoost': rel / 'recuperacao_xgboost_20261001/runner.json'}
    for nome, path in paths.items():
        gravar(path, fila(etapa=xgb_etapa if nome == 'XGBoost' else 'concluida'))
    monkeypatch.setattr(f, 'REL', rel)
    monkeypatch.setattr(f, 'SAIDA', saida)
    monkeypatch.setattr(f, 'DESTINO', rel / 'finalizacao_20261001')
    monkeypatch.setattr(f, 'FILAS_RECUPERACAO', paths)
    monkeypatch.setattr(f, 'identidade', lambda pid: {'pid': pid, 'creation_time': 'fixture'})
    monkeypatch.setattr(f.ctypes, 'windll', SimpleNamespace(kernel32=SimpleNamespace(
        SetThreadExecutionState=lambda flag: 1)), raising=False)
    monkeypatch.setattr(f, 'conferir_escopo_rnn', lambda rel: 'escopo-fixo')
    conferir_original = f.conferir_fila
    monkeypatch.setattr(f, 'conferir_fila', lambda registro, nome: conferir_original(
        registro, nome, instante=AGORA, checar=lambda r: False, arvore=lambda r: []))
    monkeypatch.setattr(f, 'conferir_sem_filas_ativas', lambda rel: None)
    return rel, paths


def test_main_nao_inicia_coordenador_apos_erro_xgboost(tmp_path, monkeypatch):
    rel, paths = preparar_main(tmp_path, monkeypatch, xgb_etapa='erro')
    iniciados = []
    monkeypatch.setattr(f, 'ProcessoProprio', lambda *a, **k: iniciados.append(a))
    with pytest.raises(RuntimeError, match='XGBoost falhou'):
        f.main()
    assert not iniciados
    status = json.loads((rel / 'finalizacao_20261001/status.json').read_text())
    assert status['etapa'] == 'erro'
    assert status['publicado'] is False


def test_main_mantem_travas_e_valida_adapter_antes_dos_coordenadores(tmp_path, monkeypatch):
    rel, paths = preparar_main(tmp_path, monkeypatch)
    travas, eventos = set(), []

    class Trava:
        def __init__(self, path):
            self.path = path
        def __enter__(self):
            assert self.path not in travas
            travas.add(self.path)
            return self
        def __exit__(self, *exc):
            travas.remove(self.path)

    def validar(path):
        assert all(p.parent in travas for p in paths.values())
        eventos.append('adapter')

    class Filho:
        def __init__(self, cmd, **kwargs):
            modulo = cmd[4]
            assert eventos[0] == 'adapter'
            if modulo == 'codigo_fonte.acompanhamento.coordenar_quantizacao_atual':
                assert all(p.parent in travas for p in paths.values())
                gravar(rel / 'coordenacao_atual/status.json', {'etapa': 'pronto_para_revisao_visual'})
            else:
                assert modulo == 'codigo_fonte.acompanhamento.coordenar_quantizacao_historica'
                assert all(p.parent not in travas for p in paths.values())
                gravar(rel / 'coordenacao_historica/status.json', {'etapa': 'pronto_para_revisao_visual'})
            eventos.append(modulo)
            self.registro = {'pid': 999, 'creation_time': 'fixture'}
            self.returncode = 0
        def poll(self):
            return 0
        def fechar(self):
            pass

    import types
    fake = types.ModuleType('codigo_fonte.experimentos.experimento_xgboost_horario_controle_auditado_v1')
    fake.validar_controle_adaptado = validar
    package = types.ModuleType('codigo_fonte')
    experimentos = types.ModuleType('codigo_fonte.experimentos')
    experimentos.__path__ = []
    experimentos.experimento_xgboost_horario_controle_auditado_v1 = fake
    package.experimentos = experimentos
    monkeypatch.setitem(sys.modules, 'codigo_fonte', package)
    monkeypatch.setitem(sys.modules, 'codigo_fonte.experimentos', experimentos)
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    monkeypatch.setattr(f, 'TravaDiretorio', Trava)
    monkeypatch.setattr(f, 'ProcessoProprio', Filho)
    f.main()
    assert eventos == ['adapter', 'codigo_fonte.acompanhamento.coordenar_quantizacao_atual',
                       'codigo_fonte.acompanhamento.coordenar_quantizacao_historica']
    assert not travas
    status = json.loads((rel / 'finalizacao_20261001/status.json').read_text())
    assert status['etapa'] == 'pronto_para_revisao_visual'
    assert status['publicado'] is False
    assert status['revisao_visual_pendente'] is True

def test_main_reconfere_escopo_ao_adquirir_travas(tmp_path, monkeypatch):
    rel, paths = preparar_main(tmp_path, monkeypatch)
    leituras, iniciados = [], []
    def mudar_escopo(rel):
        leituras.append(rel)
        return 'inicial' if len(leituras) == 1 else 'alterado'
    monkeypatch.setattr(f, 'conferir_escopo_rnn', mudar_escopo)
    monkeypatch.setattr(f, 'ProcessoProprio', lambda *a, **k: iniciados.append(a))
    with pytest.raises(ValueError, match='Escopo da recuperacao mudou'):
        f.main()
    assert len(leituras) == 2
    assert not iniciados
    for path in paths.values():
        with f.TravaDiretorio(path.parent):
            pass


def test_main_nao_inicia_coordenacao_com_par_ausente(tmp_path, monkeypatch):
    rel, paths = preparar_main(tmp_path, monkeypatch)
    (f.SAIDA / 'atual/monthly_6/lstm/status.json').unlink()
    iniciados = []
    monkeypatch.setattr(f, 'ProcessoProprio', lambda *a, **k: iniciados.append(a))
    with pytest.raises(RuntimeError, match='44 refits completos nao foram confirmados'):
        f.main()
    assert not iniciados
