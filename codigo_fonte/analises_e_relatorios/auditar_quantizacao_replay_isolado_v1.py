"""Auditoria historica com estado cuDNN restaurado depois de cada replay.

A CLI e a auditoria cientifica sao as do auditor congelado. Este wrapper
preserva apenas benchmark/deterministic entre replays: nao configura flags
antes da chamada, nao altera contratos e nao substitui nenhum gate original.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from functools import wraps
import hashlib
import importlib
import json
from pathlib import Path
import sys

from codigo_fonte.utilitarios.migracao import verificar_fonte_historica

RAIZ = Path(__file__).resolve().parents[2]
ID = 'auditoria_replay_isolado_v1'
REGIMES = ('historico_1998_2022', 'historico_curto_pareado')
FONTE_ORIGINAL = 'scripts/auditar_quantizacao_todos_modelos.py'
FONTE_ATIVA = RAIZ / 'codigo_fonte/analises_e_relatorios/auditar_quantizacao_todos_modelos.py'
REGISTRO_MIGRACAO = RAIZ / 'documentacao/organizacao/reorganizacao_codigo_20261027.json'
SHA_ORIGINAL = '2a8a1e9c5f014dcd554494bf798dc60c55c4eeecbd9fd80700dfe39cc1595c43'
_ativo = False


def conferir_fonte(path, esperado):
    """Confere a fonte congelada no arquivo histórico, sem substituir seu hash."""
    try:
        verificar_fonte_historica(path, esperado)
    except (ValueError, OSError, KeyError) as erro:
        raise RuntimeError('Fonte do auditor original divergiu do SHA256 congelado.') from erro


def conferir_fonte_ativa():
    """Confere separadamente a implementação reorganizada e registrada."""
    registro = json.loads(REGISTRO_MIGRACAO.read_text(encoding='utf-8'))
    relativo = FONTE_ATIVA.resolve().relative_to(RAIZ.resolve()).as_posix()
    esperado = registro.get('fontes_depois', {}).get(relativo)
    if not esperado:
        raise RuntimeError('Fonte do auditor ativo ausente no registro da reorganizacao.')
    h = hashlib.sha256()
    with FONTE_ATIVA.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    if h.hexdigest() != esperado:
        raise RuntimeError('Fonte do auditor ativo divergiu do SHA256 registrado.')


def carregar_auditor():
    conferir_fonte(FONTE_ORIGINAL, SHA_ORIGINAL)
    conferir_fonte_ativa()
    auditor = importlib.import_module('codigo_fonte.analises_e_relatorios.auditar_quantizacao_todos_modelos')
    if Path(auditor.__file__).resolve() != FONTE_ATIVA.resolve():
        raise RuntimeError('Modulo do auditor original veio de outro caminho.')
    conferir_fonte(FONTE_ORIGINAL, SHA_ORIGINAL)
    conferir_fonte_ativa()
    return auditor


def validar_regime(argv):
    # O parser completo e os demais argumentos continuam no auditor original.
    if '--help' in argv or '-h' in argv:
        return False
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--regime', default='atual')
    args, _ = parser.parse_known_args(argv)
    if args.regime not in REGIMES:
        raise ValueError('Wrapper v1 restrito aos dois regimes historicos.')
    return True


@contextmanager
def ativar_isolamento(auditor, cudnn):
    """Delega cada replay inteiro e restaura somente as duas flags ao sair."""
    global _ativo
    if _ativo:
        raise RuntimeError('Isolamento de replay ja ativo; contextos aninhados proibidos.')
    original = auditor.replay_aprendido
    if not callable(original):
        raise RuntimeError('Replay original ausente ou invalido.')

    @wraps(original)
    def replay_isolado(*args, **kwargs):
        benchmark, deterministic = cudnn.benchmark, cudnn.deterministic
        try:
            return original(*args, **kwargs)
        finally:
            # Tenta restaurar ambas mesmo se a primeira restauracao falhar.
            try:
                cudnn.benchmark = benchmark
            finally:
                cudnn.deterministic = deterministic

    _ativo = True
    try:
        auditor.replay_aprendido = replay_isolado
        yield
    finally:
        auditor.replay_aprendido = original
        _ativo = False


def main():
    executar = validar_regime(sys.argv[1:])
    auditor = carregar_auditor()
    if not executar:
        auditor.main()
        return
    torch = importlib.import_module('torch')
    with ativar_isolamento(auditor, torch.backends.cudnn):
        auditor.main()


if __name__ == '__main__':
    main()
