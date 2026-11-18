"""Picture check for a build, run before anything is sent (the old checks tested only the voice,
so the same picture errors came back round after round).

Usage (vlog venv): python vlog_piccheck.py <trip> <id> [<id> ...]
Reads  work/review/<id>.timeline.json (written by vlog_build), work/motion/<stem>.json (clip_motion.py),
       work/transcript/<stem>.txt (each clip's own sound, Whisper), the phone copy (frames for look-alike shots)
Writes work/review/<id>.piccheck.txt; prints the problems. Each line: time, shot, what is wrong.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env  # noqa: E402
import vlog_trip
import vlog_ff
import vlog_review

MIN_SHOT = 2.0                      # shaking limits: vlog_trip (the trip's own, else the defaults)
SHOWN_FX = ("", "toptight", "dim", "zoomin", "faces", "blur", "qr")     # effects that still show the clip's own picture
LANDSCAPE_FX = ("ticket", "paneltop", "slip", "accretion", "slipend", "accretionend", "segamap", "segamap2", "malay")
CG_LEN = {"slip": 7.5, "accretion": 20.2}              # seconds of each Blender shot
HALLU = re.compile(r"点赞|订阅|转发|打赏|字幕|志愿者|谢谢大家|明镜|栏目|请不吝|Thank you|^\W*$")


def mmss(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def motion(trip, stem):
    f = trip.dir / "work" / "motion" / f"{stem}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def speech(trip, stem):
    f = trip.dir / "work" / "transcript" / f"{stem}.txt"
    out = []
    for line in f.read_text(encoding="utf-8").splitlines() if f.exists() else []:
        m = re.match(r"\[\s*([\d.]+) ->\s*([\d.]+)\] (.*)", line)
        if m and not HALLU.search(m[3]):
            out.append((float(m[1]), float(m[2]), m[3]))
    return out


def frame(path, t):
    """A colour histogram of one frame (hue, saturation, value): two shots of the same sign framed a little differently
    still match (0.95), different scenes do not (under 0.4)."""
    r = vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1", "-vf",
                        "scale=96:54", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"], capture_output=True)
    if len(r.stdout) != 96 * 54 * 3:
        return None
    x = cv2.cvtColor(np.frombuffer(r.stdout, np.uint8).reshape(54, 96, 3), cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([x], [0, 1, 2], None, [12, 6, 6], [0, 180, 0, 256, 0, 256])
    return cv2.normalize(h, h).flatten()


def check(trip, vid):
    tl = vlog_review.timeline(trip, vid)
    shots, subs = tl["shots"], tl["subs"]
    phone = vlog_review.phone_file(trip, vid)
    vertical = False
    if phone.exists():
        cap = cv2.VideoCapture(str(phone))
        vertical = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) > cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        cap.release()
    probs = []

    def add(t, sh, what):
        probs.append((t, f"{mmss(t)}  {sh['stem']:<10} {what}"))

    used = []                                           # (stem, from, to, shot) of the source used
    for k, sh in enumerate(shots):
        fx = (sh.get("fx") or "").split(":")[0]
        kind = sh.get("kind")
        # a map or CG shot only borrows a clip to draw over (v01's Google Earth shots were reported as
        # reused, look-alike and too short): only shots that show the clip's own picture are judged as footage
        real = not sh["stem"].startswith("P:") and fx in SHOWN_FX
        # 1 too short (the music-only opening montage is short on purpose; a drawn shot's hold continues the one before)
        if sh["d"] < MIN_SHOT and kind != "M" and sh["stem"] != sh.get("voice") and (real or not fx.endswith("end")):
            add(sh["t"], sh, f"only {sh['d']:.1f} s on screen")
        if sh.get("src") is None or not real:
            continue
        a, b = sh["src"], sh["src"] + sh["d"] * (sh.get("speed") or 1)
        # 2 the same stretch of a clip twice
        for st, p, q, k2 in used:
            if st == sh["stem"] and min(b, q) - max(a, p) > 0.5 and not (sh.get("voice") == st) and shots[k2].get("kind") != "M":
                add(sh["t"], sh, f"same part of the clip as at {mmss(shots[k2]['t'])} ({max(a, p):.1f}-{min(b, q):.1f} s of the clip)")
                break
        used.append((sh["stem"], a, b, k))
        # 3 shaking inside the part used
        mo = motion(trip, sh["stem"]) if sh["stem"] != sh.get("voice") else None   # the speaker walking: natural
        if mo and mo["shake"]:
            secs = mo["shake"][int(a):max(int(a) + 1, int(np.ceil(b)))]
            worst = max(secs) if secs else 0
            if worst >= vlog_trip.limit(trip.dir, "shake_violent"):
                add(sh["t"], sh, f"violent shaking in the part used (shake {worst:.1f} at {int(a) + secs.index(worst)} s of the clip)")
            elif worst >= vlog_trip.limit(trip.dir, "shake_warn") and sh["stem"] != sh.get("voice"):
                add(sh["t"], sh, f"shaky in the part used (shake {worst:.1f})")
        # 4 someone talking in the clip's own sound, where the clip's sound is heard (breathing room, montage)
        if kind in ("S",):
            for s0, s1, txt in speech(trip, sh["stem"]):
                if min(b, s1) - max(a, s0) > 0.2:
                    add(sh["t"], sh, f"speech in its own sound: 「{txt[:20]}」 ({s0:.1f}-{s1:.1f} s of the clip)")
                    break
    # 5 two look-alike shots back to back
    if phone.exists():
        prev = None
        for sh in shots:
            f = frame(phone, sh["t"] + sh["d"] / 2)
            cont = prev is not None and prev[1]["stem"] == sh["stem"] and sh.get("src") is not None and prev[1].get("src") is not None \
                and abs(sh["src"] - (prev[1]["src"] + prev[1]["d"] * (prev[1].get("speed") or 1))) < 1.0   # the same shot carrying on
            if f is not None and prev is not None and not cont and sh.get("kind") != "M" \
                    and (sh.get("fx") or "").split(":")[0] in SHOWN_FX and (prev[1].get("fx") or "").split(":")[0] in SHOWN_FX:
                c = float(cv2.compareHist(f, prev[0], cv2.HISTCMP_CORREL))
                if c > 0.9 or (sh["stem"] == prev[1]["stem"] and sh["stem"] != sh.get("voice") and not (sh.get("fx") or "").split(":")[0].endswith("end")):
                    add(sh["t"], sh, f"looks like the shot before ({prev[1]['stem']}, similarity {c:.2f})")
            prev = (f, sh) if f is not None else prev
    # 6 animations: cut off before the end with no hold after, or a landscape graphic in a 9:16 video
    for k, sh in enumerate(shots):
        fx = (sh.get("fx") or "").split(":")[0]
        if fx in CG_LEN and sh["d"] < CG_LEN[fx] - 0.5:
            nxt = shots[k + 1] if k + 1 < len(shots) else None
            if not (nxt and (nxt.get("fx") or "").startswith(fx + "end")):
                add(sh["t"], sh, f"animation cut at {sh['d']:.1f} s of {CG_LEN[fx]:.1f} s, nothing continues it")
        base = fx[:-3] if fx.endswith("end") else fx
        if vertical and fx in LANDSCAPE_FX and not (vlog_env.LOCAL / "cg" / f"{base}-v").exists():
            add(sh["t"], sh, f"landscape graphic ({fx}) in a 9:16 video")
    # 7 subtitles: notes, cut marks or the director's / left in what is burned in
    for x in subs:
        if re.search(r"[()（）〔〕\[\]［］/／]", x["text"]):
            probs.append((x["s"], f"{mmss(x['s'])}  subtitle   marks left in: 「{x['text'][:30]}」"))
        if x["e"] - x["s"] < 0.6:
            probs.append((x["s"], f"{mmss(x['s'])}  subtitle   on screen only {x['e'] - x['s']:.1f} s: 「{x['text'][:20]}」"))
    probs.sort()
    lines = [p for _, p in probs]
    out = trip.dir / "work" / "review" / f"{vid}.piccheck.txt"
    out.write_text(f"# {vid}: {len(lines)} picture problem(s)" + (" (old build: no source times)" if tl.get("rebuilt") else "") + "\n"
                   + "\n".join(lines) + "\n", encoding="utf-8")
    return lines, tl.get("rebuilt")


if __name__ == "__main__":
    import vlog_editor
    trip = vlog_editor.Trip(sys.argv[1])
    for vid in sys.argv[2:]:
        lines, old = check(trip, vid)
        print(f"# {vid}: {len(lines)} picture problem(s)" + (" (old build, rough check)" if old else ""))
        for l in lines:
            print("  " + l)
