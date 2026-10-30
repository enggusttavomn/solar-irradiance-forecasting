'''Diagnostico somente: controles Transformer/Informer, sem treino nem emissao de aceite.'''
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import platform
import warnings

from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as x
from codigo_fonte.experimentos import experimento_baselines_adicionais as e
from codigo_fonte.experimentos import experimento_baselines_gpu as g
from codigo_fonte.experimentos import experimento_multirresolucao as m
import numpy as np
import pandas as pd
import torch

REL = x.RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929/investigacao_atencao'
TAREFAS = ('daily_30', 'hourly_72_extension')
MODELOS = ('Transformer', 'Informer')


def igual(a, b):
    return bool(np.array_equal(np.asarray(a), np.asarray(b)))


def arrays_hash(a):
    import hashlib
    z = np.ascontiguousarray(a)
    return {'shape': list(z.shape), 'dtype': str(z.dtype), 'sha256': hashlib.sha256(z.tobytes()).hexdigest()}


def normalizar_sem_y(j, escala):
    s = escala.set_index('localidade_id').loc[j.localidade_id]
    v = (j.x_bruto.astype(np.float32) - s.minimo_treino_wm2.to_numpy(np.float32)[:,None])
    return v / s.amplitude_escala_wm2.to_numpy(np.float32)[:,None]


def auditar_dados(original, novo, fase):
    part = 'validacao' if fase == 'selecao' else 'teste'
    oldpart = 'validacao_2023' if fase == 'selecao' else 'teste_2024'
    ajuste = 'ajuste' if fase == 'selecao' else 'refit'
    registros = {}
    for a, b in ((ajuste, ajuste), (oldpart, part)):
        jo, jn = original.janelas[a], novo.janelas[b]
        xo, yo = jo.normalizar(original.escalas[fase])
        xn, yn = jn.normalizar(novo.escalas[fase])
        campos = {'x_bruto': igual(jo.x_bruto, jn.x_bruto), 'y_bruto': igual(jo.y_bruto, jn.y_bruto),
                  'ids': igual(jo.localidade_id, jn.localidade_id), 'x_normalizado': igual(xo, xn),
                  'y_normalizado': igual(yo, yn), 'normalizacao_independente': igual(xn, normalizar_sem_y(jn, novo.escalas[fase]))}
        if novo.tarefa.resolucao == 'horaria':
            campos['origens'] = igual(jo.origem_utc, jn.origem_utc)
        else:
            campos['origens'] = igual(jo.origem.to_numpy(), jn.origem.to_numpy())
            campos['datas_alvo'] = igual(jo.datas_alvo, jn.datas_alvo)
        registros[b] = {'igualdade_bitexata': campos, 'x_normalizado': arrays_hash(xn), 'y_normalizado': arrays_hash(yn)}
    return {'ok': all(all(r['igualdade_bitexata'].values()) for r in registros.values()), 'particoes': registros}


def rede_gpu(ctx, modelo, seed, state=None):
    m.fixar_semente(seed, 1)
    rede = e.redes.criar_baseline(modelo, ctx.tarefa.seq_len, ctx.tarefa.pred_len, len(ctx.series))
    if state is not None:
        rede.load_state_dict(state, strict=True)
    return g.no_dispositivo(rede, torch.device('cuda'))


def prever(rede, j, escala, lote):
    j = copy.copy(j)
    object.__setattr__(j, 'y_bruto', np.full_like(j.y_bruto, np.nan))
    xn = normalizar_sem_y(j, escala)
    return j.inverter(m.prever_rede(rede, xn, j.localidade_id, batch_size=lote), escala)


def replay(ctx, modelo, seed, checkpoint, cache, chave, fase):
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    rede = rede_gpu(ctx, modelo, seed, payload['state_dict'])
    part = 'validacao' if fase == 'selecao' else 'teste'
    lote = int(x.parametros(ctx, modelo)['batch_size'])
    bruto = prever(rede, ctx.janelas[part], ctx.escalas[fase], lote)
    # Uma segunda passagem sem reset do RNG testa a independencia da avaliacao.
    estado_rng = torch.cuda.get_rng_state().clone()
    segundo = prever(rede, ctx.janelas[part], ctx.escalas[fase], lote)
    rng_igual = bool(torch.equal(estado_rng, torch.cuda.get_rng_state()))
    with np.load(cache, allow_pickle=False) as z:
        esperado = z[chave]
    delta = float(np.max(np.abs(bruto - esperado)))
    repeticao = float(np.max(np.abs(bruto - segundo)))
    resultado = {'checkpoint': str(checkpoint), 'checkpoint_sha256': m.sha256_arquivo(checkpoint),
        'cache': str(cache), 'cache_sha256': m.sha256_arquivo(cache), 'seed': seed, 'fase': fase,
        'epocas': payload['epocas'], 'max_replay_wm2': delta, 'estrito_1e_6': bool(delta <= 1e-6),
        'max_repeticao_sem_reset_rng_wm2': repeticao, 'rng_cuda_global_inalterado_eval': rng_igual,
        'alvos_nan': True, 'batch_size': lote, 'n_previsoes': bruto.size}
    del rede
    torch.cuda.empty_cache()
    return resultado


def experimento_lote(ctx, modelo, seed):
    par = x.parametros(ctx, modelo)
    j = ctx.janelas['ajuste']
    xn, yn = j.normalizar(ctx.escalas['selecao'])
    dl = m._carregador(xn, yn, j.localidade_id, batch_size=par['batch_size'], embaralhar=True, semente=seed)
    xb, yb, ids = next(iter(dl))
    original = rede_gpu(ctx, modelo, seed)
    novo = x.nova_rede(ctx, modelo, seed, par)
    estado_igual = all(torch.equal(v, novo.state_dict()[k]) for k,v in original.state_dict().items())
    estado = copy.deepcopy(original.state_dict())

    def passagem(rede, strict=False):
        rede.load_state_dict(estado, strict=True)
        rede.zero_grad(set_to_none=True)
        rede.train()
        m.fixar_semente(seed, 1)
        if strict:
            torch.use_deterministic_algorithms(True, warn_only=False)
        with warnings.catch_warnings(record=True) as avisos:
            warnings.simplefilter('always')
            y = rede(xb, ids)
            loss = ((y-yb)**2).mean()
            loss.backward()
        grad = torch.cat([p.grad.detach().cpu().reshape(-1) for p in rede.parameters() if p.grad is not None])
        return y.detach(), grad, [str(a.message) for a in avisos]

    saidas = [passagem(original), passagem(novo), passagem(novo), passagem(novo)]
    deltas = [{'repeticao': i, 'max_saida_normalizada': float(torch.max(torch.abs(s[0]-saidas[0][0]))),
               'max_gradiente_normalizado': float(torch.max(torch.abs(s[1]-saidas[0][1])))} for i,s in enumerate(saidas[1:],1)]
    erro_strict = None
    try:
        passagem(novo, strict=True)
    except RuntimeError as exc:
        erro_strict = str(exc)
    from torch.nn.attention import sdpa_kernel, SDPBackend
    matematico = {}
    try:
        with sdpa_kernel(SDPBackend.MATH):
            a, b = passagem(novo, strict=True), passagem(novo, strict=True)
        matematico = {'executou': True, 'max_saida_repetida': float(torch.max(torch.abs(a[0]-b[0]))),
                     'max_gradiente_repetido': float(torch.max(torch.abs(a[1]-b[1]))),
                     'avisos': a[2] + b[2]}
    except RuntimeError as exc:
        matematico = {'executou': False, 'erro': str(exc)}
    finally:
        m.fixar_semente(seed, 1)
    return {'seed': seed, 'batch_size': par['batch_size'], 'estado_inicial_original_novo_exato': estado_igual,
            'sem_optimizer_step': True, 'mesmo_lote_e_rng_reposto_em_cada_passagem': True,
            'repeticoes_backend_original': deltas,
            'avisos': sorted({a for s in saidas for a in s[2]}),
            'backend_original_com_determinismo_estrito_erro': erro_strict,
            'backend_matematico_com_determinismo_estrito': matematico}


def main():
    REL.mkdir(parents=True, exist_ok=True)
    ambiente = {'python': platform.python_version(), 'torch': torch.__version__, 'cuda': torch.version.cuda,
                'cudnn': torch.backends.cudnn.version(), 'gpu': torch.cuda.get_device_name(0),
                'cublas_workspace_config': os.environ.get('CUBLAS_WORKSPACE_CONFIG')}
    saidas = []
    for tarefa in TAREFAS:
        antigo_ctx = e.preparar_contexto(tarefa, 'completa')
        for modelo in MODELOS:
            pasta = x.SAIDA / 'atual' / tarefa / modelo.lower()
            fonte = e.SAIDA / tarefa / modelo.lower()
            contrato = x.ler_json(pasta / 'contrato_execucao.json')
            antigo = x.ler_json(fonte / 'contrato.json')
            x.conferir_hashes(contrato['codigo'])
            x.conferir_hashes(contrato['entradas'])
            rows, dados = [], {}
            rec = {'tarefa': tarefa, 'modelo': modelo, 'sem_treinamento': True, 'nao_emite_aceite': True,
                   'ambiente_atual': ambiente, 'ambiente_original': {'python': antigo['python'],
                   'pacotes': antigo['pacotes'], **antigo['execucao']}, 'dados': dados, 'replays': rows,
                   'divergencia_registrada': x.ler_json(pasta/'controle_validacao_divergencia.json'),
                   'fontes_sha256': x.hashes([pasta/'contrato_execucao.json',fonte/'contrato.json', Path(__file__)])}
            rec['fontes_codigo_originais'] = [{**r,'sha256_atual': m.sha256_arquivo(Path(r['arquivo'])),
                  'exato': r['sha256']==m.sha256_arquivo(Path(r['arquivo']))} for r in antigo['arquivos_codigo']]
            rec['configuracao_canonica_igual'] = contrato['parametros']['configuracao'] == antigo['configuracao_canonica']
            po, pn = antigo['parametros'], contrato['parametros']
            rec['parametros_iguais'] = {a: po[a]==pn[b] for a,b in [('batch_size','batch_size'),
                 ('max_epocas','max_epocas'),('paciencia','paciencia'),('sementes','sementes')]}
            rec['parametros_iguais'].update(lr=po['lr']==pn['configuracao']['taxa_aprendizado'],
                weight_decay=po['weight_decay']==pn['configuracao']['peso_decay'])
            for fase, part in [('selecao','validacao'), ('refit','teste')]:
                ctx = x.preparar_contexto(tarefa, fase, 'completa', contrato['protocolo'], modelo)
                dados[fase] = auditar_dados(antigo_ctx, ctx, fase)
                if fase == 'selecao':
                    rec['lote_inicial'] = experimento_lote(ctx, modelo, pn['sementes'][0])
                for seed in pn['sementes']:
                    oldcp = fonte / 'modelos' / f'seed{seed}_{fase}.pt'
                    oldcache = fonte / 'cache' / f'seed{seed}.npz'
                    row = replay(ctx, modelo, seed, oldcp, oldcache,
                                 'validacao_2023_bruta' if fase=='selecao' else 'teste_2024_bruta', fase)
                    row['tipo'] = 'original'
                    rows.append(row)
                    print(tarefa, modelo, fase, seed, 'original', row['max_replay_wm2'], flush=True)
                    if fase == 'selecao':
                        newcp = pasta/'sem_quantizacao/modelos'/f'seed{seed}_{fase}.pt'
                        newcache = pasta/'sem_quantizacao'/fase/f'seed{seed}.npz'
                        row = replay(ctx, modelo, seed, newcp, newcache, 'previsao', fase)
                        row['tipo'] = 'novo'
                        rows.append(row)
                        print(tarefa, modelo, fase, seed, 'novo', row['max_replay_wm2'], flush=True)
                del ctx
            from codigo_fonte.analises_e_relatorios.parecer_controles_quantizacao import parecer
            fp = parecer(pasta, 'selecao', REL / 'metricas')
            rec['comparacao_metricas'] = {'path': str(fp), 'sha256': m.sha256_arquivo(fp)}
            path = REL / f'{tarefa}_{modelo.lower()}.json'
            m.salvar_json_atomico(rec, path)
            saidas.append({'path': str(path), 'sha256':m.sha256_arquivo(path)})
            print('PARECER',path,flush=True)
        del antigo_ctx
    m.salvar_json_atomico({'relatorios':saidas, 'sem_treinamento':True, 'nao_emite_aceite':True,
                          'gerado_em_utc':x.agora()}, REL/'indice.json')


if __name__ == '__main__':
    main()
