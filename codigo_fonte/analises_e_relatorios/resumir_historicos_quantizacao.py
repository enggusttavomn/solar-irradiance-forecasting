"""Resume o efeito observado do historico nas mesmas amostras de teste."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from codigo_fonte.analises_e_relatorios.gerar_pdf_quantizacao_todos_modelos import carregar_auditoria, ROTULOS
from codigo_fonte.acompanhamento.metricas_quantizacao_todos import MODELOS, TAREFAS, sha256


def resumir(longo_path, curto_path, pareamento_path, destino):
    longo_a, longo = carregar_auditoria(longo_path)
    curto_a, curto = carregar_auditoria(curto_path)
    par = json.loads(pareamento_path.read_text(encoding='utf-8'))
    if longo_a['regime'] != 'historico_1998_2022' or curto_a['regime'] != 'historico_curto_pareado':
        raise ValueError('Regimes invertidos ou incorretos.')
    pares_esperados = {(t, m) for t in TAREFAS for m in MODELOS}
    for auditoria in (longo_a, curto_a):
        registros = auditoria.get('resultados', [])
        pares = [(r.get('tarefa'), r.get('modelo')) for r in registros]
        if (len(pares) != len(pares_esperados) or set(pares) != pares_esperados
                or not all(r.get('ok') is True for r in registros)):
            raise ValueError('Auditoria sem os 44 pares aprovados e unicos.')
    if not (par.get('ok') is True and par.get('publicavel') is True and len(par.get('resultados', [])) == 8):
        raise ValueError('Pareamento completo nao aprovado.')
    particoes_esperadas = {(t, p) for t in TAREFAS for p in ('validacao', 'teste')}
    if ({(r.get('tarefa'), r.get('particao')) for r in par['resultados']} != particoes_esperadas
            or not all(r.get('observacoes_e_datas_iguais') is True for r in par['resultados'])):
        raise ValueError('Pareamento sem todas as tarefas e particoes identicas.')
    for arquivo, digest in par['fontes_sha256'].items():
        if sha256(Path(arquivo)) != digest:
            raise ValueError(f'Fonte alterada: {arquivo}')
    for path in (longo_path, curto_path):
        if par['fontes_sha256'].get(str(path.resolve())) != sha256(path):
            raise ValueError('Pareamento de outra auditoria.')

    def controle(frame):
        recorte = frame[(frame.particao == 'teste') & (frame.variante == 'sem_quantizacao')]
        return recorte[recorte.apply(lambda r: r.horizonte == max(TAREFAS[r.tarefa]), axis=1)]

    juntos = controle(curto).merge(controle(longo), on=['tarefa', 'modelo', 'horizonte'],
                                   suffixes=('_curto', '_longo'), validate='one_to_one')
    if len(juntos) != 44 or set(juntos[['tarefa', 'modelo']].itertuples(index=False, name=None)) != pares_esperados:
        raise ValueError('Faltam comparacoes de controle.')
    for campo in ('N_localidades', 'N_origens', 'N_pontos'):
        if not (juntos[campo + '_curto'] == juntos[campo + '_longo']).all():
            raise ValueError('Amostras de tamanhos diferentes.')
    juntos['delta'] = juntos.MAE_wm2_longo - juntos.MAE_wm2_curto
    melhoraram = int((juntos.delta < -1e-7).sum())
    pioraram = int((juntos.delta > 1e-7).sum())
    iguais = len(juntos) - melhoraram - pioraram
    texto = [
        '# Comparacao dos historicos nas mesmas datas', '',
        '> Thales, concluí também os testes com o histórico de 1998–2022 e as tabelas por nível estão no PDF histórico. '
        'Comparei com um histórico mais curto, começando em abril de 2014, usando as mesmas datas de validação e teste.',
        '>',
        f'> Nos controles sem quantização, o histórico longo teve menor MAE em {melhoraram} das 44 combinações de modelo e caso, '
        f'maior em {pioraram} e diferença praticamente nula em {iguais}. Essa comparação ajuda a avaliar o efeito do histórico, '
        'mas não demonstra que a causa seja variação climática nem reproduz integralmente o estudo do Luís.', '',
        'Contagens descritivas no horizonte completo de cada caso; sem teste de significância. '
        'Empate numérico: diferença absoluta de MAE até 0,0000001 W/m². '
        'Os níveis de quantização permanecem detalhados no PDF.', '',
        '| Caso | Modelo | MAE curto | MAE longo | Diferença W/m² |',
        '|---|---|---:|---:|---:|',
    ]
    for r in juntos.sort_values(['tarefa', 'modelo']).itertuples():
        valores = [f'{v:.4f}'.replace('.', ',') for v in (r.MAE_wm2_curto, r.MAE_wm2_longo, r.delta)]
        texto.append(f'| {ROTULOS[r.tarefa]} | {r.modelo} | ' + ' | '.join(valores) + ' |')
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('\n'.join(texto) + '\n', encoding='utf-8')
    destino.with_suffix('.json').write_text(json.dumps({
        'controle_sem_quantizacao': True, 'pares': 44,
        'menor_MAE_longo': melhoraram, 'maior_MAE_longo': pioraram, 'empates_numericos': iguais,
        'tolerancia_empate_wm2': 1e-7,
        'fontes_sha256': {str(p.resolve()): sha256(p) for p in (longo_path, curto_path, pareamento_path)},
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print(destino, flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--longo', type=Path, required=True)
    ap.add_argument('--curto', type=Path, required=True)
    ap.add_argument('--pareamento', type=Path, required=True)
    ap.add_argument('--saida', type=Path, required=True)
    args = ap.parse_args()
    resumir(args.longo, args.curto, args.pareamento, args.saida)
