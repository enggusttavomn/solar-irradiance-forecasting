"""Keep at most two production renders active, then release geography."""
import json
from pathlib import Path
import subprocess
import time
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
source=OUT/'cenas/entradas_tarefas_manifesto_v7.json'
while True:
    try:ready=json.loads(source.read_text(encoding='utf-8')).get('render_complete',False)
    except (OSError,json.JSONDecodeError):ready=False
    if ready:break
    time.sleep(5)
with (ROOT/'tmp/render_geografia_v7.log').open('w',encoding='utf-8') as log:
    result=subprocess.run([str(ROOT/'.tools/blender/blender-4.5.14-windows-x64/blender.exe'),
       '--background','--threads','6','--python',str(ROOT/'codigo_fonte/video_ea019/director_v7.py'),
       '--','--chapter','geografia','--render','--percentage','100','--samples','16'],
       cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
if result.returncode:raise SystemExit(result.returncode)
print('V7_GEOGRAPHY_RENDER_COMPLETE',flush=True)
