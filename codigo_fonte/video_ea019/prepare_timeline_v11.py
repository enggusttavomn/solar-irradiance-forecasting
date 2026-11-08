"""Rebuild the V11 narration timeline with visual breathing room.

The V10 speech selections are immutable inputs: this module only relocates their
already edited PCM and caption cues. It neither stretches speech nor reselects
takes. The external pacing plan supplies integer output frames and integer-frame
audio lead-ins. Every body animation must retain at least its native duration.
"""
from __future__ import annotations

from array import array
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
import wave

import prepare_timeline_v10 as captions_v10
from montagem_v10_common import ROOT, read, sha, write


OUT = ROOT / "documentacao/relatorio_final_ea019/video/montagem_final_v11"
TMP = ROOT / "tmp/montagem_final_v11"
PREVIOUS = ROOT / "documentacao/relatorio_final_ea019/video/montagem_final_v10"
PLAN = TMP / "plano_ritmo_v11.json"
TIMELINE = OUT / "timeline_montagem_v11.json"
VOICE = OUT / "audio/voz_montada_v11.wav"
SRT = OUT / "Legendas_Finais_v11.srt"
ASS = OUT / "Legendas_Finais_v11.ass"
REPORT = OUT / "relatorio_ritmo_v11.json"
RATE = 48000
FPS = 30
SPF = RATE // FPS
FADE_SAMPLES = 240


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def absolute(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def load_pcm(path: Path) -> array:
    with wave.open(str(path), "rb") as handle:
        assert (handle.getframerate(), handle.getnchannels(), handle.getsampwidth()) == (RATE, 1, 2)
        return array("h", handle.readframes(handle.getnframes()))


def integer(value, description: str) -> int:
    result = int(value)
    if result != value:
        raise ValueError(f"{description} must be an integer: {value!r}")
    return result


def main() -> None:
    plan = read(PLAN)
    if plan is None:
        raise SystemExit(f"Waiting for the reviewed visual pacing plan: {PLAN}")

    previous_path = PREVIOUS / "timeline_montagem_v10.json"
    previous_report_path = PREVIOUS / "relatorio_edicao_v10.json"
    previous = read(previous_path)
    previous_report = read(previous_report_path)
    previous_voice_path = absolute(previous["audio_path"])
    protected_inputs = [previous_path, previous_report_path, previous_voice_path,
                        absolute(previous["srt_path"]), absolute(previous["ass_path"])]
    input_hashes = {relative(path): sha(path) for path in protected_inputs}

    assert previous["fps"] == FPS and previous["sample_rate"] == RATE
    assert len(previous["items"]) == 90
    assert [item["index"] for item in previous["items"] if item["kind"] == "body"] == list(range(88))
    assert previous["voice_stretched"] is False and previous["speech_synthesis"] is False
    schedule_items = plan["items"]
    schedule = {entry["id"]: entry for entry in schedule_items}
    if len(schedule) != len(schedule_items):
        raise ValueError("The pacing plan contains duplicate item identifiers")
    if set(schedule) != {item["id"] for item in previous["items"]}:
        raise ValueError("The pacing plan must contain exactly the same 90 items as V10")

    items = []
    phase_rows = []
    cursor = 0
    for old in previous["items"]:
        choice = schedule[old["id"]]
        frames = integer(choice["frames"], f"frames for {old['id']}")
        offset_frames = integer(choice.get("audio_offset_frames", 0), f"audio offset for {old['id']}")
        if frames <= 0 or offset_frames < 0:
            raise ValueError(f"Invalid pacing values for {old['id']}")
        lead_samples = offset_frames * SPF
        clip_samples = integer(old["audio_samples"], f"audio samples for {old['id']}")
        target_samples = frames * SPF
        if lead_samples + clip_samples > target_samples:
            raise ValueError(f"Speech plus lead-in exceeds the scheduled duration: {old['id']}")
        native_frames = math.ceil((old["video_end"] - old["video_start"]) * FPS - 1e-6)
        if old["kind"] == "body" and frames < native_frames:
            raise ValueError(f"V11 must not accelerate body animations: {old['id']}")
        if old["kind"] in ("intro", "ending"):
            if frames != old["frames"] or offset_frames != 0:
                raise ValueError(f"Approved opening and ending timing must remain unchanged: {old['id']}")
        old_offset = round(float(old.get("audio_offset", 0)) * RATE)
        assert old_offset == 0, "This derivation expects the audited V10 clips to start at local sample zero"
        offset_seconds = offset_frames / FPS
        item = deepcopy(old)
        item.update({
            "frames": frames,
            "duration": frames / FPS,
            "start_frame": cursor,
            "end_frame": cursor + frames,
            "start": cursor / FPS,
            "end": (cursor + frames) / FPS,
            "audio_offset": offset_seconds,
            "audio_offset_frames": offset_frames,
            "audio_offset_samples": lead_samples,
            "lead_silence_samples": lead_samples,
            "tail_silence_samples": target_samples - lead_samples - clip_samples,
            "pad_samples": target_samples - clip_samples,
            "previous_v10_start": old["start"],
            "previous_v10_duration": old["duration"],
            "visual_playback_speed": 1.0,
            "visual_source_frames": native_frames if old["kind"] != "ending" else None,
            "visual_tail_hold_frames": max(0, frames - native_frames) if old["kind"] != "ending" else 0,
            "pacing_note": choice.get("reason", choice.get("note", "Original visual duration retained")),
            "pacing_plan": deepcopy(choice),
        })
        item["cues"] = [dict(cue, start=round(cue["start"] + offset_seconds, 6),
                             end=round(cue["end"] + offset_seconds, 6)) for cue in old["cues"]]
        for cue in item["cues"]:
            assert 0 <= cue["start"] < cue["end"] <= item["duration"] + 1e-5, (item["id"], cue)
        items.append(item)
        phase_rows.append({
            "id": item["id"], "index": item["index"], "kind": item["kind"],
            "source_animation_seconds": native_frames / FPS if item["kind"] != "ending" else None,
            "v10_output_seconds": old["duration"], "v11_output_seconds": item["duration"],
            "voice_clip_seconds": clip_samples / RATE,
            "lead_silence_seconds": lead_samples / RATE,
            "tail_silence_seconds": item["tail_silence_samples"] / RATE,
            "visual_tail_hold_seconds": item["visual_tail_hold_frames"] / FPS,
            "playback_speed": 1.0, "reason": item["pacing_note"],
        })
        cursor += frames

    assert sum(len(item["cues"]) for item in items) == 130
    assert all(a["end_frame"] == b["start_frame"] for a, b in zip(items, items[1:]))
    assert cursor / FPS <= 600, "The full video must remain within the assignment's ten-minute limit"
    old_pcm = load_pcm(previous_voice_path)
    assert len(old_pcm) == previous["samples"]
    source_pcm = {path: load_pcm(absolute(path)) for path in {item["audio_source"] for item in items}}

    OUT.mkdir(parents=True, exist_ok=True)
    VOICE.parent.mkdir(parents=True, exist_ok=True)
    temporary_voice = VOICE.with_suffix(".wav.tmp")
    with wave.open(str(temporary_voice), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(RATE)
        for old, item in zip(previous["items"], items):
            origin = old["start_frame"] * SPF
            clip = old_pcm[origin:origin + old["audio_samples"]]
            assert len(clip) == item["audio_samples"]
            output.writeframesraw(b"\0\0" * item["lead_silence_samples"])
            output.writeframesraw(clip.tobytes())
            output.writeframesraw(b"\0\0" * item["tail_silence_samples"])
    with wave.open(str(temporary_voice), "rb") as check:
        assert check.getnframes() == cursor * SPF
    temporary_voice.replace(VOICE)

    assembled = load_pcm(VOICE)
    pcm_checks = []
    for old, item in zip(previous["items"], items):
        start = item["start_frame"] * SPF
        end = item["end_frame"] * SPF
        speech_start = start + item["lead_silence_samples"]
        speech_end = speech_start + item["audio_samples"]
        old_start = old["start_frame"] * SPF
        old_clip = old_pcm[old_start:old_start + old["audio_samples"]]
        actual_clip = assembled[speech_start:speech_end]
        exact_previous = actual_clip == old_clip
        pcm = source_pcm[item["audio_source"]]
        original_clip = pcm[item["audio_start_sample"]:item["audio_end_sample"]]
        interior_exact = actual_clip[FADE_SAMPLES:-FADE_SAMPLES] == original_clip[FADE_SAMPLES:-FADE_SAMPLES]
        fade = min(FADE_SAMPLES, len(original_clip) // 2)
        for index in range(fade):
            gain = index / max(1, fade - 1)
            original_clip[index] = round(original_clip[index] * gain)
            original_clip[-1 - index] = round(original_clip[-1 - index] * gain)
        exact_ramps = actual_clip == original_clip
        lead_zero = not any(assembled[start:speech_start])
        tail_zero = not any(assembled[speech_end:end])
        assert exact_previous and interior_exact and exact_ramps and lead_zero and tail_zero, item["id"]
        pcm_checks.append({"id": item["id"], "v10_edited_clip_exact": exact_previous,
                           "normalized_source_interior_exact": interior_exact,
                           "five_ms_endpoint_ramps_exact": exact_ramps,
                           "lead_padding_zero": lead_zero, "tail_padding_zero": tail_zero})
    assert len(assembled) == cursor * SPF

    original_srt, original_ass = captions_v10.SRT, captions_v10.ASS
    try:
        captions_v10.SRT, captions_v10.ASS = SRT, ASS
        captions_report = captions_v10.write_captions(items)
    finally:
        captions_v10.SRT, captions_v10.ASS = original_srt, original_ass
    ass_content = ASS.read_text(encoding="utf-8-sig").replace(
        "Title: EA019 final recorded narration V10", "Title: EA019 recorded narration with visual pauses V11")
    ASS.write_text(ass_content, encoding="utf-8-sig")

    timeline = deepcopy(previous)
    timeline.update({
        "version": 11, "status": "ready_for_encoding",
        "frames": cursor, "samples": cursor * SPF, "duration": cursor / FPS,
        "audio_path": relative(VOICE), "srt_path": relative(SRT), "ass_path": relative(ASS),
        "items": items, "voice_stretched": False, "speech_synthesis": False,
        "body_animations_accelerated": False,
        "pacing_plan_path": relative(PLAN), "pacing_plan_sha256": sha(PLAN),
        "previous_timeline_path": relative(previous_path),
        "previous_timeline_sha256": input_hashes[relative(previous_path)],
        "editing": dict(previous["editing"], visual_pauses_restored=True,
                        body_animation_playback_speed=1.0, audio_offsets_in_integer_frames=True,
                        retained_source_cuts_and_retake_selections=True),
    })
    write(TIMELINE, timeline)
    assert {relative(path): sha(path) for path in protected_inputs} == input_hashes
    report = {
        "version": 11, "status": "ready_for_encoding",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "PCM, source-selection, caption and timeline checks; no listening or realtime playback claimed.",
        "duration_seconds": cursor / FPS, "frames": cursor, "samples": cursor * SPF,
        "fps": FPS, "sample_rate": RATE, "items": len(items), "body_phases": 88,
        "body_original_visual_seconds": sum(row["source_animation_seconds"] for row in phase_rows if row["kind"] == "body"),
        "body_output_seconds": sum(item["duration"] for item in items if item["kind"] == "body"),
        "body_animation_playback_speed": 1.0,
        "body_animations_accelerated": False,
        "original_body_intervals_retained": True,
        "within_ten_minute_assignment_limit": cursor / FPS <= 600,
        "voice_speed_changed": False, "voice_synthesis_used": False,
        "same_90_voice_clips_as_v10": True, "same_130_caption_texts_as_v10": True,
        "retakes": deepcopy(previous_report["retakes"]),
        "numeric_omissions": deepcopy(previous_report["numeric_omissions"]),
        "intro_timing_preserved": True, "ending_timing_preserved": True,
        "total_lead_silence_seconds": sum(item["lead_silence_samples"] for item in items) / RATE,
        "total_tail_silence_seconds": sum(item["tail_silence_samples"] for item in items) / RATE,
        "total_voice_clip_seconds": sum(item["audio_samples"] for item in items) / RATE,
        "frame_sample_exact": True, "timeline_contiguous": True,
        "all_v10_edited_clips_exact": True,
        "all_normalized_source_interiors_exact": True,
        "all_endpoint_ramps_exact": True, "all_padding_zero": True,
        "captions": captions_report,
        "phase_durations": phase_rows, "pcm_checks": pcm_checks,
        "protected_v10_inputs_unchanged": input_hashes,
        "outputs": {relative(path): {"bytes": path.stat().st_size, "sha256": sha(path)}
                    for path in [TIMELINE, VOICE, SRT, ASS]},
        "audio_listening_performed": False, "full_realtime_playback_reviewed": False,
    }
    write(REPORT, report)
    print(f"V11_TIMELINE_READY: {len(items)} items, {cursor} frames, {cursor / FPS:.6f}s, "
          f"130 captions, unchanged voice, no accelerated body animations")


if __name__ == "__main__":
    main()
