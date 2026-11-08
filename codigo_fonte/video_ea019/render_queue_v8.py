"""Run at most two approved, resumable Full HD chapter renders."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v8'
ORDER=['metodologia','resultados','quantizacao','interpretacao','metricas']

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(path,default=None):
    try:return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,json.JSONDecodeError):return default

def main():
    active={};finished=set();failed={}
    logs=OUT/'logs';logs.mkdir(parents=True,exist_ok=True)
    while len(finished)+len(failed)<len(ORDER):
        for name,(process,stream) in list(active.items()):
            code=process.poll()
            if code is None:continue
            stream.close();del active[name]
            record=read(OUT/'cenas'/f'{name}_manifesto_v8.json',{})
            if code==0 and record.get('render_complete'):
                finished.add(name);print('V8_RENDER_FINISHED '+name,flush=True)
            else:failed[name]={'returncode':code,'log':str(logs/f'render_{name}.log')}
        gates=read(OUT/'qa_aprovado_v8.json',{})
        if not failed:
            for name in ORDER:
                if len(active)>=2:break
                if name in active or name in finished:continue
                gate=gates.get(name,{})
                if not gate.get('approved'):continue
                if not gate.get('source_hashes'):raise RuntimeError('Manual source hashes missing for '+name)
                for file,digest in gate['source_hashes'].items():
                    if sha(ROOT/file)!=digest:raise RuntimeError('Approved source changed: '+file)
                stream=(logs/f'render_{name}.log').open('w',encoding='utf-8')
                command=[str(ROOT/'.tools/blender/blender-4.5.14-windows-x64/blender.exe'),
                  '--background','--threads','6','--python-exit-code','1','--python',str(ROOT/'codigo_fonte/video_ea019/director_v8.py'),
                  '--','--chapter',name,'--render','--percentage','100','--samples','16']
                process=subprocess.Popen(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                   creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                active[name]=(process,stream);print('V8_RENDER_STARTED '+name,flush=True)
        state={'running':list(active),'complete':sorted(finished),'failed':failed,'total_chapters':len(ORDER),'updated_unix':time.time()}
        tmp=OUT/'fila_render_v8.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n',encoding='utf-8')
        # Windows readers/antivirus can briefly deny replacement of an open
        # progress file. This must never terminate the rendering process tree.
        for attempt in range(100):
            try:
                os.replace(tmp,OUT/'fila_render_v8.json');break
            except PermissionError:
                time.sleep(.05)
        else:
            print('V8_PROGRESS_WRITE_DEFERRED',flush=True)
        if failed and not active:raise SystemExit('Render failed; see fila_render_v8.json')
        if len(finished)==len(ORDER):break
        time.sleep(5)
    print('V8_ALL_RENDERS_COMPLETE',flush=True)

if __name__=='__main__':main()
