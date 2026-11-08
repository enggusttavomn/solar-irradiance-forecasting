"""Render the remaining film in resumable ten-second Full HD blocks."""
import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from common_v7 import ROOT,setup,frame
from compose_pilot import DEFAULT_FFMPEG,command,probe_and_decode

OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v8'
MODULES={
 'metodologia':('methodology_v8',62,224),
 'quantizacao':('quantization_v8',54,286),
 'metricas':('metrics_v8',48,340),
 'resultados':('results_v8',88,388),
 'interpretacao':('interpretation_v8',74,476),
}

def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def fingerprint(module,samples=16):
    paths=[Path(__file__).resolve(),ROOT/f'codigo_fonte/video_ea019/{module}.py',
      ROOT/'codigo_fonte/video_ea019/common_v7.py',ROOT/'codigo_fonte/video_ea019/blender_pilot.py',
      ROOT/'codigo_fonte/video_ea019/factory_site_v6.py',OUT/'fontes_resultados_v8.json']
    values={str(p.relative_to(ROOT)):digest(p) for p in paths if p.is_file()}
    key=hashlib.sha256(json.dumps({'sources':values,'samples':samples,'resolution':[1920,1080],'fps':30},sort_keys=True).encode()).hexdigest()
    return key,values

def write_json(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(tmp,path)

def main():
    p=argparse.ArgumentParser();p.add_argument('--chapter',choices=MODULES,required=True)
    p.add_argument('--qa',action='store_true');p.add_argument('--qa-times',type=float,nargs='*')
    p.add_argument('--render',action='store_true');p.add_argument('--percentage',type=int,default=100)
    p.add_argument('--samples',type=int,default=16)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    if args.render and args.percentage!=100:raise ValueError('Production render requires Full HD')
    module,duration,start=MODULES[args.chapter]
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'cenas').mkdir(exist_ok=True);(OUT/'qa_3d').mkdir(exist_ok=True)
    scene=setup(duration,args.samples,args.percentage)
    info=importlib.import_module(module).build(scene)
    if info.get('duration')!=duration:raise ValueError('Chapter duration mismatch')
    scene.name='V8 '+args.chapter
    scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=args.percentage
    scene.render.fps=30;scene.frame_start=1;scene.frame_end=duration*30
    scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4'
    scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
    scene.render.ffmpeg.ffmpeg_preset='REALTIME';scene.render.ffmpeg.audio_codec='NONE'
    raw=OUT/'cenas'/f'{args.chapter}_3d_v8.mp4';scene.render.filepath=str(raw)
    scene.frame_set(1);bpy.context.preferences.filepaths.save_version=0
    blend=OUT/'cenas'/f'{args.chapter}_v8.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    key,sources=fingerprint(module,args.samples)
    record={**info,'version':8,'chapter':args.chapter,'start':start,'end':start+duration,
      'blend':str(blend),'raw_mp4':str(raw),'fps':30,'frames':duration*30,'resolution':[1920,1080],
      'resolution_percentage':args.percentage,'samples':args.samples,'render_complete':False,
      'source_fingerprint':key,'source_hashes':sources,'blocks':[]}
    manifest=OUT/'cenas'/f'{args.chapter}_manifesto_v8.json';write_json(manifest,record)
    if args.qa:
        scene.render.image_settings.file_format='PNG'
        for t in args.qa_times or info['qa_times']:
            scene.frame_set(frame(t));scene.render.filepath=str(OUT/'qa_3d'/f'{args.chapter}_{str(t).replace(".","_")}.png')
            bpy.ops.render.render(write_still=True)
        scene.render.image_settings.file_format='FFMPEG';scene.render.filepath=str(raw)
    if args.render:
        blockdir=OUT/'cenas/blocos'/args.chapter;blockdir.mkdir(parents=True,exist_ok=True)
        for first in range(1,duration*30+1,300):
            last=min(first+299,duration*30)
            target=blockdir/f'f{first:05d}_{last:05d}.mp4';check=target.with_suffix('.json')
            reuse=False
            if target.is_file() and check.is_file():
                old=json.loads(check.read_text(encoding='utf-8'))
                reuse=(old.get('source_fingerprint')==key and old.get('bytes')==target.stat().st_size and old.get('sha256')==digest(target))
            if not reuse:
                scene.frame_start=first;scene.frame_end=last;scene.render.filepath=str(target)
                bpy.ops.render.render(animation=True)
            block={'first_frame':first,'last_frame':last,'frame_count':last-first+1,
              'path':str(target),'bytes':target.stat().st_size,'sha256':digest(target),'source_fingerprint':key,'reused':reuse}
            write_json(check,block);record['blocks'].append(block);write_json(manifest,record)
            print(f'V8_BLOCK_COMPLETE {args.chapter} {last}/{duration*30}',flush=True)
        playlist=blockdir/'concat.txt';playlist.write_text(''.join("file '"+b['path'].replace('\\','/').replace("'","'\\''")+"'\n" for b in record['blocks']),encoding='utf-8')
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',playlist,'-map','0:v:0','-an','-c:v','copy','-movflags','+faststart',raw])
        record['raw_verification']=probe_and_decode(DEFAULT_FFMPEG,raw,duration,duration*30)
        record['render_complete']=True;write_json(manifest,record)
    print('V8_CHAPTER_READY '+args.chapter,flush=True)

if __name__=='__main__':main()
