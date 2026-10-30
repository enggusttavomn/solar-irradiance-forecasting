"""Confere amostras e colunas dos controles reais, sem treinar modelos."""
from pathlib import Path
import numpy as np
import pandas as pd
from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as x
from codigo_fonte.experimentos import experimento_multirresolucao as m


def main():
    registros=[]
    leitor_original = pd.read_csv
    cache_leitura = {}
    def ler_csv(caminho, *args, **kwargs):
        p = Path(caminho).resolve()
        if (x.FONTE.resolve() not in p.parents and x.e.FONTE.resolve() not in p.parents):
            return leitor_original(caminho, *args, **kwargs)
        if p not in cache_leitura:
            cache_leitura[p] = leitor_original(caminho, float_precision='round_trip')
        quadro = cache_leitura[p]
        if kwargs.get('usecols') is not None:
            quadro = quadro[list(kwargs['usecols'])]
        return quadro.copy(deep=True)
    pd.read_csv = ler_csv
    for tarefa in x.e.TAREFAS:
        for fase,part in [('selecao','validacao'),('refit','teste')]:
            cache_leitura.clear()
            ctx=x.preparar_contexto(tarefa,fase,'completa')
            fonte=x.FONTE/tarefa/f'previsoes_{part}.csv.gz'
            antigo=pd.read_csv(fonte,float_precision='round_trip')
            tab=x.e.tabela_chaves(ctx,part)
            datas=['origem_utc','timestamp_alvo_utc'] if ctx.tarefa.resolucao=='horaria' else ['origem','data_alvo']
            chaves=['localidade',*datas,'passo_h' if ctx.tarefa.resolucao=='horaria' else 'passo']
            for coluna in datas:
                antigo[coluna]=pd.to_datetime(antigo[coluna],utc=True)
                tab[coluna]=pd.to_datetime(tab[coluna],utc=True)
            junto=tab.merge(antigo,on=chaves,how='left',validate='one_to_one',sort=False,suffixes=('','_original'))
            for modelo in x.MODELOS[:-1]:
                seeds=x.parametros(ctx,modelo)['sementes']
                brutas=[]
                for seed in seeds:
                    col=f'previsao_bruta_{modelo.lower()}_seed{seed}_wm2'
                    if col not in junto:col=f'previsao_bruta_{modelo.lower()}_wm2'
                    brutas.append(junto[col].to_numpy(float).reshape(ctx.janelas[part].y_bruto.shape))
                destino=x.RAIZ/'tmp/quantizacao_todos_modelos_20260929/layout_controles'/tarefa/modelo.lower()/part
                m.salvar_json_atomico({'sha256_contrato':'teste_layout_sem_treinamento'},destino/'contrato_execucao.json')
                r=x.conferir_controle(ctx,modelo,part,brutas,seeds,destino)
                assert r['aprovado'] and r['alvos_primarios_bitexatos']
                assert all(v==0 for v in r['max_diferenca_por_seed'].values())
                registros.append({'tarefa':tarefa,'modelo':modelo,'particao':part,
                    'n_linhas':len(tab),'alvos_bitexatos':True,'previsoes_controle_diferenca':0.,
                    'relatorio':str(destino/f'controle_{part}.json'),
                    'sha256_relatorio':m.sha256_arquivo(destino/f'controle_{part}.json')})
                print(tarefa,modelo,part,'OK',flush=True)
    m.salvar_json_atomico({'ok':True,'casos':len(registros),'registros':registros,
        'motor_sha256':m.sha256_arquivo(x.__file__),
        'escopo':'48 comparacoes de layout/alvos/colunas; usa previsoes historicas como controle e nao comprova novo treinamento'},
        x.RAIZ/'resultados/relatorios/quantizacao_todos_modelos_20260929/verificacao_layout_controles.json')


if __name__=='__main__':main()
