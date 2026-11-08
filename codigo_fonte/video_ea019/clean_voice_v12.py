"""Conservative local denoising with measured FFT-delay compensation.

This prepares an uncut narration source. It never chooses takes, removes words,
changes the recording speed or overwrites the M4A supplied by the user.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.venv/Lib/site-packages'))
import numpy as np
from scipy.signal import butter, correlate, correlation_lags, sosfilt

SOURCE = Path('C:/Users/gusta/OneDrive/Documents/Sound Recordings/GRAVACAO.m4a')
FFMPEG = ROOT / '.tools/video-python/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe'
TMP = ROOT / 'tmp/montagem_final_v12/voice_pcm'
OUT = ROOT / 'documentacao/relatorio_final_ea019/video/montagem_final_v12/audio'
RATE = 48000
FFT_DELAY = 1200
FILTER = 'highpass=f=70,afftdn=nr=6:nf=-60:tn=0:gs=6'
RAW = TMP / 'gravacao_raw_48k.wav'
HP = TMP / 'highpass_reference_48k.f32'
ALIGNED = TMP / 'gravacao_clean_alinhada_antes_ganho_48k.f32'
CLEAN = OUT / 'gravacao_limpa_integral_48k.wav'
MANIFEST = OUT / 'limpeza_voz_v12.json'


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def relative(path):
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def run(args):
    result = subprocess.run([str(FFMPEG), *[str(a) for a in args]], capture_output=True,
                            cwd=ROOT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-7000:])
    return result


def db(value):
    return float(20 * np.log10(max(float(value), 1e-12)))


def windows(x, rate=RATE):
    size = rate // 10
    count = len(x) // size
    return np.sqrt(np.mean(np.asarray(x[:count * size]).reshape(count, size).astype(np.float64) ** 2, axis=1))


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    source_hash = sha(SOURCE)
    run(['-v', 'error', '-y', '-threads', 2, '-i', SOURCE, '-map', '0:a:0', '-vn',
         '-af', 'asetpts=PTS-STARTPTS', '-ac', 1, '-ar', RATE,
         '-c:a', 'pcm_s16le', '-map_metadata', -1, RAW])
    with wave.open(str(RAW), 'rb') as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, RATE)
        n = handle.getnframes()
        raw = np.frombuffer(handle.readframes(n), dtype='<i2').astype(np.float32) / 32768
    # The FFT filter adds 25ms of algorithmic delay. Extend its input by that
    # amount so the last original samples can flush, then remove exactly the
    # added latency. This keeps every original source timestamp meaningful.
    graph = (
        f'[0:a]highpass=f=70,asplit=2[h][d];'
        f'[d]apad=pad_len={FFT_DELAY},afftdn=nr=6:nf=-60:tn=0:gs=6,'
        f'atrim=start_sample={FFT_DELAY}:end_sample={n + FFT_DELAY},asetpts=PTS-STARTPTS[c]')
    run(['-v', 'error', '-y', '-threads', 2, '-i', RAW, '-filter_complex', graph,
         '-map', '[h]', '-f', 'f32le', HP, '-map', '[c]', '-f', 'f32le', ALIGNED])
    hp = np.memmap(HP, dtype='<f4', mode='r')
    clean = np.memmap(ALIGNED, dtype='<f4', mode='r')
    assert len(hp) == len(clean) == n
    peak = float(np.max(np.abs(clean)))
    # IIR high-pass transient overshoot can exceed full scale, so apply one
    # constant gain before converting back to 16 bit. No peak gate/limiter is used.
    gain = min(1., 10 ** (-1.5 / 20) / max(peak, 1e-12))
    with wave.open(str(CLEAN), 'wb') as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        for begin in range(0, n, RATE * 30):
            block = np.rint(np.asarray(clean[begin:begin + RATE * 30]) * gain * 32768).astype('<i2')
            handle.writeframesraw(block.tobytes())
    with wave.open(str(CLEAN), 'rb') as handle:
        assert handle.getnframes() == n
        actual = np.frombuffer(handle.readframes(n), dtype='<i2').astype(np.float32) / 32768
    noise_before, noise_after = windows(hp), windows(clean)
    raw_windows = windows(raw)
    voice = raw_windows > 10 ** (-35 / 20)
    quiet = (raw_windows >= 10 ** (-80 / 20)) & (raw_windows < 10 ** (-50 / 20))
    reductions = 20 * np.log10(np.maximum(noise_before, 1e-12) / np.maximum(noise_after, 1e-12))
    sos = butter(3, [300, 3000], btype='bandpass', fs=RATE, output='sos')
    alignment = []
    for second in [2, 38, 102, 183, 305, 450, 560]:
        a, b = int(second * RATE), int((second + 4) * RATE)
        reference = sosfilt(sos, np.asarray(hp[a:b], dtype=np.float64))
        treated = sosfilt(sos, np.asarray(clean[a:b], dtype=np.float64))
        correlation = correlate(treated, reference, mode='full', method='fft')
        lags = correlation_lags(len(treated), len(reference))
        candidates = abs(lags) <= 7200
        lag = int(lags[candidates][np.argmax(correlation[candidates])])
        alignment.append({'source_start_seconds': second, 'duration_seconds': 4,
                          'best_lag_samples': lag,
                          'voice_band_correlation_at_zero_lag': float(np.corrcoef(reference, treated)[0, 1])})
    assert all(row['best_lag_samples'] == 0 for row in alignment)
    assert min(row['voice_band_correlation_at_zero_lag'] for row in alignment) > .995
    assert np.max(np.abs(actual)) < 1
    assert sha(SOURCE) == source_hash
    stereo_result = run(['-v', 'error', '-threads', 2, '-i', SOURCE, '-t', 45,
                         '-map', '0:a:0', '-vn', '-ar', RATE, '-ac', 2, '-f', 'f32le', 'pipe:1'])
    stereo = np.frombuffer(stereo_result.stdout, dtype='<f4').reshape(-1, 2)
    stereo_check = {
        'sample_duration_seconds': len(stereo) / RATE,
        'channel_correlation': float(np.corrcoef(stereo.T)[0, 1]),
        'channel_rms_dbfs': [db(np.sqrt(np.mean(stereo[:, i].astype(np.float64) ** 2))) for i in range(2)],
        'channel_peak_dbfs': [db(np.max(np.abs(stereo[:, i]))) for i in range(2)],
        'mono_downmix': 'FFmpeg -ac1 standard equal-weight stereo-to-mono; first45s channels checked',
    }
    hits = np.flatnonzero(np.abs(raw) >= .999)
    spans = []
    for hit in hits:
        if not spans or hit - spans[-1][1] > RATE * .05:
            spans.append([int(hit), int(hit), 1])
        else:
            spans[-1][1] = int(hit)
            spans[-1][2] += 1
    meta = {
        'version': 12, 'status': 'ready_for_editing',
        'generated_utc': datetime.now(timezone.utc).isoformat(),
        'source_path': str(SOURCE), 'source_sha256': source_hash, 'source_modified': False,
        'raw_path': relative(RAW), 'raw_sha256': sha(RAW),
        'clean_path': relative(CLEAN), 'clean_sha256': sha(CLEAN),
        'sample_rate': RATE, 'channels': 1, 'sample_width_bytes': 2,
        'source_pcm_samples': n, 'clean_pcm_samples': n, 'duration_seconds': n / RATE,
        'timebase': 'First decoded original PCM sample = 0; no compressed-source seeking.',
        'base_filters': FILTER,
        'actual_filtergraph': graph,
        'denoiser_noise_reduction_limit_db': 6,
        'noise_floor_dbfs': -60,
        'noise_tracking': False,
        'gain_smoothing_radius': 6,
        'algorithmic_delay_measured_before_compensation_samples': FFT_DELAY,
        'algorithmic_delay_compensated_seconds': FFT_DELAY / RATE,
        'input_extended_by_zero_samples': FFT_DELAY,
        'uniform_output_gain': gain, 'uniform_output_gain_db': db(gain),
        'global_loudness_normalization_performed': False,
        'normalization_recommendation': 'Normalize the assembled final voice edit to about -16 LUFS with a true-peak ceiling; keep timestamps/sample length unchanged.',
        'raw_peak_dbfs': db(np.max(np.abs(raw))),
        'raw_samples_at_or_above_0_999': int(np.sum(np.abs(raw) >= .999)),
        'raw_peak_fraction': float(np.mean(np.abs(raw) >= .999)),
        'original_near_full_scale_event_times': [
            {'start': a / RATE, 'end': b / RATE, 'near_fullscale_samples': count}
            for a, b, count in spans],
        'stereo_input_check': stereo_check,
        'raw_rms_dbfs': db(np.sqrt(np.mean(raw.astype(np.float64) ** 2))),
        'highpass_float_peak_before_headroom_gain': float(np.max(np.abs(hp))),
        'clean_float_peak_before_headroom_gain': peak,
        'clean_output_peak_dbfs': db(np.max(np.abs(actual))),
        'clean_output_samples_at_or_above_0_999': int(np.sum(np.abs(actual) >= .999)),
        'clean_output_rms_dbfs': db(np.sqrt(np.mean(actual.astype(np.float64) ** 2))),
        'alignment_checks': alignment,
        'comparison_windows_ms': 100,
        'voice_window_criterion': 'Original RMS > -35 dBFS',
        'voice_windows': int(np.sum(voice)),
        'median_denoiser_attenuation_in_voice_windows_db': float(np.median(reductions[voice])),
        'quiet_candidate_criterion': '-80 <= original 100ms RMS < -50 dBFS; a proxy, not labeled noise ground truth.',
        'quiet_candidate_windows': int(np.sum(quiet)),
        'median_denoiser_attenuation_in_quiet_candidate_windows_db': float(np.median(reductions[quiet])),
        'denoiser_attenuation_comparison_excludes_uniform_gain': True,
        'reading_cuts_or_retakes_selected': False,
        'silences_removed': False,
        'speech_synthesis_used': False, 'voice_time_stretch_used': False,
        'hard_gate_used': False, 'spectral_declick_or_declip_used': False,
        'audio_listening_performed': False,
        'limitations': [
            'Stationary low-level background is attenuated conservatively. No claim of removing all external noises or voices overlapping speech.',
            'Short original near-full-scale samples cannot be reconstructed reliably by these filters.',
            'Metrics and waveform/source alignment checks do not replace human listening.',
            'Background events during unused speech gaps should be removed during the edit, not by gating every quiet syllable.',
        ],
    }
    MANIFEST.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': meta['status'], 'clean_path': meta['clean_path'],
                      'samples': n, 'duration': n / RATE, 'gain_db': meta['uniform_output_gain_db'],
                      'quiet_attenuation_db': meta['median_denoiser_attenuation_in_quiet_candidate_windows_db'],
                      'voice_attenuation_db': meta['median_denoiser_attenuation_in_voice_windows_db'],
                      'alignment_lags': [row['best_lag_samples'] for row in alignment]}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    main()
