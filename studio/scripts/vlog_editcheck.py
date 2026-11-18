"""Check that the voice the build keeps is exactly what the director marked on the editing page / sheet.

Usage: python vlog_editcheck.py <trip> [<video id> ...]      (no ids: every sheet)

For every V block of the edit list it works out the build's keep ranges (vlog_build.voice_plan, same as the page plays)
and reports, with the video's sheet time:
  kept word not heard   a word the director did not cut whose middle falls outside what is kept
  cut word still heard  a word marked 〔〕 whose middle is still kept
  time cut still heard  a stretch cut by ear on the waveform that is still kept
  voice lost            0.15 s or more of voice that is dropped although no cut word, time cut or 〔〕 text the
                        Whisper words missed is next to it (a word end Whisper put too early, say)
Exit code 1 when anything is found.
"""
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vlog_editor as E   # noqa: E402


def inside(t, ranges, pad=0.0):
    return any(a - pad <= t <= b + pad for a, b in ranges)


def check(trip, vid, page=None):
    """page: the editing page's unsaved state {rows: [{cid, shown}], restore, cuts, keeps}; None = the saved files."""
    rows, _, vd = trip.rows(vid)
    if page:
        by = {r["cid"]: r["shown"] for r in page["rows"]}
        for r in rows:
            r["shown"] = by.get(r["cid"], r["shown"])
        vd = dict(restore=page.get("restore", []), cuts=page.get("cuts", []), keeps=page.get("keeps", []))
    blocks = trip.keep(vid, [dict(cid=r["cid"], raw=r["raw"], shown=r["shown"], auto=r["auto"]) for r in rows],
                       vd["restore"], vd["cuts"], vd["keeps"])
    snap = trip._snap
    out = []
    # which words the director cut, by the page's own rule (the build decides the same through removed_words)
    import vlog_build as VB
    for blk in blocks:
        v, ks = blk["voice"], blk["ranges"]
        when = next((r["when"] for r in rows if r["voice"] == v and r["words"] and blk["a"] - 0.5 <= r["words"][0]["s"] <= blk["b"]), "?")
        rws = [r for r in rows if r["voice"] == v and r["words"] and r["words"][0]["s"] < blk["b"] and r["words"][-1]["e"] > blk["a"]]
        # over the whole block, as the build does: the director moves words between rows and marks them there
        # Whisper's own pieces (要 apart from 我就), the words the build cuts by
        allw = trip._vb.words(v)
        toks = [w for w in allw if w[3] >= blk["a"] - 0.5 and (w[3] + w[4]) / 2 <= blk["b"] + 0.5]
        t0r = [(float(r["cid"].rsplit("@", 1)[1]), r["when"]) for r in rws]
        text = "".join(VB.norm_marks(r["shown"]) for r in rws)
        first = next((k for k, w in enumerate(toks) if abs(w[3] - t0r[0][0]) < 0.006), 0) if t0r else 0
        toks = toks[first:]
        want = len(re.sub(r"\s", "", "".join(r["raw"] for r in rws)))
        got, j = 0, 0
        while j < len(toks) and got < want:
            got += len(re.sub(r"\s", "", toks[j][2]))
            j += 1
        toks = toks[:j]
        gone = VB.removed_words(toks, None, text)
        whenof = lambda ws_: next((w for t_, w in reversed(t0r) if t_ <= ws_ + 0.006), t0r[0][1] if t0r else when)
        words = [(w[0], w[1], w[2], n in gone, whenof(w[3])) for n, w in enumerate(toks)
                 if blk["a"] - 0.05 <= (w[0] + w[1]) / 2 <= blk["b"] + 0.05]
        kps = [(c["from"], c["to"]) for c in vd["keeps"] if c["voice"] == v]
        tcs = [(c["from"], c["to"]) for c in vd["cuts"] if c["voice"] == v]
        def share(s, e, rs):                   # how much of [s, e] the ranges hold
            return sum(max(0.0, min(e, q) - max(s, p)) for p, q in rs) / (e - s)
        for s, e, t, g, w in words:
            if e - s < 0.06 or s < blk["a"] - 0.01 or e > blk["b"] + 0.01:
                continue                       # too short to judge, or cut in two by the edit list's own part edge
            if not g and share(s, e, tcs) < 0.5 and share(s, e, ks) < 0.4:
                out.append(f"{w}  {v}@{s:.2f}  kept word not heard: {t.strip()} (kept {share(s, e, ks):.0%})")
            if g and share(s, e, ks) > 0.6 and share(s, e, kps) < 0.5:
                out.append(f"{w}  {v}@{s:.2f}  cut word still heard: {t.strip()} (kept {share(s, e, ks):.0%})")
        for a, b in tcs:
            if a < blk["b"] and b > blk["a"]:
                for p, q in ks:
                    if min(b, q) - max(a, p) > 0.03:
                        out.append(f"{when}  {v}@{a:.2f}  time cut still heard: {a:.2f}-{b:.2f}")
        # voice that disappears with nothing marked: loud 20 ms frames between the first and last word, not kept,
        # not inside / next to a cut word, a time cut, or a gap where the text has 〔〕 words Whisper missed
        x16 = snap.samples(v)
        fr = 320
        a0, b0 = max(words[0][0], blk["a"]) if words else blk["a"], min(words[-1][1], blk["b"]) if words else blk["b"]
        seg = x16[int(a0 * 16000):int(b0 * 16000)]
        if len(seg) < fr * 4:
            continue
        rms = np.sqrt(np.mean(seg[:len(seg) // fr * fr].reshape(-1, fr) ** 2, axis=1))
        thr = 0.25 * float(np.percentile(rms, 90))
        excused = [(s - 0.35, e + 0.35) for s, e, t, g, w in words if g] + [(a - 0.1, b + 0.1) for a, b in tcs]
        excused += [(x[1], y[0]) for x, y in zip(words, words[1:]) if x[3]]   # after a cut word (unheard 〔就参加咯〕): meant to go
        for r in rws:                          # 〔〕 text the words don't hold: the gaps of that row may go
            text = VB.norm_marks(r["shown"])
            if "〔" in text:
                ws_ = r["words"]
                for x, y in zip(ws_, ws_[1:]):
                    if y["s"] - x["e"] > 0.15:
                        excused.append((x["e"], y["s"]))
        run = None
        for i, val in enumerate(rms):
            t = a0 + (i + 0.5) * fr / 16000
            lost = val > thr and not inside(t, ks) and not inside(t, excused)
            if lost and run is None:
                run = t
            if not lost and run is not None:
                if t - run >= 0.15:
                    near = next((w for w in words if w[0] - 0.5 <= run <= w[1] + 0.5), None)
                    out.append(f"{near[4] if near else when}  {v}@{run:.2f}  voice lost: {run:.2f}-{t:.2f}"
                               f"{' (after ' + near[2].strip() + ')' if near else ''}")
                run = None
    return out


if __name__ == "__main__":
    trip = E.Trip(sys.argv[1])
    vids = [a for a in sys.argv[2:] if not a.startswith("--")] or trip.sheets()
    bad = 0
    for vid in vids:
        if not (trip.dir / "work" / "edl" / f"{vid}.py").exists():
            continue
        found = check(trip, vid)
        print(f"# {vid}: {len(found)} problem(s)")
        for f in found:
            print("  " + f)
        bad += len(found)
    sys.exit(1 if bad else 0)
