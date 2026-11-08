"""Compare decoded pixels of the approved V6 intro and the V7 video prefix.

Read-only for all videos. Run after verificacao_video_v7.json is complete.
For each caption variant, decode the first40seconds/1200frames as yuv420p,
then compare frame MD5 sequences while ignoring headers and timestamp fields.
Only verificacao_preservacao_intro_v7.json is written.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
INTRO = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
FFMPEG = ROOT / '.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
REPORT_PATH = OUT / 'verificacao_preservacao_intro_v7.json'
SECONDS = 40
FRAME_COUNT = 1200
EXPECTED_FRAME_BYTES = 1920 * 1080 * 3 // 2


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(path):
    return {'path': str(path), 'bytes': path.stat().st_size,
            'mtime_ns': path.stat().st_mtime_ns, 'sha256': sha256(path)}


def declared_record(report, path):
    for entry in report.get('files', []):
        declared = Path(entry.get('path', ''))
        resolved = declared.resolve() if declared.is_absolute() else (ROOT / declared).resolve()
        if resolved == path.resolve():
            return entry
    raise RuntimeError('Completed export report does not declare '+str(path))


def require_complete_report(path, version):
    report = json.loads(path.read_text(encoding='utf-8-sig'))
    if (report.get('status') != 'complete'
            or str(report.get('version')).lower().lstrip('v') != str(version)
            or report.get('fps') != 30 or report.get('full_decode_errors') != 0
            or report.get('audio_tracks') != 0):
        raise RuntimeError('Export is not complete and verified: '+str(path))
    return report


def audio_tracks(path):
    probe = subprocess.run([str(FFMPEG), '-hide_banner', '-i', str(path)],
                           cwd=ROOT, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if 'Video:' not in probe.stderr:
        raise RuntimeError('Cannot inspect video streams: '+probe.stderr[-2000:])
    return len(re.findall(r'^\s*Stream #.*?Audio:', probe.stderr, re.M))


def frame_md5(path):
    args = [str(FFMPEG), '-hide_banner', '-loglevel', 'error', '-i', str(path),
            '-map', '0:v:0', '-an', '-t', str(SECONDS), '-frames:v', str(FRAME_COUNT),
            '-pix_fmt', 'yuv420p', '-f', 'framemd5', 'pipe:1']
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode or result.stderr.strip():
        raise RuntimeError('Frame MD5 decode failed: '+result.stderr[-5000:])
    hashes = []
    sizes = set()
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        fields = [field.strip() for field in line.split(',')]
        if len(fields) < 6 or not re.fullmatch(r'[0-9a-fA-F]{32}', fields[-1]):
            raise RuntimeError('Unexpected framemd5 record: '+line)
        # Stream, DTS, PTS and duration fields are intentionally ignored.
        hashes.append(fields[-1].lower())
        sizes.add(int(fields[-2]))
    return {'hashes': hashes, 'frame_count': len(hashes),
            'decoded_frame_bytes': sorted(sizes),
            'frame_hash_sequence_sha256': hashlib.sha256('\n'.join(hashes).encode('ascii')).hexdigest(),
            'decode_errors': 0}


def run():
    v6_report = require_complete_report(INTRO / 'verificacao_intro_v6.json', 6)
    v7_report = require_complete_report(OUT / 'verificacao_video_v7.json', 7)
    records = []
    for tag in ('com_legendas', 'sem_legendas'):
        source = INTRO / f'Revisao_00_40_{tag}_v6.mp4'
        target = OUT / f'Video_GHI_Inicio_ate_Plano22_{tag}_v7.mp4'
        before = {'approved_v6': snapshot(source), 'v7': snapshot(target)}
        for name, report, path in [('approved_v6', v6_report, source), ('v7', v7_report, target)]:
            declared = declared_record(report, path)
            if (declared.get('bytes') != before[name]['bytes']
                    or declared.get('sha256') != before[name]['sha256']
                    or declared.get('full_decode_errors') != 0):
                raise RuntimeError('Video differs from its completed export verification: '+str(path))
        source_audio, target_audio = audio_tracks(source), audio_tracks(target)
        original = frame_md5(source)
        prefix = frame_md5(target)
        mismatch = [i + 1 for i in range(max(len(original['hashes']), len(prefix['hashes'])))
                    if (i >= len(original['hashes']) or i >= len(prefix['hashes'])
                        or original['hashes'][i] != prefix['hashes'][i])]
        after = {'approved_v6': snapshot(source), 'v7': snapshot(target)}
        count_ok = original['frame_count'] == prefix['frame_count'] == FRAME_COUNT
        size_ok = (original['decoded_frame_bytes'] == prefix['decoded_frame_bytes']
                   == [EXPECTED_FRAME_BYTES])
        unchanged = before == after
        equal = count_ok and size_ok and not mismatch
        records.append({'variant': tag, 'pixel_md5_equal': equal,
                        'approved_v6_frames': original['frame_count'], 'v7_prefix_frames': prefix['frame_count'],
                        'expected_frames': FRAME_COUNT, 'frame_size_matches': size_ok,
                        'mismatch_count': len(mismatch), 'first_mismatched_frames_1based': mismatch[:20],
                        'approved_v6_frame_hash_sequence_sha256': original['frame_hash_sequence_sha256'],
                        'v7_prefix_frame_hash_sequence_sha256': prefix['frame_hash_sequence_sha256'],
                        'approved_v6_audio_tracks': source_audio, 'v7_audio_tracks': target_audio,
                        'inputs_unchanged_during_check': unchanged, 'files_before': before, 'files_after': after,
                        'full_prefix_decode_errors': original['decode_errors'] + prefix['decode_errors']})
        print(f'PREFIX_CHECKED {tag}: {original["frame_count"]}/{prefix["frame_count"]} '
              f'frames equal={equal}', flush=True)
    passed = (len(records) == 2 and all(r['pixel_md5_equal'] and r['inputs_unchanged_during_check']
              and r['approved_v6_audio_tracks'] == r['v7_audio_tracks'] == 0 for r in records))
    report = {'version': 7, 'generated_utc': datetime.now(timezone.utc).isoformat(),
              'status': 'passed' if passed else 'failed', 'approved_intro_preserved_pixel_exact': passed,
              'prefix_seconds': SECONDS, 'expected_frame_count_per_variant': FRAME_COUNT,
              'pixel_format': 'yuv420p', 'pixel_comparison': 'decoded per-frame MD5 in decode order',
              'timestamp_and_header_fields_ignored': True, 'variants': records,
              'input_videos_modified_by_utility': False, 'audio_modified_by_utility': False,
              'video_or_audio_encoding_performed': False, 'only_output_written': str(REPORT_PATH)}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    report = run()
    print(json.dumps({'report': str(REPORT_PATH), 'status': report['status'],
                      'approved_intro_preserved_pixel_exact': report['approved_intro_preserved_pixel_exact'],
                      'variants': len(report['variants']), 'frames_per_variant': FRAME_COUNT},
                     ensure_ascii=True, indent=2), flush=True)
    return 0 if report['approved_intro_preserved_pixel_exact'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
