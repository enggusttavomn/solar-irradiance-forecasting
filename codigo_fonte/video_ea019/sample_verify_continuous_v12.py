"""Sample the actual V12 export, including sequential native-motion comparisons."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from montagem_v10_common import ROOT, FFMPEG, read, write, run, sha

sys.path.insert(0, str(ROOT/'.venv/Lib/site-packages'))
import numpy as np
from PIL import Image, ImageDraw, ImageFont

OUT = ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TMP = ROOT/'tmp/montagem_final_v12'
QA = OUT/'verificacao_final'
VIDEO = OUT/'Video_TCC_Final_Continuo_Somente_Voz_v12.mp4'


def extract(source, seconds, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    run([FFMPEG,'-v','error','-y','-ss',f'{seconds:.8f}','-threads','2','-i',source,
         '-frames:v','1','-threads','2','-update','1',target])
    return target


def sheets(stills, prefix, title_key='label'):
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
    outputs=[]
    for at in range(0,len(stills),12):
        group=stills[at:at+12]
        canvas=Image.new('RGB',(1920,388*math.ceil(len(group)/3)),(5,6,7))
        draw=ImageDraw.Draw(canvas)
        for i,row in enumerate(group):
            x,y=i%3*640,i//3*388
            with Image.open(ROOT/row['path']) as im:
                canvas.paste(im.resize((640,360),Image.Resampling.LANCZOS),(x,y+28))
            draw.text((x+8,y+3),str(row.get(title_key,row['time'])),font=font,fill=(240,240,240))
        target=QA/f'{prefix}_{at//12+1:02d}.png'
        canvas.save(target)
        outputs.append({'path':target.relative_to(ROOT).as_posix(),'sha256':sha(target)})
    return outputs


def main():
    timeline=read(OUT/'timeline_montagem_v12.json')
    verification=read(OUT/'verificacao_video_final_v12.json')
    assert verification and VIDEO.exists(), 'Wait for completed production exports'
    assert sha(VIDEO)==verification['files'][0]['sha256']
    voice=read(OUT/'voz_e_legendas_continuas_v12.json')
    QA.mkdir(exist_ok=True)
    times=[.5,7.,13.,timeline['duration']-.25]
    times.extend([(x['start_frame']+x['end_frame'])/60 for x in timeline['visual_items']])
    times.extend([(x['edited_start']+x['edited_end'])/2 for x in voice['paragraphs']])
    times=sorted(set(round(t,5)for t in times if 0<=t<timeline['duration']))
    def still(t):
        target=extract(VIDEO,t,QA/'geral'/f't_{t:.5f}.png')
        return {'time':t,'label':f'{int(t)//60}:{t%60:05.2f}',
                'path':target.relative_to(ROOT).as_posix(),'sha256':sha(target)}
    with ThreadPoolExecutor(max_workers=3)as pool:
        general=list(pool.map(still,times))
    contact=sheets(general,'geral_contato_v12')
    write(OUT/'amostras_exportacao_v12.json',{
        'video':VIDEO.relative_to(ROOT).as_posix(),'video_sha256':sha(VIDEO),
        'stills':general,'contact_sheets':contact,'count':len(general),
        'scope':'Midpoint and paragraph coverage only, not full realtime playback.'})

    important=[(11,25),(56,103),(144,157),(305,327),(341,348),
               (363,396),(396,420),(460,468),(474,481)]
    tasks=[]
    for item in timeline['visual_items']:
        if item['kind']!='body':continue
        a,b=float(item['video_start']),float(item['video_end'])
        is_patch='matriz_historica_corrigida' in item['source_path']
        if not is_patch and not any(min(b,d)>max(a,c)for c,d in important):continue
        duration=b-a
        # Native construction order is checked at five successive instants.
        for i in range(5):
            local=min(duration-1/30,.15+(duration-.3)*i/4)
            local=max(0,local)
            output_time=item['start_frame']/30+local
            tasks.append((item,local,output_time))
    def temporal(task):
        item,local,t=task
        name=f'{item["id"]}_{local:.5f}'
        actual=extract(VIDEO,t,QA/'sequencias'/f'{name}.png')
        source=Path(item['source_path'])
        if not source.is_absolute():source=ROOT/source
        reference=extract(source,item['video_start']+local,TMP/'qa_source'/f'{name}.png')
        with Image.open(actual)as f,Image.open(reference)as r:
            av=np.array(f.convert('RGB'))[:840].astype(np.float32)
            rv=np.array(r.convert('RGB'))[:840].astype(np.float32)
        diff=av-rv
        mse=float(np.mean(diff*diff))
        foreground=(np.max(av,axis=2)>30)|(np.max(rv,axis=2)>30)
        fg_mae=float(np.mean(np.abs(diff)[foreground]))if np.any(foreground)else 0.
        return {'time':t,'source_time':item['video_start']+local,'item':item['id'],
                'label':f'{item["id"]} +{local:.2f}s | {int(t)//60}:{t%60:05.2f}',
                'path':actual.relative_to(ROOT).as_posix(),'sha256':sha(actual),
                'source_path':reference.relative_to(ROOT).as_posix(),'source_sha256':sha(reference),
                'rgb_mae':float(np.mean(np.abs(diff))),'foreground_rgb_mae':fg_mae,
                'psnr_db':10*math.log10(255*255/max(mse,1e-12)),
                'native_frame_correspondence_pass':fg_mae<5.0 and mse<12.0}
    with ThreadPoolExecutor(max_workers=3)as pool:
        temporal_stills=list(pool.map(temporal,tasks))
    temporal_stills.sort(key=lambda x:x['time'])
    temporal_sheets=sheets(temporal_stills,'sequencia_contato_v12')
    failures=[x for x in temporal_stills if not x['native_frame_correspondence_pass']]
    result={
        'version':12,'status':'automated_checks_complete_pending_manual_visual_review',
        'generated_utc':datetime.now(timezone.utc).isoformat(),
        'video_sha256':sha(VIDEO),'general_samples':len(general),
        'temporal_samples':len(temporal_stills),'temporal_items':len(set(x['item']for x in temporal_stills)),
        'source_frame_comparison_failures':failures,
        'all_sampled_native_frames_correspond':not failures,
        'temporal_stills':temporal_stills,'temporal_contact_sheets':temporal_sheets,
        'general_contact_sheets':contact,'manual_general_review_passed':False,
        'manual_sequence_review_passed':False,'audio_listening_performed':False,
        'full_realtime_playback_reviewed':False,
    }
    write(OUT/'verificacao_amostral_continua_v12.json',result)
    print(json.dumps({'general_samples':len(general),'general_sheets':len(contact),
                      'temporal_samples':len(temporal_stills),'temporal_sheets':len(temporal_sheets),
                      'native_comparison_failures':len(failures)}),flush=True)


if __name__=='__main__':
    main()
