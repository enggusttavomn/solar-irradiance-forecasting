"""GPU 3D renderer, verified resumable blocks and exact reused intervals."""
import argparse,hashlib,importlib,json,os,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy,gpu
from config_v9 import *
from common_v7 import setup,frame
from compose_pilot import DEFAULT_FFMPEG,command,probe_and_decode

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for n in range(200):
        try:os.replace(tmp,path);return
        except PermissionError:time.sleep(.05)
    raise RuntimeError('Cannot replace '+str(path))
def sources(module):
    names=['director_v9','config_v9','common_v7','blender_pilot','factory_site_v6','retime_v9',module]
    extra={'intro_v9':['director_intro_v6','solar_atmosphere_v6','common_v4'],
      'models_v9':['models_explainer_v7','narration_v7'],
      'geography_data_v9':['geography_data_v7'],'inputs_tasks_v9':['inputs_tasks_v7','geography_data_v7'],
      'methodology_v9':['methodology_v8','retime_v9'],
      'interpretation_v9':['interpretation_v8','retime_v9']}
    names+=extra.get(module,[])
    paths=[ROOT/f'codigo_fonte/video_ea019/{n}.py' for n in dict.fromkeys(names)]
    paths+=[ROOT/'documentacao/relatorio_final_ea019/video/completo_v8/fontes_resultados_v8.json']
    paths+=[ROOT/'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7/referencias/ghi_distributions_training.json']
    if module=='models_v9':paths.append(MODELS_SOURCE)
    assets=ROOT/'codigo_fonte/video_ea019/assets'
    paths+=list(assets.glob('*.json'))
    values={p.relative_to(ROOT).as_posix():sha(p) for p in paths if p.is_file()}
    key=hashlib.sha256(json.dumps({'sources':values,'samples':16,'resolution':[1920,1080],'fps':30},sort_keys=True).encode()).hexdigest()
    return key,values
def concat(pieces,target):
    listing=target.with_suffix('.concat.txt')
    listing.write_text(''.join("file '"+str(p).replace('\\','/').replace("'","'\\''")+"'\n" for p in pieces),encoding='utf-8')
    command([DEFAULT_FFMPEG,'-v','error','-y','-f','concat','-safe','0','-i',listing,'-an','-c:v','copy','-movflags','+faststart',target])
def cfr(source,target,first=0,count=None):
    filters=f'trim=start_frame={first}'
    if count is not None:filters+=f':end_frame={first+count}'
    filters+=',setpts=N/(30*TB)'
    command([DEFAULT_FFMPEG,'-v','error','-y','-i',source,'-vf',filters,'-an',
      '-c:v','libx264','-preset','medium','-crf','18','-r','30','-fps_mode','cfr',
      '-video_track_timescale','15360','-pix_fmt','yuv420p','-threads','6',target])
def main():
    p=argparse.ArgumentParser();p.add_argument('--chapter',choices=CHAPTERS,required=True)
    p.add_argument('--qa',action='store_true');p.add_argument('--qa-times',type=float,nargs='*')
    p.add_argument('--render',action='store_true');p.add_argument('--percentage',type=int,default=100)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    spec=CHAPTERS[a.chapter];module=spec['module'];duration=spec['duration']
    out=OUT/'cenas';out.mkdir(parents=True,exist_ok=True);qa=OUT/'qa_3d';qa.mkdir(exist_ok=True)
    scene=setup(duration,16,a.percentage)
    info=importlib.import_module(module).build(scene)
    if info['duration']!=duration:raise ValueError('Incorrect duration '+a.chapter)
    scene.frame_start=1;scene.frame_end=duration*30;scene.render.fps=30
    scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=a.percentage
    scene.render.image_settings.file_format='FFMPEG';scene.render.ffmpeg.format='MPEG4'
    scene.render.ffmpeg.codec='H264';scene.render.ffmpeg.constant_rate_factor='HIGH'
    scene.render.ffmpeg.ffmpeg_preset='REALTIME';scene.render.ffmpeg.audio_codec='NONE'
    raw=out/f'{a.chapter}_3d_v9.mp4';scene.render.filepath=str(raw)
    scene.frame_set(1);bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(out/f'{a.chapter}_v9.blend'))
    key,hashes=sources(module)
    record={**info,**spec,'version':9,'chapter':a.chapter,'fps':30,'frames':duration*30,
     'resolution':[1920,1080],'resolution_percentage':a.percentage,'samples':16,
     'raw_mp4':str(raw),'render_complete':False,'source_fingerprint':key,'source_hashes':hashes,'blocks':[]}
    manifest=out/f'{a.chapter}_manifesto_v9.json';write_json(manifest,record)
    if a.qa:
        scene.render.image_settings.file_format='PNG'
        for t in a.qa_times or info['qa_times']:
            scene.frame_set(frame(t));scene.render.filepath=str(qa/f'{a.chapter}_{str(t).replace(".","_")}.png')
            bpy.ops.render.render(write_still=True)
    if a.render:
        if a.percentage!=100:raise ValueError('Production must be FullHD')
        gate=json.loads((OUT/'qa_aprovado_v9.json').read_text(encoding='utf-8'))[a.chapter]
        if not gate.get('approved') or gate.get('source_hashes')!=hashes:raise ValueError('Unapproved source '+a.chapter)
        ranges=[(480,570),(1530,1800)] if a.chapter=='modelos' else [(0,duration*30)]
        scene.render.image_settings.file_format='FFMPEG'
        blockdir=out/'blocos'/a.chapter;blockdir.mkdir(parents=True,exist_ok=True)
        for lo,hi in ranges:
            for first0 in range(lo,hi,300):
                last=min(first0+300,hi);target=blockdir/f'f{first0+1:05d}_{last:05d}.mp4';check=target.with_suffix('.json')
                old=json.loads(check.read_text()) if check.exists() else {}
                reuse=target.exists() and old.get('source_fingerprint')==key and old.get('sha256')==sha(target)
                if not reuse:
                    scene.frame_start=first0+1;scene.frame_end=last;scene.render.filepath=str(target)
                    bpy.ops.render.render(animation=True)
                if 'Arc' not in gpu.platform.renderer_get():
                    raise RuntimeError('Expected Intel Arc hardware graphics, got '+gpu.platform.renderer_get())
                block={'first_frame':first0+1,'last_frame':last,'frame_count':last-first0,'path':str(target),
                  'bytes':target.stat().st_size,'sha256':sha(target),'source_fingerprint':key,'reused':reuse}
                write_json(check,block);record['blocks'].append(block);write_json(manifest,record)
                print(f'V9_BLOCK_COMPLETE {a.chapter} {last}',flush=True)
        if a.chapter=='modelos':
            pieces=[]
            for n,(source,first,count) in enumerate([(MODELS_SOURCE,0,480),(Path(record['blocks'][0]['path']),0,90),
              (MODELS_SOURCE,570,960),(Path(record['blocks'][1]['path']),0,270)]):
                clip=blockdir/f'join_{n}.mp4';cfr(source,clip,first,count);pieces.append(clip)
            concat(pieces,raw)
            record['approved_geometry_reused_ranges_seconds']=[[0,16],[19,51]]
        else:concat([Path(b['path']) for b in record['blocks']],raw)
        record['raw_verification']=probe_and_decode(DEFAULT_FFMPEG,raw,duration,duration*30)
        record['gpu']={'renderer':gpu.platform.renderer_get(),'vendor':gpu.platform.vendor_get(),
                       'backend':gpu.platform.backend_type_get(),'engine':scene.render.engine}
        record['render_complete']=True;write_json(manifest,record)
    print('V9_READY '+a.chapter,flush=True)
if __name__=='__main__':main()
