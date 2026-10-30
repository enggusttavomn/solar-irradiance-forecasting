"""Gravacao JSON duravel; bloqueios Windows tem retry limitado a cerca de 60 s."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import sys
import time


def salvar_json(dados, path, *, tentativas=240, intervalo=0.25):
    if not isinstance(tentativas, int) or isinstance(tentativas, bool) or tentativas < 1:
        raise ValueError('tentativas deve ser um inteiro positivo.')
    if intervalo < 0:
        raise ValueError('intervalo deve ser nao negativo.')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix=path.name + '.', suffix='.tmp', dir=path.parent)
    tmp = Path(nome)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(dados, stream, ensure_ascii=False, indent=2)
            # Sincronizar o temporario antes da troca reduz o risco apos uma
            # interrupcao; nao garante toda durabilidade contra energia/disco.
            stream.flush()
            os.fsync(stream.fileno())
        for tentativa in range(tentativas):
            try:
                tmp.replace(path)
                return
            except PermissionError as exc:
                # O Windows tambem pode retornar ERROR_ACCESS_DENIED durante
                # uma troca bloqueada brevemente. A repeticao e limitada; uma
                # negacao persistente continua falhando sem mudar permissoes.
                if getattr(exc, 'winerror', None) not in (5, 32, 33) or tentativa + 1 == tentativas:
                    raise
                time.sleep(intervalo)
    finally:
        erro_original = sys.exc_info()[0] is not None
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            if not erro_original:
                raise
