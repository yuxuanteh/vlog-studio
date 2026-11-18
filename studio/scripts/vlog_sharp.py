r"""Sharpness of every shot in a 4K final (from the v01 test: a 480p review copy cannot show soft focus or
noise, so the final is looked at once at full size before the director is told it is ready).

    python vlog_sharp.py <trip> <id>

Reads the final in publish/ and the build's timeline (work/review/<id>.timeline.json). For the middle frame of each
shot it measures how much fine detail the centre of the picture holds, prints the softest shots against the video's
median, and writes a sheet of 100 % crops of the six softest to <local>/send/sharp-<id>.jpg for Claude to look at.
Nothing stops the run: a soft shot is told to the director with its time, never fixed in the edit (lighting and focus
are fixed on site).
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402
import vlog_review  # noqa: E402


def final_file(trip_dir, vid):
    """The final of this edit: the long video publish/<video>.mp4, or the short publish/short/short-9x16-final.mp4."""
    edl = (trip_dir / "work" / "edl" / f"{vid}.py").read_text(encoding="utf-8")
    import re
    m = re.search(r"^W, H = (\d+), (\d+)", edl, re.M)
    video = (re.search(r'^VIDEO = "([^"]+)"', edl, re.M) or [None, vid.split("-")[0]])[1]
    pub = trip_dir / "videos" / video / "publish"
    return pub / "short" / "short-9x16-final.mp4" if m and int(m[2]) > int(m[1]) else pub / f"{video}.mp4"


def main(trip, vid):
    trip_dir = vlog_env.TRIPS / trip
    f = final_file(trip_dir, vid)
    if not f.exists():
        raise SystemExit(f"SHARP: no final yet ({f})")
    tl = json.loads((trip_dir / "work" / "review" / f"{vid}.timeline.json").read_text(encoding="utf-8"))
    cap = cv2.VideoCapture(str(f))
    rows = []
    for s in tl["shots"]:
        if (s.get("fx") or "").split(":")[0] == "black":
            continue
        t = s["t"] + s["d"] / 2
        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, fr = cap.read()
        if not ok:
            continue
        h, w = fr.shape[:2]
        mid = fr[int(h * 0.18):int(h * 0.78), int(w * 0.2):int(w * 0.8)]            # away from the subtitle band and tags
        g = cv2.cvtColor(mid, cv2.COLOR_BGR2GRAY)
        rows.append((float(cv2.Laplacian(g, cv2.CV_64F).var()), t, s["stem"], s.get("fx") or "",
                     fr[h // 2 - 300:h // 2 + 300, w // 2 - 600:w // 2 + 600].copy()))
    cap.release()
    if not rows:
        raise SystemExit("SHARP: no frames read")
    med = float(np.median([r[0] for r in rows]))
    rows.sort(key=lambda r: r[0])
    print(f"# {vid}: {len(rows)} shots, median detail {med:.0f}")
    for sh, t, stem, fx, _ in rows[:8]:
        print(f"  {int(t // 60)}:{t % 60:04.1f}  {stem:<10} detail {sh:5.0f} ({sh / med * 100:.0f} % of the median){' ' + fx if fx else ''}")
    tiles = []
    for sh, t, stem, fx, c in rows[:6]:
        cv2.putText(c, f"{int(t // 60)}:{t % 60:04.1f} {stem} {sh:.0f}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 255, 255), 3)
        tiles.append(c)
    while len(tiles) < 6:
        tiles.append(np.zeros_like(tiles[0]))
    out = vlog_env.LOCAL / "send" / f"sharp-{vid}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[:3]), np.hstack(tiles[3:6])]), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(f"SHARP SHEET {out}  (look at it before calling the final ready)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1], sys.argv[2])
