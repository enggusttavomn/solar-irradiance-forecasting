"""Complemento operacional: reaproveita refit concluido e isola flags no replay.

O coordenador, os motores e o auditor originais permanecem intactos. Todos os
gates cientificos, inclusive replay completo, continuam no fluxo original.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import sys
from pathlib import Path

from scripts import coordenar_quantizacao_historica as original
from scripts.retomar_historico_apos_calendario import digest, ler, Bloqueio, local

RAIZ = Path(__file__).resolve().parents[1]
ID = 'coordenacao_historica_replay_isolado_v1'
REGIME = 'historico_1998_2022'


def conferir_recibo(path, sha):
    path = local(path)
    if digest(path) != sha:
        raise Bloqueio('Recibo operacional alterado.')
    r = ler(path)
    if r.get('aprovado') is not True or r.get('id') != ID:
        raise Bloqueio('Recibo operacional nao aprovado.')
    if local(r['parada']).exists():
        raise Bloqueio('Pedido de parada presente na retomada atual.')
    for p, esperado in r['fontes_sha256'].items():
        if digest(local(p)) != esperado:
            raise Bloqueio(f'Fonte operacional/cientifica alterada: {p}')
    if r['fontes_sha256'].get(str(Path(__file__).resolve())) != digest(__file__):
        raise Bloqueio('Coordenador complementar nao vinculado ao recibo.')
    return r


def conferir_refit_concluido(recibo):
    from scripts.rodar_quantizacao_todos_modelos import TAREFAS, MODELOS
    path = local(recibo['runner_concluido']['path'])
    if digest(path) != recibo['runner_concluido']['sha256']:
        raise Bloqueio('Runner concluido mudou antes de seu reaproveitamento.')
    r = ler(path)
    esperado = {(t, m) for t in TAREFAS for m in MODELOS}
    jobs = r.get('concluidos', [])
    if (r.get('regime') != REGIME or r.get('etapa') != 'concluida'
            or r.get('falhas') or r.get('processos') or r.get('pendentes')
            or len(jobs) != 44
            or {(j.get('tarefa'), j.get('modelo')) for j in jobs} != esperado
            or any(j.get('fase') != 'refit' or j.get('returncode') != 0 for j in jobs)):
        raise Bloqueio('Os 44 refits completos sem falhas sao obrigatorios.')
    for tarefa, modelo in esperado:
        p = original.SAIDA / REGIME / tarefa / modelo.lower().replace(' ', '_')
        s = ler(p / 'status.json')
        if s.get('etapa') != 'concluida' or s.get('modo') != 'completa':
            raise Bloqueio(f'Refit incompleto: {tarefa}/{modelo}')
    return r


@contextmanager
def complemento(recibo, recibo_path, recibo_sha):
    classe = original.ExecutadorCoordenacao

    class ExecutadorIsolado(classe):
        def __init__(self, raiz, rel, status):
            status['coordenador_complementar'] = {
                'id': ID, 'arquivo': str(Path(__file__).resolve()),
                'sha256': digest(__file__), 'recibo': str(recibo_path),
                'recibo_sha256': recibo_sha,
            }
            super().__init__(raiz, rel, status)

        def executar(self, cmd, nome, exigir_sucesso=True):
            conferir_recibo(recibo_path, recibo_sha)
            if nome == 'fila_' + REGIME:
                conferir_refit_concluido(recibo)
                self.status.setdefault('eventos', []).append({
                    'etapa': nome, 'retorno': 0, 'fim_utc': original.agora(),
                    'refits_concluidos_reaproveitados': 44,
                    'runner_sha256': recibo['runner_concluido']['sha256'],
                })
                self.registrar(nome + '_concluida', processo_filho=None,
                               refits_concluidos_reaproveitados=44)
                return 0
            cmd = list(cmd)
            if nome in {'auditoria_' + r for r in original.REGIMES}:
                idx = cmd.index('-m') + 1
                if cmd[idx] != 'scripts.auditar_quantizacao_todos_modelos' or '--replay' not in cmd:
                    raise Bloqueio('Comando de auditoria completo inesperado.')
                cmd[idx] = 'scripts.auditar_quantizacao_replay_isolado_v1'
            return super().executar(cmd, nome, exigir_sucesso)

    original.ExecutadorCoordenacao = ExecutadorIsolado
    try:
        yield
    finally:
        original.ExecutadorCoordenacao = classe


def main():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--recibo', type=Path, required=True)
    ap.add_argument('--recibo-sha256', required=True)
    args, restante = ap.parse_known_args()
    if restante != ['--cpu-workers', '2', '--gpu-workers', '2']:
        raise Bloqueio('Somente a fila local 2 CPU / 2 GPU esta autorizada.')
    r = conferir_recibo(args.recibo, args.recibo_sha256)
    conferir_refit_concluido(r)
    argv = sys.argv
    try:
        sys.argv = [argv[0], *restante]
        with complemento(r, args.recibo.resolve(), args.recibo_sha256):
            original.main()
    finally:
        sys.argv = argv


if __name__ == '__main__':
    main()
