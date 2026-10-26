import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from scripts import piloto_treinamento_atencao_estrito as p


def test_plano_nao_executa_treinamento(monkeypatch,capsys):
    monkeypatch.setattr('sys.argv',['piloto'])
    monkeypatch.setattr(p,'executar',lambda *a: pytest.fail('Execucao sem flag explicita'))
    p.main()
    plano=json.loads(capsys.readouterr().out)
    assert plano['optimizer_steps_totais']==64
    assert plano['resultado_publicavel'] is False


def test_subconjunto_distribuido_em_todas_localidades_e_extremos():
    ids=np.repeat(np.arange(10),120)
    indices=p.selecionar_indices(ids,512)
    assert len(indices)==512 and len(set(indices))==512
    assert np.array_equal(indices,p.selecionar_indices(ids,512))
    for local in range(10):
        amostra=indices[ids[indices]==local]
        assert amostra[0]==local*120 and amostra[-1]==local*120+119
        assert len(amostra) in (51,52)


@pytest.mark.parametrize('total',[0,9,1201])
def test_subconjunto_quantidade_invalida(total):
    with pytest.raises(ValueError):p.selecionar_indices(np.repeat(np.arange(10),120),total)


def test_wrapper_reaplica_estrito_e_restaura_funcao_e_flags():
    antes=(torch.are_deterministic_algorithms_enabled(),torch.is_deterministic_algorithms_warn_only_enabled())
    calls=[]
    def original(seed,threads):
        calls.append((seed,threads))
        torch.use_deterministic_algorithms(True,warn_only=True)
    modulo=SimpleNamespace(fixar_semente=original)
    with p.fixar_semente_estrita(modulo,torch) as registros:
        for seed in (11,42):
            modulo.fixar_semente(seed,1)
            assert torch.are_deterministic_algorithms_enabled()
            assert not torch.is_deterministic_algorithms_warn_only_enabled()
        assert len(registros)==2
    assert calls==[(11,1),(42,1)] and modulo.fixar_semente is original
    assert (torch.are_deterministic_algorithms_enabled(),torch.is_deterministic_algorithms_warn_only_enabled())==antes


def test_limite_allocator_um_gib_sem_inferir_uso_total():
    calls=[]
    cuda=SimpleNamespace(get_device_properties=lambda d:SimpleNamespace(total_memory=4*1024**3),
        set_per_process_memory_fraction=lambda f,d:calls.append((f,d)),reset_peak_memory_stats=lambda d:None,
        mem_get_info=lambda d:(3*1024**3,4*1024**3))
    r=p.configurar_limite_gpu(SimpleNamespace(cuda=cuda))
    assert calls==[(.25,0)]
    assert r['limite_allocator_bytes']==1024**3
    assert r['sem_fallback_de_batch_dispositivo_ou_dados'] is True


def amostra():
    return {'curvas':[{'epoca':1,'loss':.3},{'epoca':2,'loss':.2}], 'epoca_escolhida':2,'updates':8,
            'estado_retornado':{'w':torch.tensor([1.,2.])},
            'estado_ultima_atualizacao':{'w':torch.tensor([2.,3.])},
            'previsao_normalizada':np.array([[.1,.2]]),'previsao_bruta':np.array([[10.,20.]])}


@pytest.mark.parametrize('campo',['curvas','updates','epoca_escolhida','estado_retornado','estado_ultima_atualizacao','previsao_normalizada','previsao_bruta'])
def test_comparacao_rejeita_divergencia_em_qualquer_evidencia(campo):
    a,b=amostra(),amostra()
    assert p.comparar_execucoes(a,b)['ok']
    if campo=='curvas':b[campo][0]['loss']+=.001
    elif campo in ('updates','epoca_escolhida'):b[campo]+=1
    elif campo.startswith('estado'):b[campo]['w'][0]+=1e-6
    else:b[campo][0,0]+=1e-12
    assert p.comparar_execucoes(a,b)['ok'] is False


def test_resumo_nao_aprova_piloto_parcial():
    r={'ok':True,'pares':[],'fontes_sha256':{'fonte_teste':'hash_teste'}}
    assert p.resumo_estavel(r)['aprovado'] is False
    comp=p.comparar_execucoes(amostra(),amostra())
    r['pares']=[{'tarefa':t,'modelo':m,**copy.deepcopy(comp)} for t in p.TAREFAS for m in p.MODELOS]
    s=p.resumo_estavel(r)
    assert s['aprovado'] and len(s['pares'])==4
    assert all(a['pesos_finais_bitexatos'] and a['previsoes_bitexatas'] for a in s['pares'])
