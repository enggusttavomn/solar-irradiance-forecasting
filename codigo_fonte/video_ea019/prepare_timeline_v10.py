"""Build the frame-exact V10 edit plan, original-voice PCM and final captions.

No video encoding, speech synthesis, voice stretching or music mixing occurs here.
All cuts address decoded PCM samples, never compressed-file seek timestamps.
"""
from __future__ import annotations

from array import array
from copy import deepcopy
import json
import math
from pathlib import Path
import re
import textwrap
import wave

from montagem_v10_common import ROOT, OUT, TMP, BASE, PATCH, INTRO, FACTORY, FPS, read, write, sha

RATE = 48000
SAMPLES_PER_FRAME = RATE // FPS
FADE_SAMPLES = 240  # 5 ms
PRE_ROLL = .20
POST_ROLL = .25
SHORT_GAP = 1.20
INTRO_FRAMES = 424
NUMERIC_MIN_SECONDS = 4.80
VOICE = OUT / 'audio/voz_montada_v10.wav'
TIMELINE = OUT / 'timeline_montagem_v10.json'
SRT = OUT / 'Legendas_Finais_v10.srt'
ASS = OUT / 'Legendas_Finais_v10.ass'
REPORT = OUT / 'relatorio_edicao_v10.json'
APPROVED_INTRO_TEXT = (
    'Olá, eu sou Gustavo, aluno da Engenharia Elétrica da Unicamp. '
    'Neste trabalho, comparo LSTM, Transformer e Informer na previsão da irradiância solar '
    'em localidades ligadas à fabricação de veículos elétricos.'
)
APPROVED_ENDING_TEXT = (
    'Este projeto comparou três arquiteturas em dez localidades, sob o mesmo protocolo de avaliação. '
    'Nos horizontes completos, o Transformer teve menor erro nas previsões horárias e diárias, '
    'e o Informer liderou nas tarefas mensais. '
    'Esses resultados oferecem uma base experimental para orientar a escolha dos modelos '
    'na previsão da irradiância solar.'
)


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def seconds_samples(seconds: float) -> int:
    return round(seconds * RATE)


def frame_count(seconds: float) -> int:
    return math.ceil(seconds * FPS - 1e-8)


def load_pcm(path: Path) -> array:
    with wave.open(str(path), 'rb') as f:
        assert (f.getframerate(), f.getnchannels(), f.getsampwidth()) == (RATE, 1, 2)
        return array('h', f.readframes(f.getnframes()))


def flatten_words(record: dict) -> list[dict]:
    return [dict(w, index=i) for i, w in enumerate(w for s in record['segments'] for w in s.get('words', []))]


def chunks(text: str) -> list[str]:
    lines = textwrap.wrap(text, width=42, break_long_words=False, break_on_hyphens=False)
    if len(lines) == 3:
        return [lines[0], '\n'.join(lines[1:])]
    return ['\n'.join(lines[i:i + 2]) for i in range(0, len(lines), 2)]


def weight(text: str) -> int:
    return max(1, len(re.findall(r'\w+', text, flags=re.UNICODE)))


def make_cues(text: str, speech_start: float, speech_end: float, cut_start: float,
              duration: float, source_words: list[dict]) -> list[dict]:
    """Canonical words, with chunk changes anchored to recorded word onsets."""
    parts = chunks(text)
    if not parts:
        return []
    active_start = max(0., speech_start - cut_start)
    active_end = min(duration, speech_end - cut_start + .10)
    observations = [w for w in source_words if w['end'] > speech_start - .005 and w['start'] < speech_end + .005]
    boundaries = [active_start]
    total_weight = sum(weight(part) for part in parts)
    cumulative = 0
    for part in parts[:-1]:
        cumulative += weight(part)
        fraction = cumulative / total_weight
        if observations:
            position = min(len(observations) - 1, max(1, round(len(observations) * fraction)))
            anchor = observations[position]['start'] - cut_start
        else:
            anchor = active_start + (active_end - active_start) * fraction
        # Preserve word anchors unless they would create unreadable fragments.
        minimum = boundaries[-1] + .65
        maximum = active_end - .65 * (len(parts) - len(boundaries))
        if minimum > maximum:
            anchor = active_start + (active_end - active_start) * fraction
        else:
            anchor = min(maximum, max(minimum, anchor))
        boundaries.append(anchor)
    boundaries.append(active_end)
    return [{'start': round(a, 6), 'end': round(b, 6), 'text': part}
            for a, b, part in zip(boundaries, boundaries[1:], parts)]


def timing_string(seconds: float, *, ass: bool = False) -> str:
    scale = 100 if ass else 1000
    value = round(seconds * scale)
    h, remainder = divmod(value, 3600 * scale)
    m, remainder = divmod(remainder, 60 * scale)
    s, fraction = divmod(remainder, scale)
    return f'{h}:{m:02d}:{s:02d}.{fraction:02d}' if ass else f'{h:02d}:{m:02d}:{s:02d},{fraction:03d}'


def write_captions(items: list[dict]) -> dict:
    events = []
    for item in items:
        for cue in item['cues']:
            events.append(dict(cue, start=item['start'] + cue['start'],
                               end=item['start'] + cue['end'], item=item['id'], kind=item['kind']))
    for index, event in enumerate(events):
        assert event['start'] < event['end']
        assert index == 0 or event['start'] >= events[index - 1]['end'] - 1e-6
        assert len(event['text'].splitlines()) <= 2
        assert max(map(len, event['text'].splitlines())) <= 42
    SRT.write_text('\n\n'.join(
        f"{i}\n{timing_string(c['start'])} --> {timing_string(c['end'])}\n{c['text']}"
        for i, c in enumerate(events, 1)) + '\n', encoding='utf-8-sig')
    styles = '''[Script Info]
Title: EA019 final recorded narration V10
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes
WrapStyle: 2
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Segoe UI,44,&H00FBF6F3,&H00FFFFFF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,3,12,0,2,110,110,80,1
Style: Intro,Segoe UI,40,&H00FBF6F3,&H00FFFFFF,&H80000000,&H80000000,0,0,0,0,100,100,0,0,3,10,0,2,100,820,80,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    dialogues = []
    for c in events:
        is_intro = c['kind'] == 'intro'
        style, x, size = ('Intro', 600, 40) if is_intro else ('Caption', 960, 44)
        text = c['text'].replace('\n', r'\N')
        assert not any(char in text for char in '{}')
        tags = rf'\an2\pos({x},985)\fs{size}\q2\fad(80,80)'
        dialogues.append(f"Dialogue: 10,{timing_string(c['start'], ass=True)},{timing_string(c['end'], ass=True)},{style},,0,0,0,,{{{tags}}}{text}")
    ASS.write_text(styles + '\n'.join(dialogues) + '\n', encoding='utf-8-sig')
    return {'count': len(events), 'max_lines': max(len(c['text'].splitlines()) for c in events),
            'max_columns': max(len(line) for c in events for line in c['text'].splitlines()),
            'nonoverlapping': True, 'canonical_body_text': True,
            'intro_text_source': 'approved transcript of the actual recording; orthography corrected, no added full name',
            'intro_layout': {'font_size': 40, 'x': 600, 'y': 985, 'width': 1000},
            'body_ending_layout': {'font_size': 44, 'x': 960, 'y': 985}}


def complement(intervals: list[list[int]], length: int) -> list[list[int]]:
    out, cursor = [], 0
    for start, end in sorted(intervals):
        if start > cursor:
            out.append([cursor, start])
        cursor = max(cursor, end)
    if cursor < length:
        out.append([cursor, length])
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    VOICE.parent.mkdir(parents=True, exist_ok=True)
    alignment = read(TMP / 'audio/phase_alignment_draft.json')
    retakes = read(TMP / 'audio/proposed_retakes.json')
    main_asr = read(TMP / 'audio/transcript_raw.json')
    intro_asr = read(TMP / 'audio/intro_transcript_raw.json')
    end_asr = read(TMP / 'audio/end_transcript.json')
    sources_meta = read(OUT / 'fontes_voz_v10.json')
    assert len(alignment['phases']) == 88
    sources = {key: ROOT / sources_meta[key]['normalized_path'] for key in ('principal', 'apresentacao', 'encerramento')}
    pcm = {key: load_pcm(path) for key, path in sources.items()}
    words = {'principal': flatten_words(main_asr), 'apresentacao': flatten_words(intro_asr), 'encerramento': flatten_words(end_asr)}
    # Verified FFmpeg->16k ASR against full FFmpeg->48k PCM: lag zero.
    # 20.0106875 vs 20.0106667 is one resampling-rounding sample, not AAC delay.
    end_offset = 0.0
    assert abs(end_asr['duration'] - len(pcm['encerramento']) / RATE) < 1 / 16000

    phases = deepcopy(alignment['phases'])
    obstacles = [r['discard'] for r in retakes['retakes']] + [x['omit'] for x in retakes['numeric_omissions']] + [[494.19, len(pcm['principal']) / RATE]]
    starts = [p['audio_start'] for p in phases]
    ends = [p['audio_end'] for p in phases]
    cut_starts, cut_ends = starts.copy(), ends.copy()
    extra_tail = [0.] * len(phases)
    cut_starts[0] = max(0., starts[0] - PRE_ROLL)
    cut_ends[-1] = ends[-1] + POST_ROLL
    for i in range(len(phases) - 1):
        gap = starts[i + 1] - ends[i]
        has_omission = any(a < starts[i + 1] - 1e-6 and b > ends[i] + 1e-6 for a, b in obstacles)
        if gap <= SHORT_GAP and not has_omission:
            cut_ends[i] = cut_starts[i + 1] = (ends[i] + starts[i + 1]) / 2
        else:
            cut_ends[i] = ends[i] + POST_ROLL
            cut_starts[i + 1] = max(0., starts[i + 1] - PRE_ROLL)
    for i in range(len(phases)):
        wanted_end = cut_ends[i]
        for a, b in obstacles:
            if a >= ends[i] - 1e-6 and a < cut_ends[i]:
                cut_ends[i] = max(ends[i], a)
            if b <= starts[i] + 1e-6 and b > cut_starts[i]:
                cut_starts[i] = min(starts[i], b)
        extra_tail[i] = max(0., wanted_end - cut_ends[i])
        assert cut_starts[i] <= starts[i] <= ends[i] <= cut_ends[i]
        assert not any(min(cut_ends[i], b) - max(cut_starts[i], a) > 1e-5 for a, b in obstacles)

    items: list[dict] = []

    def add_item(kind: str, ident: str, index: int, source_path: Path, video_start: float,
                 video_end: float, source_key: str, a: float, b: float, text: str,
                 speech_start: float, speech_end: float, source_words: list[dict],
                 *, fixed_frames: int | None = None, minimum: float = 1.8,
                 tail_silence: float = 0., extra: dict | None = None) -> None:
        sa = max(0, seconds_samples(a))
        sb = min(len(pcm[source_key]), seconds_samples(b))
        assert sb > sa
        clip_samples = sb - sa
        frames = fixed_frames if fixed_frames is not None else frame_count(max(minimum, clip_samples / RATE + tail_silence))
        target_samples = frames * SAMPLES_PER_FRAME
        assert target_samples >= clip_samples
        start_frame = items[-1]['end_frame'] if items else 0
        duration = frames / FPS
        item = {'kind': kind, 'id': ident, 'index': index, 'source_path': relative(source_path),
                'video_start': video_start, 'video_end': video_end,
                'audio_source': relative(sources[source_key]),
                'audio_start': sa / RATE, 'audio_end': sb / RATE,
                'audio_start_sample': sa, 'audio_end_sample': sb,
                'audio_offset': 0., 'audio_samples': clip_samples,
                'pad_samples': target_samples - clip_samples,
                'frames': frames, 'duration': duration,
                'start_frame': start_frame, 'end_frame': start_frame + frames,
                'start': start_frame / FPS, 'end': (start_frame + frames) / FPS,
                'text': text, 'cues': make_cues(text, speech_start, speech_end, sa / RATE, duration, source_words),
                'caption_layout': {'font_size': 40 if kind == 'intro' else 44, 'x': 600 if kind == 'intro' else 960, 'y': 985,
                                   'width': 1000 if kind == 'intro' else 1700}}
        if extra:
            item.update(extra)
        items.append(item)

    intro_text = APPROVED_INTRO_TEXT
    add_item('intro', 'intro', -1, INTRO, 0., INTRO_FRAMES / FPS, 'apresentacao', 0., INTRO_FRAMES / FPS,
             intro_text, words['apresentacao'][0]['start'], words['apresentacao'][-1]['end'], words['apresentacao'],
             fixed_frames=INTRO_FRAMES, extra={'source_role': 'approved color V5, black background'})

    for i, phase in enumerate(phases):
        patch = phase['video_start'] == 520 and phase['video_end'] == 526
        source_path = PATCH if patch else BASE
        video_a, video_b = (0., 6.) if patch else (phase['video_start'], phase['video_end'])
        active_words = [words['principal'][j] for j in phase['word_indices']]
        add_item('body', f'phase_{i:02d}', i, source_path, video_a, video_b, 'principal', cut_starts[i], cut_ends[i],
                 phase['text'], starts[i], ends[i], active_words,
                 minimum=NUMERIC_MIN_SECONDS if i in (74, 76) else 1.8, tail_silence=extra_tail[i],
                 extra={'reference_video_start': phase['video_start'], 'reference_video_end': phase['video_end'],
                        'alignment_confidence': phase['confidence'], 'editorial_note': phase['editorial_note'],
                        'numeric_omission': i in (74, 76), 'replacement_patch': patch})

    ending_words = [dict(w, start=w['start'] + end_offset, end=w['end'] + end_offset) for w in words['encerramento']]
    end_a = max(0., ending_words[0]['start'] - .20)
    end_b = min(len(pcm['encerramento']) / RATE, ending_words[-1]['end'] + .20)
    # Approved transcript of the actual new recording, including corrected ASR model spellings.
    ending_text = APPROVED_ENDING_TEXT
    add_item('ending', 'ending', 88, FACTORY, 0., end_b - end_a + 1.20, 'encerramento', end_a, end_b,
             ending_text, ending_words[0]['start'], ending_words[-1]['end'], ending_words,
             tail_silence=1.20, extra={'source_role': 'clean factory still plate', 'asr_pcm_offset': end_offset,
                                      'final_silent_hold_seconds': 1.20})

    # Preserve the waveform and speed, with only 5 ms endpoint ramps and zero padding.
    key_by_path = {relative(path): key for key, path in sources.items()}
    written_samples = 0
    with wave.open(str(VOICE), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        for item in items:
            key = key_by_path[item['audio_source']]
            clip = pcm[key][item['audio_start_sample']:item['audio_end_sample']]
            fade = min(FADE_SAMPLES, len(clip) // 2)
            for i in range(fade):
                gain = i / max(1, fade - 1)
                clip[i] = round(clip[i] * gain)
                clip[-1 - i] = round(clip[-1 - i] * gain)
            out.writeframesraw(clip.tobytes())
            if item['pad_samples']:
                out.writeframesraw(b'\0\0' * item['pad_samples'])
            written_samples += len(clip) + item['pad_samples']

    frames = items[-1]['end_frame']
    assert written_samples == frames * SAMPLES_PER_FRAME
    with wave.open(str(VOICE), 'rb') as check:
        assert check.getnframes() == written_samples
    assembled = load_pcm(VOICE)
    pcm_exact_items = 0
    for item in items:
        key = key_by_path[item['audio_source']]
        a = item['start_frame'] * SAMPLES_PER_FRAME
        b = a + item['audio_samples']
        sa, sb = item['audio_start_sample'], item['audio_end_sample']
        assert assembled[a + FADE_SAMPLES:b - FADE_SAMPLES] == pcm[key][sa + FADE_SAMPLES:sb - FADE_SAMPLES]
        assert not any(assembled[b:item['end_frame'] * SAMPLES_PER_FRAME])
        pcm_exact_items += 1
    del assembled
    caption_report = write_captions(items)
    timeline = {'version': 10, 'fps': FPS, 'sample_rate': RATE, 'samples_per_frame': SAMPLES_PER_FRAME,
                'frames': frames, 'samples': written_samples, 'duration': frames / FPS,
                'timebase': 'global start/end derived from integer 30 fps frames; source audio cuts are integer PCM48k samples',
                'audio_path': relative(VOICE), 'srt_path': relative(SRT), 'ass_path': relative(ASS),
                'items': items, 'voice_stretched': False, 'speech_synthesis': False,
                'editing': {'short_gap_midpoint_max_seconds': SHORT_GAP, 'large_gap_lead_seconds': PRE_ROLL,
                            'large_gap_tail_seconds': POST_ROLL, 'cut_fade_ms': 5,
                            'numeric_omission_min_visual_seconds': NUMERIC_MIN_SECONDS,
                            'ending_final_silence_seconds': 1.20}}
    write(TIMELINE, timeline)

    body_items = [item for item in items if item['kind'] == 'body']
    kept = [[item['audio_start_sample'], item['audio_end_sample']] for item in body_items]
    removed = complement(kept, len(pcm['principal']))
    report = {'status': 'ready_for_encoding', 'version': 10, 'frames': frames, 'duration': frames / FPS,
              'items': len(items), 'body_phases': len(body_items), 'voice_samples': written_samples,
              'frame_exact_samples': frames * SAMPLES_PER_FRAME, 'sample_duration_exact': True,
              'original_pcm_interior_exact_items': pcm_exact_items, 'zero_padding_verified': True,
              'timeline_contiguous': all(a['end_frame'] == b['start_frame'] for a, b in zip(items, items[1:])),
              'source_audio_order_nondecreasing': all(a['audio_end_sample'] <= b['audio_start_sample'] for a, b in zip(body_items, body_items[1:])),
              'source_audio_sample_rate': RATE, 'voice_speed_changed': False, 'synthesized_voice': False,
              'fade_ms': 5, 'captions': caption_report,
              'retakes': retakes['retakes'], 'numeric_omissions': retakes['numeric_omissions'],
              'body_kept_sample_intervals': kept, 'body_removed_sample_intervals': removed,
              'body_kept_source_seconds': sum(b - a for a, b in kept) / RATE,
              'body_removed_source_seconds': sum(b - a for a, b in removed) / RATE,
              'body_output_seconds': sum(item['frames'] for item in body_items) / FPS,
              'zero_padding_seconds': sum(item['pad_samples'] for item in items) / RATE,
              'intro': {'frames': INTRO_FRAMES, 'duration': INTRO_FRAMES / FPS, 'audio_start': 0., 'audio_end': INTRO_FRAMES / FPS},
              'ending': {'asr_pcm_offset_seconds': end_offset, 'pcm_source_duration': len(pcm['encerramento']) / RATE,
                         'asr_duration': end_asr['duration'], 'first_word': ending_words[0]['start'], 'last_word': ending_words[-1]['end'],
                         'source_keep': [end_a, end_b], 'output_duration': items[-1]['duration'],
                         'caption_text': 'approved transcript of the actual recording; scientific names and orthography corrected',
                         'offset_evidence': 'ASR script feeds full FFmpeg 16k PCM; duration difference 20.8 microseconds. Independent cross-correlation with full48k decode: best lag0, r=0.9999999986.'},
              'alignment_issues': alignment['issues'],
              'source_visuals': [{'path': relative(p), 'exists': p.exists()} for p in (INTRO, BASE, PATCH, FACTORY)],
              'output_files': {relative(p): {'bytes': p.stat().st_size, 'sha256': sha(p)} for p in (TIMELINE, VOICE, SRT, ASS)}}
    assert report['timeline_contiguous'] and report['source_audio_order_nondecreasing']
    write(REPORT, report)
    print(json.dumps({'status': report['status'], 'items': len(items), 'body_phases': len(body_items),
                      'frames': frames, 'duration': frames / FPS, 'samples': written_samples,
                      'caption_count': caption_report['count'], 'zero_padding_seconds': report['zero_padding_seconds'],
                      'ending_offset': end_offset, 'source_visuals_ready': all(x['exists'] for x in report['source_visuals'])}))


if __name__ == '__main__':
    main()
