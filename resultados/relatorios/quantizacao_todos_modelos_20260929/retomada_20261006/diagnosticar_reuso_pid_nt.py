"""Investiga PID/FILETIME duplicados em snapshots NT somente leitura."""
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
from scripts import processos_quantizacao as p
from scripts import retomar_historico_apos_calendario as h
nt = ctypes.WinDLL('ntdll')
query = nt.NtQuerySystemInformation
query.argtypes = [w.ULONG,ctypes.c_void_p,w.ULONG,ctypes.POINTER(w.ULONG)]
query.restype = w.LONG
backend = h.Windows()
report = {'utc':datetime.now(timezone.utc).isoformat(), 'pid':os.getpid(), 'tentativas':[]}
for _ in range(100):
    buf = ctypes.create_string_buffer(4*1024*1024); returned = w.ULONG()
    status = int(query(5,buf,len(buf),ctypes.byref(returned))) & 0xffffffff
    row = {'status':status,'tamanho':int(returned.value),'duplicados':[]}
    if status == 0 and 0 < returned.value <= len(buf):
        offset = 0; by_pid = {}
        while offset + ctypes.sizeof(p.ProcessoSistemaPrefixo) <= returned.value:
            item = p.ProcessoSistemaPrefixo.from_buffer_copy(buf.raw,offset)
            pid = int(item.pid or 0)
            by_pid.setdefault(pid,[]).append({'pid':pid,'ppid':int(item.ppid or 0),
                                             'creation_time':str(item.creation_time)})
            if not item.next_offset: break
            if item.next_offset < ctypes.sizeof(item): break
            offset += item.next_offset
        row['count'] = sum(map(len,by_pid.values()))
        for pid, items in by_pid.items():
            if len(items) < 2: continue
            evidence = {'pid':pid,'instancias':items}
            try:
                actual = backend.identificar(pid)
                evidence['handle_vivo'] = h.asdict(actual) if actual else None
            except Exception as exc:
                evidence['handle_erro'] = f'{type(exc).__name__}: {exc}'
            row['duplicados'].append(evidence)
    report['tentativas'].append(row)
    time.sleep(0.1)
backend.fechar()
target = Path(__file__).with_name('diagnostico_reuso_pid_nt.json')
with target.open('x',encoding='utf-8') as stream: json.dump(report,stream,ensure_ascii=False,indent=2)
print(json.dumps({'amostras':len(report['tentativas']), 'duplicacoes':[row for row in report['tentativas'] if row['duplicados']],
                  'relatorio':str(target)},ensure_ascii=False))
