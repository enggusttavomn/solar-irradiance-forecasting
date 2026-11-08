"""Render only the six-second historical matrix with an unobstructed exception.

The approved V8/V9 sources and media are read-only inputs. This patch is inserted
at 520..526 seconds in the V9 animation before the final narration retiming.
"""
from pathlib import Path
import argparse, hashlib, json, sys, subprocess, re
import bpy, gpu

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v10/patches'
SOURCE=ROOT/'documentacao/relatorio_final_ea019/video/completo_v9/cenas/conclusao_v9.blend'
FFMPEG=ROOT/'.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
PATCH_BLEND=OUT/'matriz_historica_corrigida_v10.blend'
RAW=OUT/'matriz_historica_corrigida_bruta_v10.mp4'
FINAL=OUT/'matriz_historica_corrigida_6s_v10.mp4'

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--render',action='store_true')
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    OUT.mkdir(parents=True,exist_ok=True)
    original_hash=sha(SOURCE)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene=bpy.context.scene
    old=bpy.data.objects['V8 interpretação Exceção histórica']
    legend=bpy.data.objects['V8 interpretação Legenda históricos']
    old_body=old.data.body
    old.data.body=''
    legend.data.body='L: longo · C: curto     Exceção: LSTM horária'
    legend.data.size=.30
    legend.location.y=-.80
    legend.location.z=.85
    scene.render.engine='BLENDER_EEVEE_NEXT'
    scene.eevee.taa_render_samples=16
    scene.render.resolution_x=1920;scene.render.resolution_y=1080
    scene.render.resolution_percentage=100;scene.render.fps=30
    scene.frame_start=361;scene.frame_end=540
    scene.frame_set(361)
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(PATCH_BLEND))
    if not args.render:
        scene.render.image_settings.file_format='PNG'
        for t in [15,16.5,17.5]:
            scene.frame_set(round(t*30)+1)
            scene.render.filepath=str(OUT/f'qa_matriz_{str(t).replace(".","_")}.png')
            bpy.ops.render.render(write_still=True)
        record={'status':'awaiting_manual_sampled_visual_review','source_blend':str(SOURCE),
            'source_blend_sha256':original_hash,'old_exception_text':old_body,
            'new_combined_legend':legend.data.body,'legend_location':list(legend.location),
            'source_start':520,'source_end':526,'source_chapter_local_start':12,
            'source_chapter_local_end':18,'source_first_frame':361,'source_last_frame':540,
            'frame_count':180,'duration_seconds':6,'resolution':[1920,1080],'fps':30,'samples':16,
            'method':'Read-only V9 blend loaded; old obstructed label emptied; explicit exception merged into unobstructed foreground legend.',
            'original_sources_modified':False,'qa_samples_local_seconds':[15,16.5,17.5]}
        (OUT/'patch_excecao_lstm_v10.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    else:
        record=json.loads((OUT/'patch_excecao_lstm_v10.json').read_text(encoding='utf-8'))
        if not record.get('manual_visual_review_passed'):raise ValueError('Manual QA approval required before rendering patch')
        if record['source_blend_sha256']!=original_hash:raise ValueError('The source blend changed after QA')
        scene.render.image_settings.file_format='FFMPEG'
        scene.render.ffmpeg.format='MPEG4';scene.render.ffmpeg.codec='H264'
        scene.render.ffmpeg.constant_rate_factor='HIGH';scene.render.ffmpeg.ffmpeg_preset='REALTIME'
        scene.render.ffmpeg.audio_codec='NONE';scene.render.filepath=str(RAW)
        scene.frame_set(361);bpy.ops.render.render(animation=True)
        renderer=gpu.platform.renderer_get()
        if 'Arc' not in renderer:raise ValueError('Expected Intel Arc GPU, found '+renderer)
        command=[str(FFMPEG),'-v','error','-y','-i',str(RAW),'-vf','setpts=N/(30*TB)',
            '-r','30','-fps_mode','cfr','-frames:v','180','-an','-c:v','libx264','-crf','18',
            '-preset','medium','-threads','2','-pix_fmt','yuv420p','-video_track_timescale','15360',
            '-movflags','+faststart',str(FINAL)]
        result=subprocess.run(command,capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr[-3000:])
        decoded=subprocess.run([str(FFMPEG),'-v','error','-nostats','-progress','pipe:1','-i',str(FINAL),
            '-map','0:v:0','-f','null','-'],capture_output=True,text=True)
        counts=re.findall(r'^frame=(\d+)$',decoded.stdout,re.M)
        if decoded.returncode or decoded.stderr.strip() or not counts or int(counts[-1])!=180:
            raise ValueError('Patch decode/frame-count verification failed')
        record.update(status='complete',render_complete=True,path=str(FINAL.relative_to(ROOT)),
            sha256=sha(FINAL),bytes=FINAL.stat().st_size,full_decode_errors=0,
            gpu={'renderer':renderer,'vendor':gpu.platform.vendor_get(),'backend':gpu.platform.backend_type_get(),
                 'engine':scene.render.engine},original_blend_sha256_after=sha(SOURCE))
        if record['original_blend_sha256_after']!=original_hash:raise ValueError('Original blend changed')
        (OUT/'patch_excecao_lstm_v10.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
        print('V10_EXCEPTION_PATCH_READY',flush=True)
    if sha(SOURCE)!=original_hash:raise ValueError('Original blend must remain unchanged')

if __name__=='__main__':main()
