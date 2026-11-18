"""Build a full vlog / site-video cut from an edit list, with final assets (originals, real music, real CG).

Usage: python vlog_build.py <trip> <edit id> [--check]
Reads   <trip>/work/edl/<id>.py   (W, H, VIDEO, BLOCKS, TRACKS, optional FIX, STEADY, MIX_REL)
        <trip>/work/subtitles/<id>.xlsx + <id>.voice.json  (the director's subtitle and voice edits; 〔〕 = cut that voice)
Writes  <trip>/videos/<video>/preview/<id>-phone.mp4    the checking copy (--phone); a final goes to publish/
        <trip>/videos/<video>/preview/<id>-voice.m4a    the voice track exactly as used (voice + site sound, no music)
        <trip>/work/subtitles/<id>.tsv                  every subtitle and narration line, for the director to edit
        <trip>/work/edl/<id>.cues.txt, <id>.report.txt  cue list and shot list for checks

Blocks
  V(voice, a, b, pics, ...)  the director's voice (recap, re-record or on-camera) from a to b seconds of that recording.
                             Cuts snap to word edges (work/words/<voice>.json); long pauses shrink; subtitles are timed
                             word by word. sync=True keeps every pause (on-camera: the picture is the same clip).
  N(text, pics, ...)         new narration, shown as text until recorded; timed at the director's 4 characters a second
  S(pics, ...)               pictures with their own site sound, no talk (gain=0.8)
  M(pics, ...)               montage on music only
  T(title, pics)             title moment: logo seal + title over the picture, music hit
  E(pics, next=...)          end card, 12 s: credits, "下一支", YouTube end-screen slots kept clear
Keyword options: cap= place tag (bottom-left), src= source note (top-right, from its word if src_at= is given),
  name=True name tag, fade="in"/"out"/"inout".
Pictures: "C0394@12+5" clip C0394 from 12 s for 5 s; "C0394@12=+5" the same, pinned: the start never slides to a calmer
  stretch (the director chose it); "P:DSC08630+5" photo; suffixes in this order:
  %0.3 vertical crop centre · *0.5 slow motion (half speed, site sound muted) · >412.3 start this picture when the voice
  reaches 412.3 s of its recording · ^ force / ~ skip stabilising · !fx drawn effect (vlog_fx.py).
  "SELF>27.0" in a V block = the voice's own clip at that moment (on-camera, lips in sync), for cutaways.
"""
import shutil
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env
import vlog_ff
import vlog_layout
import vlog_sheet
import vlog_trip


def tighten(snap, stem, a, b, longest=0.8, leave=0.2):
    """Ranges of a voice block to keep: long pauses come down to leave x 2 seconds."""
    x = snap.samples(stem)[int(a * 16000):int(b * 16000)]
    n = len(x) // 320
    if n < 10:
        return [(0.0, b - a)]
    r = np.sqrt(np.mean(x[:n * 320].reshape(n, 320) ** 2, axis=1))
    gate = np.sqrt(np.mean(r[r >= np.median(r)] ** 2)) * 0.1
    quiet, keep, start, i = r < gate, [], 0.0, 0
    while i < n:
        if quiet[i]:
            j = i
            while j < n and quiet[j]:
                j += 1
            if (j - i) * 0.02 >= longest:
                end = i * 0.02 + leave
                if end > start:
                    keep.append((start, end))
                start = j * 0.02 - leave
            i = j
        else:
            i += 1
    keep.append((start, b - a))
    return [(round(p, 3), round(q, 3)) for p, q in keep if q - p > 0.02]


def squeeze(cues, keep):
    """Move cue times from the source's time to the tightened time; cues in removed pauses are dropped."""
    out = []
    for s, e, text in cues:
        t0 = t1 = None
        lost = 0.0
        last = 0.0
        for p, q in keep:
            lost += p - last
            last = q
            if t0 is None and s < q:
                t0 = max(s, p) - lost
            if e > p:
                t1 = min(e, q) - lost
        if t0 is not None and t1 is not None and t1 > t0:
            out.append((t0, t1, text))
    return out


def clock(sec):
    h, m = int(sec // 3600), int(sec % 3600 // 60)
    return f"{h}:{m:02d}:{sec % 60:05.2f}"

SR = 48000
L = vlog_env.tr
C_ = vlog_env.CHANNEL
RATE = float(vlog_env.LANG.get("pace", 4.0 if vlog_env.CJK else 2.6))   # characters (or words) a second, for text not yet recorded
FONT_DIR = vlog_env.FONT_DIR
# the name tag, the end card and the credits: [channel] in vlog.toml (\\N = a new line on screen)
NAME_TAG = C_.get("name_tag") or "\\N".join(x for x in (C_.get("presenter", C_.get("name", "")), C_.get("presenter_title", "")) if x)
CREDITS = C_.get("credits", "")
END_HEAD = C_.get("end_head", L("Thanks for watching", "谢谢你看到这里"))
END_NEXT = C_.get("end_next", L("Watch another", "再看一支"))
# lines said to the editor, not to the viewer ("I filmed that, you can put it in"): cut by default. A trip lists its
# own in work/trip-settings.json "meta"; [language] meta in vlog.toml holds the ones that come back on every trip.
META = list(vlog_env.LANG.get("meta", []))


def _blk(kind, **kw):
    d = dict(kind=kind, voice=None, a=0.0, b=0.0, pics=[], text=None, cap=None, src=None, src_at=None, fade=None, gain=0.8,
             sync=False, name=False, title=None, next=None)
    d.update(kw)
    return d


def V(voice, a, b, pics, **kw):
    return _blk("V", voice=voice, a=a, b=b, pics=pics, **kw)


def N(text, pics, **kw):
    return _blk("N", text=text, pics=pics, **kw)


def S(pics, **kw):
    return _blk("S", pics=pics if isinstance(pics, list) else [pics], **kw)


def M(pics, **kw):
    return _blk("M", pics=pics, gain=0.0, **kw)


def T(title, pics, **kw):
    return _blk("T", title=title, pics=pics, gain=0.0, **kw)


def E(pics, **kw):
    return _blk("E", pics=pics, gain=0.3, **kw)


def units(text):
    """How long a text is on screen, in subtitle units: one Chinese / Japanese character = 1 (an English word in it
    1.5); in other languages a unit is about two letters, so the same line limits hold for every language."""
    if not vlog_env.CJK:
        return len(text.strip()) * 0.5
    return len(re.sub(r"[^\u4e00-\u9fff\u3040-\u30ff]", "", text)) + 1.5 * len(re.findall(r"[A-Za-z]+", text)) + 0.8 * len(re.findall(r"\d+", text))


class Trip:
    def __init__(self, name):
        self.dir = vlog_env.TRIPS / name
        rows = json.loads((self.dir / "work" / "footage-index.json").read_text(encoding="utf-8"))
        self.clips = vlog_trip.clip_table(rows)
        sc = json.loads((self.dir / "work" / "clip-scores.json").read_text(encoding="utf-8"))
        self.shake = {Path(k).stem: v.get("shake") or 0 for k, v in sc.items()}
        self.cache, self.words_cache = {}, {}
        self._local = {}                               # stem -> where its raw clip is read from (local copy or Drive)
        vlog_trip.teach_words(self.dir)

    def path(self, stem):
        if stem.startswith("P:"):
            roots = [self.dir / "raw"] + [vlog_env._path(p) for p in vlog_env.cfg("paths", "photo_libraries", [])]
            found = next((q for r in roots for q in r.rglob(f"{stem[2:]}.*")), None)
            if found is None:
                raise SystemExit(f"photo not found: {stem}")
            return found
        drive = self.dir / "raw" / self.clips[stem]["file"]
        if stem not in self._local:
            self._local[stem] = drive
            want = None
            for root in vlog_trip.mirrors(self.dir):
                cand = root / drive.name
                if cand.exists():
                    want = want if want is not None else drive.stat().st_size
                    if cand.stat().st_size == want:          # same name, same size: the same clip
                        self._local[stem] = cand
                        break
        return self._local[stem]

    def length(self, stem):
        return 1e6 if stem.startswith("P:") else self.clips[stem]["duration"]

    def audio(self, stem, start, dur):
        key = (stem, round(start, 3), round(dur, 3))
        if stem.startswith("P:"):
            return np.zeros(int(round(dur * SR)), np.float32)
        if key not in self.cache:
            pcm = vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", str(self.path(stem)),
                                  "-map", "0:a:0", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True).stdout
            x = np.frombuffer(pcm, np.int16).astype(np.float32) / 32768.0
            n = int(round(dur * SR))
            self.cache[key] = np.pad(x, (0, max(0, n - len(x))))[:n]
        return self.cache[key]

    def level_db(self, stem):
        x = self.audio(stem, 0, self.length(stem))
        n = len(x) // 24000
        r = np.sqrt(np.mean(x[:n * 24000].reshape(n, 24000) ** 2, axis=1)) + 1e-6
        loud = r[r >= np.median(r)]
        return float(-20 - 20 * np.log10(np.sqrt(np.mean(loud ** 2))))

    def words(self, stem):
        if stem not in self.words_cache:
            p = self.dir / "work" / "words" / f"{stem}.json"
            if not p.exists():
                raise SystemExit(f"no word times for {stem}: run whisper_run.py first")
            ws = json.loads(p.read_text(encoding="utf-8"))
            al = p.with_name(f"{stem}.aligned.json")
            ts = json.loads(al.read_text(encoding="utf-8")) if al.exists() else ws
            self.words_cache[stem] = [(float(a[0]), float(a[1]), w[2], float(w[0]), float(w[1])) for w, a in zip(ws, ts)]
        return self.words_cache[stem]


class Snap:
    def __init__(self, trip):
        self.trip, self.s = trip, {}

    def samples(self, stem):
        """The recording's sound at 16 kHz, for finding cuts. Kept on the local disk once worked out (the
        editing page's first "计算剪辑" took four minutes while Google Drive fetched a recap again; every check and
        build decoded every recording again too). The copy is named after the file's size and time, so a changed
        recording is decoded anew; the numbers are exactly the ones decoding gives."""
        if stem not in self.s:
            f = None
            if not stem.startswith("P:"):
                try:
                    st = self.trip.path(stem).stat()
                    f = vlog_env.LOCAL / "editor-cache" / "samples" / f"{self.trip.dir.name}-{stem}-{st.st_size}-{int(st.st_mtime)}.npy"
                except OSError:
                    f = None
            if f is not None and f.exists():
                self.s[stem] = np.load(f)
            else:
                self.s[stem] = self.trip.audio(stem, 0, self.trip.length(stem))[::3].copy()
                if f is not None:
                    f.parent.mkdir(parents=True, exist_ok=True)
                    tmp = f.with_suffix(".part.npy")
                    np.save(tmp, self.s[stem])
                    tmp.replace(f)
        return self.s[stem]


# ---------- pictures ----------
PIC = re.compile(r"([^@+!^~%*>=]+)(?:@([\d.]+))?(=?)(?:\+([\d.]+))?(?:%([\d.]+))?(?:\*([\d.]+))?(?:>([\d.]+))?([\^~]?)(?:!(\w+(?::[\d.]+)?))?$")   # !effect:seconds = an end effect that carries on from that second (4K pieces)


def parse_pic(p, voice=None):
    m = PIC.match(p)
    if not m:
        raise SystemExit(f"bad picture {p}")
    stem, anchor = m[1], float(m[7]) if m[7] else None
    start = float(m[2]) if m[2] else (anchor if stem == "SELF" and anchor is not None else 0.5)
    if stem == "SELF":
        stem = voice
    return dict(stem=stem, start=start, fixed=float(m[4]) if m[4] else None, cx=float(m[5]) if m[5] else 0.5,
                speed=float(m[6]) if m[6] else 1.0, anchor=anchor, stab=m[8], fx=m[9], pinned=bool(m[3]))


MIN_SHOT = 2.5


def share(trip, items, dur, minimum=MIN_SHOT):
    """minimum: the shortest a shot may be (talking blocks); 0 for a montage or a pause whose shots set their own length."""
    for it in items:
        it["room"] = (trip.length(it["stem"]) - it["start"] - 0.05) / it["speed"]
    # too many shots for the time: drop from the end, but only while the shots left can still fill it
    # (shots that all have a set length which fits the time stay: a 1.5 s QR shot + C0071 lost C0071)
    while minimum and len(items) > 1 and dur / len(items) < minimum and sum(it["room"] for it in items[:-1]) >= dur             and not (all(it["fixed"] for it in items[:-1]) and sum(it["fixed"] for it in items[:-1]) + minimum <= dur + 0.05):
        items = items[:-1]
    if not minimum:
        minimum = 0.0
    elif all(it["fixed"] for it in items):            # after dropping, someone must fill the time: the last shot stretches
        items[-1]["fixed"] = None
    fixed = [it for it in items if it["fixed"]]
    nfree = len(items) - len(fixed)
    need = sum(it["fixed"] for it in fixed) + minimum * nfree
    if fixed and minimum and need > dur:                           # shrink the fixed ones in proportion, never under the minimum
        extra = sum(max(0.0, it["fixed"] - minimum) for it in fixed)
        k = max(0.0, (dur - minimum * len(items)) / extra) if extra > 0 else 0.0
        for it in fixed:
            it["fixed"] = min(it["fixed"], minimum + max(0.0, it["fixed"] - minimum) * min(1.0, k))
    left, free = dur, []
    for it in items:
        if it["fixed"]:
            it["d"] = min(it["fixed"], it["room"])
            left -= it["d"]
        else:
            free.append(it)
    while free:
        each = max(left, 0) / len(free)
        short = [it for it in free if it["room"] < each]
        if not short:
            for it in free:
                it["d"] = each
            break
        for it in short:
            it["d"] = it["room"]
            left -= it["room"]
            free.remove(it)
    over = sum(it["d"] for it in items) - dur
    for it in reversed(items):
        if over <= 0.01:
            break
        cut = max(0.0, min(over, it["d"] - 0.8))
        it["d"] -= cut
        over -= cut
    return [it for it in items if it["d"] > 0.05]


def out_time(keep, a, T):
    """Output time (within the block) of source time T, given the kept ranges (relative to a)."""
    r, t = T - a, 0.0
    for p, q in keep:
        if r <= p:
            return t
        if r <= q:
            return t + r - p
        t += q - p
    return t


def plan_pictures(trip, b, dur, keep, i):
    items = [parse_pic(p, b["voice"]) for p in b["pics"]]
    mn = MIN_SHOT if b["kind"] == "V" else 0
    if not any(it["anchor"] is not None for it in items):
        res = share(trip, items, dur, mn)
    else:
        if items[0]["anchor"] is not None:
            items[0]["anchor"] = None
        if mn:                                         # a shot pinned to a word that would leave a sliver joins its neighbour
            last = 0.0
            anch = [it for it in items if it["anchor"] is not None]
            for k_, it in enumerate(anch):
                t_ = out_time(keep, b["a"], it["anchor"])
                nxt = out_time(keep, b["a"], anch[k_ + 1]["anchor"]) if k_ + 1 < len(anch) else dur
                if t_ - last < mn or nxt - t_ < mn:
                    it["anchor"] = None
                else:
                    last = t_
        cuts = [0.0] + [out_time(keep, b["a"], it["anchor"]) for it in items if it["anchor"] is not None] + [dur]
        groups, cur = [], []
        for it in items:
            if it["anchor"] is not None and cur:
                groups.append(cur)
                cur = []
            cur.append(it)
        groups.append(cur)
        res = []
        for g, (s, e) in zip(groups, zip(cuts, cuts[1:])):
            res += share(trip, g, e - s, mn)
    if b.get("sync"):
        res = follow_voice(res, keep, b)
    calm_starts(trip, res, b)
    got = sum(it["d"] for it in res)
    if got < dur - 0.05:
        raise SystemExit(f"block {i}: pictures {b['pics']} are {dur - got:.1f}s short of {dur:.1f}s (no freeze frames)")
    return res


_MOTION = {}


_LAST_END = {}


def calm_starts(trip, res, b):
    """A shot whose stretch of its clip holds violent shaking (work/motion, clip_motion.py) slides up to 3 s, to the
    calmest window that still fits (shots ran into shaking). The speaker's own clip, photos and
    drawn shots stay put."""
    for it in res:
        prev_end = _LAST_END.get(it["stem"])
        _LAST_END[it["stem"]] = it["start"] + it["d"] * it["speed"]
        if prev_end is not None and abs(it["start"] - prev_end) < 1.0:
            continue                                   # carries on the same take from the shot before: never slid
        if it.get("pinned") or it.get("self") or it["stem"] == b.get("voice") or it["stem"].startswith("P:") or (it["fx"] or "") not in (
                "", "toptight", "zoomin"):                 # an effect (QR blur, ticket, drawn shot) is tied to its exact frames
            continue
        if it["stem"] not in _MOTION:
            f = trip.dir / "work" / "motion" / f"{it['stem']}.json"
            _MOTION[it["stem"]] = json.loads(f.read_text(encoding="utf-8"))["shake"] if f.exists() else None
        sh = _MOTION[it["stem"]]
        if not sh:
            continue
        span = it["d"] * it["speed"]
        worst = lambda a: max(sh[int(a):max(int(a) + 1, int(a + span + 0.999))] or [0])
        if worst(it["start"]) < vlog_trip.limit(trip.dir, "shake_violent"):
            continue
        top = trip.length(it["stem"]) - span - 0.1
        cands = [it["start"] + k * 0.25 for k in range(-24, 25)]
        cands = [c for c in cands if 0 <= c <= top]
        if cands:
            best = min(cands, key=lambda c: (round(worst(c), 1), abs(c - it["start"])))
            if worst(best) < worst(it["start"]):
                it["start"] = best
                _LAST_END[it["stem"]] = it["start"] + it["d"] * it["speed"]


def follow_voice(res, keep, b):
    """In a sync block, a shot of the speaker (the voice's own clip) is cut where the voice is cut: each kept stretch of
    voice shows the picture from that same moment of the recording, so the lips stay in sync."""
    out, t = [], 0.0
    for it in res:
        if it["stem"] != b["voice"]:
            out.append(it)
            t += it["d"]
            continue
        o0, o1, tk = t, t + it["d"], 0.0
        for p, q in keep:
            r0, r1 = tk, tk + (q - p)
            lo, hi = max(o0, r0), min(o1, r1)
            if hi - lo > 0.02:
                out.append(dict(it, start=b["a"] + p + (lo - r0), d=hi - lo, fixed=None, anchor=None, self=True))
            tk = r1
        t = o1
    return no_flash(out)


FLASH = 1.0          # a shot this short that jumps to other picture is a flash (v01 1:01, 1:15)


def no_flash(out):
    """A piece of the speaker's own take shorter than FLASH: a neighbouring cutaway covers it (lips never shown out of
    sync), else the neighbouring piece of the same take runs over it. Order: cutaway before, cutaway after, own piece
    before, own piece after."""
    i = 0
    while i < len(out):
        it = out[i]
        if not it.get("self") or it["d"] >= FLASH or len(out) == 1:
            i += 1
            continue
        prv = out[i - 1] if i > 0 else None
        nxt = out[i + 1] if i + 1 < len(out) else None
        if prv is not None and not prv.get("self"):
            prv["d"] += it["d"]
        elif nxt is not None and not nxt.get("self") and nxt["start"] - it["d"] * nxt["speed"] >= 0:
            nxt["start"] -= it["d"] * nxt["speed"]
            nxt["d"] += it["d"]
        elif prv is not None:
            prv["d"] += it["d"]
        elif nxt is not None:
            nxt["start"] = max(0.0, nxt["start"] - it["d"])
            nxt["d"] += it["d"]
        else:
            i += 1
            continue
        out.pop(i)
    return out


import vlog_grade
GRADE = bool(vlog_env.cfg("look", "level_brightness", True))   # false = colours exactly as filmed
# pieces are keyed on everything that makes them (audit): the clip itself (size + time on disk), this
# function's own code, the effects / steadying / tracking code and the trip's fx.py - no hand-bumped numbers
import inspect
import cv2
import vlog_fx
import vlog_stab


def _raw_id(trip, stem):
    p = trip.path(stem)
    st = p.stat()
    return [st.st_size, int(st.st_mtime)]


def _plain(trip, it, W, H, fades, out, cwd, vidstab=False):
    """The shot at W x H: cropped, graded, slowed, faded; not steadied here (vlog_stab does that, same at every size),
    except vidstab=True: ffmpeg's vid.stab at this size, for a video approved with it (edit list STEADY = "vidstab")."""
    base = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}:x='(iw-{W})*{it['cx']}':y='(ih-{H})/2',setsar=1"
    src = ["-ss", f"{it['start']:.3f}", "-t", f"{it['d'] * it['speed']:.3f}", "-i", str(trip.path(it["stem"]))]
    vf = [base]
    if vidstab and not it["stem"].startswith("P:"):
        trf = out.with_suffix(".trf").name
        vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", *src, "-vf", f"{base},vidstabdetect=shakiness=5:accuracy=15:result={trf}",
                     "-an", "-f", "null", "-"], cwd=cwd, check=True)
        vf.append(f"vidstabtransform=input={trf}:smoothing=30:zoom=6:optzoom=0:relative=1:maxangle=0.02:interpol=bicubic")
    if it["stem"].startswith("P:"):
        src = ["-loop", "1", "-framerate", "30", "-t", f"{it['d']:.3f}", "-i", str(trip.path(it["stem"]))]
        vf = [f"scale={int(W * 1.08)}:{int(H * 1.08)}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}:x='(iw-{W})*t/{max(it['d'], 0.1):.3f}':y='(ih-{H})/2',setsar=1"]
    if GRADE:                                          # per-shot levels + the trip curve (vlog_grade.py)
        vf.append(vlog_grade.grade_filter(trip, it["stem"]))
    if it["speed"] != 1.0:
        vf.append(f"setpts=PTS/{it['speed']}")
    vf += ["fps=30", "format=yuv420p"]
    for kind, d in fades:
        st = 0 if kind == "in" else max(it["d"] - d, 0)
        vf.append(f"fade=t={kind}:st={st:.3f}:d={d}")
    vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", *src, "-vf", ",".join(vf), "-an", "-t", f"{it['d']:.3f}",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", str(out)], cwd=cwd, check=True)


def analysis(trip, it, W, H, fades, stab, fxname, fxarg):
    """Steadying and tracking for one shot, worked out ONCE on the analysis-size frames (vlog_layout "edit") and saved
    as fractions of the frame, so the phone copy and the 4K final get exactly the same result (the 4K final ran the QR tracker on 3840-wide frames and lost the code). Shared by every output size."""
    eW, eH = vlog_layout.frame("edit", W, H)
    key = hashlib.md5(json.dumps([it["stem"], it["start"], round(it["d"], 3), eW, eH, stab, fxname, fxarg, fades,
                                  it["cx"], it["speed"], GRADE and vlog_grade.VERSION, _raw_id(trip, it["stem"]),
                                  vlog_fx.code_hash(trip.dir), SEG_CODE]).encode()).hexdigest()[:14]
    f = vlog_env.LOCAL / "analysis" / trip.dir.name / f"{it['stem'].replace(':', '_')}-{key}.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".mp4")
    _plain(trip, it, eW, eH, fades, tmp, f.parent)
    fs = vlog_fx.frames(tmp)
    res = {"stab": None, "fx": None, "frames": len(fs)}
    if stab:
        corr, blind = vlog_stab.analyse(fs)
        if blind:
            print(f"steadying note {it['stem']}@{it['start']}: {len(blind)} of {len(fs)} steps not measurable (held still)", flush=True)
        res["stab"] = corr
        fs = [vlog_stab.apply(fr, c) for fr, c in zip(fs, corr)]
    if fxname:
        res["fx"] = vlog_fx.tracked(trip.dir)[fxname][0](fs, *([fxarg] if fxarg else []))
    tmp.unlink()
    f.write_text(json.dumps(res), encoding="utf-8")
    return res


def segment(trip, it, W, H, fades, work):
    """One picture piece (video only) at W x H, steadied, slowed and with its drawn effect. Shots that are steadied or
    carry a tracked effect are analysed once at the analysis size (analysis()) and drawn here at W x H from that."""
    fxname, _, fxarg = (it["fx"] or "").partition(":")
    is_tracked = fxname in vlog_fx.tracked(trip.dir)
    shake = trip.shake.get(it["stem"], 0)
    if is_tracked:                                     # steadied first when it shakes noticeably, then tracked
        stab = it["stab"] == "^" or (it["stab"] != "~" and shake > vlog_trip.limit(trip.dir, "shake_track_stab"))
    else:
        stab = it["stab"] == "^" or (it["stab"] != "~" and shake > vlog_trip.limit(trip.dir, "shake_stab"))
    if it.get("self"):
        stab = False                                   # walking selfie: natural sway looks better than steadying's wobble
    if it["speed"] != 1.0:
        stab = stab and it["stab"] == "^"
    if it["stem"].startswith("P:"):
        stab, is_tracked = False, False
    legacy = it.get("steady") == "vidstab"             # approved with the old steadying: kept exactly (v02)
    if legacy and is_tracked:
        stab = False                                   # as it was then: tracked shots were not steadied
    key = hashlib.md5(json.dumps([it["stem"], it["start"], round(it["d"], 3), W, H, stab, it["fx"] or "", fades, legacy,
                                  it["cx"], it["speed"], GRADE and vlog_grade.VERSION, _raw_id(trip, it["stem"]),
                                  vlog_fx.code_hash(trip.dir) if (it["fx"] or stab) else "", SEG_CODE]
                                 ).encode()).hexdigest()[:14]
    name = it["stem"].replace(":", "_")
    out = work / "seg" / f"{name}-{key}.mp4"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp, part = out.with_suffix(".raw.mp4"), out.with_suffix(".part.mp4")
    _plain(trip, it, W, H, fades, tmp, out.parent, vidstab=legacy and stab)
    if legacy:
        stab = False                                   # done by vid.stab above
    if stab or is_tracked:
        ana = analysis(trip, it, W, H, fades, stab, fxname if is_tracked else "", fxarg)
        draw = vlog_fx.tracked(trip.dir)[fxname][1] if is_tracked else None
        cap = cv2.VideoCapture(str(tmp))
        p = vlog_fx.writer(part, W, H)
        i = 0
        while True:                                    # one frame at a time: a 4K shot never sits whole in memory
            ok, fr = cap.read()
            if not ok:
                break
            if ana["stab"]:
                fr = vlog_stab.apply(fr, ana["stab"][min(i, len(ana["stab"]) - 1)])
            if draw is not None:
                fr = draw(fr, min(i, ana["frames"] - 1), ana["fx"], W, H, *([fxarg] if fxarg else []))
            p.stdin.write(fr.tobytes())
            i += 1
        cap.release()
        p.stdin.close()
        p.wait()
        if abs(i - ana["frames"]) > 1:
            raise SystemExit(f"{it['stem']}@{it['start']}: {i} frames at {W}x{H} but {ana['frames']} analysed")
        tmp.unlink()
    elif it["fx"]:
        vlog_fx.apply(it["fx"], tmp, part, W, H, trip.dir)
        tmp.unlink()
    else:
        tmp.replace(part)
    part.replace(out)
    return out


SEG_CODE = hashlib.md5("".join(inspect.getsource(f) for f in (_plain, analysis, segment)).encode()).hexdigest()[:10]


# ---------- words, subtitles, the director's edits ----------
def join(ws):
    """Words back into text: Whisper's English comes in pieces ("S", "ed", "iment"); a leading space starts a new word."""
    t = "".join(w[2] for w in ws)
    t = re.sub(r"(?<=[^\x00-\x7f])\s+|\s+(?=[^\x00-\x7f])", "", t)
    return re.sub(r"\s+", " ", t).strip()


def fixed_text(raw, fixes):
    t = raw.replace("，", ", ").replace(",", ", ").replace("  ", " ").strip()
    for w, r in fixes:
        t = t.replace(w, r)
    return t.strip(" ,")


def word_tokens(text):
    """The pieces a line may be broken between: Chinese words (jieba, taught each trip's names), else words and spaces."""
    if vlog_env.ZH:
        import jieba
        jieba.setLogLevel(60)
        return list(jieba.cut(text))
    return re.findall(r"\S+\s*|\s+", text)


_ZH = vlog_env.ZH
PARTICLE = re.compile(r"[了的呢吗啊吧嘛啦着]" if _ZH else r"(?!x)x")   # a subtitle never starts with one of these
# ... never ends on one of these, and likes to break before one of the linking words ([language] in vlog.toml)
DANGLING = tuple(vlog_env.LANG.get("dangling", ("所以", "然后", "因为", "但是", "可是", "这个", "那个", "一个", "而且") if _ZH else
                                    ("and", "but", "so", "because", "the", "a", "an", "to", "of")))
CONNECT = tuple(vlog_env.LANG.get("connect", ("所以", "然后", "但是", "可是", "因为", "就是", "结果", "而且", "不过", "那我", "那个", "后来", "当然", "虽然") if _ZH else
                                   ("and", "but", "so", "because", "then", "which", "when", "while", "although")))


def make_cues(ws, limit, starts=()):
    """Words into subtitle cues. Phrases end at pauses or punctuation (and at Whisper's sentence starts, when given); a
    phrase longer than the limit is split where the speaker paused longest, preferring a break before a linking word,
    never inside a word, and never leaving a scrap."""
    phrases, cur = [], []
    for w in ws:
        if cur and (w[0] - cur[-1][1] > 0.45 or re.search(r"(?:[,?!，。？！]|(?<!\d)\.)$", cur[-1][2].strip())
                    or any(abs(w[0] - s0) < 0.005 for s0 in starts)):
            phrases.append(cur)
            cur = []
        cur.append(w)
    if cur:
        phrases.append(cur)

    def split(p):
        if units(join(p)) <= limit or len(p) < 2:
            return [p]
        text = join(p)
        ok, n = set(), 0
        for tok in word_tokens(text):                         # never break inside a word
            n += len(tok)
            ok.add(n)
        best, score = None, -1e9
        for k in range(1, len(p)):
            if len(join(p[:k])) not in ok:
                continue
            left, right = units(join(p[:k])), units(join(p[k:]))
            if left < 4 or right < 4:
                continue
            gap = p[k][0] - p[k - 1][1]
            sc = gap * 20 + (3 if p[k][2].strip().startswith(CONNECT) else 0) - abs(left - right) / max(limit, 1) * 2
            if re.match(r"[A-Za-z]", p[k][2]) and not p[k][2].startswith(" "):
                sc -= 100                                     # inside an English word
            if left > limit + 4:
                sc -= 5
            if PARTICLE.match(p[k][2].strip()):
                sc -= 30
            if join(p[:k]).strip().endswith(DANGLING):
                sc -= 30
            if sc > score:
                best, score = k, sc
        if best is None:
            return [p]
        return split(p[:best]) + split(p[best:])

    cues = [c for p in phrases for c in split(p)]
    out = []
    for c in cues:                                            # scraps of 1-3 characters join a neighbour
        if out and (units(join(c)) < 4 or units(join(out[-1])) < 4) and units(join(out[-1] + c)) <= limit + 4:
            out[-1] = out[-1] + c
        else:
            out.append(c)
    for i in range(1, len(out)):                              # pauses can still leave one: move that word across the break
        if len(out[i]) > 1 and PARTICLE.fullmatch(out[i][0][2].strip()):
            out[i - 1].append(out[i].pop(0))
        if len(out[i - 1]) > 1 and out[i - 1][-1][2].strip() in DANGLING:
            out[i].insert(0, out[i - 1].pop())
    return out


class Edits(dict):
    """id -> (Whisper text, edited text) from every sheet; .own holds this video's own edited rows (and rows an earlier
    edit list dropped), the only ones allowed to follow their words into differently split rows."""
    own = {}
    ids = set()


def load_edits(trip, eid=None):
    """The director's edits from every sheet: id -> (Whisper text it was made on, edited text). A row counts as an edit
    only where the subtitle column differs from the automatic text (hidden last column)."""
    edits = Edits()
    edits.own = {}
    edits.ids = set()
    edits.sheet = {}                                     # every row of this video's sheet: id -> (Whisper text, subtitle)
    import vlog_sheet
    d = trip.dir / "work" / "subtitles" / f"{eid}.dropped.tsv"
    for line in (d.read_text(encoding="utf-8-sig").splitlines()[1:] if eid and d.exists() else []):
        c = line.split("\t")
        if len(c) >= 4 and c[1].strip():
            edits.own[c[1].strip()] = (c[2].strip(), c[3].strip())
    files = sorted((trip.dir / "work" / "subtitles").glob("*.tsv"), key=lambda f: f.stem == eid)   # own sheet last = wins
    own = set()
    for f in files:
        for c in vlog_sheet.rows_for_edits(f):          # the director edits the .xlsx; the .tsv is the machine copy
            if f.stem == eid and len(c) >= 2 and c[1].strip():
                own.add(c[1].strip())
                edits.ids.add(c[1].strip())
                if len(c) >= 4:
                    edits.sheet[c[1].strip()] = (c[2].strip(), c[3].strip())
                edits.pop(c[1].strip(), None)             # this video's sheet has the row: its own text decides
            if len(c) >= 6 and c[1].strip() and c[3].strip() != c[5].strip():
                edits[c[1].strip()] = (c[2].strip(), c[3].strip())
                if f.stem == eid:
                    edits.own[c[1].strip()] = (c[2].strip(), c[3].strip())
    return edits


def unheard_cuts(ws, edited):
    """Marked text Whisper never wrote down (it missed 就变成, say): where it sits between two words, so the gap can be cut.
    Returns (index of word before, index of word after, text)."""
    raw = join(ws)
    offs, pos = [], 0
    for w in ws:
        t = w[2].strip()
        i = raw.find(t, pos)
        offs.append((i, i + len(t)))
        pos = i + len(t)
    plain = edited.replace("〔", "").replace("〕", "")
    spans, k = [], 0
    for part in re.split(r"(〔[^〕]*〕)", edited):
        if part.startswith("〔"):
            spans.append((k, k + len(part) - 2))
            k += len(part) - 2
        else:
            k += len(part)
    out = []
    sm = difflib.SequenceMatcher(None, plain, raw, autojunk=False)
    for a0, a1 in spans:
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "delete" and i1 < a1 and i2 > a0 and min(i2, a1) - max(i1, a0) >= 2:
                before = max((n for n, (s0, e0) in enumerate(offs) if e0 <= j1), default=None)
                after = min((n for n, (s0, e0) in enumerate(offs) if s0 >= j1), default=None)
                if before is not None and after is not None:
                    out.append((before, after, plain[max(i1, a0):min(i2, a1)]))
    return out


def removed_words(cue_ws, shown_auto, edited):
    """Which words the 〔〕 marks remove. Map the edited text's bracketed spans back to words through the raw text."""
    raw = join(cue_ws)
    offs, pos = [], 0
    for w in cue_ws:
        t = w[2].strip()
        i = raw.find(t, pos)
        offs.append((i, i + len(t)))
        pos = i + len(t)
    plain = edited.replace("〔", "").replace("〕", "")
    gone_plain, k = [], 0
    for part in re.split(r"(〔[^〕]*〕)", edited):
        if part.startswith("〔"):
            gone_plain.append((k, k + len(part) - 2))
            k += len(part) - 2
        else:
            k += len(part)
    if not gone_plain:
        return set()
    sm = difflib.SequenceMatcher(None, plain, raw, autojunk=False)
    gone = set()
    for a0, a1 in gone_plain:
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ("equal", "replace") and i2 > a0 and i1 < a1:
                lo = j1 + max(0, a0 - i1) if tag == "equal" else j1
                hi = j1 + min(i2, a1) - i1 if tag == "equal" else j2
                for n, (s, e) in enumerate(offs):
                    if s < hi and e > lo:
                        gone.add(n)
    return gone


def runs(ns):
    out = []
    for n in ns:
        if out and n == out[-1][-1] + 1:
            out[-1].append(n)
        else:
            out.append([n])
    return out


# Music level per block kind (dB on the rendered score). Set from a reference: background about 9-12 dB under
# the voice while he talks, and near the voice level when nobody talks (ours was 20 dB and 12-21 dB under).
# music level against the voice's own speech level, in dB (music was as loud as the talk; the old
# fixed levels put a -19 dBFS track about 1 dB under a quiet voice). Under talk 18 dB down; between lines it fills in.
MIX_REL = {"V": -18.0, "N": -18.0, "S": -3.0, "M": -2.0, "T": -18.0, "E": -8.0}


def norm_marks(t):
    """The director's sheet marks: [..] means the same as 〔..〕 (cut that voice); (..) / （..） are notes to the editor."""
    t = t.replace("[", "〔").replace("]", "〕").replace("［", "〔").replace("］", "〕")
    t = re.sub(r"[（(][^）)]*[）)]", "", t)
    t = re.sub(r"[（(].*$", "", t)                  # a note left open: to the end of the line
    # brackets read the way the editing page reads them (vlog_selftest compares the two): a 〕 with no open 〔 is
    # dropped, a 〔 left open runs to the end of the row ("a（b〔c）d〕e" kept a stray 〕 here)
    out, depth = [], 0
    for ch in t:
        if ch == "〔":
            if depth:
                continue
            depth = 1
        elif ch == "〕":
            if not depth:
                continue
            depth = 0
        out.append(ch)
    t = "".join(out)
    if depth:
        t += "〕"
    return t


def retime(pieces, limit):
    """pieces: (kept words, subtitle text) per sheet row, in order. Every row, and every part of a row between the
    director's / or ／, is one subtitle, in the sheet's order: never joined to a neighbour, never split further
    ("fully follow the symbol and the line sequence"; ＋ joins are join_marks' job). The director
    may move words between rows, so each subtitle takes its time from the voice letter by letter: a / inside one
    Whisper word still splits there, and text with no voice of its own (typed in) shares the time of its place."""
    split = []
    for kw, t in pieces:
        for k, part in enumerate(re.split(r"[/／]", t)):
            split.append((kw if k == 0 else [], part.strip()))
    words = [w for kw, _ in split for w in kw]
    texts = [t for _, t in split]
    if not words:
        return []
    # one time span per character of the voice's own text
    raw, ct = "", []
    for w in words:
        t = re.sub(r"\s", "", w[2])
        n = max(len(t), 1)
        for j in range(len(t)):
            ct.append((w[0] + (w[1] - w[0]) * j / n, w[0] + (w[1] - w[0]) * (j + 1) / n))
        raw += t
    plain = "".join(re.sub(r"\s", "", t) for t in texts)
    sm = difflib.SequenceMatcher(None, plain, raw, autojunk=False)
    ops = sm.get_opcodes()

    def to_raw(i):
        for tag, i1, i2, j1, j2 in ops:
            if i1 <= i < i2 or (i == i2 == len(plain)):
                return j1 + (i - i1 if tag == "equal" else (j2 - j1) * (i - i1) // max(i2 - i1, 1))
        return len(raw)

    spans, k = [], 0
    for t in texts:
        n = len(re.sub(r"\s", "", t))
        lo, hi = to_raw(k), to_raw(k + n)
        k += n
        spans.append((lo, hi) if t else None)
    # voice letters no subtitle claimed (a cut the text does not show, a difflib gap) go to the subtitle before them,
    # so the screen is never empty while that voice plays
    own = [s_ for s_ in spans if s_]
    if own:                                          # letters before the first / after the last subtitle belong to them
        own[0] = (0, own[0][1])   # (a typed-over English phrase must not start late)
        own[-1] = (own[-1][0], len(raw))
    for i, s_ in enumerate(own[:-1]):
        nxt = own[i + 1]
        if s_[1] < nxt[0]:
            own[i] = (s_[0], nxt[0])
    out, m = [], 0
    for t, s_ in zip(texts, spans):
        if not t:
            continue
        lo, hi = own[m]
        m += 1
        if hi > lo:
            s0, e0 = ct[min(lo, len(ct) - 1)][0], ct[min(hi, len(ct)) - 1][1]
        else:                                        # typed text with no voice under it: a moment at its place
            x = ct[min(lo, len(ct) - 1)][0] if lo < len(ct) else ct[-1][1]
            s0, e0 = x, x + 0.6
        out.append((s0, e0, t))
    # the sheet order is the screen order: a typed line never overlaps the next one
    for i in range(len(out) - 1):
        if out[i][1] > out[i + 1][0]:
            out[i] = (out[i][0], max(out[i + 1][0], out[i][0] + 0.3), out[i][2])
    return out


def load_restores(trip, eid):
    """Words the director put back on the editing page (work/subtitles/<id>.voice.json): stretches of a recording, in
    Whisper times, that must be in the video although the edit list stops before them. Kept apart from the edit list, so
    a rewritten edit list still gets them."""
    f = trip.dir / "work" / "subtitles" / f"{eid}.voice.json"
    return json.loads(f.read_text(encoding="utf-8")).get("restore", []) if f.exists() else []


def load_timecuts(trip, eid, what="cuts"):
    """Sound the director cut by time on the editing page (a 嗯 Whisper never heard), or put back by ear (what="keeps":
    an edge that cut off a 城): recording seconds."""
    f = trip.dir / "work" / "subtitles" / f"{eid}.voice.json"
    return json.loads(f.read_text(encoding="utf-8")).get(what, []) if f.exists() else []


def apply_restores(b, restores):
    """A block that ends just before a put-back stretch runs on to its end."""
    b["_restores"] = restores
    for r in restores:
        if r["voice"] == b["voice"] and b["a"] <= r["from"] and -1.0 <= r["from"] - b["b"] <= 1.5 and r["to"] > b["b"]:
            b["b"] = r["to"] + 0.02
        if r["voice"] == b["voice"] and b["a"] <= r["from"] and r["to"] <= b["b"] + 0.05:
            r["_used"] = True


def parse_marks(t):
    """Subtitle text as chars with a cut flag: 〔..〕 / [..] = cut, (..) / （..） = a note kept with the text."""
    out, cut, note = [], False, False
    for ch in t:
        if not note and ch in "(（":
            note = True
        if note:
            out.append((ch, cut))
            if ch in ")）":
                note = False
            continue
        if ch in "〔[［":
            cut = True
        elif ch in "〕]］":
            cut = False
        else:
            out.append((ch, cut))
    return out


def serial_marks(chars):
    s, cut = "", False
    for ch, c in chars:
        if c != cut:
            s += "〔" if c else "〕"
            cut = c
        s += ch
    return s + ("〕" if cut else "")


def word_texts(allw, voice, edits, restores):
    """The director's text per word of one recording, from every edited sheet row and every put-back stretch with its
    own wording: word index -> chars. Lets an edit follow its words when the rows are split differently (words put
    back, a rewritten edit list)."""
    out = {}
    for cid, (raw_old, shown_old) in edits.items():
        m = re.fullmatch(r"(.+)@([\d.]+)", cid)
        if not m or m[1] != voice:
            continue
        k = next((i for i, w in enumerate(allw) if abs(w[3] - float(m[2])) < 0.006), None)
        if k is None:
            continue
        want, got, j = len(re.sub(r"\s", "", raw_old)), 0, k
        while j < len(allw) and got < want:
            got += len(re.sub(r"\s", "", allw[j][2]))
            j += 1
        if join(allw[k:j]) != raw_old:
            continue
        sh = parse_marks(shown_old)
        att = [[] for _ in raw_old]                       # shown chars hung on each raw char
        sm = difflib.SequenceMatcher(None, raw_old, "".join(ch for ch, _ in sh), autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for d in range(i2 - i1):
                    att[i1 + d].append(sh[j1 + d])
            elif tag in ("replace", "insert"):
                at = i1 if tag == "replace" or i1 == 0 else i1 - 1
                att[min(at, len(att) - 1)].extend(sh[j1:j2])
        pos = 0
        for n in range(k, j):
            t = allw[n][2].strip()
            i = raw_old.find(t, pos)
            if i < 0:
                break
            nxt = raw_old.find(allw[n + 1][2].strip(), i + len(t)) if n + 1 < j else len(raw_old)
            out[n] = [c for q in range(i, nxt if nxt >= 0 else i + len(t)) for c in att[q]]
            pos = i + len(t)
    for r in restores:
        if r["voice"] == voice and r.get("text") is not None:
            ks = [n for n, w in enumerate(allw) if r["from"] - 0.006 <= w[3] <= r["to"] + 0.006]
            for q, n in enumerate(ks):
                out[n] = parse_marks(r["text"]) if q == 0 else []
    return out


def sound_from(x16, t, step, around):
    """Where the sound that is going on at time t stops (step 1: forward) or began (step -1: backward), in seconds,
    reading 20 ms frames of the 16 kHz copy. Loud = above a quarter of the speech level near `around`."""
    fr = 320
    lo_, hi_ = int(max(around[0] - 1.5, 0) * 16000), int(min((around[1] + 1.5) * 16000, len(x16)))
    seg = x16[lo_:hi_]
    if len(seg) < fr * 4:
        return t
    rms = np.sqrt(np.mean(seg[:len(seg) // fr * fr].reshape(-1, fr) ** 2, axis=1))
    thr = 0.25 * float(np.percentile(rms, 90))
    i = int((t * 16000 - lo_) // fr)
    if step < 0:
        i -= 1
    last, quiet = i, 0                       # a dip under 0.12 s between syllables does not end the sound
    while 0 <= i < len(rms) and quiet < 6:
        if rms[i] > thr:
            last, quiet = i, 0
        else:
            quiet += 1
        i += step
    return (lo_ + (last + 1 if step > 0 else last) * fr) / 16000


def voice_plan(trip, snap, b, fixes, edits, limit):
    """Keep ranges (relative to the cut-in), duration and subtitle cues for a V block."""
    allw = trip.words(b["voice"])
    idx = [k for k, w in enumerate(allw) if w[3] >= b["a"] - 0.03 and (w[3] + w[4]) / 2 <= b["b"]]   # most of the word inside the range
    if not idx:
        raise SystemExit(f"{b['voice']} {b['a']}-{b['b']}: no words")
    ws = [allw[k] for k in idx]
    prev_end = allw[idx[0] - 1][1] if idx[0] > 0 else 0.0
    next_start = allw[idx[-1] + 1][0] if idx[-1] + 1 < len(allw) else ws[-1][1] + 1
    a = max(ws[0][0] - min(0.12, (ws[0][0] - prev_end) * 0.6), prev_end + 0.02 if idx[0] > 0 else 0)
    bb = min(ws[-1][1] + min(0.35, (next_start - ws[-1][1]) * 0.7), next_start - 0.02)    # Whisper ends words early
    x16 = snap.samples(b["voice"])

    def quietest(lo, hi):
        i0, i1 = int(max(lo, 0) * 16000), int(hi * 16000)
        if i1 - i0 < 480:
            return (lo + hi) / 2
        e = [np.mean(x16[i:i + 320] ** 2) for i in range(i0, i1 - 320, 80)]
        return (i0 + int(np.argmin(e)) * 80 + 160) / 16000

    if idx[0] > 0 and ws[0][0] - prev_end < 0.6:             # cut in the quietest moment before the first word
        a = quietest(max(prev_end - 0.08, ws[0][0] - 0.5), ws[0][0] + 0.03)
    if next_start - ws[-1][1] < 0.6:                         # and after the last word (Whisper ends words early)
        bb = quietest(ws[-1][1] - 0.02, min(next_start + 0.08, ws[-1][1] + 0.5))

    def edges(a, bb):
        """Whisper often ends the last word early (城, 亡 cut off) and starts the first late: the part runs on to where
        the sound of its last word stops, and back to where its first word's sound began."""
        x_ = sound_from(x16, ws[-1][1], 1, (ws[-1][0], ws[-1][1]))
        if x_ - ws[-1][1] < 0.8:
            bb = max(bb, min(x_ + 0.06, next_start - 0.02))
        y_ = sound_from(x16, ws[0][0], -1, (ws[0][0], ws[0][1]))
        if ws[0][0] - y_ < 0.5:
            a = min(a, max(y_ - 0.06, prev_end + 0.02 if idx[0] > 0 else 0))
        return a, bb

    a, bb = edges(a, bb)
    segs = []
    tf = trip.dir / "work" / "transcript" / f"{b['voice']}.txt"
    labels = "|".join(re.escape(x) for x in vlog_trip.take_labels(trip.dir))          # the trip's take-label words
    for line in tf.read_text(encoding="utf-8").splitlines() if tf.exists() else []:
        m_ = re.match(r"\[\s*([\d.]+) ->\s*([\d.]+)\] (.*)", line)
        if m_ and not re.fullmatch(r"\s*([A-Za-z]{1,2}\s*\d{1,2}" + (f"|{labels}" if labels else "") + r")\s*", m_[3]):
            segs.append((float(m_[1]), float(m_[2])))
    # words the word list missed but the transcript has (e.g. a 然后 at the start): trust the edit list's own cut point
    if any(abs(s0 - b["a"]) < 0.2 for s0, _ in segs) and b["a"] < a - 0.25:
        a = max(b["a"] - 0.05, prev_end + 0.02 if idx[0] > 0 else 0)
    if b["sync"]:
        a, bb = b["a"], b["b"]
        bb = edges(a, bb)[1] if ws[-1][1] > bb - 0.4 else bb    # the last word's sound is not cut off (死亡's 亡)
    cues, removals, sheet, pieces, rowinfo, goneidx = [], [], [], [], [], set()
    # the piece just before, from the same recording, already played up to here: start where it stopped, or the
    # overlap is heard twice (啦 twice at 12:11, one piece ran to 176.615 s and the next began at 176.48 s)
    pv = b.get("_prev")
    if pv and pv[0] == b["voice"] and pv[1] < a < pv[2]:
        a = pv[2]
    if not b["sync"]:
        # long pauses where neither the word list nor the transcript heard words (take labels like "X02", coughs): cut
        # the middle, leaving a natural 0.4 s pause
        marks = [(a, a)] + [(w[0], w[1]) for w in ws] + [(bb, bb)]
        for (p0, e0), (s1, _) in zip(marks, marks[1:]):
            lo, hi = e0 + 0.2, s1 - 0.2
            if e0 > a:                                   # Whisper ends words early: not into the end of 影响's 响
                lo = max(lo, sound_from(x16, e0, 1, (p0, e0)) + 0.1)
            if s1 < bb:
                hi = min(hi, sound_from(x16, s1, -1, (s1, s1 + 0.3)) - 0.1)
            if hi - lo > 0.2 and not any(min(hi, s2) - max(lo, s0) > 0.15 for s0, s2 in segs if not (s0 >= e0 - 0.05 and s2 <= e0 + 0.05)):
                removals.append((lo - a, hi - a))
    merged = []
    cues_w, k_ = [], 0
    starts = ()
    if not any(k_.startswith(b["voice"] + "@") for k_ in getattr(edits, "own", {})):   # nobody edited this recording's rows yet
        wf = trip.dir / "work" / "words" / f"{b['voice']}.txt"
        starts = [float(l_.split()[0]) for l_ in wf.read_text(encoding="utf-8").splitlines() if l_.strip()] if wf.exists() else ()
    sheet_at = sorted(float(i_.rsplit("@", 1)[1]) for i_ in getattr(edits, "ids", ()) if i_.rsplit("@", 1)[0] == b["voice"])
    sheet_at = [x for x in sheet_at if ws and ws[0][3] - 0.006 <= x <= ws[-1][3] + 0.006]
    if sheet_at:                                         # the director's sheet already has these rows: keep its split exactly
        groups, cur_ = [], []                            # (a re-split dropped their edits)
        raw_at = {round(float(i_.rsplit("@", 1)[1]), 2): r_[0] for i_, r_ in getattr(edits, "sheet", {}).items()
                  if i_.rsplit("@", 1)[0] == b["voice"]}
        done_at = set()
        for n_, w in enumerate(ws):
            x = next((x for x in sheet_at if abs(w[3] - x) < 0.006), None)
            # several words can share one start (我 说 我 all at 58.03): the row starts at the word that gives its text
            if x is not None and x not in done_at and re.sub(r"\s", "", join(ws[n_:])).startswith(re.sub(r"\s", "", raw_at.get(round(x, 2), ""))[:4]):
                done_at.add(x)
                if cur_:
                    groups.append(cur_)
                    cur_ = []
            cur_.append(w)
        groups.append(cur_)
        if not any(abs(groups[0][0][3] - x) < 0.006 for x in sheet_at):     # words before the first known row: split as usual
            head_ = groups.pop(0)
            for c in make_cues([(w[3], w[4], w[2]) for w in head_], limit, starts):
                cues_w.append(head_[k_:k_ + len(c)])
                k_ += len(c)
        cues_w += groups
    else:
        for c in make_cues([(w[3], w[4], w[2]) for w in ws], limit, starts):   # rows are split on Whisper's times (stable ids)
            cues_w.append(ws[k_:k_ + len(c)])
            k_ += len(c)
    for c in cues_w:                                     # join= in the edit list: keep one sentence in one subtitle
        if merged and not sheet_at and any(join(c).startswith(j) for j in b.get("join", ())):   # only before a sheet exists
            merged[-1] = merged[-1] + c
        else:
            merged.append(c)
    rows_ = []
    # the same for every block of one recording (it reads the whole sheet and the whole recording's words), so it is
    # worked out once per recording and run (it was half of the editing page's wait after each edit)
    memo = edits.__dict__.setdefault("_wt", {}) if isinstance(edits, Edits) else {}
    if b["voice"] not in memo:
        memo[b["voice"]] = word_texts(allw, b["voice"], getattr(edits, "own", {}), b.get("_restores", []))
    wtext = memo[b["voice"]]
    for c in merged:
        cid = f"{b['voice']}@{c[0][3]:.2f}"
        raw = join(c)
        auto = fixed_text(raw, fixes)
        note = ""
        for m_ in META + vlog_trip.meta(trip.dir):
            if m_ in auto:
                auto = auto.replace(m_, f"〔{m_}〕")
                note = L("said to the editor, cut by default", "跟剪辑讲的话，默认剪掉")
        e_ = edits.get(cid)
        if not (e_ and e_[0] == raw) and getattr(edits, "sheet", {}).get(cid, ("",))[0] == raw:
            e_ = edits.sheet[cid]                        # the row is in the sheet as it stands: its text decides, even unedited
        shown = e_[1] if e_ and e_[0] == raw else auto
        if not (e_ and e_[0] == raw):                    # split differently from when it was edited: the edit follows its words
            ks = [allw.index(w) for w in c]
            if any(k in wtext for k in ks):
                parts, run = [], []
                for k in ks:
                    if k in wtext:
                        if run:
                            parts += [(ch, False) for ch in fixed_text(join(run), fixes)]
                            run = []
                        parts += wtext[k]
                    else:
                        run.append(allw[k])
                if run:
                    parts += [(ch, False) for ch in fixed_text(join(run), fixes)]
                shown = serial_marks(parts)
                e_ = (raw, shown)
                if shown != auto:
                    note = L("the split changed; your earlier edit followed its words, please check", "分段变了，之前的修改已跟着字过来，请看一下")
        shown = norm_marks(shown)
        if e_ and e_[0] != raw:                          # an edit made on different words is not applied
            note = L("the split of this line changed; your earlier edit was not applied, please look again", "这句的分段变了，之前的修改没套用，请再看一次")
        rows_.append((cid, raw, auto, note, e_, shown, c))
    # which words to cut, worked out over the whole block: the director may move a word to the next row and mark it there
    blockw = [w for r_ in rows_ for w in r_[6]]
    gone_all = removed_words(blockw, None, "".join(r_[5] for r_ in rows_))
    for run in runs(sorted(gone_all)):
        w0, w1 = blockw[run[0]], blockw[run[-1]]
        k0, k1 = allw.index(w0), allw.index(w1)
        pe = allw[k0 - 1][1] if k0 > 0 else w0[0] - 0.3
        ns = allw[k1 + 1][0] if k1 + 1 < len(allw) else w1[1] + 0.3
        lo = quietest(min(pe, w0[0] - 0.06) - 0.04, w0[0] + 0.06)
        hi = quietest(w1[1] - 0.06, max(ns, w1[1] + 0.06) + 0.04)
        # the pause around it goes too (a 额 Whisper missed), a breath stays. But Whisper often ends a word too early
        # (seismometer at 318.6 s, still sounding until 319.3 s): sound that runs on straight from the kept word before,
        # or runs straight into the kept word after, belongs to that word and stays.
        if ns - w1[1] > 0.3:
            hi = max(hi, min(ns - 0.15, sound_from(x16, ns, -1, (pe, ns)) - 0.05))
        if w0[0] - pe > 0.3:
            lo = min(lo, max(pe + 0.15, sound_from(x16, pe, 1, (pe, ns)) + 0.05))
        # never past the middle of a kept word next to the cut: the quietest moment can sit inside an unstressed 的
        # (其实是蛮远的[就是说] lost its 的)
        if run[0] > 0:
            pw = blockw[run[0] - 1]
            lo = max(lo, (pw[0] + pw[1]) / 2 + 0.03)
        if run[-1] + 1 < len(blockw):
            nw = blockw[run[-1] + 1]
            hi = min(hi, (nw[0] + nw[1]) / 2 - 0.03)
        if hi - lo < 0.04:
            continue
        removals.append((lo - a, hi - a))
        goneidx.update(range(k0, k1 + 1))
    for tc in b.get("_timecuts", []):                  # cut by ear on the editing page: exactly where the director put it
        if tc["voice"] == b["voice"] and tc["to"] > a and tc["from"] < bb:
            removals.append((max(tc["from"], a) - a, min(tc["to"], bb) - a))
    for kb, ka, txt in unheard_cuts(blockw, "".join(r_[5] for r_ in rows_)):
        wb, wa = blockw[kb], blockw[ka]
        if wa[0] - wb[1] < 0.2 or kb in gone_all or ka in gone_all:
            continue                                   # no room for a missed word there
        if any(tc["voice"] == b["voice"] and tc["to"] > wb[1] and tc["from"] < wa[0] for tc in b.get("_timecuts", [])):
            continue                                   # the director cut it by ear there: exact, keeps the rest of the gap
        lo = quietest(wb[1] - 0.02, wb[1] + 0.12)
        hi = quietest(wa[0] - 0.12, wa[0] + 0.02)
        removals.append((lo - a, hi - a))
    off = 0
    for cid, raw, auto, note, e_, shown, c in rows_:
        gone = {n - off for n in gone_all if off <= n < off + len(c)}
        off += len(c)
        text = re.sub(r"〔[^〕]*〕", "", shown).strip(" ,")
        kept = [w for n, w in enumerate(c) if n not in gone]
        pieces.append((kept, text))
        cut_texts = [x for x in re.findall(r"〔([^〕]*)〕", shown) if x.strip()]
        span = (kept[0][0], kept[-1][1]) if kept else (c[0][0], c[-1][1])
        rowinfo.append(dict(cid=cid, kept=text, kept_raw=join(kept), cuts=cut_texts, s=span[0], e=span[1], all_cut=not kept,
                            kw=[(w[0], w[1], w[2]) for w in kept]))
        sheet.append((cid, raw, e_[1] if e_ and e_[0] == raw else auto, note, auto))
    cues = [(p - a, q - a, t) for p, q, t in retime(pieces, limit)]
    if b["sync"]:
        keep = [(0.0, bb - a)]
    else:
        keep = tighten(snap, b["voice"], a, bb, longest=0.7, leave=0.18)
    for lo, hi in sorted(removals):            # take out the cut words
        nk = []
        for p, q in keep:
            if hi <= p or lo >= q:
                nk.append((p, q))
            else:
                if lo > p:
                    nk.append((p, lo))
                if hi < q:
                    nk.append((hi, q))
        keep = [(p, q) for p, q in nk if q - p > 0.02]
    # a sliver left between two cuts that holds no kept word (0.1 s of a cut 它) is noise, not voice: drop it
    # (the wider leftover-sound rules were removed - they caused more problems than they solved)
    mids = [(w[0] + w[1]) / 2 - a for k, w in zip(idx, ws) if k not in goneidx]
    keep = [(p, q) for p, q in keep if q - p >= 0.12 or any(p <= m <= q for m in mids)]
    # sound the director put back by ear on the editing page (a 城 an edge cut off): kept whatever the rules above did
    ks_ = [k_ for k_ in b.get("_keeps", []) if k_["voice"] == b["voice"] and k_["to"] > a - 1.5 and k_["from"] < bb + 1.5]
    if ks_:
        a_old = a
        absk = sorted([(a + p, a + q) for p, q in keep] + [(k_["from"], k_["to"]) for k_ in ks_])
        a, bb = min(a, absk[0][0]), max(bb, max(t_ for _, t_ in absk))
        merged = []
        for f_, t_ in absk:
            if merged and f_ <= merged[-1][1] + 0.005:
                merged[-1] = (merged[-1][0], max(merged[-1][1], t_))
            else:
                merged.append((f_, t_))
        keep = [(f_ - a, t_ - a) for f_, t_ in merged]
        cues = [(p + a_old - a, q + a_old - a, t_) for p, q, t_ in cues]
    b["a"], b["b"] = a, bb
    dur = sum(q - p for p, q in keep)
    for r_ in rowinfo:
        r_["os"], r_["oe"] = out_time(keep, a, r_["s"]), out_time(keep, a, r_["e"])
        r_["kw"] = [(out_time(keep, a, w0), out_time(keep, a, w1), x) for w0, w1, x in r_["kw"]]
    return keep, dur, squeeze(cues, keep), sheet, rowinfo


def seen_text(t):
    """What a subtitle row puts on screen: no cut parts, no notes, no / splits, no ＋ joins, no spaces."""
    t = re.sub(r"〔[^〕]*〕", "", norm_marks(t))
    return re.sub(r"[\s/／＋+]", "", t)


def guard_sheet(trip, eid, rows, blocks, restores=()):
    """The director's sheet is final (never touch an edited subtitle). Every edited row of this
    video whose recording is still used must come out exactly as written: the same row with the same text, or, when
    the edit list splits it differently, the same words on screen. Anything else stops the build before any rendering,
    with a list in work/review/<id>.subtitle-guard.txt, so Claude asks the director first. --accept-subs overrides
    after the director has answered."""
    import vlog_sheet
    f = trip.dir / "work" / "subtitles" / f"{eid}.tsv"
    old = [c for c in (vlog_sheet.rows_for_edits(f) if f.exists() else []) if len(c) >= 6 and c[1].strip()]
    d = f.with_name(f"{eid}.dropped.tsv")
    old += [c for c in (line.split("\t") for line in (d.read_text(encoding="utf-8-sig").splitlines()[1:] if d.exists() else []))
            if len(c) >= 6 and c[1].strip()]
    new = {r[1]: r[3] for r in rows}
    screen = "".join(seen_text(r[3]) for r in rows)
    used = [(b["voice"], b["a"], b["b"]) for b in blocks if b.get("kind") == "V"]
    bad, moved = [], []
    for c in old:
        cid, raw, shown, auto = c[1].strip(), c[2].strip(), c[3].strip(), c[5].strip()
        if shown == auto or "@" not in cid:
            continue
        voice, t0 = cid.rsplit("@", 1)
        try:
            allw, t0 = trip.words(voice), float(t0)
        except (SystemExit, ValueError):
            continue
        k = next((i for i, w in enumerate(allw) if abs(w[3] - t0) < 0.006), None)
        if k is None:
            continue
        j, got = k, 0
        while j < len(allw) and got < len(re.sub(r"\s", "", raw)):
            got += len(re.sub(r"\s", "", allw[j][2]))
            j += 1
        t1 = allw[j - 1][4]
        if not any(v == voice and a < t1 and b_ > t0 for v, a, b_ in used):
            continue                                       # its recording left the edit list: reported as dropped
        plus = "".join(r_.get("text") or "" for r_ in restores if r_.get("after") == cid)   # words put back after this row
        if cid in new:
            if norm_marks(new[cid]) not in (norm_marks(shown), norm_marks(shown) + plus):
                if seen_text(shown) and seen_text(shown) in screen:      # its words now sit in a neighbouring row
                    moved.append((c[0], cid, shown))                    # (a block boundary through the row): same on screen
                else:
                    bad.append((c[0], cid, shown, new[cid]))
        elif seen_text(shown) and seen_text(shown) not in screen:
            bad.append((c[0], cid, shown, L("(the split changed: your wording is not shown in full)", "（分段变了，导演的字没有完整出现）")))
        else:
            moved.append((c[0], cid, shown))
    out = trip.dir / "work" / "review" / f"{eid}.subtitle-guard.txt"
    out.parent.mkdir(exist_ok=True)
    (out.parent / f"{eid}.rows-preview.tsv").write_text("".join(f"{clock(r[0])[2:10]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\n" for r in rows),
                                                        encoding="utf-8")       # what the sheet would become
    lines = [f"# {eid}: {len(bad)} edited subtitle(s) would change, {len(moved)} moved to differently split rows (text kept)"]
    lines += [f"CHANGED  {t}  {cid}\n  {L("yours", "导演")}: {a}\n  {L("now", "新的")}: {b_}" for t, cid, a, b_ in bad]
    lines += [f"moved    {t}  {cid}  {a}" for t, cid, a in moved]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if bad and "--accept-subs" not in sys.argv:
        print("\n".join(lines[:1 + 3 * min(len(bad), 10)]))
        raise SystemExit(f"STOP {eid}: the director's subtitles would change; ask the director first ({out.name})")
    if moved:
        print(lines[0])


def join_marks(events):
    """The director's ＋ (or +) in a subtitle: at the end, this subtitle and the next one show as one; at the start,
    it joins the one before. Works across recordings and rows, where words cannot be dragged over."""
    subs = sorted([e for e in events if e[0] in ("Sub", "Nar")], key=lambda e: e[1])
    rest = [e for e in events if e[0] not in ("Sub", "Nar")]
    out = []
    for e in subs:
        t = e[3]
        glue = bool(out) and (t.lstrip().startswith(("＋", "+")) or out[-1][3].rstrip().endswith(("＋", "+")))
        t = t.strip().strip("＋+").strip()
        if glue:
            p_ = out[-1]
            out[-1] = (p_[0], p_[1], max(p_[2], e[2]), p_[3].strip().strip("＋+").strip() + t)
        else:
            out.append((e[0], e[1], e[2], t if not e[3].rstrip().endswith(("＋", "+")) else t + "＋"))
    out = [(k, s_, e_, x.rstrip("＋+")) for k, s_, e_, x in out]
    return rest + out


def sub_audit(events, sheet, rows):
    """Two promises to the director, checked before anything renders:
    SUB ORDER: the subtitles on screen are their sheet's rows, each / part on its own, ＋ joins joined, in his order;
    SUB GAP: while a row's kept voice plays, a subtitle is on screen (no empty stretch after he drags words)."""
    def flat(x):
        return re.sub(r"[\s＋+]", "", x.replace(r"\N", ""))
    want = []
    for _, cid, raw, shown, note, auto in sheet:
        for part in re.split(r"[/／]", re.sub(r"〔[^〕]*〕", "", norm_marks(shown))):
            part = part.strip()
            if not re.sub(r"[\s＋+]", "", part):
                if part.strip().startswith(("＋", "+")) or part.strip().endswith(("＋", "+")):
                    want.append(part.strip())
                continue
            want.append(part)
    joined = []
    for x in want:
        if joined and (x.startswith(("＋", "+")) or joined[-1].endswith(("＋", "+"))):
            joined[-1] = joined[-1].rstrip("＋+") + x.lstrip("＋+")
        else:
            joined.append(x)
    want = [flat(x) for x in joined if flat(x)]
    subs = sorted([e for e in events if e[0] == "Sub"], key=lambda e: e[1])
    got = [flat(e[3]) for e in subs]
    out = []
    if want != got:
        sm = difflib.SequenceMatcher(None, want, got, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                at = clock(subs[min(j1, len(subs) - 1)][1])[2:10] if subs else "?"
                out.append(f"SUB ORDER near {at}: sheet {' | '.join(want[i1:i2]) or '-'}  screen {' | '.join(got[j1:j2]) or '-'}")
    bare = []                                          # kept words (as heard in the video) with no subtitle on screen
    for r in rows:
        for w0, w1, x in r.get("kw", []):
            if w1 - w0 < 0.05:
                continue
            cover = sum(max(0.0, min(e[2], w1) - max(e[1], w0)) for e in subs)
            if cover < (w1 - w0) * 0.5:
                if bare and w0 - bare[-1][1] < 0.6:
                    bare[-1] = (bare[-1][0], w1, bare[-1][2] + x)
                else:
                    bare.append((w0, w1, x))
    for w0, w1, x in bare:
        out.append(f"SUB GAP at {clock(w0)[2:10]}: {w1 - w0:.1f} s of voice ({x.replace(' ', '')[:20]}) with no subtitle")
    for line in out:
        print(line)
    return out


def write_sheet(trip, eid, rows):
    f = trip.dir / "work" / "subtitles" / f"{eid}.tsv"
    f.parent.mkdir(parents=True, exist_ok=True)
    import vlog_sheet
    # the director's sheet is the final voice and subtitles: an edit list that no longer holds an edited row must not
    # lose it silently. Keep those rows in <id>.dropped.tsv and say so.
    if f.exists():
        new = {r[1] for r in rows}
        heard = "".join(re.sub(r"\s", "", r[2]) for r in rows)     # an edit whose words are still in (split anew) is not gone
        gone = [c for c in vlog_sheet.rows_for_edits(f) if len(c) >= 6 and c[1].strip() and c[1].strip() not in new
                and c[3].strip() != c[5].strip() and re.sub(r"\s", "", c[2]) not in heard]
        if gone:
            d = f.with_name(f"{eid}.dropped.tsv")
            old = d.read_text(encoding="utf-8-sig").splitlines()[1:] if d.exists() else []
            keep = {line.split("\t")[1]: line for line in old if "\t" in line}
            keep.update({c[1]: "\t".join(c[:6]) for c in gone})
            d.write_text(chr(0xFEFF) + "\t".join(vlog_sheet.HEAD) + "\n" + "\n".join(keep.values()) + "\n",
                         encoding="utf-8")
            print(f"WARNING {eid}: {len(gone)} edited subtitle rows are not in this edit list any more (kept in {d.name}):")
            for c in gone[:12]:
                print(f"  {c[1]}  {c[3][:30]}")
    head = "\t".join(vlog_sheet.HEAD) + "\n"
    f.write_text(chr(0xFEFF) + head + "".join(f"{clock(t)[2:10]}\t{cid}\t{raw}\t{shown}\t{note}\t{auto}\n"
                                              for t, cid, raw, shown, note, auto in rows), encoding="utf-8")
    import vlog_sheet
    vlog_sheet.write_xlsx(f.with_suffix(".xlsx"), [[clock(t)[2:10], cid, raw, shown, note, auto] for t, cid, raw, shown, note, auto in rows])


def ass_text(s):
    return s.replace("{", "(").replace("}", ")").replace("\n", "\\N")


def wrap2(text, limit):
    """Vertical video: a long cue becomes two lines, broken near the middle between whole words."""
    if units(text) <= limit:
        return text
    ok, n = [], 0
    for tok in word_tokens(text):
        n += len(tok)
        ok.append(n)
    cand = [k for k in ok if 3 <= k <= len(text) - 3] or [len(text) // 2]
    mid = len(text) / 2
    best = min(cand, key=lambda k: abs(k - mid) - (2 if text[k - 1] in (",的了吗呢啊啦咯" if _ZH else ",;:") else 0))
    return text[:best].rstrip(" ,") + chr(92) + "N" + text[best:].lstrip(" ,")


# ---------- build ----------
def build(name, eid, check=False):
    if GRADE:
        vlog_grade.check_version()
    trip = Trip(name)
    env = {"V": V, "N": N, "S": S, "M": M, "T": T, "E": E}
    exec((trip.dir / "work" / "edl" / f"{eid}.py").read_text(encoding="utf-8"), env)
    phone = "--phone" in sys.argv                    # a small checking copy (phone is enough to check)
    # frame sizes live in vlog_layout (the final was 1920x1080 here but 4K everywhere else)
    W, H = vlog_layout.frame("phone" if phone else "final", env["W"], env["H"])
    # --rehearse (full debug): the whole run - every shot, effect, steadying, the sound, subtitles,
    # the final encode, the copies and clean-up - at a tiny size, writing ONLY into <local>/rehearse/<trip>/<id>-<mode>;
    # nothing in the trip folder, publish/, preview/ or send/ is touched. Analysis is shared with the real run.
    rehearse = "--rehearse" in sys.argv
    if rehearse:
        k = 320 / max(W, H)
        W, H = int(W * k) // 2 * 2, int(H * k) // 2 * 2
    vertical = H > W
    video = env.get("VIDEO", eid.split("-")[0])
    fixes = list(env.get("FIX", [])) + vlog_trip.fixes(trip.dir)
    edits = load_edits(trip, eid)
    restores = load_restores(trip, eid)
    timecuts = load_timecuts(trip, eid)
    keeps = load_timecuts(trip, eid, "keeps")
    for r_ in restores:
        r_["_used"] = False
    work = vlog_env.LOCAL / "render" / name / (eid + ("-phone" if phone else "")
                                               + (("-rehearse-phone" if phone else "-rehearse-final") if rehearse else ""))
    work.mkdir(parents=True, exist_ok=True)
    sandbox = vlog_env.LOCAL / "rehearse" / name / f"{eid}-{'phone' if phone else 'final'}" if rehearse else None
    if not check:                                      # one build per video at a time: two runs writing the same pieces
        lock = work / "build.lock"                     # broke v01-pilot
        if lock.exists():
            old = lock.read_text().strip()
            alive = old.isdigit() and vlog_env.pid_alive(int(old))
            if alive:
                sys.exit(f"STOP: {eid} is already being built (process {old}); not starting a second build")
        lock.write_text(str(os.getpid()))
        import atexit
        atexit.register(lambda: lock.unlink(missing_ok=True))
    snap = Snap(trip)
    limit = vlog_layout.sub_chars(W, H)
    t, events, report, segs, sheet, checkrows = 0.0, [], [], [], [], []
    voice_tl, site_tl, kinds, starts = [], [], [], []
    named = False
    carry = None                                         # a too-short piece borrowed the next piece's first shot
    for i, b in enumerate(env["BLOCKS"]):
        keep = None
        if b["kind"] == "V":
            apply_restores(b, restores)
            b["_timecuts"] = timecuts
            b["_keeps"] = keeps
            pb = env["BLOCKS"][i - 1] if i else None
            b["_prev"] = (pb["voice"], pb["a"], pb["b"]) if pb and pb["kind"] == "V" else None
            keep, dur, cues, rows, rinfo = voice_plan(trip, snap, b, fixes, edits, limit)
            for r_ in rinfo:
                checkrows.append(dict(r_, os=t + r_["os"], oe=t + r_["oe"], kw=[(t + p_, t + q_, x_) for p_, q_, x_ in r_["kw"]]))
        elif b["kind"] == "N":
            nid = "N:" + hashlib.md5(b["text"].encode()).hexdigest()[:8]
            b["orig_text"] = b["text"]
            b["text"] = edits.get(nid, ("", b["text"]))[1]
            dur = units(b["text"]) / RATE + 0.9
        elif b["kind"] == "E":
            dur = 10.0 if b.get("plain") else max(12.0, sum(parse_pic(p)["fixed"] or 0 for p in b["pics"]))
        else:
            dur = sum(parse_pic(p)["fixed"] or 0 for p in b["pics"])
        items = plan_pictures(trip, b, dur, keep or [(0.0, dur)], i)
        if b["kind"] == "M":                             # a montage with its own track: every cut on a beat of that track
            tr_ = next((x_ for x_ in env.get("TRACKS", []) if x_[0] == i and len(x_) > 2 and x_[2] == "montage"), None)
            if tr_ and env.get("MONTAGE_BEAT", True):
                import vlog_tracks
                dur = vlog_tracks.on_the_beat(items, tr_[1])
        for it_ in items:
            it_["steady"] = env.get("STEADY", "")
        if not items:
            raise SystemExit(f"block {i} ({b['kind']} {b.get('voice')} {b['a']}-{b['b']}) has no pictures: its kept voice is {dur:.2f}s")
        # a whole talking piece shorter than FLASH (v02 7:48: 「大垣城」 alone, C0417 for 0.59 s): it shows the
        # next piece's first shot, which then starts that much later, so the picture runs straight through the cut
        if carry:                                        # carry = (clip, where the borrowed shot stopped in it)
            if items[0]["stem"] == carry[0]:
                items[0]["start"] = carry[1]
            carry = None
        nb = env["BLOCKS"][i + 1] if i + 1 < len(env["BLOCKS"]) else None
        if b["kind"] == "V" and dur < FLASH and len(items) == 1 and nb is not None and nb["kind"] == "V" and nb["pics"] \
                and not b.get("sync") and items[0]["stem"] != parse_pic(nb["pics"][0], nb.get("voice"))["stem"]:
            first = parse_pic(nb["pics"][0], nb.get("voice"))
            if not first["stem"].startswith("P:") and first["stem"] != nb.get("voice"):
                items = [dict(items[0], stem=first["stem"], start=first["start"], cx=first["cx"], speed=first["speed"],
                              fx=first["fx"], stab=first["stab"], pinned=True)]
                carry = (first["stem"], first["start"] + dur * first["speed"])
        starts.append(t)
        n = int(round(dur * SR))
        if b.get("bed"):                                   # replace the shots' own sound (announcements etc.) with a quiet bed
            st_, at_ = b["bed"].split("@")
            items_bed = [dict(stem=st_, start=float(at_), d=sum(it["d"] for it in items), speed=1.0)]
        else:
            items_bed = items
        # a check run never mixes: skip reading every shot's site sound from Drive (v02's check took 15+ min on it)
        site = np.concatenate([trip.audio(it["stem"], it["start"], it["d"]) if it["speed"] == 1.0 and not check else np.zeros(int(round(it["d"] * SR)), np.float32)
                               for it in items_bed])[:n]
        site = np.pad(site, (0, n - len(site)))
        r = min(int(0.03 * SR), n // 2)
        site[:r] *= np.linspace(0, 1, r)
        site[n - r:] *= np.linspace(1, 0, r)
        gain = 0.0 if b["sync"] else {"V": 0.14, "N": 0.45, "S": b["gain"], "M": 0.0, "T": 0.0, "E": 0.3}[b["kind"]]
        site_tl.append(site * gain)
        v = np.zeros(n, np.float32)
        if b["kind"] == "V":
            g = 10 ** (trip.level_db(b["voice"]) / 20)
            parts = []
            for p, q in keep:
                x = trip.audio(b["voice"], b["a"] + p, q - p).copy()
                rr = min(int(0.012 * SR), len(x) // 2)
                x[:rr] *= np.linspace(0, 1, rr)
                x[len(x) - rr:] *= np.linspace(1, 0, rr)
                parts.append(x)
            x = np.concatenate(parts)[:n]
            v[:len(x)] = x * g
            for s, e, x_ in cues:
                events.append(("Sub", t + s, t + max(e, s + 0.7), wrap2(x_, 13) if vertical else x_))
            for cid, raw, shown, note, auto in rows:
                tt = next((t + s for s, e, xx in cues if xx and xx in re.sub(r"〔[^〕]*〕", "", shown)), t)
                sheet.append((tt, cid, raw, shown, note, auto))
        elif b["kind"] == "N":
            for s, e, x_ in split_text(b["text"], 0.35, dur - 0.55, vlog_layout.sub_chars(W, H)):
                events.append(("Nar", t + s, t + e, wrap2(x_, 13) if vertical else x_))
            events.append(("Tag", t + 0.2, t + dur - 0.2, L("text narration · not recorded yet", "文字旁白 · 待录音")))
            sheet.append((t, nid, "（新旁白）", b["text"], L("new narration: change it freely before recording", "新旁白，录音前可以改"), b["orig_text"]))
        elif b["kind"] == "T":
            events.append(("Title", t + 0.6, t + dur - 0.2, b["title"]))
        elif b["kind"] == "E":
            if not b.get("plain"):                       # plain: black, nothing written (space for YouTube's end screen)
                events += end_card_events(t, dur, b.get("next"), W, H)
        voice_tl.append(v)
        kinds.append((t, t + dur, b["kind"]))
        if b["cap"]:
            events.append(("Cap", t + 0.4, t + min(dur, 3.4), b["cap"]))
        if b["src"]:
            s0 = out_time(keep, b["a"], b["src_at"]) if (b["src_at"] is not None and keep) else 0.4
            events.append(("Src", t + s0, max(t + dur - 0.2, t + s0 + b.get("src_hold", 0)), b["src"]))
        if b["name"] and not named:
            events.append(("Name", t + 0.5, t + min(dur, 5.0), NAME_TAG))
            named = True
        if items and (items[0]["fx"] or "") in ("slipend", "accretionend") and i > 0:
            prev = env["BLOCKS"][i - 1].get("items") or []
            if prev and prev[-1]["fx"] == items[0]["fx"][:-3]:
                items[0]["fx"] = f"{items[0]['fx']}:{prev[-1]['d']:.2f}"
        for k, it in enumerate(items):
            fades = []
            if b["fade"] in ("in", "inout") and k == 0:
                fades.append(("in", 0.5))
            if b["fade"] in ("out", "inout") and k == len(items) - 1:
                fades.append(("out", 0.5))
            it["fades"] = fades
            report.append(f"{clock(t + sum(x['d'] for x in items[:k]))} {b['kind']} {it['stem']}@{it['start']:.1f} {it['d']:.1f}s"
                          f"{' slow' + str(it['speed']) if it['speed'] != 1 else ''}"
                          f"{' stab' if trip.shake.get(it['stem'], 0) > vlog_trip.limit(trip.dir, 'shake_stab') and it['stab'] != '~' else ''}{' fx=' + it['fx'] if it['fx'] else ''}")
        b["items"] = items
        b["t"] = t
        t += dur
    total = t
    for r_ in restores:
        if not r_["_used"]:
            print(f"WARNING {eid}: words put back on the editing page are not in this edit list: {r_['voice']} "
                  f"{r_['from']:.2f}-{r_['to']:.2f} {r_.get('words', '')} (no {r_['voice']} block ends just before them)")
    guard_sheet(trip, eid, sheet, env["BLOCKS"], restores)
    first = not (trip.dir / "work" / "subtitles" / f"{eid}.xlsx").exists()
    if (not check and not rehearse) or (check and first and not rehearse):
        # a check or a rehearsal never rewrites the director's sheet; a brand-new video's first check writes it once,
        # so the checks that read the sheet (side effects, the editing page) have one from the start
        write_sheet(trip, eid, sheet)
    (trip.dir / "work" / "edl" / f"{eid}.rows.json").write_text(json.dumps(checkrows, ensure_ascii=False), encoding="utf-8")
    events = join_marks(events)
    sub_audit(events, sheet, checkrows)
    (trip.dir / "work" / "edl" / f"{eid}.cues.txt").write_text(
        f"# {total / 60:.2f} min, {len(env['BLOCKS'])} blocks\n" + "\n".join(f"{clock(s)} {clock(e)} {k:4s} {x}" for k, s, e, x in sorted(events, key=lambda e: e[1])),
        encoding="utf-8")
    (trip.dir / "work" / "edl" / f"{eid}.report.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"{eid}: {total / 60:.2f} min, {len(report)} shots")
    if check:                                          # the text layout is checked too (source line ran off 9:16)
        import tempfile
        write_ass(Path(tempfile.gettempdir()) / f"{eid}-check.ass", events, W, H)
        for w_ in TEXT_WARN:
            print("TEXT TOO WIDE:", w_)
        return
    # the review page's map of the video: which shot is on screen when, and what is being said
    shots = []
    for bi, b in enumerate(env["BLOCKS"]):
        t_ = b["t"]
        for it in b["items"]:
            shots.append(dict(t=round(t_, 3), d=round(it["d"], 3), stem=it["stem"], src=round(it["start"], 3), speed=it["speed"],
                              fx=it["fx"] or "", block=bi, kind=b["kind"], voice=b.get("voice"), a=b.get("a"), b=b.get("b"),
                              pics=b.get("pics", [])))
            t_ += it["d"]
    rev = sandbox / "review" if rehearse else trip.dir / "work" / "review"
    rev.mkdir(parents=True, exist_ok=True)
    # written as "pending" and made the real one only when the copy exists (a frozen render left a record of
    # a copy the director never saw, and the side-effect check compared against it)
    (rev / f"{eid}.timeline.pending.json").write_text(json.dumps(dict(
        eid=eid, video=video, phone=phone, total=round(total, 3), shots=shots,
        subs=[dict(s=round(s_, 3), e=round(e_, 3), text=x_) for k_, s_, e_, x_ in sorted(events, key=lambda e: e[1]) if k_ in ("Sub", "Nar")]),
        ensure_ascii=False), encoding="utf-8")
    for b in env["BLOCKS"]:
        for it in b["items"]:
            segs.append(segment(trip, it, W, H, it["fades"], work))
    print("pictures done", flush=True)
    voice, site = np.concatenate(voice_tl), np.concatenate(site_tl)
    n = len(voice)
    # the voice track exactly as used (no music), for the director to listen through
    folder = sandbox / "preview" if rehearse else trip.dir / "videos" / video / "preview"
    folder.mkdir(parents=True, exist_ok=True)
    write_wav(work / "voice.wav", np.stack([voice + site] * 2, 1))
    vlog_ff.run([vlog_env.FFMPEG, "-y", "-v", "error", "-i", str(work / "voice.wav"), "-af", "loudnorm=I=-16:TP=-2", "-ac", "1",
                    "-c:a", "aac", "-b:a", "64k", str(folder / f"{eid}-voice.m4a")], check=True)
    if env.get("TRACKS"):                              # licensed tracks the director chose (vlog_tracks.py)
        import vlog_tracks
        ends = [b["t"] for b in env["BLOCKS"] if b["kind"] == "E"]
        mrep = []
        music = vlog_tracks.render(env["TRACKS"], starts, ends[0] if ends else total, total, report=mrep)
        (work / "music-plan.txt").write_text("\n".join(mrep), encoding="utf-8")
        print("\n".join(mrep))
    else:                                              # no tracks chosen yet (a first cut): no music. The programmed
        music = np.zeros((n, 2), np.float32)           # music was dropped (it sounded cheap)
        print("music: none (the edit list has no TRACKS yet)")
    music = np.pad(music, ((0, max(0, n - len(music))), (0, 0)))[:n]
    fr_ = int(0.4 * SR)
    rv_ = 20 * np.log10(np.sqrt(np.mean(voice[:len(voice) // fr_ * fr_].reshape(-1, fr_) ** 2, axis=1)) + 1e-9)
    talk_db = float(np.median(rv_[rv_ > np.percentile(rv_, 90) - 15])) if len(rv_) else -22.0
    import vlog_tracks as _vt
    base = talk_db - (_vt.TARGET_RMS_DB if env.get("TRACKS") else -19.0)   # music files sit near -19 dBFS
    env_db = np.full(n, base - 10.0, np.float32)
    for s, e, k in kinds:
        env_db[int(s * SR):int(e * SR)] = base + env.get("MIX_REL", MIX_REL)[k]
    print(f"mix: speech {talk_db:.1f} dBFS, music under talk {talk_db + MIX_REL['V']:.1f}")
    k = int(0.6 * SR)
    c = np.cumsum(np.pad(env_db, (k // 2, k - k // 2), mode="edge"), dtype=np.float64)
    env_db = ((c[k:] - c[:-k]) / k)[:n].astype(np.float32)
    mix = music * (10 ** (env_db / 20))[:, None] + (voice + site)[:, None]
    write_wav(work / "mix.wav", mix)
    # the music alone, as mixed (ducking included), so the director can listen to the joins and endings
    write_wav(work / "music-only.wav", music * (10 ** (env_db / 20))[:, None])
    vlog_ff.run([vlog_env.FFMPEG, "-y", "-v", "error", "-i", str(work / "music-only.wav"), "-c:a", "aac", "-b:a", "96k",
                    str(folder / f"{eid}-music.m4a")], check=True)
    write_ass(work / "subs.ass", events, W, H)
    for w_ in TEXT_WARN:
        print("TEXT TOO WIDE:", w_)
    (work / "list.txt").write_text("".join(f"file '{p.as_posix()}'\n" for p in segs), encoding="utf-8")
    stats = vlog_ff.run([vlog_env.FFMPEG, "-hide_banner", "-i", str(work / "mix.wav"), "-af", "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
                            "-f", "null", "-"], capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    m = json.loads(stats[stats.rindex("{"):stats.rindex("}") + 1])
    an = (f"loudnorm=I=-14:TP=-2.5:LRA=11:linear=true:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:"
          f"measured_thresh={m['input_thresh']}:offset={m['target_offset']},aresample=48000,alimiter=limit=0.72:level=false")
    final = work / f"{eid}.mp4"  # encode on the local disk; writing straight to Google Drive stalls ffmpeg
    fd = FONT_DIR.as_posix().replace(":", "\\:")
    wm, seal = logo("logo_watermark"), logo("logo_seal")
    wsz = int(min(W, H) * 0.075)
    fc = [f"[0:v]subtitles=subs.ass:fontsdir='{fd}'[v0]",
          f"[2:v]scale={wsz}:-1,format=rgba,colorchannelmixer=aa=0.7[wm]",
          f"[v0][wm]overlay=W-w-{int(W * 0.025)}:{int(H * 0.025)}:enable='not({end_enable(env, total)})'[v1]"]
    last = "v1"
    for k_, b in enumerate([b for b in env["BLOCKS"] if b["kind"] == "T"]):
        a0, a1 = b["t"] + 0.3, b["t"] + sum(it["d"] for it in b["items"]) - 0.2
        fc.append(f"[3:v]scale={int(min(W, H) * 0.24)}:-1,format=rgba,fade=t=in:st={a0:.2f}:d=0.5:alpha=1,"
                  f"fade=t=out:st={a1 - 0.5:.2f}:d=0.5:alpha=1[s{k_}]")
        fc.append(f"[{last}][s{k_}]overlay=(W-w)/2:H*0.07:enable='between(t,{a0:.2f},{a1:.2f})'[t{k_}]")
        last = f"t{k_}"
    # looping images: copy to the local disk and give them an end, or ffmpeg re-reads them from Drive forever
    shutil.copyfile(wm, work / "wm.png")
    shutil.copyfile(seal, work / "seal.png")
    # an input the filter graph never reads (the seal, when a video has no title card) can freeze ffmpeg 9
    # for good (v03-short hung 1 h 40 min at 0 % CPU), so the seal is only given when it is used; no stdin; a time limit
    seal_in = ["-loop", "1", "-t", f"{total:.3f}", "-i", "seal.png"] if any("[3:v]" in f for f in fc) else []
    vlog_ff.run([vlog_env.FFMPEG, "-nostdin", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", "list.txt", "-i", str(work / "mix.wav"),
                    "-loop", "1", "-t", f"{total:.3f}", "-i", "wm.png"] + seal_in + [
                    "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "1:a", "-af", an,
                    "-c:v", "libx264", "-preset", "medium", "-crf", "27" if phone else "20", "-c:a", "aac", "-b:a", "128k" if phone else "192k", "-movflags", "+faststart",
                    "-t", f"{total:.3f}", str(final)], cwd=work, check=True, stdin=subprocess.DEVNULL, timeout=max(1800, total * 20))
    err = vlog_ff.run([vlog_env.FFMPEG, "-hide_banner", "-i", str(final), "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stderr
    tp = float(re.findall(r"Peak:\s+(-?[\d.]+) dBFS", err)[-1])
    if tp > -1.6:
        fixed = final.with_suffix(".tp.mp4")
        vlog_ff.run([vlog_env.FFMPEG, "-y", "-v", "error", "-i", str(final), "-map", "0", "-c:v", "copy", "-af", f"volume={-1.8 - tp:.2f}dB",
                        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(fixed)], check=True)
        fixed.replace(final)
        print(f"true peak {tp} dBFS: turned down {tp + 1.8:.1f} dB")
    if phone:                                          # editing stage: the small checking copy only
        shutil.copyfile(final, folder / f"{eid}-phone.mp4")
        print(folder / f"{eid}-phone.mp4")
        (rev / f"{eid}.timeline.pending.json").replace(rev / f"{eid}.timeline.json")
        return
    # the final goes straight to publish/ (no light copy for a final; once the final exists the
    # editing-stage videos of that piece are removed). Short: publish/short/short-9x16-final.mp4; long: publish/<video>.mp4
    pub = sandbox / "publish" if rehearse else trip.dir / "videos" / video / "publish"
    dest = pub / "short" / "short-9x16-final.mp4" if vertical else pub / f"{video}.mp4"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(final, dest)
    print(dest)
    gone = [folder / f"{eid}.mp4"] + sorted(folder.glob(f"{eid}-phone*.mp4")) + \
        ([] if rehearse else sorted((vlog_env.LOCAL / "send").rglob(f"{eid}*.mp4")))
    for g in gone:
        if g.exists():
            g.unlink()
            print("removed editing copy", g)
    if not rehearse:
        shutil.rmtree(vlog_env.LOCAL / "render" / name / f"{eid}-phone", ignore_errors=True)
    # the review page's copy, made from the final itself notes then land on exactly what
    # goes out; replaced whenever the final changes, never posted
    rW, rH = vlog_layout.frame("phone", env["W"], env["H"])
    if rehearse:
        rW, rH = rW // 4 // 2 * 2, rH // 4 // 2 * 2
    review = folder / f"{eid}-phone.mp4"
    vlog_ff.run([vlog_env.FFMPEG, "-nostdin", "-v", "error", "-y", "-i", str(dest), "-vf", f"scale={rW}:{rH}:flags=lanczos",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart",
                 str(review)], check=True)
    print("review copy (from the final):", review)
    (rev / f"{eid}.timeline.pending.json").replace(rev / f"{eid}.timeline.json")


def end_enable(env, total):
    ends = [b for b in env["BLOCKS"] if b["kind"] == "E"]
    if not ends:
        return "0"
    return f"gte(t,{ends[0]['t']:.2f})"


def split_text(text, s, e, limit):
    """New narration: split at punctuation into cues no longer than limit, timed by length."""
    parts = [p.strip() for p in re.split(r"(?<=[，。？！：；,.?!:;])", text) if p.strip()]
    pieces = []
    for p in parts:
        if pieces and units(pieces[-1] + p) <= limit:
            pieces[-1] += p
        else:
            pieces.append(p)
    total = sum(units(p) for p in pieces) or 1
    out, t = [], s
    for p in pieces:
        d = (e - s) * units(p) / total
        out.append((t, t + d, p.rstrip("，。,；;")))
        t += d
    return out


def logo(key):
    """A channel logo file ([channel] logo_watermark / logo_seal, relative to the folder that holds trips/), or a
    transparent stand-in when the channel has none, so the encode graph stays the same."""
    p = vlog_env.CHANNEL.get(key, "")
    f = vlog_env._path(p, vlog_env.TRIPS.parent) if p else None
    if f and f.is_file():
        return f
    blank = vlog_env.LOCAL / "render" / "blank-logo.png"
    if not blank.exists():
        from PIL import Image
        blank.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGBA", (64, 64), (0, 0, 0, 0)).save(blank)
    return blank


def end_card_events(t, dur, nxt, W, H):
    ev = [("EndHead", t + 0.5, t + dur, END_HEAD),
          ("EndNext", t + 1.0, t + dur, f"{END_NEXT} · {nxt}" if nxt else END_NEXT)]
    if CREDITS:
        ev.append(("Credit", t + 1.5, t + dur, CREDITS))
    if W > H:      # YouTube end-screen slots at 1080p (visuals.md), drawn faintly so nothing important sits under them
        for x, y, w, h in vlog_layout.end_slots(W, H):
            ev.append(("Slot", t + 0.3, t + dur, f"{{\\pos({x},{y})\\p1}}m 0 0 l {w} 0 l {w} {h} l 0 {h}{{\\p0}}"))
    return ev


def libass_lines(style, text, W, H, n):
    """The box of each line of `text` exactly as libass draws it in `style` (an ASS Style line) on a W x H frame:
    [(x0, x1, y0, y1)] top to bottom. One small render, cached on disk by its inputs."""
    import numpy as np
    from PIL import Image
    key = hashlib.md5(json.dumps([style, text, W, H, n, 2]).encode()).hexdigest()[:16]
    cache = vlog_env.LOCAL / "textcache"
    cache.mkdir(exist_ok=True)
    js = cache / f"{key}.json"
    if js.exists():
        return json.loads(js.read_text())
    ass_ = cache / f"{key}.ass"
    png = cache / f"{key}.png"
    ass_.write_text("\n".join(["[Script Info]", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
                               "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, "
                               "BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV", style, "", "[Events]",
                               "Format: Layer, Start, End, Style, Text", f"Dialogue: 0,0:00:00.00,0:00:05.00,Src,{text}"]),
                    encoding="utf-8")
    vlog_ff.run([vlog_env.FFMPEG, "-nostdin", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={W}x{H}:d=1",
                    "-vf", f"subtitles={ass_.name}:fontsdir='{FONT_DIR.as_posix().replace(':', chr(92) + ':')}'",
                    "-frames:v", "1", png.name], cwd=cache, check=True, stdin=subprocess.DEVNULL, timeout=60)
    a = np.asarray(Image.open(png).convert("L")) > 40
    rows = np.where(a.any(1))[0]
    if not len(rows):
        raise RuntimeError(f"source line drew nothing: {text}")
    # split the inked rows into n lines at the n-1 widest blank gaps
    gaps = sorted(((rows[i + 1] - rows[i], i) for i in range(len(rows) - 1) if rows[i + 1] - rows[i] > 1), reverse=True)[:n - 1]
    cuts = sorted(i for _, i in gaps)
    bands, a0 = [], 0
    for c in cuts + [len(rows) - 1]:
        bands.append((rows[a0], rows[c]))
        a0 = c + 1
    out = []
    for y0, y1 in bands:
        cols = np.where(a[y0:y1 + 1].any(0))[0]
        out.append((int(cols[0]), int(cols[-1]), int(y0), int(y1)))
    if len(out) != n:
        raise RuntimeError(f"source line: expected {n} lines, libass drew {len(out)}: {text}")
    js.write_text(json.dumps(out))
    ass_.unlink(missing_ok=True)
    png.unlink(missing_ok=True)
    return out


def ass_font(file, size):
    """A PIL font at the size libass really draws an ASS font size (libass fits ascender + descender to the size)."""
    from PIL import ImageFont
    f = ImageFont.truetype(str(FONT_DIR / file), 200)
    a, d = f.getmetrics()
    return ImageFont.truetype(str(FONT_DIR / file), max(1, round(size * 200 / (a + d))))


def wrap_px(text, font, maxw):
    """Lines (split on \\N or a newline) re-wrapped so none is wider than maxw pixels; breaks after punctuation or a
    space when one is in the second half of the line, never inside a Latin word if it can help it."""
    out = []
    for line in re.split(r"\\N|\n", text):
        while line and font.getlength(line) > maxw:
            k = max([i for i in range(1, len(line) + 1) if font.getlength(line[:i]) <= maxw] or [1])
            brk = max((i + 1 for i in range(k) if line[i] in "；;，,、。：: ）)"), default=0)
            if brk < k * 0.5:                          # no punctuation late enough: at least don't cut a Latin word
                sp = max((i for i in range(1, k) if not (line[i - 1].isascii() and line[i - 1].isalnum()
                                                          and line[i].isascii() and line[i].isalnum())), default=k)
                brk = sp if sp >= k * 0.5 else k
            out.append(line[:brk].rstrip())
            line = line[brk:].lstrip()
        out.append(line)
    return [l_ for l_ in out if l_]


TEXT_WARN = []                                         # boxed text that would run past the frame (printed by build)
BOXED = {k: v for k, v in vlog_layout.STYLE.items() if k != "Src"}   # the same table write_ass draws with


def write_ass(path, events, W, H):
    vertical = H > W
    size = vlog_layout.sub_size(W, H)
    mv = vlog_layout.sub_margin_v(W, H)
    rel = {k: v[1] for k, v in vlog_layout.STYLE.items()}     # every style's size, from the one table
    font, hand, bold = vlog_layout.FONT_NAME["text"], vlog_layout.FONT_NAME["hand"], vlog_layout.FONT_NAME["bold"]
    st = [
        f"Style: Sub,{font},{size},&H00F5F1F4,&H00101010,&H64000000,0,1,{size // 14},1,2,{W // 20},{W // 20},{mv}",
        f"Style: Nar,{font},{size},&H00A6E8FF,&H00101010,&H64000000,0,1,{size // 14},1,2,{W // 20},{W // 20},{mv}",
        f"Style: Tag,{font},{size * rel['Tag']:.0f},&H00A6E8FF,&H00101010,&H80000000,0,1,1,0,9,{round(W * vlog_layout.SRC_MARGIN_X)},{round(W * vlog_layout.SRC_MARGIN_X)},{int(H * 0.11)}",
        # sources: the handwriting font on a soft translucent plate, no outline (must not look like a subtitle)
        f"Style: Src,{hand},{size * rel['Src']:.0f},&H00F0F0F0,&H00141414,&H00000000,0,1,0,0,9,{round(W * vlog_layout.SRC_MARGIN_X)},{round(W * vlog_layout.SRC_MARGIN_X)},{int(H * vlog_layout.SRC_TOP)}",
        f"Style: Plate,{hand},10,&H66141414,&H00000000,&H00000000,0,1,0,0,7,0,0,0",
        # place tag: bottom-left, above the subtitle band (visuals.md)
        f"Style: Cap,{bold},{size * rel['Cap']:.0f},&H00FFFFFF,&H8C1A1814,&H00000000,1,3,{max(3, size // 10)},0,7,{int(W * 0.045)},{W // 24},{int(H * 0.06)}",
        # the gold dot drawn on its own over the tag's box (one box only: two colour runs drew two boxes)
        f"Style: CapDot,{bold},{size * rel['Cap']:.0f},&H003AB4E0,&H00000000,&H00000000,1,1,0,0,7,{int(W * 0.045)},{W // 24},{int(H * 0.06)}",
        f"Style: Name,{hand},{size * rel['Name']:.0f},&H00F4F4F4,&H00202020,&H64000000,0,1,{max(2, size // 20)},1,1,{W // 24},{W // 24},{mv + int(size * 1.7)}",
        f"Style: Title,{hand},{size * rel['Title']:.0f},&H00F4F4F4,&H00202020,&H64000000,0,1,{max(2, size // 12)},2,5,{W // 10},{W // 10},0",
        f"Style: EndHead,{hand},{size * rel['EndHead']:.0f},&H00F4F4F4,&H00202020,&H64000000,0,1,{max(2, size // 16)},1,7,{int(W * 0.06)},0,{int(H * 0.16)}",
        f"Style: EndNext,{hand},{size * rel['EndNext']:.0f},&H00A6E8FF,&H00202020,&H64000000,0,1,{max(2, size // 20)},1,7,{int(W * 0.06)},0,{int(H * 0.30)}",
        f"Style: Credit,{font},{size * rel['Credit']:.0f},&H00E0E0E0,&H00202020,&H64000000,0,1,1,0,1,{int(W * 0.24)},{int(W * 0.38)},{int(H * 0.08)}",
        f"Style: Slot,{font},20,&HFFFFFFFF,&HB0FFFFFF,&HFFFFFFFF,0,1,2,0,7,0,0,0",
    ]
    ass = ["[Script Info]", f"PlayResX: {W}", f"PlayResY: {H}", "WrapStyle: 0", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]",
           "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
           *st, "", "[Events]", "Format: Layer, Start, End, Style, Text"]
    subs = sorted([e_ for e_ in events if e_[0] in ("Sub", "Nar")], key=lambda e_: e_[1])
    for a_, b_ in zip(subs, subs[1:]):                 # one subtitle at a time: end each before the next starts
        if a_[2] > b_[1] - 0.04:
            events[events.index(a_)] = (a_[0], a_[1], max(a_[1] + 0.3, b_[1] - 0.04), a_[3])
    for k_, s, e, x in sorted(events, key=lambda e: e[1]):
        fx = "{\\fad(350,350)}" if k_ in ("Cap", "Tag", "Src", "Name", "Title", "EndHead", "EndNext", "Credit") else ""
        text = x if k_ == "Slot" else ass_text(x)
        if k_ == "Src":                                # one translucent plate behind all lines (a box per line overlapped)
            fs_ = int(round(size * rel["Src"]))        # = the Src style size
            pf = ass_font(vlog_layout.STYLE["Src"][0], fs_)
            pad = max(4, fs_ // 3)
            # wrapped here to the frame (9:16 is narrow), so libass never re-wraps behind the plate's back
            lines_ = wrap_px(x, pf, W - 2 * round(W * vlog_layout.SRC_MARGIN_X) - 2 * pad)
            text = "{\\q2}" + ass_text("\\N".join(lines_))
            # the plate hugs each line as libass draws it (fit around the words): a stepped shape,
            # right edge shared (the lines are right-aligned), each line's left edge its own, rounded-off steps
            style_ = next(l_ for l_ in st if l_.startswith("Style: Src,"))
            boxes = libass_lines(style_, text, W, H, len(lines_))
            if min(b[0] for b in boxes) < W // 80:
                TEXT_WARN.append(f"Src at {s:.1f} s reaches the frame edge: {x}")
            px, py = max(3, fs_ // 3), max(2, fs_ // 5)
            r_ = max(b[1] for b in boxes) + px
            tops = [boxes[0][2] - py] + [(boxes[i][3] + boxes[i + 1][2]) / 2 for i in range(len(boxes) - 1)] + [boxes[-1][3] + py]
            pts = [(r_, tops[0])]
            for i, b in enumerate(boxes):              # down the left side, line by line
                pts += [(b[0] - px, tops[i]), (b[0] - px, tops[i + 1])]
            pts.append((r_, tops[-1]))
            path_ = "m " + " l ".join(f"{x_:.0f} {y_:.0f}" for x_, y_ in pts)
            ass.append(f"Dialogue: 0,{clock(s)},{clock(e)},Plate,{fx}{{\\pos(0,0)\\p1}}{path_}{{\\p0}}")
        elif k_ in BOXED:                              # other boxed text: say so if it would not fit the frame
            file_, frac_ = BOXED[k_]
            pf = ass_font(file_, round(size * frac_))
            for l_ in re.split(r"\\N|\n", x):
                if pf.getlength(l_) > W * vlog_layout.TEXT_FIT:
                    TEXT_WARN.append(f"{k_} at {s:.1f} s is {pf.getlength(l_):.0f} px wide in a {W} px frame: {l_}")
        if k_ == "Cap":                                # the place tag: room for the gold dot, which is its own event above
            ass.append(f"Dialogue: 2,{clock(s)},{clock(e)},CapDot,{fx}●")
            text = "\\h\\h\\h\\h\\h" + text
        ass.append(f"Dialogue: {1 if k_ != 'Slot' else 0},{clock(s)},{clock(e)},{k_},{fx}{text}")
    path.write_text("\n".join(ass), encoding="utf-8")


def write_wav(path, x):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1] if x.ndim > 1 else 1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    build(a[0], a[1], "--check" in sys.argv)
