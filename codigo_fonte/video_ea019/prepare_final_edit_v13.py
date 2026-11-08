"""Remove the failed final attempt; preserve all approved body timing."""
from copy import deepcopy
from pathlib import Path
import re

from montagem_v10_common import ROOT, read, write, sha

OLD = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12'
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v13'
RATE, FPS, SPF = 48000, 30, 1600
FRAMES, DURATION = 14667, 488.9
SOURCE_START = 541.60


def ass_seconds(value):
    h, m, s = value.strip().split(':')
    return int(h)*3600 + int(m)*60 + float(s)


def ass_time(value):
    ticks = round(value * 100)
    return f'{ticks//360000}:{ticks//6000%60:02}:{ticks//100%60:02}.{ticks%100:02}'


def srt_time(value):
    ticks = round(value * 1000)
    return f'{ticks//3600000:02}:{ticks//60000%60:02}:{ticks//1000%60:02},{ticks%1000:03}'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    plan = deepcopy(read(OLD / 'voz_e_legendas_continuas_v12.json'))
    event = plan['events'][-1]
    assert event['kind'] == 'recorded_voice'
    assert abs(event['source_start'] - 539.89) < 1e-6
    delta_samples = round(SOURCE_START * RATE) - event['source_start_sample']
    delta = delta_samples / RATE
    assert delta_samples == 82080 and abs(delta - 1.71) < 1e-6
    old_event = deepcopy(event)
    event['source_start_sample'] += delta_samples
    event['source_start'] = SOURCE_START
    event['output_end_sample'] -= delta_samples
    event['global_end'] -= delta
    assert event['source_end_sample'] - event['source_start_sample'] == event['output_end_sample'] - event['output_start_sample']
    new_offset = event['global_start'] - SOURCE_START
    first_caption_start = 542.18 + new_offset
    captions = plan['captions']
    assert len(captions) == 112 and captions[107]['paragraph_index'] == 26
    protected_captions = deepcopy(captions[:107])
    for caption in captions[107:]:
        caption['start'] -= delta
        caption['end'] -= delta
    captions[107]['start'] = first_caption_start
    captions[107]['text'] = 'O projeto entrega uma comparação\nexperimental das três arquiteturas em dez'
    assert captions[:107] == protected_captions
    assert all(a['end'] <= b['start'] + .001 for a,b in zip(captions, captions[1:]))

    p = plan['paragraphs'][-1]
    for item in p['words']:
        token = item.get('canonical_token', '').lower()
        if token in {'o', 'projeto', 'entrega'} and item.get('canonical_local_token_index', 999) <= 2:
            source_times = {'o': (542.18,542.26), 'projeto': (542.26,542.48), 'entrega': (542.48,542.98)}[token]
            item['start'], item['end'] = source_times
            item['edited_start'], item['edited_end'] = [v + new_offset for v in source_times]
            item['v13_onset_evidence'] = 'RAW small micro-window plus quiet-valley boundary; keep later continuous take.'
        else:
            for key in ('edited_start', 'edited_end'):
                if key in item:
                    item[key] -= delta
    p.update(start=542.18, audio_start=542.18, edited_start=first_caption_start,
             edited_end=p['edited_end']-delta)
    p['issues'] = list(p.get('issues', [])) + ['V13 removes failed attempt540.52–541.45; source begins541.60 before the complete restart.']
    plan.update(version=13, status='final_edit_ready_for_natural_voice', frames=FRAMES,
                duration=DURATION, edited_main_seconds=plan['edited_main_seconds']-delta,
                audio_path='documentacao/relatorio_final_ea019/video/montagem_final_v13/audio/voz_original_natural_v13.wav')
    for key in ('whole_recording_cleanup_report', 'normalization_measured', 'normalization_filter', 'voice_sha256'):
        plan.pop(key, None)
    for interval in plan['cuts_source_seconds']:
        if abs(interval[1] - 539.89) < 1e-6:
            interval[1] = SOURCE_START
    plan['ending_retake_removed'] = {
        'previous_source_event': old_event,
        'later_continuous_take_source_start': SOURCE_START,
        'removed_source_interval': [539.89, SOURCE_START],
        'failed_attempt_voice_interval': [540.52, 541.45],
        'continuous_take_strong_onset': 542.27,
        'evidence': ['tmp/montagem_final_v13/qa_final_retakes_small_raw_micro.json',
                     'tmp/montagem_final_v13/qa_final_retakes_waveform.json',
                     'tmp/montagem_final_v13/audio/final_raw_medium_v13.json'],
        'body_timing_unchanged': True,
        'voice_synthesized_or_time_stretched': False,
        'audio_listening_performed': False,
    }
    plan['voice_processing_filters'] = []
    plan['voice_constant_gain_db'] = -1.
    write(OUT / 'voz_e_legendas_continuas_v13.json', plan)
    write(OUT / 'corte_encerramento_v13.json', plan['ending_retake_removed'])

    lines = (OLD / 'Legendas_Finais_v12.ass').read_text(encoding='utf-8-sig').splitlines()
    new_lines, caption_index = [], 0
    for line in lines:
        if not line.startswith('Dialogue:'):
            new_lines.append(line)
            continue
        fields = line.split(',', 9)
        if fields[3] == 'Caption':
            if caption_index >= 107:
                caption = captions[caption_index]
                fields[1], fields[2] = ass_time(caption['start']), ass_time(caption['end'])
                prefix = fields[9].split('}',1)[0] + '}'
                fields[9] = prefix + caption['text'].replace('\n', '\\N')
                line = ','.join(fields)
            caption_index += 1
        elif ass_seconds(fields[1]) >= 467.966:
            fields[1] = ass_time(max(first_caption_start, ass_seconds(fields[1]) - delta))
            fields[2] = ass_time(min(DURATION, ass_seconds(fields[2]) - delta))
            line = ','.join(fields)
        new_lines.append(line)
    assert caption_index == 112
    (OUT / 'Legendas_Finais_v13.ass').write_text('\n'.join(new_lines) + '\n', encoding='utf-8-sig')
    (OUT / 'Legendas_Finais_v13.srt').write_text('\n\n'.join(
        f'{i+1}\n{srt_time(c["start"])} --> {srt_time(c["end"])}\n{c["text"]}'
        for i,c in enumerate(captions)) + '\n', encoding='utf-8-sig')

    timeline = deepcopy(read(OLD / 'timeline_montagem_v12.json'))
    timeline.update(version=13, frames=FRAMES, duration=DURATION,
                    audio_path=plan['audio_path'],
                    ass_path='documentacao/relatorio_final_ea019/video/montagem_final_v13/Legendas_Finais_v13.ass',
                    srt_path='documentacao/relatorio_final_ea019/video/montagem_final_v13/Legendas_Finais_v13.srt')
    ending = timeline['visual_items'][-1]
    ending.update(frames=FRAMES-ending['start_frame'], end_frame=FRAMES,
                  end=DURATION, duration=(FRAMES-ending['start_frame'])/FPS,
                  video_end=(FRAMES-ending['start_frame'])/FPS)
    write(OUT / 'timeline_montagem_v13.json', timeline)
    write(OUT / 'revisao_edicao_final_v13.json', {
        'version':13, 'status':'ending_cut_and_captions_ready', 'frames':FRAMES,
        'duration':DURATION, 'caption_count':112, 'body_caption_events_preserved':107,
        'ending_cut_source':[539.89,SOURCE_START], 'duration_removed_from_audio':delta,
        'body_visual_start_frames_preserved':True, 'final_visual_tail_seconds':DURATION-captions[-1]['end'],
        'main_source_sha256':sha(Path('C:/Users/gusta/OneDrive/Documents/Sound Recordings/GRAVACAO.m4a')),
        'voice_plan_sha256':sha(OUT/'voz_e_legendas_continuas_v13.json'),
        'srt_sha256':sha(OUT/'Legendas_Finais_v13.srt'),
        'ass_sha256':sha(OUT/'Legendas_Finais_v13.ass'),
    })
    print(f'V13_EDIT_READY duration={DURATION} frames={FRAMES} removed_attempt={delta:.2f}s captions=112')


if __name__ == '__main__':
    main()
