"""Reaproveita a auditoria longa completa e continua a fila curta apos reboot."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from pathlib import Path
import sys

from scripts import coordenar_quantizacao_historica_replay_isolado_v1 as anterior
from scripts.coordenacao_quantizacao import auditoria_publicavel
from scripts.retomar_historico_apos_calendario import digest, ler, local, Bloqueio

RAIZ = Path(__file__).resolve().parents[1]
ID = 'retomada_historico_apos_reinicio_v1'


def conferir_recibo(path, sha):
    path = local(path)
    if digest(path) != sha:
        raise Bloqueio('Recibo de reinicio alterado.')
    r = ler(path)
    if r.get('aprovado') is not True or r.get('id') != ID:
        raise Bloqueio('Recibo de reinicio nao aprovado.')
    if local(r['parada']).exists():
        raise Bloqueio('Pedido de parada vigente.')
    for p, esperado in r['fontes_sha256'].items():
        if digest(local(p)) != esperado:
            raise Bloqueio(f'Fonte do reinicio alterada: {p}')
    if r['fontes_sha256'].get(str(Path(__file__).resolve())) != digest(__file__):
        raise Bloqueio('Coordenador de reinicio nao vinculado.')
    anterior.conferir_recibo(local(r['recibo_anterior']['path']), r['recibo_anterior']['sha256'])
    return r


def conferir_auditoria_longa(r):
    from scripts.rodar_quantizacao_todos_modelos import TAREFAS, MODELOS
    item = r['auditoria_longa']
    path = local(item['path'])
    if digest(path) != item['sha256']:
        raise Bloqueio('Auditoria longa mudou apos o aceite.')
    a = ler(path)
    esperado = {(t, m) for t in TAREFAS for m in MODELOS}
    resultados = a.get('resultados', [])
    if (not auditoria_publicavel(a, anterior.REGIME) or len(resultados) != 44
            or {(x.get('tarefa'), x.get('modelo')) for x in resultados} != esperado
            or any(x.get('ok') is not True or not x.get('replays') for x in resultados)
            or a.get('codigo_auditor_sha256') != digest(RAIZ / 'scripts/auditar_quantizacao_todos_modelos.py')):
        raise Bloqueio('Auditoria longa integral com replay obrigatoria.')
    if digest(local(a['metricas']['path'])) != a['metricas']['sha256']:
        raise Bloqueio('Metricas longas auditadas foram alteradas.')
    for resultado in resultados:
        pasta = anterior.original.SAIDA / anterior.REGIME / resultado['tarefa'] / resultado['modelo'].lower().replace(' ', '_')
        if digest(pasta / 'selecao_congelada.json') != resultado['selecao_sha256']:
            raise Bloqueio('Selecao longa diferente da auditada.')
        for replay in resultado['replays']:
            if (replay.get('alvos_substituidos_por_nan') is not True
                    or not 0 <= replay.get('diferenca_maxima', float('inf')) <= 1e-6):
                raise Bloqueio('Replay longo nao aprovado.')
            if 'checkpoint' in replay and digest(local(replay['checkpoint'])) != replay['sha256']:
                raise Bloqueio('Checkpoint longo diferente do replay aprovado.')
    for p, sha in a.get('fontes_controles_suplementares_sha256', {}).items():
        if digest(local(p)) != sha:
            raise Bloqueio('Fonte suplementar da auditoria longa alterada.')
    return a


@contextmanager
def complemento(r, path, sha):
    oldpath = local(r['recibo_anterior']['path'])
    oldsha = r['recibo_anterior']['sha256']
    old = anterior.conferir_recibo(oldpath, oldsha)
    with anterior.complemento(old, oldpath, oldsha):
        classe = anterior.original.ExecutadorCoordenacao

        class ExecutadorReinicio(classe):
            def __init__(self, raiz, rel, status):
                status['retomada_apos_reinicio'] = {
                    'id': ID, 'arquivo': str(Path(__file__).resolve()),
                    'sha256': digest(__file__), 'recibo': str(path), 'recibo_sha256': sha,
                    'coordenador_anterior': r['coordenador_anterior'],
                }
                super().__init__(raiz, rel, status)

            def executar(self, cmd, nome, exigir_sucesso=True):
                conferir_recibo(path, sha)
                if nome == 'auditoria_' + anterior.REGIME:
                    conferir_auditoria_longa(r)
                    self.status.setdefault('eventos', []).append({
                        'etapa': nome, 'retorno': 0, 'fim_utc': anterior.original.agora(),
                        'auditoria_completa_reaproveitada': True,
                        'auditoria_sha256': r['auditoria_longa']['sha256'],
                    })
                    self.registrar(nome + '_concluida', processo_filho=None,
                        auditoria_longa_reaproveitada=True)
                    return 0
                return super().executar(cmd, nome, exigir_sucesso)

        anterior.original.ExecutadorCoordenacao = ExecutadorReinicio
        try:
            yield
        finally:
            anterior.original.ExecutadorCoordenacao = classe


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--recibo-reinicio', type=Path, required=True)
    ap.add_argument('--recibo-reinicio-sha256', required=True)
    args, restante = ap.parse_known_args()
    if restante != ['--cpu-workers', '2', '--gpu-workers', '2']:
        raise Bloqueio('Workers locais devem permanecer 2 CPU / 2 GPU.')
    r = conferir_recibo(args.recibo_reinicio, args.recibo_reinicio_sha256)
    conferir_auditoria_longa(r)
    argv = sys.argv
    try:
        sys.argv = [argv[0], *restante]
        with complemento(r, args.recibo_reinicio.resolve(), args.recibo_reinicio_sha256):
            anterior.original.main()
    finally:
        sys.argv = argv


if __name__ == '__main__':
    main()
