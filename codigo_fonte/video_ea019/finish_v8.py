"""Wait for the production queue, then encode and verify the complete delivery."""
from datetime import datetime, timezone
import json
import re
import subprocess
import sys
import time
from compose_v8 import (ROOT, OUT, PREFIX, CHAPTERS, DURATION, FINAL, MOBILE,
                        atomic_json, sha, compose, progress)
from compose_pilot import DEFAULT_FFMPEG, command


def ready():
    queue = OUT / 'fila_render_v8.json'
    if queue.exists():
        try:
            state = json.loads(queue.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return False
        if state.get('failed'):
            raise RuntimeError('Production queue failed: '+str(state['failed']))
        # Do not hold production manifests open while the renderer replaces
        # them. Inspect them only after the queue declares all five complete.
        if len(state.get('complete', [])) != len(CHAPTERS):
            return False
    else:
        return False
    for name, start, duration in CHAPTERS:
        path = OUT / 'cenas' / f'{name}_manifesto_v8.json'
        if not path.exists():
            return False
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            return False
        if not record.get('render_complete') or record.get('resolution_percentage') != 100:
            return False
    return True


def contacts():
    sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
    from PIL import Image, ImageDraw, ImageFont
    qa = OUT / 'verificacao_final'
    files = sorted(qa.glob('t_*.png'), key=lambda p: float(p.stem[2:].replace('_', '.')))
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 21)
    result = []
    for group, offset in enumerate(range(0, len(files), 12), 1):
        subset = files[offset:offset+12]
        width, height = 640, 388
        image = Image.new('RGB', (width*3, height*((len(subset)+2)//3)), (9, 11, 13))
        draw = ImageDraw.Draw(image)
        for i, path in enumerate(subset):
            x, y = i%3*width, i//3*height
            with Image.open(path) as source:
                if source.size != (1920, 1080):
                    raise ValueError('Final sample resolution mismatch')
                image.paste(source.resize((640, 360), Image.Resampling.LANCZOS), (x, y+28))
            t = float(path.stem[2:].replace('_', '.'))
            draw.text((x+8, y), f'{int(t)//60}:{t%60:04.1f}', font=font, fill=(210, 222, 230))
        target = qa / f'contato_v8_{group}.png'
        image.save(target)
        result.append(str(target.relative_to(ROOT)))
    return result


def mobile():
    command([DEFAULT_FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-i', FINAL[True],
             '-vf', 'scale=1280:720,fps=24,tpad=stop_mode=clone:stop_duration=0.1',
             '-frames:v', DURATION*24, '-t', DURATION, '-an', '-c:v', 'libx264',
             '-preset', 'medium', '-crf', '23', '-profile:v', 'baseline', '-level', '3.1',
             '-pix_fmt', 'yuv420p', '-threads', '6', '-movflags', '+faststart', MOBILE])
    info = subprocess.run([str(DEFAULT_FFMPEG), '-hide_banner', '-i', str(MOBILE)],
                          capture_output=True, text=True, encoding='utf-8', errors='replace').stderr
    if ('1280x720' not in info or '24 fps' not in info or 'Video: h264' not in info
            or 'Duration: 00:09:10.00' not in info or 'Audio:' in info):
        raise ValueError('Mobile metadata differs: '+info)
    decoded = command([DEFAULT_FFMPEG, '-hide_banner', '-loglevel', 'error', '-nostats',
                       '-progress', 'pipe:1', '-i', MOBILE, '-map', '0:v:0', '-f', 'null', '-'])
    frames = [int(v) for v in re.findall(r'^frame=(\d+)$', decoded.stdout, re.M)]
    if not frames or frames[-1] != DURATION*24 or decoded.stderr.strip():
        raise ValueError('Mobile full decode failed')
    return {'path': str(MOBILE.relative_to(ROOT)), 'bytes': MOBILE.stat().st_size,
            'sha256': sha(MOBILE), 'width': 1280, 'height': 720, 'fps': 24,
            'frame_count': DURATION*24, 'duration_seconds': DURATION,
            'codec': 'H.264 Baseline', 'audio_tracks': 0, 'full_decode_errors': 0,
            'client_playback_confirmed': False}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print('V8_FINISHER_WAITING_FOR_FIVE_CHAPTERS', flush=True)
    while not ready():
        time.sleep(5)
    command([sys.executable, ROOT/'codigo_fonte/video_ea019/audit_delivery_v8.py', '--renders-only'])
    compose()
    sheets = contacts()
    progress('encoding_mobile')
    phone = mobile()
    report = OUT / 'verificacao_video_v8.json'
    record = json.loads(report.read_text(encoding='utf-8'))
    record.update(mobile_preview=phone, contact_sheets=sheets,
                  encoded_utc=datetime.now(timezone.utc).isoformat())
    atomic_json(report, record)
    command([sys.executable, ROOT/'codigo_fonte/video_ea019/verify_prefix_v8.py'])
    command([sys.executable, ROOT/'codigo_fonte/video_ea019/audit_delivery_v8.py'])
    progress('complete_pending_manual_visual_review', duration_seconds=DURATION,
             files=record['files'], mobile_preview=phone)
    print('V8_DELIVERY_READY_FOR_MANUAL_REVIEW', flush=True)


if __name__ == '__main__':
    main()
