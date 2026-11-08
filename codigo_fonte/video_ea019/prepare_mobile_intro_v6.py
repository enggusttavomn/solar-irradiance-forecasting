"""Prepare four self-contained ten-second V6 review players after export.

Run only once verificacao_intro_v6.json declares the final export complete.
This script reads the Full HD source and the V5 literal fragment template;
it never changes the V5 deliverables, template, or the V6 Full HD files.
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
SOURCE = OUT / 'Revisao_00_40_com_legendas_v6.mp4'
FINAL_VERIFICATION = OUT / 'verificacao_intro_v6.json'
CLIPS = OUT / 'previa_celular'
VIZ = Path('C:/Users/gusta/.codex/visualizations/2026/11/01/01a19860-10ec-70a2-bd13-50910b568b88')
TEMPLATE = VIZ / 'video-v5-fragment-template.html'
FFMPEG = ROOT / '.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
REPORT = CLIPS / 'verificacao_previa_celular_v6.json'
PART_SECONDS = 10
PART_COUNT = 4
FPS = 24
WIDTH, HEIGHT = 768, 432
MAX_MP4_BYTES = 720000
MAX_FRAGMENT_BYTES = 1000000


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require_completed_export():
    """Reject incomplete/stale exports before creating any output files."""
    if not FINAL_VERIFICATION.is_file():
        raise RuntimeError('V6 export is not ready: verificacao_intro_v6.json does not exist.')
    report = json.loads(FINAL_VERIFICATION.read_text(encoding='utf-8-sig'))
    expected = {'status': 'complete', 'duration_seconds': 40, 'fps': 30,
                'frame_count': 1200, 'resolution': [1920, 1080],
                'full_decode_errors': 0, 'audio_tracks': 0}
    for key, value in expected.items():
        if report.get(key) != value:
            raise RuntimeError(f'V6 export is not ready: {key}={report.get(key)!r}; expected {value!r}.')
    if str(report.get('version')).lower().lstrip('v') != '6':
        raise RuntimeError('Unexpected final verification version.')
    entries = report.get('files', [])
    source_entry = None
    for entry in entries:
        declared = Path(entry.get('path', ''))
        candidate = declared if declared.is_absolute() else ROOT / declared
        if candidate.resolve() == SOURCE.resolve():
            source_entry = entry
            break
    if source_entry is None:
        raise RuntimeError('The completed report does not declare the expected captioned V6 source.')
    if (not SOURCE.is_file() or SOURCE.stat().st_size <= 0
            or SOURCE.stat().st_size != source_entry.get('bytes')
            or source_entry.get('full_decode_errors') != 0):
        raise RuntimeError('The V6 source is missing, partial, or differs from its completed verification.')
    digest = sha256(SOURCE)
    if digest != source_entry.get('sha256'):
        raise RuntimeError('The V6 source hash differs from its completed verification.')
    if not TEMPLATE.is_file() or not FFMPEG.is_file():
        raise RuntimeError('The literal fragment template or FFmpeg binary is missing.')
    return {'source': str(SOURCE), 'source_bytes': SOURCE.stat().st_size,
            'source_sha256': digest, 'verification': str(FINAL_VERIFICATION),
            'template_sha256': sha256(TEMPLATE)}


def run(args, check=True):
    result = subprocess.run([str(FFMPEG), '-hide_banner', '-loglevel', 'error', *map(str, args)],
                            cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if check and result.returncode:
        raise RuntimeError(result.stderr[-5000:])
    return result


def verify_clip(path):
    # FFmpeg's ordinary input inspection returns1 because no output is given.
    probe = subprocess.run([str(FFMPEG), '-hide_banner', '-i', str(path)],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    info = probe.stderr
    required_patterns = [r'Video:\s*h264\b', r'\b768x432\b', r'\b24(?:\.0+)? fps\b',
                         r'Duration:\s*00:00:10\.00']
    if any(not re.search(pattern, info) for pattern in required_patterns) or 'Audio:' in info:
        raise RuntimeError('Unexpected mobile clip metadata: '+info[-3000:])
    decoded = run(['-nostats', '-progress', 'pipe:1', '-i', path,
                   '-map', '0:v:0', '-f', 'null', '-'])
    frames = [int(value) for value in re.findall(r'^frame=(\d+)$', decoded.stdout, re.M)]
    if not frames or frames[-1] != PART_SECONDS * FPS or decoded.stderr.strip():
        raise RuntimeError('Mobile clip full-decode verification failed: '
                           +decoded.stderr[-2000:]+decoded.stdout[-1000:])
    return {'width': WIDTH, 'height': HEIGHT, 'fps': FPS,
            'frame_count': frames[-1], 'duration_seconds': PART_SECONDS,
            'codec': 'H.264 Constrained Baseline', 'audio_tracks': 0,
            'full_decode_errors': 0, 'sha256': sha256(path), 'bytes': path.stat().st_size}


class FragmentReader(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = []
        self.videos = []
        self.tags = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append(tag)
        if 'id' in attributes:
            self.ids.append(attributes['id'])
        if tag == 'video':
            self.videos.append(attributes)


def verify_fragment(text, root_id, video_bytes):
    reader = FragmentReader()
    reader.feed(text)
    if len(text.encode('utf-8')) >= MAX_FRAGMENT_BYTES:
        raise RuntimeError('Mobile fragment exceeds1MB.')
    if (reader.ids != [root_id] or len(reader.videos) != 1
            or any(tag in reader.tags for tag in ('html', 'head', 'body'))
            or '<!doctype' in text.lower() or '%%' in text or r'\"' in text):
        raise RuntimeError('Invalid literal mobile fragment markup.')
    video = reader.videos[0]
    if 'controls' not in video or 'playsinline' not in video:
        raise RuntimeError('The mobile player must have native controls and playsinline.')
    src = video.get('src', '')
    if not src.startswith('data:video/mp4;base64,'):
        raise RuntimeError('The mobile player must contain its local encoded media.')
    if base64.b64decode(src.split(',', 1)[1], validate=True) != video_bytes:
        raise RuntimeError('Embedded video differs from the verified mobile MP4.')
    if f"document.getElementById('{root_id}')" not in text:
        raise RuntimeError('The fragment script must address its unique root.')


def encode_part(index, template):
    start = index * PART_SECONDS
    end = start + PART_SECONDS
    target = CLIPS / f'trecho_{index + 1:02d}_v6.mp4'
    stats = CLIPS / f'pass_{index + 1:02d}_v6'
    used_bitrate = None
    verification = None
    reused = False
    if (target.is_file() and 0 < target.stat().st_size < MAX_MP4_BYTES
            and target.stat().st_mtime_ns >= SOURCE.stat().st_mtime_ns):
        try:
            verification = verify_clip(target)
            reused = True
        except RuntimeError:
            pass
    if verification is None:
        for bitrate in (420000, 350000, 280000):
            # At the source's final boundary, fps conversion may otherwise
            # emit239frames. A short cloned tail supplies the missing final
            # sample; the explicit frame cap retains exactly10s/240frames.
            video_filter = (f'scale={WIDTH}:{HEIGHT},fps={FPS},'
                            'tpad=stop_mode=clone:stop_duration=0.1')
            common = ['-y', '-ss', start, '-i', SOURCE, '-t', PART_SECONDS,
                      '-vf', video_filter, '-frames:v', PART_SECONDS * FPS, '-an',
                      '-c:v', 'libx264', '-preset', 'medium', '-b:v', bitrate,
                      '-pix_fmt', 'yuv420p', '-profile:v', 'baseline', '-level', '3.1',
                      '-threads', '2', '-passlogfile', stats]
            run([*common, '-pass', '1', '-f', 'null', 'NUL'])
            run([*common, '-pass', '2', '-movflags', '+faststart', target])
            if target.stat().st_size < MAX_MP4_BYTES:
                used_bitrate = bitrate
                break
        if used_bitrate is None:
            raise RuntimeError(f'Could not reduce part{index+1} below{MAX_MP4_BYTES}bytes.')
        verification = verify_clip(target)
    root_id = f'intro-v6-mobile-{index + 1:02d}'
    label = f'Trecho {index + 1}/4 | 0:{start:02d}–0:{end:02d}'
    fragment = (template.replace('%%ROOT%%', root_id).replace('%%LABEL%%', label)
                .replace('%%VIDEO%%', base64.b64encode(target.read_bytes()).decode('ascii')))
    verify_fragment(fragment, root_id, target.read_bytes())
    path = VIZ / f'intro-v6-celular-{index + 1:02d}.html'
    temporary = path.with_suffix('.html.tmp')
    temporary.write_text(fragment, encoding='utf-8')
    temporary.replace(path)
    # Verify the literal fragment again after writing it to the durable root.
    verify_fragment(path.read_text(encoding='utf-8'), root_id, target.read_bytes())
    print(f'V6_MOBILE_PART_READY {index + 1}/4 {verification["bytes"]}bytes', flush=True)
    return {'part': index + 1, 'start_seconds': start, 'end_seconds': end,
            'mp4': str(target.relative_to(ROOT)), 'fragment': str(path),
            'fragment_bytes': path.stat().st_size, 'bitrate_bits_per_second': used_bitrate,
            'validated_clip_reused': reused, 'html_integrity_verified': True, **verification}


def prepare():
    """Guard final export, encode four clips, and return the written report."""
    source_check = require_completed_export()
    template = TEMPLATE.read_text(encoding='utf-8')
    if any(token not in template for token in ('%%ROOT%%', '%%LABEL%%', '%%VIDEO%%')):
        raise RuntimeError('The existing literal template has unexpected placeholders.')
    CLIPS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        parts = list(pool.map(lambda index: encode_part(index, template), range(PART_COUNT)))
    if (sum(part['duration_seconds'] for part in parts) != 40
            or sum(part['frame_count'] for part in parts) != 960):
        raise RuntimeError('Mobile preview coverage does not match40seconds at24fps.')
    if sha256(SOURCE) != source_check['source_sha256']:
        raise RuntimeError('The Full HD source changed during preview encoding.')
    if sha256(TEMPLATE) != source_check['template_sha256']:
        raise RuntimeError('The V5 literal template changed during preview encoding.')
    report = {'version': 6, 'status': 'complete',
              'generated_utc': datetime.now(timezone.utc).isoformat(),
              'purpose': 'Review of the revised first40seconds on mobile.',
              'duration_seconds': 40, 'parts': parts, 'source_verification': source_check,
              'resolution': [WIDTH, HEIGHT], 'fps': FPS, 'audio_tracks': 0,
              'full_decode_errors': 0, 'html_integrity_verified': True,
              'client_playback_confirmed': False,
              'source_v5_deliverables_modified': False,
              'source_full_hd_unchanged': True, 'v5_template_unchanged': True}
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('V6_MOBILE_PREVIEW_READY', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true',
                        help='Validate the completed Full HD export without creating clips or fragments.')
    args = parser.parse_args()
    if args.check_ready:
        print(json.dumps(require_completed_export(), ensure_ascii=True, indent=2))
    else:
        report = prepare()
        print(json.dumps({'report': str(REPORT), 'parts': len(report['parts']),
                          'duration_seconds': report['duration_seconds'],
                          'client_playback_confirmed': False}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
