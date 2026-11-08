"""Render integral, composição e verificação dos 415 segundos da versão 3."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
from compose_pilot import command,probe_and_decode,DEFAULT_FFMPEG,srt_time
from overlays import timestamp,ass_color
from overlays_v3 import write_v3_ass

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v3'
BLENDER=ROOT/'.tools/blender/blender-4.5.14-windows-x64/blender.exe'
MANIFEST=OUT/'manifesto_producao_v3.json'
PROGRESS=OUT/'progresso_render_v3.json'


def write_progress(**values):
    state={'updated_unix':time.time(),**values}
    temporary=PROGRESS.with_suffix('.tmp')
    temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    os.replace(temporary,PROGRESS)


def transitions(path,chapters):
    body=path.read_text(encoding='utf-8-sig')
    color=ass_color('07090D')
    for chapter in chapters[1:]:
        boundary=chapter['start_seconds']
        for a,b,initial,final in [(boundary-4/30,boundary,'FF','00'),(boundary,boundary+4/30,'00','FF')]:
            milliseconds=round((b-a)*1000)
            tags=f'\\an7\\pos(0,0)\\p1\\bord0\\shad0\\c{color}&\\alpha&H{initial}&\\t(0,{milliseconds},\\alpha&H{final}&)'
            body+=f'Dialogue: 0,{timestamp(a)},{timestamp(b)},Drawing,,0,0,0,,{{{tags}}}m 0 0 l 1920 0 l 1920 1080 l 0 1080{{\\p0}}\n'
    path.write_text(body,encoding='utf-8-sig')


def main():
    started=time.monotonic()
    data=json.loads(MANIFEST.read_text(encoding='utf-8'))
    chapters=sorted(data['chapters'],key=lambda c:c['id'])
    assert len(chapters)==13
    assert sum(c['frame_count'] for c in chapters)==12450
    completed=0
    for chapter in chapters:
        number=chapter['id']
        blend=Path(chapter['blend']);raw=Path(chapter['raw_mp4'])
        assert blend.is_file() and blend.is_relative_to(OUT)
        valid=False
        if raw.is_file() and raw.stat().st_size>10000 and raw.stat().st_mtime>=blend.stat().st_mtime:
            try:
                probe_and_decode(DEFAULT_FFMPEG,raw,chapter['duration_seconds'],chapter['frame_count'])
                valid=True
            except (AssertionError,RuntimeError):
                valid=False
        if not valid:
            logpath=OUT/'cenas'/f'cena_{number:02d}_render.log'
            write_progress(stage='render',chapter=number,chapter_frames=chapter['frame_count'],chapter_frame=0,total_frames=12450,completed_frames=completed)
            print(f'INICIANDO_CAPITULO {number:02d}/13 ({chapter["duration_seconds"]} s)',flush=True)
            args=[str(BLENDER),'--background',str(blend),'-t','6','-s','1','-e',str(chapter['frame_count']),'-a']
            with logpath.open('w',encoding='utf-8') as log:
                process=subprocess.Popen(args,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                         text=True,encoding='utf-8',errors='replace',bufsize=1,
                                         creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in process.stdout:
                    log.write(line)
                    match=re.search(r'Append frame (\d+)',line)
                    if match:
                        local=int(match[1])
                        if local%30==0 or local==chapter['frame_count']:
                            write_progress(stage='render',chapter=number,chapter_frames=chapter['frame_count'],chapter_frame=local,
                                           total_frames=12450,completed_frames=completed+local)
                        if local%300==0:
                            print(f'QUADROS {completed+local}/12450 · capítulo {number:02d}',flush=True)
                code=process.wait()
                if code:
                    raise RuntimeError(f'Blender terminou com código {code}; consultar {logpath}')
        assert raw.is_file() and raw.stat().st_size>10000,raw
        chapter['raw_verification']=probe_and_decode(DEFAULT_FFMPEG,raw,chapter['duration_seconds'],chapter['frame_count'])
        chapter['rendered']=True
        completed+=chapter['frame_count']
        print(f'CAPITULO_CONCLUIDO {number:02d}/13 · {completed}/12450 quadros',flush=True)
        (OUT/'cenas'/f'cena_{number:02d}_manifesto.json').write_text(json.dumps(chapter,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        data['full_rendered']=all(c.get('rendered') for c in chapters)
        MANIFEST.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_progress(stage='composition',completed_frames=12450,total_frames=12450)
    listing=OUT/'capitulos_para_unir_v3.txt'
    lines=[]
    for chapter in chapters:
        escaped=Path(chapter['raw_mp4']).as_posix().replace("'","'\\''")
        lines.append("file '"+escaped+"'")
    listing.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    rawfull=OUT/'video_completo_3d_base_v3.mp4'
    command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',listing,
             '-map','0:v:0','-an','-c:v','copy','-movflags','+faststart',rawfull])
    probe_and_decode(DEFAULT_FFMPEG,rawfull,415,12450)
    finals=[]
    for captions,suffix in [(True,'com_legendas'),(False,'sem_legendas')]:
        print('COMPONDO '+suffix,flush=True)
        ass=OUT/f'textos_{suffix}.ass'
        write_v3_ass(ass,include_captions=captions)
        transitions(ass,chapters)
        target=OUT/f'Video_TCC_GHI_6min55_{suffix}_v3.mp4'
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',rawfull,
                 '-vf','ass='+ass.relative_to(ROOT).as_posix(),'-an','-c:v','libx264','-preset','veryfast',
                 '-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-threads','6',target])
        finals.append(probe_and_decode(DEFAULT_FFMPEG,target,415,12450))
        print('MP4_VERIFICADO '+json.dumps(finals[-1],ensure_ascii=True),flush=True)
    shotplan=json.loads((OUT/'plano_73_extraido.json').read_text(encoding='utf-8'))
    cues=shotplan['subtitles']
    srt='\n\n'.join(f"{i}\n{srt_time(c['start_s'])} --> {srt_time(c['end_s'])}\n{c['text']}" for i,c in enumerate(cues,1))+'\n'
    (OUT/'Legendas_video_completo_v3.srt').write_text(srt,encoding='utf-8-sig')
    narration=(ROOT/'documentacao/relatorio_final_ea019/video/trecho_animado_v2/falas_trecho_animado_v2.txt').read_text(encoding='utf-8-sig')
    narration=narration.replace('FALAS — TRECHO ANIMADO DO TCC — V2','FALAS — VÍDEO COMPLETO DO TRECHO ANIMADO — V3',1)
    (OUT/'Falas_para_narrar_video_completo_v3.txt').write_text(narration,encoding='utf-8-sig')
    write_progress(stage='verification',completed_frames=12450,total_frames=12450)
    verification_dir=OUT/'verificacao_final'
    verification_dir.mkdir(exist_ok=True)
    video=OUT/'Video_TCC_GHI_6min55_com_legendas_v3.mp4'
    sampled=[]
    for shot in shotplan['middle_shots']:
        second=(shot['start_s']+shot['end_s'])/2
        target=verification_dir/(shot['id']+'.png')
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-ss',f'{second:.3f}','-i',video,'-frames:v','1','-update','1',target])
        sampled.append({'shot':shot['id'],'second':second,'file':str(target.relative_to(ROOT))})
    report={'version':3,'status':'vídeo completo renderizado e decodificado integralmente',
            'duration_seconds':415,'frame_count':12450,'fps':30,'resolution':[1920,1080],
            'shot_count':63,'chapters':13,'camera_footage_included':False,'audio_tracks':0,
            'factory_included':True,'background_grid':False,'palette_background':'#07090D',
            'subtitles':90,'subtitle_timing':'referência do roteiro, aguardando a voz gravada',
            'files':finals,'sampled_shots':sampled,'total_pipeline_seconds':round(time.monotonic()-started,2)}
    (OUT/'verificacao_video_completo_v3.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_progress(stage='complete',completed_frames=12450,total_frames=12450,files=finals)
    print('VIDEO_COMPLETO_V3_CONCLUIDO',flush=True)


if __name__=='__main__':
    try:
        main()
    except Exception as error:
        write_progress(stage='error',error=str(error))
        raise
