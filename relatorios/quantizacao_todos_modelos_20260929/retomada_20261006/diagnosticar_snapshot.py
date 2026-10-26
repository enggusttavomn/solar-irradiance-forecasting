"""Compara snapshots nativos somente leitura, sem criar/encerrar treinamentos."""
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
from scripts import retomar_historico_apos_calendario as h
from scripts import processos_quantizacao as p

backend = h.Windows()
entrada = h.Windows.Entrada
report = {'utc':datetime.now(timezone.utc).isoformat(), 'pid':os.getpid(), 'ppid':os.getppid(),
          'pointer_size':ctypes.sizeof(ctypes.c_void_p), 'entrada_size':ctypes.sizeof(entrada),
          'entrada_offsets':{name:getattr(entrada,name).offset for name,_ in entrada._fields_},
          'tentativas':[], 'escopo':'Somente consultas nativas. Nenhum treinamento iniciado, interrompido ou alterado.'}
for _ in range(30):
    attempt = {'utc':datetime.now(timezone.utc).isoformat()}
    try:
        toolhelp = backend.mapa()
        attempt.update(toolhelp_count=len(toolhelp), toolhelp_proprio=toolhelp.get(os.getpid()))
    except Exception as exc:
        attempt['toolhelp_erro'] = f'{type(exc).__name__}: {exc}'
        snapshot = backend.k.CreateToolhelp32Snapshot(2,0)
        if snapshot != ctypes.c_void_p(-1).value:
            try:
                record = entrada(); record.size = ctypes.sizeof(record)
                trace = []
                ok = backend.k.Process32FirstW(snapshot,ctypes.byref(record))
                seen = set()
                for step in range(4096):
                    if not ok: break
                    row = {'step':step, 'ok':int(ok),'size':int(record.size), 'pid':int(record.pid),
                           'ppid':int(record.ppid), 'exe':record.exe, 'repeated':int(record.pid) in seen}
                    trace.append(row)
                    if row['repeated']: break
                    seen.add(row['pid'])
                    ok = backend.k.Process32NextW(snapshot,ctypes.byref(record))
                attempt['toolhelp_trace'] = trace
                attempt['toolhelp_final_error'] = ctypes.get_last_error()
            finally: backend.k.CloseHandle(snapshot)
    try:
        native = p.snapshot_identidades_windows()
        attempt.update(nt_count=len(native), nt_proprio=native.get(os.getpid()))
    except Exception as exc:
        attempt['nt_erro'] = f'{type(exc).__name__}: {exc}'
    report['tentativas'].append(attempt)
    time.sleep(0.1)
backend.fechar()
out = Path(__file__).with_name('diagnostico_snapshot_original.json')
with out.open('x',encoding='utf-8') as stream:
    json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps(report,ensure_ascii=False))
