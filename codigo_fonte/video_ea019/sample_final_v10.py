"""Extract review frames from the actual narrated exports, not source renders."""
import sys,math
from concurrent.futures import ThreadPoolExecutor
from montagem_v10_common import *
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
from PIL import Image,ImageDraw,ImageFont

if __name__=='__main__':
    timeline=read(OUT/'timeline_montagem_v10.json')
    target=OUT/'Video_TCC_Final_Somente_Voz_v10.mp4'
    qa=OUT/'verificacao_final';qa.mkdir(exist_ok=True)
    times=[(x['start']+x['end'])/2 for x in timeline['items']]
    times += [0.5,7,13,timeline['duration']-12,timeline['duration']-4,timeline['duration']-.25]
    for idx in [74,76,83]:
        x=next(x for x in timeline['items'] if x['kind']=='body'and x['index']==idx)
        times += [x['start']+x['duration']*.82]
    times=sorted(set(round(x,4)for x in times))
    def extract(t):
        p=qa/f't_{t:.4f}.png'
        run([FFMPEG,'-v','error','-y','-ss',f'{t:.6f}','-threads','2','-i',target,
            '-frames:v','1','-threads','2','-update','1',p])
        return {'time':t,'path':str(p.relative_to(ROOT)),'sha256':sha(p)}
    with ThreadPoolExecutor(max_workers=3) as pool:stills=list(pool.map(extract,times))
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20);sheets=[]
    for a in range(0,len(stills),12):
        group=stills[a:a+12];im=Image.new('RGB',(1920,388*math.ceil(len(group)/3)),(6,7,8));d=ImageDraw.Draw(im)
        for i,r in enumerate(group):
            x=i%3*640;y=i//3*388
            with Image.open(ROOT/r['path']) as frame:im.paste(frame.resize((640,360),Image.Resampling.LANCZOS),(x,y+28))
            t=r['time'];d.text((x+8,y),f'{int(t)//60}:{t%60:05.2f}',fill=(230,235,240),font=font)
        p=qa/f'contato_v10_{a//12+1}.png';im.save(p);sheets.append(str(p.relative_to(ROOT)))
    write(OUT/'amostras_exportacao_v10.json',{'video':str(target.relative_to(ROOT)),
        'video_sha256':sha(target),'stills':stills,'contact_sheets':sheets,'count':len(stills),
        'scope':'Sampled still-frame review, not full real-time playback'})
    print('V10_SAMPLES_READY',len(stills),len(sheets),flush=True)
