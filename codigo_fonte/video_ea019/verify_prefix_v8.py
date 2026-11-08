"""Read-only pixel audit of the approved 224-second V7 prefix in V8.

Run after both final V8 exports exist. This utility never edits media, scenes,
or sources. It checks the approved V7 MP4 SHA256/size declarations, decodes
the first 224 seconds / 6720 frames of each corresponding version to yuv420p,
and compares MD5 hashes in decode order, ignoring timestamp/header fields.
Only completo_v8/verificacao_preservacao_prefixo_v8.json is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[2]
V7 = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/completo_v8'
FFMPEG = ROOT / '.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
REPORT_PATH = OUT / 'verificacao_preservacao_prefixo_v8.json'
SECONDS = 224
FRAME_COUNT = 6720
WIDTH, HEIGHT, FPS = 1920, 1080, 30
FRAME_BYTES = WIDTH * HEIGHT * 3 // 2
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(path: Path) -> dict:
    before = path.stat()
    digest = sha256(path)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError('Input changed while hashing: ' + str(path))
    return {'path': str(path.resolve()), 'bytes': after.st_size,
            'mtime_ns': after.st_mtime_ns, 'sha256': digest}


def resolved_record_path(record: dict) -> Path:
    path = Path(record['path'])
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def approved_source_records(report: dict) -> dict:
    if (report.get('status') != 'complete'
            or str(report.get('version')).lower().lstrip('v') != '7'
            or report.get('duration_seconds') != SECONDS
            or report.get('frame_count') != FRAME_COUNT
            or report.get('fps') != FPS
            or report.get('resolution') != [WIDTH, HEIGHT]
            or report.get('audio_tracks') != 0
            or report.get('full_decode_errors') != 0):
        raise RuntimeError('The V7 export report is not complete and technically verified.')
    records = {}
    for tag in ('com_legendas', 'sem_legendas'):
        filename = f'Video_GHI_Inicio_ate_Plano22_{tag}_v7.mp4'
        matches = [r for r in report.get('files', [])
                   if Path(r.get('path', '')).name == filename]
        if len(matches) != 1:
            raise RuntimeError(f'V7 report must declare exactly one {filename}.')
        record = matches[0]
        if (record.get('width') != WIDTH or record.get('height') != HEIGHT
                or record.get('fps') != FPS or record.get('frame_count') != FRAME_COUNT
                or record.get('duration_seconds') != SECONDS
                or record.get('audio_tracks') != 0 or record.get('full_decode_errors') != 0
                or not re.fullmatch(r'[0-9a-fA-F]{64}', str(record.get('sha256', '')))
                or not isinstance(record.get('bytes'), int) or record['bytes'] <= 0):
            raise RuntimeError('Invalid completed V7 file record: ' + filename)
        records[tag] = record
    return records


def parse_framemd5(output: str) -> dict:
    hashes, sizes, dimensions, time_base = [], set(), None, None
    for original in output.splitlines():
        line = original.strip()
        if not line:
            continue
        if line.startswith('#'):
            match = re.fullmatch(r'#dimensions\s+0:\s*(\d+)x(\d+)', line)
            if match:
                dimensions = [int(match[1]), int(match[2])]
            match = re.fullmatch(r'#tb\s+0:\s*(\d+)\s*/\s*(\d+)', line)
            if match:
                time_base = Fraction(int(match[1]), int(match[2]))
            continue
        fields = [value.strip() for value in line.split(',')]
        if (len(fields) != 6 or fields[0] != '0'
                or not re.fullmatch(r'[0-9a-fA-F]{32}', fields[-1])):
            raise RuntimeError('Unexpected framemd5 record: ' + line)
        # Stream DTS, PTS, and duration are not used for pixel equality.
        hashes.append(fields[-1].lower())
        sizes.add(int(fields[-2]))
    return {'hashes': hashes, 'frame_count': len(hashes),
            'decoded_frame_bytes': sorted(sizes), 'decoded_dimensions': dimensions,
            'decoded_time_base': str(time_base) if time_base else None,
            'decoded_fps': float(1 / time_base) if time_base else None,
            'frame_hash_sequence_sha256': hashlib.sha256(
                '\n'.join(hashes).encode('ascii')).hexdigest(),
            'decode_errors': 0}


def frame_md5(ffmpeg: Path, path: Path) -> dict:
    args = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-threads', '2', '-i', str(path), '-map', '0:v:0', '-an',
            '-t', str(SECONDS), '-frames:v', str(FRAME_COUNT),
            '-pix_fmt', 'yuv420p', '-threads', '2', '-f', 'framemd5', 'pipe:1']
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', creationflags=NO_WINDOW,
                            timeout=1800)
    if result.returncode != 0 or result.stderr.strip():
        raise RuntimeError('Frame MD5 decode failed for ' + str(path)
                           + ': ' + result.stderr[-6000:])
    return parse_framemd5(result.stdout)


def audio_tracks(ffmpeg: Path, path: Path) -> int:
    # With no output specified, FFmpeg returns a nonzero code after printing
    # stream metadata. That exit code is expected; a missing video is not.
    result = subprocess.run([str(ffmpeg), '-hide_banner', '-nostdin', '-i', str(path)],
                            cwd=ROOT, capture_output=True, text=True,
                            encoding='utf-8', errors='replace', creationflags=NO_WINDOW,
                            timeout=60)
    if not re.search(r'^\s*Stream #.*?Video:', result.stderr, re.M):
        raise RuntimeError('Cannot inspect video streams: ' + str(path)
                           + ': ' + result.stderr[-2000:])
    return len(re.findall(r'^\s*Stream #.*?Audio:', result.stderr, re.M))


def base_report() -> dict:
    return {'version': 8, 'generated_utc': datetime.now(timezone.utc).isoformat(),
            'status': 'failed', 'approved_v7_prefix_preserved_pixel_exact': False,
            'approved_v7_source_hashes_match': False,
            'prefix_seconds': SECONDS, 'expected_frame_count_per_variant': FRAME_COUNT,
            'expected_resolution': [WIDTH, HEIGHT], 'expected_fps': FPS,
            'pixel_format': 'yuv420p',
            'pixel_comparison': 'decoded per-frame MD5 in decode order',
            'timestamp_and_header_fields_ignored_for_pixel_equality': True,
            'header_dimensions_and_time_base_checked_separately': True,
            'v7_verification_encoding': 'utf-8-sig', 'variants': [], 'errors': [],
            'input_videos_modified_by_utility': False, 'audio_modified_by_utility': False,
            'video_or_audio_encoding_performed': False,
            'scope': 'Approved V7 sources and first224seconds of the final V8 exports; not a full V8 duration audit',
            'only_output_written': str(REPORT_PATH)}


def write_report(report: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    temp = REPORT_PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, REPORT_PATH)


def run(v8_paths: dict, verification_path: Path, ffmpeg: Path) -> dict:
    report = base_report()
    try:
        required = [ffmpeg, verification_path, *v8_paths.values()]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError('Required final files are not ready: ' + '; '.join(missing))
        verification_before = snapshot(verification_path)
        verification = json.loads(verification_path.read_text(encoding='utf-8-sig'))
        records = approved_source_records(verification)
        sources = {tag: resolved_record_path(record) for tag, record in records.items()}
        report['approved_v7_verification_file'] = verification_before
        all_paths = [*sources.values(), *v8_paths.values()]
        if len({path.resolve() for path in all_paths}) != 4:
            raise RuntimeError('The four input MP4 paths must be distinct.')
        before = {tag: {'approved_v7': snapshot(sources[tag]), 'v8': snapshot(v8_paths[tag])}
                  for tag in records}
        source_checks = {}
        for tag, record in records.items():
            source_checks[tag] = {
                'path': str(sources[tag]), 'declared_bytes': record['bytes'],
                'declared_sha256': record['sha256'].lower(),
                'actual_bytes': before[tag]['approved_v7']['bytes'],
                'actual_sha256': before[tag]['approved_v7']['sha256'],
                'matches': record['bytes'] == before[tag]['approved_v7']['bytes']
                           and record['sha256'].lower() == before[tag]['approved_v7']['sha256']}
        report['approved_v7_source_integrity'] = source_checks
        report['approved_v7_source_hashes_match'] = all(r['matches'] for r in source_checks.values())
        if not report['approved_v7_source_hashes_match']:
            raise RuntimeError('An approved V7 source differs from verificacao_video_v7.json.')
        for tag in records:
            print(f'PREFIX_DECODE_START {tag} approved_v7 {FRAME_COUNT}frames', flush=True)
            source_audio = audio_tracks(ffmpeg, sources[tag])
            target_audio = audio_tracks(ffmpeg, v8_paths[tag])
            original = frame_md5(ffmpeg, sources[tag])
            print(f'PREFIX_DECODE_START {tag} v8 {FRAME_COUNT}frames', flush=True)
            prefix = frame_md5(ffmpeg, v8_paths[tag])
            mismatch = [i + 1 for i in range(max(original['frame_count'], prefix['frame_count']))
                        if (i >= original['frame_count'] or i >= prefix['frame_count']
                            or original['hashes'][i] != prefix['hashes'][i])]
            count_ok = original['frame_count'] == prefix['frame_count'] == FRAME_COUNT
            size_ok = original['decoded_frame_bytes'] == prefix['decoded_frame_bytes'] == [FRAME_BYTES]
            resolution_ok = original['decoded_dimensions'] == prefix['decoded_dimensions'] == [WIDTH, HEIGHT]
            fps_ok = original['decoded_fps'] == prefix['decoded_fps'] == FPS
            after = {'approved_v7': snapshot(sources[tag]), 'v8': snapshot(v8_paths[tag])}
            unchanged = before[tag] == after
            equal = count_ok and size_ok and resolution_ok and fps_ok and not mismatch
            report['variants'].append({
                'variant': tag, 'pixel_md5_equal': equal,
                'approved_v7_frames': original['frame_count'], 'v8_prefix_frames': prefix['frame_count'],
                'expected_frames': FRAME_COUNT, 'frame_count_matches': count_ok,
                'frame_size_matches': size_ok, 'resolution_matches': resolution_ok, 'fps_matches': fps_ok,
                'decoded_frame_bytes': {'approved_v7': original['decoded_frame_bytes'], 'v8': prefix['decoded_frame_bytes']},
                'decoded_resolution': {'approved_v7': original['decoded_dimensions'], 'v8': prefix['decoded_dimensions']},
                'decoded_fps': {'approved_v7': original['decoded_fps'], 'v8': prefix['decoded_fps']},
                'mismatch_count': len(mismatch), 'first_mismatched_frames_1based': mismatch[:20],
                'approved_v7_frame_hash_sequence_sha256': original['frame_hash_sequence_sha256'],
                'v8_prefix_frame_hash_sequence_sha256': prefix['frame_hash_sequence_sha256'],
                'approved_v7_audio_tracks': source_audio, 'v8_audio_tracks': target_audio,
                'inputs_unchanged_during_check': unchanged,
                'files_before': before[tag], 'files_after': after,
                'full_prefix_decode_errors': original['decode_errors'] + prefix['decode_errors']})
            print(f'PREFIX_CHECKED {tag}: {original["frame_count"]}/{prefix["frame_count"]} '
                  f'frames pixel_equal={equal} unchanged={unchanged}', flush=True)
        # Re-check every input after both variants, including the first pair.
        final = {tag: {'approved_v7': snapshot(sources[tag]), 'v8': snapshot(v8_paths[tag])}
                 for tag in records}
        report['all_inputs_unchanged_during_check'] = before == final
        report['approved_v7_verification_unchanged'] = verification_before == snapshot(verification_path)
        passed = (len(report['variants']) == 2 and report['approved_v7_source_hashes_match']
                  and report['all_inputs_unchanged_during_check'] and report['approved_v7_verification_unchanged']
                  and all(r['pixel_md5_equal'] and r['inputs_unchanged_during_check']
                          and r['approved_v7_audio_tracks'] == r['v8_audio_tracks'] == 0
                          for r in report['variants']))
        report['approved_v7_prefix_preserved_pixel_exact'] = passed
        report['status'] = 'passed' if passed else 'failed'
        if not passed:
            report['errors'].append('Prefix equality, source integrity, metadata, audio, or unchanged-input check failed.')
    except Exception as error:
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    write_report(report)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v8-with-captions', type=Path,
                        default=OUT / 'Video_TCC_GHI_Completo_com_legendas_v8.mp4')
    parser.add_argument('--v8-without-captions', type=Path,
                        default=OUT / 'Video_TCC_GHI_Completo_sem_legendas_v8.mp4')
    parser.add_argument('--v7-verification', type=Path, default=V7 / 'verificacao_video_v7.json')
    parser.add_argument('--ffmpeg', type=Path, default=FFMPEG)
    args = parser.parse_args(argv)
    report = run({'com_legendas': args.v8_with_captions.resolve(),
                  'sem_legendas': args.v8_without_captions.resolve()},
                 args.v7_verification.resolve(), args.ffmpeg.resolve())
    print(json.dumps({'report': str(REPORT_PATH), 'status': report['status'],
                      'approved_v7_source_hashes_match': report['approved_v7_source_hashes_match'],
                      'approved_v7_prefix_preserved_pixel_exact': report['approved_v7_prefix_preserved_pixel_exact'],
                      'variants': len(report['variants']), 'frames_per_variant': FRAME_COUNT,
                      'errors': report['errors']}, ensure_ascii=True, indent=2), flush=True)
    return 0 if report['approved_v7_prefix_preserved_pixel_exact'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
