"""Wait for the complete Arc render queue and prepare all reviewable outputs."""
import sys,time,subprocess
from pipeline_v9 import *
def contact():
    sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
    from PIL import Image,ImageDraw,ImageFont
    r=read(OUT/'verificacao_video_v9.json');paths=[ROOT/p for p in r['sampled_frames']]
    sheets=[];font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    for start in range(0,len(paths),12):
        subset=paths[start:start+12];sheet=Image.new('RGB',(1920,388*((len(subset)+2)//3)),(8,10,13));d=ImageDraw.Draw(sheet)
        for i,p in enumerate(subset):
            x=i%3*640;y=i//3*388
            with Image.open(p) as im:sheet.paste(im.resize((640,360),Image.Resampling.LANCZOS),(x,y+28))
            t=float(p.stem[2:].replace('_','.'));d.text((x+8,y),f'{int(t)//60}:{t%60:04.1f}',font=font,fill=(220,230,240))
        target=OUT/'verificacao_final'/f'contato_v9_{start//12+1}.png';sheet.save(target);sheets.append(str(target.relative_to(ROOT)))
    return sheets
def main():
    print('V9_WAITING_FOR_APPROVED_RENDERS',flush=True)
    while True:
        q=read(OUT/'fila_render_v9.json',{})
        if q.get('failed'):raise RuntimeError('Render queue failed '+str(q['failed']))
        if len(q.get('complete',[]))==9:break
        time.sleep(5)
    for name,spec in CHAPTERS.items():
        r=read(OUT/'cenas'/f'{name}_manifesto_v9.json')
        if not r['render_complete']:raise ValueError('Incomplete render '+name)
        if name!='resultados':
            key,values=current_sources(spec['module'])
            if r['source_fingerprint']!=key or r['source_hashes']!=values:raise ValueError('Changed source '+name)
    # Load speech/caption decisions only after rendering, so editorial timing
    # refinements made during the long GPU queue are included in the export.
    from compose_v9 import compose,mobile,progress
    compose();sheets=contact();phone=mobile()
    p=OUT/'verificacao_video_v9.json';r=read(p);r.update(mobile_preview=phone,contact_sheets=sheets)
    write_json(p,r)
    for script in ['verify_reused_results_v9.py','audit_delivery_v9.py']:
        result=subprocess.run([sys.executable,str(ROOT/'codigo_fonte/video_ea019'/script)],cwd=ROOT,
             capture_output=True,text=True,encoding='utf-8',errors='replace')
        if result.returncode:raise RuntimeError(script+'\n'+result.stdout[-6000:]+'\n'+result.stderr[-3000:])
        print('V9_CHECK_PASSED '+script,flush=True)
    progress('complete_pending_manual_visual_review',files=r['files'],mobile_preview=phone)
    print('V9_DELIVERY_READY_FOR_REVIEW',flush=True)
if __name__=='__main__':main()
