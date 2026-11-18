"""Per-shot colour correction (natural, realistic, consistent shot to shot).

Each clip is measured once over its whole length (8 frames, cached in <local>/grade/<stem>.json). The correction only
levels it: black point down to just above black, highlights opened up when they never reach white, and brightness
pulled part of the way toward the median of the clips shot at the same place, so neighbouring shots match. No colour
shift (casts are mostly the real light: sky, lanterns, wood), every step is clamped, then one gentle trip curve.
"""
import json
import subprocess
from pathlib import Path

import numpy as np

import vlog_env
import vlog_ff

LOOK = "eq=saturation=1.06,curves=all='0/0 0.25/0.225 0.5/0.5 0.75/0.775 1/1'"
VERSION = "g1"
_place_cache = {}


def measure(trip, stem):
    """Luma percentiles (1, 50, 99.7) of one clip, from 8 frames across it."""
    f = vlog_env.LOCAL / "grade" / f"{stem.replace(':', '_')}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    f.parent.mkdir(parents=True, exist_ok=True)
    path = str(trip.path(stem))
    if stem.startswith("P:"):
        cmd = [vlog_env.FFMPEG, "-v", "error", "-i", path, "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"]
    else:
        dur = float(vlog_ff.run([vlog_env.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                                   capture_output=True, text=True).stdout.strip() or 8)
        cmd = None
    if cmd:
        raw = vlog_ff.run(cmd, capture_output=True).stdout
    else:                                                     # 8 quick seeks instead of decoding the whole 4K clip
        raw = b"".join(vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-ss", f"{dur * (k + 0.5) / 8:.2f}", "-i", path, "-frames:v", "1",
                                       "-vf", "scale=160:90,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
                       for k in range(8))
    y = np.frombuffer(raw, np.uint8).astype(np.float32) / 255
    if not len(y):
        m = dict(p1=0.03, p50=0.42, p99=0.95)
    else:
        y = y.reshape(-1, 90, 160)[:, 9:72]                 # leave out the top strip and the subtitle band
        fr = [(np.percentile(a, 1), np.percentile(a, 50), np.percentile(a, 99.7)) for a in y if a.mean() > 0.03]
        fr = fr or [(0.03, 0.42, 0.95)]
        m = dict(zip(("p1", "p50", "p99"), map(float, np.median(np.array(fr), 0))))
    f.write_text(json.dumps(m), encoding="utf-8")
    return m


def place_median(trip, stem):
    """Median brightness of the clips in the same folder (same place, same light)."""
    folder = Path(str(trip.path(stem))).parent
    if folder not in _place_cache:
        stems = [p.stem for p in folder.iterdir() if p.suffix.upper() in (".MP4", ".MOV")][:40]
        vals = [measure(trip, s)["p50"] for s in stems if not s.startswith("P:")]
        _place_cache[folder] = float(np.median(vals)) if vals else 0.42
    return _place_cache[folder]


def grade_filter(trip, stem):
    m = measure(trip, stem)
    bp = float(np.clip(m["p1"] - 0.02, 0.0, 0.08))           # lifted blacks down, never crushed
    wp = float(np.clip(m["p99"] + 0.03, 0.88, 1.0))           # highlights opened a little at most
    mid = (m["p50"] - bp) / max(wp - bp, 0.3)
    try:
        target = 0.6 * place_median(trip, stem) + 0.4 * 0.44  # mostly the place's own light, a little toward the trip
    except Exception as e:                                    # said out loud, never silent (audit)
        print(f"grade note {stem}: the place's own light could not be measured ({type(e).__name__}: {e}); "
              f"using the trip default", flush=True)
        target = 0.44
    target = (target - bp) / max(wp - bp, 0.3)
    gamma = float(np.clip(np.log(max(target, 0.05)) / np.log(min(max(mid, 0.05), 0.95)), 0.85, 1.2))
    return (f"colorlevels=rimin={bp:.3f}:gimin={bp:.3f}:bimin={bp:.3f}:rimax={wp:.3f}:gimax={wp:.3f}:bimax={wp:.3f},"
            f"eq=gamma={1 / gamma:.3f},{LOOK}")


def check_version():
    """Plain pieces are keyed on VERSION (re-keying them all would throw the whole cache away). So if this file's code
    changes while VERSION stays, stop: the old graded pieces would be reused with the new grade's name on them."""
    import hashlib
    import json
    src = Path(__file__).read_text(encoding="utf-8")
    body = "\n".join(line for line in src.splitlines() if not line.startswith("VERSION ="))
    h = hashlib.md5(body.encode()).hexdigest()[:12]
    f = vlog_env.LOCAL / "codever.json"
    seen = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    key = f"vlog_grade:{VERSION}"
    if seen.get(key, h) != h:
        raise SystemExit(f"STOP: vlog_grade.py changed but VERSION is still {VERSION!r}; bump VERSION so graded pieces re-render")
    seen[key] = h
    f.write_text(json.dumps(seen, indent=1), encoding="utf-8")
