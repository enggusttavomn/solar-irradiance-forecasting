"""Normalize only new uncaptioned chapters; preserve the approved prefix/media."""
import json
import sys
from compose_v8 import (ROOT, OUT, PREFIX, CHAPTERS, DURATION, FINAL, atomic_json,
                        encode_chapter, prepare, sha, progress)
from compose_pilot import DEFAULT_FFMPEG, command, probe_and_decode


def main():
    report_path = OUT/'verificacao_video_v8.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    unchanged = {FINAL[True]: sha(FINAL[True]),
                 OUT/'Video_TCC_GHI_Completo_para_celular_v8.mp4':
                 sha(OUT/'Video_TCC_GHI_Completo_para_celular_v8.mp4')}
    records, _ = prepare()
    pieces = [PREFIX/'Video_GHI_Inicio_ate_Plano22_sem_legendas_v7.mp4']
    checks = []
    for record, (name, start, duration) in zip(records, CHAPTERS):
        target, check = encode_chapter(record, name, duration, False)
        pieces.append(target)
        checks.append(check)
        print('V8_NO_CAPTIONS_NORMALIZED '+name, flush=True)
    playlist = OUT/'concat_sem_legendas_v8.txt'
    playlist.write_text(''.join("file '"+p.as_posix().replace("'", "'\\''")+"'\n" for p in pieces), encoding='utf-8')
    command([DEFAULT_FFMPEG, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat',
             '-safe', '0', '-i', playlist, '-map', '0:v:0', '-c:v', 'copy', '-an',
             '-movflags', '+faststart', FINAL[False]])
    verified = probe_and_decode(DEFAULT_FFMPEG, FINAL[False], DURATION, DURATION*30)
    report['files'] = [entry if 'com_legendas_v8.mp4' in entry['path'] else verified
                       for entry in report['files']]
    report['uncaptioned_chapter_verification'] = checks
    report['uncaptioned_cfr_normalized_after_timestamp_audit'] = True
    for path, digest in unchanged.items():
        if sha(path) != digest:
            raise ValueError('Other final media changed: '+str(path))
    atomic_json(report_path, report)
    command([sys.executable, ROOT/'codigo_fonte/video_ea019/verify_prefix_v8.py'])
    command([sys.executable, ROOT/'codigo_fonte/video_ea019/audit_delivery_v8.py'])
    progress('complete_pending_manual_visual_review', duration_seconds=DURATION,
             files=report['files'], mobile_preview=report['mobile_preview'])
    print('V8_NO_CAPTIONS_REPAIR_PASSED', flush=True)


if __name__ == '__main__':
    main()
