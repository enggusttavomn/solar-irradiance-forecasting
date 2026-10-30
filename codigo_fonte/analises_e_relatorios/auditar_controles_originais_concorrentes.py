"""Replay independente dos checkpoints CPU preservados de LSTM/GRU/DilatedRNN.

Nao treina, nao altera checkpoints, nao aprova migracao de dispositivo sozinho.
Informa explicitamente quando o experimento original nao salvou a selecao.
"""
from __future__ import annotations
import argparse
import platform
from pathlib import Path
import time
import numpy as np
import pandas as pd
import torch
from codigo_fonte.experimentos import experimento_multirresolucao as m
from codigo_fonte.experimentos import experimento_horario_timesnet as h
from codigo_fonte.modelos import modelos_baselines_adicionais as redes
from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as novo

RAIZ=Path(__file__).resolve().parents[2]
REL=RAIZ/'resultados/relatorios/quantizacao_todos_modelos_20260929'
MODELOS=('LSTM','GRU','DilatedRNN')
TAREFAS=('hourly_72_extension','daily_30')
ATOL_COMPATIBILIDADE_ANTIGA=1e-4
RTOL_COMPATIBILIDADE_ANTIGA=1e-6


def caminho_checkpoint(tarefa,modelo,seed,fase):
    if modelo=='GRU':
        return RAIZ/'resultados/avaliacao_baselines_revisao_20260912'/tarefa/'gru/modelos'/f'seed{seed}_{fase}.pt'
    if tarefa=='hourly_72_extension' and modelo=='LSTM':
        return RAIZ/'resultados/avaliacao_horaria_timesnet/modelos'/f'lstm_encoder_direto_{fase}.pt'
    return RAIZ/'resultados/avaliacao_multirresolucao_corrigida_v2'/tarefa/'modelos'/f'{modelo.lower()}_seed{seed}_{fase}.pt'


def rede_original(ctx,modelo,seed,payload):
    if modelo=='GRU':
        m.fixar_semente(seed,1)
        rede=redes.criar_baseline(modelo,ctx.tarefa.seq_len,ctx.tarefa.pred_len,len(ctx.series))
        lote=int(payload['parametros']['batch_size'])
    elif modelo=='LSTM' and ctx.tarefa.resolucao=='horaria':
        fonte=RAIZ/'resultados/avaliacao_horaria_timesnet/configuracao_execucao.json'
        valores=novo.ler_json(fonte)
        valores['horizontes']=tuple(valores['horizontes'])
        valores['anos_treino']=tuple(valores['anos_treino'])
        conf=h.ConfiguracaoExperimentoHorario(**valores)
        rede=h.criar_lstm(conf,len(ctx.series))
        lote=conf.batch_size
    else:
        conf=m.ConfiguracaoMultirresolucao(**payload['configuracao'])
        rede=m.criar_modelo_neural(modelo,tarefa=ctx.tarefa,configuracao=conf,
                                  num_localidades=len(ctx.series),semente=seed)
        lote=conf.batch_size_diario
    rede.load_state_dict(payload.get('state_dict',payload.get('estado_modelo')),strict=True)
    return rede.cpu().eval(),lote


def alinhar_previsoes(ctx,particao,fonte):
    anterior=pd.read_csv(fonte,float_precision='round_trip')
    nova=novo.e.tabela_chaves(ctx,particao)
    datas=['origem_utc','timestamp_alvo_utc'] if ctx.tarefa.resolucao=='horaria' else ['origem','data_alvo']
    chaves=['localidade',*datas,'passo_h' if ctx.tarefa.resolucao=='horaria' else 'passo']
    for col in datas:
        anterior[col]=pd.to_datetime(anterior[col],utc=True)
        nova[col]=pd.to_datetime(nova[col],utc=True)
    if len(anterior)!=len(nova) or anterior.duplicated(chaves).any() or nova.duplicated(chaves).any():
        raise ValueError('Chaves nao correspondem integralmente ao original.')
    junto=nova.merge(anterior,on=chaves,how='left',validate='one_to_one',suffixes=('','_original'),sort=False)
    np.testing.assert_allclose(junto.ghi_real_wm2,junto.ghi_real_wm2_original,atol=1e-6,rtol=0)
    return junto


def auditar(tarefas=TAREFAS,modelos=MODELOS):
    inicio=time.perf_counter()
    resultados=[]
    ausencias=[]
    por_par={}
    for tarefa in tarefas:
        por_modelo={modelo:[] for modelo in modelos}
        fontes_modelo={modelo:set() for modelo in modelos}
        seeds=[42] if tarefa=='hourly_72_extension' else [11,23,42,67,89]
        for fase,part in [('selecao','validacao'),('refit','teste')]:
            presentes=[(modelo,seed,caminho_checkpoint(tarefa,modelo,seed,fase))
                       for modelo in modelos for seed in seeds]
            for modelo,seed,cp in presentes:
                if not cp.is_file():
                    ausencias.append({'tarefa':tarefa,'modelo':modelo,'seed':seed,'fase':fase,'arquivo_ausente':str(cp)})
            presentes=[r for r in presentes if r[2].is_file()]
            if not presentes:continue
            ctx=novo.preparar_contexto(tarefa,fase,'completa')
            j=ctx.janelas[part]
            escala=ctx.escalas[fase].set_index('localidade_id').loc[j.localidade_id]
            # Formula original independente, apenas X; nao consulta y.
            x=(j.x_bruto.astype(np.float32)-escala.minimo_treino_wm2.to_numpy(np.float32)[:,None])
            x/=escala.amplitude_escala_wm2.to_numpy(np.float32)[:,None]
            fonte=novo.FONTE/tarefa/f'previsoes_{part}.csv.gz'
            antigo=alinhar_previsoes(ctx,part,fonte)
            for modelo,seed,cp in presentes:
                payload=torch.load(cp,map_location='cpu',weights_only=False)
                rede,lote=rede_original(ctx,modelo,seed,payload)
                if modelo=='LSTM' and tarefa=='hourly_72_extension':
                    normalizado=h.prever_rede_direta(rede,x,j.localidade_id,batch_size=lote)
                else:
                    normalizado=m.prever_rede(rede,x,j.localidade_id,batch_size=lote)
                bruto=j.inverter(normalizado,ctx.escalas[fase])
                col=f'previsao_bruta_{modelo.lower()}_seed{seed}_wm2'
                if col not in antigo:col=f'previsao_bruta_{modelo.lower()}_wm2'
                anterior=antigo[col].to_numpy(float)
                diferenca=np.abs(bruto.reshape(-1)-anterior)
                maximo=float(np.max(diferenca))
                aproximado=bool(np.allclose(bruto.reshape(-1),anterior,
                    atol=ATOL_COMPATIBILIDADE_ANTIGA,rtol=RTOL_COMPATIBILIDADE_ANTIGA))
                row={'tarefa':tarefa,'modelo':modelo,'seed':seed,'fase':fase,
                     'checkpoint':str(cp),'checkpoint_sha256':m.sha256_arquivo(cp),'dispositivo':'cpu',
                     'batch_size':lote,'quantidade_previsoes':int(bruto.size),'max_diferenca_wm2':maximo,
                     'aprovado':aproximado,'reproducao_absoluta_1e_6_aprovada':bool(np.isfinite(maximo) and maximo<=1e-6),
                     'paridade_numerica_aproximada_aprovada':aproximado,
                     'atol_compatibilidade_wm2':ATOL_COMPATIBILIDADE_ANTIGA,
                     'rtol_compatibilidade':RTOL_COMPATIBILIDADE_ANTIGA,
                     'max_razao_limite_tolerancia':float(np.max(diferenca/(ATOL_COMPATIBILIDADE_ANTIGA+RTOL_COMPATIBILIDADE_ANTIGA*np.abs(anterior)))),
                     'previsoes_originais':str(fonte),'previsoes_originais_sha256':m.sha256_arquivo(fonte)}
                resultados.append(row)
                por_modelo[modelo].append(row)
                fontes_modelo[modelo].update([cp,fonte,*ctx.entradas])
                print(tarefa,modelo,seed,fase,'maxdiff',maximo,'aprovado',row['aprovado'],flush=True)
                if not row['aprovado']:
                    m.salvar_json_atomico({'ok':False,'resultados':resultados,'ausencias':ausencias},REL/'auditoria_controles_originais_concorrentes.json')
                    # Preservar a falha e concluir os checkpoints independentes.
                    # Qualquer tolerancia alternativa depende de analise separada.
        for modelo in modelos:
            faltas=[r for r in ausencias if r['tarefa']==tarefa and r['modelo']==modelo]
            registro={'tarefa':tarefa,'modelo':modelo,'aprovado':bool(por_modelo[modelo]) and all(r['aprovado'] for r in por_modelo[modelo]),
                'checkpoints_reproduzidos':len(por_modelo[modelo]),'resultados':por_modelo[modelo],
                'ausencias':faltas,'fases_sem_checkpoint_original':sorted({r['fase'] for r in faltas}),
                'fontes_sha256':novo.hashes(sorted(fontes_modelo[modelo],key=str)),
                'codigo_auditoria_sha256':novo.hashes([Path(__file__),Path(novo.__file__),Path(m.__file__),Path(h.__file__),Path(redes.__file__)]),
                'ambiente_replay':{'python':platform.python_version(),'torch':torch.__version__,'dispositivo':'cpu'},
                'evidencia_complementar_loop':{'testes':str(RAIZ/'testes/test_quantizacao_concorrentes.py'),
                    'sha256':m.sha256_arquivo(RAIZ/'testes/test_quantizacao_concorrentes.py'),
                    'escopo':'test_noquant_repete_loop_original para cinco redes; paridade CPU exata em dados sinteticos'},
                'limites':'Replay apenas dos checkpoints listados. Nao comprova replay das fases ausentes nem reproducao exata de retreinamento CUDA.'}
            if tarefa=='hourly_72_extension' and modelo=='LSTM':
                origem_ambiente=RAIZ/'resultados/avaliacao_horaria_timesnet/manifesto_artefatos.json'
                registro['ambiente_original']=novo.ler_json(origem_ambiente)['ambiente']
            elif modelo=='GRU':
                origem_ambiente=RAIZ/'resultados/avaliacao_baselines_revisao_20260912'/tarefa/'gru/contrato.json'
                co=novo.ler_json(origem_ambiente)
                registro['ambiente_original']={'python':co['python'],**co['pacotes']}
            else:
                origem_ambiente=RAIZ/'resultados/avaliacao_multirresolucao_corrigida_v2'/tarefa/'contrato_execucao.json'
                registro['ambiente_original']=novo.ler_json(origem_ambiente)['dependencias']
            registro['fonte_ambiente_original']={'arquivo':str(origem_ambiente),'sha256':m.sha256_arquivo(origem_ambiente)}
            registro['politica_numerica']='Compatibilidade aproximada de CPs antigos: rtol=1e-6,atol=1e-4 W/m2, criterio autorizado antes de concluir a auditoria. Reporta tambem erro absoluto1e-6; nao chamar paridade aproximada de reproducao exata. CPs novos exigem1e-6 absoluto.'
            registro['ambiente_antigo_workspace']={'ambiente_2_6_disponivel':False,
                'inspecao':'rg --files -uuu -g pyvenv.cfg: somente .venv-baselines-gpu-20260912; Python3.14.4/Torch2.12.0+cu126',
                'configuracoes_encontradas':novo.hashes([RAIZ/'.venv-baselines-gpu-20260912/pyvenv.cfg'])}
            evidencia_xml=REL/'testes_concorrentes.xml'
            if evidencia_xml.is_file():
                registro['relatorio_testes_loop']={'arquivo':str(evidencia_xml),'sha256':m.sha256_arquivo(evidencia_xml)}
            saida=REL/'auditoria_controles_originais'/f'{tarefa}_{modelo.lower()}.json'
            m.salvar_json_atomico(registro,saida)
            por_par[f'{tarefa}/{modelo}']={'arquivo':str(saida),'sha256':m.sha256_arquivo(saida)}
    resumo={'ok':all(r['aprovado'] for r in resultados),'checkpoints_reproduzidos':len(resultados),
            'resultados':resultados,'ausencias':ausencias,'relatorios_por_par':por_par,
            'segundos':time.perf_counter()-inicio,'gerado_em_utc':novo.agora()}
    m.salvar_json_atomico(resumo,REL/'auditoria_controles_originais_concorrentes.json')
    m.salvar_csv_atomico(pd.DataFrame(resultados),REL/'auditoria_controles_originais_concorrentes.csv')
    return resumo


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--tarefa',choices=TAREFAS,nargs='+',default=list(TAREFAS))
    ap.add_argument('--modelo',choices=MODELOS,nargs='+',default=list(MODELOS))
    args=ap.parse_args()
    auditar(args.tarefa,args.modelo)
