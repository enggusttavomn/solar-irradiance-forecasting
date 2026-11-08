"""Preserve native animation timing while placing the recorded voice around it."""

from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import math
from pathlib import Path
import subprocess
import time

import montagem_v10_common as common
from audit_delivery_v8 import mp4_headers
from render_montagem_v10 import overlays_for

ROOT = common.ROOT
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v11'
TMP = ROOT / 'tmp/montagem_final_v11'
FFMPEG = common.FFMPEG
FPS = 30
CHUNKS = OUT / 'cenas_editadas'
SILENT = OUT / 'Imagem_Final_Ritmo_Didatico_v11.mp4'
VOICE_ONLY = OUT / 'Video_TCC_Ritmo_Didatico_Somente_Voz_v11.mp4'
WITH_MUSIC = OUT / 'Video_TCC_Ritmo_Didatico_Com_Trilha_v11.mp4'
MUSIC = common.OUT / 'audio/trilha_ambiente_original_v10.wav'
read, write, sha, run = common.read, common.write, common.sha, common.run


def absolute(value):
    value = Path(value)
    return value if value.is_absolute() else ROOT / value


def progress(stage, **extra):
    write(OUT / 'progresso_montagem_v11.json', {
        'stage': stage, 'updated_unix': time.time(), **extra})


def encode(item, source_hashes):
    frames = int(item['frames'])
    duration = frames / FPS
    source = absolute(item['source_path'])
    target = CHUNKS / (item['id'] + '.mp4')
    ass, cache = target.with_suffix('.ass'), target.with_suffix('.json')
    overlays_for(item, ass)
    start, end = float(item['video_start']), float(item['video_end'])
    original = end - start
    key = {
        'source': str(source), 'source_sha256': source_hashes[str(source)],
        'start': start, 'end': end, 'frames': frames, 'ass_sha256': sha(ass),
        'format': 'native_1x_qsv_icq18_medium_nv12_cfr30_v11a',
    }
    old = read(cache, {})
    if target.exists() and old.get('key') == key and sha(target) == old.get('sha256'):
        return old

    if item['kind'] == 'ending':
        inputs = ['-loop', '1', '-framerate', FPS, '-i', source]
        vf = "scale=2016:1134,crop=1920:1080:x='48+8*sin(t/8)':y='27+5*sin(t/11)',fps=30,"
    else:
        assert frames >= round(original * FPS), f"Would accelerate {item['id']}"
        inputs = ['-ss', f'{start:.8f}', '-threads', '2', '-i', source]
        # Play every source second at its original rate. Extra time holds the
        # completed diagram; there is no duration/original speed multiplier.
        padding = max(1., duration - original + .10)
        vf = (f'trim=duration={original:.8f},setpts=PTS-STARTPTS,fps=30,'
              f'tpad=stop_mode=clone:stop_duration={padding:.8f},trim=end_frame={frames},')
    vf += 'ass=' + ass.relative_to(ROOT).as_posix()
    if item['kind'] == 'intro':
        vf += ',fade=t=in:st=0:d=0.10'
    if item['kind'] == 'ending':
        vf += f',fade=t=out:st={duration - .65:.6f}:d=0.65'
    vf += ',format=nv12'
    run([FFMPEG, '-v', 'error', '-y', *inputs, '-vf', vf, '-an',
         '-frames:v', frames, '-r', FPS, '-fps_mode', 'cfr',
         '-c:v', 'h264_qsv', '-global_quality', '18', '-preset', 'medium',
         '-look_ahead', '0', '-profile:v', 'high', '-g', '120', '-bf', '3',
         '-video_track_timescale', '15360', '-map_metadata', '-1',
         '-movflags', '+faststart', target])
    header = mp4_headers(target)
    assert abs(header['fps'] - FPS) < 1e-6
    assert abs(header['duration_seconds'] - duration) < 1e-5
    record = {
        'id': item['id'], 'key': key, 'path': str(target.relative_to(ROOT)),
        'sha256': sha(target), 'frames': frames, 'duration': duration, 'header': header,
        'animation_speed': 1., 'native_animation_seconds': original,
        'completed_scene_hold_seconds': max(0., duration - original),
        'encoder': 'h264_qsv',
    }
    write(cache, record)
    return record


def compose_picture(timeline):
    CHUNKS.mkdir(parents=True, exist_ok=True)
    items = timeline['items']
    source_hashes = {str(absolute(x['source_path'])): sha(absolute(x['source_path'])) for x in items}
    results = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        tasks = {pool.submit(encode, x, source_hashes): x['id'] for x in items}
        for task in as_completed(tasks):
            results.append(task.result())
            progress('encoding_native_animation', completed=len(results), total=len(items), last=tasks[task])
            print(f"V11_CHUNK {len(results)}/{len(items)} {tasks[task]}", flush=True)
    by_id = {r['id']: ROOT / r['path'] for r in results}
    listing = OUT / 'concat_imagem_v11.txt'
    listing.write_text(''.join("file '" + by_id[x['id']].as_posix().replace("'", "'\\''") + "'\n" for x in items), encoding='utf-8')
    progress('assembling_picture')
    run([FFMPEG, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', listing,
         '-map', '0:v:0', '-an', '-c:v', 'copy', '-map_metadata', '-1', '-movflags', '+faststart', SILENT])
    header = mp4_headers(SILENT)
    assert header['fps'] == FPS and abs(header['duration_seconds'] - timeline['duration']) < 1e-5
    write(OUT / 'verificacao_imagem_montada_v11.json', {
        'source_hashes': source_hashes, 'chunks': results, 'frames': timeline['frames'],
        'duration': timeline['duration'], 'header': header, 'sha256': sha(SILENT),
        'body_animation_speed_original': True, 'accelerated_body_scenes': 0,
        'encoder': 'Intel Quick Sync h264_qsv (hardware encode)',
    })


def mix(timeline):
    duration = timeline['duration']
    voice = absolute(timeline['audio_path'])
    progress('exporting_voice_only')
    run([FFMPEG, '-v', 'error', '-y', '-i', SILENT, '-i', voice,
         '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
         '-af', 'alimiter=limit=0.891251:attack=5:release=70:level=false:latency=true',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-t', f'{duration:.8f}',
         '-map_metadata', '-1', '-movflags', '+faststart', VOICE_ONLY])
    progress('mixing_ducked_music')
    graph = (
        f'[1:a]asplit=2[v][sc];[2:a]atrim=duration={duration:.8f},asetpts=PTS-STARTPTS,'
        f'volume=.75,afade=t=in:st=0:d=1.8,afade=t=out:st={duration-3:.8f}:d=3[m];'
        '[m][sc]sidechaincompress=threshold=.04:ratio=6:attack=25:release=650:knee=4:link=maximum:mix=1[duck];'
        '[v][duck]amix=inputs=2:duration=first:normalize=0,'
        'alimiter=limit=.891251:attack=5:release=70:level=false:latency=true[out]')
    run([FFMPEG, '-v', 'error', '-y', '-i', SILENT, '-i', voice, '-i', MUSIC,
         '-filter_complex', graph, '-map', '0:v:0', '-map', '[out]', '-c:v', 'copy',
         '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-ac', '2', '-t', f'{duration:.8f}',
         '-map_metadata', '-1', '-movflags', '+faststart', WITH_MUSIC])
    progress('verifying_final_exports')
    files = [common.media_info(p, decode=True) for p in [VOICE_ONLY, WITH_MUSIC]]
    for value in files:
        assert value['decoded_frames'] == timeline['frames'] and value['has_audio']
    hashes = [run([FFMPEG, '-v', 'error', '-i', p, '-map', '0:v:0', '-c', 'copy',
                   '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip() for p in [VOICE_ONLY, WITH_MUSIC]]
    assert hashes[0] == hashes[1]
    write(OUT / 'verificacao_video_final_v11.json', {
        'version': 11, 'status': 'encoded_pending_timing_review', 'files': files,
        'frames': timeline['frames'], 'fps': FPS, 'duration_seconds': duration,
        'resolution': [1920, 1080], 'body_animation_speed_original': True,
        'accelerated_body_scenes': 0, 'voice_time_stretch_used': False,
        'voice_synthesis_used': False, 'same_video_bitstream': True,
        'video_stream_sha256': hashes[0], 'music_ducking': True,
        'presenter_original_color': True, 'background_black': True, 'cover_version': 5,
        'sampled_temporal_review_passed': False, 'full_realtime_playback_reviewed': False,
        'encoder': 'h264_qsv',
    })
    write_player(timeline)
    print('V11_EXPORTS_READY_FOR_REVIEW', flush=True)


def write_player(timeline):
    body = [x for x in timeline['items'] if x['kind'] == 'body']
    starts = {x['index']: x['start'] for x in body}
    chapters = [('Introdução', 0.), ('GHI e aplicações', starts[0]), ('Como funcionam as redes', starts[10]),
                ('Localidades e dados', starts[25]), ('Entradas e tarefas', starts[34]),
                ('Protocolo de avaliação', starts[47]), ('Quantização', starts[53]),
                ('Entendendo o MAE', starts[62]), ('Resultados', starts[69]),
                ('Interpretação e limites', starts[81]), ('Conclusão', timeline['items'][-1]['start'])]
    buttons = ''.join(f'<button data-time="{t:.6f}">{html.escape(name)}</button>' for name, t in chapters)
    title = 'Vídeo final — ritmo didático'
    duration = timeline['duration']
    display = f'{round(duration)//60}min{round(duration)%60:02d}s'
    page = f'''<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
body{{margin:0;background:#000;color:#eee;font:16px Segoe UI,Arial}}main{{max-width:1280px;margin:auto;padding:20px}}
h1{{font-size:24px}}video{{width:100%;background:#000}}p{{line-height:1.5}}select,button{{font:inherit;background:#171b1e;color:#a8d7e0;border:1px solid #344349;border-radius:6px;padding:9px;margin:4px}}
a{{color:#a8d7e0;margin-right:20px}}nav{{display:flex;flex-wrap:wrap;margin:16px 0}}button{{cursor:pointer}}
</style><main><h1>{title}</h1><p>{display} · Full HD · Animações na velocidade original</p>
<video controls playsinline preload="metadata" poster="../montagem_final_v10/previas/Capa_Fundo_Preto_Apresentador_Colorido_v5.png" src="{VOICE_ONLY.name}"></video>
<p><label>Áudio: <select><option value="{VOICE_ONLY.name}">Somente voz</option><option value="{WITH_MUSIC.name}">Voz com trilha sonora</option></select></label></p>
<nav aria-label="Ir para um trecho">{buttons}</nav>
<p><a href="{VOICE_ONLY.name}" download>Baixar sem música</a><a href="{WITH_MUSIC.name}" download>Baixar com música</a><a href="Legendas_Finais_v11.srt" download>Legendas</a></p>
</main><script>
const v=document.querySelector('video');document.querySelector('select').onchange=e=>{{const t=v.currentTime,play=!v.paused;v.pause();v.src=e.target.value;v.addEventListener('loadedmetadata',()=>{{v.currentTime=t;if(play)v.play().catch(()=>{{}})}},{{once:true}})}};
document.querySelectorAll('button[data-time]').forEach(b=>b.onclick=()=>{{v.currentTime=Number(b.dataset.time);v.play().catch(()=>{{}})}});
</script></html>'''
    player = OUT / 'assistir_video_ritmo_didatico_v11.html'
    player.write_text(page, encoding='utf-8')
    (ROOT / 'ASSISTIR_VIDEO_RITMO_DIDATICO_V11.cmd').write_bytes(
        ('@echo off\r\nstart "" "%~dp0' + str(player.relative_to(ROOT)) + '"\r\n').encode('ascii'))


if __name__ == '__main__':
    timeline = read(OUT / 'timeline_montagem_v11.json')
    if not timeline:
        raise SystemExit('Missing reviewed timing plan / V11 timeline')
    compose_picture(timeline)
    mix(timeline)
