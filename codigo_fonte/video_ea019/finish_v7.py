"""Wait for final chapter renders, export, create mobile copy and review contact."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib
import json
import re
import subprocess
import sys
import time
from compose_v7 import OUT,ROOT,CHAPTERS,DURATION,compose,progress
from compose_pilot import DEFAULT_FFMPEG,command

def ready():
    for name,start,duration in CHAPTERS:
        p=OUT/'cenas'/f'{name}_manifesto_v7.json'
        if not p.exists():return False
        try:r=json.loads(p.read_text(encoding='utf-8'))
        except json.JSONDecodeError:return False
        if not r.get('render_complete') or r.get('resolution_percentage')!=100:return False
    return True

def contact():
    sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
    from PIL import Image,ImageDraw,ImageFont
    qa=OUT/'verificacao_final'
    files=sorted(qa.glob('t_*.png'),key=lambda p:float(p.stem[2:].replace('_','.')))
    width,height=480,292
    image=Image.new('RGB',(width*4,height*((len(files)+3)//4)),(9,11,13));d=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
    for i,p in enumerate(files):
        x=i%4*width;y=i//4*height
        with Image.open(p) as src:
            if src.size!=(1920,1080):raise ValueError('Sample resolution mismatch')
            image.paste(src.resize((480,270),Image.Resampling.LANCZOS),(x,y+22))
        t=float(p.stem[2:].replace('_','.'));d.text((x+8,y),f'{int(t)//60}:{t%60:04.1f}',font=font,fill=(210,222,230))
    target=qa/'contato_v7.png';image.save(target);return str(target)

def mobile():
    target=OUT/'Video_GHI_ate_Plano22_para_celular_v7.mp4'
    source=OUT/'Video_GHI_Inicio_ate_Plano22_com_legendas_v7.mp4'
    command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',source,
             '-vf','scale=1280:720,fps=24,tpad=stop_mode=clone:stop_duration=0.1',
             '-frames:v',DURATION*24,'-t',DURATION,'-an','-c:v','libx264','-preset','medium',
             '-crf','23','-profile:v','baseline','-level','3.1','-pix_fmt','yuv420p','-threads','6','-movflags','+faststart',target])
    probe=subprocess.run([str(DEFAULT_FFMPEG),'-hide_banner','-i',str(target)],capture_output=True,text=True,encoding='utf-8',errors='replace').stderr
    if '1280x720' not in probe or '24 fps' not in probe or 'Duration: 00:03:44.00' not in probe or 'Audio:' in probe:raise ValueError('Mobile metadata differs: '+probe)
    dec=command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-nostats','-progress','pipe:1','-i',target,'-map','0:v:0','-f','null','-'])
    frames=[int(v) for v in re.findall(r'^frame=(\d+)$',dec.stdout,re.M)]
    if not frames or frames[-1]!=DURATION*24 or dec.stderr.strip():raise ValueError('Mobile decode failed')
    with target.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(target.relative_to(ROOT)),'bytes':target.stat().st_size,'sha256':digest,
            'width':1280,'height':720,'fps':24,'frame_count':frames[-1],'duration_seconds':DURATION,
            'codec':'H.264 Baseline','audio_tracks':0,'full_decode_errors':0,'client_playback_confirmed':False}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    while not ready():
        time.sleep(5)
    compose();sheet=contact();progress('encoding_mobile')
    phone=mobile()
    p=OUT/'verificacao_video_v7.json';r=json.loads(p.read_text(encoding='utf-8'))
    r['mobile_preview']=phone;r['contact_sheet']=sheet
    r['completed_utc']=datetime.now(timezone.utc).isoformat()
    p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    progress('complete_pending_manual_visual_review',duration_seconds=DURATION,files=r['files'],mobile_preview=phone)
    print('V7_DELIVERY_READY_FOR_MANUAL_REVIEW',flush=True)

if __name__=='__main__':main()
