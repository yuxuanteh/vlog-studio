"""The review page's side of the editing server (notes on a build without typing long feedback).

The director plays a build's phone copy, pauses, taps a ready-made note ("too short", "shaky", ...) and maybe adds a few
words. Each note is saved with the exact time, the shot on screen (clip, source second, edit-list block) and the subtitle
being said, so Claude knows precisely which shot is meant.

Files
  <trip>/work/review/<id>.timeline.json   written by vlog_build.py: every shot and subtitle with its time
  <trip>/work/review/<id>.notes.json      the director's notes (this module writes it; a copy goes to editor-cache/backup)
  <trip>/videos/<video>/preview/<id>-phone.mp4   the build being reviewed
For builds made before the timeline existed, the timeline is rebuilt from the render folder (list.txt + subs.ass):
same shots and times, without the source second and block.
"""
import json
import re
import shutil
import subprocess
import time
from pathlib import Path

import vlog_env
import vlog_ff

CACHE = vlog_env.LOCAL / "editor-cache"


def video_name(trip, vid):
    f = trip.dir / "work" / "edl" / f"{vid}.py"
    m = re.search(r'^VIDEO\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"), re.M) if f.exists() else None
    return m[1] if m else vid.split("-")[0]


def phone_file(trip, vid):
    return trip.dir / "videos" / video_name(trip, vid) / "preview" / f"{vid}-phone.mp4"


def reviews(trip):
    """Videos that have a phone copy to review."""
    out = []
    for f in sorted((trip.dir / "work" / "edl").glob("*.py")):
        if f.stem.endswith(".bak") or "." in f.stem:
            continue
        p = phone_file(trip, f.stem)
        if p.exists():
            out.append(dict(id=f.stem, built=time.strftime("%m-%d %H:%M", time.localtime(p.stat().st_mtime))))
    return out


def _clock(s):
    h, m, x = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(x)


def _probe(path):
    r = vlog_ff.run([vlog_env.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def timeline(trip, vid):
    phone = phone_file(trip, vid)
    f = trip.dir / "work" / "review" / f"{vid}.timeline.json"
    if f.exists() and phone.exists() and f.stat().st_mtime <= phone.stat().st_mtime + 5:
        # a final's timeline is as good: phone and final share every time, and after a final the phone copy is made
        # from the final itself ("no timeline for v02-teaser" after the final had cleared the phone build)
        return json.loads(f.read_text(encoding="utf-8"))
    # an older build: rebuild the map from what the render left behind
    work = vlog_env.LOCAL / "render" / trip.dir.name / f"{vid}-phone"
    lst = work / "list.txt"
    if not lst.exists():
        raise FileNotFoundError(f"no timeline for {vid}: rebuild it once")
    CACHE.mkdir(parents=True, exist_ok=True)
    cf = CACHE / f"{trip.dir.name}-{vid}-timeline.json"
    if cf.exists() and cf.stat().st_mtime >= lst.stat().st_mtime:
        return json.loads(cf.read_text(encoding="utf-8"))
    shots, t = [], 0.0
    for s in re.findall(r"file '([^']+)'", lst.read_text(encoding="utf-8")):
        d = _probe(s)
        shots.append(dict(t=round(t, 3), d=round(d, 3), stem=Path(s).name.rsplit("-", 1)[0].replace("P_", "P:"), src=None,
                          block=None, kind=None, fx=""))
        t += d
    subs = []
    sf = work / "subs.ass"
    for line in sf.read_text(encoding="utf-8").splitlines() if sf.exists() else []:
        if line.startswith("Dialogue") and (",Sub," in line or ",Nar," in line):
            p = line.split(",", 4)
            text = re.sub(r"\{[^}]*\}", "", line.split(",Sub," if ",Sub," in line else ",Nar,", 1)[1]).replace("\\N", " ")
            subs.append(dict(s=_clock(p[1]), e=_clock(p[2]), text=text.strip()))
    d = dict(eid=vid, video=video_name(trip, vid), phone=True, total=round(t, 3), shots=shots, subs=subs, rebuilt=True)
    cf.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def thumb(trip, vid, k):
    """One small frame from the middle of shot k of the phone copy, made once per build."""
    tl = timeline(trip, vid)
    sh = tl["shots"][k]
    phone = phone_file(trip, vid)
    d = CACHE / "thumbs" / f"{trip.dir.name}-{vid}-{int(phone.stat().st_mtime)}"
    d.mkdir(parents=True, exist_ok=True)
    out = d / f"{k:04d}.jpg"
    if not out.exists():
        vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", "-ss", f"{sh['t'] + sh['d'] / 2:.3f}", "-i", str(phone),
                        "-frames:v", "1", "-vf", "scale=-2:90", "-q:v", "5", str(out)], check=True)
    return out


def notes_file(trip, vid):
    return trip.dir / "work" / "review" / f"{vid}.notes.json"


def _note_time(n):
    """A note's own time ("at", UTC from the page) as epoch seconds; None when it has none."""
    import datetime
    try:
        return datetime.datetime.fromisoformat(n["at"].replace("Z", "+00:00")).timestamp()
    except (KeyError, ValueError, AttributeError):
        return None


def copy_id(phone):
    """Which copy: its size and time on disk (a new copy always differs in one)."""
    if not phone.exists():
        return None
    st = phone.stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


def archive_old_notes(trip, vid):
    """Notes left on an older copy than the one on the page now are moved out ("do them
    automatically"). A new copy only exists after Claude worked through the notes, and their times point at the old cut.
    They go to work/review/old-notes/<id>.notes.<old build>.json, never deleted. Each note is judged by its own time,
    not the file's "build" stamp, which every save rewrites to the current copy."""
    f, phone = notes_file(trip, vid), phone_file(trip, vid)
    if not f.exists() or not phone.exists():
        return 0
    data = json.loads(f.read_text(encoding="utf-8"))
    built = phone.stat().st_mtime
    cur = copy_id(phone)
    old = [n for n in data.get("notes", [])
           if (n["copy"] != cur if n.get("copy") else (_note_time(n) or built) < built - 60)]
    if not old:
        return 0
    keep = [n for n in data["notes"] if n not in old]
    stamp = time.strftime("%Y%m%d-%H%M", time.localtime(max(_note_time(n) for n in old)))
    dest = f.parent / "old-notes" / f"{vid}.notes.{stamp}.json"
    dest.parent.mkdir(exist_ok=True)
    prev = json.loads(dest.read_text(encoding="utf-8"))["notes"] if dest.exists() else []
    dest.write_text(json.dumps(dict(notes=prev + [n for n in old if n not in prev], moved=time.strftime("%Y-%m-%d %H:%M")),
                               ensure_ascii=False, indent=1), encoding="utf-8")
    data["notes"] = keep
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(old)


def load_notes(trip, vid):
    archive_old_notes(trip, vid)
    f = notes_file(trip, vid)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else dict(notes=[])


def save_notes(trip, vid, data):
    f = notes_file(trip, vid)
    f.parent.mkdir(exist_ok=True)
    if f.exists():
        b = CACHE / "backup"
        b.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, b / f"{vid}.notes.{time.strftime('%Y%m%d-%H%M%S')}.json")
    phone = phone_file(trip, vid)
    data["build"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(phone.stat().st_mtime)) if phone.exists() else None
    # each note carries the copy it was left on old notes move out by that, never by clock times
    copy = copy_id(phone)
    for n in data.get("notes", []):
        n.setdefault("copy", copy)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return dict(ok=True, n=len(data.get("notes", [])))


def send_file(handler, path, ctype):
    """Serve a file with byte ranges, so the browser can seek in a video."""
    size = path.stat().st_size
    rng = handler.headers.get("Range")
    start, end = 0, size - 1
    if rng:
        m = re.match(r"bytes=(\d*)-(\d*)", rng)
        if m:
            if m[1]:
                start = int(m[1])
                end = int(m[2]) if m[2] else size - 1
            elif m[2]:
                start = max(0, size - int(m[2]))
        end = min(end, size - 1)
        handler.send_response(206)
        handler.send_header("Content-Range", f"bytes {start}-{end}/{size}")
    else:
        handler.send_response(200)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Length", str(end - start + 1))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    with open(path, "rb") as fh:
        fh.seek(start)
        left = end - start + 1
        try:
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk:
                    break
                handler.wfile.write(chunk)
                left -= len(chunk)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass                                        # the browser seeks by dropping a request: normal
