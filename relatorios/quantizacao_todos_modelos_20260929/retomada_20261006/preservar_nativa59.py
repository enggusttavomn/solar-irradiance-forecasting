"""Preserva fontes e provas da primeira validacao NT mediante copia exclusiva."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ARCHIVE = OUT / 'nativa59_anterior'
ARCHIVE.mkdir(exist_ok=False)
rows = []
for rel in ('scripts/retomar_historico_apos_calendario.py','tests/test_retomar_historico_apos_calendario.py',
            str((OUT/'testes_snapshot_nt.json').relative_to(ROOT)),
            str((OUT/'testes_snapshot_nt.log').relative_to(ROOT)),
            str((OUT/'revisao_reparo_snapshot_nt.json').relative_to(ROOT))):
    source = ROOT / rel; stat = source.stat(); raw = source.read_bytes()
    target = ARCHIVE / source.name
    with target.open('xb') as stream:
        stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    assert target.read_bytes() == source.read_bytes() == raw
    assert source.stat().st_mtime_ns == stat.st_mtime_ns
    rows.append({'origem':str(source),'copia':str(target),'sha256':hashlib.sha256(raw).hexdigest(),
                 'mtime_ns_original':stat.st_mtime_ns})
receipt = {'versao':1,'preservado_em_utc':datetime.now(timezone.utc).isoformat(),'arquivos':rows,
           'escopo':'Copias exclusivas; fontes e evidencias originais ainda nao alteradas.'}
with (ARCHIVE/'preservacao.json').open('x',encoding='utf-8') as stream: json.dump(receipt,stream,ensure_ascii=False,indent=2)
print(json.dumps(receipt,ensure_ascii=False))
