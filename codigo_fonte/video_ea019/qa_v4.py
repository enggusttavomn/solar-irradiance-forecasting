"""Composite actual subtitle timing on preflight stills, or contact final frames."""
import argparse
import json
from pathlib import Path
import re
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from compose_pilot import DEFAULT_FFMPEG,command
from overlays_v4 import write_v4_ass
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v4'

def main():
    p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');args=p.parse_args()
    source=OUT/('verificacao_final' if args.final else 'qa_3d')
    target=source if args.final else OUT/'qa_com_textos';target.mkdir(exist_ok=True)
    plan=json.loads((OUT/'plano_video_v4.json').read_text(encoding='utf-8'));starts={c['id']:c['start'] for c in plan['chapters']}
    manifest=json.loads((OUT/'manifesto_producao_v4.json').read_text(encoding='utf-8'))
    expected={c['id']:set(c['qa_times']) for c in manifest['chapters']}
    if not args.final:
        ass=OUT/'qa_legendas_v4.ass';report=write_v4_ass(ass)
        (OUT/'verificacao_textos_v4.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    records=[]
    for src in source.glob('cena_*_t*.png'):
        match=re.fullmatch(r'cena_(\d+)_t([\d_]+)\.png',src.name)
        if not match:continue
        chapter=int(match[1]);local=float(match[2].replace('_','.'));second=starts[chapter]+local;dst=target/src.name
        if local not in expected[chapter]:continue
        if not args.final:
            command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',src,'-vf',
              f'setpts=PTS+{second}/TB,ass={ass.relative_to(ROOT).as_posix()},setpts=PTS-STARTPTS','-frames:v','1','-update','1',dst])
        records.append((chapter,local,second,dst))
    records.sort();sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
    from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    contacts=[]
    for start in range(0,len(records),12):
        sheet=Image.new('RGB',(1920,930),'#07090D');draw=ImageDraw.Draw(sheet)
        for slot,(chapter,local,second,path) in enumerate(records[start:start+12]):
            x=slot%4*480;y=slot//4*310
            with Image.open(path) as im:
                assert im.size==(1920,1080),(path,im.size)
                sheet.paste(im.convert('RGB').resize((480,270),Image.Resampling.LANCZOS),(x,y+30))
            draw.text((x+12,y+3),f'{chapter:02d} · {second//60:.0f}:{second%60:04.1f} · local {local:g}s',font=font,fill='#A9B2BE')
        path=target/f'contato_{start//12+1:02d}.png';sheet.save(path);contacts.append(str(path))
    print(json.dumps({'frames':len(records),'contacts':contacts,'final':args.final},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
