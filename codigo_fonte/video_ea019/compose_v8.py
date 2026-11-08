"""Compose the complete film, preserving the approved 224-second V7 prefix."""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import html
import json
import textwrap

from compose_pilot import DEFAULT_FFMPEG, command, probe_and_decode, srt_time
from overlays import Cue, Overlay, read_srt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/completo_v8'
PREFIX = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
CHAPTERS = [('metodologia', 224, 62), ('quantizacao', 286, 54),
            ('metricas', 340, 48), ('resultados', 388, 88), ('interpretacao', 476, 74)]
DURATION = 550
SRT = OUT / 'Legendas_Video_Completo_v8.srt'
NARRATION = OUT / 'Falas_Video_Completo_v8.txt'
FINAL = {True: OUT / 'Video_TCC_GHI_Completo_com_legendas_v8.mp4',
         False: OUT / 'Video_TCC_GHI_Completo_sem_legendas_v8.mp4'}
MOBILE = OUT / 'Video_TCC_GHI_Completo_para_celular_v8.mp4'
# Shorter spoken sentences; the rendered values, horizons and selected conditions
# remain explicit in the 3D scene. Original renderer manifests are never edited.
NARRATION_OVERRIDES = {
    'resultados': {
        (7, 16): 'No horário, o Transformer teve o menor macro-MAE: 53,21 watts por metro quadrado.',
        (16, 24): 'A vantagem sobre a LSTM foi de aproximadamente 0,32 watt por metro quadrado.',
        (24, 32): 'Na diária, o Transformer liderou: 43,89 watts por metro quadrado de macro-MAE.',
        (40, 48): 'No mensal de um passo, o Informer liderou: 12,73 watts por metro quadrado.',
        (54, 61): 'Em seis meses, o Informer liderou: erro cumulativo de 13,67 watts por metro quadrado.',
    }
}


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


def progress(stage, **data):
    atomic_json(OUT / 'progresso_v8.json', {
        'stage': stage, 'updated_utc': datetime.now(timezone.utc).isoformat(), **data})


def cues(phases):
    result = []
    for a, b, text in phases:
        lines = textwrap.wrap(text, 42, break_long_words=False, break_on_hyphens=False)
        chunks = ([lines[0], '\n'.join(lines[1:])] if len(lines) == 3 else
                  ['\n'.join(lines[i:i+2]) for i in range(0, len(lines), 2)])
        total = sum(len(c) for c in chunks)
        t = a
        for i, chunk in enumerate(chunks):
            end = b if i == len(chunks)-1 else t + (b-a)*len(chunk)/total
            result.append(Cue(t, end, chunk))
            t = end
    return result


def prepare(require_render=True):
    OUT.mkdir(parents=True, exist_ok=True)
    previous = json.loads((PREFIX / 'plano_video_v7.json').read_text(encoding='utf-8-sig'))
    phases = list(previous['phases'])
    all_cues = read_srt(PREFIX / 'Legendas_Revisao_ate_Plano22_v7.srt')
    if previous['duration'] != 224 or all_cues[-1].end > 224:
        raise ValueError('Approved prefix timing differs')
    records = []
    for name, start, duration in CHAPTERS:
        record = json.loads((OUT / 'cenas' / f'{name}_manifesto_v8.json').read_text(encoding='utf-8-sig'))
        if record['duration'] != duration or record['start'] != start:
            raise ValueError('Chapter timing differs: ' + name)
        if require_render and (not record['render_complete'] or record['resolution_percentage'] != 100):
            raise ValueError('Production render incomplete: ' + name)
        overrides = NARRATION_OVERRIDES.get(name, {})
        local = [(a, b, overrides.get((a, b), text)) for a, b, text in record['cues']]
        record['cues'] = local
        if local[0][0] != 0 or local[-1][1] != duration:
            raise ValueError('Narration does not cover chapter: ' + name)
        for i, (a, b, text) in enumerate(local):
            if b <= a or not 0 <= a < b <= duration or (i and a < local[i-1][1]):
                raise ValueError('Invalid narration interval: ' + name)
        phases.extend((a+start, b+start, text) for a, b, text in local)
        all_cues.extend(Cue(c.start+start, c.end+start, c.text) for c in cues(local))
        records.append(record)
    if phases[-1][1] != DURATION or DURATION > 560:
        raise ValueError('Duration exceeds reserved budget')
    SRT.write_text('\n\n'.join(f'{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{c.text}'
                                  for i, c in enumerate(all_cues, 1)) + '\n', encoding='utf-8-sig')
    parsed = read_srt(SRT)
    stamp = lambda s: f'{int(s)//60}:{s%60:04.1f}'
    NARRATION.write_text(
        'FALAS PARA NARRAR — VÍDEO COMPLETO V8\n'
        'Animação: 9min10s. Sem áudio e sem filmagens pessoais.\n'
        'Acrescente sua apresentação de 20s antes e seu encerramento de 20s depois: total previsto 9min50s.\n'
        'Tempos abaixo relativos ao início da animação; a gravação poderá ser sincronizada por trecho.\n\n'
        + '\n\n'.join(f'{stamp(a)}–{stamp(b)}\n{text}' for a, b, text in phases) + '\n',
        encoding='utf-8-sig')
    atomic_json(OUT / 'plano_video_v8.json', {
        'version': 8, 'duration': DURATION, 'fps': 30, 'frames': DURATION*30,
        'personal_intro_seconds': 20, 'personal_outro_seconds': 20,
        'projected_total_with_personal_footage': DURATION+40,
        'approved_prefix_reused_seconds': 224, 'phases': phases,
        'cues': [c.__dict__ for c in parsed],
        'chapters': [{'name': n, 'start': s, 'duration': d} for n, s, d in CHAPTERS],
        'narration_recorded': False, 'camera_footage_included': False,
        'animated_title_cards_replacing_personal_footage': False})
    return records, phases


def encode_chapter(record, name, duration, captions):
    tag = 'com_legendas' if captions else 'sem_legendas'
    source = Path(record['raw_mp4'])
    target = OUT / 'cenas' / f'{name}_{tag}_v8.mp4'
    ass = target.with_suffix('.ass')
    overlay = Overlay(duration)
    if captions:
        for cue in cues(record['cues']):
            overlay.caption(cue)
    overlay.write(ass)
    key = {'raw_sha256': sha(source), 'ass_sha256': sha(ass),
           'encoding': ('libx264_medium_crf18_yuv420p_30fps' if captions else
                        'libx264_medium_crf18_yuv420p_cfr30_timescale15360')}
    cache = target.with_suffix('.compose.json')
    old = json.loads(cache.read_text(encoding='utf-8')) if cache.exists() else {}
    if not (target.exists() and old.get('sources') == key and old.get('sha256') == sha(target)):
        progress('adding_captions' if captions else 'encoding_without_captions', chapter=name)
        args = [DEFAULT_FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', source,
                '-vf', 'ass='+ass.relative_to(ROOT).as_posix(), '-an', '-c:v', 'libx264',
                '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p']
        if not captions:
            args += ['-r', '30', '-fps_mode', 'cfr', '-frames:v', duration*30,
                     '-video_track_timescale', '15360']
        args += ['-movflags', '+faststart', '-threads', '6', target]
        command(args)
    check = probe_and_decode(DEFAULT_FFMPEG, target, duration, duration*30)
    atomic_json(cache, {'sources': key, 'sha256': check['sha256'], 'verification': check})
    return target, check


def compose():
    records, phases = prepare()
    files, chapter_files, prefix_hashes = [], [], {}
    for captions in (True, False):
        tag = 'com_legendas' if captions else 'sem_legendas'
        initial = PREFIX / f'Video_GHI_Inicio_ate_Plano22_{tag}_v7.mp4'
        prefix_hashes[str(initial.relative_to(ROOT))] = sha(initial)
        pieces = [initial]
        for record, (name, start, duration) in zip(records, CHAPTERS):
            target, check = encode_chapter(record, name, duration, captions)
            if captions:
                chapter_files.append(check)
            pieces.append(target)
        playlist = OUT / f'concat_{tag}_v8.txt'
        playlist.write_text(''.join("file '"+p.as_posix().replace("'", "'\\''")+"'\n" for p in pieces), encoding='utf-8')
        progress('joining_complete_video', captions=captions)
        command([DEFAULT_FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat',
                 '-safe', '0', '-i', playlist, '-map', '0:v:0', '-c:v', 'copy', '-an',
                 '-movflags', '+faststart', FINAL[captions]])
        files.append(probe_and_decode(DEFAULT_FFMPEG, FINAL[captions], DURATION, DURATION*30))
    for path, expected in prefix_hashes.items():
        if sha(ROOT/path) != expected:
            raise ValueError('Approved prefix changed: '+path)
    qa = OUT / 'verificacao_final'
    qa.mkdir(exist_ok=True)
    samples = [1, 21, 39, 45, 61, 83, 99, 112, 135, 161, 198, 221,
               223.9, 224.1, 227, 232.5, 240, 247, 253, 265.8, 276.5, 283.5,
               286.1, 289, 298.3, 310, 316.5, 325.4, 329, 337,
               340.1, 343, 358.5, 363.5, 372, 386.8,
               388.1, 391, 400, 409, 417, 425, 435, 449, 457.5, 463.5, 466.5, 473,
               476.1, 482, 492, 501, 510, 517, 524, 529.5, 533, 539, 546.5, 549.5]
    paths = []
    progress('extracting_final_review_frames', count=len(samples))
    for t in samples:
        target = qa / f't_{str(t).replace(".", "_")}.png'
        command([DEFAULT_FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-ss', t,
                 '-i', FINAL[True], '-frames:v', '1', '-update', '1', target])
        paths.append(str(target.relative_to(ROOT)))
    record = {
        'version': 8, 'status': 'encoded_pending_manual_final_review',
        'duration_seconds': DURATION, 'fps': 30, 'frame_count': DURATION*30,
        'resolution': [1920, 1080], 'files': files,
        'captioned_chapter_verification': chapter_files,
        'audio_tracks': 0, 'full_decode_errors': 0, 'sampled_frames': paths,
        'sampled_visual_review_passed': False, 'final_realtime_playback_reviewed': False,
        'approved_prefix_unchanged': True, 'approved_prefix_hashes': prefix_hashes,
        'approved_prefix_seconds': 224, 'new_animation_seconds': 326,
        'older_versions_modified': False, 'personal_footage_included': False,
        'narration_recorded': False, 'total_with_40s_personal_footage': 590,
        'maximum_animation_seconds': 560}
    atomic_json(OUT / 'verificacao_video_v8.json', record)
    write_player()
    print('V8_FULL_HD_COMPLETE', flush=True)


def write_player():
    chapters = [(0, 'Sol e GHI'), (40, 'Redes'), (100, 'Localidades e dados'),
                (154, 'Entradas e tarefas'), (224, 'Protocolo'), (286, 'Quantização'),
                (340, 'Como medir o erro'), (388, 'Resultados'), (476, 'Interpretação'),
                (513, 'Limitações'), (535, 'Síntese')]
    buttons = ''.join(f'<button type="button" data-t="{t}">{html.escape(label)}</button>' for t, label in chapters)
    options = ''.join(f'<option value="{p.name}">{label}</option>' for p, label in
                      [(FINAL[True], 'Full HD com legendas'), (MOBILE, 'Celular com legendas'),
                       (FINAL[False], 'Full HD sem legendas')])
    document = f'''<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vídeo TCC completo</title>
<style>body{{margin:0;background:#080a0d;color:#edf2f5;font:16px Segoe UI,Arial}}main{{max-width:1280px;margin:auto;padding:20px}}video{{width:100%;background:black}}nav{{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}}button,select{{background:#202a32;color:#edf2f5;border:1px solid #53616b;padding:10px;border-radius:6px}}a{{color:#75d4de}}p{{line-height:1.5}}</style>
<main><h1>Vídeo completo</h1><p>9min10s de animação · sem áudio, pronto para sua narração. Com sua abertura de 20s e seu encerramento de 20s: 9min50s.</p>
<video controls playsinline preload="metadata" src="{FINAL[True].name}"></video><nav>{buttons}<select aria-label="Versão">{options}</select></nav>
<p><a href="{NARRATION.name}">Falas para narrar</a> · <a href="{SRT.name}">Legendas SRT</a></p></main>
<script>const v=document.querySelector('video');document.querySelectorAll('[data-t]').forEach(b=>b.onclick=()=>{{v.currentTime=Number(b.dataset.t);v.play()}});document.querySelector('select').onchange=e=>{{const t=v.currentTime;const playing=!v.paused;v.src=e.target.value;v.onloadedmetadata=()=>{{v.currentTime=t;if(playing)v.play()}}}};</script></html>'''
    player = OUT / 'assistir_video_completo_v8.html'
    player.write_text(document, encoding='utf-8')
    relative = str(player.relative_to(ROOT))
    shortcut = ('@echo off\r\nstart "" "%~dp0'+relative+'"\r\n').encode('ascii')
    (ROOT / 'ASSISTIR_VIDEO_COMPLETO_V8.cmd').write_bytes(shortcut)


if __name__ == '__main__':
    compose()
