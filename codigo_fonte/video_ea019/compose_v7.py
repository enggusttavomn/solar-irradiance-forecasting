"""Compose the approved introduction plus plans9-22 as one review MP4."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import html
import json
import subprocess
import textwrap
import sys
from compose_pilot import DEFAULT_FFMPEG,command,probe_and_decode
from overlays import Cue,Overlay,read_srt
from intro_v6_plan import PHASES as INTRO_PHASES,srt_time
from narration_v7 import final_cues

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
INTRO=ROOT/'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
CHAPTERS=[('modelos',40,60),('geografia',100,54),('entradas_tarefas',154,70)]
DURATION=224

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def cues(phases):
    result=[]
    for a,b,text in phases:
        lines=textwrap.wrap(text,42,break_long_words=False,break_on_hyphens=False)
        chunks=[lines[0],'\n'.join(lines[1:])] if len(lines)==3 else ['\n'.join(lines[i:i+2]) for i in range(0,len(lines),2)]
        total=sum(len(c) for c in chunks);t=a
        for i,c in enumerate(chunks):
            end=b if i==len(chunks)-1 else t+(b-a)*len(c)/total
            result.append(Cue(t,end,c));t=end
    return result

def progress(stage,**data):
    (OUT/'progresso_v7.json').write_text(json.dumps({'stage':stage,'updated_utc':datetime.now(timezone.utc).isoformat(),**data},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def prepare():
    phases=list(INTRO_PHASES);records=[]
    for name,start,duration in CHAPTERS:
        record=json.loads((OUT/'cenas'/f'{name}_manifesto_v7.json').read_text(encoding='utf-8'))
        if not record['render_complete'] or record['resolution_percentage']!=100:raise ValueError('Final render not complete: '+name)
        if record['duration']!=duration:raise ValueError('Chapter length differs')
        record['cues']=final_cues(name,record['cues'])
        phases.extend((a+start,b+start,text) for a,b,text in record['cues']);records.append(record)
    allcues=cues(phases)
    (OUT/'Legendas_Revisao_ate_Plano22_v7.srt').write_text('\n\n'.join(f'{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}' for i,c in enumerate(allcues,1))+'\n',encoding='utf-8-sig')
    read_srt(OUT/'Legendas_Revisao_ate_Plano22_v7.srt')
    stamp=lambda s:f'{int(s)//60}:{s%60:04.1f}'
    (OUT/'Falas_Revisao_ate_Plano22_v7.txt').write_text('FALAS PARA NARRAR — INÍCIO ATÉ O PLANO22\nDuração3min44s. Sem filmagens pessoais; sem áudio.\n\n'+'\n\n'.join(f'{stamp(a)}–{stamp(b)}\n{t}' for a,b,t in phases)+'\n',encoding='utf-8-sig')
    plan={'version':7,'duration':DURATION,'phases':phases,'cues':[c.__dict__ for c in allcues],
          'approved_intro_reused':True,'approved_intro_seconds':40,'review_through_storyboard_plan':22,
          'narration_recorded':False,'camera_footage_included':False,'original_storyboard_retimed_for_explanation':True}
    (OUT/'plano_video_v7.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return records,phases

def compose():
    records,phases=prepare();files=[];raw=[];intro_hashes={}
    for captions in (True,False):
        tag='com_legendas' if captions else 'sem_legendas'
        initial=INTRO/f'Revisao_00_40_{tag}_v6.mp4';intro_hashes[str(initial)]=sha(initial)
        pieces=[initial]
        for record,(name,start,duration) in zip(records,CHAPTERS):
            source=Path(record['raw_mp4']);target=OUT/'cenas'/f'{name}_{tag}_v7.mp4'
            ass=OUT/'cenas'/f'{name}_{tag}_v7.ass';o=Overlay(duration)
            if captions:
                for c in cues(record['cues']):o.caption(c)
            o.write(ass)
            if not target.exists() or target.stat().st_mtime<max(source.stat().st_mtime,ass.stat().st_mtime):
                progress('composing',chapter=name,captions=captions)
                command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',source,'-vf','ass='+ass.relative_to(ROOT).as_posix(),
                         '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-threads','6',target])
            raw.append(probe_and_decode(DEFAULT_FFMPEG,target,duration,duration*30));pieces.append(target)
        concat=OUT/f'concat_{tag}_v7.txt'
        concat.write_text(''.join("file '"+p.as_posix().replace("'","'\\''")+"'\n" for p in pieces),encoding='utf-8')
        target=OUT/f'Video_GHI_Inicio_ate_Plano22_{tag}_v7.mp4'
        progress('joining',captions=captions)
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',concat,
                 '-map','0:v:0','-c:v','copy','-an','-movflags','+faststart',target])
        files.append(probe_and_decode(DEFAULT_FFMPEG,target,DURATION,DURATION*30))
    qa=OUT/'verificacao_final';qa.mkdir(exist_ok=True)
    samples=[1,39,41,46,50,55,61,66,72,79,83,88,94,98,103,108,114,121,129,136,143,149,157,166,174,181,188,197,205,211,216,222]
    samplepaths=[]
    for t in samples:
        p=qa/f't_{str(t).replace(".","_")}.png'
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-ss',t,'-i',OUT/'Video_GHI_Inicio_ate_Plano22_com_legendas_v7.mp4','-frames:v','1','-update','1',p]);samplepaths.append(str(p.relative_to(ROOT)))
    for path,digest in intro_hashes.items():
        if sha(Path(path))!=digest:raise ValueError('Approved introduction changed')
    record={'version':7,'status':'complete','duration_seconds':DURATION,'fps':30,'frame_count':DURATION*30,
            'resolution':[1920,1080],'files':files,'rendered_chapter_verification':raw,'audio_tracks':0,
            'full_decode_errors':0,'sampled_frames':samplepaths,'sampled_visual_review_passed':False,
            'scope':'Continuous review from beginning through revised storyboard plan22, no later footage',
            'approved_intro_unchanged':True,'approved_intro_hashes':intro_hashes,
            'older_versions_modified':False,'final_realtime_playback_reviewed':False}
    (OUT/'verificacao_video_v7.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    write_player(phases)
    progress('complete',duration_seconds=DURATION,files=files,full_decode_errors=0)
    print('V7_EXPORT_COMPLETE',flush=True)

def write_player(phases):
    name='Video_GHI_Inicio_ate_Plano22_com_legendas_v7.mp4'
    buttons=''.join(f'<button type="button" data-t="{s}">{html.escape(label)}</button>' for s,label in [(0,'Início'),(40,'Modelos'),(44,'LSTM'),(59,'Transformer'),(75,'Informer'),(91,'Mesma entrada'),(100,'Mapa'),(110,'NSRDB'),(125,'Distribuições'),(154,'Entradas'),(186,'Tarefas'),(190,'Horária'),(201,'Diária'),(212,'Mensal1'),(218,'Mensal6')])
    script='''<script>const v=document.querySelector('video');document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{v.currentTime=Number(b.dataset.t);v.play()});document.querySelector('select').onchange=e=>{const t=v.currentTime;v.src=e.target.value;v.onloadedmetadata=()=>{v.currentTime=t}};</script>'''
    doc=f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisão até plano22</title><style>body{{margin:0;background:#080a0d;color:#edf2f5;font:16px Segoe UI,Arial}}main{{max-width:1280px;margin:auto;padding:20px}}video{{width:100%;background:black}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}}button,select{{background:#202a32;color:#edf2f5;border:1px solid #53616b;padding:10px;border-radius:6px}}a{{color:#75d4de}}p{{line-height:1.5}}</style><main><h1>Revisão: início até o plano22</h1><p>3min44s · FullHD · sem áudio para gravação da sua narração. Os primeiros40s aprovados foram preservados.</p><video controls playsinline src="{name}"></video><nav>{buttons}<select aria-label="Versão"><option value="{name}">Com legendas</option><option value="Video_GHI_Inicio_ate_Plano22_sem_legendas_v7.mp4">Sem legendas</option></select></nav><p><a href="Falas_Revisao_ate_Plano22_v7.txt">Falas para narrar</a> · <a href="Legendas_Revisao_ate_Plano22_v7.srt">Legendas SRT</a></p></main>{script}</html>'''
    player=OUT/'assistir_revisao_ate_plano22_v7.html';player.write_text(doc,encoding='utf-8')
    relative=player.relative_to(ROOT)
    (ROOT/'ASSISTIR_REVISAO_ATE_PLANO22.cmd').write_bytes(('@echo off\r\nstart "" "%~dp0'+str(relative)+'"\r\n').encode('ascii'))

if __name__=='__main__':compose()
