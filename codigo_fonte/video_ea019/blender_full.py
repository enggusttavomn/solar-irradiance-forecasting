"""Preparar/renderizar os capítulos 3D do trecho de 6min55s.

Cada capítulo é salvo separadamente para permitir ajustes locais sem refazer
toda a animação. O comando sem --render só prepara os arquivos .blend.
"""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from mathutils import Vector

from blender_pilot import FPS, box, emission, physical_scene, polyline, setup, temporal_scene
from scenes_models import build_models, build_quantization
from scenes_explainer import (
    build_objective, build_tasks, build_evaluation, build_mae,
    build_results, build_complements, build_limits, build_summary, build_opening,
)
from scenes_map import build_map

ROOT=Path(__file__).resolve().parents[2]
PLAN=ROOT/'documentacao/relatorio_final_ea019/video/trecho_animado_v2/plano_trecho_animado_v2.json'
OUT=ROOT/'documentacao/relatorio_final_ea019/video/trecho_animado_v2/producao'


def stage():
    from blender_pilot import surface
    floor=surface('Preto acetinado de palco',(.006,.011,.018,1),.5,.30)
    lines=emission('Grade discreta de palco',(.018,.038,.050,1),.5)
    box('Piso do palco',(0,0,-.13),(200,200,.12),floor,.02)
    for i in range(-11,12):
        polyline(f'Grade longa {i}',[(i,-12,-.055),(i,12,-.055)],lines,.004)
        polyline(f'Grade curta {i}',[(-12,i,-.055),(12,i,-.055)],lines,.004)


def timewarp_action(action, transform):
    if action is None:
        return
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            for vec in (point.co,point.handle_left,point.handle_right):
                vec.x=1+FPS*transform((vec.x-1)/FPS)
        curve.update()


def retime_all_ghi():
    def transform(t):
        return t*1.25 if t <=20 else t+5
    for action in bpy.data.actions:
        timewarp_action(action,transform)


def static_front_camera(scene, location=(0,-16,2.65), target=(0,0,2.65), ortho=13):
    camera=scene.camera
    camera.animation_data_clear()
    camera.location=location
    camera.rotation_euler=(Vector(target)-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.ortho_scale=ortho


def render_settings(scene, directory, number, duration):
    scene.frame_start=1
    scene.frame_end=duration*FPS
    scene.render.image_settings.file_format='FFMPEG'
    scene.render.ffmpeg.format='MPEG4'
    scene.render.ffmpeg.codec='H264'
    scene.render.ffmpeg.constant_rate_factor='HIGH'
    scene.render.ffmpeg.ffmpeg_preset='GOOD'
    scene.render.ffmpeg.audio_codec='NONE'
    scene.render.filepath=str(directory/f'cena_{number:02d}_3d.mp4')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=OUT)
    parser.add_argument('--index',type=int,nargs='*')
    parser.add_argument('--samples',type=int,default=16)
    parser.add_argument('--resolution-percentage',type=int,default=100)
    parser.add_argument('--render',action='store_true')
    parser.add_argument('--stills',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    directory=args.output_dir.resolve()
    directory.mkdir(parents=True,exist_ok=True)
    plan=json.loads(PLAN.read_text(encoding='utf-8'))
    prepared=[]
    bpy.context.preferences.filepaths.save_version=0
    builders={1:build_opening,3:build_objective,4:build_map,5:build_tasks,
              6:build_evaluation,7:build_models,8:build_quantization,9:build_mae,
              10:build_results,11:build_complements,12:build_limits,13:build_summary}
    for section in plan['scenes']:
        number=section['id']
        if args.index and number not in args.index:
            continue
        duration=section['end_seconds']-section['start_seconds']
        scene=setup(SimpleNamespace(engine='BLENDER_EEVEE_NEXT',samples=args.samples,
                                     resolution_percentage=args.resolution_percentage))
        # Discard orphan actions so a prior chapter's keyframes are not retimed.
        for action in list(bpy.data.actions):
            if action.users==0:
                bpy.data.actions.remove(action)
        scene.name=f"EA019 · {number:02d} · {section['title']}"
        if number==2:
            physical_scene()
            temporal_scene()
            retime_all_ghi()
            info={'physical_until_seconds':25,'time_series_from_seconds':25}
        else:
            stage()
            # Only the shared camera was originally keyed over 30 seconds.
            if scene.camera.animation_data:
                timewarp_action(scene.camera.animation_data.action,lambda t:t*duration/30)
            info=builders[number](duration=duration) or {}
            if number in (1,4,6,9,10,11,12,13):
                static_front_camera(scene)
        render_settings(scene,directory,number,duration)
        scene.frame_set(1)
        blend=directory/f'cena_{number:02d}.blend'
        bpy.ops.wm.save_as_mainfile(filepath=str(blend))
        entry={'id':number,'title':section['title'],'duration_seconds':duration,
               'start_seconds':section['start_seconds'],'end_seconds':section['end_seconds'],
               'frame_count':duration*FPS,'blend':str(blend),'raw_mp4':scene.render.filepath,
               'metadata':info,'rendered':False}
        if args.stills:
            old_format=scene.render.image_settings.file_format
            old_path=scene.render.filepath
            scene.frame_set(max(1,round(duration*FPS*.55)))
            scene.render.image_settings.file_format='PNG'
            scene.render.filepath=str(directory/f'cena_{number:02d}_preview.png')
            bpy.ops.render.render(write_still=True)
            scene.render.image_settings.file_format=old_format
            scene.render.filepath=old_path
        if args.render:
            bpy.ops.render.render(animation=True)
            entry['rendered']=True
        prepared.append(entry)
        (directory/f'cena_{number:02d}_manifesto.json').write_text(json.dumps(entry,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('CHAPTER_PREPARED '+json.dumps({'id':number,'duration':duration,'rendered':entry['rendered']}),flush=True)
    manifest={'duration_seconds':415,'fps':30,'width':1920,'height':1080,
              'full_expected_frames':12450,'chapters':prepared,
              'all_chapters_prepared':len(prepared)==13,
              'full_video_rendered':len(prepared)==13 and all(p['rendered'] for p in prepared),
              'subtitle_timing':'tempos de referência; sem voz gravada'}
    (directory/'manifesto_producao_3d.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('FULL_PROJECT_PREPARED '+json.dumps({'chapters':len(prepared),'rendered':manifest['full_video_rendered']}),flush=True)


if __name__=='__main__':
    main()
