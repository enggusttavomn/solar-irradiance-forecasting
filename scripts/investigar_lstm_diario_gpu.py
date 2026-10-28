"""Investiga a migracao CPU/CUDA sem retreinar ou emitir aceite cientifico."""
from pathlib import Path
import copy
import hashlib
import numpy as np
import pandas as pd
import torch
from codigo_fonte import experimento_quantizacao_concorrentes as x
from codigo_fonte import experimento_multirresolucao as m


def main():
    pasta=x.SAIDA/'atual/daily_30/lstm'
    origem=x.RAIZ/'resultados/avaliacao_multirresolucao_corrigida_v2/daily_30'
    saida=x.RAIZ/'relatorios/quantizacao_todos_modelos_20260929/pareceres_controles'
    c=x.ler_json(pasta/'contrato_execucao.json')
    antigo=x.ler_json(origem/'contrato_execucao.json')
    par=c['parametros']
    assert antigo['configuracao']==par['configuracao']
    ctx=x.preparar_contexto('daily_30','selecao','completa',c['protocolo'],'LSTM')
    original=x.e.preparar_contexto('daily_30','completa')
    auditoria_dados={}
    for part,part_antiga in [('ajuste','ajuste'),('validacao','validacao_2023')]:
        a,b=ctx.janelas[part],original.janelas[part_antiga]
        checks={k:bool(np.array_equal(getattr(a,k),getattr(b,k))) for k in
                ('x_bruto','y_bruto','localidade_id','origem','datas_alvo')}
        an,bn=a.normalizar(ctx.escalas['selecao']),b.normalizar(original.escalas['selecao'])
        checks.update(x_normalizado_bitexato=bool(np.array_equal(an[0],bn[0])),
                      y_normalizado_bitexato=bool(np.array_equal(an[1],bn[1])))
        assert all(checks.values())
        auditoria_dados[part]=checks
    ep_old=pd.read_csv(origem/'epocas_selecionadas.csv')
    historico_old=pd.read_csv(origem/'historico_treinamento.csv',float_precision='round_trip')
    comparacoes=[]
    resumo=[]
    for seed in par['sementes']:
        ho=historico_old.loc[(historico_old.modelo=='LSTM') & (historico_old.semente==seed)
                             & (historico_old.fase=='selecao_epocas')]
        hn=pd.read_csv(pasta/'sem_quantizacao/selecao'/f'seed{seed}.csv',float_precision='round_trip')
        junto=hn.merge(ho,on='epoca',suffixes=('_gpu','_cpu'))
        for metrica in ('mse_treino_normalizado','mse_validacao_normalizado'):
            junto[f'delta_{metrica}']=junto[f'{metrica}_gpu']-junto[f'{metrica}_cpu']
        junto['seed']=seed
        comparacoes.append(junto)
        with np.load(pasta/'sem_quantizacao/selecao'/f'seed{seed}.npz') as z: ep_new=int(z['epocas'].item())
        pos=ep_old.loc[(ep_old.modelo=='LSTM') & (ep_old.semente==seed),'epocas_selecionadas_em_2023']
        resumo.append({'seed':seed,'epoca_cpu':int(pos.iloc[0]),'epoca_gpu':ep_new,
                       'epocas_executadas_cpu':len(ho),'epocas_executadas_gpu':len(hn),
                       'delta_mse_validacao_primeira_epoca':float(junto.delta_mse_validacao_normalizado.iloc[0]),
                       'max_delta_mse_validacao_absoluto':float(junto.delta_mse_validacao_normalizado.abs().max()),
                       'primeira_epoca_delta_maior_1e_6':None if not (junto.delta_mse_validacao_normalizado.abs()>1e-6).any()
                         else int(junto.loc[junto.delta_mse_validacao_normalizado.abs()>1e-6,'epoca'].iloc[0])})
    csv=saida/'daily_30_lstm_curvas_cpu_gpu.csv'
    pd.concat(comparacoes).to_csv(csv,index=False)
    # Um lote real, estado inicial igual, sem optimizer.step nem alteracao de checkpoints.
    seed=11
    conf=m.ConfiguracaoMultirresolucao(**par['configuracao'])
    cpu=m.criar_modelo_neural('LSTM',tarefa=ctx.tarefa,configuracao=conf,num_localidades=len(ctx.series),semente=seed)
    gpu=copy.deepcopy(cpu).to('cuda')
    init_igual=all(torch.equal(v.cpu(),gpu.state_dict()[k].cpu()) for k,v in cpu.state_dict().items())
    treino=ctx.janelas['ajuste']
    xn,yn=treino.normalizar(ctx.escalas['selecao'])
    lote=next(iter(m._carregador(xn,yn,treino.localidade_id,batch_size=par['batch_size'],embaralhar=True,semente=seed)))
    xb,yb,ids=lote
    cpu.train();gpu.train()
    pc=cpu(xb,ids)
    pg=gpu(xb.to('cuda'),ids.to('cuda')).cpu()
    lc=((pc-yb)**2).mean();lg=((pg-yb)**2).mean()
    lc.backward();lg.backward()
    gradientes={k:float((p.grad.cpu()-dict(gpu.named_parameters())[k].grad.cpu()).abs().max())
                for k,p in cpu.named_parameters()}
    old_cp=torch.load(origem/'modelos/lstm_seed11_refit.pt',map_location='cpu',weights_only=False)
    old_state=old_cp['state_dict']
    shapes={k:list(v.shape) for k,v in cpu.state_dict().items()}
    assert shapes=={k:list(v.shape) for k,v in old_state.items()}
    raw=Path(m.__file__).read_bytes()
    restaurado=raw.replace(b'executaveis/executar_avaliacao_multirresolucao.py',b'executar_avaliacao_multirresolucao.py')
    codigo_old=antigo['codigo_sha256'][str(Path(m.__file__).resolve())]
    hash_restaurado=hashlib.sha256(restaurado).hexdigest()
    fontes=[Path(__file__),Path(m.__file__),pasta/'contrato_execucao.json',origem/'contrato_execucao.json',
            origem/'historico_treinamento.csv',origem/'epocas_selecionadas.csv',csv,
            saida/'daily_30_lstm_validacao.json',saida/'daily_30_lstm_replay_novo_validacao.json']
    r={'modelo':'LSTM','tarefa':'daily_30','nao_emite_aceite':True,'retreino_realizado':False,
       'contrato_sha256':c['sha256_contrato'],'configuracao_igual':True,'dados':auditoria_dados,
       'arquitetura_shapes_iguais_checkpoint_original_refit':shapes,
       'diferenca_fonte_multirresolucao':{'hash_original':codigo_old,'hash_apos_restaurar_caminho_wrapper':hash_restaurado,
         'diferenca_restrita_ao_caminho_wrapper':hash_restaurado==codigo_old},
       'ambiente_original':antigo['dependencias'],
       'ambiente_atual':{'torch':torch.__version__,'cuda':torch.version.cuda,'cudnn':torch.backends.cudnn.version(),
          'gpu':torch.cuda.get_device_name(0),'deterministic_algorithms':torch.are_deterministic_algorithms_enabled(),
          'deterministic_warn_only':torch.is_deterministic_algorithms_warn_only_enabled(),
          'cudnn_benchmark':torch.backends.cudnn.benchmark,'cudnn_deterministic':torch.backends.cudnn.deterministic,
          'cudnn_allow_tf32':torch.backends.cudnn.allow_tf32,'matmul_allow_tf32':torch.backends.cuda.matmul.allow_tf32},
       'curvas':resumo,'lote_inicial_sem_atualizacao':{'seed':seed,'tamanho':len(xb),
          'estado_inicial_bitexato':init_igual,'max_delta_previsao_normalizada':float((pc-pg).abs().max()),
          'mse_cpu':float(lc.detach()),'mse_gpu':float(lg.detach()),'max_delta_gradientes':gradientes},
       'interpretacao':('Mesmos dados, arquitetura e hiperparametros. As diferencas pequenas nas operacoes CPU/CUDA '
          'podem crescer na otimizacao recorrente e mudar a epoca selecionada. O experimento isolado de um lote '
          'demonstra diferencas de backend, mas nao prova que esse fator explica toda a divergencia final. '
          'Comparar quantizacao contra o novo controle no mesmo ambiente; nao chamar o controle GPU reproducao exata do antigo.'),
       'fontes_sha256':x.hashes(fontes)}
    dest=saida/'daily_30_lstm_investigacao_backend.json'
    m.salvar_json_atomico(r,dest)
    print(dest,flush=True)
    print(resumo,flush=True)
    print(r['lote_inicial_sem_atualizacao'],flush=True)
    print(r['diferenca_fonte_multirresolucao'],flush=True)


if __name__=='__main__':main()
