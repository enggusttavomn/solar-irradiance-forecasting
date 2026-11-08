"""Render native-speed visuals under a single continuous voice/caption timeline.

The visual cuts never divide the narration or restart subtitle events. Each
temporary visual segment evaluates the same global ASS at its final timestamp.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
from pathlib import Path
import time

from audit_delivery_v8 import mp4_headers
import montagem_v10_common as common

ROOT = common.ROOT
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12'
TMP = ROOT / 'tmp/montagem_final_v12'
FFMPEG = common.FFMPEG
FPS = 30
TIMELINE = OUT / 'timeline_montagem_v12.json'
CHUNKS = OUT / 'cenas_editadas'
SILENT = OUT / 'Imagem_Final_Continua_1080p_v12.mp4'
VOICE_ONLY = OUT / 'Video_TCC_Final_Continuo_Somente_Voz_v12.mp4'
WITH_MUSIC = OUT / 'Video_TCC_Final_Continuo_Com_Trilha_v12.mp4'
MUSIC = common.OUT / 'audio/trilha_ambiente_original_v10.wav'
read, write, sha, run = common.read, common.write, common.sha, common.run


def absolute(value):
    value = Path(value)
    return value if value.is_absolute() else ROOT / value


def progress(stage, **extra):
    write(OUT / 'progresso_montagem_v12.json', {
        'stage': stage, 'updated_unix': time.time(), **extra})


def filter_path(path):
    # The global ASS is a task-owned workspace artifact. Keeping this reference
    # relative also avoids treating the Windows drive colon as a filter option.
    value = path.resolve().relative_to(ROOT.resolve()).as_posix()
    if "'" in value or ':' in value:
        raise ValueError('Unexpected quoting character in caption path')
    return "'" + value + "'"


def validate_timeline(timeline):
    items = timeline['visual_items']
    frames = int(timeline['frames'])
    assert frames > 0 and abs(timeline['duration'] - frames / FPS) < 1e-6
    assert frames / FPS <= 600
    assert items and len({x['id'] for x in items}) == len(items)
    cursor = 0
    for item in items:
        assert item['kind'] in ('intro', 'body', 'ending')
        assert item['start_frame'] == cursor
        assert item['frames'] > 0 and item['end_frame'] == cursor + item['frames']
        assert abs(item['duration'] - item['frames'] / FPS) < 1e-6
        assert absolute(item['source_path']).is_file()
        if item['kind'] != 'ending':
            original = float(item['video_end']) - float(item['video_start'])
            assert original > 0
            assert item['frames'] >= round(original * FPS), f"Would accelerate {item['id']}"
        cursor = item['end_frame']
    assert cursor == frames
    for key in ['audio_path', 'ass_path', 'srt_path']:
        assert absolute(timeline[key]).is_file(), key
    assert MUSIC.is_file()


def encode(item, source_hashes, global_ass, ass_hash):
    frames = int(item['frames'])
    duration = frames / FPS
    source = absolute(item['source_path'])
    target = CHUNKS / (item['id'] + '.mp4')
    cache = target.with_suffix('.json')
    start, end = float(item['video_start']), float(item['video_end'])
    native_duration = end - start
    key = {
        'source': str(source), 'source_sha256': source_hashes[str(source)],
        'source_start': start, 'source_end': end, 'frames': frames,
        'global_start_frame': item['start_frame'], 'global_ass_sha256': ass_hash,
        'format': 'native_1x_global_ass_qsv_icq18_medium_nv12_cfr30_v12a',
    }
    old = read(cache, {})
    if target.exists() and old.get('key') == key and sha(target) == old.get('sha256'):
        return old
    if item['kind'] == 'ending':
        inputs = ['-loop', '1', '-framerate', FPS, '-i', source]
        vf = ("scale=2016:1134,crop=1920:1080:x='48+8*sin(t/8)':y='27+5*sin(t/11)',"
              f'fps=30,trim=end_frame={frames},setpts=PTS-STARTPTS,')
    else:
        inputs = ['-ss', f'{start:.8f}', '-threads', 2, '-i', source]
        padding = max(1., duration - native_duration + .10)
        vf = (f'trim=duration={native_duration:.8f},setpts=PTS-STARTPTS,fps=30,'
              f'tpad=stop_mode=clone:stop_duration={padding:.8f},trim=end_frame={frames},')
    # The same ASS event can span several visual clips. It is sampled at the
    # final global time so a cut cannot restart its fade or shift its wording.
    vf += (f"setpts=PTS+{int(item['start_frame'])}/(30*TB),"
           f'ass=filename={filter_path(global_ass)},setpts=PTS-STARTPTS')
    if item['kind'] == 'intro':
        vf += ',fade=t=in:st=0:d=0.10'
    if item['kind'] == 'ending':
        vf += f',fade=t=out:st={max(0., duration - .65):.6f}:d=0.65'
    vf += ',format=nv12'
    run([FFMPEG, '-v', 'error', '-y', *inputs, '-vf', vf, '-an',
         '-frames:v', frames, '-r', FPS, '-fps_mode', 'cfr',
         '-c:v', 'h264_qsv', '-global_quality', 18, '-preset', 'medium',
         '-look_ahead', 0, '-profile:v', 'high', '-g', 120, '-bf', 3,
         '-video_track_timescale', 15360, '-map_metadata', -1,
         '-movflags', '+faststart', target])
    header = mp4_headers(target)
    assert header['frame_count'] == frames and header['fps'] == FPS
    assert header['width'] == 1920 and header['height'] == 1080
    assert abs(header['duration_seconds'] - duration) < 1e-5
    assert sha(global_ass) == ass_hash, 'Global captions changed during rendering'
    record = {
        'id': item['id'], 'key': key, 'path': str(target.relative_to(ROOT)),
        'sha256': sha(target), 'frames': frames, 'duration': duration, 'header': header,
        'global_start_frame': item['start_frame'], 'global_end_frame': item['end_frame'],
        'global_ass_evaluated': True, 'native_visual_speed': 1.,
        'source_visual_seconds': native_duration if item['kind'] != 'ending' else None,
        'terminal_visual_hold_seconds': max(0., duration - native_duration) if item['kind'] != 'ending' else 0.,
        'encoder': 'h264_qsv',
    }
    write(cache, record)
    return record


def compose_picture(timeline):
    validate_timeline(timeline)
    previous_export = read(OUT / 'verificacao_video_final_v12.json')
    if previous_export:
        previous_export['status'] = 'rebuilding_visuals'
        previous_export['revision_started_unix'] = time.time()
        write(OUT / 'verificacao_video_final_v12.json', previous_export)
    CHUNKS.mkdir(parents=True, exist_ok=True)
    items = timeline['visual_items']
    sources = {str(absolute(item['source_path'])) for item in items}
    source_hashes = {path: sha(Path(path)) for path in sources}
    global_ass = absolute(timeline['ass_path'])
    ass_hash = sha(global_ass)
    records = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(encode, item, source_hashes, global_ass, ass_hash): item['id'] for item in items}
        for task in as_completed(tasks):
            records.append(task.result())
            progress('encoding_continuous_picture', completed=len(records), total=len(items), last=tasks[task])
            print(f"V12_VISUAL {len(records)}/{len(items)} {tasks[task]}", flush=True)
    by_id = {record['id']: ROOT / record['path'] for record in records}
    listing = OUT / 'concat_imagem_v12.txt'
    listing.write_text(''.join("file '" + by_id[item['id']].as_posix().replace("'", "'\\''") + "'\n"
                               for item in items), encoding='utf-8')
    progress('assembling_continuous_picture')
    run([FFMPEG, '-v', 'error', '-y', '-f', 'concat', '-safe', 0, '-i', listing,
         '-map', '0:v:0', '-an', '-c:v', 'copy', '-map_metadata', -1,
         '-movflags', '+faststart', SILENT])
    header = mp4_headers(SILENT)
    assert header['fps'] == FPS and header['frame_count'] == timeline['frames']
    assert header['width'] == 1920 and header['height'] == 1080
    assert abs(header['duration_seconds'] - timeline['duration']) < 1e-5
    assert source_hashes == {path: sha(Path(path)) for path in sources}
    write(OUT / 'verificacao_imagem_montada_v12.json', {
        'version': 12, 'source_hashes': source_hashes, 'global_ass_sha256': ass_hash,
        'visual_items': records, 'frames': timeline['frames'], 'duration': timeline['duration'],
        'header': header, 'sha256': sha(SILENT), 'native_visual_speed': 1.,
        'accelerated_visual_items': 0, 'captions_sample_global_time': True,
        'voice_is_not_cut_at_visual_boundaries': True,
        'encoder': 'Intel Quick Sync h264_qsv',
    })


def mix(timeline):
    duration = timeline['duration']
    voice = absolute(timeline['audio_path'])
    voice_hash = sha(voice)
    progress('exporting_voice_only')
    run([FFMPEG, '-v', 'error', '-y', '-i', SILENT, '-i', voice,
         '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
         '-af', 'alimiter=limit=0.891251:attack=5:release=70:level=false:latency=true',
         '-c:a', 'aac', '-b:a', '192k', '-ar', 48000, '-ac', 2, '-t', f'{duration:.8f}',
         '-map_metadata', -1, '-movflags', '+faststart', VOICE_ONLY])
    progress('exporting_voice_with_ducked_music')
    graph = (
        f'[1:a]asplit=2[v][sc];[2:a]atrim=duration={duration:.8f},asetpts=PTS-STARTPTS,'
        f'volume=0.75,afade=t=in:st=0:d=1.8,afade=t=out:st={max(0., duration-3):.8f}:d=3[m];'
        '[m][sc]sidechaincompress=threshold=0.04:ratio=6:attack=25:release=650:knee=4:link=maximum:mix=1[duck];'
        '[v][duck]amix=inputs=2:duration=first:normalize=0,'
        'alimiter=limit=0.891251:attack=5:release=70:level=false:latency=true[out]')
    run([FFMPEG, '-v', 'error', '-y', '-i', SILENT, '-i', voice, '-i', MUSIC,
         '-filter_complex', graph, '-map', '0:v:0', '-map', '[out]', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '192k', '-ar', 48000, '-ac', 2, '-t', f'{duration:.8f}',
         '-map_metadata', -1, '-movflags', '+faststart', WITH_MUSIC])
    progress('verifying_final_exports')
    files = [common.media_info(path, decode=True) for path in [VOICE_ONLY, WITH_MUSIC]]
    for record, path in zip(files, [VOICE_ONLY, WITH_MUSIC]):
        header = mp4_headers(path)
        assert record['decoded_frames'] == timeline['frames'] and record['has_audio']
        assert not record['full_decode_errors']
        assert header['frame_count'] == timeline['frames'] and header['fps'] == FPS
        assert header['width'] == 1920 and header['height'] == 1080 and header['audio_tracks'] == 1
        assert abs(header['duration_seconds'] - duration) < 1e-5
        record['mp4_header'] = header
    hashes = [run([FFMPEG, '-v', 'error', '-i', path, '-map', '0:v:0', '-c', 'copy',
                   '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip() for path in [VOICE_ONLY, WITH_MUSIC]]
    assert hashes[0] == hashes[1]
    assert sha(voice) == voice_hash
    write(OUT / 'verificacao_video_final_v12.json', {
        'version': 12, 'status': 'encoded_pending_timing_review', 'files': files,
        'frames': timeline['frames'], 'fps': FPS, 'duration_seconds': duration,
        'resolution': [1920, 1080], 'visual_items': len(timeline['visual_items']),
        'accelerated_visual_items': 0, 'visual_speed_native': True,
        'voice_global_continuous': True, 'voice_cut_at_visual_boundaries': False,
        'voice_time_stretch_used': False, 'voice_synthesis_used': False,
        'global_captions_rendered_at_global_timestamps': True,
        'audio_master_path': str(voice.relative_to(ROOT)), 'audio_master_sha256': voice_hash,
        'same_video_bitstream': True, 'video_stream_sha256': hashes[0],
        'music_ducking': True, 'presenter_original_color': True,
        'background_black': True, 'cover_version': 5, 'encoder': 'h264_qsv',
        'sampled_visual_review_passed': False, 'sampled_temporal_review_passed': False,
        'full_realtime_playback_reviewed': False, 'audio_listening_performed': False,
        'within_assignment_ten_minute_limit': duration <= 600,
    })
    write_player(timeline)
    print('V12_EXPORTS_READY_FOR_REVIEW', flush=True)


def write_player(timeline):
    duration = timeline['duration']
    display = f'{round(duration)//60}min{round(duration)%60:02d}s'
    chapters = timeline.get('chapters', [])
    buttons = ''.join(f'<button data-time="{float(chapter["start"]):.6f}">{html.escape(str(chapter["title"]))}</button>'
                      for chapter in chapters)
    srt_name = absolute(timeline['srt_path']).name
    page = f'''<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Vídeo final com narração contínua</title><style>
body{{margin:0;background:#000;color:#eee;font:16px Segoe UI,Arial}}main{{max-width:1280px;margin:auto;padding:20px}}
h1{{font-size:24px}}video{{width:100%;background:#000}}p{{line-height:1.5}}
select,button{{font:inherit;background:#171b1e;color:#a8d7e0;border:1px solid #344349;border-radius:6px;padding:9px;margin:4px}}
a{{color:#a8d7e0;margin-right:20px}}nav{{display:flex;flex-wrap:wrap;margin:16px 0}}button{{cursor:pointer}}
</style><main><h1>Vídeo final com narração contínua</h1><p>{display} · Full HD</p>
<video controls playsinline preload="metadata" poster="../montagem_final_v10/previas/Capa_Fundo_Preto_Apresentador_Colorido_v5.png" src="{VOICE_ONLY.name}"></video>
<p><label>Áudio: <select><option value="{VOICE_ONLY.name}">Somente voz</option><option value="{WITH_MUSIC.name}">Voz com trilha sonora</option></select></label></p>
<nav aria-label="Ir para um trecho">{buttons}</nav>
<p><a href="{VOICE_ONLY.name}" download>Baixar sem música</a><a href="{WITH_MUSIC.name}" download>Baixar com música</a><a href="{html.escape(srt_name)}" download>Legendas</a></p>
</main><script>
const v=document.querySelector('video');document.querySelector('select').onchange=e=>{{const t=v.currentTime,play=!v.paused;v.pause();v.src=e.target.value;v.addEventListener('loadedmetadata',()=>{{v.currentTime=t;if(play)v.play().catch(()=>{{}})}},{{once:true}})}};
document.querySelectorAll('button[data-time]').forEach(b=>b.onclick=()=>{{v.currentTime=Number(b.dataset.time);v.play().catch(()=>{{}})}});
</script></html>'''
    player = OUT / 'assistir_video_final_continuo_v12.html'
    player.write_text(page, encoding='utf-8')
    (ROOT / 'ASSISTIR_VIDEO_FINAL_CONTINUO_V12.cmd').write_bytes(
        ('@echo off\r\nstart "" "%~dp0' + str(player.relative_to(ROOT)) + '"\r\n').encode('ascii'))


if __name__ == '__main__':
    timeline = read(TIMELINE)
    if not timeline:
        raise SystemExit('Waiting for the reviewed V12 voice/global-caption timeline')
    compose_picture(timeline)
    mix(timeline)
