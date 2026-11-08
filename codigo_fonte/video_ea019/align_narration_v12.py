"""Monotonic word-level alignment of the new narration, without editing audio.

Times always address full decoded PCM sample zero. Later-take exclusions and
independently checked ASR replacement windows come from the reviewed manifest.
The canonical script is an alignment reference, never evidence of spoken words.
"""
from __future__ import annotations

from array import array
from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
AUDIO = ROOT / 'tmp/montagem_final_v12/audio'
SCRIPT = ROOT / 'documentacao/relatorio_final_ea019/video/roteiro_continuo_v12/narracao_continua_v12.json'
RAW = AUDIO / 'transcript_raw.json'
MANIFEST = AUDIO / 'retakes_review_v12.json'
OUTPUT = AUDIO / 'paragraph_alignment_v12.json'
FALLBACK_EXCLUDES = [[265.0, 274.7], [397.4, 405.5]]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def plain(value):
    return unicodedata.normalize('NFKD', value.lower()).encode('ascii', 'ignore').decode()


ONES = ['', 'um', 'dois', 'tres', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove', 'dez',
        'onze', 'doze', 'treze', 'catorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
TENS = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
HUNDREDS = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']
ALIASES = {
    'informar': 'informer', 'informa': 'informer', 'informe': 'informer', 'inform': 'informer',
    'transfomer': 'transformer', 'transforme': 'transformer',
    'gh': 'ghi', 'he': 'ghi', 'catorze': 'quatorze', 'duas': 'dois', 'watts': 'watt', 'metros': 'metro',
    'quadrados': 'quadrado', 'zeros': 'zero', 'photovoltaica': 'fotovoltaica', 'medio': 'medio',
}
ACRONYMS = {'ghi': ['ge', 'aga', 'i'], 'dni': ['de', 'ene', 'i'],
            'nsrdb': ['ene', 'esse', 'erre', 'de', 'be'],
            'lstm': ['ele', 'esse', 'te', 'eme'], 'mae': ['eme', 'a', 'e']}
NUMBER_TOKENS = set(ONES[1:] + TENS[2:] + HUNDREDS[1:] + ['zero', 'cem', 'mil', 'quatorze', 'virgula'])
MODELS = {'transformer', 'informer'}


def integer(number):
    if number == 0:
        return 'zero'
    if number < 20:
        return ONES[number]
    if number < 100:
        return TENS[number // 10] + (' e ' + integer(number % 10) if number % 10 else '')
    if number == 100:
        return 'cem'
    if number < 1000:
        return HUNDREDS[number // 100] + (' e ' + integer(number % 100) if number % 100 else '')
    if number < 1000000:
        thousands, remainder = divmod(number, 1000)
        result = ('mil' if thousands == 1 else integer(thousands) + ' mil')
        if remainder:
            result += (' e ' if remainder < 100 or remainder % 100 == 0 else ' ') + integer(remainder)
        return result
    return str(number)


def tokens(text):
    text = plain(text)
    text = re.sub(r'\bmacro[-\s]*m[.\s]*a[.\s]*[ei]\b', 'macro mae', text)
    text = re.sub(r'\bw\s*/?\s*m(?:\^?2|²)\b', ' watt por metro quadrado ', text)
    text = text.replace('%', ' por cento ')
    text = re.sub(r'\b([gm])\s*\.\s*([ha])\s*\.\s*([ie])\s*\.?',
                  lambda m: 'ghi' if m.group(1) == 'g' else 'mae', text)
    text = re.sub(r'(\d+)[,.](\d+)', lambda m: integer(int(m[1])) + ' virgula ' + integer(int(m[2])), text)
    # Whisper sometimes splits53,21 into separate words53 and,21.
    text = re.sub(r'^[,.](\d+)', lambda m: 'virgula ' + integer(int(m[1])), text.strip())
    text = re.sub(r'\d+', lambda m: integer(int(m[0])), text)
    raw = [ALIASES.get(token, token) for token in re.findall(r'[a-z0-9]+', text)]
    result = []
    for token in raw:
        result.extend(ACRONYMS.get(token, [token]))
    return result


def interval(value):
    if isinstance(value, (list, tuple)) and len(value) == 2:
        return [float(value[0]), float(value[1])]
    if isinstance(value, dict):
        for key in ['discard', 'source_range', 'range', 'interval', 'replace_range']:
            if key in value:
                return interval(value[key])
        if 'start' in value and 'end' in value:
            return [float(value['start']), float(value['end'])]
    return None


def overlaps(word, bounds):
    return word['start'] < bounds[1] - .001 and word['end'] > bounds[0] + .001


def flatten(record):
    words = []
    for segment_index, segment in enumerate(record.get('segments', [])):
        for word in segment.get('words', []):
            words.append(dict(word, index=len(words), raw_word_index=len(words),
                              segment_index=segment_index, origin='main_full_pcm0_asr'))
    return words


def corrected_observations(source, manifest):
    words = flatten(source)
    issues, changes = [], []
    excludes = []
    if manifest is None:
        excludes = deepcopy(FALLBACK_EXCLUDES)
        issues.append({'type': 'retake_manifest_pending', 'severity': 'review',
                       'fallback_exclusions': excludes})
    else:
        for key in ['discard_intervals', 'discard_ranges', 'exclusions', 'exclude_intervals']:
            for value in manifest.get(key, []):
                bounds = interval(value)
                if bounds:
                    excludes.append(bounds)
        for retake in manifest.get('retakes', []):
            for key in ['discard', 'discard_range', 'earlier_range']:
                bounds = interval(retake.get(key))
                if bounds:
                    excludes.append(bounds)
        # Retain the known discard ranges unless the explicit reviewed list
        # overrides defaults. They address first takes, not corrected later takes.
        if not excludes and not manifest.get('explicitly_no_exclusions', False):
            excludes = deepcopy(FALLBACK_EXCLUDES)

        next_id = len(words)
        replacements = manifest.get('replacement_segments', manifest.get('replacement_windows', []))
        for replacement_index, replacement in enumerate(replacements):
            bounds = interval(replacement.get('source_range', replacement.get('replace_range')))
            if bounds is None:
                issues.append({'type': 'replacement_missing_source_range', 'severity': 'error', 'replacement_index': replacement_index})
                continue
            if 'words' in replacement:
                incoming = replacement['words']
            else:
                incoming = [w for s in replacement.get('segments', []) for w in s.get('words', [])]
            if not incoming:
                issues.append({'type': 'replacement_has_no_word_timestamps', 'severity': 'error', 'source_range': bounds})
                continue
            offset = float(replacement.get('timestamp_offset_seconds', 0))
            if replacement.get('relative_timestamps', False):
                offset += bounds[0]
            converted = []
            for word in incoming:
                candidate = dict(word, start=float(word['start']) + offset, end=float(word['end']) + offset,
                                 index=next_id, raw_word_index=None, origin='reviewed_replacement', replacement_index=replacement_index)
                next_id += 1
                if not bounds[0] - 1 <= candidate['start'] <= candidate['end'] <= bounds[1] + 1:
                    issues.append({'type': 'replacement_outside_declared_full_pcm0_range', 'severity': 'error',
                                   'source_range': bounds, 'word': candidate})
                    continue
                converted.append(candidate)
            removed = [w['index'] for w in words if overlaps(w, bounds)]
            words = [w for w in words if not overlaps(w, bounds)] + converted
            changes.append({'type': 'reviewed_window_replacement', 'source_range': bounds,
                            'removed_observed_ids': removed, 'inserted_observed_ids': [w['index'] for w in converted]})

        manual = manifest.get('manual_asr_corrections', manifest.get('manual_word_corrections', []))
        if isinstance(manual, dict):
            manual = [dict(value if isinstance(value, dict) else {'word': value}, word_index=int(key)) for key, value in manual.items()]
        for correction in manual:
            ident = correction.get('word_index', correction.get('raw_word_index', correction.get('index')))
            bounds = interval(correction.get('source_range', correction.get('range')))
            targets = [w for w in words if (ident is not None and w.get('raw_word_index') == ident)
                       or (ident is None and bounds is not None and overlaps(w, bounds))]
            if not targets:
                issues.append({'type': 'manual_correction_target_not_found', 'severity': 'review', 'correction': correction})
                continue
            replacement_text = correction.get('word', correction.get('replacement_word', correction.get('replacement_text', correction.get('text'))))
            if len(targets) != 1:
                issues.append({'type': 'manual_multiword_correction_requires_replacement_segments', 'severity': 'review', 'correction': correction})
                continue
            word = targets[0]
            previous = deepcopy(word)
            if replacement_text is not None:
                word['word'] = replacement_text
            if correction.get('start') is not None:
                word['start'] = float(correction['start'])
            if correction.get('end') is not None:
                word['end'] = float(correction['end'])
            word['manual_correction'] = correction
            changes.append({'type': 'manual_asr_word_correction', 'before': previous, 'after': deepcopy(word)})

    excludes = sorted(set(tuple(x) for x in excludes))
    discarded_ids = [w['index'] for w in words if any(overlaps(w, bounds) for bounds in excludes)]
    words = sorted([w for w in words if w['index'] not in set(discarded_ids)], key=lambda w: (w['start'], w['end'], w['index']))
    by_id = {w['index']: w for w in words}
    assert len(by_id) == len(words)
    for word in words:
        if word['end'] < word['start'] or word['start'] < 0:
            issues.append({'type': 'invalid_word_interval', 'severity': 'error', 'word': word})
        elif word['end'] == word['start']:
            word['zero_duration_asr_anchor'] = True
            issues.append({'type': 'zero_duration_asr_anchor_preserved', 'severity': 'info',
                           'word_index': word['index'], 'time': word['start'],
                           'note': 'An ASR timing point, not evidence of a zero-length spoken word; do not synthesize or stretch speech.'})
    return words, by_id, [list(x) for x in excludes], discarded_ids, changes, issues


@lru_cache(maxsize=None)
def match_cost(a, b):
    if a == b:
        return 0.
    if a in MODELS and b in MODELS:
        return 1.55
    similarity = SequenceMatcher(None, a, b).ratio()
    if len(a) <= 2 or len(b) <= 2:
        return 1.35
    if similarity >= .84:
        return .25
    if similarity >= .68:
        return .65
    if similarity >= .50:
        return 1.
    return 1.4


def align(reference, observed):
    n, m = len(reference), len(observed)
    insertion_cost, deletion_cost = .78, .90
    previous = array('f', (j * insertion_cost for j in range(m + 1)))
    trace = [bytearray([2] * (m + 1))]
    trace[0][0] = 0
    for i in range(1, n + 1):
        current, row = array('f', [i * deletion_cost]), bytearray(m + 1)
        row[0] = 1
        for j in range(1, m + 1):
            diagonal = previous[j - 1] + match_cost(reference[i - 1]['token'], observed[j - 1]['token'])
            deletion = previous[j] + deletion_cost
            insertion = current[j - 1] + insertion_cost
            if diagonal <= deletion and diagonal <= insertion:
                current.append(diagonal); row[j] = 0
            elif deletion <= insertion:
                current.append(deletion); row[j] = 1
            else:
                current.append(insertion); row[j] = 2
        previous = current
        trace.append(row)
    matches, deleted, inserted = [], [], []
    i, j = n, m
    while i or j:
        direction = trace[i][j]
        if direction == 0 and i and j:
            matches.append((i-1, j-1)); i -= 1; j -= 1
        elif direction == 1 and i:
            deleted.append(i-1); i -= 1
        else:
            inserted.append(j-1); j -= 1
    return list(reversed(matches)), list(reversed(deleted)), list(reversed(inserted)), float(previous[-1])


def main():
    source, script = read(RAW), read(SCRIPT)
    manifest = read(MANIFEST) if MANIFEST.exists() else None
    original_hashes = {str(p.relative_to(ROOT)): sha(p) for p in [RAW, SCRIPT]}
    words, by_id, excludes, discarded, changes, issues = corrected_observations(source, manifest)
    reference, paragraphs, reference_edits = [], [], []
    text_overrides = manifest.get('reference_text_overrides', {}) if manifest else {}
    for section in script['sections']:
        for section_index, text in enumerate(section['paragraphs']):
            index = len(paragraphs)
            original_text = text
            if str(index) in text_overrides or index in text_overrides:
                text = text_overrides.get(str(index), text_overrides.get(index))
                reference_edits.append({'paragraph_index': index, 'reason': 'Explicit reviewed text override.',
                                        'original_text': original_text, 'edited_text': text})
            # The parent authorized deletion of the spoken13.77clause, not
            # replacement by the correct13.67in captions or synthetic voice.
            approved_six_month_omission = manifest and any(
                row.get('id') == 'six_month_incorrect_spoken_value' and row.get('action_authorized_by_parent')
                for row in manifest.get('numeric_omissions', []))
            if index == 21 and approved_six_month_omission:
                clause = ' e treze vírgula sessenta e sete em seis meses'
                if clause in text:
                    text = text.replace(clause, '', 1)
                    reference_edits.append({'paragraph_index': index, 'reason': 'Parent-authorized numeric-clause omission, exact voice remains unchanged.',
                                            'manifest_id': 'six_month_incorrect_spoken_value',
                                            'removed_reference_clause': clause, 'original_text': original_text, 'edited_text': text,
                                            'correct13_67_remains_visual_only': True})
            token_start = len(reference)
            for local_index, token in enumerate(tokens(text)):
                reference.append({'token': token, 'paragraph_index': index, 'local_token_index': local_index,
                                  'canonical_ref_index': len(reference)})
            paragraphs.append({'index': index, 'section_id': section['id'], 'section_paragraph_index': section_index,
                               'text': text, 'original_canonical_text': original_text,
                               'reference_token_start': token_start, 'reference_token_end': len(reference)})
    observed = []
    for word in words:
        for local_index, token in enumerate(tokens(word['word'])):
            observed.append({'token': token, 'word_index': word['index'], 'local_token_index': local_index})
    matches, deleted, inserted, edit_cost = align(reference, observed)
    matches_by_paragraph = [[] for _ in paragraphs]
    for ri, oi in matches:
        ref, obs = reference[ri], observed[oi]
        word = by_id[obs['word_index']]
        cost = match_cost(ref['token'], obs['token'])
        record = {'canonical_ref_index': ri, 'canonical_local_token_index': ref['local_token_index'],
                  'canonical_token': ref['token'], 'observed_token': obs['token'],
                  'observed_word_indices': [word['index']], 'start': word['start'], 'end': word['end'],
                  'similarity': round(max(0., 1-cost/1.55), 4), 'match_cost': cost,
                  'observed_word_text': word['word'], 'observed_origin': word['origin']}
        matches_by_paragraph[ref['paragraph_index']].append(record)

    paragraph_overrides = manifest.get('paragraph_overrides', []) if manifest else []
    if isinstance(paragraph_overrides, dict):
        paragraph_overrides = [dict(value, index=int(key)) for key, value in paragraph_overrides.items()]
    overrides = {x.get('index', x.get('paragraph_index')): x for x in paragraph_overrides}
    for paragraph in paragraphs:
        index = paragraph['index']
        mapped = matches_by_paragraph[index]
        missing = [ri for ri in deleted if reference[ri]['paragraph_index'] == index]
        local_issues = []
        ids = sorted(set(wid for row in mapped for wid in row['observed_word_indices']), key=lambda wid: (by_id[wid]['start'], wid))
        override = overrides.get(index)
        if override:
            start, end = float(override['start']), float(override['end'])
            ids = [w['index'] for w in words if w['start'] >= start-.005 and w['end'] <= end+.005]
            mapped = [row for row in mapped if row['start'] >= start-.005 and row['end'] <= end+.005]
            paragraph['manual_boundary_override'] = override
        elif ids:
            start, end = min(by_id[wid]['start'] for wid in ids), max(by_id[wid]['end'] for wid in ids)
        else:
            start = end = None
            local_issues.append({'type': 'no_paragraph_alignment', 'severity': 'error'})
        ref_count = paragraph['reference_token_end'] - paragraph['reference_token_start']
        coverage = len(mapped) / max(1, ref_count)
        average = sum(row['similarity'] for row in mapped) / max(1, len(mapped))
        confidence = min(1., .65 * average + .35 * coverage)
        substitutions = [row for row in mapped if row['canonical_token'] != row['observed_token']]
        for row in substitutions:
            a, b = row['canonical_token'], row['observed_token']
            if a in NUMBER_TOKENS and b not in {'a', 'e', 'o', 'de', 'do', 'da', 'em'}:
                local_issues.append({'type': 'numeric_token_substitution_needs_review', 'severity': 'critical',
                                     'canonical_ref_index': row['canonical_ref_index'], 'expected': a,
                                     'observed': b, 'observed_word_text': row['observed_word_text'],
                                     'start': row['start'], 'end': row['end']})
            if a in MODELS and b in MODELS and a != b:
                local_issues.append({'type': 'model_name_substitution_needs_review', 'severity': 'critical',
                                     'expected': a, 'observed': b, 'start': row['start'], 'end': row['end']})
        critical_deleted = [reference[ri] for ri in missing if reference[ri]['token'] in NUMBER_TOKENS or reference[ri]['token'] in MODELS]
        if critical_deleted:
            local_issues.append({'type': 'unmatched_critical_reference_tokens', 'severity': 'critical', 'tokens': critical_deleted})
        if missing:
            local_issues.append({'type': 'unmatched_reference_tokens', 'severity': 'review',
                                 'tokens': [reference[ri] for ri in missing]})
        if confidence < .80:
            local_issues.append({'type': 'low_fuzzy_alignment_confidence', 'severity': 'review', 'confidence': confidence})
        chronological = sorted([by_id[wid] for wid in ids], key=lambda w: (w['start'], w['end']))
        gaps = []
        for before, after in zip(chronological, chronological[1:]):
            gap = after['start'] - before['end']
            if gap > 1.6:
                gaps.append({'start': before['end'], 'end': after['start'], 'seconds': gap,
                             'before_observed_word': before['word'], 'after_observed_word': after['word']})
        if gaps:
            local_issues.append({'type': 'internal_gaps_require_editorial_trim_review', 'severity': 'review', 'gaps': gaps})
        for word in chronological:
            if word['end'] - word['start'] > 2.0:
                local_issues.append({'type': 'overlong_observed_word_boundary', 'severity': 'review', 'word': word})
        if len(chronological) > 1 and chronological[0]['word'].strip(' .,;:!?').lower() in {'o', 'a', 'os', 'as', 'dentro'}:
            if chronological[1]['start'] - chronological[0]['end'] > 2:
                local_issues.append({'type': 'possibly_false_leading_function_word', 'severity': 'critical',
                                     'word': chronological[0], 'next_word': chronological[1],
                                     'instruction': 'Do not stretch this word or infer a long spoken phrase. Use reviewed replacement-window boundaries.'})
        content_missing = [reference[ri]['token'] for ri in missing if len(reference[ri]['token']) > 2]
        blocking = any(row['severity'] in {'error', 'critical'} for row in local_issues)
        all_span_ids = [word['index'] for word in words
                        if start is not None and word['start'] >= start-.005 and word['end'] <= end+.005]
        paragraph.update({'start': start, 'end': end, 'audio_start': start, 'audio_end': end,
                          'confidence': round(confidence, 4), 'coverage': round(coverage, 4),
                          'average_token_similarity': round(average, 4), 'word_indices': ids,
                          'matched_word_indices': ids, 'all_observed_word_indices_in_span': all_span_ids,
                          'unassigned_observed_words_within_span': [wid for wid in all_span_ids if wid not in set(ids)],
                          'words': mapped, 'reference_token_count': ref_count, 'matched_token_count': len(mapped),
                          'unmatched_reference_token_indices': missing, 'substitution_count': len(substitutions),
                          'caption_canonical_text_eligible': confidence >= .90 and coverage >= .96 and not blocking and not content_missing,
                          'caption_text_policy': 'Canonical orthography only after actual words/values are verified; never replace a substantively different spoken value with the script.',
                          'issues': local_issues})
        issues.extend(dict(row, paragraph_index=index) for row in local_issues)

    for before, after in zip(paragraphs, paragraphs[1:]):
        if before['end'] is not None and after['start'] is not None and before['end'] > after['start'] + .005:
            issues.append({'type': 'paragraph_boundary_overlap', 'severity': 'error',
                           'paragraph_index': after['index'], 'previous_paragraph_index': before['index'],
                           'seconds': before['end'] - after['start']})
    matched_ids = {observed[oi]['word_index'] for _, oi in matches}
    output = {
        'version': 12, 'status': 'aligned_pending_editorial_issues' if issues else 'aligned',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'timebase': 'Full decoded source PCM first sample0, no AAC seek offsets.',
        'source': source['source'], 'source_sha256': source.get('source_sha256'),
        'source_duration_seconds': source['duration'], 'source_uploaded': False,
        'input_hashes': original_hashes,
        'reviewed_retakes_manifest': {'path': str(MANIFEST.relative_to(ROOT)), 'sha256': sha(MANIFEST)} if manifest else None,
        'manifest_scientific_issues': manifest.get('scientific_issues', []) if manifest else [],
        'excluded_intervals': excludes, 'discarded_observed_word_indices': discarded,
        'applied_observation_changes': changes,
        'canonical_reference_edits_for_authorized_omissions': reference_edits,
        'paragraphs': paragraphs, 'issues': issues,
        'alignment_stats': {'reference_tokens': len(reference), 'observed_tokens': len(observed),
                            'original_main_asr_words': len(flatten(source)), 'reviewed_observed_words': len(words),
                            'global_edit_cost': round(edit_cost, 4), 'matched_pairs': len(matches),
                            'reference_deletions': len(deleted), 'observed_insertions': len(inserted)},
        'reference_tokens': reference, 'observed_words': words,
        'observed_word_id_policy': 'Original raw IDs remain stable; reviewed replacements receive new IDs. Look up by index, not by list position. Paragraphword_indices are matched IDs; all_observed_word_indices_in_span also retains recognized insertions.',
        'unmatched_observed_word_indices': [w['index'] for w in words if w['index'] not in matched_ids],
        'safe_for_automatic_final_caption_generation': False,
        'audio_edited': False, 'video_rendered': False,
    }
    assert len(paragraphs) == 27
    assert original_hashes == {str(p.relative_to(ROOT)): sha(p) for p in [RAW, SCRIPT]}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'paragraphs': len(paragraphs), 'issues': len(issues),
                      'critical_issues': sum(x['severity'] in {'critical','error'} for x in issues),
                      'caption_eligible_paragraphs': sum(p['caption_canonical_text_eligible'] for p in paragraphs),
                      'range': [paragraphs[0]['start'], paragraphs[-1]['end']],
                      'manifest_loaded': manifest is not None, 'stats': output['alignment_stats']}, ensure_ascii=True))


if __name__ == '__main__':
    main()
