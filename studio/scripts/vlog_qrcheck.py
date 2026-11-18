r"""The effects sheet: every shot with a drawn or tracked effect (QR blur, ticket circle, arrows, maps, CG), from the rendered video itself, every 0.2 s, for Claude to
look at before saying a video is ready (the v02 4K final showed the ticket's QR code sharp after its first
0.4 s; every check looked at the code that makes the blur, none at the video that came out, and an OpenCV read-back
test passed that video, so the eye is the check). The blur step itself stops a build on a frame left sharp between
blurred ones (vlog_fx.fx_qr "QR UNBLURRED").

    python vlog_qrcheck.py <trip> <id> <video.mp4>

Writes <local>/send/qr-<id>.jpg and prints "QR SHEET <path>"; nothing when the video has no QR shot.
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402

PLAIN_FX = ("", "black", "toptight", "dim")      # effects that only crop or darken: nothing to follow or hide


def sheet(trip_dir, vid, video):
    tl = json.loads((trip_dir / "work" / "review" / f"{vid}.timeline.json").read_text(encoding="utf-8"))
    shots = [s for s in tl["shots"] if (s.get("fx") or "").partition(":")[0] not in PLAIN_FX]
    if not shots:
        return None
    if not Path(video).exists():
        raise SystemExit(f"QR SHEET: {video} not found")
    cap = cv2.VideoCapture(str(video))
    tiles = []
    for s in shots:
        t = s["t"] + 0.02
        while t < s["t"] + s["d"]:
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, f = cap.read()
            if not ok:
                break
            h, w = f.shape[:2]
            f = cv2.resize(f, (480, round(480 * h / w)))
            cv2.putText(f, f"{s['fx']} {int(t // 60)}:{t % 60:05.2f}", (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            tiles.append(f)
            t += 0.2
    while len(tiles) % 5:
        tiles.append(np.zeros_like(tiles[0]))
    out = vlog_env.LOCAL / "send" / f"qr-{vid}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), np.vstack([np.hstack(tiles[k:k + 5]) for k in range(0, len(tiles), 5)]), [cv2.IMWRITE_JPEG_QUALITY, 85])
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = sheet(vlog_env.TRIPS / sys.argv[1], sys.argv[2], sys.argv[3])
    if p:
        print(f"QR SHEET {p}  (look at every frame before calling the video ready)")
