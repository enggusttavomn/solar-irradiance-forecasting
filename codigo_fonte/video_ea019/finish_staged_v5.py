"""Wait for both staged V5 render jobs and assemble the verified delivery."""
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v5'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def main():
    print('WAITING_FOR_STAGED_V5_RENDERS',flush=True)
    for name in ('progresso_render_v5.json','progresso_fabrica_v5.json'):
        while True:
            data=read(OUT/name)
            if data.get('stage')=='error':raise RuntimeError(data.get('error',name))
            if data.get('stage')=='staged':break
            time.sleep(3)
    factory=read(OUT/'manifesto_parcial_2.json')
    diagrams=read(OUT/'manifesto_parcial_3_4_5_6_7_8_9_10_11_12_13.json')
    plan=read(OUT/'plano_video_v5.json')
    chapters=sorted(factory['chapters']+diagrams['chapters'],key=lambda c:c['id'])
    assert [c['id'] for c in chapters]==list(range(2,14))
    assert sum(c['frame_count'] for c in chapters)==12450
    for c in chapters:
        assert c['rendered'] and c['raw_verification']['full_decode_errors']==0
        assert Path(c['raw_mp4']).is_file()
        c['label_events']=next(p['label_events'] for p in plan['chapters'] if p['id']==c['id'])
    manifest={**factory,'chapters':chapters,'all_prepared':True,'full_rendered':True,
      'rendering_strategy':'EEVEE shaded physical factory; matte Workbench diagrams'}
    (OUT/'manifesto_producao_v5.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    jobs=[('render_complete_v5.py',[]),('qa_v5.py',['--final']),
          ('delivery_v5.py',[]),('verify_delivery_v5.py',[])]
    for filename,args in jobs:
        print('RUNNING '+filename,flush=True)
        subprocess.run([sys.executable,str(Path(__file__).resolve().parent/filename),*args],
          cwd=ROOT,check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    print('V5_DELIVERY_READY_FOR_VISUAL_REVIEW',flush=True)

if __name__=='__main__':main()
