"""Independent, read-only V8 media/source audit; writes only its audit JSON.

--sources-only checks approved source snapshots and the planned 224+326 s.
--renders-only additionally requires all five complete production renders.
With no mode flag, also checks the final two exports, mobile copy, pixel-prefix
audit, captions/narration/plan, review PNGs and local player references.
No renderer, decoder, encoder, browser, network request or approval is started.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import re
import struct
import sys
import unicodedata
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/completo_v8'
PREFIX = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_ate_plano22_v7'
CHAPTERS = [('metodologia', 'methodology_v8', 224, 62),
            ('quantizacao', 'quantization_v8', 286, 54),
            ('metricas', 'metrics_v8', 340, 48),
            ('resultados', 'results_v8', 388, 88),
            ('interpretacao', 'interpretation_v8', 476, 74)]
FINAL_NAMES = {'Video_TCC_GHI_Completo_com_legendas_v8.mp4',
               'Video_TCC_GHI_Completo_sem_legendas_v8.mp4'}
MOBILE_NAME = 'Video_TCC_GHI_Completo_para_celular_v8.mp4'
SHA = re.compile(r'[0-9a-fA-F]{64}')


def issue(errors, kind, **details):
    errors.append({'kind': kind, **details})


def read_json(path, errors, kind='missing_or_invalid_json'):
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if not isinstance(value, dict):
            raise ValueError('Expected a JSON object')
        return value
    except (OSError, UnicodeError, ValueError) as error:
        issue(errors, kind, path=str(path), error=str(error))
        return {}


def resolve(value):
    path = Path(str(value).replace('\\', '/'))
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def path_key(value):
    path = resolve(value)
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('Source path escapes the project workspace: '+str(value))
    # Windows paths are case-insensitive; both hash producers also differ in
    # slash style. The digest itself is never recomputed from normalized keys.
    return path.relative_to(ROOT).as_posix().casefold()


def normalize_hashes(values, errors, context):
    normalized = {}
    if not isinstance(values, dict) or not values:
        issue(errors, 'missing_source_hashes', context=context)
        return normalized
    for original, digest in values.items():
        try:
            key = path_key(original)
            if key in normalized:
                raise ValueError('Duplicate paths after slash/case normalization')
            if not SHA.fullmatch(str(digest)):
                raise ValueError('Invalid SHA256')
            normalized[key] = str(digest).lower()
        except ValueError as error:
            issue(errors, 'invalid_source_hash_record', context=context,
                  path=str(original), error=str(error))
    return normalized


class Snapshots:
    def __init__(self):
        self.cache = {}

    def get(self, path):
        path = path.resolve()
        before = path.stat()
        token = (str(path).casefold(), before.st_size, before.st_mtime_ns)
        if token not in self.cache:
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise RuntimeError('Input changed while hashing: '+str(path))
            self.cache[token] = {'path': str(path), 'bytes': after.st_size,
                                 'mtime_ns': after.st_mtime_ns, 'sha256': digest}
        return self.cache[token]


def boxes(stream, start, end):
    offset = start
    while offset + 8 <= end:
        stream.seek(offset)
        raw = stream.read(8)
        size, tag = struct.unpack('>I4s', raw)
        header = 8
        if size == 1:
            extra = stream.read(8)
            if len(extra) != 8:
                raise ValueError('Truncated extended atom')
            size = struct.unpack('>Q', extra)[0]
            header = 16
        elif size == 0:
            size = end-offset
        if size < header or offset+size > end:
            raise ValueError('Invalid MP4 atom bounds')
        yield {'tag': tag.decode('latin1'), 'payload': offset+header,
               'end': offset+size, 'size': size-header}
        offset += size


def children(stream, atom):
    return list(boxes(stream, atom['payload'], atom['end']))


def atom_bytes(stream, atom, maximum=4096):
    stream.seek(atom['payload'])
    return stream.read(min(atom['size'], maximum))


def mp4_headers(path):
    """Independent ISO-BMFF metadata/sample-table inspection, not a decode."""
    with path.open('rb') as stream:
        top = list(boxes(stream, 0, path.stat().st_size))
        moov = next((a for a in top if a['tag'] == 'moov'), None)
        if not moov:
            raise ValueError('No complete MP4 moov atom')
        tracks = []
        for trak in (a for a in children(stream, moov) if a['tag'] == 'trak'):
            tc = {a['tag']: a for a in children(stream, trak)}
            mdia = {a['tag']: a for a in children(stream, tc['mdia'])}
            hdlr = atom_bytes(stream, mdia['hdlr'])
            kind = hdlr[8:12].decode('latin1')
            mdhd = atom_bytes(stream, mdia['mdhd'])
            if mdhd[0] == 1:
                timescale = struct.unpack_from('>I', mdhd, 20)[0]
                duration = struct.unpack_from('>Q', mdhd, 24)[0]
            else:
                timescale, duration = struct.unpack_from('>II', mdhd, 12)
            info = {'handler': kind, 'media_timescale': timescale,
                    'duration_seconds': duration/timescale if timescale else None}
            if kind == 'vide':
                tkhd = atom_bytes(stream, tc['tkhd'])
                width, height = struct.unpack('>II', tkhd[-8:])
                info.update(width=width/65536, height=height/65536)
                minf = {a['tag']: a for a in children(stream, mdia['minf'])}
                stbl = {a['tag']: a for a in children(stream, minf['stbl'])}
                stsz = atom_bytes(stream, stbl['stsz'], 12)
                info['frame_count'] = struct.unpack_from('>I', stsz, 8)[0]
                stts = stbl['stts']
                stream.seek(stts['payload'])
                header = stream.read(8)
                count = struct.unpack_from('>I', header, 4)[0]
                ticks = samples = 0
                for _ in range(count):
                    n, delta = struct.unpack('>II', stream.read(8))
                    samples += n
                    ticks += n*delta
                if samples != info['frame_count'] or not ticks or not timescale:
                    raise ValueError('Invalid or inconsistent MP4 sample tables')
                info['sample_table_seconds'] = ticks/timescale
                info['fps'] = samples*timescale/ticks
                stsd = stbl['stsd']
                entries = list(boxes(stream, stsd['payload']+8, stsd['end']))
                if not entries:
                    raise ValueError('No video sample description')
                info['codec_tag'] = entries[0]['tag']
                if entries[0]['size'] >= 78:
                    extensions = list(boxes(stream, entries[0]['payload']+78, entries[0]['end']))
                    avcc = next((a for a in extensions if a['tag'] == 'avcC'), None)
                    if avcc:
                        avc = atom_bytes(stream, avcc, 4)
                        info.update(avc_profile_idc=avc[1], avc_level_idc=avc[3])
            tracks.append(info)
        video = [track for track in tracks if track['handler'] == 'vide']
        if len(video) != 1:
            raise ValueError('Expected exactly one MP4 video track')
        return {**video[0], 'video_tracks': len(video),
                'audio_tracks': sum(track['handler'] == 'soun' for track in tracks)}


def audit_video(entry, expected, errors, snapshots, context, require_decode=True):
    result = {'context': context, 'header_inspected_independently': False,
              'video_decoded_by_this_audit': False,
              'source_full_decode_declaration_required': require_decode}
    try:
        path = resolve(entry['path'])
        result['path'] = str(path)
        if not path.is_relative_to(ROOT) or not path.is_file():
            raise ValueError('Video missing or outside workspace')
        actual = snapshots.get(path)
        result['snapshot'] = actual
        if actual['bytes'] <= 1000 or actual['bytes'] != entry.get('bytes'):
            issue(errors, 'video_size_mismatch', context=context, path=str(path))
        if actual['sha256'] != str(entry.get('sha256', '')).lower():
            issue(errors, 'video_hash_mismatch', context=context, path=str(path))
        if require_decode and entry.get('full_decode_errors') != 0:
            issue(errors, 'missing_or_failed_full_decode_declaration', context=context)
        header = mp4_headers(path)
        result.update(header=header, header_inspected_independently=True)
        for key, value in expected.items():
            if entry.get(key) != value:
                issue(errors, 'video_declared_metadata_mismatch', context=context,
                      field=key, expected=value, actual=entry.get(key))
            observed = header.get(key)
            tolerance = .03 if key == 'duration_seconds' else .0001
            good = (abs(observed-value) <= tolerance if isinstance(value, (int, float))
                    and isinstance(observed, (int, float)) else observed == value)
            if not good:
                issue(errors, 'video_actual_header_mismatch', context=context,
                      field=key, expected=value, actual=observed)
        if header.get('codec_tag') not in {'avc1', 'avc3'}:
            issue(errors, 'unexpected_video_codec', context=context, actual=header.get('codec_tag'))
    except (OSError, ValueError, KeyError, RuntimeError, struct.error) as error:
        issue(errors, 'unreadable_video_or_metadata', context=context, error=str(error))
    return result


def audit_sources(output, errors, snapshots, renders):
    approved = read_json(output/'qa_aprovado_v8.json', errors)
    records, manifests = [], {}
    previous_end = 224
    for chapter, module, start, duration in CHAPTERS:
        manifest = read_json(output/'cenas'/f'{chapter}_manifesto_v8.json', errors)
        manifests[chapter] = manifest
        gate = approved.get(chapter, {})
        item = {'chapter': chapter, 'start': start, 'duration': duration,
                'source_checks': [], 'render_complete': manifest.get('render_complete') is True}
        if gate.get('approved') is not True or gate.get('automatically_approved') is not False:
            issue(errors, 'missing_manual_source_approval', chapter=chapter)
        mh = normalize_hashes(manifest.get('source_hashes'), errors, chapter+' manifest')
        gh = normalize_hashes(gate.get('source_hashes'), errors, chapter+' approval')
        required = {path_key('codigo_fonte/video_ea019/'+module+'.py'),
                    path_key('codigo_fonte/video_ea019/director_v8.py'),
                    path_key('codigo_fonte/video_ea019/common_v7.py'),
                    path_key('codigo_fonte/video_ea019/blender_pilot.py'),
                    path_key('codigo_fonte/video_ea019/factory_site_v6.py'),
                    path_key(output/'fontes_resultados_v8.json')}
        if set(mh) != required or set(gh) != required:
            issue(errors, 'incomplete_approved_source_set', chapter=chapter,
                  manifest_paths=sorted(mh), approval_paths=sorted(gh), expected=sorted(required))
        if mh != gh:
            issue(errors, 'manifest_and_approval_hashes_differ', chapter=chapter)
        for key in sorted(required):
            check = {'path': key, 'manifest_sha256': mh.get(key), 'approved_sha256': gh.get(key)}
            try:
                current = snapshots.get(ROOT/key)
                check['actual_sha256'] = current['sha256']
                check['matches'] = current['sha256'] == mh.get(key) == gh.get(key)
                if not check['matches']:
                    issue(errors, 'approved_render_source_changed', chapter=chapter, path=key)
            except (OSError, RuntimeError) as error:
                check['matches'] = False
                issue(errors, 'missing_approved_render_source', chapter=chapter, path=key, error=str(error))
            item['source_checks'].append(check)
        if manifest.get('source_hashes'):
            payload = {'sources': manifest['source_hashes'], 'samples': manifest.get('samples'),
                       'resolution': [1920, 1080], 'fps': 30}
            actual = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            item['fingerprint_matches'] = actual == manifest.get('source_fingerprint')
            if not item['fingerprint_matches']:
                issue(errors, 'invalid_render_fingerprint', chapter=chapter)
        expected = {'version': 8, 'chapter': chapter, 'duration': duration,
                    'start': start, 'end': start+duration, 'fps': 30,
                    'frames': duration*30, 'resolution': [1920, 1080], 'samples': 16}
        for key, value in expected.items():
            if manifest.get(key) != value:
                issue(errors, 'chapter_metadata_mismatch', chapter=chapter, field=key,
                      expected=value, actual=manifest.get(key))
        if start != previous_end:
            issue(errors, 'noncontiguous_chapter_timeline', chapter=chapter)
        previous_end = start+duration
        if renders:
            if manifest.get('render_complete') is not True or manifest.get('resolution_percentage') != 100:
                issue(errors, 'production_render_not_complete', chapter=chapter)
            blocks = manifest.get('blocks', [])
            next_frame = 1
            block_results = []
            for block in blocks:
                first, last = block.get('first_frame'), block.get('last_frame')
                if not isinstance(first, int) or not isinstance(last, int):
                    issue(errors, 'invalid_render_block_bounds', chapter=chapter)
                    continue
                if first != next_frame or last < first or last-first+1 > 300 or last > duration*30:
                    issue(errors, 'noncontiguous_render_block', chapter=chapter, first=first, last=last)
                if block.get('frame_count') != last-first+1 or block.get('source_fingerprint') != manifest.get('source_fingerprint'):
                    issue(errors, 'render_block_source_or_count_mismatch', chapter=chapter, first=first)
                entry = {**block, 'duration_seconds': (last-first+1)/30, 'fps': 30,
                         'width': 1920, 'height': 1080, 'audio_tracks': 0}
                # Blocks are independently header/hash checked here; their
                # concatenated chapter has the recorded full decode below.
                checked = audit_video(entry, {'duration_seconds': (last-first+1)/30,
                    'fps': 30, 'frame_count': last-first+1, 'width': 1920,
                    'height': 1080, 'audio_tracks': 0}, errors, snapshots,
                    chapter+' block '+str(first), require_decode=False)
                block_results.append(checked)
                next_frame = last+1
            if next_frame != duration*30+1:
                issue(errors, 'incomplete_render_block_coverage', chapter=chapter,
                      expected_frames=duration*30, covered_until=next_frame-1)
            item['blocks'] = block_results
            raw = manifest.get('raw_verification', {})
            item['raw_video'] = audit_video(raw, {'duration_seconds': duration,
                'fps': 30, 'frame_count': duration*30, 'width': 1920, 'height': 1080,
                'audio_tracks': 0}, errors, snapshots, chapter+' complete raw')
            if raw.get('path') and resolve(raw['path']) != resolve(manifest.get('raw_mp4')):
                issue(errors, 'chapter_raw_path_mismatch', chapter=chapter)
        records.append(item)
    timeline = {'prefix_seconds': 224, 'prefix_frames': 6720,
                'new_chapter_seconds': sum(c[3] for c in CHAPTERS),
                'new_chapter_frames': sum(c[3]*30 for c in CHAPTERS),
                'total_seconds': previous_end, 'total_frames': previous_end*30}
    if timeline != {'prefix_seconds': 224, 'prefix_frames': 6720,
                    'new_chapter_seconds': 326, 'new_chapter_frames': 9780,
                    'total_seconds': 550, 'total_frames': 16500}:
        issue(errors, 'incorrect_complete_timeline', actual=timeline)
    return records, manifests, timeline


def parse_srt(path):
    text = path.read_text(encoding='utf-8-sig').strip()
    result = []
    stamp = r'(\d+):(\d{2}):(\d{2}),(\d{3})'
    for index, block in enumerate(re.split(r'\r?\n\s*\r?\n', text), 1):
        lines = block.splitlines()
        if len(lines) < 3 or lines[0] != str(index):
            raise ValueError('Invalid SRT sequence at '+str(index))
        match = re.fullmatch(stamp+r' --> '+stamp, lines[1])
        if not match:
            raise ValueError('Invalid SRT timing at '+str(index))
        values = list(map(int, match.groups()))
        time = lambda a: a[0]*3600+a[1]*60+a[2]+a[3]/1000
        a, b = time(values[:4]), time(values[4:])
        body = lines[2:]
        if not 1 <= len(body) <= 2 or any(not line or len(line) > 42 for line in body):
            raise ValueError('SRT exceeds two42-character lines at '+str(index))
        if b <= a or (result and a < result[-1]['end']-.0001):
            raise ValueError('Overlapping or empty SRT cue at '+str(index))
        result.append({'start': a, 'end': b, 'text': '\n'.join(body)})
    return result


def normalize(text):
    return ' '.join(unicodedata.normalize('NFC', str(text)).split())


def audit_narration(output, manifests, errors, warnings):
    record = {'checked': False, 'narration_recorded': False,
              'timing_is_planned_for_future_user_recording': True}
    try:
        plan = json.loads((output/'plano_video_v8.json').read_text(encoding='utf-8-sig'))
        source_plan = json.loads((PREFIX/'plano_video_v7.json').read_text(encoding='utf-8-sig'))
        cues = parse_srt(output/'Legendas_Video_Completo_v8.srt')
        prefix_cues = parse_srt(PREFIX/'Legendas_Revisao_ate_Plano22_v7.srt')
        assert plan['duration'] == 550 and plan['frames'] == 16500 and plan['fps'] == 30
        assert plan['approved_prefix_reused_seconds'] == 224
        assert plan['personal_intro_seconds'] == plan['personal_outro_seconds'] == 20
        assert plan['projected_total_with_personal_footage'] == 590
        assert plan['narration_recorded'] is False and plan['camera_footage_included'] is False
        assert plan['animated_title_cards_replacing_personal_footage'] is False
        assert cues and cues[0]['start'] == 0 and cues[-1]['end'] == 550
        assert cues[:len(prefix_cues)] == prefix_cues
        assert len(cues) == len(plan['cues'])
        for a, b in zip(cues, plan['cues']):
            assert abs(a['start']-b['start']) < .001 and abs(a['end']-b['end']) < .001 and a['text'] == b['text']
        # Read only the literal speech overrides; importing prepare/compose
        # would write files and would compromise the independence of this audit.
        tree = ast.parse((ROOT/'codigo_fonte/video_ea019/compose_v8.py').read_text(encoding='utf-8-sig'))
        overrides = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'NARRATION_OVERRIDES' for t in node.targets):
                overrides = ast.literal_eval(node.value)
        expected_phases = [list(p) for p in source_plan['phases']]
        for chapter, module, start, duration in CHAPTERS:
            for a, b, text in manifests[chapter]['cues']:
                expected_phases.append([a+start, b+start, overrides.get(chapter, {}).get((a, b), text)])
        assert plan['phases'] == expected_phases
        last = 0
        for a, b, text in plan['phases']:
            assert a == last and b > a
            contained = [c['text'] for c in cues if c['start'] >= a-.001 and c['end'] <= b+.001]
            assert normalize(' '.join(contained)) == normalize(text)
            last = b
        assert last == 550
        speech = (output/'Falas_Video_Completo_v8.txt').read_text(encoding='utf-8-sig')
        blocks = re.findall(r'^(\d+:\d{2}\.\d)[\u2013-](\d+:\d{2}\.\d)\n([^\n]+)', speech, re.M)
        assert len(blocks) == len(plan['phases'])
        for (a, b, text), (ta, tb, narration) in zip(plan['phases'], blocks):
            convert = lambda t: int(t.split(':')[0])*60+float(t.split(':')[1])
            assert abs(convert(ta)-a) < .051 and abs(convert(tb)-b) < .051
            assert normalize(narration) == normalize(text)
        assert 'sem áudio' in normalize(speech).casefold()
        record.update(checked=True, cues=len(cues), phases=len(plan['phases']),
                      prefix_cues_preserved=True, final_speech_overrides_used=bool(overrides),
                      first_cue_seconds=cues[0]['start'], last_cue_seconds=cues[-1]['end'])
        fast = []
        for index, cue in enumerate(cues, 1):
            duration = cue['end']-cue['start']
            cps = len(cue['text'].replace('\n', ' '))/duration
            if duration < .75 or cps > 25:
                fast.append({'cue': index, 'start': cue['start'], 'end': cue['end'],
                             'characters_per_second': round(cps, 2)})
        record['short_or_fast_planned_cues'] = fast
        if fast:
            warnings.append({'kind': 'planned_captions_to_align_with_recorded_voice',
                             'count': len(fast), 'includes_approved_prefix': any(c['start'] < 224 for c in fast)})
    except (OSError, ValueError, KeyError, TypeError, AssertionError, SyntaxError) as error:
        issue(errors, 'narration_caption_or_plan_mismatch', error=type(error).__name__+': '+str(error))
    return record


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs, self.seeks = [], []

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        for key in ('href', 'src', 'poster'):
            if attrs.get(key):
                self.refs.append(attrs[key])
        if tag == 'option' and attrs.get('value', '').lower().endswith('.mp4'):
            self.refs.append(attrs['value'])
        if 'data-t' in attrs:
            self.seeks.append(float(attrs['data-t']))


def audit_images(output, source, errors):
    try:
        from PIL import Image
    except ModuleNotFoundError:
        sys.path.insert(0, str(ROOT/'.venv/Lib/site-packages'))
        from PIL import Image
    records = []
    samples = source.get('sampled_frames', [])
    sheets = source.get('contact_sheets', [])
    if len(samples) != 60 or len(sheets) != 5:
        issue(errors, 'unexpected_final_review_image_count', samples=len(samples), sheets=len(sheets))
    seen = set()
    for kind, values in [('sample', samples), ('contact', sheets)]:
        for value in values:
            path = resolve(value)
            item = {'kind': kind, 'path': str(path), 'readable': False}
            try:
                assert path.parent == (output/'verificacao_final').resolve() and path not in seen
                seen.add(path)
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                    item['dimensions'] = list(image.size)
                    assert image.format == 'PNG'
                    assert image.size == ((1920, 1080) if kind == 'sample' else (1920, 1552))
                item['readable'] = True
            except (OSError, ValueError, AssertionError, SyntaxError) as error:
                issue(errors, 'invalid_final_review_image', path=str(path), error=str(error))
            records.append(item)
    return records


def audit_caption_provenance(output, source, errors, snapshots):
    """Check the five actual ASS/cache inputs against the final local speech."""
    records = []
    try:
        final_cues = parse_srt(output/'Legendas_Video_Completo_v8.srt')
    except (OSError, ValueError) as error:
        issue(errors, 'caption_source_srt_unreadable', error=str(error))
        return records
    entries = source.get('captioned_chapter_verification', [])
    expected_names = {chapter+'_com_legendas_v8.mp4' for chapter, *_ in CHAPTERS}
    if len(entries) != 5 or {Path(str(e.get('path', '')).replace('\\', '/')).name for e in entries} != expected_names:
        issue(errors, 'invalid_captioned_chapter_set')
    by_name = {Path(str(e.get('path', '')).replace('\\', '/')).name: e for e in entries}
    for chapter, module, start, duration in CHAPTERS:
        target = output/'cenas'/f'{chapter}_com_legendas_v8.mp4'
        ass = target.with_suffix('.ass')
        cache = read_json(target.with_suffix('.compose.json'), errors)
        raw = output/'cenas'/f'{chapter}_3d_v8.mp4'
        item = {'chapter': chapter, 'speech_matches_actual_ass_input': False}
        try:
            key = {'raw_sha256': snapshots.get(raw)['sha256'],
                   'ass_sha256': snapshots.get(ass)['sha256'],
                   'encoding': 'libx264_medium_crf18_yuv420p_30fps'}
            if cache.get('sources') != key or cache.get('sha256') != snapshots.get(target)['sha256']:
                issue(errors, 'caption_composition_cache_source_mismatch', chapter=chapter)
            entry = by_name.get(target.name, {})
            if cache.get('verification') != entry:
                issue(errors, 'caption_composition_verification_mismatch', chapter=chapter)
            item['video'] = audit_video(entry, {'duration_seconds': duration, 'fps': 30,
                'frame_count': duration*30, 'width': 1920, 'height': 1080, 'audio_tracks': 0},
                errors, snapshots, chapter+' captioned input')
            text = ass.read_text(encoding='utf-8-sig')
            assert re.search(r'^PlayResX:\s*1920\s*$', text, re.M)
            assert re.search(r'^PlayResY:\s*1080\s*$', text, re.M)
            events = []
            for line in text.splitlines():
                if not line.startswith('Dialogue: '):
                    continue
                fields = line[10:].split(',', 9)
                assert len(fields) == 10 and fields[3] == 'Caption'
                def stamp(value):
                    hours, minutes, seconds = value.split(':')
                    return int(hours)*3600+int(minutes)*60+float(seconds)
                body = re.sub(r'^\{[^}]*\}', '', fields[9]).replace(r'\N', '\n')
                events.append({'start': stamp(fields[1]), 'end': stamp(fields[2]), 'text': body})
            expected = [cue for cue in final_cues
                        if cue['start'] >= start-.001 and cue['end'] <= start+duration+.001]
            assert len(events) == len(expected)
            for actual, wanted in zip(events, expected):
                assert abs(actual['start']-(wanted['start']-start)) <= .011
                assert abs(actual['end']-(wanted['end']-start)) <= .011
                assert actual['text'] == wanted['text']
            item.update(speech_matches_actual_ass_input=True, caption_events=len(events),
                        ass_sha256=key['ass_sha256'], raw_sha256=key['raw_sha256'])
        except (OSError, ValueError, KeyError, RuntimeError, AssertionError) as error:
            issue(errors, 'caption_composition_provenance_invalid', chapter=chapter,
                  error=type(error).__name__+': '+str(error))
        records.append(item)
    return records


def audit_final(output, manifests, errors, warnings, snapshots):
    source = read_json(output/'verificacao_video_v8.json', errors)
    result = {'source_status': source.get('status'), 'videos': [], 'mobile': {},
              'visual_approval_automatically_granted': False,
              'source_final_visual_review_passed': source.get('sampled_visual_review_passed') is True}
    if source.get('status') not in {'encoded_pending_manual_final_review', 'complete', 'complete_pending_manual_visual_review'}:
        issue(errors, 'final_export_not_ready', status=source.get('status'))
    expected = {'version': 8, 'duration_seconds': 550, 'fps': 30, 'frame_count': 16500,
                'resolution': [1920, 1080], 'audio_tracks': 0, 'full_decode_errors': 0,
                'approved_prefix_seconds': 224, 'new_animation_seconds': 326,
                'approved_prefix_unchanged': True, 'older_versions_modified': False,
                'personal_footage_included': False, 'narration_recorded': False,
                'total_with_40s_personal_footage': 590, 'maximum_animation_seconds': 560}
    for key, value in expected.items():
        if source.get(key) != value:
            issue(errors, 'unexpected_complete_export_metadata', field=key, expected=value, actual=source.get(key))
    entries = source.get('files', [])
    if len(entries) != 2 or {Path(str(e.get('path', '')).replace('\\', '/')).name for e in entries} != FINAL_NAMES:
        issue(errors, 'unexpected_final_video_names_or_count')
    for entry in entries:
        result['videos'].append(audit_video(entry, {'duration_seconds': 550, 'fps': 30,
            'frame_count': 16500, 'width': 1920, 'height': 1080, 'audio_tracks': 0},
            errors, snapshots, 'final '+str(entry.get('path'))))
    phone = source.get('mobile_preview', {})
    if Path(str(phone.get('path', '')).replace('\\', '/')).name != MOBILE_NAME:
        issue(errors, 'unexpected_mobile_video_name')
    result['mobile'] = audit_video(phone, {'duration_seconds': 550, 'fps': 24,
        'frame_count': 13200, 'width': 1280, 'height': 720, 'audio_tracks': 0},
        errors, snapshots, 'mobile complete')
    if result['mobile'].get('header', {}).get('avc_profile_idc') != 66:
        issue(errors, 'mobile_not_h264_baseline')
    result['mobile_client_playback_confirmed'] = phone.get('client_playback_confirmed') is True
    prefix = read_json(PREFIX/'verificacao_video_v7.json', errors)
    result['approved_prefix_sources'] = []
    declared = normalize_hashes(source.get('approved_prefix_hashes'), errors, 'complete export prefix sources')
    prefix_entries = prefix.get('files', [])
    if len(prefix_entries) != 2 or {Path(str(e.get('path', '')).replace('\\', '/')).name for e in prefix_entries} != {
            'Video_GHI_Inicio_ate_Plano22_com_legendas_v7.mp4',
            'Video_GHI_Inicio_ate_Plano22_sem_legendas_v7.mp4'}:
        issue(errors, 'unexpected_approved_prefix_source_set')
    if set(declared) != {path_key(entry['path']) for entry in prefix_entries}:
        issue(errors, 'unexpected_declared_prefix_source_set')
    for entry in prefix_entries:
        inspected = audit_video(entry, {'duration_seconds': 224, 'fps': 30, 'frame_count': 6720,
            'width': 1920, 'height': 1080, 'audio_tracks': 0}, errors, snapshots, 'approved V7 prefix')
        result['approved_prefix_sources'].append(inspected)
        if declared.get(path_key(entry['path'])) != entry.get('sha256'):
            issue(errors, 'prefix_snapshot_differs_from_approved_v7', path=entry['path'])
    pixel = read_json(output/'verificacao_preservacao_prefixo_v8.json', errors)
    result['pixel_prefix_audit'] = {'status': pixel.get('status'),
        'approved_v7_prefix_preserved_pixel_exact': pixel.get('approved_v7_prefix_preserved_pixel_exact')}
    if pixel.get('status') != 'passed' or pixel.get('approved_v7_prefix_preserved_pixel_exact') is not True:
        issue(errors, 'prefix_pixel_equality_not_verified')
    variants = pixel.get('variants', [])
    if len(variants) != 2 or {v.get('variant') for v in variants} != {'com_legendas', 'sem_legendas'}:
        issue(errors, 'invalid_pixel_prefix_variants')
    for variant in variants:
        if (variant.get('pixel_md5_equal') is not True or variant.get('approved_v7_frames') != 6720
                or variant.get('v8_prefix_frames') != 6720 or variant.get('full_prefix_decode_errors') != 0):
            issue(errors, 'pixel_prefix_variant_failed', variant=variant.get('variant'))
        target = variant.get('files_after', {}).get('v8', {})
        try:
            if snapshots.get(resolve(target['path']))['sha256'] != target.get('sha256'):
                issue(errors, 'stale_prefix_pixel_audit', path=target.get('path'))
        except (OSError, KeyError, RuntimeError) as error:
            issue(errors, 'invalid_prefix_pixel_snapshot', error=str(error))
    result['narration_and_captions'] = audit_narration(output, manifests, errors, warnings)
    result['caption_composition_provenance'] = audit_caption_provenance(output, source, errors, snapshots)
    result['review_images'] = audit_images(output, source, errors)
    try:
        player = output/'assistir_video_completo_v8.html'
        parsed = Links()
        parsed.feed(player.read_text(encoding='utf-8-sig'))
        checked = []
        for value in parsed.refs:
            parts = urlsplit(value)
            if parts.scheme or parts.netloc or not parts.path:
                continue
            path = (player.parent/unquote(parts.path)).resolve()
            exists = path.is_relative_to(ROOT) and path.is_file() and path.stat().st_size > 0
            checked.append({'url': value, 'path': str(path), 'exists': exists})
            if not exists:
                issue(errors, 'invalid_player_link', url=value)
        assert all(0 <= t < 550 for t in parsed.seeks)
        assert {224, 286, 340, 388, 476}.issubset(set(parsed.seeks))
        assert FINAL_NAMES | {MOBILE_NAME} <= {Path(unquote(urlsplit(v).path)).name for v in parsed.refs}
        shortcut = (ROOT/'ASSISTIR_VIDEO_COMPLETO_V8.cmd').read_text(encoding='ascii')
        match = re.search(r'start\s+""\s+"%~dp0([^\"]+)"', shortcut, re.I)
        assert match and (ROOT/match[1].replace('\\', '/')).resolve() == player.resolve()
        result['player_links'] = checked
    except (OSError, ValueError, AssertionError) as error:
        issue(errors, 'player_or_shortcut_invalid', error=type(error).__name__+': '+str(error))
    return result


def run(output=OUT, sources_only=False, renders_only=False):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or not output.is_dir():
        raise ValueError('Audit output must be the existing project delivery directory')
    errors, warnings, snapshots = [], [], Snapshots()
    chapters, manifests, timeline = audit_sources(output, errors, snapshots, not sources_only)
    final = None if sources_only or renders_only else audit_final(output, manifests, errors, warnings, snapshots)
    mode = 'sources' if sources_only else 'renders' if renders_only else 'delivery'
    report = {'version': 8, 'generated_utc': datetime.now(timezone.utc).isoformat(),
              'mode': mode, 'technical_ok': not errors, 'error_count': len(errors),
              'errors': errors, 'warnings': warnings, 'timeline': timeline,
              'renderer_source_hash_path_normalization': 'Workspace-relative POSIX slashes and casefold; fingerprints use original serialized source keys',
              'chapters': chapters, 'final_delivery': final,
              'rendering_or_encoding_performed': False, 'video_decoding_performed': False,
              'external_processes_started': False, 'frozen_sources_modified': False,
              'visual_approval_automatically_granted': False}
    name = 'audit_sources_v8.json' if sources_only else 'audit_renders_v8.json' if renders_only else 'audit_delivery_v8.json'
    target = output/name
    report['only_output_written'] = str(target)
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    os.replace(temp, target)
    return target, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--renders-only', action='store_true')
    modes.add_argument('--sources-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=OUT)
    args = parser.parse_args()
    target, report = run(args.output_dir, sources_only=args.sources_only, renders_only=args.renders_only)
    print(json.dumps({'report': str(target), 'mode': report['mode'],
                      'technical_ok': report['technical_ok'], 'error_count': report['error_count'],
                      'errors': report['errors'], 'warnings': report['warnings'],
                      'timeline': report['timeline'], 'approved_renderers': len(report['chapters'])},
                     ensure_ascii=True, indent=2), flush=True)
    return 0 if report['technical_ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
