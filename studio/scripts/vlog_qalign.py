"""Exact word times with Qwen3-ForcedAligner (picked by the pilot over Whisper and the MMS aligner).

Usage (with <studio>/.venv-align): python vlog_qalign.py <trip> <stem> [<stem> ...]
Reads  work/words/<stem>.json          Whisper words [start, end, text, p] (their text and order are kept: the sheet rows match on them)
Writes work/words/<stem>.aligned.json  same words, times from the aligner; vlog_build.py cuts on these
The recording is aligned in pieces of at most 25 s split at quiet moments; each piece gets the Whisper words whose middle
falls inside it. A word the aligner can't place keeps Whisper's time moved by its neighbours' shift.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch
from qwen_asr import Qwen3ForcedAligner

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env
import vlog_ff

FA = str(vlog_env.MODELS / "qwen3-forced-aligner")
SR = 16000


def pieces(x, words, most=25.0):
    """Cut points at quiet moments between words, so no piece is longer than `most` seconds."""
    cuts, s = [0.0], 0.0
    total = len(x) / SR
    gaps = [((a[1] + b[0]) / 2, b[0] - a[1]) for a, b in zip(words, words[1:])]
    while total - s > most:
        cand = [(g, w) for g, w in gaps if s + 8 <= g <= s + most]
        g = max(cand, key=lambda z: z[1])[0] if cand else s + most
        cuts.append(g)
        s = g
    cuts.append(total)
    return list(zip(cuts, cuts[1:]))


def main():
    trip = vlog_env.TRIPS / sys.argv[1]
    rows = json.loads((trip / "work" / "footage-index.json").read_text(encoding="utf-8"))
    files = {r.get("stem") or Path(r["file"]).stem: r["file"] for r in rows}     # as vlog_trip.clip_stem
    fa = Qwen3ForcedAligner.from_pretrained(FA, dtype=torch.float32, device_map="cpu")
    torch.set_num_threads(8)
    for stem in sys.argv[2:]:
        wf = trip / "work" / "words" / f"{stem}.json"
        out = wf.with_name(f"{stem}.aligned.json")
        words = json.loads(wf.read_text(encoding="utf-8"))
        src = Path(files[stem]) if Path(files[stem]).is_absolute() else trip / "raw" / files[stem]
        px = Path(str(src).replace(str(trip / "raw"), str(vlog_env.LOCAL / "trips" / trip.name / "proxy"))).with_suffix(".mp4")
        pcm = vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-i", str(px if px.exists() else src), "-map", "0:a:0", "-ac", "1", "-ar", str(SR),
                              "-f", "s16le", "-"], capture_output=True).stdout
        x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768
        new = [list(w) for w in words]
        for p0, p1 in pieces(x, words):
            ks = [k for k, w in enumerate(words) if p0 <= (w[0] + w[1]) / 2 < p1]
            text = "".join(words[k][2] for k in ks).strip()
            if not ks or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
                continue
            try:
                res = fa.align(audio=(x[int(p0 * SR):int(p1 * SR)], SR), text=text, language="Chinese")[0]
            except Exception as e:
                print(stem, "piece", p0, "not aligned:", e, flush=True)
                continue
            items = [(getattr(i, "text", ""), float(getattr(i, "start_time", 0)), float(getattr(i, "end_time", 0))) for i in getattr(res, "items", res)]
            # the aligner returns its own units (characters / English words): walk them along the Whisper words
            chars = []
            for t, s, e in items:
                cs = re.findall(r"[\u4e00-\u9fff]|[A-Za-z]+|\d", t) or [t]
                d = (e - s) / max(len(cs), 1)
                chars += [(c.lower(), p0 + s + n * d, p0 + s + (n + 1) * d) for n, c in enumerate(cs)]
            ci = 0
            for k in ks:
                cs = [c.lower() for c in re.findall(r"[\u4e00-\u9fff]|[A-Za-z]+|\d", words[k][2])]
                got = []
                for c in cs:
                    j = next((j for j in range(ci, min(ci + 4, len(chars))) if chars[j][0] == c), None)
                    if j is not None:
                        got.append(chars[j])
                        ci = j + 1
                if got:
                    new[k][0], new[k][1] = round(got[0][1], 3), round(got[-1][2], 3)
        shift = 0.0
        for k, w in enumerate(words):                     # unplaced words move with their neighbours
            if new[k][0] == w[0] and new[k][1] == w[1]:
                new[k][0], new[k][1] = round(w[0] + shift, 3), round(w[1] + shift, 3)
            else:
                shift = new[k][0] - w[0]
        for k in range(1, len(new)):
            if new[k][0] < new[k - 1][1] - 0.02:
                new[k][0] = new[k - 1][1]
                new[k][1] = max(new[k][1], new[k][0] + 0.03)
        out.write_text(json.dumps(new, ensure_ascii=False), encoding="utf-8")
        print(stem, len(new), "words aligned (Qwen)", flush=True)


if __name__ == "__main__":
    main()
