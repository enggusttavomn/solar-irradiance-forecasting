"""Read-only independent V9 audit; writes only completo_v9/audit_delivery_v9.json.

--sources-only checks frozen approvals, scientific examples and planned speech.
The default additionally requires completed renders and every final export.
No Blender, GPU job, decoder, encoder, browser or network request is started.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import zlib
from urllib.parse import unquote, urlsplit

from audit_delivery_v8 import (Links, Snapshots, issue, mp4_headers, normalize,
                               normalize_hashes, parse_srt, path_key, read_json,
                               resolve)
from pipeline_v9 import CHAPTERS, DURATION, OUT, ROOT, SECTIONS, current_sources

V8 = ROOT/'documentacao/relatorio_final_ea019/video/completo_v8'
EXPECTED = [('introducao', 'intro_v9', 52), ('modelos', 'models_v9', 60),
            ('geografia', 'geography_data_v9', 60), ('entradas_tarefas', 'inputs_tasks_v9', 64),
            ('metodologia', 'methodology_v9', 54), ('quantizacao', 'quantization_v9', 64),
            ('metricas', 'metrics_v9', 66), ('resultados', 'results_v8', 88),
            ('conclusao', 'interpretation_v9', 52)]
FINAL_NAMES = {'Video_TCC_GHI_Revisado_com_legendas_v9.mp4',
               'Video_TCC_GHI_Revisado_sem_legendas_v9.mp4'}
PHONE_NAME = 'Video_TCC_GHI_Revisado_para_celular_v9.mp4'


def need(condition, errors, kind, **details):
    if not condition:
        issue(errors, kind, **details)
    return condition


def literal_assignments(path, names):
    values = {}
    for node in ast.parse(path.read_text(encoding='utf-8-sig')).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in names:
                    values[target.id] = ast.literal_eval(node.value)
    return values


def cues_equal_serialized_ms(actual, expected):
    # SRT serializes milliseconds while the plan can retain thirds of seconds.
    return (len(actual) == len(expected) and all(
        a.get('text') == b.get('text') and
        round(a['start']*1000) == round(b['start']*1000) and
        round(a['end']*1000) == round(b['end']*1000)
        for a, b in zip(actual, expected)))


def media(entry, seconds, frames, errors, snapshots, context, fps=30,
          resolution=(1920, 1080), require_decode=True):
    result = {'context': context, 'independent_header_checked': False,
              'video_decoded_by_this_audit': False,
              'source_full_decode_declaration_required': require_decode}
    try:
        path = resolve(entry['path'])
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError('Missing video or path outside workspace')
        snapshot = snapshots.get(path)
        result['snapshot'] = snapshot
        need(snapshot['bytes'] > 1000 and snapshot['bytes'] == entry.get('bytes'),
             errors, 'media_size_mismatch', context=context)
        need(snapshot['sha256'] == entry.get('sha256'), errors,
             'media_sha256_mismatch', context=context)
        if require_decode:
            need(entry.get('full_decode_errors') == 0, errors,
                 'missing_or_failed_complete_decode_record', context=context)
        header = mp4_headers(path)
        result.update(header=header, independent_header_checked=True)
        expected = {'duration_seconds': seconds, 'fps': fps, 'frame_count': frames,
                    'width': resolution[0], 'height': resolution[1], 'audio_tracks': 0}
        for field, value in expected.items():
            # Exact cadence is deliberate: V8 exposed a two-frame DTS gap
            # that FFmpeg's rounded "30 fps" summary did not reveal.
            need(header.get(field) == value, errors, 'actual_media_header_mismatch',
                 context=context, field=field, expected=value, actual=header.get(field))
            need(entry.get(field) == value, errors, 'declared_media_metadata_mismatch',
                 context=context, field=field, expected=value, actual=entry.get(field))
        need(header.get('sample_table_seconds') == seconds, errors,
             'nonuniform_total_sample_duration', context=context)
        need(header.get('codec_tag') in {'avc1', 'avc3'}, errors,
             'unexpected_codec', context=context)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, struct.error) as error:
        issue(errors, 'media_unreadable', context=context, error=str(error))
    return result


def source_audit(errors, warnings, snapshots, sources_only):
    need(SECTIONS == EXPECTED and DURATION == 560, errors, 'config_v9_schedule_changed')
    expected_config = {}
    cursor = 0
    for name, module, duration in EXPECTED:
        expected_config[name] = {'module': module, 'duration': duration,
                                 'start': cursor, 'end': cursor+duration}
        cursor += duration
    need(CHAPTERS == expected_config and cursor*30 == 16800, errors,
         'config_v9_incorrect_bounds_or_frame_count')
    gates = read_json(OUT/'qa_aprovado_v9.json', errors)
    expected_gate_names = set(CHAPTERS)-{'resultados'}
    need(set(gates) == expected_gate_names, errors, 'incorrect_eight_renderer_approval_set')
    records, manifests = [], {}
    for name, spec in expected_config.items():
        record = read_json(OUT/'cenas'/f'{name}_manifesto_v9.json', errors)
        manifests[name] = record
        item = {'chapter': name, **spec, 'render_complete': record.get('render_complete') is True}
        for field, value in {'version': 9, 'chapter': name, **spec, 'fps': 30,
                             'frames': spec['duration']*30, 'resolution': [1920, 1080],
                             'samples': 16}.items():
            need(record.get(field) == value, errors, 'incorrect_chapter_metadata',
                 chapter=name, field=field, expected=value, actual=record.get(field))
        if name == 'resultados':
            old = read_json(V8/'cenas/resultados_manifesto_v8.json', errors)
            approval = read_json(V8/'qa_aprovado_v8.json', errors).get('resultados', {})
            frozen = normalize_hashes(old.get('source_hashes'), errors, 'approved V8 results')
            approved = normalize_hashes(approval.get('source_hashes'), errors, 'V8 results gate')
            actual = {key: snapshots.get(ROOT/key)['sha256'] for key in frozen}
            need(approval.get('approved') is True and approval.get('automatically_approved') is False,
                 errors, 'missing_original_results_manual_approval')
            need(frozen == approved == actual == normalize_hashes(record.get('source_hashes'), errors, 'V9 results reuse'),
                 errors, 'reused_results_frozen_sources_changed')
            need(record.get('source_fingerprint') == old.get('source_fingerprint'), errors,
                 'reused_results_fingerprint_changed')
            need(record.get('approved_v8_results_reused') is True and
                 resolve(record.get('raw_mp4')) == (V8/'cenas/resultados_3d_v8.mp4').resolve(),
                 errors, 'results_not_reusing_approved_v8_raw')
            for field in ('cues', 'main_results', 'deltas_from_full_precision',
                          'per_locality_leader_counts', 'daily_horizon_leaders', 'raw_verification'):
                need(record.get(field) == old.get(field), errors,
                     'reused_results_metadata_changed', field=field)
            item['approved_v8_results_sources_unchanged'] = frozen == approved == actual
        else:
            fingerprint, current = current_sources(spec['module'])
            actual = normalize_hashes(current, errors, name+' current_sources')
            gate = gates.get(name, {})
            approved = normalize_hashes(gate.get('source_hashes'), errors, name+' approval')
            manifest = normalize_hashes(record.get('source_hashes'), errors, name+' manifest')
            need(gate.get('approved') is True and gate.get('automatically_approved') is False,
                 errors, 'missing_manual_source_approval', chapter=name)
            need(approved == actual and gate.get('source_fingerprint') == fingerprint,
                 errors, 'approved_source_snapshot_changed', chapter=name)
            item.update(current_sources_count=len(actual), current_fingerprint=fingerprint,
                        approval_matches_current=approved == actual,
                        manifest_matches_current=manifest == actual and record.get('source_fingerprint') == fingerprint)
            if sources_only and not record.get('render_complete') and not item['manifest_matches_current']:
                warnings.append({'kind': 'pending_production_manifest_refresh', 'chapter': name})
            else:
                need(item['manifest_matches_current'], errors,
                     'render_manifest_source_snapshot_changed', chapter=name)
        if not sources_only:
            need(record.get('render_complete') is True and record.get('resolution_percentage') == 100,
                 errors, 'production_render_incomplete', chapter=name)
            item['raw_video'] = media(record.get('raw_verification', {}), spec['duration'],
                                      spec['duration']*30, errors, snapshots, name+' complete raw')
            need(record.get('raw_verification', {}).get('path') and
                 resolve(record['raw_verification']['path']) == resolve(record.get('raw_mp4')),
                 errors, 'raw_manifest_path_mismatch', chapter=name)
            if name != 'resultados':
                gpu = record.get('gpu', {})
                item['gpu'] = gpu
                need(gpu.get('renderer') == 'Intel(R) Arc(TM) B390 GPU' and
                     gpu.get('vendor') == 'Intel' and gpu.get('backend') == 'OPENGL' and
                     gpu.get('engine') == 'BLENDER_EEVEE_NEXT', errors,
                     'production_gpu_or_engine_differs_from_approved_device', chapter=name, actual=gpu)
                ranges = [(481, 570), (1531, 1800)] if name == 'modelos' else [(1, spec['duration']*30)]
                wanted = [(first, min(first+299, last)) for lo, last in ranges for first in range(lo, last+1, 300)]
                blocks = record.get('blocks', [])
                need([(b.get('first_frame'), b.get('last_frame')) for b in blocks] == wanted,
                     errors, 'production_block_coverage_mismatch', chapter=name)
                item['blocks'] = []
                for block in blocks:
                    first, last = block['first_frame'], block['last_frame']
                    count = last-first+1
                    need(block.get('source_fingerprint') == record.get('source_fingerprint') and
                         block.get('frame_count') == count, errors,
                         'render_block_provenance_mismatch', chapter=name, first=first)
                    declared = {**block, 'duration_seconds': count/30, 'fps': 30,
                                'width': 1920, 'height': 1080, 'audio_tracks': 0}
                    item['blocks'].append(media(declared, count/30, count, errors, snapshots,
                                                name+' block '+str(first), require_decode=False))
                if name == 'modelos':
                    need(record.get('approved_geometry_reused_ranges_seconds') == [[0, 16], [19, 51]],
                         errors, 'approved_model_geometry_reuse_ranges_changed')
        records.append(item)
    return records, manifests


def scientific_audit(manifests, errors, snapshots):
    result = {}
    try:
        geo, inputs = manifests['geografia'], manifests['entradas_tarefas']
        data_path = resolve(geo['distribution_source'])
        data = read_json(data_path, errors)
        locality = next(x for x in data['localities'] if str(x['id']) == '1')
        positive = sum(locality['positive_counts'])
        count = locality['positive_counts'][8]
        percent = count/positive*100
        example = {'locality': 'Camaçari', 'range_w_m2': [400, 450],
                   'left_closed_right_open': True, 'count': 881,
                   'positive_hours': 18496, 'percent': percent}
        need(count == 881 and positive == 18496 and data['bin_edges_w_m2'][8:10] == [400, 450]
             and geo.get('example_bin') == example, errors, 'real_frequency_example_mismatch')
        need(geo.get('distribution_source_sha256') == snapshots.get(data_path)['sha256'],
             errors, 'distribution_source_hash_mismatch')
        for field, expected in {'synthetic_distribution_or_history': False,
                'frequency_denominator': 'per-locality hours strictly GHI > 0',
                'all_ten_localities_shown': True, 'temporal_curve_and_histogram_distinguished': True,
                'no_factory_sensor_claim': True, 'zeros_separate': True}.items():
            need(geo.get(field) == expected, errors, 'geography_semantics_changed', field=field)
        need(len(data['localities']) == 10 and all(x['sample_count'] == 35064 for x in data['localities']),
             errors, 'hourly_distribution_source_scope_changed')
        tasks = {'hourly': [336, 72], 'daily': [365, 30], 'monthly1': [12, 1], 'monthly6': [12, 6]}
        need(inputs.get('tasks') == tasks and inputs.get('monthly_networks_trained_separately') is True,
             errors, 'forecast_windows_or_monthly_training_changed')
        need(inputs.get('real_intro_window_values') == locality['series_example']['values_w_m2'][5:11]
             == [19, 193, 439, 673.5, 867, 1001], errors, 'real_input_window_mismatch')
        need(inputs.get('embedding_geometry_illustrative_not_actual_weights') is True and
             inputs.get('task_curve_values_illustrative') is True, errors,
             'didactic_input_geometry_mislabeled')
        q = manifests['quantizacao']
        need(q.get('original_example_W_m2') == 437 and q.get('illustrative_scaler_min') == 0 and
             q.get('illustrative_scaler_max') == 1000 and q.get('levels') == [64, 128, 256],
             errors, 'quantization_example_scope_changed')
        expected_quant = []
        for levels in (64, 128, 256):
            index = round(.437*(levels-1))
            reconstructed = struct.unpack('<f', struct.pack('<f', index/(levels-1)))[0]
            expected_quant.append({'levels': levels, 'normalized_original': .437,
                'nearest_index': index, 'normalized_float32': reconstructed,
                'reconstructed_W_m2': reconstructed*1000,
                'input_absolute_difference_W_m2': abs(reconstructed*1000-437)})
        need(q.get('examples') == expected_quant, errors, 'quantization_numeric_example_mismatch')
        for field, expected in {'numerical_example_is_didactic': True, 'clipping_precedes_rounding': True,
                'continuous_control_uses_clipping': False, 'continuous_control_rounds': False,
                'locality_identifier_bypasses_quantizer': True, 'reconstructed_dtype': 'float32',
                'quantization_applies_to': 'input GHI only', 'weights_targets_outputs_continuous': True,
                'uniform_quantization_not_integer_network_inference': True, 'timestamps_unchanged': True}.items():
            need(q.get(field) == expected, errors, 'quantization_semantics_changed', field=field)
        m = manifests['metricas']
        reference, prediction = [0, 200, 600, 300, 0], [20, 170, 650, 270, 10]
        absolute = [abs(a-b) for a, b in zip(reference, prediction)]
        need(m.get('example_reference') == reference and m.get('example_prediction') == prediction and
             m.get('example_absolute_errors') == absolute and m.get('example_mae') == sum(absolute)/len(absolute) == 28,
             errors, 'mae_arithmetic_example_mismatch')
        for field, expected in {'numeric_example_is_not_an_experiment_result': True,
                'distance_is_vertical_at_same_time': True, 'zoom_reference_W_m2': 600,
                'zoom_prediction_W_m2': 650, 'zoom_absolute_error_W_m2': 50,
                'improvement_example_mae_plateaus': [28, 14, 0], 'mae_lower_is_better_for_same_task': True,
                'zero_means_all_example_predictions_match': True, 'macro_equal_locality_weight': .1,
                'cumulative_includes_steps_1_through_H': True, 'cumulative_includes_night': True}.items():
            need(m.get(field) == expected, errors, 'mae_semantics_changed', field=field)
        need(len(m.get('macro_localities', [])) == 10, errors, 'macro_locality_count_changed')
        r = manifests['resultados']
        for field in ('all_numeric_bar_axes_start_at_zero', 'small_differences_not_visually_exaggerated',
                      'tasks_have_separate_axis_scales_and_targets', 'selection_frozen_by_validation_not_reranked_on_test'):
            need(r.get(field) is True, errors, 'approved_results_comparison_semantics_changed', field=field)
        result = {'frequency_example': example, 'forecast_windows': tasks,
                  'quantization_example_didactic': expected_quant,
                  'mae_example_didactic': {'reference': reference, 'prediction': prediction,
                                          'absolute_errors': absolute, 'mae': 28, 'plateaus': [28, 14, 0]},
                  'automated_check_is_metadata_and_arithmetic_not_visual_approval': True}
    except (OSError, ValueError, KeyError, TypeError, StopIteration, RuntimeError) as error:
        issue(errors, 'scientific_metadata_unreadable', error=str(error))
    return result


def narration_audit(manifests, errors, warnings):
    result = {'checked': False, 'recorded_voice_alignment_reviewed': False}
    try:
        plan = read_json(OUT/'plano_video_v9.json', errors)
        v9 = literal_assignments(ROOT/'codigo_fonte/video_ea019/compose_v9.py', {'OPENING', 'VOICE_OVERRIDES9'})
        v8 = literal_assignments(ROOT/'codigo_fonte/video_ea019/compose_v8.py', {'NARRATION_OVERRIDES'})
        opening = v9['OPENING']
        phases = []
        for name, spec in CHAPTERS.items():
            for a, b, text in manifests[name]['cues']:
                text = v9['VOICE_OVERRIDES9'].get(name, {}).get((a, b),
                       v8['NARRATION_OVERRIDES'].get(name, {}).get((a, b), text))
                phases.append([a+spec['start'], b+spec['start'], text])
        for field, value in {'version': 9, 'duration': 560, 'fps': 30, 'frames': 16800,
                'personal_intro_seconds': 20, 'personal_outro_seconds': 0, 'total_with_personal_intro': 580,
                'opening_spoken_text': opening, 'phases': phases, 'chapters': CHAPTERS,
                'narration_recorded': False, 'personal_footage_included': False}.items():
            need(plan.get(field) == value, errors, 'narration_plan_mismatch', field=field)
        animation = parse_srt(OUT/'Legendas_Animacao_v9.srt')
        presented = parse_srt(OUT/'Legendas_Com_Apresentacao_v9.srt')
        need(animation[0]['start'] == 0 and animation[-1]['end'] == 560 and
             presented[0]['start'] == 0 and presented[-1]['end'] == 580,
             errors, 'caption_total_time_mismatch')
        need(cues_equal_serialized_ms(animation, plan.get('cues', [])), errors,
             'animation_captions_differ_from_plan')
        intro = [c for c in presented if c['end'] <= 20]
        shifted = [c for c in presented if c['start'] >= 20]
        need(intro and intro[-1]['end'] == 20 and normalize(' '.join(c['text'] for c in intro)) == normalize(opening),
             errors, 'spoken_opening_captions_mismatch')
        wanted = [{'start': c['start']+20, 'end': c['end']+20, 'text': c['text']} for c in animation]
        need(cues_equal_serialized_ms(shifted, wanted) and len(presented) == len(intro)+len(animation),
             errors, 'caption_intro_shift_not_exactly_20_seconds')
        cursor = 0
        for a, b, text in phases:
            need(a == cursor and b > a, errors, 'narration_phase_gap_or_overlap', start=a, end=b)
            contained = [c['text'] for c in animation if c['start'] >= a-.001 and c['end'] <= b+.001]
            need(normalize(' '.join(contained)) == normalize(text), errors, 'phase_captions_text_mismatch', start=a)
            cursor = b
        need(cursor == 560, errors, 'narration_does_not_end_at_560')
        speech = (OUT/'Falas_Para_Gravar_Video_v9.txt').read_text(encoding='utf-8-sig')
        blocks = re.findall(r'^(\d+:\d{2}\.\d)[\u2013-](\d+:\d{2}\.\d)(?:[^\n]*)\n([^\n]+)', speech, re.M)
        wanted_speech = [[0, 20, opening]]+[[a+20, b+20, text] for a, b, text in phases]
        need(len(blocks) == len(wanted_speech), errors, 'timed_speech_block_count_mismatch')
        def seconds(text):
            minutes, rest = text.split(':')
            return int(minutes)*60+float(rest)
        for (a, b, text), (ta, tb, body) in zip(wanted_speech, blocks):
            need(abs(seconds(ta)-a) < .051 and abs(seconds(tb)-b) < .051 and body == text,
                 errors, 'timed_speech_text_or_times_mismatch', start=a)
        continuous = (OUT/'Texto_Corrido_Para_Gravar_v9.txt').read_text(encoding='utf-8-sig')
        need(continuous == opening+'\n\n'+'\n\n'.join(text for a, b, text in phases)+'\n',
             errors, 'continuous_spoken_text_mismatch')
        fast = [i for i, c in enumerate(presented, 1)
                if c['end']-c['start'] < .75 or len(c['text'].replace('\n', ' '))/(c['end']-c['start']) > 25]
        if fast:
            warnings.append({'kind': 'planned_captions_need_recorded_voice_alignment', 'cues': fast})
        result.update(checked=True, opening_seconds=20, personal_outro_seconds=0,
                      animation_seconds=560, total_seconds=580, phases=len(phases),
                      animation_cues=len(animation), captions_with_opening=len(presented),
                      short_or_fast_planned_cues=fast, source_voice_overrides_read_without_importing_composer=True)
    except (OSError, ValueError, KeyError, TypeError, IndexError, SyntaxError) as error:
        issue(errors, 'narration_or_captions_unreadable', error=str(error))
    return result


def ass_events(path):
    text = path.read_text(encoding='utf-8-sig')
    if not re.search(r'^PlayResX:\s*1920\s*$', text, re.M) or not re.search(r'^PlayResY:\s*1080\s*$', text, re.M):
        raise ValueError('Incorrect ASS canvas')
    events = []
    for line in text.splitlines():
        if line.startswith('Dialogue: '):
            fields = line[10:].split(',', 9)
            if len(fields) != 10 or fields[3] != 'Caption':
                raise ValueError('Unexpected non-caption overlay')
            def stamp(v):
                h, m, s = v.split(':')
                return int(h)*3600+int(m)*60+float(s)
            events.append({'start': stamp(fields[1]), 'end': stamp(fields[2]),
                           'text': re.sub(r'^\{[^}]*\}', '', fields[9]).replace(r'\N', '\n')})
    return events


def chunk_audit(source, manifests, errors, snapshots):
    records = []
    chunks = source.get('chapters', [])
    need(len(chunks) == 18 and {(c.get('chapter'), c.get('captions')) for c in chunks} ==
         {(name, cap) for name in CHAPTERS for cap in (True, False)}, errors,
         'incorrect_eighteen_composed_chapter_set')
    animation = parse_srt(OUT/'Legendas_Animacao_v9.srt')
    old = read_json(V8/'verificacao_video_v8.json', errors)
    for chunk in chunks:
        name, captions = chunk.get('chapter'), chunk.get('captions')
        if name not in CHAPTERS or captions not in (True, False):
            continue
        spec = CHAPTERS[name]
        tag = 'com_legendas' if captions else 'sem_legendas'
        path = (V8/'cenas'/f'resultados_{tag}_v8.mp4' if name == 'resultados'
                else OUT/'cenas'/f'{name}_{tag}_v9.mp4')
        item = media(chunk, spec['duration'], spec['duration']*30, errors, snapshots, name+' '+tag)
        need(resolve(chunk.get('path')) == path.resolve(), errors,
             'composed_chapter_path_mismatch', chapter=name, captions=captions)
        cache = read_json(path.with_suffix('.compose.json'), errors)
        ass = path.with_suffix('.ass')
        try:
            raw_sha = snapshots.get(resolve(manifests[name]['raw_mp4']))['sha256']
            ass_sha = snapshots.get(ass)['sha256']
            need(cache.get('sources', {}).get('raw_sha256') == raw_sha and
                 cache.get('sources', {}).get('ass_sha256') == ass_sha and
                 cache.get('sha256') == snapshots.get(path)['sha256'], errors,
                 'composed_chapter_cache_provenance_mismatch', chapter=name, captions=captions)
            verification = {k: v for k, v in chunk.items() if k not in ('chapter', 'captions')}
            need(cache.get('verification') == verification, errors,
                 'composition_decode_record_mismatch', chapter=name, captions=captions)
            if name != 'resultados':
                need(cache.get('sources', {}).get('format') == 'x264_medium_crf18_cfr30_timescale15360',
                     errors, 'new_chapter_encoding_spec_changed', chapter=name)
            else:
                key = 'captioned_chapter_verification' if captions else 'uncaptioned_chapter_verification'
                previous = next(c for c in old[key] if resolve(c['path']) == path.resolve())
                need(verification == previous, errors, 'approved_v8_results_clip_changed', captions=captions)
                item['approved_v8_reused_clip_hash_matches'] = verification == previous
            events = ass_events(ass)
            expected = [c for c in animation if c['start'] >= spec['start']-.001 and
                        c['end'] <= spec['end']+.001] if captions else []
            need(len(events) == len(expected), errors,
                 'burned_caption_event_count_mismatch', chapter=name, captions=captions)
            for actual, wanted in zip(events, expected):
                need(abs(actual['start']-(wanted['start']-spec['start'])) <= .011 and
                     abs(actual['end']-(wanted['end']-spec['start'])) <= .011 and
                     actual['text'] == wanted['text'], errors,
                     'burned_caption_text_or_time_mismatch', chapter=name, start=wanted['start'])
            item['actual_ass_events_match_final_srt'] = len(events) == len(expected)
        except (OSError, ValueError, KeyError, RuntimeError, StopIteration) as error:
            issue(errors, 'composition_provenance_unreadable', chapter=name, error=str(error))
        records.append(item)
    for captions in (True, False):
        try:
            playlist = OUT/('concat_com_v9.txt' if captions else 'concat_sem_v9.txt')
            listed = []
            for line in playlist.read_text(encoding='utf-8').splitlines():
                if not line.startswith("file '") or not line.endswith("'"):
                    raise ValueError('Unexpected concat playlist syntax')
                listed.append(resolve(line[6:-1].replace("'\\''", "'")))
            tag = 'com_legendas' if captions else 'sem_legendas'
            wanted = [(V8/'cenas'/f'resultados_{tag}_v8.mp4' if name == 'resultados'
                       else OUT/'cenas'/f'{name}_{tag}_v9.mp4').resolve() for name in CHAPTERS]
            need(listed == wanted, errors, 'concat_order_or_reused_results_input_mismatch', captions=captions)
        except (OSError, ValueError) as error:
            issue(errors, 'concat_playlist_unreadable', error=str(error))
    return records


def png_info(path):
    """CRC/decompression integrity check using only the standard library."""
    data = path.read_bytes()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('Not a PNG')
    cursor, compressed, dimensions = 8, [], None
    complete = False
    while cursor+12 <= len(data):
        length = struct.unpack_from('>I', data, cursor)[0]
        tag = data[cursor+4:cursor+8]
        payload = data[cursor+8:cursor+8+length]
        if cursor+12+length > len(data):
            raise ValueError('Truncated PNG chunk')
        crc = struct.unpack_from('>I', data, cursor+8+length)[0]
        if zlib.crc32(tag+payload) & 0xffffffff != crc:
            raise ValueError('PNG CRC mismatch')
        if tag == b'IHDR':
            width, height, depth, color, comp, filt, interlace = struct.unpack('>IIBBBBB', payload)
            if depth != 8 or color not in (2, 6) or comp or filt or interlace:
                raise ValueError('Unexpected PNG encoding')
            dimensions = (width, height)
            channels = 3 if color == 2 else 4
        elif tag == b'IDAT':
            compressed.append(payload)
        elif tag == b'IEND':
            complete = True
            break
        cursor += length+12
    if not complete or dimensions is None:
        raise ValueError('Incomplete PNG')
    rows = zlib.decompress(b''.join(compressed))
    stride = width*channels+1
    if len(rows) != stride*height or any(rows[i] > 4 for i in range(0, len(rows), stride)):
        raise ValueError('Invalid PNG rows')
    return list(dimensions)


def review_assets(source, manifests, errors):
    expected_samples = []
    for name, spec in CHAPTERS.items():
        for local in manifests[name].get('qa_times', []):
            t = spec['start']+local
            if t < 560:
                expected_samples.append((OUT/'verificacao_final'/f't_{str(t).replace(".", "_")}.png').resolve())
    samples = [resolve(p) for p in source.get('sampled_frames', [])]
    sheets = [resolve(p) for p in source.get('contact_sheets', [])]
    need(samples == expected_samples and len(samples) == len(set(samples)), errors,
         'final_sample_frame_set_mismatch')
    need(len(sheets) == math.ceil(len(samples)/12), errors, 'contact_sheet_count_mismatch')
    records = []
    for index, path in enumerate(samples+sheets):
        item = {'path': str(path), 'png_integrity_checked': False}
        try:
            need(path.parent == (OUT/'verificacao_final').resolve(), errors, 'review_image_outside_review_directory')
            actual = png_info(path)
            wanted = [1920, 1080]
            if index >= len(samples):
                count = min(12, len(samples)-(index-len(samples))*12)
                wanted = [1920, math.ceil(count/3)*388]
            need(actual == wanted, errors, 'review_png_dimensions_mismatch', path=str(path), actual=actual)
            item.update(png_integrity_checked=True, dimensions=actual)
        except (OSError, ValueError, zlib.error, struct.error) as error:
            issue(errors, 'review_png_unreadable', path=str(path), error=str(error))
        records.append(item)
    return records


def final_audit(manifests, errors, snapshots):
    source = read_json(OUT/'verificacao_video_v9.json', errors)
    result = {'videos': [], 'visual_approval_automatically_granted': False,
              'source_manual_sampled_visual_review_passed': source.get('sampled_visual_review_passed') is True,
              'source_final_realtime_playback_reviewed': source.get('final_realtime_playback_reviewed') is True}
    need(source.get('status') in {'encoded_pending_manual_final_review', 'complete',
                                 'complete_pending_manual_visual_review'}, errors, 'final_delivery_not_ready')
    for field, value in {'version': 9, 'duration_seconds': 560, 'fps': 30, 'frame_count': 16800,
            'resolution': [1920, 1080], 'audio_tracks': 0, 'full_decode_errors': 0,
            'personal_intro_seconds_reserved': 20, 'personal_outro_seconds_reserved': 0,
            'total_with_personal_intro': 580, 'older_video_files_modified': False}.items():
        need(source.get(field) == value, errors, 'complete_delivery_metadata_mismatch', field=field)
    entries = source.get('files', [])
    need(len(entries) == 2 and {Path(str(e.get('path', '')).replace('\\', '/')).name for e in entries} == FINAL_NAMES,
         errors, 'incorrect_final_video_names_or_count')
    for entry in entries:
        result['videos'].append(media(entry, 560, 16800, errors, snapshots, 'final '+str(entry.get('path'))))
    phone = source.get('mobile_preview', {})
    need(Path(str(phone.get('path', '')).replace('\\', '/')).name == PHONE_NAME,
         errors, 'incorrect_phone_preview_name')
    result['phone'] = media(phone, 560, 13440, errors, snapshots, 'phone', fps=24, resolution=(1280, 720))
    need(result['phone'].get('header', {}).get('avc_profile_idc') == 66,
         errors, 'phone_not_h264_baseline')
    result['phone_client_playback_confirmed'] = phone.get('client_playback_confirmed') is True
    result['chapters'] = chunk_audit(source, manifests, errors, snapshots)
    result['results_reuse'] = {'global_seconds': [420, 508], 'frames': 2640,
        'provenance_checked_in_concat_inputs_and_approved_v8_hashes': True,
        'pixel_md5_comparison_performed_by_this_audit': False}
    result['review_images'] = review_assets(source, manifests, errors)
    try:
        player = OUT/'assistir_video_revisado_v9.html'
        parsed = Links()
        parsed.feed(player.read_text(encoding='utf-8-sig'))
        checked = []
        for value in parsed.refs:
            parts = urlsplit(value)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            path = (player.parent/unquote(parts.path)).resolve()
            exists = path.is_relative_to(ROOT) and path.is_file() and path.stat().st_size > 0
            need(exists, errors, 'player_link_missing', url=value)
            checked.append({'url': value, 'exists': exists})
        need({s['start'] for s in CHAPTERS.values()} <= set(parsed.seeks) and
             all(0 <= t < 560 for t in parsed.seeks), errors, 'player_chapter_seek_mismatch')
        need(FINAL_NAMES | {PHONE_NAME} <= {Path(unquote(urlsplit(v).path)).name for v in parsed.refs},
             errors, 'player_missing_video_version_choices')
        shortcut = (ROOT/'ASSISTIR_VIDEO_REVISADO_V9.cmd').read_text(encoding='ascii')
        match = re.search(r'start\s+""\s+"%~dp0([^\"]+)"', shortcut, re.I)
        need(match and (ROOT/match[1].replace('\\', '/')).resolve() == player.resolve(),
             errors, 'local_video_shortcut_invalid')
        result['player_links'] = checked
    except (OSError, ValueError) as error:
        issue(errors, 'player_or_shortcut_unreadable', error=str(error))
    return result


def run(sources_only=False):
    errors, warnings, snapshots = [], [], Snapshots()
    chapters, manifests = source_audit(errors, warnings, snapshots, sources_only)
    science = scientific_audit(manifests, errors, snapshots)
    narration = narration_audit(manifests, errors, warnings)
    final = None if sources_only else final_audit(manifests, errors, snapshots)
    target = OUT/'audit_delivery_v9.json'
    report = {'version': 9, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'mode': 'sources' if sources_only else 'delivery', 'technical_ok': not errors,
        'error_count': len(errors), 'errors': errors, 'warnings': warnings,
        'timeline': {'chapters': 9, 'animation_seconds': 560, 'animation_frames': 16800,
                     'fps': 30, 'personal_intro_seconds': 20, 'personal_outro_seconds': 0,
                     'total_with_personal_intro': 580},
        'chapters': chapters, 'science': science, 'narration': narration, 'final_delivery': final,
        'frozen_sources_modified': False, 'render_or_gpu_job_started': False,
        'video_decoding_performed': False, 'external_processes_started': False,
        'visual_approval_automatically_granted': False, 'only_output_written': str(target)}
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temp, target)
    return target, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources-only', action='store_true')
    args = parser.parse_args()
    target, report = run(sources_only=args.sources_only)
    print(json.dumps({key: report[key] for key in ('mode', 'technical_ok', 'error_count', 'errors', 'warnings', 'timeline')}
                     | {'report': str(target)}, ensure_ascii=True, indent=2), flush=True)
    return 0 if report['technical_ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
