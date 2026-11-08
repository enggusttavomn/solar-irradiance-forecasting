"""Edit the continuous recording by PCM samples; captions follow actual words."""
from array import array
from bisect import bisect_right
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import textwrap
import wave

from montagem_v10_common import ROOT, FFMPEG, read, write, run, sha
import align_narration_v12 as alignment_api

OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TMP = ROOT / 'tmp/montagem_final_v12'
RATE, FPS, SPF = 48000, 30, 1600
FADE = 336  # 7ms at edit joins; speech interiors are preserved.


def rel(path):
    return path.relative_to(ROOT).as_posix()


def pcm(path):
    with wave.open(str(path), 'rb') as f:
        assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (RATE, 1, 2)
        return array('h', f.readframes(f.getnframes()))


def save_pcm(path, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(RATE); f.writeframes(values.tobytes())


def merge(bounds):
    out = []
    for a, b in sorted(bounds):
        if b <= a:
            continue
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def complement(bounds, a, b):
    result, cursor = [], a
    for x, y in bounds:
        if y <= a or x >= b:
            continue
        x, y = max(x, a), min(y, b)
        if cursor < x:
            result.append([cursor, x])
        cursor = max(cursor, y)
    if cursor < b:
        result.append([cursor, b])
    return result


def main():
    data = read(TMP / 'audio/paragraph_alignment_v12.json')
    manifest = read(TMP / 'audio/retakes_review_v12.json')
    words = [w for w in data['observed_words'] if w['end'] > w['start'] and
             not any(w['start'] < b-.001 and w['end'] > a+.001 for a,b in manifest['discard_intervals'])]
    words.sort(key=lambda w: (w['start'], w['end']))
    clean_path = OUT / 'audio/gravacao_limpa_integral_48k.wav'
    clean = pcm(clean_path)
    assert len(clean) == 27823104
    intro_path = ROOT / 'tmp/montagem_final_v10/voice_pcm/apresentacao_normalizado_48k.wav'
    intro = pcm(intro_path)[:424*SPF]
    assert len(intro) == 424*SPF

    # Only long recording gaps are shortened. Existing breaths and normal
    # clause-to-clause pauses stay intact; key results get local observation time.
    cuts = [list(v) for v in manifest['discard_intervals']]
    gap_edits = []
    for previous, following in zip(words, words[1:]):
        a, b = float(previous['end']), float(following['start'])
        if b-a > 3.0:
            keep = 1.5 if any(abs(a-v)<.3 for v in [316.90, 442.17]) else 1.0
            cuts.append([a+keep/2, b-keep/2])
            gap_edits.append({'source_gap':[a,b], 'retained_seconds':keep, 'reason':'long quiet recording gap / discarded attempt'})
    cuts = merge(cuts)
    first, last = .39, 561.26
    kept = complement(cuts, first, last)

    # Point pauses while a visible calculation/convergence/scan completes.
    # No silence is inserted at the old 88 phase boundaries.
    additions = [(168.20, .65, 'histogram percentage'), (365.35, .80, 'MAE28 result'),
                 (368.52, 2.00, 'forecast converges to zero'), (389.10, 2.00, 'complete72-hour scan')]
    events, edited, cursor = [], array('h'), 0
    for a,b in kept:
        points = [(t, seconds, reason) for t,seconds,reason in additions if a < t < b]
        at = a
        for end, seconds, reason in [*points, (b, 0, '')]:
            sa, sb = round(at*RATE), round(end*RATE)
            clip = clean[sa:sb]
            fade = min(FADE, len(clip)//2)
            for i in range(fade):
                gain = i/max(1,fade-1)
                clip[i] = round(clip[i]*gain); clip[-1-i] = round(clip[-1-i]*gain)
            edited.extend(clip)
            events.append({'kind':'recorded_voice','source_start_sample':sa,'source_end_sample':sb,
                           'source_start':sa/RATE,'source_end':sb/RATE,
                           'output_start_sample':cursor,'output_end_sample':cursor+len(clip)})
            cursor += len(clip)
            if seconds:
                count = round(seconds*RATE)
                edited.extend(array('h',[0])*count)
                events.append({'kind':'observation_pause','seconds':seconds,'reason':reason,
                               'output_start_sample':cursor,'output_end_sample':cursor+count})
                cursor += count
            at = end
    assert len(edited) == cursor
    raw_edited = OUT / 'audio/narracao_continua_editada_48k.wav'
    save_pcm(raw_edited, edited)

    def mapped(seconds):
        source = round(seconds*RATE)
        for event in events:
            if event['kind']=='recorded_voice' and event['source_start_sample'] <= source <= event['source_end_sample']:
                return (event['output_start_sample'] + source-event['source_start_sample'])/RATE
        # An ASR boundary can lie a few ms inside the deliberately removed valley.
        anchors = [(abs(source-e[key]), e[out]) for e in events if e['kind']=='recorded_voice'
                   for key,out in [('source_start_sample','output_start_sample'),('source_end_sample','output_end_sample')]]
        distance, where = min(anchors)
        if distance > RATE*.12:
            raise ValueError(f'Word boundary inside a removed interval: {seconds} ({distance/RATE:.3f}s)')
        return where/RATE

    # Whole-track normalization avoids per-sentence volume pumping.
    loud = run([FFMPEG,'-hide_banner','-nostats','-i',raw_edited,'-af',
                'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'])
    norm = json.loads(re.findall(r'\{\s*"input_i".*?\}',loud.stderr,re.S)[-1])
    normalized_path = OUT / 'audio/narracao_continua_normalizada_48k.wav'
    nf = ('loudnorm=I=-16:TP=-1.5:LRA=11:linear=true:'
          f"measured_I={norm['input_i']}:measured_TP={norm['input_tp']}:measured_LRA={norm['input_lra']}:"
          f"measured_thresh={norm['input_thresh']}:offset={norm['target_offset']},aresample=48000,"
          f'apad=whole_len={cursor},atrim=end_sample={cursor},asetpts=PTS-STARTPTS')
    run([FFMPEG,'-v','error','-y','-i',raw_edited,'-af',nf,'-ar',RATE,'-ac',1,'-c:a','pcm_s16le',normalized_path])
    normalized = pcm(normalized_path)
    assert len(normalized) == cursor
    final_tail = round(1.25*RATE)
    total_frames = math.ceil((len(intro)+len(normalized)+final_tail)/SPF)
    final_pcm = intro + normalized + array('h',[0])*(total_frames*SPF-len(intro)-len(normalized))
    voice = OUT / 'audio/voz_completa_continua_v12.wav'
    save_pcm(voice, final_pcm)
    offset = len(intro)/RATE
    paragraphs = []
    captions = []
    old_intro = read(ROOT/'documentacao/relatorio_final_ea019/video/montagem_final_v11/timeline_montagem_v11.json')['items'][0]
    captions.extend([dict(c,kind='intro') for c in old_intro['cues']])
    for paragraph in data['paragraphs']:
        row = deepcopy(paragraph)
        row['edited_start'] = mapped(row['start']) + offset
        row['edited_end'] = mapped(row['end']) + offset
        for item in row['words']:
            item['edited_start'] = mapped(item['start']) + offset
            item['edited_end'] = mapped(item['end']) + offset
        paragraphs.append(row)

        # Canonical orthography follows independently checked words; the one
        # incorrect numerical clause was explicitly removed from both streams.
        units, ref_position = [], row['reference_token_start']
        lookup = {w['canonical_ref_index']: w for w in row['words']}
        # The final paragraph's concise caption uses the same spoken order.
        canonical_units = re.findall(r'\S+', row['text'])
        for token in canonical_units:
            count = len(alignment_api.tokens(token))
            anchors = [lookup[j] for j in range(ref_position,ref_position+count) if j in lookup]
            units.append({'text':token,'start':min([w['edited_start'] for w in anchors],default=None),
                          'end':max([w['edited_end'] for w in anchors],default=None)})
            ref_position += count
        for i,u in enumerate(units):
            if u['start'] is None:
                previous = next((x for x in reversed(units[:i]) if x['end'] is not None),None)
                following = next((x for x in units[i+1:] if x['start'] is not None),None)
                u['start'] = previous['end'] if previous else row['edited_start']
                u['end'] = following['start'] if following else row['edited_end']
        # Remove only the uncertain/redundant article and noun in the tail's
        # caption; all audio remains the user's actual complete final take.
        if row['index']==26:
            if units[0]['text']=='O': units=units[1:]
        batch=[]
        for unit in units:
            candidate=' '.join([x['text']for x in batch]+[unit['text']])
            lines=textwrap.wrap(candidate,width=42,break_long_words=False,break_on_hyphens=False)
            if batch and (len(lines)>2 or (unit['end']-batch[0]['start']>5.4 and len(batch)>=5)):
                captions.append({'start':batch[0]['start'],'end':max(batch[-1]['end'],batch[0]['start']+.3)+.05,
                                 'text':'\n'.join(textwrap.wrap(' '.join(x['text']for x in batch),width=42,break_long_words=False,break_on_hyphens=False)),
                                 'kind':'body','paragraph_index':row['index']})
                batch=[]
            batch.append(unit)
        if batch:
            captions.append({'start':batch[0]['start'],'end':max(batch[-1]['end'],batch[0]['start']+.3)+.05,
                             'text':'\n'.join(textwrap.wrap(' '.join(x['text']for x in batch),width=42,break_long_words=False,break_on_hyphens=False)),
                             'kind':'body','paragraph_index':row['index']})
    for i,c in enumerate(captions):
        if i+1<len(captions): c['end']=min(c['end'],captions[i+1]['start'])
        assert c['start']<c['end'],c
        assert len(c['text'].splitlines())<=2
    for event in events:
        event['global_start'] = offset + event['output_start_sample']/RATE
        event['global_end'] = offset + event['output_end_sample']/RATE
    result = {'version':12,'status':'continuous_voice_ready_for_visual_assembly','frames':total_frames,
              'duration':total_frames/FPS,'intro_duration':offset,'audio_path':rel(voice),
              'paragraphs':paragraphs,'captions':captions,'events':events,'cuts_source_seconds':cuts,
              'gap_edits':gap_edits,'inserted_observation_pauses':additions,
              'original_source_duration':579.648,'edited_main_seconds':cursor/RATE,
              'voice_time_stretch_used':False,'speech_synthesis_used':False,
              'whole_recording_cleanup_report':rel(OUT/'audio/limpeza_voz_v12.json'),
              'normalization_measured':norm,'normalization_filter':nf,
              'retake_manifest_sha256':sha(TMP/'audio/retakes_review_v12.json'),
              'voice_sha256':sha(voice),'new_recording_used':True,
              'incorrect_numeric_clause_removed':True,'six_month_plot_value_remains':'13,67 W/m²'}
    write(OUT/'voz_e_legendas_continuas_v12.json',result)
    print(json.dumps({'status':result['status'],'duration':result['duration'],
                      'edited_main_seconds':result['edited_main_seconds'],'captions':len(captions),
                      'events':len(events),'gaps_shortened':len(gap_edits)},ensure_ascii=True),flush=True)


if __name__=='__main__':
    main()
