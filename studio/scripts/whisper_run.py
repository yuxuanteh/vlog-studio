"""One Whisper pass on a clip or voice memo. Usage from code: out, lines = run(decode(path), prompt)."""
import subprocess

import numpy as np
from faster_whisper import WhisperModel

import vlog_env

_model = None


def decode(path):
    """16 kHz mono float via ffmpeg (faster-whisper's own decoder breaks with av>=19)."""
    pcm = subprocess.run([vlog_env.FFMPEG, "-v", "error", "-i", str(path), "-map", "0:a:0", "-ac", "1", "-ar", "16000",
                          "-f", "s16le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0


def run(audio, prompt=None):
    """-> ({duration, segments[words]}, readable lines)."""
    global _model
    if _model is None:
        _model = WhisperModel(str(vlog_env.WHISPER_MODEL), device=vlog_env.cfg("whisper", "device", "cpu"),
                              compute_type=vlog_env.cfg("whisper", "compute_type", "int8"))
    segs, info = _model.transcribe(audio, language=vlog_env.NARRATION[:2], word_timestamps=True, initial_prompt=prompt,
                                   vad_filter=True, vad_parameters={"min_silence_duration_ms": 300},
                                   condition_on_previous_text=False)
    out = {"duration": info.duration, "segments": []}
    lines = []
    for s in segs:
        out["segments"].append({"start": s.start, "end": s.end, "text": s.text.strip(),
                                "words": [{"start": w.start, "end": w.end, "word": w.word, "p": w.probability}
                                          for w in s.words]})
        lines.append(f"[{s.start:7.2f} -> {s.end:7.2f}] {s.text.strip()}")
    return out, lines
