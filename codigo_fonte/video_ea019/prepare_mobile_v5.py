"""Create a complete, low-bandwidth V5 review copy in eight inline players.

Full HD delivery is read-only. Each self-contained fragment stays below 1 MB.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/completo_v5/previa_celular'
VIZ = Path('C:/Users/gusta/.codex/visualizations/2026/11/01/01a19860-10ec-70a2-bd13-50910b568b88')
FFMPEG = ROOT / '.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
SOURCE = OUT.parent / 'Video_TCC_GHI_6min55_com_legendas_v5.mp4'
BOUNDS = [0, 55, 105, 155, 205, 255, 310, 365, 415]


def run(args):
    result = subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr[-4000:])
    return result


def stamp(second):
    return f'{second // 60}:{second % 60:02d}'


def encode(index):
    start, end = BOUNDS[index:index + 2]
    duration = end - start
    target = OUT / f'trecho_{index + 1:02d}.mp4'
    stats = OUT / f'pass_{index + 1:02d}'
    for bitrate in (90000, 78000):
        common = ['-y', '-ss', start, '-i', SOURCE, '-t', duration, '-vf', 'scale=640:360,fps=12',
                  '-an', '-c:v', 'libx264', '-preset', 'medium', '-b:v', bitrate,
                  '-pix_fmt', 'yuv420p', '-profile:v', 'baseline', '-level', '3.0',
                  '-threads', '2', '-passlogfile', stats]
        run([*common, '-pass', '1', '-f', 'null', 'NUL'])
        run([*common, '-pass', '2', '-movflags', '+faststart', target])
        if target.stat().st_size <= 720000:
            break
    assert target.stat().st_size <= 720000, target
    decoded = run(['-nostats', '-progress', 'pipe:1', '-i', target, '-map', '0:v:0', '-f', 'null', '-'])
    import re
    frames = [int(x) for x in re.findall(r'^frame=(\d+)$', decoded.stdout, re.M)]
    assert frames[-1] == duration * 12 and not decoded.stderr.strip()
    # Read literal markup from the template, then insert the encoded media.
    text = (VIZ / 'video-v5-fragment-template.html').read_text(encoding='utf-8')
    label = f'Trecho {index + 1}/8 | {stamp(start)} - {stamp(end)}'
    fragment = text.replace('%%ROOT%%', f'video-v5-mobile-{index + 1:02d}').replace('%%LABEL%%', label)
    fragment = fragment.replace('%%VIDEO%%', base64.b64encode(target.read_bytes()).decode('ascii'))
    path = VIZ / f'video-v5-celular-{index + 1:02d}.html'
    path.write_text(fragment, encoding='utf-8')
    assert path.stat().st_size < 1000000
    assert '<!doctype' not in fragment.lower() and '%%' not in fragment
    print(f'MOBILE_PART_READY {index + 1}/8 {target.stat().st_size} bytes', flush=True)
    return {'part': index + 1, 'start': start, 'end': end, 'duration': duration,
            'frames': frames[-1], 'fps': 12, 'resolution': [640, 360],
            'mp4': str(target.relative_to(ROOT)), 'fragment': str(path),
            'fragment_bytes': path.stat().st_size, 'full_decode_errors': 0}


def main():
    assert SOURCE.is_file()
    OUT.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        parts = list(pool.map(encode, range(8)))
    assert sum(part['duration'] for part in parts) == 415
    report = {'purpose': 'Complete low-bandwidth mobile review; Full HD originals unchanged.',
              'source': str(SOURCE.relative_to(ROOT)), 'duration_seconds': 415,
              'quality': '640x360, 12fps, no audio, reduced bitrate for inline review',
              'parts': parts, 'client_playback_confirmed': False}
    (OUT / 'verificacao_previa_celular.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('MOBILE_V5_PREVIEW_READY', flush=True)


if __name__ == '__main__':
    main()
