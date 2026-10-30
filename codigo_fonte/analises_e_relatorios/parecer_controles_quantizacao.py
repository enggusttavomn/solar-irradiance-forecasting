"""Caracteriza controles novos versus arquivos antigos, sem emitir aceites."""
from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as x
from codigo_fonte.experimentos import experimento_multirresolucao as m


def parecer(pasta,fase,saida):
    pasta=Path(pasta)
    part='validacao' if fase=='selecao' else 'teste'
    caminho=pasta/f'controle_{part}_divergencia.json'
    if not caminho.is_file():return None
    divergencia=x.ler_json(caminho)
    contrato=x.ler_json(pasta/'contrato_execucao.json')
    modelo=contrato['modelo']
    tarefa=contrato['tarefa']['slug']
    ctx=x.preparar_contexto(tarefa,fase,contrato['modo'],contrato['protocolo'],modelo)
    fonte=Path(divergencia['fonte'])
    antigo=pd.read_csv(fonte,float_precision='round_trip')
    atual=x.e.tabela_chaves(ctx,part)
    datas=['origem_utc','timestamp_alvo_utc'] if ctx.tarefa.resolucao=='horaria' else ['origem','data_alvo']
    chaves=['localidade',*datas,'passo_h' if ctx.tarefa.resolucao=='horaria' else 'passo']
    for col in datas:
        antigo[col]=pd.to_datetime(antigo[col],utc=True)
        atual[col]=pd.to_datetime(atual[col],utc=True)
    junto=atual.merge(antigo,on=chaves,how='left',validate='one_to_one',sort=False,suffixes=('','_original'))
    velhos,novos,epocas,arquivos=[],[],{},[caminho,pasta/'contrato_execucao.json',fonte]
    for seed in contrato['parametros']['sementes']:
        col=f'previsao_bruta_{modelo.lower()}_seed{seed}_wm2'
        if col not in junto:col=f'previsao_bruta_{modelo.lower()}_wm2'
        velhos.append(junto[col].to_numpy(float).reshape(ctx.janelas[part].y_bruto.shape))
        cache=pasta/'sem_quantizacao'/fase/f'seed{seed}.npz'
        with np.load(cache,allow_pickle=False) as z:
            novos.append(z['previsao'])
            epocas[str(seed)]=int(z['epocas'].item())
        arquivos.append(cache)
    _,metrica_antiga=x.metricas(ctx,part,np.mean(velhos,axis=0),modelo,'controle_antigo')
    _,metrica_nova=x.metricas(ctx,part,np.mean(novos,axis=0),modelo,'controle_novo')
    comparacao=metrica_nova.merge(metrica_antiga,on=['tarefa','modelo','particao','horizonte'],suffixes=('_novo','_antigo'))
    comparacao['delta_MAE_wm2']=comparacao.MAE_wm2_novo-comparacao.MAE_wm2_antigo
    cp_report=x.RAIZ/'resultados/relatorios/quantizacao_todos_modelos_20260929/auditoria_controles_originais'/f'{tarefa}_{modelo.lower()}.json'
    evidencia=None
    if cp_report.is_file():
        audit=x.ler_json(cp_report)
        evidencia={'arquivo':str(cp_report),'sha256':m.sha256_arquivo(cp_report),
            'compatibilidade_aproximada_aprovada':audit['aprovado'],
            'checkpoints_disponiveis_reproduzidos':audit['checkpoints_reproduzidos'],
            'fases_sem_checkpoint_original':audit['fases_sem_checkpoint_original'],
            'criterio':audit['politica_numerica']}
    texto=('A mudanca de dispositivo foi definida antes dos resultados, por desempenho computacional. '
           if contrato['parametros']['novo_controle_por_dispositivo'] else
           'O controle foi retreinado no dispositivo original; a divergencia exige investigar ambiente e determinismo. ')
    texto+=('Este parecer nao e aceite. Comparacoes de quantizacao devem usar o controle novo e as variantes '
            'no mesmo ambiente; nao atribuir diferencas entre controles antigos e novos a quantizacao. '
            'A validacao do checkpoint novo e do protocolo completo cabe ao auditor independente.')
    resultado={'tarefa':tarefa,'modelo':modelo,'fase':fase,'nao_emite_aceite':True,
        'contrato_sha256':contrato['sha256_contrato'],'dispositivo_atual':contrato['parametros']['dispositivo'],
        'dispositivo_original':contrato['parametros']['dispositivo_original'],
        'max_diferenca_por_seed_wm2':divergencia['max_diferenca_por_seed'],'epocas_novas':epocas,
        'comparacao_metricas':comparacao.to_dict('records'),'evidencia_checkpoints_antigos':evidencia,
        'parecer':texto,'arquivos_sha256':x.hashes(arquivos)}
    destino=Path(saida)/f'{tarefa}_{modelo.lower()}_{part}.json'
    m.salvar_json_atomico(resultado,destino)
    return destino


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--raiz',type=Path,default=x.SAIDA/'atual')
    ap.add_argument('--saida',type=Path,default=x.RAIZ/'resultados/relatorios/quantizacao_todos_modelos_20260929/pareceres_controles')
    args=ap.parse_args()
    for tarefa in x.e.TAREFAS:
        for modelo in x.MODELOS[:-1]:
            pasta=args.raiz/tarefa/modelo.lower()
            for fase in ('selecao','refit'):
                path=parecer(pasta,fase,args.saida)
                if path:print(path,flush=True)


if __name__=='__main__':main()
