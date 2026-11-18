"""Score every clip from its 720p copy: shake, sharpness, exposure, and its steadiest stretch. Done once per trip.

Usage: python clip_score.py <trip>
Writes <trip>/work/clip-scores.json: file -> shake (share of frame width per step, after removing smooth camera moves),
pan (smooth camera movement), sharp (median Laplacian), bright (mean 0-255), clipped (% blown or black),
best: [start, end, shake] for the steadiest 3 s. Lower shake is steadier.
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env

STEP_FPS, WIDTH = 10, 320


def score(path):
    cap = cv2.VideoCapture(str(path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    step = max(int(round(fps / STEP_FPS)), 1)
    prev, moves, sharp, bright, clipped, i = None, [], [], [], [], 0
    while True:
        if not cap.grab():
            break
        if i % step == 0:
            ok, frame = cap.retrieve()
            if not ok:
                break
            gray = cv2.cvtColor(cv2.resize(frame, (WIDTH, WIDTH * frame.shape[0] // frame.shape[1])), cv2.COLOR_BGR2GRAY)
            sharp.append(cv2.Laplacian(gray, cv2.CV_64F).var())
            bright.append(float(gray.mean()))
            clipped.append(float(np.mean((gray < 8) | (gray > 247))) * 100)
            if prev is not None:
                pts = cv2.goodFeaturesToTrack(prev, 150, 0.01, 8)
                dx = dy = 0.0
                if pts is not None and len(pts) >= 8:
                    nxt, st, _ = cv2.calcOpticalFlowPyrLK(prev, gray, pts, None)
                    good = st.ravel() == 1
                    if good.sum() >= 6:
                        m, _ = cv2.estimateAffinePartial2D(pts[good], nxt[good], method=cv2.RANSAC)
                        if m is not None:
                            dx, dy = float(m[0, 2]), float(m[1, 2])
                moves.append((dx, dy))
            prev = gray
        i += 1
    cap.release()
    if not moves:
        return {"shake": None}
    a = np.array(moves) / WIDTH * 100
    size = min(STEP_FPS, len(a))      # very short clips have fewer steps than a one-second window
    kernel = np.ones(size) / size
    smooth = np.column_stack([np.convolve(a[:, k], kernel, mode="same") for k in (0, 1)])
    jitter = np.hypot(*(a - smooth).T)
    best = [0.0, min(len(jitter) / STEP_FPS, 3.0), float(jitter.mean())]
    w = 3 * STEP_FPS
    if len(jitter) > w:
        means = np.convolve(jitter, np.ones(w) / w, mode="valid")
        k = int(np.argmin(means))
        best = [k / STEP_FPS, (k + w) / STEP_FPS, float(means[k])]
    return {"shake": round(float(jitter.mean()), 3), "pan": round(float(np.hypot(*smooth.T).mean()), 3),
            "sharp": round(float(np.median(sharp)), 1), "bright": round(float(np.mean(bright)), 1),
            "clipped": round(float(np.mean(clipped)), 1), "best": [round(x, 2) for x in best]}


def main():
    name = sys.argv[1]
    proxy = vlog_env.LOCAL / "trips" / name / "proxy"
    out = vlog_env.TRIPS / name / "work" / "clip-scores.json"
    done = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    todo = [p for p in sorted(proxy.rglob("*.mp4")) if str(p.relative_to(proxy)) not in done and p.parent.name != "Rerecord"]
    with ProcessPoolExecutor(max_workers=10) as pool:
        for n, (p, r) in enumerate(zip(todo, pool.map(score, todo)), 1):
            done[str(p.relative_to(proxy))] = r
            if n % 25 == 0:
                out.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
                print(f"{n}/{len(todo)}", flush=True)
    out.write_text(json.dumps(done, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{len(done)} clips scored")


if __name__ == "__main__":
    main()
