"""Run approved Intel Arc jobs, preserving completed blocks on restart."""
import subprocess,time
from pipeline_v9 import *
from compose_pilot import probe_and_decode,DEFAULT_FFMPEG
ORDER=['metricas','quantizacao','entradas_tarefas','geografia','metodologia','introducao','conclusao','modelos']
def reuse_results():
    source=ROOT/'documentacao/relatorio_final_ea019/video/completo_v8/cenas/resultados_manifesto_v8.json'
    r=read(source);r.update(CHAPTERS['resultados'])
    r.update(version=9,chapter='resultados',approved_v8_results_reused=True,raw_mp4=str(RESULTS_SOURCE),
      render_complete=True,resolution_percentage=100)
    r['raw_verification']=probe_and_decode(DEFAULT_FFMPEG,RESULTS_SOURCE,88,2640)
    write_json(OUT/'cenas/resultados_manifesto_v9.json',r)
def main():
    OUT.mkdir(parents=True,exist_ok=True);logs=OUT/'logs';logs.mkdir(exist_ok=True)
    reuse_results();active={};done={'resultados'};failed={}
    for name in ORDER:
        r=read(OUT/'cenas'/f'{name}_manifesto_v9.json',{})
        if r.get('render_complete'):
            key,values=current_sources(CHAPTERS[name]['module'])
            if r.get('source_fingerprint')==key and Path(r['raw_mp4']).exists() and sha(r['raw_mp4'])==r['raw_verification']['sha256']:
                done.add(name)
    while True:
        for name,(job,stream) in list(active.items()):
            code=job.poll()
            if code is None:continue
            stream.close();del active[name]
            r=read(OUT/'cenas'/f'{name}_manifesto_v9.json',{})
            if code==0 and r.get('render_complete'):
                done.add(name);print('V9_RENDER_COMPLETE '+name,flush=True)
            else:failed[name]={'returncode':code,'log':str(logs/f'{name}.log')}
        limit=read(OUT/'controle_fila_v9.json',{'workers':2}).get('workers',2)
        gates=read(OUT/'qa_aprovado_v9.json',{})
        if not failed:
            for name in ORDER:
                if len(active)>=limit:break
                if name in done or name in active:continue
                gate=gates.get(name,{})
                if not gate.get('approved'):continue
                key,values=current_sources(CHAPTERS[name]['module'])
                if gate.get('source_hashes')!=values:
                    failed[name]={'error':'Approved source changed'};break
                stream=(logs/f'{name}.log').open('w',encoding='utf-8')
                cmd=[str(BLENDER),'--background','--threads','6','--python-exit-code','1','--python',
                     str(ROOT/'codigo_fonte/video_ea019/director_v9.py'),'--','--chapter',name,'--render','--percentage','100']
                job=subprocess.Popen(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                active[name]=(job,stream);print('V9_RENDER_STARTED '+name,flush=True)
        write_json(OUT/'fila_render_v9.json',{'running':list(active),'complete':sorted(done),'failed':failed,
                   'total_chapters':9,'updated_unix':time.time()})
        if len(done)==9:break
        if failed and not active:raise SystemExit('V9_RENDER_FAILED')
        time.sleep(5)
    print('V9_ALL_RENDERED',flush=True)
if __name__=='__main__':main()
