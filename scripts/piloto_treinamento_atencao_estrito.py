'''Piloto isolado de reprodutibilidade; sem --executar apenas apresenta o plano.'''
from __future__ import annotations
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import time

RAIZ = Path(__file__).resolve().parents[1]
REL = RAIZ / 'relatorios/quantizacao_todos_modelos_20260929/investigacao_atencao'
MOTOR_SHA256 = 'ca56d2040cc7c0bb1ec353464b861bf75c690a9330e543272eb58ca26450769a'
TAREFAS = ('daily_30', 'hourly_72_extension')
MODELOS = ('Transformer', 'Informer')
N_TREINO, N_VALIDACAO, BATCH_SIZE, EPOCAS, REPETICOES = 512, 128, 128, 2, 2
LIMITE_ALLOCATOR_BYTES = 1024**3


def plano():
    return {'modo': 'piloto_curto', 'resultado_publicavel': False,
        'tarefas': list(TAREFAS), 'modelos': list(MODELOS),
        'janelas_treino': N_TREINO, 'janelas_validacao': N_VALIDACAO,
        'criterio_subconjunto': 'linspace por localidade, incluindo extremos temporais; sem sorteio',
        'localidades': 10, 'minmax': 'original ajustado antes de 2023',
        'batch_size': BATCH_SIZE, 'epocas': EPOCAS, 'repeticoes': REPETICOES,
        'sementes': {'daily_30': 11, 'hourly_72_extension': 42},
        'optimizer_steps_por_execucao': EPOCAS * (N_TREINO // BATCH_SIZE),
        'optimizer_steps_totais': len(TAREFAS) * len(MODELOS) * REPETICOES * EPOCAS * (N_TREINO // BATCH_SIZE),
        'backend': 'SDPA automatico existente; deterministic_algorithms=True,warn_only=False apos cada fixar_semente',
        'quantizacao': None, 'estimativa_minutos': [2, 5],
        'criterio': 'curvas, epoca escolhida, pesos finais/retornados e previsoes bitexatos',
        'limite': 'Nao substitui treino completo nem garante todos os dados/epocas de uma execucao completa.'}


def selecionar_indices(ids, total):
    import numpy as np
    ids = np.asarray(ids)
    localidades = np.unique(ids)
    if ids.ndim != 1 or total < len(localidades) or total > len(ids):
        raise ValueError('Quantidade de janelas invalida para estratificacao.')
    base, resto = divmod(total, len(localidades))
    selecionados = []
    for i, local in enumerate(localidades):
        indices = np.flatnonzero(ids == local)
        quantidade = base + (i < resto)
        if quantidade > len(indices):
            raise ValueError('Localidade com poucas janelas para o piloto.')
        selecionados.extend(indices[np.linspace(0, len(indices)-1, quantidade, dtype=int)])
    resultado = np.sort(np.asarray(selecionados, dtype=np.int64))
    if len(resultado) != total or len(np.unique(resultado)) != total:
        raise ValueError('Subconjunto contem tamanho incorreto ou duplicatas.')
    return resultado


def hash_array(a):
    import numpy as np
    a = np.ascontiguousarray(a)
    return {'shape': list(a.shape), 'dtype': str(a.dtype), 'sha256': hashlib.sha256(a.tobytes()).hexdigest()}


def configurar_limite_gpu(torch):
    total = int(torch.cuda.get_device_properties(0).total_memory)
    if total < LIMITE_ALLOCATOR_BYTES:
        raise RuntimeError('GPU menor que o limite solicitado para o piloto.')
    fracao = LIMITE_ALLOCATOR_BYTES / total
    torch.cuda.set_per_process_memory_fraction(fracao, 0)
    torch.cuda.reset_peak_memory_stats(0)
    livre, total_reportado = torch.cuda.mem_get_info(0)
    return {'limite_allocator_bytes':LIMITE_ALLOCATOR_BYTES, 'fracao_allocator':fracao,
        'memoria_total_bytes':total, 'memoria_livre_inicial_bytes':int(livre),
        'memoria_usada_global_inicial_bytes':int(total_reportado-livre),
        'observacao':'Limite do allocator PyTorch; contexto CUDA/bibliotecas possuem overhead externo.',
        'sem_fallback_de_batch_dispositivo_ou_dados':True}


def resumo_estavel(resultado):
    pares = []
    for r in resultado['pares']:
        v, p = r['verificacoes'], r['pesos']
        pares.append({'tarefa':r['tarefa'], 'modelo':r['modelo'], 'aprovado':r['ok'],
            'repeticoes':REPETICOES, 'optimizer_steps_por_repeticao':plano()['optimizer_steps_por_execucao'],
            'curvas_bitexatas':v['curvas_bitexatas'], 'epocas_escolhidas_iguais':v['epocas_escolhidas_iguais'],
            'pesos_finais_bitexatos':p['estado_ultima_atualizacao']['bitexato'],
            'pesos_retornados_bitexatos':p['estado_retornado']['bitexato'],
            'previsoes_bitexatas':v['previsoes_normalizadas_bitexatas'] and v['previsoes_brutas_bitexatas']})
    resumo = {'schema':1, 'politica':'atencao_cuda_deterministica_v1',
        'aprovado':resultado['ok'] is True and len(pares)==4 and all(r['aprovado'] for r in pares)
            and bool(resultado['fontes_sha256'])
            and {(r['tarefa'],r['modelo']) for r in pares} == {(t,m) for t in TAREFAS for m in MODELOS},
        'pares':pares, 'fontes_sha256':resultado['fontes_sha256'], 'resultado_publicavel':False,
        'politica_numerica':plano()['backend'], 'memoria':resultado.get('memoria'),
        'concorrencia':resultado.get('concorrencia'), 'ambiente':resultado.get('ambiente'),
        'limitacao':plano()['limite'], 'erro':resultado.get('erro')}
    resumo['ok'] = resumo['aprovado']
    return resumo


@contextmanager
def fixar_semente_estrita(modulo, torch):
    original = modulo.fixar_semente
    antes = (torch.are_deterministic_algorithms_enabled(), torch.is_deterministic_algorithms_warn_only_enabled())
    chamadas = []

    def estrita(*args, **kwargs):
        original(*args, **kwargs)
        torch.use_deterministic_algorithms(True, warn_only=False)
        chamadas.append({'args': list(args), 'kwargs': kwargs})

    modulo.fixar_semente = estrita
    try:
        yield chamadas
    finally:
        modulo.fixar_semente = original
        torch.use_deterministic_algorithms(antes[0], warn_only=antes[1])


def comparar_execucoes(a, b):
    import numpy as np
    curvas = a['curvas'] == b['curvas']
    pesos = {}
    for tipo in ('estado_retornado', 'estado_ultima_atualizacao'):
        sa, sb = a[tipo], b[tipo]
        chaves_iguais = list(sa) == list(sb)
        max_delta = max((float(np.max(np.abs(sa[k].numpy().astype(float)-sb[k].numpy().astype(float))))
                         for k in sa), default=0) if chaves_iguais else None
        pesos[tipo] = {'bitexato': chaves_iguais and all(np.array_equal(sa[k].numpy(), sb[k].numpy()) for k in sa),
                       'max_delta': max_delta}
    pn, pb = a['previsao_normalizada'], b['previsao_normalizada']
    bruto_a, bruto_b = a['previsao_bruta'], b['previsao_bruta']
    verificacoes = {'curvas_bitexatas': curvas, 'epocas_escolhidas_iguais': a['epoca_escolhida']==b['epoca_escolhida'],
        'updates_iguais': a['updates']==b['updates']==plano()['optimizer_steps_por_execucao'],
        'previsoes_normalizadas_bitexatas': bool(np.array_equal(pn,pb)),
        'previsoes_brutas_bitexatas': bool(np.array_equal(bruto_a,bruto_b))}
    return {'ok': all(verificacoes.values()) and all(p['bitexato'] for p in pesos.values()),
        'verificacoes': verificacoes, 'pesos': pesos,
        'max_delta_previsao_normalizada': float(np.max(np.abs(pn-pb))),
        'max_delta_previsao_wm2': float(np.max(np.abs(bruto_a-bruto_b)))}


def executar_repeticao(ctx, modelo, seed, dados, destino, x, m, torch):
    import numpy as np
    par = x.parametros(ctx, modelo)
    if par['batch_size'] != BATCH_SIZE or par['dispositivo'] != 'cuda':
        raise ValueError('Lote/dispositivo do piloto divergem do experimento real.')
    updates, ultima = 0, {}
    iniciar = time.perf_counter()
    with fixar_semente_estrita(m, torch) as chamadas:
        rede = x.nova_rede(ctx, modelo, seed, par)

        def conferir_flags(*unused):
            if not torch.are_deterministic_algorithms_enabled() or torch.is_deterministic_algorithms_warn_only_enabled():
                raise RuntimeError('Determinismo estrito foi perdido durante a execucao.')

        rede.register_forward_pre_hook(conferir_flags)
        original_step = torch.optim.Adam.step

        def contar_step(otimizador, *args, **kwargs):
            nonlocal updates, ultima
            conferir_flags()
            resultado = original_step(otimizador, *args, **kwargs)
            updates += 1
            if updates == plano()['optimizer_steps_por_execucao']:
                ultima = {k:v.detach().cpu().clone() for k,v in rede.state_dict().items()}
            return resultado

        torch.optim.Adam.step = contar_step
        try:
            rede, epoca, curvas = m.treinar_rede(rede,
                x_treino=dados['xt'], y_treino=dados['yt'], ids_treino=dados['it'],
                x_validacao=dados['xv'], y_validacao=dados['yv'], ids_validacao=dados['iv'],
                batch_size=BATCH_SIZE, taxa_aprendizado=ctx.config.taxa_aprendizado,
                peso_decay=ctx.config.peso_decay, semente=seed, threads_torch=ctx.config.threads_torch,
                max_epocas=EPOCAS, paciencia=par['paciencia'])
        finally:
            torch.optim.Adam.step = original_step
        if len(curvas) != EPOCAS or updates != plano()['optimizer_steps_por_execucao'] or not ultima:
            raise ValueError('Quantidade de epocas/atualizacoes incorreta no piloto.')
        estado = {k:v.detach().cpu().clone() for k,v in rede.state_dict().items()}
        normalizado = m.prever_rede(rede, dados['xv'], dados['iv'], batch_size=BATCH_SIZE)
        bruto = normalizado * dados['amplitude'][:,None] + dados['minimo'][:,None]
        if not np.isfinite(normalizado).all() or not np.isfinite(bruto).all():
            raise ValueError('Piloto produziu previsao nao finita.')
    destino.mkdir(parents=True, exist_ok=False)
    m.salvar_torch_atomico({'state_dict': estado, 'ultima_atualizacao': ultima, 'modelo': modelo,
        'seed': seed, 'resultado_publicavel': False, 'modo': 'piloto_curto'}, destino/'pesos.pt')
    m.salvar_npz_atomico(destino/'previsoes.npz', normalizada=normalizado, bruta=bruto)
    resultado = {'curvas': curvas, 'epoca_escolhida': epoca, 'updates': updates,
        'estado_retornado': estado, 'estado_ultima_atualizacao': ultima,
        'previsao_normalizada': normalizado, 'previsao_bruta': bruto}
    meta = {'curvas': curvas, 'epoca_escolhida': epoca, 'updates': updates,
        'chamadas_fixar_semente_estrita': chamadas, 'segundos': time.perf_counter()-iniciar,
        'artefatos_sha256': x.hashes([destino/'pesos.pt',destino/'previsoes.npz']),
        'hashes_estado_retornado': {k:hash_array(v.numpy()) for k,v in estado.items()},
        'hashes_estado_ultima_atualizacao': {k:hash_array(v.numpy()) for k,v in ultima.items()}}
    m.salvar_json_atomico(meta, destino/'metadados.json')
    del rede
    torch.cuda.empty_cache()
    return resultado


def executar(destino):
    # Importacao do motor configura CUBLAS antes de inicializar CUDA.
    from codigo_fonte import experimento_quantizacao_concorrentes as x
    from codigo_fonte import experimento_multirresolucao as m
    import importlib.metadata
    import os
    import platform
    import numpy as np
    import torch
    if m.sha256_arquivo(Path(x.__file__)) != MOTOR_SHA256:
        raise ValueError('Motor congelado foi alterado.')
    destino = Path(destino).resolve()
    if not destino.is_relative_to(REL.resolve()) or destino.exists():
        raise ValueError('Destino deve ser novo e isolado dentro da pasta de investigacao.')
    destino.mkdir(parents=True)
    memoria = configurar_limite_gpu(torch)
    resultado = {'plano':plano(), 'inicio_utc':x.agora(), 'ok':False, 'resultado_publicavel':False,
        'ambiente': {'python':platform.python_version(), 'torch':torch.__version__, 'cuda':torch.version.cuda,
            'gpu':torch.cuda.get_device_name(0), 'cudnn':torch.backends.cudnn.version(),
            'cublas_workspace_config':os.environ.get('CUBLAS_WORKSPACE_CONFIG'),
            'pacotes':{k:importlib.metadata.version(k) for k in ('numpy','pandas','torch')}},
        'fontes_sha256':x.hashes([Path(__file__),Path(x.__file__),Path(m.__file__),Path(x.e.redes.__file__)]),
        'pares':[], 'memoria':memoria,
        'concorrencia':{'processo_piloto':os.getpid(),'fila_rnn_gpu_ativa_informada_pelo_root':True,
            'execucao_concorrente_autorizada_com_limite_1GiB':True,'fila_existente_alterada_ou_interrompida':False}}
    try:
        for tarefa in TAREFAS:
            ctx = x.preparar_contexto(tarefa, 'selecao', 'completa')
            t, v = ctx.janelas['ajuste'], ctx.janelas['validacao']
            xt, yt = t.normalizar(ctx.escalas['selecao'])
            xv, yv = v.normalizar(ctx.escalas['selecao'])
            pt, pv = selecionar_indices(t.localidade_id,N_TREINO), selecionar_indices(v.localidade_id,N_VALIDACAO)
            escala = ctx.escalas['selecao'].set_index('localidade_id').loc[v.localidade_id[pv]]
            dados = {'xt':xt[pt], 'yt':yt[pt], 'it':t.localidade_id[pt],
                     'xv':xv[pv], 'yv':yv[pv], 'iv':v.localidade_id[pv],
                     'amplitude':escala.amplitude_escala_wm2.to_numpy(float),
                     'minimo':escala.minimo_treino_wm2.to_numpy(float)}
            if len(np.unique(dados['it'])) != 10 or len(np.unique(dados['iv'])) != 10:
                raise ValueError('Piloto deve incluir as dez localidades.')
            for modelo in MODELOS:
                pasta = destino/tarefa/modelo.lower()
                seed = plano()['sementes'][tarefa]
                par = x.parametros(ctx,modelo)
                cabecalho = {'tarefa':tarefa,'modelo':modelo,'seed':seed,'parametros_reais':par,
                    'tarefa_real':x.asdict(ctx.tarefa), 'protocolo_real':ctx.protocolo,
                    'hashes_entradas':x.hashes(ctx.entradas),
                    'indices_treino':pt.tolist(),'indices_validacao':pv.tolist(),
                    'hashes_matrizes':{k:hash_array(a) for k,a in dados.items()}}
                m.salvar_json_atomico(cabecalho,pasta/'contrato_piloto.json')
                execucoes = []
                for repeticao in range(1,REPETICOES+1):
                    print(tarefa,modelo,'repeticao',repeticao,'inicio',flush=True)
                    execucoes.append(executar_repeticao(ctx,modelo,seed,dados,pasta/f'repeticao_{repeticao}',x,m,torch))
                comparacao = comparar_execucoes(*execucoes)
                m.salvar_json_atomico(comparacao,pasta/'comparacao.json')
                resultado['pares'].append({'tarefa':tarefa,'modelo':modelo,**comparacao,
                    'contrato_piloto_sha256':m.sha256_arquivo(pasta/'contrato_piloto.json')})
                m.salvar_json_atomico(resultado,destino/'resultado.json')
                print(tarefa,modelo,'bitexato',comparacao['ok'],flush=True)
                if not comparacao['ok']:
                    raise ValueError('Piloto nao reproduziu integralmente as duas execucoes; preservar para inspecao.')
        resultado['ok'] = len(resultado['pares'])==len(TAREFAS)*len(MODELOS)
        resultado['fim_utc'] = x.agora()
        resultado['memoria']['pico_allocator_alocado_bytes'] = torch.cuda.max_memory_allocated(0)
        resultado['memoria']['pico_allocator_reservado_bytes'] = torch.cuda.max_memory_reserved(0)
        resultado['fontes_sha256'].update(x.hashes([p for p in destino.rglob('*')
            if p.is_file() and p != destino/'resultado.json']))
        m.salvar_json_atomico(resultado,destino/'resultado.json')
        r = resumo_estavel(resultado)
        r['fontes_sha256'] = {**r['fontes_sha256'],str((destino/'resultado.json').resolve()):m.sha256_arquivo(destino/'resultado.json')}
        r['evidencia_completa'] = {'path':str(destino/'resultado.json'),'sha256':m.sha256_arquivo(destino/'resultado.json')}
        m.salvar_json_atomico(r,REL/'piloto_treinamento_estrito.json')
    except BaseException as exc:
        resultado['erro'] = f'{type(exc).__name__}: {exc}'
        m.salvar_json_atomico(resultado,destino/'resultado.json')
        m.salvar_json_atomico(resumo_estavel(resultado),REL/'piloto_treinamento_estrito.json')
        raise


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--executar',action='store_true',help='Executa GPU; usar somente depois de liberar a fila.')
    ap.add_argument('--saida',type=Path,default=REL/'piloto_treino_estrito_v1')
    args = ap.parse_args()
    if not args.executar:
        print(json.dumps(plano(),ensure_ascii=False,indent=2))
        return
    executar(args.saida)


if __name__=='__main__':main()
