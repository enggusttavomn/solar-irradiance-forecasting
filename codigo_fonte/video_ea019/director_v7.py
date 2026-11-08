"""Build, render and sample the three new V7 chapters independently."""
import argparse
import importlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from common_v7 import OUT,setup,frame

MODULES={'modelos':('models_explainer_v7',60,40),
         'geografia':('geography_data_v7',54,100),
         'entradas_tarefas':('inputs_tasks_v7',70,154)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--chapter',choices=MODULES,required=True)
    p.add_argument('--qa',action='store_true');p.add_argument('--qa-times',type=float,nargs='*')
    p.add_argument('--render',action='store_true');p.add_argument('--percentage',type=int,default=100)
    p.add_argument('--samples',type=int,default=16)
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    module,duration,start=MODULES[args.chapter]
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'cenas').mkdir(exist_ok=True);(OUT/'qa_3d').mkdir(exist_ok=True)
    scene=setup(duration,args.samples,args.percentage)
    info=importlib.import_module(module).build(scene)
    if info.get('duration')!=duration:raise ValueError('Unexpected chapter duration')
    scene.name='V7 '+args.chapter
    scene.render.resolution_x=1920;scene.render.resolution_y=1080
    scene.render.resolution_percentage=args.percentage;scene.render.fps=30
    scene.frame_start=1;scene.frame_end=duration*30
    scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4'
    scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
    scene.render.ffmpeg.ffmpeg_preset='REALTIME';scene.render.ffmpeg.audio_codec='NONE'
    target=OUT/'cenas'/f'{args.chapter}_3d_v7.mp4';scene.render.filepath=str(target)
    scene.frame_set(1);bpy.context.preferences.filepaths.save_version=0
    blend=OUT/'cenas'/f'{args.chapter}_v7.blend';bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    record={**info,'chapter':args.chapter,'start':start,'end':start+duration,
            'blend':str(blend),'raw_mp4':str(target),'fps':30,'frames':duration*30,
            'resolution':[1920,1080],'resolution_percentage':args.percentage,
            'samples':args.samples,'render_complete':False}
    manifest=OUT/'cenas'/f'{args.chapter}_manifesto_v7.json'
    manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.qa:
        scene.render.image_settings.file_format='PNG'
        for t in args.qa_times or info['qa_times']:
            scene.frame_set(frame(t));scene.render.filepath=str(OUT/'qa_3d'/f'{args.chapter}_{str(t).replace(".","_")}.png')
            bpy.ops.render.render(write_still=True)
        scene.render.image_settings.file_format='FFMPEG';scene.render.filepath=str(target)
    if args.render:
        bpy.ops.render.render(animation=True)
        record['render_complete']=True;manifest.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('V7_CHAPTER_READY '+args.chapter,flush=True)

if __name__=='__main__':main()
