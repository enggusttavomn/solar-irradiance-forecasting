"""Montar contatos e auditar os arquivos finais do video EA019, sem render.

Executar depois de render_complete_v3.py. Usa apenas Pillow e biblioteca
padrao: nao inicia Blender, FFmpeg, navegadores ou processos auxiliares.
A integridade tecnica dos arquivos nunca e uma aprovacao visual automatica.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT/'documentacao/relatorio_final_ea019/video/completo_v3'

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ModuleNotFoundError:
    # The embedded CPython can use the workspace's Pillow installation even
    # when the .venv/Scripts/python.exe launcher cannot find its base Python.
    sys.path.insert(0, str(ROOT/'.venv/Lib/site-packages'))
    from PIL import Image, ImageDraw, ImageFont, ImageOps


THUMBNAIL = (480, 270)
LABEL_HEIGHT = 38
COLS = ROWS = 4
BACKGROUND = '#07090D'
FOREGROUND = '#F3F5F7'
SECONDARY = '#A9B2BE'


def _font(size):
    for candidate in (Path('C:/Windows/Fonts/segoeui.ttf'),
                      Path('C:/Windows/Fonts/arial.ttf')):
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    try:
        return ImageFont.truetype('DejaVuSans.ttf', size)
    except OSError:
        return ImageFont.load_default()


def _timecode(seconds):
    seconds = float(seconds)
    minutes, remainder = divmod(seconds, 60)
    if abs(remainder-round(remainder)) < 1e-6:
        return f'{int(minutes):02d}:{int(round(remainder)):02d}'
    return f'{int(minutes):02d}:{remainder:04.1f}'


def _read_json(path, issues, required=True):
    if not path.is_file():
        if required:
            issues.append({'kind': 'missing_json', 'path': str(path)})
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        issues.append({'kind': 'invalid_json', 'path': str(path), 'error': str(error)})
        return None


def _placeholder(shot_id, message):
    image = Image.new('RGB', THUMBNAIL, BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((9, 9, 470, 260), outline='#626D7A', width=2)
    draw.text((24, 95), shot_id, font=_font(28), fill=FOREGROUND)
    draw.text((24, 137), message, font=_font(19), fill=SECONDARY)
    return image


def _inspect_frame(path, shot, expected_dimensions, issues):
    record = {
        'shot': shot['id'], 'path': str(path), 'exists': path.is_file(),
        'nonempty': False, 'decodable': False, 'dimensions': None,
        'expected_dimensions': list(expected_dimensions),
        'dimensions_match': False, 'bytes': 0,
        'start_seconds': shot['start_s'], 'end_seconds': shot['end_s'],
        'sample_seconds': (float(shot['start_s'])+float(shot['end_s']))/2,
    }
    if not record['exists']:
        issues.append({'kind': 'missing_frame', 'shot': shot['id'], 'path': str(path)})
        return record, _placeholder(shot['id'], 'QUADRO AINDA AUSENTE')
    try:
        record['bytes'] = path.stat().st_size
        record['nonempty'] = record['bytes'] > 0
        if not record['nonempty']:
            raise ValueError('arquivo vazio')
        with Image.open(path) as source:
            source.load()
            record['format'] = source.format
            record['mode'] = source.mode
            record['dimensions'] = list(source.size)
            record['decodable'] = True
            record['dimensions_match'] = source.size == tuple(expected_dimensions)
            thumb = ImageOps.pad(source.convert('RGB'), THUMBNAIL,
                                 method=Image.Resampling.LANCZOS, color=BACKGROUND)
        if not record['dimensions_match']:
            issues.append({'kind': 'unexpected_dimensions', 'shot': shot['id'],
                           'actual': record['dimensions'],
                           'expected': list(expected_dimensions)})
        return record, thumb
    except (OSError, ValueError) as error:
        record['error'] = str(error)
        issues.append({'kind': 'unreadable_frame', 'shot': shot['id'],
                       'path': str(path), 'error': str(error)})
        return record, _placeholder(shot['id'], 'QUADRO ILEGIVEL OU VAZIO')


class _LocalLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attributes):
        for attribute, value in attributes:
            if attribute in ('href', 'src', 'poster') and value:
                self.references.append({'tag': tag, 'attribute': attribute, 'url': value})


def _audit_links(html_path, issues):
    audit = {'html': str(html_path), 'checked': False,
             'scope': 'relative href, src and poster attributes; no network requests',
             'references': [], 'ignored': [], 'all_relative_targets_nonempty': False}
    if not html_path.is_file():
        issues.append({'kind': 'missing_player_html', 'path': str(html_path)})
        return audit
    parser = _LocalLinks()
    try:
        parser.feed(html_path.read_text(encoding='utf-8-sig'))
    except (OSError, UnicodeError) as error:
        issues.append({'kind': 'unreadable_player_html', 'path': str(html_path), 'error': str(error)})
        return audit
    seen = set()
    for reference in parser.references:
        url = reference['url']
        parsed = urlsplit(url)
        if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith('/'):
            audit['ignored'].append({**reference, 'reason': 'not a relative file reference'})
            continue
        target = (html_path.parent/unquote(parsed.path)).resolve()
        key = (url, str(target))
        if key in seen:
            continue
        seen.add(key)
        exists = target.is_file()
        size = target.stat().st_size if exists else 0
        record = {**reference, 'resolved': str(target), 'exists': exists,
                  'bytes': size, 'nonempty': exists and size > 0}
        audit['references'].append(record)
        if not record['nonempty']:
            issues.append({'kind': 'missing_or_empty_player_target',
                           'url': url, 'resolved': str(target)})
    audit['checked'] = True
    audit['all_relative_targets_nonempty'] = bool(audit['references']) and all(
        reference['nonempty'] for reference in audit['references'])
    return audit


def _audit_delivery_files(verification, out, issues):
    """Audit only already declared final files; never decode video here."""
    checked = []
    if not verification:
        return checked
    for entry in verification.get('files', []):
        if isinstance(entry, str):
            filename = entry
        else:
            filename = next((entry.get(key) for key in ('path', 'file', 'filename')
                             if entry.get(key)), None)
        if not filename:
            checked.append({'source': entry, 'path_available': False})
            continue
        path = Path(filename)
        if not path.is_absolute():
            in_root = ROOT/path
            path = in_root if in_root.is_file() else out/path
        exists = path.is_file()
        size = path.stat().st_size if exists else 0
        checked.append({'path': str(path.resolve()), 'path_available': True,
                        'exists': exists, 'nonempty': exists and size > 0, 'bytes': size})
        if not exists or size <= 0:
            issues.append({'kind': 'missing_or_empty_declared_video', 'path': str(path)})
    return checked


def run(out=DEFAULT_OUT):
    out = Path(out).resolve()
    qa_dir = out/'verificacao_final'
    qa_dir.mkdir(parents=True, exist_ok=True)
    issues = []
    plan = _read_json(out/'plano_73_extraido.json', issues)
    verification = _read_json(out/'verificacao_video_completo_v3.json', issues)
    shots = plan.get('middle_shots', []) if plan else []
    if len(shots) != 63:
        issues.append({'kind': 'unexpected_shot_count', 'expected': 63, 'actual': len(shots)})
    ids = [shot.get('id') for shot in shots]
    if len(ids) != len(set(ids)):
        issues.append({'kind': 'duplicate_shot_ids'})
    expected_ids = [f'P{i:02d}' for i in range(5, 68)]
    if ids != expected_ids:
        issues.append({'kind': 'unexpected_shot_order_or_ids', 'expected': expected_ids, 'actual': ids})
    expected_dimensions = tuple(verification.get('resolution', [1920, 1080])) if verification else (1920, 1080)
    font = _font(22)
    small_font = _font(18)
    frame_stats, contacts = [], []
    # The expected middle contains 63 shots: four sheets, 16 slots each.
    for page in range((len(shots)+15)//16):
        sheet = Image.new('RGB', (COLS*THUMBNAIL[0], ROWS*(THUMBNAIL[1]+LABEL_HEIGHT)), BACKGROUND)
        draw = ImageDraw.Draw(sheet)
        page_shots = shots[page*16:(page+1)*16]
        for slot, shot in enumerate(page_shots):
            path = qa_dir/(shot['id']+'.png')
            record, thumb = _inspect_frame(path, shot, expected_dimensions, issues)
            frame_stats.append(record)
            x = slot % COLS*THUMBNAIL[0]
            y = slot // COLS*(THUMBNAIL[1]+LABEL_HEIGHT)
            sheet.paste(thumb, (x, y))
            draw.rectangle((x, y+THUMBNAIL[1], x+THUMBNAIL[0]-1,
                            y+THUMBNAIL[1]+LABEL_HEIGHT-1), fill='#171C22')
            label = f"{shot['id']}   {_timecode(shot['start_s'])} - {_timecode(shot['end_s'])}"
            draw.text((x+10, y+THUMBNAIL[1]+5), label, font=font, fill=FOREGROUND)
            duration = float(shot['end_s'])-float(shot['start_s'])
            duration_text = f'{duration:g} s'
            duration_width = draw.textlength(duration_text, font=small_font)
            draw.text((x+THUMBNAIL[0]-10-duration_width, y+THUMBNAIL[1]+8),
                      duration_text, font=small_font, fill=SECONDARY)
        filename = qa_dir/f'contato_final_{page+1:02d}.png'
        sheet.save(filename, format='PNG', optimize=True)
        contacts.append({'path': str(filename), 'dimensions': list(sheet.size),
                         'bytes': filename.stat().st_size,
                         'shots': [shot['id'] for shot in page_shots]})
    links = _audit_links(out/'assistir_video_completo.html', issues)
    delivery_files = _audit_delivery_files(verification, out, issues)
    counts = Counter(issue['kind'] for issue in issues)
    frames_integrity_ok = len(frame_stats) == 63 and all(
        frame['nonempty'] and frame['decodable'] and frame['dimensions_match']
        for frame in frame_stats)
    report = {
        'version': 3, 'generated_utc': datetime.now(timezone.utc).isoformat(),
        'tool': 'qa_delivery_v3.py', 'gpu_used': False,
        'external_processes_started': False, 'source_directory': str(out),
        'source_plan': str(out/'plano_73_extraido.json'),
        'source_video_verification': str(out/'verificacao_video_completo_v3.json'),
        'verification_present': verification is not None,
        'video_verification_summary': {key: verification.get(key) for key in (
            'status', 'duration_seconds', 'frame_count', 'fps', 'resolution',
            'shot_count', 'audio_tracks')} if verification else None,
        'frame_summary': {
            'expected': 63, 'inspected': len(frame_stats),
            'existing': sum(frame['exists'] for frame in frame_stats),
            'nonempty': sum(frame['nonempty'] for frame in frame_stats),
            'decodable': sum(frame['decodable'] for frame in frame_stats),
            'dimensions_match': sum(frame['dimensions_match'] for frame in frame_stats),
            'expected_dimensions': list(expected_dimensions),
            'integrity_ok': frames_integrity_ok,
        },
        'contact_sheets': contacts, 'frames': frame_stats,
        'relative_links': links, 'declared_video_files': delivery_files,
        'issues': issues, 'issue_counts': dict(counts),
        'technical_file_checks_ok': not issues,
        'visual_review': {
            'status': 'pending', 'automatically_approved': False,
            'instruction': 'Inspecionar os quatro contatos e os quadros originais; '
                           'registrar separadamente qualquer sobreposicao, corte, '
                           'problema de legibilidade ou divergencia cientifica.',
            'limitation': 'Dimensoes e arquivos integros nao comprovam a qualidade '
                          'visual nem a correção cientifica do video.',
        },
    }
    report_path = qa_dir/'qa_entrega_v3.json'
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    return report_path, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=DEFAULT_OUT,
                        help='Diretorio completo_v3 que contem o player e os quadros finais.')
    args = parser.parse_args()
    path, report = run(args.output_dir)
    print(json.dumps({'report': str(path), 'contact_sheets': len(report['contact_sheets']),
                      'frames': report['frame_summary'],
                      'technical_file_checks_ok': report['technical_file_checks_ok'],
                      'visual_review': 'pending', 'issues': report['issue_counts']},
                     ensure_ascii=False), flush=True)
    return 0 if report['technical_file_checks_ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
