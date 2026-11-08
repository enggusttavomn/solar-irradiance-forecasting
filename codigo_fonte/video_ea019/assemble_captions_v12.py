"""Write globally timed V12 captions and combine voice with the visual schedule.

Caption wording is taken from the reviewed recorded-voice manifest, not invented
from the planned script. The only automatic wording edit is sentence capitalization.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import unicodedata

from montagem_v10_common import ROOT, read, write, sha
from overlays import Overlay, WHITE, CYAN, VIOLET, MUTED


OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TMP = ROOT / 'tmp/montagem_final_v12'
VOICE = OUT / 'voz_e_legendas_continuas_v12.json'
SCHEDULE = TMP / 'visual_schedule_v12.json'
SRT = OUT / 'Legendas_Finais_v12.srt'
ASS = OUT / 'Legendas_Finais_v12.ass'
TIMELINE = OUT / 'timeline_montagem_v12.json'
REPORT = OUT / 'verificacao_legendas_globais_v12.json'


def relative(path):
    return path.relative_to(ROOT).as_posix()


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def srt_time(seconds):
    value = round(seconds * 1000)
    h, rest = divmod(value, 3600000)
    m, rest = divmod(rest, 60000)
    s, ms = divmod(rest, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def token(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value)).casefold()
                   if c.isalnum() and not unicodedata.combining(c))


def word_anchor(paragraph, phrase):
    words = [word for word in paragraph['words'] if word.get('edited_start') is not None]
    wanted = [token(part) for part in phrase.split()]
    for start in range(len(words) - len(wanted) + 1):
        if [token(word['canonical_token']) for word in words[start:start + len(wanted)]] == wanted:
            return float(words[start]['edited_start'])
    raise ValueError('Missing reviewed closing word anchor: ' + phrase)


def closing_headers(voice, overlay):
    paragraph = next(row for row in voice['paragraphs'] if row['index'] == 26)
    duration = float(voice['duration'])
    first = float(paragraph['edited_start'])
    winners = word_anchor(paragraph, 'Nos horizontes completos')
    contribution = word_anchor(paragraph, 'Esses resultados')
    thanks = duration - 1.20
    assert 0 <= first < winners < contribution < thanks < duration
    overlay.text(first, winners, '3 arquiteturas · 10 localidades', x=960, y=92,
                 align=8, size=49, bold=True, fade_ms=280)
    overlay.text(first, winners, 'Um protocolo comum de avaliação', x=960, y=154,
                 align=8, size=31, color=MUTED, fade_ms=280)
    overlay.text(winners, contribution, 'Transformer · horária e diária', x=960, y=78,
                 align=8, size=43, color=CYAN, bold=True, fade_ms=220)
    overlay.text(winners, contribution, 'Informer · tarefas mensais', x=960, y=137,
                 align=8, size=43, color=VIOLET, bold=True, fade_ms=220)
    overlay.text(winners, contribution, 'Nos horizontes completos avaliados', x=960, y=199,
                 align=8, size=27, color=MUTED, fade_ms=220)
    overlay.text(contribution, duration, 'Uma base experimental para orientar', x=960, y=75,
                 align=8, size=44, bold=True, fade_ms=260)
    overlay.text(contribution, duration, 'a escolha dos modelos de previsão solar', x=960, y=133,
                 align=8, size=40, fade_ms=260)
    overlay.text(thanks, duration, 'Obrigado pela atenção', x=960, y=213,
                 align=8, size=29, color=MUTED, fade_ms=180)
    return {'factory_closing_start': first, 'winner_summary_start': winners,
            'experimental_contribution_start': contribution, 'thanks_start': thanks,
            'spoken_thanks_start': word_anchor(paragraph, 'Obrigado pela atenção'),
            'source': 'Paragraph26 reviewed words, using their edited global timestamps.'}


def chapter_list(voice):
    titles = {
        'ghi': 'GHI e aplicações', 'modelos': 'Como funcionam as redes',
        'dados': 'Localidades e dados', 'entradas': 'Entradas e tarefas',
        'protocolo': 'Protocolo de comparação', 'quantizacao': 'Quantização',
        'mae': 'Entendendo o MAE', 'resultados': 'Resultados',
        'conclusao': 'Interpretação e conclusão',
    }
    chapters = [{'id': 'abertura', 'title': 'Apresentação', 'start': 0.}]
    seen = set()
    for paragraph in voice['paragraphs']:
        ident = paragraph['section_id']
        if ident not in seen:
            chapters.append({'id': ident, 'title': titles.get(ident, ident),
                             'start': float(paragraph['edited_start'])})
            seen.add(ident)
    chapters.append({'id': 'encerramento', 'title': 'Conclusão sobre a fábrica',
                     'start': float(voice['paragraphs'][-1]['edited_start'])})
    return chapters


def main():
    voice = read(VOICE)
    if not voice:
        raise SystemExit('Waiting for the reviewed continuous-voice manifest')
    voice_hash = sha(VOICE)
    duration = float(voice['duration'])
    frames = int(voice['frames'])
    assert abs(duration - frames / 30) < 1e-6 and duration <= 600
    assert voice['voice_time_stretch_used'] is False and voice['speech_synthesis_used'] is False
    assert sha(absolute(voice['audio_path'])) == voice['voice_sha256']
    captions = deepcopy(voice['captions'])
    corrections = []
    # The weak, unconfirmed article before "projeto" was already removed by
    # the voice editor. Capitalize the actual sentence start without adding it.
    for index, cue in enumerate(captions):
        if cue.get('paragraph_index') == 26 and cue['text'].startswith('projeto'):
            before = cue['text']
            cue['text'] = 'P' + before[1:]
            corrections.append({'cue_index': index, 'before': before, 'after': cue['text'],
                                'reason': 'Capitalization of the reviewed spoken sentence start; no article added.'})
            break
    for index, cue in enumerate(captions):
        assert cue['kind'] in ('intro', 'body')
        assert 0 <= cue['start'] < cue['end'] <= duration
        assert index == 0 or cue['start'] >= captions[index - 1]['end'] - 1e-6
        assert len(cue['text'].splitlines()) <= 2
        assert max(map(len, cue['text'].splitlines())) <= 42
        assert not any(c in cue['text'] for c in '{}\ufffd')
    # All semantic caption words remain exactly as supplied by the voice editor.
    assert [row['text'].casefold() for row in captions] == [row['text'].casefold() for row in voice['captions']]
    assert len(captions) == 112
    OUT.mkdir(parents=True, exist_ok=True)
    SRT.write_text('\n\n'.join(
        f'{index}\n{srt_time(cue["start"])} --> {srt_time(cue["end"])}\n{cue["text"]}'
        for index, cue in enumerate(captions, 1)) + '\n', encoding='utf-8-sig')
    overlay = Overlay(duration)
    for cue in captions:
        intro = cue['kind'] == 'intro'
        overlay.text(cue['start'], cue['end'], cue['text'], x=600 if intro else 960,
                     y=985, size=40 if intro else 44, color=WHITE, style='Caption',
                     align=2, layer=10, fade_ms=80)
    anchors = closing_headers(voice, overlay)
    overlay_record = overlay.write(ASS)
    # The title identifies this deliverable; it is not an on-screen overlay.
    content = ASS.read_text(encoding='utf-8-sig').replace(
        'Title: EA019 scientific animation - deterministic text overlay',
        'Title: V12 continuous recorded narration and global captions')
    ASS.write_text(content, encoding='utf-8-sig')
    assert sha(VOICE) == voice_hash
    report = {
        'version': 12, 'status': 'captions_ready_waiting_visual_schedule',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'voice_manifest_path': relative(VOICE), 'voice_manifest_sha256': voice_hash,
        'voice_audio_path': voice['audio_path'], 'voice_audio_sha256': voice['voice_sha256'],
        'duration_seconds': duration, 'frames': frames, 'captions': len(captions),
        'global_events': len(overlay.checks), 'intro_caption_count': sum(row['kind'] == 'intro' for row in captions),
        'body_caption_count': sum(row['kind'] == 'body' for row in captions),
        'maximum_caption_lines': max(len(row['text'].splitlines()) for row in captions),
        'maximum_caption_line_characters': max(len(line) for row in captions for line in row['text'].splitlines()),
        'caption_word_changes': False, 'orthographic_corrections': corrections,
        'incorrect_numeric_clause_added_back': False, 'closing_anchors': anchors,
        'captions_at_global_time': True, 'restarted_on_visual_boundaries': False,
        'caption_font': 'Segoe UI', 'body_caption_anchor': [960, 985], 'body_caption_fontsize': 44,
        'intro_caption_anchor': [600, 985], 'intro_caption_fontsize': 40,
        'fade_ms': 80, 'overlay_events': overlay_record['events'],
        'outputs': [{'path': relative(path), 'sha256': sha(path), 'bytes': path.stat().st_size} for path in [SRT, ASS]],
        'visual_inspection_performed': False,
    }
    schedule = read(SCHEDULE)
    if schedule:
        visual_items = schedule.get('visual_items', schedule.get('items'))
        if not visual_items:
            raise ValueError('Visual schedule has no visual_items')
        cursor = 0
        for item in visual_items:
            assert item['start_frame'] == cursor and item['end_frame'] == cursor + item['frames']
            assert abs(item['duration'] - item['frames'] / 30) < 1e-6
            if item['kind'] != 'ending':
                assert item['frames'] >= round((item['video_end'] - item['video_start']) * 30)
            assert absolute(item['source_path']).is_file()
            cursor = item['end_frame']
        assert cursor == frames
        assert schedule.get('frames', frames) == frames
        chapters = schedule.get('chapters') or chapter_list(voice)
        timeline = {
            'version': 12, 'status': 'ready_for_encoding', 'frames': frames, 'duration': duration,
            'fps': 30, 'resolution': [1920, 1080], 'audio_path': voice['audio_path'],
            'ass_path': relative(ASS), 'srt_path': relative(SRT),
            'visual_items': visual_items, 'chapters': chapters,
            'voice_manifest_path': relative(VOICE), 'voice_manifest_sha256': voice_hash,
            'voice_master_status': voice['status'], 'voice_sha256': voice['voice_sha256'],
            'visual_schedule_path': relative(SCHEDULE), 'visual_schedule_sha256': sha(SCHEDULE),
            'captions_count': len(captions), 'caption_orthographic_corrections': corrections,
            'captions_global_continuous': True, 'voice_global_continuous': True,
            'voice_cut_at_visual_boundaries': False, 'voice_time_stretch_used': False,
            'speech_synthesis_used': False, 'native_visual_playback_speed': 1.,
            'new_recording_used': voice['new_recording_used'],
            'whole_recording_cleanup_report': voice['whole_recording_cleanup_report'],
            'incorrect_numeric_clause_removed': voice['incorrect_numeric_clause_removed'],
            'six_month_plot_value_remains': voice['six_month_plot_value_remains'],
        }
        write(TIMELINE, timeline)
        report['status'] = 'ready_for_encoding'
        report['visual_items_count'] = len(visual_items)
        report['timeline_sha256'] = sha(TIMELINE)
    write(REPORT, report)
    print(f"V12_CAPTIONS_READY: {len(captions)} captions, {len(overlay.checks)} global events, "
          f"{duration:.6f}s; {report['status']}", flush=True)


if __name__ == '__main__':
    main()
