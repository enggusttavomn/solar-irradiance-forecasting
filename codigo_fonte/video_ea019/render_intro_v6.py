"""Render, compose and fully decode the revised forty-second excerpt."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import time

from compose_pilot import DEFAULT_FFMPEG, command, probe_and_decode
from intro_v6_plan import OUT, ROOT, prepare

BLENDER=ROOT/'.tools/blender/blender-4.5.14-windows-x64/blender.exe'


def progress(stage,**data):
    target=OUT/'progresso_intro_v6.json'
    temp=target.with_suffix('.tmp')
    temp.write_text(json.dumps({'stage':stage,'updated_unix':time.time(),**data},indent=2)+'\n',encoding='utf-8')
    os.replace(temp,target)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--qa-only',action='store_true');parser.add_argument('--preflight-gate',action='store_true');args=parser.parse_args()
    prepare()
    manifest=json.loads((OUT/'manifesto_intro_v6.json').read_text(encoding='utf-8'))
    samples=[]
    qa=OUT/('qa_com_textos' if args.qa_only else 'verificacao_final');qa.mkdir(exist_ok=True)
    if not args.qa_only:
        raw=Path(manifest['raw_mp4']);blend=Path(manifest['blend'])
        valid=False
        if raw.is_file() and raw.stat().st_size>10000 and raw.stat().st_mtime>=blend.stat().st_mtime:
            try:probe_and_decode(DEFAULT_FFMPEG,raw,40,1200);valid=True
            except (AssertionError,RuntimeError):pass
        if not valid:
            progress('render',completed_frames=0,total_frames=1200)
            with (OUT/'render_intro_v6.log').open('w',encoding='utf-8') as log:
                render_args=[str(BLENDER),'--background',str(blend),'-t','6']
                render_args+=['--python-exit-code','1','--python',str(ROOT/'codigo_fonte/video_ea019/render_intro_v6_blender.py')] if args.preflight_gate else ['-s','1','-e','1200','-a']
                p=subprocess.Popen(render_args,cwd=ROOT,
                  stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',bufsize=1,
                  creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in p.stdout:
                    log.write(line);log.flush()
                    if 'V6_QA_GATE_READY' in line:
                        progress('visual_quality_review',completed_frames=0,total_frames=1200)
                        print('V6_QA_GATE_READY',flush=True)
                    match=re.search(r'Append frame (\d+)',line)
                    if match:
                        n=int(match[1])
                        if n%30==0 or n==1200:progress('render',completed_frames=n,total_frames=1200)
                        if n%150==0:print('V6_FRAMES '+str(n)+'/1200',flush=True)
                if p.wait():raise RuntimeError('Blender render failed; see render_intro_v6.log')
        raw_check=probe_and_decode(DEFAULT_FFMPEG,raw,40,1200)
        finals=[]
        progress('composition',completed_frames=1200,total_frames=1200)
        for suffix in ['com_legendas','sem_legendas']:
            target=OUT/f'Revisao_00_40_{suffix}_v6.mp4'
            ass=OUT/f'textos_{suffix}_v6.ass'
            command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',raw,'-vf','ass='+ass.relative_to(ROOT).as_posix(),
              '-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-threads','6',target])
            finals.append(probe_and_decode(DEFAULT_FFMPEG,target,40,1200))
            print('V6_MP4_VERIFIED '+suffix,flush=True)
        for second in manifest['qa_times']:
            name='t_'+str(second).replace('.','_')+'.png';png=qa/name
            command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-ss',str(second),'-i',OUT/'Revisao_00_40_com_legendas_v6.mp4','-frames:v','1','-update','1',png])
            samples.append(str(png.relative_to(ROOT)))
        report={'version':6,'scope_seconds':[0,40],'status':'complete','duration_seconds':40,'fps':30,'frame_count':1200,
          'resolution':[1920,1080],'files':finals,'raw_verification':raw_check,'sampled_frames':samples,
          'full_decode_errors':0,'audio_tracks':0,'source_report_pages':[7,8,17,29],
          'scientific_variable':'GHI W/m2','potential_application_only':True,'v5_modified':False,
          'sampled_visual_review_passed':False}
        (OUT/'verificacao_intro_v6.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        progress('complete',files=finals)
    else:
        for second in manifest['qa_times']:
            name='t_'+str(second).replace('.','_')+'.png'
            source=OUT/'qa_3d'/name;target=qa/name
            command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',source,'-vf',
              f'setpts=PTS+{second}/TB,ass='+(OUT/'textos_com_legendas_v6.ass').relative_to(ROOT).as_posix(),'-frames:v','1','-update','1',target])
    print('V6_QA_READY' if args.qa_only else 'V6_INTRO_COMPLETE',flush=True)


if __name__=='__main__':
    try:main()
    except Exception as error:progress('error',error=str(error));raise
