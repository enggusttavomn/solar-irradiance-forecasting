"""Confere que resultados anteriores permanecem iguais ao snapshot do estudo."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from codigo_fonte.utilitarios.json_atomico import salvar_json

RAIZ = Path(__file__).resolve().parents[2]
REL = RAIZ / 'resultados/relatorios/quantizacao_todos_modelos_20260929'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--relatorio', type=Path, required=True)
    args = ap.parse_args()
    path = REL / 'snapshot_anteriores.json'
    snapshot = json.loads(path.read_text(encoding='utf-8'))
    falhas, verificados = [], 0
    for nome, digest in snapshot['arquivos'].items():
        fonte = Path(nome)
        atual = sha(fonte) if fonte.is_file() else None
        if atual != digest:
            falhas.append({'arquivo': nome, 'sha256_esperado': digest, 'sha256_atual': atual})
        verificados += 1
        if verificados % 200 == 0:
            print(f'Preservacao: {verificados}/{len(snapshot["arquivos"])}', flush=True)
    resultado = {'ok': not falhas, 'arquivos_verificados': verificados, 'falhas': falhas,
                 'snapshot_sha256': sha(path), 'codigo_sha256': sha(__file__),
                 'verificado_em_utc': datetime.now(timezone.utc).isoformat(),
                 'nota': 'Leitura logica autorizada pelo Python; nenhuma remocao de protecao documental.'}
    salvar_json(resultado, args.relatorio)
    print(json.dumps({'ok': resultado['ok'], 'arquivos': verificados, 'falhas': len(falhas)}), flush=True)
    if falhas:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
