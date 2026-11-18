"""Per-second shake and movement for every clip, so shots are picked from what really happens on screen (director
shots were chosen from one-line descriptions, so they missed the moment and ran into violent shaking).

Usage (vlog venv): python clip_motion.py <trip> [stems...]       (all clips when no stems; finished ones are skipped)
Reads  <studio>/trips/<trip>/proxy/**/<stem>.mp4  (the 720p working copies)
Writes <trip>/work/motion/<stem>.json  {"fps": 1, "shake": [...], "move": [...], "pan": [...]}, one number per second:
  shake  jitter of the camera itself: frame-to-frame translation minus its 1 s moving average, in % of the frame width
         per frame (handheld wobble, a jolt, a fall). Under ~0.4 calm, 0.4-1 noticeable, over ~1 violent.
  pan    the smooth camera movement in % of the width per second (a deliberate pan or tilt)
  move   how much the picture changes once the camera movement is taken out (0-100): something moving in the scene
         (the model's plate rising, the bow released, a train passing, mist forming a tornado)
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env

FPS = 10


def measure(path):
    cap = cv2.VideoCapture(str(path))
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(1, int(round(src_fps / FPS)))
    prev, k = None, 0
    shifts, moves = [], []
    win = None
    while True:
        ok = cap.grab()
        if not ok:
            break
        if k % step == 0:
            ok, f = cap.retrieve()
            if not ok:
                break
            g = cv2.cvtColor(cv2.resize(f, (192, 108), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY).astype(np.float32)
            if win is None:
                win = cv2.createHanningWindow(g.shape[::-1], cv2.CV_32F)
            if prev is not None:
                (dx, dy), _ = cv2.phaseCorrelate(prev, g, win)
                shifts.append((dx, dy))
                M = np.float32([[1, 0, -dx], [0, 1, -dy]])
                aligned = cv2.warpAffine(g, M, g.shape[::-1], borderMode=cv2.BORDER_REPLICATE)
                diff = np.abs(aligned[6:-6, 6:-6] - prev[6:-6, 6:-6])
                moves.append(float(np.mean(diff > 18) * 100))
            prev = g
        k += 1
    cap.release()
    if not shifts:
        return dict(fps=1, shake=[], move=[], pan=[])
    sh = np.array(shifts) / 192 * 100                      # % of frame width per sample
    kn = max(1, min(FPS, len(sh)))                         # a clip under 1 s: smooth over what there is
    kern = np.ones(kn) / kn
    smooth = np.stack([np.convolve(sh[:, i], kern, mode="same") for i in range(2)], 1)
    jitter = np.hypot(*(sh - smooth).T)
    pan = np.hypot(*smooth.T) * FPS
    mv = np.array(moves)
    n = int(np.ceil(len(sh) / FPS))
    per = lambda a, fn: [round(float(fn(a[i * FPS:(i + 1) * FPS])), 2) for i in range(n) if len(a[i * FPS:(i + 1) * FPS])]
    return dict(fps=1, shake=per(jitter, lambda x: np.percentile(x, 80)), pan=per(pan, np.mean), move=per(mv, np.mean))


def main():
    trip = sys.argv[1]
    proxy = vlog_env.LOCAL / "trips" / trip / "proxy"
    out = vlog_env.TRIPS / trip / "work" / "motion"
    out.mkdir(exist_ok=True)
    want = set(sys.argv[2:])
    files = sorted(p for p in proxy.rglob("*.mp4") if not want or p.stem in want)
    for i, p in enumerate(files):
        f = out / f"{p.stem}.json"
        if f.exists():
            continue
        try:
            f.write_text(json.dumps(measure(p)), encoding="utf-8")
        except Exception as e:                            # one broken clip must not stop the rest
            print(f"skip {p.stem}: {type(e).__name__}: {e}", flush=True)
        if i % 25 == 0:
            print(f"{i + 1}/{len(files)} {p.stem}", flush=True)
    print("motion done", flush=True)


if __name__ == "__main__":
    main()
