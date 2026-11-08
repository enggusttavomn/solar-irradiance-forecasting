"""Caption and short-label composition for the V5 natural-material revision."""
import json
from pathlib import Path
from overlays_v4 import OverlayV4
from overlays import Cue

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'documentacao/relatorio_final_ea019/video/completo_v5'

def write_v5_ass(path,include_captions=True):
    plan=json.loads((OUT/'plano_video_v5.json').read_text(encoding='utf-8'))
    overlay=OverlayV4(plan)
    for chapter in plan['chapters']:
        overlay.shot=f'chapter_{chapter["id"]:02d}'
        for event in chapter['label_events']:
            overlay.text(event['start'],event['end'],event['text'],x=event['x'],y=event['y'],
              size=event['size'],color=event['color'],align=event['align'],available=event['available'],
              minimum=30,fade=140,role='label')
    if include_captions:
        for cue in plan['cues']:
            overlay.shot=f'chapter_{cue["chapter"]:02d}'
            overlay.caption(Cue(cue['start'],cue['end'],cue['text']))
    report=overlay.write(path)
    report['version']='v5';report['source_plan']=str(OUT/'plano_video_v5.json')
    return report
