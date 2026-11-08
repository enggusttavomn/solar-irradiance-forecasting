"""Record a manual chapter review and its exact production source hashes."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v8'
MODULES={'metodologia':'methodology_v8','quantizacao':'quantization_v8','metricas':'metrics_v8','resultados':'results_v8','interpretacao':'interpretation_v8'}

def main():
    p=argparse.ArgumentParser();p.add_argument('chapters',choices=MODULES,nargs='+');args=p.parse_args()
    path=OUT/'qa_aprovado_v8.json'
    data=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    for chapter in args.chapters:
        paths=[ROOT/f'codigo_fonte/video_ea019/{MODULES[chapter]}.py',ROOT/'codigo_fonte/video_ea019/director_v8.py',
          ROOT/'codigo_fonte/video_ea019/common_v7.py',ROOT/'codigo_fonte/video_ea019/blender_pilot.py',
          ROOT/'codigo_fonte/video_ea019/factory_site_v6.py',OUT/'fontes_resultados_v8.json']
        hashes={}
        for source in paths:
            with source.open('rb') as f:hashes[str(source.relative_to(ROOT)).replace('\\','/')]=hashlib.file_digest(f,'sha256').hexdigest()
        data[chapter]={'approved':True,'automatically_approved':False,'reviewed_utc':datetime.now(timezone.utc).isoformat(),
          'scope':'Root manual visual sampled preflight plus independent scientific review','source_hashes':hashes}
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,path)
    print('V8_MANUAL_REVIEWS_RECORDED '+','.join(args.chapters),flush=True)

if __name__=='__main__':main()
