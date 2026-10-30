"""Politica prospectiva e verificacao de seis migracoes CPU -> CUDA.

Preparar politica nao audita modelos. Avaliar gera evidencias. Emitir um aceite
exige revisao externa que fixe hashes da politica e deste verificador.
Retomar treinamento e uma opcao separada, destinada ao orquestrador.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import gc
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[2]
REL = RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929'
RESULTADOS = RAIZ / 'resultados/quantizacao_todos_modelos_20260929'
MODELOS = ('GRU', 'LSTM', 'DilatedRNN')
TAREFAS = ('daily_30', 'hourly_72_extension')
FASES = {'validacao': 'selecao', 'teste': 'refit'}
LIMITES = {'replay_novo_atol_wm2': 1e-6, 'replay_novo_rtol': 0,
           'replay_antigo_atol_wm2': 1e-4, 'replay_antigo_rtol': 1e-6,
           'lote_saida_atol_normalizado': 1e-5, 'lote_gradiente_atol_normalizado': 1e-4,
           'lote_rtol': 0}


def exigir(condicao, mensagem):
    if not condicao:
        raise ValueError(mensagem)


def ler(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def hash_obj(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def verificar_hashes(fontes):
    for path, digest in fontes.items():
        exigir(sha256(path) == digest, f'Fonte/evidencia alterada: {path}')


def mapa_hashes(paths):
    return {str(Path(p).resolve()): sha256(p) for p in sorted(set(map(Path, paths)), key=str)}


def gravar_novo(obj, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    exigir(not path.exists(), f'Arquivo existente nao sera sobrescrito: {path}')
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding='utf-8')


def caminho_originais(tarefa, modelo):
    return REL / 'auditoria_controles_originais' / f'{tarefa}_{modelo.lower()}.json'


def preparar_politica(destino):
    """Somente congela a proposta e suas fontes; nao executa/autoriza a politica."""
    fontes = [Path(__file__), RAIZ/'codigo_fonte/acompanhamento/registrar_controle_gpu_revisado.py',
              RAIZ/'codigo_fonte/analises_e_relatorios/auditar_controle_gpu_parcial.py', RAIZ/'codigo_fonte/analises_e_relatorios/parecer_controles_quantizacao.py',
              RAIZ/'codigo_fonte/acompanhamento/metricas_quantizacao_todos.py', RAIZ/'testes/test_quantizacao_controle_gpu.py',
              RAIZ/'testes/test_migracao_controles_gpu.py', REL/'testes_politica_migracao_gpu.xml',
              RAIZ/'resultados/avaliacao_horaria_timesnet/configuracao_execucao.json']
    for tarefa in TAREFAS:
        fontes += [RAIZ/'resultados/avaliacao_multirresolucao_corrigida_v2'/tarefa/'contrato_execucao.json',
                   RAIZ/'resultados/avaliacao_baselines_revisao_20260912'/tarefa/'gru/contrato.json']
        for modelo in MODELOS:
            path = caminho_originais(tarefa, modelo)
            a = ler(path)
            exigir(a['aprovado'] is True, f'Auditoria original reprovada: {path}')
            fontes.append(path)
            for chave in ('codigo_auditoria_sha256', 'fontes_sha256'):
                verificar_hashes(a[chave])
                fontes.extend(a[chave])
            for chave, pk in [('evidencia_complementar_loop', 'testes'),
                              ('relatorio_testes_loop', 'arquivo'), ('fonte_ambiente_original', 'arquivo')]:
                verificar_hashes({a[chave][pk]: a[chave]['sha256']})
                fontes.append(a[chave][pk])
    politica = {'schema': 1, 'nome': 'migracoes_cpu_cuda_seis_pares_v1',
        'estado': 'proposta_exige_revisao_externa_antes_de_emitir',
        'regime': 'atual', 'modo': 'completa', 'modelos': list(MODELOS), 'tarefas': list(TAREFAS),
        'particoes': list(FASES), 'dispositivo_original': 'cpu', 'dispositivo_novo': 'cuda',
        'limites': LIMITES, 'metricas_decidem_aceite': False,
        'primeiro_lote_sem_optimizer_step': True, 'ausencias_originais_devem_ser_declaradas': True,
        'objetivo': 'Validar novos controles CUDA para comparacao com niveis no mesmo ambiente; nao reproduzir treino CPU.',
        'exclusoes': ['Transformer', 'Informer', 'CPU inalterado', 'mensais', 'historicos', 'smoke'],
        'falhas_tecnicas': 'Interromper sem apagar caches, sem ampliar tolerancias e sem aceitar automaticamente.',
        'retomada': 'Somente opt-in --retomar apos aceite; orquestrador externo controla concorrencia.',
        'criado_em_utc': datetime.now(timezone.utc).isoformat(), 'fontes_sha256': mapa_hashes(fontes)}
    politica['sha256_conteudo'] = hash_obj(politica)
    gravar_novo(politica, destino)
    print(f'Proposta preparada, sem autorizacao de emissao: {destino}', flush=True)
    return politica


def validar_politica(path):
    p = ler(path)
    exigir(p.get('schema') == 1 and p.get('nome') == 'migracoes_cpu_cuda_seis_pares_v1', 'Politica desconhecida.')
    exigir(p.get('sha256_conteudo') == hash_obj({k: v for k, v in p.items() if k != 'sha256_conteudo'}),
           'Hash de conteudo da politica invalido.')
    exigir(p.get('modelos') == list(MODELOS) and p.get('tarefas') == list(TAREFAS)
           and p.get('particoes') == list(FASES), 'Escopo da politica alterado.')
    exigir(p.get('regime') == 'atual' and p.get('modo') == 'completa'
           and p.get('dispositivo_original') == 'cpu' and p.get('dispositivo_novo') == 'cuda',
           'Politica fora da migracao aprovada para estudo.')
    exigir(p.get('limites') == LIMITES and p.get('metricas_decidem_aceite') is False
           and p.get('primeiro_lote_sem_optimizer_step') is True
           and p.get('ausencias_originais_devem_ser_declaradas') is True,
           'Criterios prospectivos alterados.')
    exigir(p['fontes_sha256'].get(str(Path(__file__).resolve())) == sha256(__file__),
           'Politica nao congela este verificador.')
    verificar_hashes(p['fontes_sha256'])
    return p


def validar_revisao(path, politica_path):
    exigir(path is not None, 'Emissao exige arquivo de revisao externa; proposta nao e aceite.')
    r = ler(path)
    exigir(r.get('aprovado') is True, 'Revisao nao aprovada.')
    exigir(r.get('politica_sha256') == sha256(politica_path), 'Revisao de outra politica.')
    exigir(r.get('verificador_sha256') == sha256(__file__), 'Revisao de outro verificador.')
    exigir(bool(str(r.get('revisor', '')).strip()) and bool(str(r.get('justificativa', '')).strip()),
           'Revisao sem autoria/justificativa.')
    return r


def validar_escopo(c, d, pasta, particao):
    exigir(particao in FASES, 'Particao invalida.')
    modelo, tarefa = c.get('modelo'), c.get('tarefa', {}).get('slug')
    exigir(modelo in MODELOS and tarefa in TAREFAS, 'Modelo/tarefa fora da politica prospectiva.')
    exigir(c.get('modo') == 'completa' and c.get('protocolo', {}).get('regime') == 'atual', 'Outro modo/regime.')
    exigir(Path(pasta).resolve() == (RESULTADOS/'atual'/tarefa/modelo.lower()).resolve(), 'Pasta fora do escopo.')
    p = c['parametros']
    exigir(p.get('novo_controle_por_dispositivo') is True and p.get('dispositivo_original') == 'cpu'
           and p.get('dispositivo') == 'cuda', 'Somente troca CPU para CUDA e coberta.')
    exigir(d.get('novo_controle_por_dispositivo') is True and d.get('dispositivo_original') == 'cpu'
           and d.get('dispositivo') == 'cuda', 'Divergencia fora da troca CPU para CUDA.')
    exigir(d.get('contrato_sha256') == c.get('sha256_contrato') and d.get('alvos_primarios_bitexatos') is True,
           'Contrato ou alvos divergentes.')
    seeds = [42] if tarefa == 'hourly_72_extension' else [11, 23, 42, 67, 89]
    exigir(p.get('sementes') == seeds, 'Conjunto/ordem de sementes divergente.')
    return modelo, tarefa, FASES[particao]


def validar_originais(a, modelo, tarefa, seeds):
    exigir(a.get('aprovado') is True and a.get('modelo') == modelo and a.get('tarefa') == tarefa,
           'Auditoria original nao corresponde ao par.')
    verificar_hashes(a['codigo_auditoria_sha256'])
    verificar_hashes(a['fontes_sha256'])
    cobertos = set()
    for cp in a['resultados']:
        exigir(cp['aprovado'] is True and cp['paridade_numerica_aproximada_aprovada'] is True
               and cp['atol_compatibilidade_wm2'] == LIMITES['replay_antigo_atol_wm2']
               and cp['rtol_compatibilidade'] == LIMITES['replay_antigo_rtol']
               and cp['max_razao_limite_tolerancia'] <= 1, 'Checkpoint antigo fora da politica numerica.')
        verificar_hashes({cp['checkpoint']: cp['checkpoint_sha256'],
                          cp['previsoes_originais']: cp['previsoes_originais_sha256']})
        par = (cp['fase'], cp['seed'])
        exigir(par not in cobertos, 'Checkpoint antigo duplicado.')
        cobertos.add(par)
    ausentes = set()
    for item in a['ausencias']:
        exigir(not Path(item['arquivo_ausente']).exists(), 'Checkpoint antes ausente agora existe; requer nova auditoria.')
        par = (item['fase'], item['seed'])
        exigir(par not in cobertos and par not in ausentes, 'Ausencia duplicada/inconsistente.')
        ausentes.add(par)
    exigir(cobertos | ausentes == {(fase, seed) for fase in FASES.values() for seed in seeds},
           'Falta enumerar checkpoint antigo ou ausencia.')
    exigir(set(a['fases_sem_checkpoint_original']) == {f for f, _ in ausentes}, 'Fases ausentes inconsistentes.')
    exigir(len(cobertos) == a['checkpoints_reproduzidos'] and bool(cobertos), 'Sem checkpoint antigo auditado.')


def validar_lote(lote):
    exigir(lote.get('estado_inicial_bitexato') is True and lote.get('parametros_apos_backward_inalterados') is True,
           'Estado inicial ou pesos do lote foram alterados.')
    exigir(lote.get('optimizer_step_executado') is False, 'Auditoria de lote nao pode otimizar pesos.')
    saida = lote['max_delta_previsao_normalizada']
    grads = lote['max_delta_gradientes']
    exigir(0 <= saida <= LIMITES['lote_saida_atol_normalizado'], 'Primeira saida CPU/CUDA fora da tolerancia.')
    exigir(bool(grads) and all(0 <= g <= LIMITES['lote_gradiente_atol_normalizado'] for g in grads.values()),
           'Primeiro gradiente CPU/CUDA fora da tolerancia.')


def provas_estrutura_dados_lote(c, fase, originais):
    import numpy as np
    import torch
    from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as x
    from codigo_fonte.experimentos import experimento_multirresolucao as m
    from codigo_fonte.experimentos import experimento_horario_timesnet as h
    modelo, tarefa, par = c['modelo'], c['tarefa']['slug'], c['parametros']
    exigir(c['pacotes'] == {nome: importlib.metadata.version(nome) for nome in c['pacotes']}
           and c['cuda'] == torch.version.cuda, 'Ambiente de bibliotecas/CUDA diverge do contrato novo.')
    ctx = x.preparar_contexto(tarefa, fase, 'completa', c['protocolo'], modelo)
    original = x.e.preparar_contexto(tarefa, 'completa')
    base = ler(RAIZ/'resultados/avaliacao_multirresolucao_corrigida_v2'/tarefa/'contrato_execucao.json')
    exigir(base['configuracao'] == par['configuracao'], 'Configuracao canonica modificada.')
    codigo_orig = base['codigo_sha256'][str(Path(m.__file__).resolve())]
    restaurado = Path(m.__file__).read_bytes().replace(
        b'codigo_fonte/experimentos/experimento_multirresolucao.py', b'executar_avaliacao_multirresolucao.py')
    exigir(hashlib.sha256(restaurado).hexdigest() == codigo_orig, 'Loop original alterado alem do caminho do wrapper.')
    exigir(c['tarefa'] == json.loads(json.dumps(x.asdict(original.tarefa))), 'Tarefa diferente do executor original.')
    treino_part = 'ajuste' if fase == 'selecao' else 'refit'
    avaliacao = 'validacao' if fase == 'selecao' else 'teste'
    avaliacao_antiga = 'validacao_2023' if fase == 'selecao' else 'teste_2024'
    dados = {}
    for part, ant in [(treino_part, treino_part), (avaliacao, avaliacao_antiga)]:
        a, b = ctx.janelas[part], original.janelas[ant]
        cols = ('x_bruto', 'y_bruto', 'localidade_id', 'localidade') + (
            ('origem_utc', 'origem_local') if tarefa == 'hourly_72_extension' else ('origem', 'datas_alvo'))
        checks = {k: bool(np.array_equal(getattr(a, k), getattr(b, k))) for k in cols}
        an, bn = a.normalizar(ctx.escalas[fase]), b.normalizar(original.escalas[fase])
        checks.update(x_normalizado_bitexato=bool(np.array_equal(an[0], bn[0])),
                      y_normalizado_bitexato=bool(np.array_equal(an[1], bn[1])))
        exigir(all(checks.values()), f'Dados/normalizacao diferentes em {part}: {checks}')
        dados[part] = checks
    conf = m.ConfiguracaoMultirresolucao(**par['configuracao'])
    esperados = {'batch_size': conf.batch_size_diario, 'max_epocas': conf.max_epocas_diario,
                 'paciencia': conf.paciencia_diario, 'perda': 'mse', 'criterio_epocas': 'MSE_normalizado'}
    exigir(all(par[k] == v for k, v in esperados.items()), 'Hiperparametros/criterio de selecao diferentes.')
    if modelo == 'GRU':
        antigo = ler(RAIZ/'resultados/avaliacao_baselines_revisao_20260912'/tarefa/'gru/contrato.json')
        exigir(antigo['configuracao_canonica'] == par['configuracao'], 'Configuracao GRU diferente.')
        ap = antigo['parametros']
        exigir(ap['batch_size'] == par['batch_size'] and ap['max_epocas'] == par['max_epocas']
               and ap['paciencia'] == par['paciencia'] and ap['lr'] == conf.taxa_aprendizado
               and ap['weight_decay'] == conf.peso_decay and ap['sementes'] == par['sementes'],
               'Parametros originais GRU diferentes.')
    seed = par['sementes'][0]
    cpupar = copy.deepcopy(par)
    cpupar['dispositivo'] = 'cpu'
    cpu = x.nova_rede(ctx, modelo, seed, cpupar)
    gpu = x.nova_rede(ctx, modelo, seed, par)
    if modelo == 'LSTM' and tarefa == 'hourly_72_extension':
        antigo_h = ler(RAIZ/'resultados/avaliacao_horaria_timesnet/configuracao_execucao.json')
        hc = h.ConfiguracaoExperimentoHorario(modo_execucao='completa', semente=seed)
        exigir(antigo_h == json.loads(json.dumps(x.asdict(hc))), 'Configuracao LSTM horaria diferente.')
        cpu_original = h.criar_lstm(hc, len(ctx.series))
        exigir(all(torch.equal(v, cpu_original.state_dict()[k]) for k, v in cpu.state_dict().items()),
               'Inicializacao difere da LSTM horaria original.')
        del cpu_original
    old_path = Path(next(cp['checkpoint'] for cp in originais['resultados'] if cp['seed'] == seed))
    old_cp = torch.load(old_path, map_location='cpu', weights_only=False)
    estado_old = old_cp.get('state_dict', old_cp.get('estado_modelo'))
    shapes = {k: list(v.shape) for k, v in cpu.state_dict().items()}
    exigir(shapes == {k: list(v.shape) for k, v in estado_old.items()}, 'Arquitetura de CP antigo diferente.')
    inicial = {k: v.detach().cpu().clone() for k, v in cpu.state_dict().items()}
    iguais = all(torch.equal(v, gpu.state_dict()[k].cpu()) for k, v in inicial.items())
    treino = ctx.janelas[treino_part]
    xn, yn = treino.normalizar(ctx.escalas[fase])
    loader = h._carregador_torch if modelo == 'LSTM' and tarefa == 'hourly_72_extension' else m._carregador
    xb, yb, ids = next(iter(loader(xn, yn, treino.localidade_id, batch_size=par['batch_size'],
                                  embaralhar=True, semente=seed)))
    cpu.train(); gpu.train()
    pc, pg = cpu(xb, ids), gpu(xb, ids)
    lc, lg = ((pc-yb)**2).mean(), ((pg-yb)**2).mean()
    lc.backward(); lg.backward()
    gradientes = {k: float((p.grad.cpu()-dict(gpu.named_parameters())[k].grad.cpu()).abs().max().detach())
                  for k, p in cpu.named_parameters()}
    inalterados = all(torch.equal(v, cpu.state_dict()[k].cpu()) and torch.equal(v, gpu.state_dict()[k].cpu())
                      for k, v in inicial.items())
    lote = {'seed': seed, 'batch_size': len(xb), 'estado_inicial_bitexato': iguais,
        'parametros_apos_backward_inalterados': inalterados, 'optimizer_step_executado': False,
        'max_delta_previsao_normalizada': float((pc-pg).abs().max().detach()),
        'max_delta_gradientes': gradientes, 'mse_cpu': float(lc.detach()), 'mse_gpu': float(lg.detach())}
    validar_lote(lote)
    # Metadados e hashes de todos os checkpoints/caches novos, alem do replay posterior.
    pasta = RESULTADOS/'atual'/tarefa/modelo.lower()
    for s in par['sementes']:
        meta = ler(pasta/'sem_quantizacao'/fase/f'seed{s}.json')
        exigir(meta['contrato_sha256'] == c['sha256_contrato'] and meta['seed'] == s
               and meta['fase'] == fase and meta['niveis'] is None
               and meta['variante'] == 'sem_quantizacao', 'Metadados de cache de outra configuracao.')
        verificar_hashes(meta['arquivos_sha256'])
        cp = torch.load(pasta/'sem_quantizacao/modelos'/f'seed{s}_{fase}.pt', map_location='cpu', weights_only=False)
        prep = cp['preprocessamento']
        exigir(prep['minmax'] is True and prep['niveis'] is None and prep['quantizacao_somente_X'] is True
               and prep['dispositivo'] == 'cuda' and prep['batch_size'] == par['batch_size']
               and prep['escalas'] == ctx.escalas[fase].to_dict('records'), 'Preprocessamento do CP inconsistente.')
        if fase == 'refit':
            _, selecao = x.validar_selecao(pasta)
            linha = next(v for v in selecao['ranking'] if v['nome'] == 'sem_quantizacao')
            exigir(cp['epocas'] == linha['epocas'][str(s)]
                   and cp['selecao_sha256'] == sha256(pasta/'selecao_congelada.json'), 'Refit nao respeita selecao congelada.')
    ambiente = {'torch': torch.__version__, 'cuda': torch.version.cuda, 'cudnn': torch.backends.cudnn.version(),
                'gpu': torch.cuda.get_device_name(0), 'deterministic_algorithms': torch.are_deterministic_algorithms_enabled(),
                'deterministic_warn_only': torch.is_deterministic_algorithms_warn_only_enabled()}
    del cpu, gpu, ctx, original, old_cp
    gc.collect(); torch.cuda.empty_cache()
    return {'dados': dados, 'configuracao_igual': True, 'codigo_loop_original_preservado': True,
            'arquitetura_shapes': shapes, 'lote_inicial': lote, 'ambiente': ambiente}


def avaliar(pasta, particao, politica_path):
    from codigo_fonte.experimentos import experimento_quantizacao_concorrentes as x
    from codigo_fonte.analises_e_relatorios.auditar_controle_gpu_parcial import auditar
    from codigo_fonte.analises_e_relatorios.parecer_controles_quantizacao import parecer
    politica = validar_politica(politica_path)
    pasta = Path(pasta).resolve()
    c = ler(pasta/'contrato_execucao.json')
    dpath = pasta/f'controle_{particao}_divergencia.json'
    d = ler(dpath)
    modelo, tarefa, fase = validar_escopo(c, d, pasta, particao)
    exigir(c['sha256_contrato'] == x.hash_obj({k: v for k, v in c.items() if k != 'sha256_contrato'}),
           'Hash do contrato incorreto.')
    for fontes in (c['codigo'], c['entradas'], c['parametros']['fontes_configuracao']):
        verificar_hashes(fontes)
    apath = caminho_originais(tarefa, modelo)
    a = ler(apath)
    validar_originais(a, modelo, tarefa, c['parametros']['sementes'])
    destino = REL/'politica_migracao_cpu_cuda'/tarefa/modelo.lower()/particao
    relatorio = destino/'verificacao.json'
    if relatorio.exists():
        r = ler(relatorio)
        exigir(r['ok'] is True and r['contrato_sha256'] == c['sha256_contrato']
               and r['politica_sha256'] == sha256(politica_path), 'Evidencia existente de outro contrato/politica.')
        verificar_hashes(r['fontes_sha256'])
        return relatorio
    exigir(not destino.exists() or not any(destino.iterdir()), 'Auditoria parcial preservada; investigar antes de repetir.')
    destino.mkdir(parents=True, exist_ok=True)
    try:
        provas = provas_estrutura_dados_lote(c, fase, a)
        gravar_novo(provas, destino/'estrutura_dados_lote.json')
        replay_path = destino/'replay_novo.json'
        replay = auditar(pasta, fase, replay_path)
        exigir(replay['ok'] is True and {cp['seed'] for cp in replay['checkpoints']} == set(c['parametros']['sementes']),
               'Replay novo incompleto.')
        for cp in replay['checkpoints']:
            exigir(cp['aprovado'] is True and 0 <= cp['max_diferenca_wm2'] <= LIMITES['replay_novo_atol_wm2']
                   and cp['alvos_substituidos_por_nan'] is True, 'Replay novo fora da politica.')
        ppath = parecer(pasta, fase, destino)
        exigir(ppath is not None, 'Parecer descritivo ausente.')
        fontes = [Path(__file__), Path(politica_path), pasta/'contrato_execucao.json', dpath,
                  apath, destino/'estrutura_dados_lote.json', replay_path, ppath]
        fontes += [Path(cp[k]) for cp in replay['checkpoints'] for k in ('checkpoint', 'cache')]
        fontes += [pasta/'sem_quantizacao'/fase/f'seed{s}.json' for s in c['parametros']['sementes']]
        for seed in c['parametros']['sementes']:
            fontes.extend(ler(pasta/'sem_quantizacao'/fase/f'seed{seed}.json')['arquivos_sha256'])
        r = {'ok': True, 'modelo': modelo, 'tarefa': tarefa, 'fase': fase, 'particao': particao,
             'contrato_sha256': c['sha256_contrato'], 'politica_sha256': sha256(politica_path),
             'fontes_sha256': mapa_hashes(fontes), 'parecer': str(ppath), 'replay': str(replay_path),
             'originais': str(apath), 'fases_originais_sem_checkpoint': a['fases_sem_checkpoint_original'],
             'metricas_usadas_como_criterio': False, 'aceite_emitido_por_esta_avaliacao': False,
             'verificado_em_utc': datetime.now(timezone.utc).isoformat()}
        gravar_novo(r, relatorio)
        return relatorio
    except Exception as exc:
        gravar_novo({'ok': False, 'aceite_emitido': False, 'erro': f'{type(exc).__name__}: {exc}',
                     'contrato_sha256': c['sha256_contrato'], 'politica_sha256': sha256(politica_path)},
                    destino/'falha.json')
        raise


def emitir(pasta, particao, politica_path, revisao_path, relatorio_path):
    validar_politica(politica_path)
    revisao = validar_revisao(revisao_path, politica_path)
    r = ler(relatorio_path)
    exigir(r['ok'] is True and r['particao'] == particao
           and r['politica_sha256'] == sha256(politica_path)
           and r['metricas_usadas_como_criterio'] is False, 'Verificacao nao habilita emissao.')
    verificar_hashes(r['fontes_sha256'])
    pasta = Path(pasta).resolve()
    c = ler(pasta/'contrato_execucao.json')
    d = ler(pasta/f'controle_{particao}_divergencia.json')
    validar_escopo(c, d, pasta, particao)
    exigir(r['contrato_sha256'] == c['sha256_contrato'], 'Verificacao de outro contrato.')
    esperado = REL/'politica_migracao_cpu_cuda'/c['tarefa']['slug']/c['modelo'].lower()/particao/'verificacao.json'
    exigir(Path(relatorio_path).resolve() == esperado.resolve(), 'Relatorio fora da pasta canonica.')
    estrutura_path = esperado.parent/'estrutura_dados_lote.json'
    exigir(r['fontes_sha256'].get(str(estrutura_path.resolve())) == sha256(estrutura_path),
           'Provas estruturais nao vinculadas ao relatorio.')
    estrutura = ler(estrutura_path)
    exigir(estrutura.get('configuracao_igual') is True and estrutura.get('codigo_loop_original_preservado') is True
           and len(estrutura.get('dados', {})) == 2
           and all(checks and all(valor is True for valor in checks.values()) for checks in estrutura['dados'].values()),
           'Provas de dados/arquitetura reprovadas.')
    validar_lote(estrutura['lote_inicial'])
    from codigo_fonte.acompanhamento.registrar_controle_gpu_revisado import registrar
    args = SimpleNamespace(pasta=pasta, particao=particao, parecer=Path(r['parecer']), replay=Path(r['replay']),
        originais=Path(r['originais']), evidencias=[Path(politica_path), Path(revisao_path), Path(relatorio_path)],
        justificativa=('Aplicacao da politica prospectiva revisada de seis migracoes CPU para CUDA. '
          'Dados, arquitetura, configuracao e normalizacao preservados; primeiro lote e replays verificados. '
          'Metricas e diferencas de treinamento sao descritivas, nao criterios de aceite. '
          'CPs antigos somente nas fases disponiveis, sob politica numerica declarada. '
          'A quantizacao e comparada ao novo controle no mesmo ambiente. Revisao: '+revisao['justificativa']))
    registrar(args)


def retomar(pasta, particao, politica_path, revisao_path):
    validar_politica(politica_path)
    validar_revisao(revisao_path, politica_path)
    pasta = Path(pasta).resolve()
    c = ler(pasta/'contrato_execucao.json')
    dpath = pasta/f'controle_{particao}_divergencia.json'
    d = ler(dpath)
    modelo, tarefa, fase = validar_escopo(c, d, pasta, particao)
    from codigo_fonte.experimentos.experimento_quantizacao_concorrentes import validar_aceite_gpu
    validar_aceite_gpu(pasta/f'aceite_controle_gpu_{particao}.json', c['sha256_contrato'], d['sha256'], sha256(dpath))
    cmd = [sys.executable, '-X', 'utf8', '-m', 'codigo_fonte.experimentos.experimento_quantizacao_concorrentes',
           '--tarefa', tarefa, '--modelo', modelo, '--regime', 'atual', '--fase', fase,
           '--saida', str(RESULTADOS), '--dispositivo', 'cuda']
    subprocess.run(cmd, cwd=RAIZ, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--preparar-politica', type=Path)
    ap.add_argument('--politica', type=Path)
    ap.add_argument('--revisao', type=Path)
    ap.add_argument('--pasta', type=Path)
    ap.add_argument('--particao', choices=list(FASES))
    ap.add_argument('--emitir', action='store_true')
    ap.add_argument('--retomar', action='store_true')
    args = ap.parse_args()
    if args.preparar_politica:
        exigir(not any((args.politica, args.revisao, args.pasta, args.particao, args.emitir, args.retomar)),
               'Preparar politica e uma operacao isolada.')
        preparar_politica(args.preparar_politica)
        return
    exigir(args.politica and args.pasta and args.particao, 'Informe politica, pasta e particao.')
    validar_politica(args.politica)
    exigir(not args.retomar or args.emitir, 'Retomada exige --emitir e revisao externa.')
    if args.emitir:
        validar_revisao(args.revisao, args.politica)
    aceite = args.pasta/f'aceite_controle_gpu_{args.particao}.json'
    if aceite.exists():
        exigir(args.emitir, 'Aceite ja existente; evidencias preservadas.')
        if args.retomar:
            retomar(args.pasta, args.particao, args.politica, args.revisao)
        else:
            print(f'Aceite existente preservado: {aceite}')
        return
    relatorio = avaliar(args.pasta, args.particao, args.politica)
    print(f'Verificacao pronta: {relatorio}', flush=True)
    if args.emitir:
        emitir(args.pasta, args.particao, args.politica, args.revisao, relatorio)
    if args.retomar:
        retomar(args.pasta, args.particao, args.politica, args.revisao)


if __name__ == '__main__':
    main()
