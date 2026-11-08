"""Build one contact sheet for the sixteen sampled V6 phases."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'.venv/Lib/site-packages'))
from PIL import Image,ImageDraw,ImageFont

OUT=ROOT/'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'


def main():
    p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');args=p.parse_args()
    manifest=json.loads((OUT/'manifesto_intro_v6.json').read_text(encoding='utf-8'))
    folder=OUT/('verificacao_final' if args.final else 'qa_com_textos')
    canvas=Image.new('RGB',(1920,4*300),'#090b0d')
    draw=ImageDraw.Draw(canvas);font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18)
    for i,t in enumerate(manifest['qa_times']):
        image=Image.open(folder/('t_'+str(t).replace('.','_')+'.png')).convert('RGB')
        image.thumbnail((480,270),Image.Resampling.LANCZOS)
        x,y=i%4*480,i//4*300
        canvas.paste(image,(x,y+30))
        draw.text((x+12,y+3),str(t)+' s',font=font,fill='#BFCBD5')
    path=folder/'contato_v6.png';canvas.save(path)
    print(path)


if __name__=='__main__':main()
