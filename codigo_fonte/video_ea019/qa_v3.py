"""Compor amostras com os mesmos textos usados no filme final."""
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from compose_pilot import DEFAULT_FFMPEG,command

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v3'


def main():
    manifest=json.loads((OUT/'manifesto_producao_v3.json').read_text(encoding='utf-8'))
    starts={part['id']:part['start_seconds'] for part in manifest['chapters']}
    qa=OUT/'qa_com_textos'
    qa.mkdir(exist_ok=True)
    ass=(OUT/'textos_com_legendas.ass').relative_to(ROOT).as_posix()
    images=[]
    for source in sorted((OUT/'qa_3d').glob('cena_*_t*.png')):
        match=re.fullmatch(r'cena_(\d+)_t([\d_]+)\.png',source.name)
        if not match:
            continue
        chapter=int(match[1]); second=float(match[2].replace('_','.'))
        global_second=starts[chapter]+second
        target=qa/source.name
        command([DEFAULT_FFMPEG,'-hide_banner','-loglevel','error','-y','-i',source,
                 '-vf',f'setpts=PTS+{global_second}/TB,ass={ass},setpts=PTS-STARTPTS',
                 '-frames:v','1','-update','1',target])
        images.append((target,chapter,global_second))
    sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
    from PIL import Image,ImageDraw,ImageFont
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    sheets=[]
    for start in range(0,len(images),12):
        page=Image.new('RGB',(1920,930),'#07090D')
        draw=ImageDraw.Draw(page)
        for i,(path,chapter,second) in enumerate(images[start:start+12]):
            x=(i%4)*480;y=(i//4)*310
            im=Image.open(path).convert('RGB').resize((480,270),Image.Resampling.LANCZOS)
            page.paste(im,(x,y+30))
            draw.text((x+12,y+3),f'C{chapter:02d}  |  {int(second)//60}:{second%60:04.1f}',font=font,fill='#A9B2BE')
        target=qa/f'contato_{start//12+1:02d}.png'
        page.save(target)
        sheets.append(str(target))
    print(json.dumps({'qa_frames':len(images),'contact_sheets':sheets},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
