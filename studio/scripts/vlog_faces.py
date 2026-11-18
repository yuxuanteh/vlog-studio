r"""Faces in the shots, before anything renders (nothing is blurred by default;
every shot where a face is clearly recognisable is listed and the render waits for their decision).

    python vlog_faces.py <trip> <id> [<id> ...]          after vlog_build.py --check (reads its report.txt)

For every shot of the edit list (photos too), a frame every 0.5 s of the part used, at the analysis size, through
OpenCV's YuNet face finder. A face counts when the finder is sure (score >= 0.85) and it is at least FACE_MIN of the
frame's height (smaller faces are not recognisable). Car plates are not found by a model: look at the sheet.

Decisions live in <trip>/work/privacy.json, by stretch of clip, so a shot that moves a little keeps its answer:
    {"C0236": [[3.0, 9.5, "ok", "the director himself"], [12.0, 14.0, "blur", "family at the next table"]]}
"ok" = leave as it is, "blur" = to blur (a tracked "hide" effect will be added for it), "cut" = not to use.
Prints "ASK privacy ..." for every shot with faces and no decision, and writes the sheet
<local>/send/faces-<id>.jpg; exit 2 when anything is undecided.
"""
import hashlib
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402

MODEL = vlog_env.LOCAL / "models" / "opencv" / "face_detection_yunet_2023mar.onnx"
MODEL_SHA256 = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
FACE_MIN = 0.06          # a face at least this part of the frame height is recognisable
SCORE = 0.85
LINE = re.compile(r"^(\S+) (\w) (\S+?)@([\d.]+) ([\d.]+)s")


def finder():
    if not MODEL.exists():
        raise SystemExit(f"face model missing: {MODEL}")
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_SHA256:
        raise SystemExit(f"face model changed on disk (sha256): {MODEL}")
    return cv2.FaceDetectorYN_create(str(MODEL), "", (320, 320), SCORE, 0.3, 50)


def on_screen(f, w, h, fx, vertical):
    """Only faces the shot actually shows (faces cut away by "toptight" were listed): the effects that crop,
    and a 9:16 video's centre crop, taken into account. A face counts when its middle is inside the shown part."""
    cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
    x0, x1, y0, y1 = 0.0, w, 0.0, h
    if fx in ("blur", "faces", "qr", "black"):
        return fx not in ("faces", "black")            # already hidden
    if fx == "toptight":                               # vlog_fx.fx_toptight: top 72 %, centred
        x0, x1, y1 = w * 0.14, w * 0.86, h * 0.72
    if vertical:                                       # a 9:16 crop of a wide clip (centre, cx 0.5 unless set)
        cw = h * 9 / 16
        x0, x1 = max(x0, (w - cw) / 2), min(x1, (w + cw) / 2)
    return x0 <= cx <= x1 and y0 <= cy <= y1


def decided(dec, stem, a, b):
    for x0, x1, what, *_ in dec.get(stem, []):
        if x0 <= a + 0.01 and b <= x1 + 0.01:
            return what
    return None


def scan(trip, vid):
    import vlog_build as B
    t = B.Trip(trip) if isinstance(trip, str) else trip
    edl = t.dir / "work" / "edl"
    shots = []
    for line in (edl / f"{vid}.report.txt").read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if m:
            fx = (re.search(r"fx=(\w+)", line) or [None, ""])[1]
            shots.append((m[1], m[3], float(m[4]), float(m[5]), fx))
    env = {}
    any_ = lambda *a, **k: {}                         # the edit list is read only for its frame size
    exec((edl / f"{vid}.py").read_text(encoding="utf-8"), {k: any_ for k in "VNSMTEC"}, env)
    vertical = env.get("H", 1080) > env.get("W", 1920)
    pf = t.dir / "work" / "privacy.json"
    dec = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    fd = finder()
    found, tiles = [], []
    for at, stem, src, d, fx in shots:
        try:
            path = t.path(stem)
        except SystemExit:
            continue
        # the 720p working copy when there is one (footage_proxy.py): seeking in 4K clips took over 30 min for v02;
        # a face of FACE_MIN is still ~43 px high at 720p, plenty for the finder
        if not stem.startswith("P:"):
            rel = t.clips[stem]["file"] if stem in t.clips else None
            prox = vlog_env.LOCAL / "trips" / t.dir.name / "proxy" / Path(rel).with_suffix(".mp4") if rel else None
            if prox is not None and prox.exists():
                path = prox
        cap = cv2.VideoCapture(str(path))
        best = None
        for k in range(max(1, int(d / 0.5))):
            if stem.startswith("P:"):
                ok, fr = True, cv2.imread(str(path))
                if fr is None:
                    break
            else:
                cap.set(cv2.CAP_PROP_POS_MSEC, (src + k * 0.5 + 0.1) * 1000)
                ok, fr = cap.read()
            if not ok:
                break
            h, w = fr.shape[:2]
            s = 1280 / max(w, h)
            if s < 1:
                fr = cv2.resize(fr, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
            h, w = fr.shape[:2]
            fd.setInputSize((w, h))
            _, faces = fd.detect(fr)
            big = [f for f in (faces if faces is not None else []) if f[3] >= FACE_MIN * h and on_screen(f, w, h, fx, vertical)]
            if big and (best is None or max(f[3] for f in big) > best[0]):
                best = (max(f[3] for f in big) / h, fr.copy(), big, src + k * 0.5)
            if stem.startswith("P:"):
                break
        cap.release()
        if best is None:
            continue
        what = decided(dec, stem, src, src + d)
        found.append(dict(at=at, stem=stem, src=src, d=d, size=round(best[0], 3), n=len(best[2]), decided=what))
        if what is None:
            fr = best[1]
            for f in best[2]:
                x, y, fw, fh = map(int, f[:4])
                cv2.rectangle(fr, (x, y), (x + fw, y + fh), (0, 230, 255), max(2, fr.shape[0] // 200))
            fr = cv2.resize(fr, (480, round(480 * fr.shape[0] / fr.shape[1])))
            cv2.putText(fr, f"{at[2:10]} {stem}@{src:.1f}", (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            tiles.append(fr)
    sheet = None
    if tiles:
        hmax = max(x.shape[0] for x in tiles)
        tiles = [cv2.copyMakeBorder(x, 0, hmax - x.shape[0], 0, 0, cv2.BORDER_CONSTANT) for x in tiles]
        while len(tiles) % 4:
            tiles.append(np.zeros_like(tiles[0]))
        sheet = vlog_env.LOCAL / "send" / f"faces-{vid}.jpg"
        sheet.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(sheet), np.vstack([np.hstack(tiles[k:k + 4]) for k in range(0, len(tiles), 4)]),
                    [cv2.IMWRITE_JPEG_QUALITY, 85])
    return found, sheet


def from_review(trip_dir, vid):
    """Review notes tagged 要打码 each one asked until privacy.json holds a decision for its shot."""
    f = trip_dir / "work" / "review" / f"{vid}.notes.json"
    pf = trip_dir / "work" / "privacy.json"
    dec = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    out = []
    for n in (json.loads(f.read_text(encoding="utf-8")).get("notes", []) if f.exists() else []):
        if any(t in ("要打码", "blur this") for t in n.get("tags", [])) and n.get("src") is not None:
            if decided(dec, n["stem"], n["src"], n["src"]) is None:
                out.append(f"ASK privacy {vid} {n['t']:.1f}s {n['stem']}@{n['src']:.1f}: the director tagged 要打码 on the "
                           f"review page - add a blur (!faces or a fixed area) and write the decision")
    return out


def blur_missing(trip_dir, vid):
    """A shot decided "blur" whose edit-list picture has no blur effect yet."""
    pf = trip_dir / "work" / "privacy.json"
    dec = json.loads(pf.read_text(encoding="utf-8")) if pf.exists() else {}
    out = []
    for line in (trip_dir / "work" / "edl" / f"{vid}.report.txt").read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if not m:
            continue
        fx = (re.search(r"fx=(\w+)", line) or [None, ""])[1]
        a = float(m[4])
        if decided(dec, m[3], a, a + float(m[5])) == "blur" and fx not in ("faces", "blur"):
            out.append(f"ASK privacy {vid} {m[1][2:10]} {m[3]}@{a:.1f}: decided blur, but the shot has no blur yet")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ask = False
    for v in sys.argv[2:]:
        extra = from_review(vlog_env.TRIPS / sys.argv[1], v) + blur_missing(vlog_env.TRIPS / sys.argv[1], v)
        for line in extra:
            print(line)
        ask |= bool(extra)
        found, sheet = scan(sys.argv[1], v)
        todo = [f for f in found if f["decided"] is None]
        for f in todo:
            print(f"ASK privacy {v} {f['at'][2:10]} {f['stem']}@{f['src']:.1f}-{f['src'] + f['d']:.1f}: "
                  f"{f['n']} face(s), largest {f['size'] * 100:.0f}% of the height - ok / blur / cut?")
        print(f"# {v}: {len(found)} shot(s) with a recognisable face, {len(todo)} undecided"
              + (f"; sheet {sheet}" if sheet else ""))
        ask |= bool(todo)
    sys.exit(2 if ask else 0)
