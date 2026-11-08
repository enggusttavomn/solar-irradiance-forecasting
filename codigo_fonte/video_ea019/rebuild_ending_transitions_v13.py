"""Replace only the final V13 factory chunk after the recorded retake cut.

All seventy existing body chunks are verified and reused byte for byte.
New global caption events before the factory must match their old version.
"""
from pathlib import Path
import argparse
import json

import prepare_visual_transitions_v13 as visual
from audit_delivery_v8 import mp4_headers

ROOT=visual.ROOT


def caption_body(path,limit):
    text=path.read_text(encoding='utf-8-sig')
    # Metadata titles/version comments can change without changing rendering.
    # Fonts/styles, canvas geometry and ASS layout options must stay equal.
    header=[line for line in text.split('[Events]',1)[0].splitlines()
            if line.startswith(('Style:','PlayResX:','PlayResY:',
                                'ScaledBorderAndShadow:','WrapStyle:',
                                'Collisions:','Timer:','YCbCr Matrix:'))]
    rows=[]
    for line in text.splitlines():
        if line.startswith('Dialogue:'):
            fields=line.split(',',9)
            h,m,s=fields[1].strip().split(':')
            start=int(h)*3600+int(m)*60+float(s)
            if start<limit:
                rows.append(line)
    return header,rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ass',required=True)
    parser.add_argument('--frames',required=True,type=int)
    args=parser.parse_args()
    plan=visual.read(visual.PLAN)
    old_manifest=visual.read(visual.OUT/'verificacao_imagem_transicoes_v13.json')
    new_ass=visual.absolute(args.ass)
    assert new_ass.is_file()
    ending=dict(plan['visual_items'][-1])
    assert ending['id']=='ending' and ending['start_frame']==14039
    assert args.frames>ending['start_frame']+30
    old_ass=visual.absolute(plan['global_ass_path'])
    assert caption_body(old_ass,ending['start_frame']/30)==caption_body(new_ass,ending['start_frame']/30), 'Body caption events/styles changed; cannot reuse baked body chunks.'
    before={item['id']:item for item in old_manifest['chunks']}
    body=[item for item in plan['visual_items'] if item['id']!='ending']
    assert len(body)==70
    for item in body:
        rec=before[item['id']]
        assert visual.sha(visual.absolute(rec['path']))==rec['sha256'],item['id']
    ending['frames']=args.frames-ending['start_frame']
    ending['end_frame']=args.frames
    ending['duration']=ending['frames']/30
    ending['video_end']=ending['duration']
    ending['end']=args.frames/30
    ending['needs_clean_source_encode']=True
    plan['visual_items'][-1]=ending
    plan['frames']=args.frames
    plan['duration']=args.frames/30
    plan['global_ass_path']=str(new_ass.relative_to(ROOT))
    plan['global_ass_sha256']=visual.sha(new_ass)
    plan['body_chunks_preserved_byte_for_byte']=70
    plan['ending_only_retake_adjustment']={'old_total_frames':old_manifest['frames'],
        'new_total_frames':args.frames,'new_factory_frames':ending['frames'],
        'factory_start_frame_unchanged':ending['start_frame'],
        'body_caption_events_and_style_identical':True,
        'reason':'Remove the incomplete spoken final attempt; keep the later continuous take and a short balanced visual tail.'}
    record=visual.encode(ending,plan)
    records=[before[item['id']] for item in body]+[record]
    byid={item['id']:visual.absolute(item['path']) for item in records}
    listing=visual.OUT/'concat_imagem_transicoes_v13.txt'
    listing.write_text(''.join("file '"+byid[item['id']].as_posix().replace("'","'\\''")+"'\n" for item in plan['visual_items']),encoding='utf-8')
    visual.run([visual.common.FFMPEG,'-v','error','-y','-f','concat','-safe',0,'-i',listing,
       '-map','0:v:0','-an','-c:v','copy','-map_metadata','-1','-movflags','+faststart',visual.PICTURE])
    header=mp4_headers(visual.PICTURE)
    assert header['frame_count']==args.frames and header['fps']==30
    assert abs(header['duration_seconds']-args.frames/30)<1e-6
    for item in body:
        rec=before[item['id']]
        assert visual.sha(visual.absolute(rec['path']))==rec['sha256']
    visual.write(visual.PLAN,plan)
    result=dict(old_manifest)
    result.update({'status':'V13_PICTURE_TRANSITIONS_FINAL_ENDING_READY',
      'sha256':visual.sha(visual.PICTURE),'frames':args.frames,'duration':args.frames/30,
      'header':header,'global_ass_sha256':plan['global_ass_sha256'],
      'transition_plan_sha256':visual.sha(visual.PLAN),'chunks':records,
      'body_chunks_preserved_byte_for_byte':70,
      'body_caption_events_and_style_identical':True,
      'ending_only_retake_adjustment':plan['ending_only_retake_adjustment']})
    visual.write(visual.OUT/'verificacao_imagem_transicoes_v13.json',result)
    print(json.dumps({k:result[k] for k in ['status','path','sha256','frames','duration','body_chunks_preserved_byte_for_byte']}),flush=True)


if __name__=='__main__':
    main()
