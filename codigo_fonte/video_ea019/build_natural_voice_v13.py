"""Rebuild the approved edit from original recordings without voice processing.

Raw AAC is decoded once to packed float stereo. The voice path uses only sample
selection, the existing 7ms join ramps, inserted zeros and an optional constant
gain explicitly recorded in the manifest. No cleaned/normalized source is read.
"""
from argparse import ArgumentParser
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
import numpy as np
from scipy.io import wavfile

from montagem_v10_common import read, write, sha, run, FFMPEG
from audit_delivery_v8 import mp4_headers

RATE, CHANNELS, FPS = 48000, 2, 30
SPF, FADE = 1600, 336
INTRO_PTS_OFFSET = 2658  # Original WIN MP4's first audio PTS, verified with -debug_ts.
OLD = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12'
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v13'
TMP = ROOT / 'tmp/montagem_final_v13/audio'
MAIN_SOURCE = Path('C:/Users/gusta/OneDrive/Documents/Sound Recordings/GRAVACAO.m4a')
INTRO_SOURCE = Path('C:/Users/gusta/Pictures/Camera Roll/WIN_20261104_20_01_05_Pro.mp4')
MUSIC_SOURCE = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v10/audio/trilha_ambiente_original_v10.wav'
VOICE = OUT / 'audio/voz_original_natural_v13.wav'
MUSIC = OUT / 'audio/trilha_baixa_independente_v13.wav'
MIX = OUT / 'audio/voz_original_com_trilha_baixa_v13.wav'
META = OUT / 'manifesto_voz_natural_v13.json'
VOICE_ONLY = OUT / 'Video_TCC_Final_SomenteVozNatural_v13.mp4'
WITH_MUSIC = OUT / 'Video_TCC_Final_ComTrilhaVozNatural_v13.mp4'


def relative(path):
    return path.relative_to(ROOT).as_posix()


def absolute(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def source_decode(source, path):
    command = [FFMPEG, '-v', 'error', '-y', '-threads', 2, '-i', source,
               '-map', '0:a:0', '-vn', '-c:a', 'pcm_f32le', '-f', 'f32le', path]
    run(command)
    values = np.memmap(path, dtype='<f4', mode='r').reshape(-1, CHANNELS)
    return values, [str(value) for value in command]


def db(value):
    return float(20 * np.log10(max(float(value), 1e-15)))


def meter(path):
    # This is a read-only meter into the null muxer. It is never in an export path.
    command = [FFMPEG, '-hide_banner', '-nostats', '-threads', 2, '-i', path,
               '-vn', '-af', 'ebur128=peak=true:framelog=verbose', '-f', 'null', '-']
    result = run(command)
    text = result.stderr
    integrated = re.findall(r'\bI:\s*(-?[\d.]+) LUFS', text)
    peak = re.findall(r'True peak:\s*\n\s*Peak:\s*(-?[\d.]+) dBFS', text)
    return {'integrated_lufs': float(integrated[-1]) if integrated else None,
            'true_peak_dbtp': float(peak[-1]) if peak else None,
            'meter_command': [str(value) for value in command],
            'meter_modifies_audio': False}


def prepare(gain_db=-1., music_gain_db=-6.93575):
    TMP.mkdir(parents=True, exist_ok=True)
    (OUT / 'audio').mkdir(parents=True, exist_ok=True)
    voice_plan_path = OUT / 'voz_e_legendas_continuas_v13.json'
    voice_plan = read(voice_plan_path)
    protected = {str(path): sha(path) for path in [MAIN_SOURCE, INTRO_SOURCE, voice_plan_path]}
    main, decode_main = source_decode(MAIN_SOURCE, TMP / 'gravacao_original_stereo_48k.f32')
    intro, decode_intro = source_decode(INTRO_SOURCE, TMP / 'apresentacao_original_stereo_48k.f32')
    assert len(main) == 27823104
    intro_samples = round(voice_plan['intro_duration'] * RATE)
    frames = int(voice_plan['frames'])
    total_samples = frames * SPF
    assert intro_samples == 678400 and len(intro) == 675840
    assert voice_plan['duration'] == frames / FPS == 488.9
    gain = float(10 ** (gain_db / 20))
    packed = np.memmap(TMP / 'voz_original_montada_v13.f32', dtype='<f4', mode='w+', shape=(total_samples, CHANNELS))
    packed[:] = 0
    intro_used = min(len(intro), intro_samples - INTRO_PTS_OFFSET)
    packed[INTRO_PTS_OFFSET:INTRO_PTS_OFFSET + intro_used] = intro[:intro_used] * gain
    checks = []
    cursor = 0
    for index, event in enumerate(voice_plan['events']):
        a, b = int(event['output_start_sample']), int(event['output_end_sample'])
        assert a == cursor and b > a
        global_a, global_b = intro_samples + a, intro_samples + b
        if event['kind'] == 'recorded_voice':
            sa, sb = int(event['source_start_sample']), int(event['source_end_sample'])
            assert sb - sa == b - a
            part = np.array(main[sa:sb], dtype=np.float32, copy=True)
            fade = min(FADE, len(part) // 2)
            ramp = np.arange(fade, dtype=np.float64) / max(1, fade - 1)
            part[:fade] = (part[:fade].astype(np.float64) * ramp[:, None]).astype(np.float32)
            part[-fade:] = (part[-fade:].astype(np.float64) * ramp[::-1, None]).astype(np.float32)
            packed[global_a:global_b] = part * gain
            expected_interior = np.asarray(main[sa + fade:sb - fade]) * gain
            exact = np.array_equal(np.asarray(packed[global_a + fade:global_b - fade]), expected_interior)
            assert exact
            checks.append({'event_index': index, 'kind': event['kind'],
                           'source_start_sample': sa, 'source_end_sample': sb,
                           'global_start_sample': global_a, 'global_end_sample': global_b,
                           'original_stereo_interior_exact_after_constant_gain': exact,
                           'fade_samples': fade})
        else:
            assert event['kind'] == 'observation_pause'
            assert not np.any(packed[global_a:global_b])
            checks.append({'event_index': index, 'kind': event['kind'],
                           'global_start_sample': global_a, 'global_end_sample': global_b,
                           'all_samples_zero': True})
        cursor = b
    assert cursor == round(voice_plan['edited_main_seconds'] * RATE)
    assert total_samples >= intro_samples + cursor
    assert not np.any(packed[intro_samples + cursor:])
    assert np.all(np.isfinite(packed))
    packed.flush()
    wavfile.write(VOICE, RATE, packed)
    main_peak = float(np.max(np.abs(packed)))
    voice_meter = meter(VOICE)

    # Duck ONLY the independent music branch. VOICE is a read-only control
    # signal here; its unprocessed PCM is added later, outside this graph.
    music_graph = (
        f'[0:a]atrim=duration={voice_plan["duration"]:.8f},asetpts=PTS-STARTPTS,'
        f'volume={music_gain_db:.6f}dB,afade=t=in:st=0:d=1.8,'
        f'afade=t=out:st={voice_plan["duration"]-3:.8f}:d=3[m];'
        '[m][1:a]sidechaincompress=threshold=0.04:ratio=6:attack=25:release=650:'
        f'knee=4:link=maximum:mix=1,apad=whole_len={total_samples},'
        f'atrim=end_sample={total_samples}[music_only]')
    music_command = [FFMPEG, '-v', 'error', '-y', '-threads', 2, '-i', MUSIC_SOURCE,
                     '-i', VOICE, '-filter_complex', music_graph, '-map', '[music_only]',
                     '-t', f'{voice_plan["duration"]:.8f}',
                     '-c:a', 'pcm_f32le', '-ar', RATE, '-ac', CHANNELS,
                     '-map_metadata', -1, MUSIC]
    run(music_command)
    music_rate, music = wavfile.read(MUSIC, mmap=True)
    assert music_rate == RATE and music.shape == packed.shape
    mixed = np.memmap(TMP / 'voz_original_trilha_montada_v13.f32', dtype='<f4', mode='w+', shape=packed.shape)
    for start in range(0, total_samples, RATE * 30):
        end = min(total_samples, start + RATE * 30)
        mixed[start:end] = packed[start:end] + music[start:end]
    mixed.flush()
    wavfile.write(MIX, RATE, mixed)
    assert np.all(np.isfinite(mixed))
    mixed_meter = meter(MIX)
    assert protected == {str(path): sha(path) for path in [MAIN_SOURCE, INTRO_SOURCE, voice_plan_path]}
    metadata = {
        'version': 13, 'status': 'natural_audio_ready_waiting_visual_stream',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'duration_seconds': voice_plan['duration'], 'frames': frames, 'fps': FPS,
        'sample_rate': RATE, 'channels': CHANNELS, 'pcm_format': 'float32 stereo, no integer clipping',
        'total_samples_per_channel': total_samples, 'intro_samples': intro_samples,
        'intro_original_decoded_samples': len(intro),
        'intro_original_audio_pts_offset_samples': INTRO_PTS_OFFSET,
        'intro_original_audio_pts_offset_seconds': INTRO_PTS_OFFSET / RATE,
        'intro_original_samples_used': intro_used,
        'intro_final_silent_tail_samples_not_used': len(intro) - intro_used,
        'intro_sync_evidence': 'Original WIN -debug_ts first AAC packet PTS2658=0.055375s; three cross-correlations against approved V10 timing independently found the same offset. V10 is timing reference only, never an audio source.',
        'edited_narration_samples': cursor, 'final_zero_tail_samples': total_samples - intro_samples - cursor,
        'voice_constant_gain_db': gain_db, 'voice_constant_gain': gain,
        'voice_processing_filters': [], 'denoising_used': False, 'equalization_used': False,
        'compression_used': False, 'limiting_used': False, 'loudness_normalization_used': False,
        'voice_time_stretch_used': False, 'voice_synthesis_used': False,
        'voice_channels_preserved': True, 'join_fade_samples': FADE, 'join_fade_seconds': FADE / RATE,
        'voice_edit_plan_path': relative(voice_plan_path), 'voice_edit_plan_sha256': sha(voice_plan_path),
        'sources': [{'role': role, 'path': str(path), 'sha256': sha(path)} for role, path in
                    [('original_narration', MAIN_SOURCE), ('original_camera_introduction', INTRO_SOURCE)]],
        'source_decode_commands': [decode_main, decode_intro],
        'raw_source_paths': {'narration': relative(TMP / 'gravacao_original_stereo_48k.f32'),
                             'intro': relative(TMP / 'apresentacao_original_stereo_48k.f32')},
        'voice_path': relative(VOICE), 'voice_sha256': sha(VOICE),
        'music_path': relative(MUSIC), 'music_sha256': sha(MUSIC),
        'mixed_path': relative(MIX), 'mixed_sha256': sha(MIX),
        'music_source_path': relative(MUSIC_SOURCE), 'music_source_sha256': sha(MUSIC_SOURCE),
        'music_fixed_gain_db': music_gain_db, 'music_command': [str(value) for value in music_command],
        'music_ducking_used': True, 'voice_untouched_by_music_preparation': True,
        'music_compressor_applies_only_to_music': True,
        'mix_operation': 'Linear float32 addition: original natural voice + independently ducked music. No compressor, denoiser, EQ, limiter or time change on the voice or final mix.',
        'natural_voice_sample_peak': main_peak, 'natural_voice_sample_peak_dbfs': db(main_peak),
        'music_mix_sample_peak': float(np.max(np.abs(mixed))),
        'voice_loudness_read_only_meter': voice_meter, 'mix_loudness_read_only_meter': mixed_meter,
        'interior_checks': checks,
        'intro_original_samples_exact_after_constant_gain': bool(np.array_equal(
            packed[INTRO_PTS_OFFSET:INTRO_PTS_OFFSET + intro_used], intro[:intro_used] * gain)),
        'intro_leading_pts_alignment_zeros_exact': bool(not np.any(packed[:INTRO_PTS_OFFSET])),
        'captions_and_timeline_changes': 'Only remove the failed final attempt539.89–541.60 and shorten the final factory shot. Body timing/107cues unchanged.',
        'external_uploads_performed': False, 'audio_listening_performed': False,
    }
    write(META, metadata)
    print('V13_NATURAL_AUDIO_READY', json.dumps({'voice': relative(VOICE), 'mix': relative(MIX),
                                               'voice_meter': voice_meter, 'mix_meter': mixed_meter}, ensure_ascii=True), flush=True)
    return metadata


def mux(video_path):
    metadata = read(META)
    if not metadata:
        raise SystemExit('Prepare original natural voice first')
    video_path = absolute(video_path)
    header = mp4_headers(video_path)
    assert header['frame_count'] == metadata['frames'] and header['fps'] == FPS
    assert header['width'] == 1920 and header['height'] == 1080
    assert abs(header['duration_seconds'] - metadata['duration_seconds']) < 1e-5
    input_hash = sha(video_path)
    results, commands = [], []
    for audio_path, target in [(VOICE, VOICE_ONLY), (MIX, WITH_MUSIC)]:
        command = [FFMPEG, '-v', 'error', '-y', '-i', video_path, '-i', audio_path,
                   '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
                   '-c:a', 'aac', '-b:a', '320k', '-ar', RATE, '-ac', CHANNELS,
                   '-t', f'{metadata["duration_seconds"]:.8f}', '-map_metadata', -1,
                   '-movflags', '+faststart', target]
        run(command)
        info = common_media_info(target)
        assert info['decoded_frames'] == metadata['frames'] and not info['full_decode_errors']
        results.append(info)
        commands.append([str(value) for value in command])
    packet_hashes = [run([FFMPEG, '-v', 'error', '-i', path, '-map', '0:v:0', '-c', 'copy',
                          '-f', 'hash', '-hash', 'sha256', '-']).stdout.strip()
                     for path in [video_path, VOICE_ONLY, WITH_MUSIC]]
    assert len(set(packet_hashes)) == 1
    assert sha(video_path) == input_hash
    metadata.update({'status': 'encoded_pending_independent_qa', 'visual_stream_path': relative(video_path),
                     'visual_stream_sha256': input_hash, 'mux_commands': commands, 'files': results,
                     'same_video_packets_as_authorized_visual_stream': True,
                     'video_stream_sha256': packet_hashes[0], 'video_reencoded_by_this_script': False})
    write(META, metadata)
    write(OUT / 'verificacao_video_final_v13.json', {
        'version': 13, 'status': 'encoded_pending_independent_qa', 'files': results,
        'duration_seconds': metadata['duration_seconds'], 'frames': metadata['frames'],
        'fps': FPS, 'resolution': [1920, 1080], 'voice_natural_original': True,
        'voice_processing_filters': [], 'voice_constant_gain_db': metadata['voice_constant_gain_db'],
        'music_ducking_used': metadata['music_ducking_used'], 'same_video_bitstream': True,
        'video_stream_sha256': packet_hashes[0], 'manifest_path': relative(META),
    })
    print('V13_NATURAL_EXPORTS_READY', flush=True)


def common_media_info(path):
    from montagem_v10_common import media_info
    value = media_info(path, decode=True)
    value['mp4_header'] = mp4_headers(path)
    return value


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--voice-gain-db', type=float, default=-1.)
    parser.add_argument('--music-gain-db', type=float, default=-6.93575)
    parser.add_argument('--mux-video')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.voice_gain_db, args.music_gain_db)
    if args.mux_video:
        mux(args.mux_video)
    if not args.prepare and not args.mux_video:
        parser.print_help()
