"""Record the checked V11 pacing revision and make its player the local default."""
from datetime import datetime, timezone
from pathlib import Path
import shutil
import time

import montagem_v10_common as common
import render_montagem_v11 as renderer

ROOT, OUT, TMP = common.ROOT, renderer.OUT, renderer.TMP
read, write, sha = common.read, common.write, common.sha


def relative(path):
    return path.relative_to(ROOT).as_posix()


def main():
    verification = read(OUT / 'verificacao_video_final_v11.json')
    timing = read(OUT / 'relatorio_ritmo_v11.json')
    samples = read(OUT / 'amostras_exportacao_v11.json')
    visual_path, temporal_path, audio_path = [TMP / name for name in
        ['qa_visual_v11.json', 'qa_temporal_v11.json', 'audit_audio_mix_v11.json']]
    visual, temporal, audio = [read(path) for path in [visual_path, temporal_path, audio_path]]
    assert visual['sampled_visual_review_passed'] and not visual['material_findings_remaining']
    assert temporal['sampled_temporal_review_passed'] and not temporal['material_flags']
    assert temporal['all_native_source_frames_match_with_codec_tolerance']
    assert not temporal['source_comparison_failures'] and not temporal['caption_offset_conflicts']
    assert audio['status'] == 'pass' and not audio['errors'] and not audio['material_flags']
    assert timing['body_animation_playback_speed'] == 1. and not timing['body_animations_accelerated']
    assert timing['all_v10_edited_clips_exact'] and timing['all_padding_zero']
    assert verification['same_video_bitstream'] and verification['frames'] == 17634
    assert verification['duration_seconds'] == 587.8 and verification['duration_seconds'] < 600
    assert samples['video_sha256'] == verification['files'][0]['sha256']
    assert len(samples['stills']) == 99
    for sample in samples['stills']:
        assert sha(ROOT / sample['path']) == sample['sha256']
    for value in verification['files']:
        path = ROOT / value['path']
        assert sha(path) == value['sha256'] and path.stat().st_size == value['bytes']
        assert value['decoded_frames'] == 17634 and not value['full_decode_errors']

    qa = OUT / 'revisao'
    qa.mkdir(exist_ok=True)
    report_records = []
    for source in [visual_path, temporal_path, audio_path, TMP / 'plano_ritmo_v11.json', TMP / 'ancoras_visuais.json']:
        target = qa / source.name
        shutil.copy2(source, target)
        report_records.append({'path': relative(target), 'sha256': sha(target)})
    central = {
        'scope': 'Manual review of all 36 stills in final-export contact sheets 4, 5 and 6.',
        'sampled_visual_review_passed': True,
        'material_findings_remaining': [], 'sample_count': 36,
        'contact_sheets': [{'path': relative(path), 'sha256': sha(path)} for path in
                          [OUT / 'verificacao_final' / f'contato_v11_{n}.png' for n in [4, 5, 6]]],
        'confirmed': ['Histogram axes, positive-hour counts and locality labels are legible.',
                      'Named factory inputs and task horizons are clear.',
                      'Training, validation, refit and retrospective-test labels are unobstructed.',
                      'Quantization examples and the geometric MAE diagrams are legible.',
                      'Captions stay in their reserved lower area.'],
        'full_realtime_playback_reviewed': False, 'audio_listening_performed': False,
    }
    write(qa / 'qa_central_v11.json', central)
    report_records.append({'path': relative(qa / 'qa_central_v11.json'), 'sha256': sha(qa / 'qa_central_v11.json')})
    consolidated = {
        'version': 11, 'status': 'complete', 'completed_utc': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': 587.8, 'duration_display': '9min47.8s',
        'previous_v10_duration_seconds': 453.4, 'recovered_visual_time_seconds': 134.4,
        'frames': 17634, 'fps': 30, 'resolution': [1920, 1080],
        'files': verification['files'], 'body_phases': 88,
        'native_body_animation_seconds': 547., 'body_output_seconds': timing['body_output_seconds'],
        'body_animation_speed': 1., 'accelerated_body_scenes': 0,
        'reading_pauses_and_native_motion_preserved': True,
        'voice_time_stretch_used': False, 'voice_synthesis_used': False,
        'all_90_edited_voice_clips_unchanged': True,
        'all_130_caption_texts_unchanged_and_retimed_with_voice': True,
        'same_retake_selections_and_new_ending_as_v10': True,
        'opening_approved_colors_and_black_background_preserved': True,
        'lstm_exception_label_repair_preserved': True,
        'visual_midpoint_and_extra_samples_reviewed': 99,
        'timeline_items_covered': 90, 'sequential_temporal_samples_reviewed': 132,
        'temporal_phases_covered': 22, 'temporal_source_1x_correspondence_passed': True,
        'sampled_visual_review_passed': True, 'sampled_temporal_review_passed': True,
        'objective_audio_review_passed': True, 'full_decode_passed_both_exports': True,
        'same_video_bitstream_in_both_versions': True,
        'encoder': 'Intel Quick Sync h264_qsv',
        'full_realtime_playback_reviewed': False, 'audio_listening_performed': False,
        'review_scope_limit': 'Reviewed static and sequential frame samples and objective source/audio checks; no full realtime playback or human listening.',
        'reports': report_records, 'production_sources_preserved': True,
    }
    write(OUT / 'revisao_final_montagem_v11.json', consolidated)
    verification.update({
        'status': 'complete', 'sampled_visual_review_passed': True,
        'sampled_temporal_review_passed': True, 'objective_audio_review_passed': True,
        'visual_samples_reviewed': 99, 'sequential_temporal_samples_reviewed': 132,
        'review_report': relative(OUT / 'revisao_final_montagem_v11.json'),
    })
    write(OUT / 'verificacao_video_final_v11.json', verification)
    renderer.write_player(read(OUT / 'timeline_montagem_v11.json'))
    launcher = ROOT / 'ASSISTIR_VIDEO_TCC.cmd'
    backup = ROOT / 'ASSISTIR_VIDEO_TCC_ANTES_V11.cmd'
    if launcher.exists() and not backup.exists():
        shutil.copy2(launcher, backup)
    shutil.copy2(ROOT / 'ASSISTIR_VIDEO_RITMO_DIDATICO_V11.cmd', launcher)
    (OUT / 'LEIA_ME_VIDEO_FINAL_V11.txt').write_text(
        'VÍDEO FINAL — RITMO DIDÁTICO V11\n\n'
        'Duração: 9min47,8s (aproximadamente 9min48s), incluindo apresentação e encerramento.\n'
        'Full HD 1920×1080, 30 quadros/s. Dentro do limite acadêmico de 10 minutos.\n\n'
        'PARA ASSISTIR\n'
        'Abra assistir_video_ritmo_didatico_v11.html e escolha o áudio.\n'
        'Na raiz do projeto, ASSISTIR_VIDEO_TCC.cmd abre esta versão.\n'
        'Os botões do player permitem ir às redes, quantização, MAE e resultados.\n\n'
        'ARQUIVOS FINAIS\n'
        'Video_TCC_Ritmo_Didatico_Somente_Voz_v11.mp4 — apresentação e narração, sem música.\n'
        'Video_TCC_Ritmo_Didatico_Com_Trilha_v11.mp4 — mesma imagem, com instrumental baixo e redução durante a fala.\n'
        'Legendas_Finais_v11.srt — legendas externas; também estão gravadas na imagem.\n\n'
        'O QUE MUDOU EM RELAÇÃO À V10 DE 7MIN33S\n'
        'Foram recuperados 2min14,4s para as construções e pausas visuais.\n'
        'Todas as 88 animações centrais são reproduzidas na velocidade original.\n'
        'Os 547 segundos originais de animação foram preservados; pequenas retenções\n'
        'do diagrama concluído permitem terminar as falas sem cortar ou acelerar.\n'
        'A voz entra nos momentos adequados, por exemplo no resultado 28 do MAE e na varredura de 72 horas.\n'
        'Não houve aceleração, síntese nem nova seleção dos trechos de voz.\n'
        'Mantidos os cortes das cinco repetições, a correção da LSTM, a capa aprovada e o novo encerramento.\n'
        'Na abertura, você e a cadeira continuam coloridos, os títulos têm cores do projeto e o fundo é preto.\n\n'
        'CONFERÊNCIA\n'
        'Decodificação integral dos dois arquivos, 99 amostras gerais, 132 quadros sequenciais\n'
        'em 22 fases comparados aos instantes originais e verificações objetivas da voz e trilha.\n'
        'Não foi feita escuta humana nem reprodução integral em tempo real.\n'
        'Registros em verificacao_video_final_v11.json e revisao_final_montagem_v11.json.\n'
        'Os vídeos anteriores, relatório e gravações originais foram preservados.\n', encoding='utf-8')
    write(OUT / 'progresso_montagem_v11.json', {
        'stage': 'complete', 'updated_unix': time.time(), 'duration_seconds': 587.8,
        'exports': 2, 'body_animation_speed': 1., 'accelerated_body_scenes': 0,
        'verification': relative(OUT / 'verificacao_video_final_v11.json'),
    })
    print('V11_DELIVERY_COMPLETE: 2 exports, 587.8 seconds, all 88 body animations at native 1x')


if __name__ == '__main__':
    main()
