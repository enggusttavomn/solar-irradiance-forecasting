"""Render the real narrated presentation, with and without a ducked music bed."""
import sys,math,re,html,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from montagem_v10_common import *
from overlays import Overlay,Cue,WHITE,CYAN,VIOLET,MUTED
from audit_delivery_v8 import mp4_headers

TIMELINE=OUT/'timeline_montagem_v10.json'
CHUNKS=OUT/'cenas_editadas'
SILENT=OUT/'Imagem_Final_1080p_v10.mp4'
VOICE_ONLY=OUT/'Video_TCC_Final_Somente_Voz_v10.mp4'
WITH_MUSIC=OUT/'Video_TCC_Final_Com_Trilha_v10.mp4'
MUSIC=OUT/'audio/trilha_ambiente_original_v10.wav'

def absolute(path):
    path=Path(path);return path if path.is_absolute() else ROOT/path

def source_for(item):
    if item['kind']=='intro':return INTRO
    if item['kind']=='ending':return FACTORY
    # An isolated repair replaces the faulty matrix before retiming.
    if abs(item['video_start']-520)<.001 and abs(item['video_end']-526)<.001:return PATCH
    return absolute(item.get('source_path',BASE))

def overlays_for(item,target):
    duration=item['frames']/FPS;overlay=Overlay(duration)
    if item['kind']=='ending':
        overlay.text(0,min(5.4,duration),'3 arquiteturas · 10 localidades',x=960,y=92,
            align=8,size=49,bold=True,fade_ms=280)
        overlay.text(0,min(5.4,duration),'Um protocolo comum de avaliação',x=960,y=154,
            align=8,size=31,color=MUTED,fade_ms=280)
        if duration>5.4:
            until=min(12.3,duration)
            overlay.text(5.4,until,'Transformer · horária e diária',x=960,y=78,align=8,
                size=43,color=CYAN,bold=True,fade_ms=220)
            overlay.text(5.4,until,'Informer · tarefas mensais',x=960,y=137,align=8,
                size=43,color=VIOLET,bold=True,fade_ms=220)
            overlay.text(5.4,until,'Nos horizontes completos avaliados',x=960,y=199,align=8,
                size=27,color=MUTED,fade_ms=220)
        if duration>12.3:
            overlay.text(12.3,duration,'Uma base experimental para orientar',x=960,y=75,
                align=8,size=44,bold=True,fade_ms=260)
            overlay.text(12.3,duration,'a escolha dos modelos de previsão solar',x=960,y=133,
                align=8,size=40,fade_ms=260)
        if duration>1.2:
            overlay.text(max(0,duration-1.15),duration,'Obrigado pela atenção',x=960,y=213,
                align=8,size=29,color=MUTED,fade_ms=180)
    for c in item.get('cues',[]):
        a=max(0,float(c['start']));b=min(duration,float(c['end']))
        if b<=a:continue
        text=c['text']
        if len(text.splitlines())>2 or max(map(len,text.splitlines()))>42:raise ValueError('Caption overflow')
        if item['kind']=='intro':
            overlay.text(a,b,text,x=600,y=985,size=40,style='Caption',align=2,layer=10,fade_ms=80)
        else:overlay.caption(Cue(a,b,text))
    overlay.write(target)

def encode(item,source_sha):
    frames=int(item['frames']);duration=frames/FPS;ident=str(item['id'])
    target=CHUNKS/(ident+'.mp4');ass=target.with_suffix('.ass');cache=target.with_suffix('.json')
    src=source_for(item);overlays_for(item,ass)
    vstart=float(item.get('video_start',0));vend=float(item.get('video_end',duration))
    if src==PATCH:vstart=0;vend=6
    key={'source':str(src),'source_sha256':source_sha[str(src)],'start':vstart,'end':vend,
        'frames':frames,'ass_sha256':sha(ass),'format':'x264_medium_crf18_cfr30_timescale15360_v10b'}
    old=read(cache,{})
    if target.exists()and old.get('key')==key and sha(target)==old.get('sha256'):
        return old
    if item['kind']=='ending':
        inputs=['-loop','1','-framerate','30','-i',src]
        # Subtle movement from the approved clean 3D factory render.
        vf=(f"scale=2016:1134,crop=1920:1080:x='48+8*sin(t/8)':y='27+5*sin(t/11)',fps=30,")
    else:
        original=vend-vstart
        inputs=['-ss',f'{vstart:.8f}','-threads','2','-i',src]
        vf=(f'trim=duration={original:.8f},setpts=(PTS-STARTPTS)*{duration/original:.10f},fps=30,'
            f'tpad=stop_mode=clone:stop_duration=2,trim=end_frame={frames},')
    vf+='ass='+ass.relative_to(ROOT).as_posix()
    if item['kind']=='intro':vf+=',fade=t=in:st=0:d=0.10'
    if item['kind']=='ending':vf+=f',fade=t=out:st={max(0,duration-.65):.6f}:d=0.65'
    run([FFMPEG,'-v','error','-y',*inputs,'-vf',vf,'-an','-frames:v',frames,'-r','30','-fps_mode','cfr',
        '-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p','-threads','3',
        '-video_track_timescale','15360','-map_metadata','-1','-movflags','+faststart',target])
    header=mp4_headers(target)
    if abs(header['fps']-30)>1e-6 or abs(header['duration_seconds']-duration)>1e-5:
        raise ValueError('Chunk timing failed '+ident+str(header))
    record={'id':ident,'key':key,'path':str(target.relative_to(ROOT)),'sha256':sha(target),
        'frames':frames,'duration':duration,'header':header}
    write(cache,record);return record

def compose_picture(timeline):
    CHUNKS.mkdir(parents=True,exist_ok=True)
    items=timeline['items'];unique={str(source_for(x)) for x in items}
    source_sha={p:sha(p)for p in unique}
    completed=[]
    with ThreadPoolExecutor(max_workers=2)as pool:
        tasks={pool.submit(encode,item,source_sha):item['id'] for item in items}
        for task in as_completed(tasks):
            completed.append(task.result())
            progress('rendering_timed_video',completed=len(completed),total=len(items),last=tasks[task])
            print(f'V10_CHUNK {len(completed)}/{len(items)} {tasks[task]}',flush=True)
    paths={r['id']:ROOT/r['path']for r in completed}
    listing=OUT/'concat_imagem_v10.txt'
    listing.write_text(''.join("file '"+paths[str(x['id'])].as_posix().replace("'","'\\''")+"'\n"for x in items),encoding='utf-8')
    progress('assembling_picture')
    run([FFMPEG,'-v','error','-y','-f','concat','-safe','0','-i',listing,'-map','0:v:0','-an',
        '-c:v','copy','-map_metadata','-1','-movflags','+faststart',SILENT])
    header=mp4_headers(SILENT)
    if header['fps']!=30 or abs(header['duration_seconds']-timeline['frames']/30)>1e-5:
        raise ValueError('Assembled picture duration error '+str(header))
    write(OUT/'verificacao_imagem_montada_v10.json',{'source_hashes':source_sha,'chunks':completed,
        'frames':timeline['frames'],'duration':timeline['frames']/30,'header':header,'sha256':sha(SILENT)})

def mix(timeline):
    voice=absolute(timeline['audio_path']);duration=timeline['frames']/30
    progress('exporting_voice_only')
    run([FFMPEG,'-v','error','-y','-i',SILENT,'-i',voice,'-map','0:v:0','-map','1:a:0',
        '-c:v','copy','-af','alimiter=limit=0.891251:attack=5:release=70:level=false:latency=true',
        '-c:a','aac','-b:a','192k','-ar','48000','-ac','2','-t',f'{duration:.8f}',
        '-map_metadata','-1','-movflags','+faststart',VOICE_ONLY])
    progress('mixing_ducked_music')
    mixgraph=(f'[1:a]asplit=2[v][sc];[2:a]atrim=duration={duration:.8f},asetpts=PTS-STARTPTS,'
        f'volume=0.75,afade=t=in:st=0:d=1.8,afade=t=out:st={max(0,duration-3):.8f}:d=3[m];'
        '[m][sc]sidechaincompress=threshold=0.04:ratio=6:attack=25:release=650:knee=4:link=maximum:mix=1[duck];'
        '[v][duck]amix=inputs=2:duration=first:normalize=0,'
        'alimiter=limit=0.891251:attack=5:release=70:level=false:latency=true[out]')
    run([FFMPEG,'-v','error','-y','-i',SILENT,'-i',voice,'-i',MUSIC,'-filter_complex',mixgraph,
        '-map','0:v:0','-map','[out]','-c:v','copy','-c:a','aac','-b:a','192k','-ar','48000',
        '-ac','2','-t',f'{duration:.8f}','-map_metadata','-1','-movflags','+faststart',WITH_MUSIC])
    progress('verifying_final_exports')
    files=[media_info(p,decode=True)for p in [VOICE_ONLY,WITH_MUSIC]]
    for f in files:
        if f['decoded_frames']!=timeline['frames']or not f['has_audio']:raise ValueError('Final stream failure')
    # Both deliverables must contain the same picture, with only the music mix differing.
    hashes=[]
    for p in [VOICE_ONLY,WITH_MUSIC]:
        r=run([FFMPEG,'-v','error','-i',p,'-map','0:v:0','-c','copy','-f','hash','-hash','sha256','-'])
        hashes.append(r.stdout.strip())
    if hashes[0]!=hashes[1]:raise ValueError('Music variant changed the picture')
    result={'version':10,'status':'encoded_pending_sampled_review','files':files,
        'frames':timeline['frames'],'fps':30,'duration_seconds':duration,'music_ducking':True,
        'same_video_bitstream':True,'video_stream_sha256':hashes[0],
        'recorded_voice_only':True,'voice_synthesis_used':False,'voice_time_stretch_used':False,
        'late_lstm_label_fixed':True,'last_weak_conclusion_replaced':True,
        'cover_version':5,'presenter_original_color':True,'background_black':True,
        'sampled_visual_review_passed':False,'full_realtime_playback_reviewed':False}
    write(OUT/'verificacao_video_final_v10.json',result)
    write_player(duration)
    print('V10_EXPORTS_READY_FOR_REVIEW',flush=True)

def write_player(duration):
    page=f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vídeo final narrado</title><style>body{{margin:0;background:#000;color:#eee;font:16px Segoe UI,Arial}}main{{max-width:1280px;margin:auto;padding:20px}}video{{width:100%;background:#000}}select,a{{font:inherit;color:#9bcfd9}}select{{background:#16191c;padding:10px}}a{{margin-right:16px}}</style><main><h1>Vídeo final narrado</h1><video controls playsinline src="{VOICE_ONLY.name}"></video><p><select aria-label="Versão do áudio"><option value="{VOICE_ONLY.name}">Somente voz</option><option value="{WITH_MUSIC.name}">Voz com trilha sonora</option></select></p><p><a href="{VOICE_ONLY.name}">Baixar sem trilha</a><a href="{WITH_MUSIC.name}">Baixar com trilha</a><a href="Legendas_Finais_v10.srt">Legendas</a></p></main><script>const v=document.querySelector('video');document.querySelector('select').onchange=e=>{{const t=v.currentTime;v.src=e.target.value;v.onloadedmetadata=()=>v.currentTime=t}};</script></html>'''
    player=OUT/'assistir_video_final_narrado_v10.html';player.write_text(page,encoding='utf-8')
    (ROOT/'ASSISTIR_VIDEO_FINAL_NARRADO_V10.cmd').write_bytes(('@echo off\r\nstart "" "%~dp0'+str(player.relative_to(ROOT))+'"\r\n').encode('ascii'))

if __name__=='__main__':
    timeline=read(TIMELINE)
    if not timeline:raise SystemExit('Waiting for reviewed PCM edit timeline')
    if not INTRO.exists()or not MUSIC.exists():raise SystemExit('Missing intro/music asset')
    compose_picture(timeline);mix(timeline)
