"""Extract still review samples from the completed V11 narrated export."""

import math
import sys
from concurrent.futures import ThreadPoolExecutor

from montagem_v10_common import ROOT, FFMPEG, read, write, sha, run

sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
from PIL import Image, ImageDraw, ImageFont


OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v11'


def main():
    timeline = read(OUT / 'timeline_montagem_v11.json')
    verification = read(OUT / 'verificacao_video_final_v11.json')
    assert verification and verification['status'] in {
        'encoded_pending_timing_review', 'complete'}, 'Final V11 export is not ready'
    target = OUT / 'Video_TCC_Ritmo_Didatico_Somente_Voz_v11.mp4'
    checked = next(v for v in verification['files']
                   if v['path'].replace('\\', '/').endswith(target.name))
    target_sha = sha(target)
    assert target_sha == checked['sha256']
    assert checked['decoded_frames'] == timeline['frames']
    assert not checked['full_decode_errors']
    assert abs(verification['duration_seconds'] - timeline['duration']) < 1e-6

    qa = OUT / 'verificacao_final'
    qa.mkdir(exist_ok=True)
    times = [(x['start'] + x['end']) / 2 for x in timeline['items']]
    times += [.5, 7, 13, timeline['duration'] - 12,
              timeline['duration'] - 4, timeline['duration'] - .25]
    for index in [74, 76, 83]:
        item = next(x for x in timeline['items']
                    if x['kind'] == 'body' and x['index'] == index)
        times += [item['start'] + item['duration'] * .82]
    times = sorted(set(round(t, 4) for t in times))
    assert len(times) == 99

    def extract(second):
        path = qa / f't_{second:.4f}.png'
        run([FFMPEG, '-v', 'error', '-y', '-ss', f'{second:.6f}',
             '-threads', '2', '-i', target, '-frames:v', '1',
             '-threads', '2', '-update', '1', path])
        item = next(x for x in timeline['items']
                    if x['start'] <= second < x['end'])
        return {'time': second, 'path': str(path.relative_to(ROOT)),
                'sha256': sha(path), 'item_id': item['id'],
                'kind': item['kind'], 'item_index': item['index']}

    with ThreadPoolExecutor(max_workers=3) as pool:
        stills = list(pool.map(extract, times))
    assert len(set(x['item_id'] for x in stills)) == 90
    font = ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf', 20)
    sheets = []
    for start in range(0, len(stills), 12):
        group = stills[start:start + 12]
        sheet = Image.new('RGB', (1920, 388 * math.ceil(len(group) / 3)), (6, 7, 8))
        draw = ImageDraw.Draw(sheet)
        for index, record in enumerate(group):
            x, y = index % 3 * 640, index // 3 * 388
            with Image.open(ROOT / record['path']) as frame:
                sheet.paste(frame.resize((640, 360), Image.Resampling.LANCZOS), (x, y + 28))
            second = record['time']
            draw.text((x + 8, y), f'{int(second)//60}:{second%60:05.2f}',
                      fill=(230, 235, 240), font=font)
        path = qa / f'contato_v11_{start//12+1}.png'
        sheet.save(path)
        sheets.append(str(path.relative_to(ROOT)))
    assert len(sheets) == 9
    write(OUT / 'amostras_exportacao_v11.json', {
        'video': str(target.relative_to(ROOT)), 'video_sha256': target_sha,
        'stills': stills, 'contact_sheets': sheets, 'count': len(stills),
        'timeline_items_covered': 90, 'timeline_items_total': 90,
        'scope': 'Still-frame visual sampling, not full realtime playback or audio listening',
    })
    print(f'V11_SAMPLES_READY: {len(stills)} stills, {len(sheets)} sheets', flush=True)


if __name__ == '__main__':
    main()
