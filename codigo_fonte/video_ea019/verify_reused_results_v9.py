"""Verify the approved 88-second V8 results interval in both final V9 exports.

Exactly four FFmpeg decode passes are used: two approved V8 clips and two
accurately sought V9 intervals. Compare 2640 decoded yuv420p frame MD5s per
variant in order, ignoring all timestamp fields. Only the audit JSON is written;
media, source modules, previous reports and frozen approvals remain read-only.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

from config_v9 import CHAPTERS, DURATION, OUT, ROOT
from verify_prefix_v8 import parse_framemd5, snapshot

V8 = ROOT/'documentacao/relatorio_final_ea019/video/completo_v8'
FFMPEG = ROOT/'.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
REPORT_PATH = OUT/'verificacao_resultados_preservados_v9.json'
TAGS = ('com_legendas', 'sem_legendas')
FPS, WIDTH, HEIGHT, FRAMES, SECONDS = 30, 1920, 1080, 2640, 88
FRAME_BYTES = WIDTH*HEIGHT*3//2
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def record_path(record):
    path = Path(str(record['path']).replace('\\', '/'))
    path = path.resolve() if path.is_absolute() else (ROOT/path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Input media path escapes the workspace')
    return path


def verified_record(entries, path, seconds, frames):
    found = [entry for entry in entries if record_path(entry) == path.resolve()]
    if len(found) != 1:
        raise ValueError('Expected exactly one completed file record for '+str(path))
    entry = found[0]
    expected = {'width': WIDTH, 'height': HEIGHT, 'fps': FPS,
                'duration_seconds': seconds, 'frame_count': frames,
                'audio_tracks': 0, 'full_decode_errors': 0}
    if any(entry.get(key) != value for key, value in expected.items()):
        raise ValueError('Unverified media metadata for '+str(path))
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(entry.get('sha256', ''))):
        raise ValueError('Missing media SHA256 for '+str(path))
    if not isinstance(entry.get('bytes'), int) or entry['bytes'] <= 1000:
        raise ValueError('Invalid declared media size for '+str(path))
    return entry


def decode_frames(path, ffmpeg, start_seconds=None):
    args = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-nostdin', '-threads', '2']
    # Input-side seek retains FFmpeg's default accurate seek when decoding.
    # The final V9 pass reads only the requested 420–508 s interval.
    if start_seconds is not None:
        args += ['-ss', str(start_seconds)]
    args += ['-i', str(path), '-map', '0:v:0', '-an',
             '-frames:v', str(FRAMES), '-pix_fmt', 'yuv420p',
             '-fps_mode', 'passthrough', '-threads', '2',
             '-f', 'framemd5', 'pipe:1']
    completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                               encoding='utf-8', errors='replace',
                               creationflags=NO_WINDOW, timeout=1800)
    if completed.returncode != 0 or completed.stderr.strip():
        raise RuntimeError('Pixel decode failed for '+str(path)+': '+completed.stderr[-6000:])
    decoded = parse_framemd5(completed.stdout)
    decoded.update(return_code=completed.returncode, stderr_empty=not completed.stderr.strip(),
                   input_seek_seconds=start_seconds, input_side_accurate_seek=True)
    return decoded


def write_report(report):
    temp = REPORT_PATH.with_suffix('.tmp')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temp, REPORT_PATH)


def run(ffmpeg=FFMPEG):
    spec = CHAPTERS['resultados']
    report = {'version': 9, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'failed', 'approved_v8_results_preserved_pixel_exact': False,
        'approved_v8_source_hashes_match': False,
        'v9_results_global_seconds': [spec['start'], spec['end']],
        'results_seconds': SECONDS, 'expected_frame_count_per_variant': FRAMES,
        'expected_resolution': [WIDTH, HEIGHT], 'expected_fps': FPS,
        'pixel_format': 'yuv420p', 'expected_decoding_passes': 4, 'decoding_passes_started': 0,
        'pixel_comparison': 'Ordered MD5 hashes of decoded frames; timestamps ignored',
        'timestamps_used_for_pixel_equality': False,
        'frame_count_size_dimensions_and_time_base_checked_separately': True,
        'variants': [], 'errors': [], 'gpu_jobs_started': False,
        'video_or_audio_encoding_performed': False, 'input_videos_modified_by_utility': False,
        'scope': 'Only the approved 88-second results chapter; not a full V9 duration or visual audit',
        'only_output_written': str(REPORT_PATH)}
    try:
        if (DURATION != 560 or spec['start'] != 420 or spec['end'] != 508
                or spec['duration'] != SECONDS or SECONDS*FPS != FRAMES):
            raise ValueError('Unexpected V9 results schedule; expected 420–508 s / 2640 frames')
        original_report_path = V8/'verificacao_video_v8.json'
        final_report_path = OUT/'verificacao_video_v9.json'
        originals = {tag: V8/'cenas'/f'resultados_{tag}_v8.mp4' for tag in TAGS}
        finals = {tag: OUT/f'Video_TCC_GHI_Revisado_{tag}_v9.mp4' for tag in TAGS}
        paths = [*originals.values(), *finals.values()]
        required = [Path(ffmpeg), original_report_path, final_report_path, *paths]
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise FileNotFoundError('Required final files are not ready: '+'; '.join(missing))
        if len({p.resolve() for p in paths}) != 4:
            raise ValueError('The four input MP4 paths must be distinct')
        report_snapshots_before = {str(path): snapshot(path)
                                   for path in (original_report_path, final_report_path)}
        old = json.loads(original_report_path.read_text(encoding='utf-8-sig'))
        new = json.loads(final_report_path.read_text(encoding='utf-8-sig'))
        if old.get('version') != 8 or new.get('version') != 9:
            raise ValueError('Unexpected version in approved V8 or final V9 verification')
        declarations = {}
        for tag in TAGS:
            key = 'captioned_chapter_verification' if tag == 'com_legendas' else 'uncaptioned_chapter_verification'
            declarations[tag] = {
                'approved_v8': verified_record(old.get(key, []), originals[tag], SECONDS, FRAMES),
                'final_v9': verified_record(new.get('files', []), finals[tag], DURATION, DURATION*FPS)}
        before = {tag: {'approved_v8': snapshot(originals[tag]), 'final_v9': snapshot(finals[tag])}
                  for tag in TAGS}
        checks = []
        for tag in TAGS:
            for role in ('approved_v8', 'final_v9'):
                actual, declared = before[tag][role], declarations[tag][role]
                matches = (actual['bytes'] == declared['bytes'] and
                           actual['sha256'] == declared['sha256'].lower())
                checks.append({'variant': tag, 'role': role, 'matches_completed_verification': matches,
                               'declared_sha256': declared['sha256'], 'actual_sha256': actual['sha256']})
        report['input_integrity_checks'] = checks
        report['approved_v8_source_hashes_match'] = all(x['matches_completed_verification']
                                                       for x in checks if x['role'] == 'approved_v8')
        report['final_v9_hashes_match_completed_verification'] = all(x['matches_completed_verification']
                                                                    for x in checks if x['role'] == 'final_v9')
        if not all(x['matches_completed_verification'] for x in checks):
            raise ValueError('An input differs from its completed verification SHA256 or size')
        for tag in TAGS:
            print(f'RESULTS_PIXEL_DECODE {tag} approved_v8 {FRAMES}frames', flush=True)
            report['decoding_passes_started'] += 1
            original = decode_frames(originals[tag], Path(ffmpeg))
            print(f'RESULTS_PIXEL_DECODE {tag} final_v9 seek={spec["start"]} {FRAMES}frames', flush=True)
            report['decoding_passes_started'] += 1
            interval = decode_frames(finals[tag], Path(ffmpeg), spec['start'])
            mismatch = [i+1 for i in range(max(original['frame_count'], interval['frame_count']))
                        if i >= original['frame_count'] or i >= interval['frame_count']
                        or original['hashes'][i] != interval['hashes'][i]]
            count_ok = original['frame_count'] == interval['frame_count'] == FRAMES
            size_ok = original['decoded_frame_bytes'] == interval['decoded_frame_bytes'] == [FRAME_BYTES]
            dimensions_ok = original['decoded_dimensions'] == interval['decoded_dimensions'] == [WIDTH, HEIGHT]
            fps_ok = original['decoded_fps'] == interval['decoded_fps'] == FPS
            equal = count_ok and size_ok and dimensions_ok and fps_ok and not mismatch
            report['variants'].append({'variant': tag, 'pixel_md5_equal': equal,
                'approved_v8_frames': original['frame_count'], 'v9_interval_frames': interval['frame_count'],
                'expected_frames': FRAMES, 'frame_count_matches': count_ok,
                'frame_size_matches': size_ok, 'resolution_matches': dimensions_ok, 'fps_matches': fps_ok,
                'decoded_frame_bytes': {'approved_v8': original['decoded_frame_bytes'], 'v9': interval['decoded_frame_bytes']},
                'decoded_resolution': {'approved_v8': original['decoded_dimensions'], 'v9': interval['decoded_dimensions']},
                'decoded_fps': {'approved_v8': original['decoded_fps'], 'v9': interval['decoded_fps']},
                'mismatch_count': len(mismatch), 'first_mismatched_frames_1based': mismatch[:20],
                'approved_v8_frame_hash_sequence_sha256': original['frame_hash_sequence_sha256'],
                'v9_interval_frame_hash_sequence_sha256': interval['frame_hash_sequence_sha256'],
                'decode_return_codes': [original['return_code'], interval['return_code']],
                'decode_stderr_empty': original['stderr_empty'] and interval['stderr_empty'],
                'interval_decode_errors': original['decode_errors']+interval['decode_errors'],
                'input_side_seek_seconds': spec['start'], 'accurate_seek_default_retained': True,
                'files_before': before[tag]})
            print(f'RESULTS_PIXEL_CHECKED {tag} {original["frame_count"]}/{interval["frame_count"]} '
                  f'frames pixel_equal={equal}', flush=True)
        after = {tag: {'approved_v8': snapshot(originals[tag]), 'final_v9': snapshot(finals[tag])}
                 for tag in TAGS}
        report['all_inputs_unchanged_during_check'] = before == after
        for variant in report['variants']:
            tag = variant['variant']
            variant['files_after'] = after[tag]
            variant['inputs_unchanged_during_check'] = before[tag] == after[tag]
        report_snapshots_after = {str(path): snapshot(path)
                                  for path in (original_report_path, final_report_path)}
        report['completed_verification_reports_unchanged'] = report_snapshots_before == report_snapshots_after
        report['completed_verification_reports_before'] = report_snapshots_before
        report['completed_verification_reports_after'] = report_snapshots_after
        passed = (report['decoding_passes_started'] == 4 and len(report['variants']) == 2
                  and report['all_inputs_unchanged_during_check']
                  and report['completed_verification_reports_unchanged']
                  and all(x['pixel_md5_equal'] and x['inputs_unchanged_during_check']
                          and x['interval_decode_errors'] == 0 and x['decode_stderr_empty']
                          for x in report['variants']))
        report['approved_v8_results_preserved_pixel_exact'] = passed
        report['status'] = 'passed' if passed else 'failed'
        if not passed:
            report['errors'].append('Pixel sequences, exact frame counts, or unchanged-input checks failed')
    except Exception as error:
        report['errors'].append(type(error).__name__+': '+str(error))
    report['completed_utc'] = datetime.now(timezone.utc).isoformat()
    write_report(report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ffmpeg', type=Path, default=FFMPEG)
    args = parser.parse_args(argv)
    report = run(args.ffmpeg)
    print(json.dumps({'report': str(REPORT_PATH), 'status': report['status'],
                      'approved_v8_results_preserved_pixel_exact': report['approved_v8_results_preserved_pixel_exact'],
                      'expected_frames_per_variant': FRAMES,
                      'decoding_passes_started': report['decoding_passes_started'],
                      'errors': report['errors']}, ensure_ascii=True, indent=2), flush=True)
    return 0 if report['status'] == 'passed' else 2


if __name__ == '__main__':
    raise SystemExit(main())
