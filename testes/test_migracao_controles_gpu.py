'''Falhas fechadas da politica, sem treinar ou emitir aceite real.'''
import json
from pathlib import Path
import pytest
from scripts import verificar_migracao_controles_gpu as v


def salvar(path,data):
    path.write_text(json.dumps(data),encoding='utf-8')
    return path


def escopo(tmp_path,monkeypatch):
    monkeypatch.setattr(v,'RESULTADOS',tmp_path)
    c={'modelo':'GRU','tarefa':{'slug':'daily_30'},'modo':'completa','protocolo':{'regime':'atual'},
       'sha256_contrato':'abc','parametros':{'novo_controle_por_dispositivo':True,
       'dispositivo_original':'cpu','dispositivo':'cuda','sementes':[11,23,42,67,89]}}
    d={'novo_controle_por_dispositivo':True,'dispositivo_original':'cpu','dispositivo':'cuda',
       'contrato_sha256':'abc','alvos_primarios_bitexatos':True}
    return c,d,tmp_path/'atual/daily_30/gru'


def test_seis_pares(tmp_path,monkeypatch):
    for tarefa in v.TAREFAS:
        for modelo in v.MODELOS:
            c,d,p=escopo(tmp_path,monkeypatch)
            c['modelo']=modelo;c['tarefa']['slug']=tarefa
            c['parametros']['sementes']=[42] if tarefa=='hourly_72_extension' else [11,23,42,67,89]
            p=tmp_path/'atual'/tarefa/modelo.lower()
            assert v.validar_escopo(c,d,p,'validacao')==(modelo,tarefa,'selecao')


@pytest.mark.parametrize('erro',['Transformer','Informer','cpu','mensal','historico','smoke','seed','dados','pasta'])
def test_fora_escopo(tmp_path,monkeypatch,erro):
    c,d,p=escopo(tmp_path,monkeypatch)
    if erro in ('Transformer','Informer'):c['modelo']=erro
    elif erro=='cpu':c['parametros']['dispositivo']='cpu'
    elif erro=='mensal':c['tarefa']['slug']='monthly_1'
    elif erro=='historico':c['protocolo']['regime']='historico_1998_2022'
    elif erro=='smoke':c['modo']='smoke'
    elif erro=='seed':c['parametros']['sementes']=[11]
    elif erro=='dados':d['alvos_primarios_bitexatos']=False
    else:p=tmp_path/'outra'
    with pytest.raises(ValueError):v.validar_escopo(c,d,p,'validacao')


def lote():
    return {'estado_inicial_bitexato':True,'parametros_apos_backward_inalterados':True,
            'optimizer_step_executado':False,'max_delta_previsao_normalizada':1e-5,
            'max_delta_gradientes':{'peso':1e-4}}


def test_lote_limite_inclusivo():v.validar_lote(lote())


@pytest.mark.parametrize('erro',['saida','gradiente','nan','init','step','peso'])
def test_lote_rejeita(erro):
    z=lote()
    if erro=='saida':z['max_delta_previsao_normalizada']=1.00001e-5
    elif erro=='gradiente':z['max_delta_gradientes']['peso']=1.00001e-4
    elif erro=='nan':z['max_delta_previsao_normalizada']=float('nan')
    elif erro=='init':z['estado_inicial_bitexato']=False
    elif erro=='step':z['optimizer_step_executado']=True
    else:z['parametros_apos_backward_inalterados']=False
    with pytest.raises(ValueError):v.validar_lote(z)


def test_revisao_hashes_e_emissao(tmp_path,monkeypatch):
    politica=salvar(tmp_path/'politica.json',{'fixa':True})
    dados={'aprovado':True,'politica_sha256':v.sha256(politica),'verificador_sha256':v.sha256(v.__file__),
           'revisor':'root','justificativa':'Politica conferida.'}
    revisao=salvar(tmp_path/'revisao.json',dados)
    assert v.validar_revisao(revisao,politica)==dados
    dados['aprovado']=False;salvar(revisao,dados)
    with pytest.raises(ValueError):v.validar_revisao(revisao,politica)
    dados['aprovado']=True;salvar(revisao,dados);salvar(politica,{'alterada':True})
    with pytest.raises(ValueError):v.validar_revisao(revisao,politica)
    with pytest.raises(ValueError):v.validar_revisao(None,politica)
    monkeypatch.setattr(v,'validar_politica',lambda p:{})
    with pytest.raises(ValueError,match='revisao externa'):
        v.emitir(tmp_path,'validacao',politica,None,tmp_path/'inexistente.json')
    assert not (tmp_path/'aceite_controle_gpu_validacao.json').exists()


def test_evidencia_nao_sobrescrita(tmp_path):
    p=tmp_path/'evidencia.json';v.gravar_novo({'original':True},p)
    with pytest.raises(ValueError):v.gravar_novo({},p)
    assert v.ler(p)=={'original':True}


def test_tolerancia_politica_nao_pode_ampliar(tmp_path):
    p={'schema':1,'nome':'migracoes_cpu_cuda_seis_pares_v1','modelos':list(v.MODELOS),
       'tarefas':list(v.TAREFAS),'particoes':list(v.FASES),'regime':'atual','modo':'completa',
       'dispositivo_original':'cpu','dispositivo_novo':'cuda','limites':dict(v.LIMITES),
       'metricas_decidem_aceite':False,'primeiro_lote_sem_optimizer_step':True,
       'ausencias_originais_devem_ser_declaradas':True,
       'fontes_sha256':{str(Path(v.__file__).resolve()):v.sha256(v.__file__)}}
    p['sha256_conteudo']=v.hash_obj(p);path=salvar(tmp_path/'politica.json',p)
    v.validar_politica(path)
    del p['sha256_conteudo'];p['limites']['replay_novo_atol_wm2']=1e-4
    p['sha256_conteudo']=v.hash_obj(p);salvar(path,p)
    with pytest.raises(ValueError,match='Criterios'):v.validar_politica(path)


def test_ausencia_original_explicita(tmp_path):
    cp=tmp_path/'cp.pt';cp.write_bytes(b'checkpoint')
    pred=tmp_path/'pred.csv';pred.write_bytes(b'previsao')
    row={'aprovado':True,'paridade_numerica_aproximada_aprovada':True,'atol_compatibilidade_wm2':1e-4,
         'rtol_compatibilidade':1e-6,'max_razao_limite_tolerancia':.5,'checkpoint':str(cp),
         'checkpoint_sha256':v.sha256(cp),'previsoes_originais':str(pred),
         'previsoes_originais_sha256':v.sha256(pred),'fase':'refit','seed':42}
    a={'aprovado':True,'modelo':'LSTM','tarefa':'hourly_72_extension','codigo_auditoria_sha256':{},
       'fontes_sha256':{},'resultados':[row],'ausencias':[{'fase':'selecao','seed':42,
       'arquivo_ausente':str(tmp_path/'ausente.pt')}],'fases_sem_checkpoint_original':['selecao'],
       'checkpoints_reproduzidos':1}
    v.validar_originais(a,'LSTM','hourly_72_extension',[42])
    a['ausencias']=[]
    with pytest.raises(ValueError,match='Falta enumerar'):
        v.validar_originais(a,'LSTM','hourly_72_extension',[42])
