"""Record a human-reviewed delivery only after all independent audits pass."""
import argparse
from datetime import datetime, timezone
import json
import sys
from compose_v8 import ROOT, OUT, atomic_json, progress, sha
from compose_pilot import command


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sampled-review-complete', action='store_true', required=True)
    parser.parse_args()
    audit = json.loads((OUT/'audit_delivery_v8.json').read_text(encoding='utf-8'))
    prefix = json.loads((OUT/'verificacao_preservacao_prefixo_v8.json').read_text(encoding='utf-8'))
    independent_path = OUT/'revisao_final_independente_v8.json'
    independent = json.loads(independent_path.read_text(encoding='utf-8'))
    if (not audit['technical_ok'] or not prefix['approved_v7_prefix_preserved_pixel_exact']
            or independent['status'] != 'approved_sampled_scientific_and_visual_review'
            or independent['material_findings']):
        raise ValueError('Required delivery or independent review has not passed')
    path = OUT/'verificacao_video_v8.json'
    record = json.loads(path.read_text(encoding='utf-8'))
    for entry in record['files']+[record['mobile_preview']]:
        if sha(ROOT/entry['path']) != entry['sha256']:
            raise ValueError('Reviewed media changed: '+entry['path'])
    now = datetime.now(timezone.utc).isoformat()
    record.update(status='complete', sampled_visual_review_passed=True,
                  completed_utc=now, final_realtime_playback_reviewed=False,
                  independent_scientific_visual_review=str(independent_path.relative_to(ROOT)))
    record['manual_visual_review'] = {
        'reviewed_utc': now, 'automatically_approved': False,
        'scope': 'Root reviewed all five contact sheets, two individual Full HD frames, two mobile frames and one repaired uncaptioned frame; independent reviewer inspected all sixty sampled frames and eight individual Full HD frames.',
        'contact_sheets_reviewed': record['contact_sheets'],
        'additional_root_samples': [
            'verificacao_final/t_449.png', 'verificacao_final/t_546_5.png',
            'verificacao_final/mobile_400.png', 'verificacao_final/mobile_546_5.png',
            'verificacao_final/sem_400.png'],
        'material_findings_remaining': [], 'full_length_realtime_playback_reviewed': False}
    record['mobile_preview']['sampled_visual_review_passed'] = True
    record['mobile_preview']['client_playback_confirmed'] = False
    launcher = ROOT/'ASSISTIR_VIDEO_TCC.cmd'
    backup = ROOT/'ASSISTIR_VIDEO_TCC_ANTES_V8.cmd'
    if launcher.exists() and not backup.exists():
        backup.write_bytes(launcher.read_bytes())
    launcher.write_bytes((ROOT/'ASSISTIR_VIDEO_COMPLETO_V8.cmd').read_bytes())
    record['default_launcher'] = str(launcher.relative_to(ROOT))
    record['previous_launcher_backup'] = str(backup.relative_to(ROOT))
    atomic_json(path, record)
    command([sys.executable, ROOT/'codigo_fonte/video_ea019/audit_delivery_v8.py'])
    progress('complete', duration_seconds=550, files=record['files'],
             mobile_preview=record['mobile_preview'], manual_sampled_review_passed=True,
             independent_review_passed=True, prefix_pixel_exact=True)
    print('V8_COMPLETE_VERIFIED_AND_MANUALLY_REVIEWED', flush=True)


if __name__ == '__main__':
    main()
