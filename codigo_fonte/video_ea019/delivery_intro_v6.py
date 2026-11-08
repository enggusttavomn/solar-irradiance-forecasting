"""Deliver only the verified 0:00-0:40 V6 revision.

No render, video decode, upload or external call is performed. The completed
render report, actual file sizes/hashes and sixteen final PNGs are checked
before the local player, README and separate root launcher are enabled.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import html
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / 'documentacao/relatorio_final_ea019/video/revisao_00_40_v6'
SOURCE_REPORT = 'verificacao_intro_v6.json'
DELIVERY_REPORT = 'verificacao_entrega_intro_v6.json'
PLAYER = 'assistir_revisao_00_40_v6.html'
VIDEOS = {'com': 'Revisao_00_40_com_legendas_v6.mp4',
          'sem': 'Revisao_00_40_sem_legendas_v6.mp4'}
ARCHITECTURE = ('https://www.hyundaimotorgroup.com/en/news/'
                'hyundai-motor-group-metaplant-america-celebrates-grand-opening-powering-us-economic-growth')
REPORT_PDF = ROOT / 'documentacao/relatorio_final_ea019/Relatorio_Final_GHI_Transformer_Informer_LSTM_Comparacao_Modelos.pdf'
PLANNING_PDF = ROOT / 'output/pdf/Planejamento_Video_GHI_75_Planos.pdf'


def _pillow():
    try:
        from PIL import Image
    except ModuleNotFoundError:
        sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
        from PIL import Image
    return Image


def _json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _inside(path, parent=ROOT):
    return path.resolve().is_relative_to(parent.resolve())


def _relative(path, parent):
    return Path(os.path.relpath(path.resolve(), parent.resolve())).as_posix()


def _declared(value, output):
    path = Path(str(value))
    if path.is_absolute():
        return path.resolve()
    candidate = (ROOT / path).resolve()
    return candidate if candidate.is_file() else (output / path).resolve()


def _error(errors, kind, **details):
    errors.append({'kind': kind, **details})


def _visual_record(source):
    record = source.get('visual_review') or source.get('manual_visual_review') or {}
    approved = (source.get('sampled_visual_review_passed') is True and isinstance(record, dict)
                and record.get('automatically_approved') is False
                and (record.get('status') in {'approved_sampled_frames', 'approved'}
                     or record.get('passed') is True))
    return {'automatically_approved': False, 'performed_by_this_script': False,
            'source_sampled_visual_review_passed': source.get('sampled_visual_review_passed') is True,
            'source_manual_record': record, 'visual_approval': approved}


def _audit_inputs(output):
    errors = []
    source = {}
    videos = []
    frames = []
    assets = []
    phases = []
    try:
        source = _json(output / SOURCE_REPORT)
        if not isinstance(source, dict):
            _error(errors, 'invalid_render_report_object')
            source = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        _error(errors, 'missing_or_invalid_render_report', error=str(error))
    expected = {'version': 6, 'status': 'complete', 'scope_seconds': [0, 40],
                'duration_seconds': 40, 'fps': 30, 'frame_count': 1200,
                'resolution': [1920, 1080], 'audio_tracks': 0, 'full_decode_errors': 0}
    for key, value in expected.items():
        if source.get(key) != value:
            _error(errors, 'render_report_not_ready', field=key, expected=value, actual=source.get(key))
    if errors:
        return source, videos, frames, assets, phases, errors
    names = []
    entries = source.get('files', [])
    if not isinstance(entries, list) or len(entries) != 2:
        _error(errors, 'unexpected_video_count', expected=2)
        entries = entries if isinstance(entries, list) else []
    metadata = {'width': 1920, 'height': 1080, 'fps': 30, 'frame_count': 1200,
                'duration_seconds': 40, 'audio_tracks': 0, 'full_decode_errors': 0}
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get('path'):
            _error(errors, 'invalid_video_record')
            continue
        path = _declared(entry['path'], output)
        names.append(path.name)
        record = {'path': str(path), 'exists': path.is_file(), 'video_decoded_again': False,
                  'size_matches': False, 'hash_matches': False,
                  'full_decode_errors_from_render': entry.get('full_decode_errors')}
        if path.parent != output or path.name not in VIDEOS.values():
            _error(errors, 'unexpected_video_path', path=str(path))
        elif not path.is_file():
            _error(errors, 'missing_video', path=str(path))
        else:
            record['actual_bytes'] = path.stat().st_size
            record['declared_bytes'] = entry.get('bytes')
            record['size_matches'] = record['actual_bytes'] > 10000 and record['actual_bytes'] == entry.get('bytes')
            if not record['size_matches']:
                _error(errors, 'video_size_mismatch', path=str(path))
            digest = str(entry.get('sha256', '')).lower()
            if not re.fullmatch('[0-9a-f]{64}', digest):
                _error(errors, 'invalid_video_hash_declaration', path=str(path))
            with path.open('rb') as stream:
                record['actual_sha256'] = hashlib.file_digest(stream, 'sha256').hexdigest()
            record['hash_matches'] = record['actual_sha256'] == digest
            if not record['hash_matches']:
                _error(errors, 'video_hash_mismatch', path=str(path))
        for key, value in metadata.items():
            if entry.get(key) != value:
                _error(errors, 'unexpected_video_metadata', path=str(path), field=key,
                       expected=value, actual=entry.get(key))
        videos.append(record)
    if set(names) != set(VIDEOS.values()) or len(names) != len(set(names)):
        _error(errors, 'unexpected_video_names', actual=names)
    samples = source.get('sampled_frames', [])
    if not isinstance(samples, list) or len(samples) != 16:
        _error(errors, 'unexpected_final_sample_count', expected=16)
        samples = samples if isinstance(samples, list) else []
    Image = _pillow()
    seen = set()
    for sample in samples:
        value = sample.get('path') if isinstance(sample, dict) else sample
        path = _declared(value, output)
        item = {'path': str(path), 'readable': False, 'dimensions_match': False}
        if path in seen:
            _error(errors, 'duplicate_final_sample', path=str(path))
        seen.add(path)
        if path.parent != (output / 'verificacao_final').resolve() or path.suffix.lower() != '.png':
            _error(errors, 'unexpected_final_sample_path', path=str(path))
        elif not path.is_file():
            _error(errors, 'missing_final_sample', path=str(path))
        else:
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    image.load()
                    item['dimensions'] = list(image.size)
                    item['readable'] = image.format == 'PNG'
                    item['dimensions_match'] = image.size == (1920, 1080)
                if not item['readable'] or not item['dimensions_match']:
                    _error(errors, 'invalid_final_sample', path=str(path))
            except (OSError, ValueError, SyntaxError) as error:
                _error(errors, 'unreadable_final_sample', path=str(path), error=str(error))
        frames.append(item)
    for path in [output / 'Falas_00_40_v6.txt', output / 'Legendas_00_40_v6.srt',
                 output / 'plano_textos_v6.json', REPORT_PDF]:
        record = {'path': str(path), 'exists': path.is_file(),
                  'bytes': path.stat().st_size if path.is_file() else 0}
        assets.append(record)
        if not record['exists'] or not record['bytes']:
            _error(errors, 'missing_supporting_asset', path=str(path))
        elif path.suffix.lower() in {'.txt', '.srt', '.json'}:
            try:
                path.read_text(encoding='utf-8-sig')
            except (UnicodeError, OSError) as error:
                _error(errors, 'unreadable_supporting_text', path=str(path), error=str(error))
    try:
        plan = _json(output / 'plano_textos_v6.json')
        assert plan['duration'] == 40
        phases = [{'start': a, 'end': b, 'narration': text} for a, b, text in plan['phases']]
        assert phases and phases[0]['start'] == 0 and phases[-1]['end'] == 40
        assert all(p['end'] > p['start'] and p['narration'] for p in phases)
        assert all(a['end'] == b['start'] for a, b in zip(phases, phases[1:]))
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, ValueError, AssertionError, TypeError) as error:
        _error(errors, 'invalid_narration_plan', error=str(error))
    return source, videos, frames, assets, phases, errors


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = []

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key in {'href', 'src', 'poster'} and value:
                self.items.append({'tag': tag, 'attribute': key, 'url': value})


def _audit_links(path, errors):
    parser = _Links()
    parser.feed(path.read_text(encoding='utf-8'))
    records = []
    for item in parser.items:
        parts = urlsplit(item['url'])
        if parts.scheme or parts.netloc or not parts.path:
            continue
        target = (path.parent / unquote(parts.path)).resolve()
        exists = _inside(target) and target.is_file() and target.stat().st_size > 0
        records.append({**item, 'resolved': str(target), 'exists': exists})
        if not exists:
            _error(errors, 'missing_or_empty_player_link', url=item['url'], path=str(target))
    return records


def _write_player(output, phases, frames):
    seek = [(0, 'Fábrica e luz'), (5, 'Área de 1 m²'), (11, 'Direta e difusa'),
            (16, 'Dia e noite'), (21, 'Nuvens'), (25, 'Histórico'),
            (30, 'Futuro'), (35, 'Aplicação possível')]
    buttons = ''.join(f'<button type="button" data-seek="{time}">{time // 60}:{time % 60:02d} · {html.escape(label)}</button>'
                      for time, label in seek)
    poster = html.escape(_relative(Path(frames[0]['path']), output), quote=True)
    report_link = _relative(REPORT_PDF, output)
    planning = (f'<a href="{html.escape(_relative(PLANNING_PDF, output), quote=True)}">Planejamento de 75 planos</a>'
                if PLANNING_PDF.is_file() else '')
    v5 = output.parent / 'completo_v5/assistir_video_v5.html'
    previous = f'<a href="{html.escape(_relative(v5, output), quote=True)}">Vídeo completo V5</a>' if v5.is_file() else ''
    shots = ''.join(f'<a href="{html.escape(_relative(Path(record["path"]), output), quote=True)}"><img loading="lazy" src="{html.escape(_relative(Path(record["path"]), output), quote=True)}" alt="Quadro final {i + 1}"></a>'
                    for i, record in enumerate(frames))
    phase_json = json.dumps(phases, ensure_ascii=False).replace('</', '<\\/')
    document = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisão 0:00-0:40 · V6</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#07090d;color:#eef3f6;font:16px/1.6 'Segoe UI',Arial,sans-serif}}main{{max-width:1180px;margin:auto;padding:32px 20px 50px}}h1{{font-size:clamp(26px,4vw,42px);line-height:1.2;margin:8px 0 14px}}h2{{font-size:21px}}p{{color:#bac8d0;max-width:940px}}.meta{{color:#8fa8b5;font-size:14px}}video{{display:block;width:100%;aspect-ratio:16/9;background:#000;margin:24px 0 14px}}.controls,.seeks,.files,.sources{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}button,.files a{{font:inherit;color:#eef3f6;background:#151d25;border:1px solid #34404b;border-radius:6px;padding:10px 14px;cursor:pointer;text-decoration:none}}button[aria-pressed=true]{{border-color:#72d3dd;background:#153038}}a{{color:#86d7e2;text-underline-offset:3px}}.narration{{margin:24px 0;padding:18px 20px;background:#111922;border-left:3px solid #659aa6}}.narration p{{margin:6px 0 0}}.notes{{padding-top:12px;border-top:1px solid #2b3741;margin-top:26px}}.sources{{gap:8px 20px;font-size:14px}}details{{margin-top:24px}}summary{{cursor:pointer}}.frames{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px}}.frames img{{display:block;width:100%;height:auto}}@media(max-width:640px){{main{{padding:22px 12px 36px}}.frames{{grid-template-columns:repeat(2,1fr)}}button,.files a{{min-height:44px}}}}
</style></head><body><main>
<div class="meta">TRECHO REVISADO · V6 · 40 SEGUNDOS</div>
<h1>Luz solar, GHI e planejamento fotovoltaico</h1>
<p>Revisão dos primeiros 40 segundos, com fábrica genérica, Sol e atmosfera, cotas de 1 m², ciclo de dia e noite e continuação tracejada do gráfico. O trecho está sem áudio para receber sua narração.</p>
<div class="meta">1920 × 1080 · 30 fps · 1.200 quadros · versões com e sem legendas</div>
<video id="player" controls playsinline preload="metadata" poster="{poster}" src="{VIDEOS['com']}"></video>
<div class="controls" role="group" aria-label="Versão do vídeo"><button type="button" data-version="com" aria-pressed="true">Com legendas</button><button type="button" data-version="sem" aria-pressed="false">Sem legendas</button></div>
<p id="state" class="meta">Com legendas de narração embutidas.</p>
<nav class="seeks" aria-label="Ir para uma cena">{buttons}</nav>
<div class="files"><a href="{VIDEOS['com']}" download>MP4 com legendas</a><a href="{VIDEOS['sem']}" download>MP4 sem legendas</a><a href="Falas_00_40_v6.txt">Falas para narrar</a><a href="Legendas_00_40_v6.srt" download>Legendas SRT</a></div>
<section class="narration" aria-label="Fala da cena atual"><span class="meta" id="phase-time"></span><p id="speech"></p></section>
<section class="notes"><h2>Contexto da revisão</h2>
<p>A área destacada é horizontal e mede 1 m × 1 m. Durante o dia, com o Sol acima do horizonte, GHI = DHI + DNI cos(θ<sub>z</sub>), em que θ<sub>z</sub> é o ângulo zenital. A iluminação e o gráfico mostram a queda da irradiância solar à noite.</p>
<p>A cobertura fotovoltaica apresentada de 0:35 a 0:40 é uma aplicação possível do planejamento do recurso solar. O estudo não estimou geração fotovoltaica, demanda industrial ou retorno financeiro. A arquitetura e o letreiro em inglês são genéricos e não identificam uma empresa real.</p></section>
<div class="sources"><a href="{html.escape(report_link, quote=True)}#page=17">Relatório: equação e recurso solar (p. 17)</a><a href="{html.escape(report_link, quote=True)}#page=7">Relatório: contexto e aplicações (p. 7)</a><a href="{ARCHITECTURE}" target="_blank" rel="noopener noreferrer">Referência arquitetônica real</a>{planning}{previous}<a href="{SOURCE_REPORT}">Verificação do vídeo</a><a href="{DELIVERY_REPORT}">Verificação da entrega</a></div>
<details><summary>16 quadros extraídos do MP4 final</summary><div class="frames">{shots}</div></details>
</main><script>
const phases={phase_json};
const versions={json.dumps(VIDEOS)};
const player=document.getElementById('player');
const speech=document.getElementById('speech');
const phaseTime=document.getElementById('phase-time');
const state=document.getElementById('state');
function stamp(t){{return Math.floor(t/60)+':'+String(Math.floor(t)%60).padStart(2,'0');}}
function update(){{const t=player.currentTime||0;const p=phases.find(p=>t>=p.start&&t<p.end)||phases[phases.length-1];speech.textContent=p.narration;phaseTime.textContent=stamp(p.start)+' - '+stamp(p.end);}}
document.querySelectorAll('[data-seek]').forEach(button=>button.addEventListener('click',()=>{{const t=Number(button.dataset.seek);if(player.readyState>0){{player.currentTime=t;update();}}else{{player.addEventListener('loadedmetadata',()=>{{player.currentTime=t;update();}},{{once:true}});player.load();}}}}));
document.querySelectorAll('[data-version]').forEach(button=>button.addEventListener('click',()=>{{const t=player.currentTime||0;const playing=!player.paused;const rate=player.playbackRate;const version=button.dataset.version;player.pause();document.querySelectorAll('[data-version]').forEach(other=>other.setAttribute('aria-pressed',String(other===button)));player.addEventListener('loadedmetadata',()=>{{player.currentTime=Math.min(t,Math.max(0,(player.duration||40)-.01));player.playbackRate=rate;update();if(playing)player.play().catch(()=>{{}});}},{{once:true}});player.src=versions[version];player.load();state.textContent=version==='com'?'Com legendas de narração embutidas.':'Sem legendas de narração; cotas, equação e rótulos das animações permanecem.';}}));
player.addEventListener('timeupdate',update);player.addEventListener('loadedmetadata',update);update();
</script></body></html>'''
    path = output / PLAYER
    path.write_text(document, encoding='utf-8')
    return path


def _readme(output):
    text = f'''REVISÃO V6 - PRIMEIROS 40 SEGUNDOS

Trecho 0:00-0:40, Full HD 1920x1080, 30 fps, 1.200 quadros. Sem áudio.
Abrir {PLAYER} ou o atalho ASSISTIR_REVISAO_40S.cmd na raiz do projeto.
Há versões com e sem legendas, falas TXT e legendas SRT para a gravação futura.

A fábrica e o letreiro ELECTRIC VEHICLE MANUFACTURING são genéricos.
A referência real orienta apenas a arquitetura, sem associação a empresa.
Vegetação, luz direta e difusa, nuvens, dia/noite e o gráfico foram revisados.
A região horizontal de referência mede exatamente 1m x 1m e usa cotas.
Equação diurna (Sol acima do horizonte): GHI = DHI + DNI cos(theta_z).
theta_z é o ângulo zenital. GHI tem unidade W/m²; não é energia acumulada.

A cobertura solar de 0:35 a 0:40 mostra uma aplicação potencial de planejamento
fotovoltaico. Não representa geração estimada, demanda da fábrica, integração
operacional medida ou resultado financeiro. O relatório avalia irradiância.

Referências: relatório final, páginas 17 e 7 (numeração do PDF), e arquitetura oficial:
{ARCHITECTURE}

O vídeo completo V5 e seu atalho ASSISTIR_VIDEO_TCC.cmd foram preservados.
Esta entrega não substitui os 6min55s completos nem inclui filmagens do aluno.

{SOURCE_REPORT} registra a decodificação integral dos dois MP4s pelo montador.
{DELIVERY_REPORT} confere tamanhos, hashes, metadados declarados, 16 PNGs e links.
A verificação técnica não constitui aprovação visual automática.
'''
    (output / 'LEIA-ME_REVISAO_00_40_V6.txt').write_text(text, encoding='utf-8-sig')


def run(output=OUTPUT):
    output = Path(output).resolve()
    if not _inside(output) or not output.is_dir():
        raise ValueError('The existing V6 output directory must remain inside the project workspace.')
    source, videos, frames, assets, phases, errors = _audit_inputs(output)
    report = {'version': 6, 'scope_seconds': [0, 40],
              'generated_utc': datetime.now(timezone.utc).isoformat(),
              'source_verification': str(output / SOURCE_REPORT),
              'pipeline_status': source.get('status'),
              'technical_ok': False, 'error_count': len(errors), 'errors': errors,
              'videos': videos, 'supporting_assets': assets,
              'sampled_frames': {'expected': 16, 'checked': len(frames),
                                 'readable': sum(item['readable'] for item in frames), 'frames': frames},
              'relative_links': [], 'video_decoding_performed': False,
              'external_processes_started': False,
              'visual_review': _visual_record(source),
              'visual_approval': _visual_record(source)['visual_approval'],
              'v5_modified': False, 'main_v5_launcher_modified': False}
    target = output / DELIVERY_REPORT
    _write_json(target, report)
    if errors:
        return target, report
    player = _write_player(output, phases, frames)
    _readme(output)
    report['relative_links'] = _audit_links(player, errors)
    report['technical_ok'] = not errors
    report['error_count'] = len(errors)
    report['errors'] = errors
    report['player'] = str(player)
    if not errors:
        launcher = ROOT / 'ASSISTIR_REVISAO_40S.cmd'
        relative_player = _relative(player, ROOT).replace('/', '\\')
        launcher.write_bytes(('@echo off\r\nstart "" "%~dp0' + relative_player + '"\r\n').encode('ascii'))
        report['launcher'] = str(launcher)
    _write_json(target, report)
    return target, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=OUTPUT)
    args = parser.parse_args()
    path, report = run(args.output_dir)
    print(json.dumps({'report': str(path), 'technical_ok': report['technical_ok'],
                      'error_count': report['error_count'], 'errors': report['errors'],
                      'videos_checked': len(report['videos']),
                      'frames_readable': report['sampled_frames']['readable'],
                      'visual_approval': report['visual_approval']}, ensure_ascii=True, indent=2), flush=True)
    return 0 if report['technical_ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
