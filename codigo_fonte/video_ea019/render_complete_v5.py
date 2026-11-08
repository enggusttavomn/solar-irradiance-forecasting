"""Render, compose and fully decode the 415-second native 3D film."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from compose_pilot import DEFAULT_FFMPEG,command,probe_and_decode
from overlays_v5 import write_v5_ass

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v5'
BLENDER=ROOT/'.tools/blender/blender-4.5.14-windows-x64/blender.exe'
PROGRESS=OUT/'progresso_render_v5.json'

def progress(**data):
    temp=PROGRESS.with_suffix('.tmp')
    temp.write_text(json.dumps({'updated_unix':time.time(),**data},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temp,PROGRESS)

def main():
    global PROGRESS
    parser=argparse.ArgumentParser()
    parser.add_argument('--render-only',action='store_true')
    parser.add_argument('--manifest',type=Path,default=OUT/'manifesto_producao_v5.json')
    parser.add_argument('--progress-file',type=Path)
    args=parser.parse_args()
    if args.progress_file:
        PROGRESS=args.progress_file
    start=time.monotonic();path=args.manifest
    data=json.loads(path.read_text(encoding='utf-8'));chapters=data['chapters']
    total=sum(c['frame_count'] for c in chapters)
    if not args.render_only:
        assert [c['id'] for c in chapters]==list(range(2,14))
        assert total==12450
    done=0
    for index,c in enumerate(chapters,1):
        n=c['id'];raw=Path(c['raw_mp4']);blend=Path(c['blend']);valid=False;raw_verification=None
        if raw.is_file() and raw.stat().st_size>10000 and raw.stat().st_mtime>=blend.stat().st_mtime:
            try:
                raw_verification=probe_and_decode(DEFAULT_FFMPEG,raw,c['duration_seconds'],c['frame_count'])
                valid=True
            except (AssertionError,RuntimeError):pass
        if not valid:
            print(f'RENDER {index}/{len(chapters)} · cena {n:02d} · {c["duration_seconds"]} s',flush=True)
            progress(stage='render',chapter=n,chapter_index=index,chapter_frame=0,chapter_frames=c['frame_count'],completed_frames=done,total_frames=total)
            with (OUT/'cenas'/f'cena_{n:02d}_render.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen([str(BLENDER),'--background',str(blend),'-t','6','-s','1','-e',str(c['frame_count']),'-a'],
                  cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,
                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in process.stdout:
                    log.write(line);match=re.search(r'Append frame (\d+)',line)
                    if match:
                        local=int(match[1])
                        if local%30==0 or local==c['frame_count']:
                            progress(stage='render',chapter=n,chapter_index=index,chapter_frame=local,chapter_frames=c['frame_count'],completed_frames=done+local,total_frames=total)
                        if local%300==0:print(f'QUADROS {done+local}/{total}',flush=True)
                if process.wait():raise RuntimeError(f'Falha no render da cena {n}; consultar log')
        c['raw_verification']=raw_verification or probe_and_decode(DEFAULT_FFMPEG,raw,c['duration_seconds'],c['frame_count'])
        c['rendered']=True;done+=c['frame_count']
        data['full_rendered']=len(chapters)==12 and all(x.get('rendered') for x in chapters)
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(f'CENA_CONCLUIDA {n:02d} · {done}/{total}',flush=True)
    if args.render_only:
        progress(stage='staged',completed_frames=done,total_frames=total,full_video_ready=False)
        print('RAW_V5_CHAPTERS_READY',flush=True)
        return
    progress(stage='composition',completed_frames=12450,total_frames=12450)
    listing=OUT/'capitulos_para_unir_v5.txt'
    listing.write_text('\n'.join("file '"+Path(c['raw_mp4']).as_posix().replace("'","'\\''")+"'" for c in chapters)+'\n',encoding='utf-8')
    base=OUT/'video_3d_base_v5.mp4'
    command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,'-an','-c:v','copy','-movflags','+faststart',base])
    probe_and_decode(DEFAULT_FFMPEG,base,415,12450)
    finals=[]
    for captions,suffix in [(True,'com_legendas'),(False,'sem_legendas')]:
        print('COMPONDO '+suffix,flush=True)
        ass=OUT/f'textos_{suffix}_v5.ass';layout=write_v5_ass(ass,include_captions=captions)
        (OUT/f'verificacao_textos_{suffix}_v5.json').write_text(json.dumps(layout,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        target=OUT/f'Video_TCC_GHI_6min55_{suffix}_v5.mp4'
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',base,'-vf','ass='+ass.relative_to(ROOT).as_posix(),
                 '-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-threads','6',target])
        verification=probe_and_decode(DEFAULT_FFMPEG,target,415,12450);finals.append(verification)
        print('MP4_VERIFICADO '+json.dumps(verification,ensure_ascii=True),flush=True)
    progress(stage='verification',completed_frames=12450,total_frames=12450)
    qa=OUT/'verificacao_final';qa.mkdir(exist_ok=True);sampled=[]
    for c in chapters:
        for t in c['qa_times']:
            second=c['start_seconds']+t;name=f'cena_{c["id"]:02d}_t{str(t).replace(".","_")}.png';png=qa/name
            command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-ss',str(second),'-i',OUT/'Video_TCC_GHI_6min55_com_legendas_v5.mp4','-frames:v','1','-update','1',png])
            sampled.append({'chapter':c['id'],'local_second':t,'global_second':second,'path':str(png.relative_to(ROOT))})
    report={'version':5,'status':'complete','duration_seconds':415,'frame_count':12450,'fps':30,'resolution':[1920,1080],
      'chapters':12,'files':finals,'sampled_frames':sampled,'full_decode_errors':0,'audio_tracks':0,
      'institutional_cards':False,'fixed_headers':False,'source_banners':False,'decorative_grid':False,
      'camera_footage_included':False,'native_3d_labels':True,'network_duration_seconds':75,'natural_factory':True,'matte_vivid_diagrams':True,
      'narration_timing':'planned; to be aligned with the recorded voice','total_pipeline_seconds':round(time.monotonic()-start,2),
      'sampled_visual_review_passed':False}
    (OUT/'verificacao_video_v5.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    progress(stage='complete',completed_frames=12450,total_frames=12450,files=finals)
    print('VIDEO_V5_COMPLETO',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        progress(stage='error',error=str(error));raise
