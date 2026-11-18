"""Licensed music tracks fitted to a video (programmed music sounded cheap; tracks from the YouTube
Audio Library, chosen by the director, logged in youtube/trips/music-used.md so none is used twice).

In an edit list:
    TRACKS = [(block, "Jomon Grove"), (31, "From Whence We Came")]
Each track plays from the start of its block to the start of the next track's block (the last one to the start of the
end card). Files: <trip>/music/<title> - <artist>.mp3.

How a track is fitted (so it starts, joins and ends like music, not like a cut):
- Beat tracking (librosa) gives the beats; bars are every 4 beats from the strongest phase; phrases every 4 bars.
- The track keeps its own start and its own ending. The ending is back-timed: it lands where the section ends.
- Too long: whole phrases are taken out of the middle, cutting at two bar lines of similar loudness, joined over half a
  beat. Too short: a middle stretch (whole phrases) is played twice.
- Between two tracks the first one's ending rings out under the second one's first bar.
- Each track is set to the same average level (-19 dBFS) as the old programmed music, so the build's ducking under the
  voice (MIX_DB) works unchanged.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

import vlog_env
import vlog_ff

SR = 48000
LOCAL = vlog_env.MUSIC                              # the music library ([paths] music_library in vlog.toml)
AUDIO_EXT = (".mp3", ".wav", ".m4a", ".flac", ".ogg")
TARGET_RMS_DB = -19.0


def file_for(title):
    hits = [p for p in LOCAL.glob("*") if p.suffix.lower() in AUDIO_EXT and (p.stem.lower().startswith(title.lower() + " - ") or p.stem.lower() == title.lower())]
    if not hits:
        raise SystemExit(f"music: no file for '{title}' in {LOCAL}")
    return hits[0]


def decode(path):
    pcm = vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.int16).reshape(-1, 2).astype(np.float32) / 32768


def analyse(title):
    """Beats, bars, phrases, loudness per bar and where the music really ends; cached next to the file."""
    path = file_for(title)
    cache = path.with_suffix(".json")
    if cache.exists() and cache.stat().st_mtime > path.stat().st_mtime:
        return json.loads(cache.read_text(encoding="utf-8"))
    import librosa
    y, sr = librosa.load(str(path), sr=22050, mono=True)
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
    beats = [float(b) for b in beats]
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    ot = librosa.times_like(onset, sr=sr)
    strength = [float(np.interp(b, ot, onset)) for b in beats]
    phase = max(range(4), key=lambda p: np.mean(strength[p::4]) if strength[p::4] else 0)
    bars = beats[phase::4]
    rms = librosa.feature.rms(y=y)[0]
    rt = librosa.times_like(rms, sr=sr)
    db = 20 * np.log10(rms + 1e-9)
    loud = float(np.percentile(db, 90))
    alive = rt[db > loud - 35]
    end = float(alive[-1]) if len(alive) else len(y) / sr
    bar_db = [float(np.mean(db[(rt >= a) & (rt < b)])) if np.any((rt >= a) & (rt < b)) else -90.0 for a, b in zip(bars, bars[1:] + [end])]
    d = dict(title=title, file=path.name, dur=len(y) / sr, tempo=float(np.atleast_1d(tempo)[0]), beats=beats, bars=bars,
             bar_db=bar_db, end=end, first=bars[0] if bars else 0.0)
    cache.write_text(json.dumps(d), encoding="utf-8")
    return d


def plan(a, length):
    """Pieces [(src_from, src_to)] of the track that make `length` seconds, keeping its start and its ending."""
    bars, bdb, end = a["bars"], a["bar_db"], a["end"]
    if end <= length + 0.5 or len(bars) < 12:
        if end >= length - 0.5:
            return [(max(0.0, end - length), end)]          # (almost) fits: start a little in, keep the ending
        # too short: play a middle stretch twice, from bar i back to bar j (i > j), whole phrases
        need = length - end
        best = None
        for i in range(8, len(bars) - 4):
            for j in range(4, i):
                if (i - j) % 4:
                    continue
                gain = bars[i] - bars[j]
                if gain <= 0:
                    continue
                rep = max(1, round(need / gain))
                err = abs(rep * gain - need) + 0.3 * abs(bdb[i] - bdb[j])
                if best is None or err < best[0]:
                    best = (err, i, j, rep)
        if best is None:
            return [(0.0, end)]
        _, i, j, rep = best
        return [(0.0, bars[i])] + [(bars[j], bars[i])] * (rep - 1) + [(bars[j], end)]
    if length < 40:                                          # a short section (a fast opening): the track's own start up to
        best = None                                          # bar i, then its last phrases from bar j; whole bars, phrases
        for i in range(0, len(bars) - 1):                    # preferred (Taking Flight's ending ran
            for j in range(i + 1, len(bars)):                # 33 s into a 15 s section)
                kept = bars[i] + (end - bars[j])
                if abs(kept - length) > (bars[1] - bars[0]):
                    continue
                err = abs(kept - length) + 0.4 * abs(bdb[i] - bdb[j]) + (0 if i % 4 == 0 else 1.5) +                     (0 if (len(bars) - j) % 4 == 0 else 1.5) + (0 if bars[i] >= 4 else 2.0)
                if best is None or err < best[0]:
                    best = (err, i, j)
        if best is not None:
            _, i, j = best
            return ([(0.0, bars[i])] if i > 0 else []) + [(bars[j], end)]
        # its ending is a long beatless outro that can't fit: from the first downbeat to a phrase end; the notes
        # ring on under the next track (render's tail), which eases in over them
        s0 = bars[0] if bars[0] > 4 else 0.0
        k = min((k for k in range(1, len(bars)) if bars[k] > s0), key=lambda k: abs(bars[k] - s0 - length) + (0 if k % 4 == 0 else 1.0))
        return [(s0, bars[k])]
    # too long: take out whole phrases from the middle; cut from bar i (keep before) to bar j (keep after)
    cut = end - length
    best = None
    lo, hi = len(bars) // 5, len(bars) * 4 // 5
    for i in range(max(4, lo), hi):
        for j in range(i + 1, len(bars) - 4):
            removed = bars[j] - bars[i]
            if removed > cut + 4 * (bars[1] - bars[0]):
                break
            err = abs(removed - cut) + 0.4 * abs(bdb[i] - bdb[j]) + (0 if (j - i) % 4 == 0 else 2.0)
            if best is None or err < best[0]:
                best = (err, i, j)
    if best is None:
        return [(end - length, end)]
    _, i, j = best
    pieces = [(0.0, bars[i]), (bars[j], end)]
    over = sum(q - p for p, q in pieces) - length
    if over > 0:                                            # a little long still: start that much into the intro
        pieces[0] = (min(over, bars[i] - 1.0), bars[i])
    return pieces


def montage_start(a):
    """Where in the track an opening montage starts: the first phrase where it is already at full energy."""
    bars, bdb = a["bars"], a["bar_db"]
    loud = float(np.median(bdb)) - 3
    s0 = next((bars[i] for i in range(0, len(bars), 4) if bdb[i] >= loud), 0.0)
    return 0.0 if s0 == bars[0] else s0


def on_the_beat(items, title):
    """The montage's cuts land on the beats of its track ("the length of clip should also match
    the beat of the music"). Each shot keeps about the length the edit list gave it; its end moves to the nearest beat
    (never closer than half a second to the cut before, never past the end of its clip). Returns the new total."""
    a = analyse(title)
    s0 = montage_start(a)
    beats = [x - s0 for x in a["beats"] if x - s0 > 0.3]
    if len(beats) < len(items):
        return sum(it["d"] for it in items)
    t = u = 0.0
    for it in items:
        t += it["d"]
        room = u + it.get("room", it["d"]) * 1.0
        ok = [x for x in beats if u + 0.5 <= x <= room] or [x for x in beats if x > u][:1] or [t]
        cut = min(ok, key=lambda x: abs(x - t))
        it["d"], u = cut - u, cut
    return u


def assemble(x, pieces):
    """Join the pieces of one track, each join over half a beat (equal power)."""
    out = np.zeros((0, 2), np.float32)
    xf = int(0.25 * SR)
    for p, q in pieces:
        seg = x[int(p * SR):int(q * SR)].copy()
        if len(out) and len(seg) > xf and len(out) > xf:
            t = np.linspace(0, np.pi / 2, xf)[:, None]
            out[-xf:] = out[-xf:] * np.cos(t) + seg[:xf] * np.sin(t)
            seg = seg[xf:]
        out = np.concatenate([out, seg])
    return out


def reverb_tail(x, n, rt60=3.0, gain_db=-4.0, hp=220.0):
    """Wet-only hall reverb of x (stereo), n samples long: decaying noise impulse, two decorrelated channels,
    bass rolled off; deterministic (fixed seed)."""
    from scipy.signal import fftconvolve, butter, sosfilt
    rng = np.random.default_rng(7)
    t = np.arange(int(rt60 * SR)) / SR
    env = np.exp(-6.9 * t / rt60)
    out = np.zeros((n, 2), np.float32)
    for c in range(2):
        ir = rng.standard_normal(len(t)) * env
        ir[: int(0.02 * SR)] *= np.linspace(0, 1, int(0.02 * SR))      # soft onset (a little pre-delay feel)
        w = fftconvolve(x[:, c], ir)[:n]
        out[:len(w), c] = w
    out = sosfilt(butter(2, hp, "highpass", fs=SR, output="sos"), out, axis=0).astype(np.float32)
    rms_x = np.sqrt(np.mean(x ** 2) + 1e-12)
    peak = np.sqrt(np.mean(out[: int(0.5 * SR)] ** 2) + 1e-12)
    out *= rms_x / peak * 10 ** (gain_db / 20)
    return out


def montage_audio(x, s0, dur):
    """The opening montage's music: exactly int(dur * SR) samples of x from s0, levelled, then its reverb tail.
    the piece was cut as x[int(s0*SR):int((s0+dur)*SR)], two roundings, so for some lengths it came out one
    sample longer than the tail's slot and the v03 render crashed (shapes (196801,2) vs (196800,2))."""
    body = int(dur * SR)
    i = int(s0 * SR)
    y = x[i:i + body].copy()
    if len(y) < body:                                    # a track shorter than the montage: silence after it
        y = np.concatenate([y, np.zeros((body - len(y), 2), np.float32)])
    rms = np.sqrt(np.mean(y ** 2) + 1e-12)
    y *= 10 ** (TARGET_RMS_DB / 20) / rms
    # the end dissolves into its own reverb (a plain fade sounded cut off; editors' usual
    # bridge between two different tracks is a reverb tail of the last note): the last 0.6 s is sent through a
    # ~3 s hall (RT60), bass rolled off so it doesn't clash, and the dry track fades out over 0.4 s under it
    y = np.concatenate([y, np.zeros((int(3.5 * SR), 2), np.float32)])
    src = y[body - int(0.6 * SR):body].copy()
    f = int(0.4 * SR)
    y[body - f:body] *= np.cos(np.linspace(0, np.pi / 2, f))[:, None] ** 2
    y[body:] = 0
    y[body - int(0.6 * SR):] += reverb_tail(src, len(y) - (body - int(0.6 * SR)))
    return y


def render(tracks, starts, end_at, total, report=None):
    """tracks: [(block, title)], starts: block start times; music runs until end_at (the end card), total = video length."""
    out = np.zeros((int(total * SR) + SR, 2), np.float32)
    secs = [(starts[t[0]], t[1], t[2] if len(t) > 2 else "") for t in tracks]
    for k, (t0, title, mode) in enumerate(secs):
        t1 = secs[k + 1][0] if k + 1 < len(secs) else end_at
        a = analyse(title)
        x = decode(file_for(title))
        if mode == "montage":                                # the opening montage: the track from a
            s0 = montage_start(a)                            # phrase start where it is already at full energy, only as long
            pieces = [(s0, s0 + t1 - t0)]
            y = montage_audio(x, s0, t1 - t0)
            i0 = int(t0 * SR)
            j = min(len(out), i0 + len(y))
            out[i0:j] += y[:j - i0]
            if report is not None:
                report.append(f"{title}: {t0:.1f}-{t1:.1f} s, montage from {s0:.1f} s of the track, ends in a 3 s reverb tail")
            continue
        if k > 0 and secs[k - 1][2] == "montage":            # after the montage: enter at the first phrase that already has
            bars, bdb = a["bars"], a["bar_db"]               # body (a near-silent ambient intro left a hole)
            i = next((i for i in range(0, len(bars), 4) if bdb[i] >= float(np.median(bdb)) - 6), 0)
            off = bars[i] if i else 0.0
            if off:
                x = x[int(off * SR):]
                a = dict(a, bars=[b - off for b in bars[i:]], bar_db=bdb[i:], end=a["end"] - off, dur=a["dur"] - off)
        pieces = plan(a, t1 - t0)
        y = assemble(x, pieces)
        e_ = pieces[-1][1]                                   # where the last piece stops in the track (its ending, or a phrase end)
        tail = x[int(e_ * SR):int(min(a["dur"], e_ + 4) * SR)]                   # the last chord's ring
        y = np.concatenate([y, tail])
        rms = np.sqrt(np.mean(y[:int((t1 - t0) * SR)] ** 2) + 1e-12)
        y *= 10 ** (TARGET_RMS_DB / 20) / rms
        i0 = int(t0 * SR)
        if k == 0 and t0 > 0.05:
            r = min(len(y), int(0.4 * SR))
            y[:r] *= np.linspace(0, 1, r)[:, None]
        elif k > 0:                                          # the next track eases in over 1 s while the last one rings out
            r = min(len(y), int(1.5 * SR))                   # (fast opening into a calm track, smoothly)
            y[:r] *= np.sin(np.linspace(0, np.pi / 2, r))[:, None] ** 2
        if k + 1 < len(secs):                                # the ring of this ending fades under the next track
            ring = len(y) - int((t1 - t0) * SR)
            if ring > 0:
                y[-ring:] *= np.linspace(1, 0, ring)[:, None]
        j = min(len(out), i0 + len(y))
        out[i0:j] += y[:j - i0]
        if report is not None:
            report.append(f"{title}: {t0:.1f}-{t1:.1f} s ({t1 - t0:.1f} s) from " +
                          ", ".join(f"{p:.1f}-{q:.1f}" for p, q in pieces) + f" of {a['dur']:.0f} s, ends at {a['end']:.1f}")
    return out[:int(total * SR)]


if __name__ == "__main__":
    import sys
    for t in sys.argv[1:]:
        a = analyse(t)
        print(f"{t}: {a['dur']:.1f} s, {a['tempo']:.0f} bpm, {len(a['bars'])} bars, music ends {a['end']:.1f} s")
