"""V13 picture-only revision: short black fades BEFORE global captions.

V12 has burned captions in its silent picture and cached chunks. Unchanged
chunks may be reused byte for byte; changed chunks must start from clean
original visuals and receive the same ASS only after picture transitions.
No audio, caption timestamps, shot timing, source speed or V12 file is changed.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json

import montagem_v10_common as common
from audit_delivery_v8 import mp4_headers

ROOT=common.ROOT
TMP=ROOT/'tmp/montagem_final_v13'
OUT=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v13'
V12=ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TIMELINE=V12/'timeline_montagem_v12.json'
PLAN=TMP/'visual_transition_plan_v13.json'
PICTURE=OUT/'Imagem_Final_Transicoes_1080p_v13.mp4'
CHUNKS=OUT/'cenas_com_transicoes'
FPS=30
read,write,sha,run=common.read,common.write,common.sha,common.run

# Incoming shot IDs at substantial changes of setting/representation/topic.
# 6+6frames for chapter changes; 4+4 for representation changes. No overlap,
# inserted frames, altered duration, or transition across the narration layer.
INCOMING={
 'sun_factory':6,
 'dashed_future':4,'photovoltaic_application':4,'three_models':6,
 'transformer_native':4,'informer_queries_intro':4,
 'same_input_three_models':4,'americas_counts':6,
 'nsrdb_satellite_atmosphere':4,'history_curve_reveal':4,
 'all_ten_distributions':4,'input_actual_history':6,'task_hourly':4,
 'initial_training_years':6,'quantization_introduction':6,
 'mae_vertical_distances':6,'mae_sum_and_28':4,
 'macro_equal_localities':4,'cumulative_72_steps':4,'hourly_results':6,
 'monthly_one_results':4,'compare_within_task':4,
 'monthly_locality_leaders':4,'quantization_reprise':6,
 'quantization_outcomes':4,'historical_setup':4,
 'historical_confounders':4,'precision_not_cost':4,
 'six_month_exploratory':4,'ending':6,
}


def absolute(value):
    path=Path(value)
    return path if path.is_absolute() else ROOT/path


def filter_path(path):
    value=path.resolve().relative_to(ROOT.resolve()).as_posix()
    if "'" in value or ':' in value:
        raise ValueError('Unsafe filter path')
    return "'"+value+"'"


def write_labels():
    """Screen-space leaders refer to the roof and the upright normal only.

    Hide before the source camera recedes so pointers never drift to a
    different geometric object. This is additional didactic annotation, not
    a correction of the scientifically correct horizontal-contribution voice.
    """
    label_path=TMP/'rotulos_superficie_normal_v13.ass'
    # Source18–24is the stable close view (output41.633–47.633). The roof
    # point is approximately960,825; the upright normal is near960,530.
    label_path.write_text('''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Label,Segoe UI,29,&H00E7D7A5,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,3,7,0,7,0,0,0,1
Style: Roof,Segoe UI,29,&H00FFFFFF,&H00FFFFFF,&H99000000,&H99000000,0,0,0,0,100,100,0,0,3,7,0,7,0,0,0,1
Style: Leader,Segoe UI,20,&H00E7D7A5,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:41.63,0:00:47.63,Label,,0,0,0,,{\\pos(1035,478)\\fad(100,180)}Normal à superfície\\N(vertical)
Dialogue: 0,0:00:41.63,0:00:47.63,Roof,,0,0,0,,{\\pos(1110,783)\\fad(100,180)}Superfície horizontal
Dialogue: 0,0:00:41.63,0:00:47.63,Leader,,0,0,0,,{\\pos(0,0)\\fad(100,180)\\p1}m 1020 529 l 972 529 l 972 527 l 1020 527 m 970 528 l 981 522 l 981 534
Dialogue: 0,0:00:41.63,0:00:47.63,Leader,,0,0,0,,{\\pos(0,0)\\fad(100,180)\\p1}m 1100 817 l 991 826 l 991 824 l 1100 815 m 981 826 l 994 819 l 995 830
''',encoding='utf-8-sig')
    return label_path


def prepare():
    timeline=read(TIMELINE)
    assert timeline['frames']==14718 and timeline['duration']==490.6
    assert len(INCOMING)==30
    TMP.mkdir(parents=True,exist_ok=True)
    OUT.mkdir(parents=True,exist_ok=True)
    labels=write_labels()
    items=[dict(item) for item in timeline['visual_items']]
    ids={item['id'] for item in items}
    assert set(INCOMING)<=ids
    boundaries=[]
    for i,item in enumerate(items):
        item['fade_in_frames']=INCOMING.get(item['id'],0)
        item['fade_out_frames']=INCOMING.get(items[i+1]['id'],0) if i+1<len(items) else 0
        item['add_geometry_labels']=item['id']=='horizontal_projection'
        item['needs_clean_source_encode']=bool(item['fade_in_frames'] or item['fade_out_frames'] or item['add_geometry_labels'])
        assert item['frames']>item['fade_in_frames']+item['fade_out_frames']+15
        if item['fade_in_frames']:
            n=item['fade_in_frames'];boundary=item['start_frame']
            boundaries.append({'outgoing':items[i-1]['id'],'incoming':item['id'],
              'boundary_frame':boundary,'boundary_seconds':boundary/FPS,
              'fade_out_first_frame':boundary-n,'fade_out_last_frame':boundary-1,
              'fade_in_first_frame':boundary,'fade_in_last_frame':boundary+n-1,
              'window_start':(boundary-n)/FPS,'window_end':(boundary+n)/FPS,
              'duration_seconds':2*n/FPS,'frames_each_side':n,
              'style':'short_fade_through_black_before_global_captions',
              'audio_untouched':True,'caption_layer_untouched':True})
    source_paths={item['source_path'] for item in items}
    plan={'version':13,'status':'reviewable_picture_transition_plan',
      'generated_utc':datetime.now(timezone.utc).isoformat(),
      'frames':14718,'fps':30,'duration':490.6,
      'visual_items':items,'boundaries':boundaries,'transition_count':len(boundaries),
      'timeline_v12_path':str(TIMELINE.relative_to(ROOT)),
      'timeline_v12_sha256':sha(TIMELINE),
      'global_ass_path':timeline['ass_path'],'global_ass_sha256':sha(absolute(timeline['ass_path'])),
      'geometry_labels_path':str(labels.relative_to(ROOT)),'geometry_labels_sha256':sha(labels),
      'source_hashes':{path:sha(absolute(path)) for path in source_paths},
      'clean_source_reencode_chunks':sum(item['needs_clean_source_encode'] for item in items),
      'byte_reused_v12_chunks':sum(not item['needs_clean_source_encode'] for item in items),
      'picture_output':str(PICTURE.relative_to(ROOT)),
      'audio_or_caption_timing_changed':False,'voice_processing_performed':False,
      'native_animation_speed':1,'transition_frames_inserted':0,
      'clean_master_note':'V12 silent picture has burned ASS. Re-encode affected chunks from clean original sources, fading before adding unchanged global ASS; reuse other V12 chunks byte for byte.',
      'geometry_annotation':'Normal label at(1035,478)beside the vertical axis; horizontal-surface label at(1110,783)points to roof/1m²near(960,825), never to the floating inclined DNI plane. Labels hide before the camera recedes.',
      'no_transition_at_microcuts':True,
    }
    write(PLAN,plan)
    print(json.dumps({key:plan[key] for key in ['status','transition_count','clean_source_reencode_chunks','byte_reused_v12_chunks','duration','frames']}),flush=True)
    return plan


def encode(item,plan):
    if not item['needs_clean_source_encode']:
        path=V12/'cenas_editadas'/(item['id']+'.mp4')
        assert path.is_file()
        return {'id':item['id'],'path':str(path.relative_to(ROOT)),
                'sha256':sha(path),'reused_v12_byte_for_byte':True,'frames':item['frames']}
    target=CHUNKS/(item['id']+'.mp4')
    cache=target.with_suffix('.json')
    source=absolute(item['source_path'])
    frames=int(item['frames']);duration=frames/FPS
    key={'source_sha256':plan['source_hashes'][item['source_path']],
         'item':item,'global_ass_sha256':plan['global_ass_sha256'],
         'labels_sha256':plan['geometry_labels_sha256'] if item['add_geometry_labels'] else None,
         'format':'v13_picture_fades_before_global_ass_qsv_icq18'}
    old=read(cache,{})
    if target.exists() and old.get('key')==key and old.get('sha256')==sha(target):
        return old
    if item['kind']=='ending':
        inputs=['-loop','1','-framerate',FPS,'-i',source]
        vf=("scale=2016:1134,crop=1920:1080:x='48+8*sin(t/8)':y='27+5*sin(t/11)',"
            f'fps=30,trim=end_frame={frames},setpts=PTS-STARTPTS')
    else:
        start=float(item['video_start']);native=float(item['video_end'])-start
        inputs=['-ss',f'{start:.8f}','-threads',2,'-i',source]
        padding=max(1.,duration-native+.10)
        vf=(f'trim=duration={native:.8f},setpts=PTS-STARTPTS,fps=30,'
            f'tpad=stop_mode=clone:stop_duration={padding:.8f},trim=end_frame={frames}')
    if item['fade_in_frames']:
        vf+=f",fade=t=in:s=0:n={item['fade_in_frames']}"
    if item['fade_out_frames']:
        n=item['fade_out_frames']
        vf+=f',fade=t=out:s={frames-n}:n={n}'
    vf+=f",setpts=PTS+{int(item['start_frame'])}/(30*TB)"
    if item['add_geometry_labels']:
        vf+=f",ass=filename={filter_path(absolute(plan['geometry_labels_path']))}"
    vf+=f",ass=filename={filter_path(absolute(plan['global_ass_path']))},setpts=PTS-STARTPTS"
    # Preserve only the pre-existing terminal/initial presentation fades.
    # New inter-scene fades are all before ASS, so captions never blink.
    if item['kind']=='intro':
        vf+=',fade=t=in:st=0:d=0.10'
    if item['kind']=='ending':
        vf+=f',fade=t=out:st={duration-.65:.6f}:d=0.65'
    vf+=',format=nv12'
    run([common.FFMPEG,'-v','error','-y',*inputs,'-vf',vf,'-an',
         '-frames:v',frames,'-r',FPS,'-fps_mode','cfr','-c:v','h264_qsv',
         '-global_quality',18,'-preset','medium','-look_ahead',0,'-profile:v','high',
         '-g',120,'-bf',3,'-video_track_timescale',15360,'-map_metadata',-1,
         '-movflags','+faststart',target])
    header=mp4_headers(target)
    assert header['frame_count']==frames and header['fps']==FPS
    assert header['width']==1920 and header['height']==1080
    record={'id':item['id'],'key':key,'path':str(target.relative_to(ROOT)),
            'sha256':sha(target),'frames':frames,'header':header,
            'reused_v12_byte_for_byte':False,'fades_before_captions':True}
    write(cache,record)
    return record


def render(plan):
    CHUNKS.mkdir(parents=True,exist_ok=True)
    results=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending={pool.submit(encode,item,plan):item['id'] for item in plan['visual_items']}
        for task in as_completed(pending):
            results.append(task.result())
            print(f'V13_PICTURE {len(results)}/{len(pending)} {pending[task]}',flush=True)
    byid={record['id']:absolute(record['path']) for record in results}
    listing=OUT/'concat_imagem_transicoes_v13.txt'
    listing.write_text(''.join("file '"+byid[item['id']].as_posix().replace("'","'\\''")+"'\n" for item in plan['visual_items']),encoding='utf-8')
    run([common.FFMPEG,'-v','error','-y','-f','concat','-safe',0,'-i',listing,
         '-map','0:v:0','-an','-c:v','copy','-map_metadata','-1','-movflags','+faststart',PICTURE])
    header=mp4_headers(PICTURE)
    assert header['frame_count']==14718 and header['fps']==30
    assert header['duration_seconds']==490.6
    assert sha(absolute(plan['global_ass_path']))==plan['global_ass_sha256']
    result={'version':13,'status':'V13_PICTURE_TRANSITIONS_READY',
      'path':str(PICTURE.relative_to(ROOT)),'sha256':sha(PICTURE),
      'frames':14718,'fps':30,'duration':490.6,'header':header,
      'transition_plan_path':str(PLAN.relative_to(ROOT)),'transition_plan_sha256':sha(PLAN),
      'global_ass_sha256':plan['global_ass_sha256'],'chunks':results,
      'audio_changed_by_picture_renderer':False,'caption_times_changed':False,
      'fades_applied_before_caption_layer':True,'native_animation_speed':1,
      'v12_files_modified':False,'encoder':'Intel Quick Sync h264_qsv'}
    write(OUT/'verificacao_imagem_transicoes_v13.json',result)
    print(json.dumps({k:result[k] for k in ['status','path','sha256','frames','duration']}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--render',action='store_true')
    args=parser.parse_args()
    plan=prepare()
    if args.render:
        render(plan)
