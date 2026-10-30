import copy
import json
from types import SimpleNamespace

import pytest
import torch

from codigo_fonte.experimentos import experimento_atencao_deterministica_v1 as a


def test_contexto_reaplica_estrito_e_restaura_em_erro(monkeypatch):
    monkeypatch.setattr(a, 'ler_evidencia', lambda path: {})
    monkeypatch.setenv('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    original = a.base.m.fixar_semente
    antes = (torch.are_deterministic_algorithms_enabled(),
             torch.is_deterministic_algorithms_warn_only_enabled(), torch.get_num_threads())
    with pytest.raises(RuntimeError, match='falha simulada'):
        with a.ativar_adaptador():
            for seed in (11, 42):
                a.base.m.fixar_semente(seed, 1)
                assert torch.are_deterministic_algorithms_enabled()
                assert not torch.is_deterministic_algorithms_warn_only_enabled()
            with pytest.raises(RuntimeError, match='aninhados'):
                with a.ativar_adaptador():
                    pass
            raise RuntimeError('falha simulada')
    assert a.base.m.fixar_semente is original
    assert a.base.construir_contrato is a.CONSTRUIR_ORIGINAL
    assert a.base.conferir_controle is a.CONFERIR_ORIGINAL
    assert a.base.nova_rede is a.REDE_ORIGINAL
    assert not a._ativo
    assert antes == (torch.are_deterministic_algorithms_enabled(),
                    torch.is_deterministic_algorithms_warn_only_enabled(), torch.get_num_threads())


def test_nao_autoriza_migracao_cpu_cuda(monkeypatch):
    ctx = SimpleNamespace(tarefa=SimpleNamespace(slug='daily_30'), protocolo={'regime':'atual'})
    monkeypatch.setattr(a.base, 'parametros', lambda *args: {
        'dispositivo':'cuda','dispositivo_original':'cpu','novo_controle_por_dispositivo':True})
    with pytest.raises(ValueError, match='mudanca de dispositivo'):
        a.validar_escopo(ctx, 'Transformer')


@pytest.mark.parametrize('tarefa,modelo', [('monthly_1','Transformer'),('daily_30','GRU')])
def test_fora_escopo_recusado(tarefa, modelo):
    ctx = SimpleNamespace(tarefa=SimpleNamespace(slug=tarefa), protocolo={'regime':'atual'})
    with pytest.raises(ValueError, match='restrito'):
        a.validar_escopo(ctx, modelo)


def evidencia():
    return {'schema':1,'politica':a.POLITICA,'aprovado':True,
        'pares':[dict(tarefa=t,modelo=m,aprovado=True,curvas_bitexatas=True,
                      pesos_finais_bitexatos=True,pesos_retornados_bitexatos=True,
                      previsoes_bitexatas=True,repeticoes=2,optimizer_steps_por_repeticao=8)
                 for t in a.TAREFAS for m in a.MODELOS],
        'fontes_sha256':a.base.hashes([a.base.__file__,a.base.m.__file__,a.base.e.redes.__file__]),
        'limitacao':'Piloto curto, sem garantir todas as trajetorias.'}


@pytest.mark.parametrize('alteracao', ['par_ausente','par_duplicado','peso_divergente','sem_updates','sem_fonte'])
def test_evidencia_parcial_ou_divergente_recusada(tmp_path, alteracao):
    ev=evidencia()
    if alteracao=='par_ausente':ev['pares'].pop()
    elif alteracao=='par_duplicado':ev['pares'][0]=copy.deepcopy(ev['pares'][1])
    elif alteracao=='peso_divergente':ev['pares'][0]['pesos_finais_bitexatos']=False
    elif alteracao=='sem_updates':ev['pares'][0]['optimizer_steps_por_repeticao']=0
    else:ev['fontes_sha256'].pop(next(iter(ev['fontes_sha256'])))
    p=tmp_path/'piloto.json'
    p.write_text(json.dumps(ev),encoding='utf-8')
    with pytest.raises(ValueError):a.ler_evidencia(p)


def test_threads_do_contrato_sao_as_efetivas(monkeypatch):
    monkeypatch.setattr(a, '_exigir_ativo', lambda: None)
    monkeypatch.setattr(a, 'validar_escopo', lambda *args: {'configuracao':{'threads_torch':1}})
    monkeypatch.setattr(a, 'ler_evidencia', lambda *args: {'fontes_sha256':{}})
    monkeypatch.setattr(a, 'CONSTRUIR_ORIGINAL', lambda *args: {
        'codigo':{},'parametros':{'fontes_configuracao':{}},'sha256_contrato':'antigo'})
    monkeypatch.setattr(a.base,'hashes',lambda *args:{})
    monkeypatch.setattr(a,'_politica',lambda:{'threads':torch.get_num_threads()})
    antes=torch.get_num_threads()
    try:
        torch.set_num_threads(2)
        c=a.construir_contrato(None,'Transformer')
        assert c['execucao_numerica']['threads']==1
        assert c['controle_execucao_numerica']['reproducao_legada_exigida'] is False
        assert c['controle_execucao_numerica']['replay_independente_obrigatorio'] is True
    finally:torch.set_num_threads(antes)


def test_rede_aceita_proveniencia_adicionada_mas_recusa_parametro_alterado(monkeypatch):
    original = {'configuracao':{'sementes':(11,42),'taxa':.001},'fontes_configuracao':{'original':'hash'}}
    monkeypatch.setattr(a,'_exigir_ativo',lambda:None)
    monkeypatch.setattr(a,'validar_escopo',lambda *args:copy.deepcopy(original))
    monkeypatch.setattr(a,'ler_evidencia',lambda *args:{'fontes_sha256':{'piloto':'digest'}})
    monkeypatch.setattr(a.base,'hashes',lambda *args:{'registro':'digest'})
    monkeypatch.setattr(a,'REDE_ORIGINAL',lambda *args:'rede')
    par=json.loads(json.dumps(original))
    par['fontes_configuracao'].update({'piloto':'digest','registro':'digest'})
    assert a.nova_rede(None,'Transformer',11,par)=='rede'
    par['configuracao']['taxa']=.1
    with pytest.raises(ValueError,match='Parametros'):
        a.nova_rede(None,'Transformer',11,par)
