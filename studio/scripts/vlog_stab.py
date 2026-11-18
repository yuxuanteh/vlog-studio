r"""Stabilising worked out once, used at every size (the phone copy he approves must move
exactly like the 4K final; ffmpeg's vid.stab worked each size out on its own, so the two could differ).

analyse(frames)   frames at the analysis size (vlog_layout "edit") -> one correction per frame, in fractions of the
                  frame (dx, dy of width / height, angle in radians), so it means the same at 854, 1920 or 3840 wide.
apply(frame, c)   that correction at the frame's own size, with a fixed small zoom so no border shows.

How: corner features followed from frame to frame (optical flow), a rigid move (shift + turn) per step, the path
summed, smoothed over SMOOTH frames (vid.stab's smoothing=30), and each frame moved by smoothed - real. Steps whose
move cannot be measured (too few features) count as no move, never a guess, and are listed in the result.
"""
import cv2
import numpy as np

SMOOTH = 30          # frames each side looked at when smoothing the path (as vid.stab smoothing=30)
ZOOM = 1.06          # as vid.stab zoom=6: hides the moved edges
MAX_TURN = 0.008     # radians: within the zoom's room (vid.stab allowed 0.02 and filled edges from old frames)


def _gray(f):
    w = f.shape[1]
    g = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    return g if w <= 960 else cv2.resize(g, (960, round(f.shape[0] * 960 / w)), interpolation=cv2.INTER_AREA)


def analyse(frames):
    """[(dx, dy, da)] per frame in fractions of the frame; plus the list of steps that could not be measured."""
    n = len(frames)
    if n < 2:
        return [(0.0, 0.0, 0.0)] * n, []
    steps, blind = [(0.0, 0.0, 0.0)], []
    prev = _gray(frames[0])
    h, w = prev.shape
    for i in range(1, n):
        cur = _gray(frames[i])
        p0 = cv2.goodFeaturesToTrack(prev, 400, 0.01, 12)
        move = None
        if p0 is not None and len(p0) >= 12:
            p1, st, _ = cv2.calcOpticalFlowPyrLK(prev, cur, p0, None, winSize=(21, 21), maxLevel=3)
            good = st.reshape(-1) == 1
            if good.sum() >= 12:
                m, inl = cv2.estimateAffinePartial2D(p0[good], p1[good], method=cv2.RANSAC, ransacReprojThreshold=3)
                if m is not None and inl is not None and inl.sum() >= 10:
                    move = (m[0, 2] / w, m[1, 2] / h, float(np.arctan2(m[1, 0], m[0, 0])))
        if move is None:
            blind.append(i)
            move = (0.0, 0.0, 0.0)
        steps.append(move)
        prev = cur
    path = np.cumsum(np.array(steps), 0)
    k = np.ones(2 * SMOOTH + 1) / (2 * SMOOTH + 1)
    padded = np.pad(path, ((SMOOTH, SMOOTH), (0, 0)), mode="edge")
    smooth = np.stack([np.convolve(padded[:, j], k, mode="valid") for j in range(3)], 1)
    corr = smooth - path
    # never move further than the fixed zoom hides (a shaky phone shot showed mirrored copies at the edges):
    # the zoom leaves (zoom - 1) / (2 zoom) of the frame each side; a turn uses part of it
    room = (ZOOM - 1) / (2 * ZOOM)
    ang = np.clip(corr[:, 2], -MAX_TURN, MAX_TURN)
    corr[:, 2] = ang
    corr[:, 0] = np.clip(corr[:, 0], -(room - 0.6 * np.abs(ang)), room - 0.6 * np.abs(ang))
    corr[:, 1] = np.clip(corr[:, 1], -(room - np.abs(ang)), room - np.abs(ang))
    return [tuple(map(float, c)) for c in corr], blind


def matrix(c, W, H, zoom=ZOOM):
    dx, dy, da = c
    m = cv2.getRotationMatrix2D((W / 2, H / 2), np.degrees(da), zoom)
    m[0, 2] += dx * W * zoom
    m[1, 2] += dy * H * zoom
    return m


def apply(frame, c, zoom=ZOOM):
    H, W = frame.shape[:2]
    return cv2.warpAffine(frame, matrix(c, W, H, zoom), (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def map_points(pts, c, W, H, zoom=ZOOM):
    """Where points of the unsteadied frame land after apply() (for drawing on what was tracked before steadying)."""
    m = matrix(c, W, H, zoom)
    p = np.asarray(pts, np.float32).reshape(-1, 2)
    return (p @ m[:, :2].T + m[:, 2]).astype(np.float32)
