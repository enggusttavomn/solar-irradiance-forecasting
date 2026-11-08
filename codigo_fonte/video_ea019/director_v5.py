"""Rebuild the factory and restyle the full film with natural vivid materials."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from blender_pilot import setup,frame

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v5'
PREVIOUS=ROOT/'documentacao/relatorio_final_ea019/video/completo_v4'

def main():
    p=argparse.ArgumentParser();p.add_argument('--index',type=int,nargs='*');p.add_argument('--qa',action='store_true')
    p.add_argument('--render',action='store_true');p.add_argument('--factory-samples',type=int,default=16)
    p.add_argument('--factory-engine',default='BLENDER_EEVEE_NEXT');p.add_argument('--diagram-engine',default='BLENDER_WORKBENCH')
    args=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    from natural_style_v5 import apply_natural_style
    plan=json.loads((OUT/'plano_video_v5.json').read_text(encoding='utf-8'))
    previous=json.loads((PREVIOUS/'manifesto_producao_v4.json').read_text(encoding='utf-8'))
    old={c['id']:c for c in previous['chapters']}
    (OUT/'cenas').mkdir(parents=True,exist_ok=True);(OUT/'qa_3d').mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.save_version=0;entries=[]
    for chapter in plan['chapters']:
        n=chapter['id'];duration=chapter['duration']
        if args.index and n not in args.index:continue
        if n==2:
            scene=setup(SimpleNamespace(engine='BLENDER_EEVEE_NEXT',samples=args.factory_samples,resolution_percentage=100))
            from scenes_factory_v5 import build_factory_v5
            info=build_factory_v5(duration)
            engine=args.factory_engine
        else:
            bpy.ops.wm.open_mainfile(filepath=old[n]['blend']);scene=bpy.context.scene
            info={**old[n]['scene_metadata'],'geometry_from_version':4};engine=args.diagram_engine
        scene.name=f'EA019 cores naturais v5 · {n:02d}'
        style=apply_natural_style(scene,n,engine=engine,samples=args.factory_samples if n==2 else 8)
        scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
        scene.render.fps=30;scene.render.fps_base=1;scene.frame_start=1;scene.frame_end=round(duration*30)
        scene.render.image_settings.file_format='FFMPEG';scene.render.image_settings.color_mode='RGB'
        scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
        scene.render.ffmpeg.ffmpeg_preset='REALTIME';scene.render.ffmpeg.audio_codec='NONE'
        scene.render.filepath=str(OUT/'cenas'/f'cena_{n:02d}_3d.mp4')
        scene.frame_set(1);blend=OUT/'cenas'/f'cena_{n:02d}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        qa_times=old[n]['qa_times']
        if args.qa:
            raw=scene.render.filepath;scene.render.image_settings.file_format='PNG'
            for second in qa_times:
                scene.frame_set(frame(second));scene.render.filepath=str(OUT/'qa_3d'/f'cena_{n:02d}_t{str(second).replace(".","_")}.png')
                bpy.ops.render.render(write_still=True)
            scene.render.image_settings.file_format='FFMPEG';scene.render.filepath=raw
        if args.render:bpy.ops.render.render(animation=True)
        entry={**chapter,'start_seconds':chapter['start'],'end_seconds':chapter['end'],
          'duration_seconds':duration,'frame_count':round(duration*30),'blend':str(blend),
          'raw_mp4':scene.render.filepath,'rendered':bool(args.render),'scene_metadata':info,
          'render_style':style,'qa_times':qa_times}
        entries.append(entry)
        (OUT/'cenas'/f'cena_{n:02d}_manifesto.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('V5_CHAPTER '+str(n),flush=True)
    manifest={'version':5,'duration_seconds':415,'fps':30,'frame_count':12450,'resolution':[1920,1080],
      'chapters':entries,'all_prepared':len(entries)==12,'full_rendered':len(entries)==12 and all(c['rendered'] for c in entries),
      'natural_factory':True,'matte_vivid_diagrams':True,'camera_footage_included':False,'narration_recorded':False,
      'fixed_headers':False,'source_banners':False}
    name='manifesto_producao_v5.json' if not args.index else 'manifesto_parcial_'+('_'.join(map(str,args.index)))+'.json'
    (OUT/name).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('V5_PREPARED '+str(len(entries)),flush=True)

if __name__=='__main__':main()
