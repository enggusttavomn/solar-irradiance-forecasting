"""Resolve the editorial timing and word/animation anchors into integer frames."""
from datetime import datetime, timezone
import math
from montagem_v10_common import ROOT, read, write, sha


def main():
    tmp = ROOT / 'tmp/montagem_final_v11'
    old_path = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v10/timeline_montagem_v10.json'
    editorial_path = tmp / 'plano_ritmo_editorial.json'
    anchors_path = tmp / 'ancoras_visuais.json'
    old, editorial, anchors = read(old_path), read(editorial_path), read(anchors_path)
    suggested = {row['index']: row for row in editorial['items']}
    offsets = {int(key): value for key, value in anchors['preferred_voice_offsets_seconds_by_phase'].items()}
    # Let the sentence anticipate the imminent histogram transition without an
    # extended quiet gap after "as barras agrupam esses valores por faixa".
    offsets[29] = 1.50
    items = []
    for original in old['items']:
        if original['kind'] != 'body':
            row = {'id': original['id'], 'frames': original['frames'],
                   'audio_offset_frames': 0, 'reason': 'Approved opening/recorded conclusion retained unchanged.'}
        else:
            index = original['index']
            proposal = suggested[index]
            lead = round(offsets[index] * 30) if index in offsets else proposal['suggested_audio_offset_frames']
            voice_frames = math.ceil(original['audio_samples'] / 1600 - 1e-8)
            native_frames = round((original['video_end'] - original['video_start']) * 30)
            frames = max(proposal['suggested_frames'], native_frames, lead + voice_frames + 6)
            row = {'id': original['id'], 'index': index, 'frames': frames,
                   'audio_offset_frames': lead, 'native_animation_frames': native_frames,
                   'animation_speed': 1., 'tail_hold_frames': frames - native_frames,
                   'reason': proposal['reason'], 'protection': proposal['protection'],
                   'source_word_event_anchor_used': index in offsets}
            if index == 29:
                row['reason'] += ' The transition sentence ends shortly before the histogram appears.'
        items.append(row)
    frames = sum(row['frames'] for row in items)
    assert frames <= 600 * 30
    output = {
        'version': 11, 'status': 'reviewed_ready_for_timeline',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'policy': 'All original body animations and pauses play at 1x. Voice is unchanged; lead-ins align explanations with construction and terminal holds keep finished results visible.',
        'prior_approximate_target_seconds': 560, 'academic_limit_seconds': 600,
        'rationale_for_new_duration': 'The user prioritizes visual pauses and comprehension; forcing 560 seconds would again require shortening useful actions/reading time.',
        'frames': frames, 'duration_seconds': frames / 30,
        'source_inputs': [{'path': str(p.relative_to(ROOT)), 'sha256': sha(p)}
                          for p in [old_path, editorial_path, anchors_path]],
        'critical_word_anchors': {
            'phase_64': {'voice_offset_frames': next(x for x in items if x['id'] == 'phase_64')['audio_offset_frames'],
                         'source_result_28_visible_at_seconds': 6., 'voice_number_28_local_onset_before_offset': 5.05},
            'phase_65': {'voice_offset_frames': next(x for x in items if x['id'] == 'phase_65')['audio_offset_frames'],
                         'source_forecast_convergence_starts_seconds': 2., 'voice_aproxima_local_onset_before_offset': 1.25},
            'phase_68': {'voice_offset_frames': next(x for x in items if x['id'] == 'phase_68')['audio_offset_frames'],
                         'source_sweep_finishes_seconds': 7.9, 'voice_72_local_onset_before_offset': 4.73,
                         'source_72_hours_label_visible_at_seconds': 8.},
        },
        'items': items,
    }
    write(tmp / 'plano_ritmo_v11.json', output)
    print(f'V11_PACING_PLAN: {frames} frames / {frames / 30:.6f} seconds; no accelerated animations')


if __name__ == '__main__':
    main()
