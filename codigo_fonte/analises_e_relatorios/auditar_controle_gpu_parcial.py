"""Replay CUDA de controles novos pausados antes das tabelas finais.

Compara diretamente cada checkpoint ao NPZ original, com normalizacao e
inversao independentes. Nao cria aceites nem modifica o experimento.
"""
from pathlib import Path
import argparse
import copy
import numpy as np
import torch
from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as x
from codigo_fonte.experimentos import experimento_multirresolucao as m
from codigo_fonte.modelos import modelos_baselines_adicionais as redes


def auditar(pasta,fase,saida):
    pasta=Path(pasta)
    c=x.ler_json(pasta/'contrato_execucao.json')
    assert c['sha256_contrato']==x.hash_obj({k:v for k,v in c.items() if k!='sha256_contrato'})
    x.conferir_hashes(c['codigo'])
    x.conferir_hashes(c['entradas'])
    modelo=c['modelo']
    par=c['parametros']
    assert par['dispositivo']=='cuda'
    assert modelo in ('LSTM','GRU','DilatedRNN','Transformer','Informer')
    part='validacao' if fase=='selecao' else 'teste'
    ctx=x.preparar_contexto(c['tarefa']['slug'],fase,c['modo'],c['protocolo'],modelo)
    j=copy.copy(ctx.janelas[part])
    object.__setattr__(j,'y_bruto',np.full_like(j.y_bruto,np.nan))
    escala=ctx.escalas[fase].set_index('localidade_id').loc[j.localidade_id]
    xn=(j.x_bruto.astype(np.float32)-escala.minimo_treino_wm2.to_numpy(np.float32)[:,None])
    xn/=escala.amplitude_escala_wm2.to_numpy(np.float32)[:,None]
    rows=[]
    for seed in par['sementes']:
        checkpoint=pasta/'sem_quantizacao/modelos'/f'seed{seed}_{fase}.pt'
        cache=pasta/'sem_quantizacao'/fase/f'seed{seed}.npz'
        cp=torch.load(checkpoint,map_location='cpu',weights_only=False)
        assert cp['contrato_sha256']==c['sha256_contrato']
        assert cp['seed']==seed and cp['fase']==fase and cp['niveis'] is None
        if modelo in ('GRU','Transformer','Informer'):
            m.fixar_semente(seed,1)
            rede=redes.criar_baseline(modelo,ctx.tarefa.seq_len,ctx.tarefa.pred_len,len(ctx.series))
        else:
            conf=m.ConfiguracaoMultirresolucao(**par['configuracao'])
            rede=m.criar_modelo_neural(modelo,tarefa=ctx.tarefa,configuracao=conf,
                                       num_localidades=len(ctx.series),semente=seed)
        rede.load_state_dict(cp['state_dict'],strict=True)
        rede.to('cuda').eval()
        pedacos=[]
        with torch.no_grad():
            for ini in range(0,len(xn),par['batch_size']):
                fim=ini+par['batch_size']
                xt=torch.as_tensor(xn[ini:fim],dtype=torch.float32,device='cuda')
                ids=torch.as_tensor(j.localidade_id[ini:fim],dtype=torch.long,device='cuda')
                pedacos.append(rede(xt,ids).cpu().numpy())
        normalizado=np.concatenate(pedacos).astype(float)
        bruto=normalizado*escala.amplitude_escala_wm2.to_numpy(float)[:,None]
        bruto+=escala.minimo_treino_wm2.to_numpy(float)[:,None]
        with np.load(cache,allow_pickle=False) as z:
            esperado=z['previsao']
            assert cp['epocas']==int(z['epocas'].item())
        delta=float(np.max(np.abs(bruto-esperado)))
        row={'seed':seed,'checkpoint':str(checkpoint),'checkpoint_sha256':m.sha256_arquivo(checkpoint),
            'cache':str(cache),'cache_sha256':m.sha256_arquivo(cache),'max_diferenca_wm2':delta,
            'aprovado':bool(np.isfinite(delta) and delta<=1e-6),'alvos_substituidos_por_nan':True,
            'epocas':cp['epocas'],'batch_size':par['batch_size'],'dispositivo':'cuda'}
        rows.append(row)
        print(modelo,seed,fase,delta,'OK' if row['aprovado'] else 'FALHOU',flush=True)
    r={'ok':all(a['aprovado'] for a in rows),'tarefa':ctx.tarefa.slug,'modelo':modelo,'fase':fase,
       'contrato_sha256':c['sha256_contrato'],'checkpoints':rows,'tolerancia_absoluta_wm2':1e-6,
       'nao_emite_aceite':True,'normalizacao_e_inversao_independentes':True,
       'codigo_auditoria_sha256':x.hashes([Path(__file__),Path(x.__file__),Path(m.__file__),Path(redes.__file__)])}
    m.salvar_json_atomico(r,saida)
    if not r['ok']:raise ValueError('Checkpoint novo nao reproduzido na tolerancia original.')
    return r


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--pasta',type=Path,required=True)
    ap.add_argument('--fase',choices=('selecao','refit'),default='selecao')
    ap.add_argument('--saida',type=Path,required=True)
    args=ap.parse_args()
    auditar(args.pasta,args.fase,args.saida)
