"""Assemble revised explanations and exact narration for the student's opening."""
from datetime import datetime,timezone
import html,json,re,subprocess,sys,time
from pipeline_v9 import *
from compose_pilot import DEFAULT_FFMPEG,command,probe_and_decode,srt_time
from compose_v8 import cues,NARRATION_OVERRIDES
from overlays import Cue,Overlay,read_srt
from audit_delivery_v8 import mp4_headers

FINAL={True:OUT/'Video_TCC_GHI_Revisado_com_legendas_v9.mp4',False:OUT/'Video_TCC_GHI_Revisado_sem_legendas_v9.mp4'}
MOBILE=OUT/'Video_TCC_GHI_Revisado_para_celular_v9.mp4'
OPENING='Olá, eu sou Gustavo de Melo Nascimento, da Engenharia Elétrica da Unicamp. Neste trabalho, comparo LSTM, Transformer e Informer na previsão da irradiância solar em localidades ligadas à fabricação de veículos elétricos.'
VOICE_OVERRIDES9={
 'introducao':{(18,25):'Multiplicamos a DNI pelo cosseno do ângulo com a vertical e somamos a luz difusa.'},
 'modelos':{(16,19):'O estado final ajuda na previsão.',(51,55):'Os três recebem o mesmo histórico e a mesma localidade.'},
 'geografia':{(10,16):'A NSRDB estima a irradiância com satélites e dados atmosféricos.'},
 'metodologia':{(13,19):'Validação em 2023; teste em 2024.'},
 'metricas':{(0,9):'MAE é o erro absoluto médio: o tamanho médio da diferença entre previsão e referência, no mesmo instante.'},
 'conclusao':{(12,18):'Histórico longo: menor erro em onze de doze casos, exceto na LSTM horária.',
              (39,45):'No horizonte completo, Transformer teve menor erro horário e diário; Informer, nas tarefas mensais.',
              (45,52):'A escolha depende da tarefa, do horizonte e da localidade. Novos testes devem confirmar essa comparação.'}}

def progress(stage,**data):write_json(OUT/'progresso_v9.json',{'stage':stage,'updated_utc':datetime.now(timezone.utc).isoformat(),**data})
def prepare(require_render=True):
    phases=[];records=[];allcues=[]
    for name,spec in CHAPTERS.items():
        r=read(OUT/'cenas'/f'{name}_manifesto_v9.json')
        if not r:raise ValueError('Missing chapter '+name)
        if require_render and (not r.get('render_complete') or r.get('resolution_percentage')!=100):raise ValueError('Incomplete chapter '+name)
        local=[(a,b,VOICE_OVERRIDES9.get(name,{}).get((a,b),NARRATION_OVERRIDES.get(name,{}).get((a,b),text))) for a,b,text in r['cues']]
        if local[0][0]!=0 or local[-1][1]!=spec['duration']:raise ValueError('Narration length '+name)
        if any(a>=b or (i and a<local[i-1][1])for i,(a,b,t)in enumerate(local)):raise ValueError('Narration timing '+name)
        r['cues']=local;records.append(r)
        phases += [(a+spec['start'],b+spec['start'],text)for a,b,text in local]
        allcues += [Cue(c.start+spec['start'],c.end+spec['start'],c.text)for c in cues(local)]
    def srt(path,items):
        path.write_text('\n\n'.join(f'{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}'for i,c in enumerate(items,1))+'\n',encoding='utf-8-sig');read_srt(path)
    srt(OUT/'Legendas_Animacao_v9.srt',allcues)
    opening=cues([(0,20,OPENING)])
    srt(OUT/'Legendas_Com_Apresentacao_v9.srt',opening+[Cue(c.start+20,c.end+20,c.text)for c in allcues])
    stamp=lambda t:f'{int(t)//60:02d}:{t%60:04.1f}'
    timed='00:00.0–00:20.0 — APRESENTAÇÃO EM CÂMERA\n'+OPENING+'\n\n'
    timed+='\n\n'.join(f'{stamp(a+20)}–{stamp(b+20)}\n{text}'for a,b,text in phases)+'\n'
    (OUT/'Falas_Para_Gravar_Video_v9.txt').write_text(timed,encoding='utf-8-sig')
    (OUT/'Texto_Corrido_Para_Gravar_v9.txt').write_text(OPENING+'\n\n'+'\n\n'.join(t for a,b,t in phases)+'\n',encoding='utf-8-sig')
    write_json(OUT/'plano_video_v9.json',{'version':9,'duration':560,'fps':30,'frames':16800,
      'personal_intro_seconds':20,'personal_outro_seconds':0,'total_with_personal_intro':580,
      'opening_spoken_text':OPENING,'phases':phases,'cues':[c.__dict__ for c in allcues],
      'chapters':CHAPTERS,'narration_recorded':False,'personal_footage_included':False})
    return records,phases

def encode(r,name,captions):
    duration=CHAPTERS[name]['duration'];tag='com_legendas' if captions else 'sem_legendas'
    if name=='resultados':
        source=ROOT/f'documentacao/relatorio_final_ea019/video/completo_v8/cenas/resultados_{tag}_v8.mp4'
        return source,probe_and_decode(DEFAULT_FFMPEG,source,88,2640)
    target=OUT/'cenas'/f'{name}_{tag}_v9.mp4';ass=target.with_suffix('.ass');cache=target.with_suffix('.compose.json')
    overlay=Overlay(duration)
    if captions:
        for c in cues(r['cues']):overlay.caption(c)
    overlay.write(ass)
    key={'raw_sha256':sha(r['raw_mp4']),'ass_sha256':sha(ass),'format':'x264_medium_crf18_cfr30_timescale15360'}
    old=read(cache,{})
    if not(target.exists()and old.get('sources')==key and old.get('sha256')==sha(target)):
        progress('encoding_chapter',chapter=name,captions=captions)
        command([DEFAULT_FFMPEG,'-v','error','-y','-i',r['raw_mp4'],'-vf','ass='+ass.relative_to(ROOT).as_posix(),
         '-an','-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-r','30','-fps_mode','cfr',
         '-frames:v',duration*30,'-video_track_timescale','15360','-threads','6','-movflags','+faststart',target])
    check=probe_and_decode(DEFAULT_FFMPEG,target,duration,duration*30)
    write_json(cache,{'sources':key,'sha256':check['sha256'],'verification':check})
    return target,check

def compose():
    records,phases=prepare();files=[];chunks=[]
    for captions in (True,False):
        pieces=[]
        for name,r in zip(CHAPTERS,records):
            p,check=encode(r,name,captions);pieces.append(p);chunks.append({'chapter':name,'captions':captions,**check})
        playlist=OUT/('concat_com_v9.txt' if captions else 'concat_sem_v9.txt')
        playlist.write_text(''.join("file '"+p.as_posix().replace("'","'\\''")+"'\n"for p in pieces),encoding='utf-8')
        command([DEFAULT_FFMPEG,'-v','error','-y','-f','concat','-safe','0','-i',playlist,'-map','0:v:0','-an','-c:v','copy','-movflags','+faststart',FINAL[captions]])
        check=probe_and_decode(DEFAULT_FFMPEG,FINAL[captions],560,16800)
        header=mp4_headers(FINAL[captions])
        if header['fps']!=30 or header['duration_seconds']!=560:raise ValueError('Timestamp audit '+str(header))
        files.append(check)
    qa=OUT/'verificacao_final';qa.mkdir(exist_ok=True);samples=[]
    for name,r in zip(CHAPTERS,records):
        spec=CHAPTERS[name]
        for local in r.get('qa_times',[]):
            t=spec['start']+local
            if t>=560:continue
            target=qa/f't_{str(t).replace(".","_")}.png'
            command([DEFAULT_FFMPEG,'-v','error','-y','-ss',t,'-i',FINAL[True],'-frames:v','1','-update','1',target])
            samples.append(str(target.relative_to(ROOT)))
    write_json(OUT/'verificacao_video_v9.json',{'version':9,'status':'encoded_pending_manual_final_review',
     'duration_seconds':560,'fps':30,'frame_count':16800,'resolution':[1920,1080],'files':files,
     'chapters':chunks,'audio_tracks':0,'full_decode_errors':0,'sampled_frames':samples,
     'sampled_visual_review_passed':False,'final_realtime_playback_reviewed':False,
     'personal_intro_seconds_reserved':20,'personal_outro_seconds_reserved':0,
     'total_with_personal_intro':580,'older_video_files_modified':False})
    write_player();print('V9_FULLHD_COMPLETE',flush=True)

def write_player():
    labels={'introducao':'Sol e aplicações','modelos':'Redes','geografia':'Dados e frequência','entradas_tarefas':'Entradas e localidades',
      'metodologia':'Protocolo','quantizacao':'Quantização com números','metricas':'Entendendo o MAE','resultados':'Resultados','conclusao':'Conclusão'}
    buttons=''.join(f'<button data-t="{s["start"]}">{html.escape(labels[n])}</button>'for n,s in CHAPTERS.items())
    page=f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Vídeo revisado</title><style>body{{margin:0;background:#080a0d;color:#edf2f5;font:16px Segoe UI,Arial}}main{{max-width:1280px;margin:auto;padding:20px}}video{{width:100%;background:black}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}}button,select{{background:#202a32;color:#edf2f5;border:1px solid #53616b;padding:10px;border-radius:6px}}a{{color:#75d4de}}</style><main><h1>Vídeo revisado</h1><p>9min20s de animação · sua apresentação de 20s antes: total 9min40s. Pronto para sua narração.</p><video controls playsinline src="{FINAL[True].name}"></video><nav>{buttons}<select aria-label="Versão"><option value="{FINAL[True].name}">Full HD com legendas</option><option value="{MOBILE.name}">Celular</option><option value="{FINAL[False].name}">Full HD sem legendas</option></select></nav><p><a href="Falas_Para_Gravar_Video_v9.txt">Falas com tempos</a> · <a href="Texto_Corrido_Para_Gravar_v9.txt">Texto para ler</a> · <a href="Legendas_Com_Apresentacao_v9.srt">SRT com abertura</a></p></main><script>const v=document.querySelector('video');document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{{v.currentTime=+b.dataset.t;v.play()}});document.querySelector('select').onchange=e=>{{const t=v.currentTime;v.src=e.target.value;v.onloadedmetadata=()=>v.currentTime=t}};</script></html>'''
    page=page.replace('<a href="Falas_Para_Gravar_Video_v9.txt">',
        '<a href="Falas_Para_Gravar_Video_v9.pdf">Falas em PDF</a> · <a href="Falas_Para_Gravar_Video_v9.txt">')
    player=OUT/'assistir_video_revisado_v9.html';player.write_text(page,encoding='utf-8')
    (ROOT/'ASSISTIR_VIDEO_REVISADO_V9.cmd').write_bytes(('@echo off\r\nstart "" "%~dp0'+str(player.relative_to(ROOT))+'"\r\n').encode('ascii'))

def mobile():
    progress('encoding_mobile')
    command([DEFAULT_FFMPEG,'-v','error','-y','-i',FINAL[True],'-vf','scale=1280:720,fps=24,tpad=stop_mode=clone:stop_duration=0.1',
      '-frames:v',13440,'-t',560,'-an','-c:v','libx264','-preset','medium','-crf','23','-profile:v','baseline','-level','3.1',
      '-pix_fmt','yuv420p','-threads','6','-movflags','+faststart',MOBILE])
    decoded=command([DEFAULT_FFMPEG,'-v','error','-nostats','-progress','pipe:1','-i',MOBILE,'-map','0:v:0','-f','null','-'])
    frames=[int(x)for x in re.findall(r'^frame=(\d+)$',decoded.stdout,re.M)]
    header=mp4_headers(MOBILE)
    if frames[-1]!=13440 or decoded.stderr.strip() or header['fps']!=24 or header['duration_seconds']!=560:raise ValueError('Mobile audit failed')
    return {'path':str(MOBILE.relative_to(ROOT)),'bytes':MOBILE.stat().st_size,'sha256':sha(MOBILE),
      'width':1280,'height':720,'fps':24,'frame_count':13440,'duration_seconds':560,'audio_tracks':0,
      'full_decode_errors':0,'codec':'H264 Baseline','client_playback_confirmed':False}
