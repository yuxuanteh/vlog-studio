r"""Follow anything in a shot (QR codes today, other things later; the rules must be general).

Always on frames at the analysis size (vlog_layout "edit", 1920 wide or 1080 wide for 9:16), already steadied when
the shot is steadied, so the phone copy and the 4K final get the same result; positions come back as fractions of
the frame (four corners, x / W and y / H) and are drawn at any size.

    follow(frames, target)            -> Track
      target = {"qr": True}                     a QR code (OpenCV's readers + flow between readings)
               {"box": [x, y, w, h], "at": k}   anything else: a box in fractions on frame k (the director's
                                                 description, marked by Claude on a still they have approved)
    Track.quads[i]  4x2 corners in fractions, or None; Track.sure[i]  False where the methods disagree or lost it

Two methods per frame, never one alone: the main tracker (QR readers, or OpenCV's ViT tracker) and optical flow on
the object's own features. Where they disagree by more than half the object's size, or a reading jumps in size or
place against the frames round it, the frame is unsure. Short unsure runs between sure frames are bridged.

Then the effect's rule (vlog_track.rule), the director's Q3:
  "hide"   (blur a code, a face, a plate): any frame left unsure stops the build - shorten the shot, cover a bigger
           fixed area, or freeze - never a guess
  "point"  (an arrow, a label, a circle on something): unsure frames fade the drawing out, listed for the director
"""
import cv2
import numpy as np

import vlog_env

VIT = vlog_env.LOCAL / "models" / "opencv" / "object_tracking_vittrack_2023sep.onnx"
VIT_SHA256 = "2990f0b7cd44d92afa48cd97db6de7be113fc1d9594fddb74e2725c10478e91d"


class Track:
    def __init__(self, quads, sure, W, H, how, hide=False):
        self.raw = quads                                 # the tracked corners (angle and all)
        self.quads, self.sure, self.how = (upright_cover(quads) if hide else quads), sure, how
        self.W, self.H = W, H

    def raw_frac(self):
        return [None if q is None else (np.asarray(q, np.float32) / [self.W, self.H]).tolist() for q in self.raw]

    def frac(self):
        """Corners as fractions of the frame (None where nothing)."""
        return [None if q is None else (np.asarray(q, np.float32) / [self.W, self.H]).tolist() for q in self.quads]


# ---------------------------------------------------------------- shared checks
def upright_cover(quads):
    """For hiding, never trust a reading's angle (rehearsal: two readings of the teaser's code came out
    turned while the phone moved fast, and its corners showed past the blur): each frame is covered by an upright
    rectangle round its own corners and those of the frames either side."""
    out = []
    for i in range(len(quads)):
        near = [np.asarray(quads[j], np.float32) for j in (i - 1, i, i + 1)
                if 0 <= j < len(quads) and quads[j] is not None]
        if quads[i] is None or not near:
            out.append(None)
            continue
        pts = np.vstack(near)
        (x0, y0), (x1, y1) = pts.min(0), pts.max(0)
        out.append(box_quad(x0, y0, x1 - x0, y1 - y0))
    return out


def usable(q):
    if q is None:
        return False
    q = np.asarray(q, np.float32)
    sides = [np.hypot(*(q[k] - q[(k + 1) % 4])) for k in range(4)]
    return max(sides) >= 2 and min(sides) >= 0.2 * max(sides)


def plausible(quads, ok=None):
    """A reading whose size or place jumps away from the frames round it is wrong (a box a tenth the
    size, 350 px off): size against the usable readings within 8 frames, place against the 2 either side, one
    object-width allowed (a phone moving fast)."""
    ok = [usable(q) for q in quads] if ok is None else list(ok)
    area = [abs(cv2.contourArea(np.asarray(q, np.float32))) if g else 0.0 for q, g in zip(quads, ok)]
    cen = [np.asarray(q, np.float32).mean(0) if g else None for q, g in zip(quads, ok)]
    sure = list(ok)
    for i in range(len(quads)):
        if not ok[i]:
            continue
        near = [j for j in range(max(0, i - 8), min(len(quads), i + 9)) if ok[j]]
        ma = float(np.median([area[j] for j in near]))
        close = [j for j in near if abs(j - i) <= 2]
        mc = np.median(np.stack([cen[j] for j in close]), 0)
        if not (0.6 * ma <= area[i] <= 1.7 * ma) or np.hypot(*(cen[i] - mc)) > np.sqrt(ma):
            sure[i] = False
    return sure


def bridge(quads, sure, reach=10, cover=False):
    """Unsure frames between sure ones (at most `reach` apart) take the corners blended from both sides; at a shot's
    ends, the nearest sure frame within 3. Longer runs stay unsure. (reach 10 = 1/3 s: the v02 teaser's phone moved fast for
    7 frames between two sure readings; the cover is widened by the speed, vlog_track.hide_margin)"""
    out = [np.asarray(q, np.float32) if s else None for q, s in zip(quads, sure)]
    good = [i for i, s in enumerate(sure) if s]
    filled = list(sure)
    for i in range(len(quads)):
        if sure[i]:
            continue
        a = max((j for j in good if j < i), default=None)
        b = min((j for j in good if j > i), default=None)
        if a is not None and b is not None and b - a <= reach:
            if cover:                                   # hide: a rectangle round BOTH sure places - a blend can twist
                pts = np.vstack([out[a], out[b]])       # (rehearsal: the teaser's code corners showed at a
                (x0, y0), (x1, y1) = pts.min(0), pts.max(0)   # turned blend while the phone moved fast)
                out[i] = box_quad(x0, y0, x1 - x0, y1 - y0)
            else:
                w = (i - a) / (b - a)
                out[i] = (out[a] * (1 - w) + out[b] * w).astype(np.float32)
            filled[i] = True
        elif a is not None and b is None and i - a <= 3:
            out[i], filled[i] = out[a].copy(), True
        elif b is not None and a is None and b - i <= 3:
            out[i], filled[i] = out[b].copy(), True
    return out, filled


def box_quad(x, y, w, h):
    return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)


def flow_follow(fs, q0, k):
    """The object's own corner features followed by optical flow from frame k both ways; the box moves with their
    median shift and scale. Returns quads (None where too few features)."""
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in fs]
    out = [None] * len(fs)
    out[k] = np.asarray(q0, np.float32)
    for order in (range(k + 1, len(fs)), range(k - 1, -1, -1)):
        q, j = out[k], k
        for i in order:
            mask = np.zeros_like(grays[j])
            cv2.fillConvexPoly(mask, q.astype(np.int32), 255)
            p0 = cv2.goodFeaturesToTrack(grays[j], 200, 0.01, 3, mask=mask)
            if p0 is None or len(p0) < 6:
                break
            p1, st, _ = cv2.calcOpticalFlowPyrLK(grays[j], grays[i], p0, None, winSize=(31, 31), maxLevel=4)
            g = st.reshape(-1) == 1
            if g.sum() < 6:
                break
            m, inl = cv2.estimateAffinePartial2D(p0[g], p1[g], method=cv2.RANSAC, ransacReprojThreshold=3)
            if m is None:
                break
            q = (q @ m[:, :2].T + m[:, 2]).astype(np.float32)
            out[i], j = q, i
    return out


# ---------------------------------------------------------------- the main trackers
def vit_follow(fs, box, k):
    """OpenCV's ViT tracker from frame k both ways. Returns (quads, scores)."""
    import hashlib
    if not VIT.exists():
        raise SystemExit(f"tracker model missing: {VIT}")
    if hashlib.sha256(VIT.read_bytes()).hexdigest() != VIT_SHA256:
        raise SystemExit(f"tracker model changed on disk (sha256): {VIT}")
    quads, scores = [None] * len(fs), [0.0] * len(fs)
    quads[k], scores[k] = box_quad(*box), 1.0
    for order in (list(range(k, len(fs))), list(range(k, -1, -1))):
        p = cv2.TrackerVit_Params()
        p.net = str(VIT)
        t = cv2.TrackerVit_create(p)
        t.init(fs[order[0]], tuple(int(round(v)) for v in box))
        for i in order[1:]:
            ok, b = t.update(fs[i])
            sc = float(t.getTrackingScore())
            if ok and b[2] > 2 and b[3] > 2:
                quads[i], scores[i] = box_quad(*b), sc
    return quads, scores


def qr_follow(fs):
    import vlog_fx
    return vlog_fx.track_quads(fs)


def follow(fs, target):
    H, W = fs[0].shape[:2]
    if target.get("qr"):
        main = qr_follow(fs)
        sure = plausible(main)
        quads, filled = bridge(main, sure, cover=target.get("hide", True))
        return Track(quads, filled, W, H, "qr", hide=target.get("hide", True))
    k = int(target.get("at", 0))
    x, y, w, h = target["box"]
    box = (x * W, y * H, w * W, h * H)
    main, score = vit_follow(fs, box, k)
    flow = flow_follow(fs, box_quad(*box), k)
    ok = []
    for q, sc, fq in zip(main, score, flow):
        if q is None or sc < 0.3:
            ok.append(False)
            continue
        if fq is not None:                       # the two methods must agree within half the object's size
            size = np.sqrt(abs(cv2.contourArea(q)))
            if np.hypot(*(q.mean(0) - fq.mean(0))) > 0.5 * size:
                ok.append(False)
                continue
        ok.append(True)
    sure = plausible(main, ok)
    quads, filled = bridge(main, sure, cover=bool(target.get("hide")))
    return Track(quads, filled, W, H, "vit+flow", hide=bool(target.get("hide")))


def rule(track, how, what="the object"):
    """'hide' stops on any unsure frame; 'point' returns an opacity per frame (fading out round unsure ones)."""
    bad = [i for i, s in enumerate(track.sure) if not s]
    if how == "hide":
        if bad:
            raise SystemExit(f"TRACK UNSURE ({what}, hide): {len(bad)} of {len(track.sure)} frames "
                             f"{bad[:10]}{'...' if len(bad) > 10 else ''}; shorten the shot, cover a bigger fixed area "
                             f"or freeze - ask the director")
        return [1.0] * len(track.sure)
    alpha = np.array([1.0 if s else 0.0 for s in track.sure])
    for _ in range(4):                            # fade over ~4 frames either side
        alpha = np.minimum(alpha, np.convolve(np.pad(alpha, 1, mode="edge"), [0.5, 0.5, 0.5], "valid") / 1.0)
    if bad:
        print(f"TRACK note ({what}, point): faded on frames {bad[:12]}{'...' if len(bad) > 12 else ''}", flush=True)
    return alpha.clip(0, 1).tolist()


def hide_margin(quads, i, base=1.3):
    """How much bigger than the object a "hide" cover must be on frame i: the object's own speed (centre moving between
    the frames either side, against its size) widens it, so a fast move never leaves an edge out (the top row
    of the v02 QR code peeked out above the blur for 0.2 s while the phone moved up)."""
    q = quads[i]
    if q is None:
        return base
    q = np.float32(q)
    side = float(np.sqrt(abs(cv2.contourArea(q)))) or 1.0
    near = [np.float32(quads[j]).mean(0) for j in (i - 1, i + 1) if 0 <= j < len(quads) and quads[j] is not None]
    speed = max([float(np.hypot(*(c - q.mean(0)))) for c in near] or [0.0])
    return base + min(0.8, 2.5 * speed / side)

