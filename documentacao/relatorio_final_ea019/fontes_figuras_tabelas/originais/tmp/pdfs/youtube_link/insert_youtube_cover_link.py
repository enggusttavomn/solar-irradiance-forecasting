"""Insert the observed YouTube URL on the report cover, preserving all other pages.

Run the PDF skill authoring marker before this script. This script is prepared but
has not been run to edit a PDF. It requires an actual URL obtained from YouTube.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
import pymupdf as fitz


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https':
        raise ValueError('Expected the actual HTTPS YouTube URL.')
    host = parsed.netloc.lower()
    if host in {'youtu.be', 'www.youtu.be'}:
        video_id = parsed.path.strip('/')
    elif host in {'youtube.com', 'www.youtube.com'} and parsed.path == '/watch':
        video_id = parse_qs(parsed.query).get('v', [''])[0]
    else:
        raise ValueError('Expected a youtu.be or youtube.com/watch URL.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('Invalid YouTube video identifier.')
    return url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    url = validate_url(args.url)
    source, output = args.source.resolve(), args.output.resolve()
    if source == output:
        raise ValueError('Use a separate output for verification before replacing the canonical file.')
    if output.exists():
        raise FileExistsError(output)
    original = fitz.open(source)
    if len(original) != 37:
        raise ValueError(f'Unexpected page count: {len(original)}')
    page = original[0]
    matches = []
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                if span['text'].startswith('Link do ') and '___' in span['text']:
                    matches.append(span)
    if len(matches) != 1:
        raise ValueError(f'Expected exactly one cover placeholder; got {len(matches)}')
    span = matches[0]
    rect = fitz.Rect(span['bbox'])
    baseline = span['origin'][1]
    size = span['size']
    font_path = Path('C:/Windows/Fonts/times.ttf')
    font = fitz.Font(fontfile=str(font_path))
    label = 'Link do vídeo: '
    text = label + url
    width = font.text_length(text, fontsize=size)
    if width > page.rect.width - 120:
        raise ValueError('Link line would exceed the cover text area.')
    x = (page.rect.width - width) / 2
    page.add_redact_annot(rect + (-1, -1, 1, 1), fill=(1, 1, 1), cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    page.insert_font(fontname='CoverTimesNewRoman', fontfile=str(font_path))
    page.insert_text((x, baseline), text, fontsize=size, fontname='CoverTimesNewRoman', color=(0, 0, 0))
    url_x = x + font.text_length(label, fontsize=size)
    url_width = font.text_length(url, fontsize=size)
    clickable = fitz.Rect(url_x, baseline - 11, url_x + url_width, baseline + 3)
    page.insert_link({'kind': fitz.LINK_URI, 'from': clickable, 'uri': url})
    output.parent.mkdir(parents=True, exist_ok=True)
    original.save(output, garbage=3, deflate=True)
    original.close()

    before, after = fitz.open(source), fitz.open(output)
    if len(before) != len(after):
        raise AssertionError('Page count changed.')
    page_checks = []
    for index in range(1, len(before)):
        p0, p1 = before[index], after[index]
        same_text = p0.get_text() == p1.get_text()
        a, b = p0.get_pixmap(), p1.get_pixmap()
        same_pixels = a.width == b.width and a.height == b.height and a.samples == b.samples
        if not same_text or not same_pixels:
            raise AssertionError(f'Unexpected change on page {index + 1}.')
        page_checks.append({'page': index + 1, 'same_text': same_text, 'same_pixels': same_pixels})
    if url not in after[0].get_text():
        raise AssertionError('URL missing from cover text.')
    if not any(link.get('uri') == url for link in after[0].get_links()):
        raise AssertionError('Clickable URL annotation missing.')
    if '___' in after[0].get_text():
        raise AssertionError('Placeholder remains on cover.')
    preview = output.with_suffix('.cover.png')
    after[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(preview)
    qa = {
        'status': 'structural_checks_passed_visual_review_required',
        'source': str(source), 'output': str(output), 'url': url,
        'source_sha256': sha256(source), 'output_sha256': sha256(output),
        'page_count': len(after), 'page_checks': page_checks,
        'cover_preview': str(preview),
        'cover_link_rect': list(clickable),
        'note': 'Inspect the cover PNG before delivery or replacing the canonical report.',
    }
    qa_path = output.with_suffix('.verification.json')
    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(qa, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
