"""Drawn elements that live inside real shots (level A: stuck to the scene by tracking). Our own designs.
Hand-drawn look: lines wobble a little and are redrawn 8 times a second, like animation drawn on top of the footage.
apply(name, src, out, W, H) is called by vlog_build.py for a picture marked "!name".
"""
import math
import random
import subprocess

import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

import vlog_env

HAND = str(vlog_env.LOCAL / "fonts" / "LXGWWenKai-Medium.ttf")
INK = (255, 112, 64, 255)          # warm orange-red ink
PAPER = (255, 248, 236, 235)


def frames(src):
    cap = cv2.VideoCapture(str(src))
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            return out
        out.append(f)


def writer(out, W, H):
    return subprocess.Popen([vlog_env.FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", "30",
                             "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", str(out)],
                            stdin=subprocess.PIPE)


def wobble_ellipse(cx, cy, rx, ry, seed, progress=1.0, n=64):
    rnd = random.Random(seed)
    pts = []
    turns = 1.08 * progress
    a0 = -2.4
    for i in range(int(n * turns) + 1):
        a = a0 + 2 * math.pi * i / n
        k = 1 + 0.035 * math.sin(3 * a + seed) + rnd.uniform(-0.012, 0.012)
        pts.append((cx + rx * k * math.cos(a), cy + ry * k * math.sin(a)))
    return pts


def hand_text(draw, xy, text, size, anchor="lm"):
    f = ImageFont.truetype(HAND, size)
    x, y = xy
    box = draw.textbbox((x, y), text, font=f, anchor=anchor)
    pad = size * 0.35
    draw.rounded_rectangle((box[0] - pad, box[1] - pad * 0.7, box[2] + pad, box[3] + pad * 0.7), radius=size * 0.3, fill=PAPER)
    draw.text((x, y), text, font=f, fill=(40, 34, 30, 255), anchor=anchor)


def track_points(fs, x, y, r):
    """Follow a spot in the scene with optical flow; returns its position in every frame."""
    g0 = cv2.cvtColor(fs[0], cv2.COLOR_BGR2GRAY)
    mask = np.zeros_like(g0)
    cv2.circle(mask, (int(x), int(y)), int(r), 255, -1)
    p0 = cv2.goodFeaturesToTrack(g0, 60, 0.01, 6, mask=mask)
    pos, cur = [(x, y)], np.array([x, y], float)
    for f in fs[1:]:
        g1 = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
        if p0 is not None and len(p0) >= 4:
            p1, st, _ = cv2.calcOpticalFlowPyrLK(g0, g1, p0, None, winSize=(31, 31), maxLevel=3)
            good = st.reshape(-1) == 1
            if good.sum() >= 4:
                cur = cur + np.median((p1 - p0).reshape(-1, 2)[good], 0)
                p0 = p1[good].reshape(-1, 1, 2)
        pos.append(tuple(cur))
        g0 = g1
    return pos


def jline(d, pts, seed, w, fill=(40, 34, 30, 255), amp=2.0):
    """A hand-drawn line: every point nudged a little, redrawn 8 times a second."""
    rnd = random.Random(seed)
    d.line([(x + rnd.uniform(-amp, amp), y + rnd.uniform(-amp, amp)) for x, y in pts], fill=fill, width=w, joint="curve")


def card_frames(fs, W, H, draw):
    """A paper card drawn over the footage, which stays visible behind it (blurred, darker)."""
    out = []
    n = len(fs)
    for i, f in enumerate(fs):
        t, u = i / 30, i / max(n - 1, 1)
        k = min(1.0, t / 0.5, (n - 1 - i) / 15 + 0.0001)
        bg = cv2.GaussianBlur(f, (0, 0), 18 * k + 0.1)
        bg = cv2.addWeighted(bg, 1 - 0.35 * k, np.zeros_like(bg), 0, 0)
        im = Image.fromarray(cv2.cvtColor(bg, cv2.COLOR_BGR2RGB)).convert("RGBA")
        if k > 0.05:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            d.rounded_rectangle((W * 0.12, H * 0.13, W * 0.88, H * 0.93), radius=H * 0.02, fill=(250, 245, 234, 240))
            draw(d, t, u, int(t * 8))
            small = layer.resize((int(W * 0.78), int(H * 0.78)), Image.LANCZOS)   # clear of the source note above, the subtitles below
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            layer.paste(small, (int(W * 0.11), int(H * 0.1086)))
            a = np.array(layer)
            a[..., 3] = (a[..., 3] * k).astype(np.uint8)
            im = Image.alpha_composite(im, Image.fromarray(a))
        out.append(cv2.cvtColor(np.array(im.convert("RGB")), cv2.COLOR_RGB2BGR))
    return out


def label(d, xy, text, size, fill=(40, 34, 30, 255), anchor="mm"):
    d.text(xy, text, font=ImageFont.truetype(HAND, size), fill=fill, anchor=anchor)


def cg_frames(name, fs, W, H, labels, start=None, fscale=1.0, portrait_at=None):
    """A shot rendered in Blender (scripts/cg/<name>.py, frames in <local>/cg/<name>/), dissolving in from the footage, with small labels pinned
    to the 3D points Blender saved for each frame. labels: (anchor, text, from, to, dx, dy); anchor None = fixed at (dx, dy) as fractions of the frame.
    In a 9:16 short the whole 16:9 diagram sits across the width, a little above the middle, over a blurred copy of itself."""
    portrait = vlog_env.LOCAL / "cg" / f"{name}-v"          # a real 9:16 render (no fitted 16:9 in shorts)
    if H > W and portrait.exists() and len(list(portrait.glob("*.jpg"))) >= len(list((vlog_env.LOCAL / "cg" / name).glob("*.jpg"))):
        return cg_frames(name + "-v", fs, W, H, labels, start, 30 * W / (22 * H), portrait_at)   # labels sized by the narrow width
    if H > W and not name.endswith("-v"):
        Hl = int(round(W * 9 / 16 / 2)) * 2
        land = cg_frames(name, [cv2.resize(f, (W, Hl), interpolation=cv2.INTER_AREA) for f in fs], W, Hl, labels, start, 1.5)
        out = []
        y0 = int(H * 0.40 - Hl / 2)
        for g in land:
            cw = int(H * 16 / 9)
            bg = cv2.resize(g, (cw, H), interpolation=cv2.INTER_LINEAR)[:, (cw - W) // 2:(cw - W) // 2 + W]
            bg = (cv2.GaussianBlur(bg, (0, 0), 30) * 0.5).astype(np.uint8)
            bg[y0:y0 + Hl] = g
            out.append(bg)
        return out
    src = vlog_env.LOCAL / "cg" / name
    last = len(list(src.glob("*.jpg"))) - 1
    size = max(18, int(H // 30 * fscale))
    font = ImageFont.truetype(str(vlog_env.LOCAL / "fonts" / "NotoSansSC-Medium.ttf"), size)
    out = []
    n = len(fs)
    sf = int(round(start * 30)) if start is not None else 0   # a held end goes on from the frame where the line ended
    for i, f in enumerate(fs):
        k = min(sf + i, last)
        g = cv2.resize(cv2.imread(str(src / f"{k:05d}.jpg")), (W, H), interpolation=cv2.INTER_LANCZOS4)
        past = sf + i - last
        if past > 0:                                       # the animation is over: hold its last frame, slowly pushed in
            z = 1 + 0.05 * min(1.0, past / 120)
            g = cv2.warpAffine(g, np.float32([[z, 0, W / 2 * (1 - z)], [0, z, H / 2 * (1 - z)]]), (W, H), flags=cv2.INTER_LINEAR)
        anchors = json.loads((src / f"{k:05d}.json").read_text())
        t = (sf + i) / 30
        im = Image.fromarray(cv2.cvtColor(g, cv2.COLOR_BGR2RGB)).convert("RGBA")
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        placed = []                                        # boxes already drawn this frame: a label never covers another
        for anchor, text, t0, t1, dx, dy in labels:
            if H > W and anchor in (portrait_at or {}):   # portrait: some labels sit on the other side so lines don't cross
                dx, dy = portrait_at[anchor]
            a = min(1.0, max(0.0, (t - t0) / 0.3), max(0.0, (t1 - t) / 0.3))
            if a <= 0:
                continue
            al = int(255 * a)
            if anchor is None:
                x, y = W * dx, H * dy
                px, py = None, None
            else:
                px, py = anchors[anchor][0] * W, min(anchors[anchor][1] * H, H * 0.8)
                x, y = px + W * dx, min(py + H * dy, H * 0.78)
            l, tp, r, bt = d.textbbox((x, y), text, font=font, anchor="mm")
            m = size * 0.45
            box = [max(l - m, W * 0.02), max(tp - m * 0.7, H * 0.03), 0, 0]
            box[2], box[3] = box[0] + (r - l) + 2 * m, box[1] + (bt - tp) + 1.4 * m
            if box[2] > W * 0.98:                          # keep inside the frame (portrait is narrow)
                box[0], box[2] = box[0] - (box[2] - W * 0.98), W * 0.98
            for q in placed:                               # overlapping an earlier label: move below it (if box[0] < q[2] and box[2] > q[0] and box[1] < q[3] and box[3] > q[1]:   # 水平约4米 sat on 上下约6米)
                    hgt = box[3] - box[1]
                    box[1] = q[3] + m * 0.6
                    box[3] = box[1] + hgt
            placed.append(list(box))
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            if px is not None:
                d.line([(cx, cy), (px, py)], fill=(255, 255, 255, al), width=max(2, H // 400))
                rr = max(3, H // 180)
                d.ellipse((px - rr, py - rr, px + rr, py + rr), fill=(255, 255, 255, al))
            d.rounded_rectangle(box, radius=size * 0.3, fill=(28, 26, 24, int(205 * a)))
            d.text((cx, cy), text, font=font, fill=(250, 247, 240, al), anchor="mm")
        g = cv2.cvtColor(np.array(Image.alpha_composite(im, layer).convert("RGB")), cv2.COLOR_RGB2BGR)
        w = 1.0 if start is not None else min(1.0, i / 12)   # dissolve in only; the cut out is clean
        out.append(cv2.addWeighted(g, w, f, 1 - w, 0) if w < 1 else g)
    return out


def fx_toptight(fs, W, H):
    """Keep only the top 72 % of the frame (centred), enlarged back to full size: hides faces in the lower part."""
    out = []
    for f in fs:
        h, w = f.shape[:2]
        ch, cw = int(h * 0.72), int(w * 0.72)
        x0 = (w - cw) // 2
        out.append(cv2.resize(f[0:ch, x0:x0 + cw], (W, H), interpolation=cv2.INTER_CUBIC))
    return out


def fx_dim(fs, W, H):
    """End card background: the footage softened and darkened so the credits read."""
    return [cv2.addWeighted(cv2.GaussianBlur(f, (0, 0), 6), 0.55, np.zeros_like(f), 0, 0) for f in fs]


def red_banner(f, near=None, last_area=None):
    """The ticket's red header: (centre, (w, h), angle) of the red patch nearest where it was, or None when the
    nearest red patch is not it (a jump in size: the gate's red body)."""
    hsv = cv2.cvtColor(f, cv2.COLOR_BGR2HSV)
    m = cv2.inRange(hsv, (0, 120, 90), (10, 255, 255)) | cv2.inRange(hsv, (170, 120, 90), (180, 255, 255))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    n, lab, st, cen = cv2.connectedComponentsWithStats(m)
    best = None
    for k in range(1, n):
        if st[k, 4] < 3000:
            continue
        score = st[k, 4] - (0 if near is None else 30 * np.hypot(*(cen[k] - near)))
        if best is None or score > best[0]:
            best = (score, k)
    if best is None:
        return None
    ys, xs = np.where(lab == best[1])
    rect = cv2.minAreaRect(np.column_stack([xs, ys]).astype(np.float32))
    area = rect[1][0] * rect[1][1]
    if last_area and not 0.6 < area / last_area < 1.6:
        return None
    return rect


def banner_frame(rect):
    """Banner axes: centre, unit vector along its long side (left to right) and across it (downwards), and its size."""
    (cx, cy), (w, h), a = rect
    if w < h:
        w, h, a = h, w, a + 90
    ux = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
    if ux[0] < 0:
        ux = -ux
    uy = np.array([-ux[1], ux[0]])
    if uy[1] < 0:
        uy = -uy
    return np.array([cx, cy]), ux, uy, w, h


def track_quads(fs):
    """The QR's four corners in every frame. Read where the code reads (the ArUco-based detector reads nearly every
    frame of a steady phone); in between, carried from the nearest reading by optical flow on the code itself
    (features inside the code only, so the floor and the hand can't pull it), forwards and backwards, blended by
    distance. Director follow it frame by frame."""
    dets = []
    det = cv2.QRCodeDetectorAruco() if hasattr(cv2, "QRCodeDetectorAruco") else cv2.QRCodeDetector()
    # never read on frames smaller than the edit size (1920 wide): at 854x480 the code never reads. Tracked effects are
    # rendered at the edit size anyway (vlog_build.TRACKED_FX); reading at 2x did not help (tested)
    up = max(1.0, 1920 / fs[0].shape[1])
    # two readers: the ArUco-based one reads most shots, the classic one reads the stabilised + graded v02 "qr" piece
    # where ArUco reads nothing (0 vs 7 of 127 frames); each frame takes whichever reads
    readers = [det] + ([cv2.QRCodeDetector()] if hasattr(cv2, "QRCodeDetectorAruco") else [])
    for f in fs:
        g = cv2.resize(f, None, fx=up, fy=up, interpolation=cv2.INTER_CUBIC) if up > 1 else f
        found = None
        for r in readers:
            ok, pts = r.detect(g)
            if ok and pts is not None and len(pts.reshape(-1, 2)) == 4:
                found = (pts.reshape(-1, 2) / up).astype(np.float32)
                break
        dets.append(found)
    area = lambda q: abs(cv2.contourArea(np.asarray(q, np.float32)))
    good = [q for q in dets if q is not None]
    if not good:
        raise SystemExit("qr: the code never reads in this shot")
    med = float(np.median([area(q) for q in good]))
    dets = [q if q is not None and 0.4 * med < area(q) < 2.5 * med else None for q in dets]
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in fs]

    def carry(order):
        banner_seen = sum(r is not None for r in rects) > 0.3 * len(fs)
        gone = [False] * len(fs)                         # 5+ frames in a row without the banner: the phone turned away
        k = 0
        while k < len(fs):
            if rects[k] is None:
                e = k
                while e < len(fs) and rects[e] is None:
                    e += 1
                if e - k >= 5:
                    gone[k:e] = [True] * (e - k)
                k = e
            else:
                k += 1
        res, quad = {}, None
        for k, i in enumerate(order):
            if dets[i] is not None:
                quad = dets[i].copy()
            elif quad is not None and banner_seen and gone[i]:
                quad = None                                  # the ticket's banner is gone: the phone turned away
            elif quad is not None:
                j = order[k - 1]
                c = quad.mean(0)
                mask = np.zeros_like(grays[j])
                poly = ((quad - c) * 1.2 + c)
                r = rects[j]
                if r is not None and np.hypot(*(np.array(r[0]) - c)) < 3 * np.ptp(quad[:, 0]):   # the ticket's banner: same flat screen
                    poly = np.vstack([poly, cv2.boxPoints(r)])
                cv2.fillConvexPoly(mask, cv2.convexHull(poly.astype(np.float32)).astype(np.int32), 255)
                p0 = cv2.goodFeaturesToTrack(grays[j], 300, 0.005, 3, mask=mask)
                if p0 is not None and len(p0) >= 6:
                    p1, st, _ = cv2.calcOpticalFlowPyrLK(grays[j], grays[i], p0, None, winSize=(41, 41), maxLevel=5)
                    ok = st.reshape(-1) == 1
                    if ok.sum() >= 6:
                        Hm, _ = cv2.findHomography(p0[ok], p1[ok], cv2.RANSAC, 3.0)
                        if Hm is not None:
                            quad = cv2.perspectiveTransform(quad.reshape(-1, 1, 2), Hm).reshape(-1, 2)
            res[i] = None if quad is None else quad.copy()
        return res

    # the red banner: in shots where the code rarely reads (a moving phone, motion blur), place the code from it
    rects, near, la = [], None, None
    for f in fs:
        r = red_banner(f, near, la)
        rects.append(r)
        if r is not None:
            near, la = np.array(r[0]), r[1][0] * r[1][1]
    fwd, bwd = carry(list(range(len(fs)))), carry(list(range(len(fs)))[::-1])
    di = [i for i, q in enumerate(dets) if q is not None]
    quads = []
    for i in range(len(fs)):
        a, b = fwd[i], bwd[i]
        if a is None or b is None:
            quads.append(a if a is not None else b)
            continue
        prev = max([x for x in di if x <= i], default=None)
        nxt = min([x for x in di if x >= i], default=None)
        if prev is None or nxt is None or nxt == prev:
            quads.append(a if prev is not None else b)
            continue
        w = (i - prev) / (nxt - prev)
        quads.append((1 - w) * a + w * b)
    for i, q_ in enumerate(quads):                           # a carried quad that blew up or folded: the code is gone
        if q_ is not None and (not cv2.isContourConvex(np.int32(q_)) or area(q_) > 2.5 * med):
            quads[i] = np.zeros((4, 2), np.float32)
    quads = [np.zeros((4, 2), np.float32) if q_ is None else q_ for q_ in quads]
    q = np.stack(quads)                                      # light smoothing: 3 frames, so detector jitter doesn't shake
    sm = q.copy()
    sm[1:-1] = (q[:-2] + q[1:-1] + q[2:]) / 3
    return list(sm)


def pixelate_quad(f, q, W, H, margin=1.3):
    """Pixelate the code and a margin round it, in its own perspective."""
    c = q.mean(0)
    q = (q - c) * margin + c
    x0, y0 = np.floor(q.min(0)).astype(int)
    x1, y1 = np.ceil(q.max(0)).astype(int)
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return f
    roi = f[y0:y1, x0:x1]
    tiny = cv2.resize(roi, (7, 7), interpolation=cv2.INTER_AREA)
    pix = cv2.resize(tiny, (roi.shape[1], roi.shape[0]), interpolation=cv2.INTER_NEAREST)
    mask = np.zeros(roi.shape[:2], np.uint8)
    cv2.fillConvexPoly(mask, (q - [x0, y0]).astype(np.int32), 255)
    roi[mask > 0] = pix[mask > 0]
    return f


def analyse_qr(fs, arg=None):
    """Tracked effect "qr": a QR code to hide. Followed on the analysis frames (vlog_track, QR readers + flow), rule
    "hide": any frame it is unsure of stops the build (the v02 4K final blurred only the first 0.4 s)."""
    import vlog_track
    tr = vlog_track.follow(fs, {"qr": True})
    vlog_track.rule(tr, "hide", "QR code")
    return {"quads": tr.frac()}


def draw_qr(f, i, data, W, H, arg=None):
    import vlog_track
    q = data["quads"][i]
    if q is None:
        return f
    return pixelate_quad(f, (np.float32(q) * [W, H]).astype(np.float32), W, H, margin=vlog_track.hide_margin(data["quads"], i))


def analyse_faces(fs, arg=None):
    """Tracked effect "faces": every face in the shot, to hide (strangers are blurred). OpenCV's
    YuNet finder on every analysis frame; each frame takes the faces found 2 frames either side, and a frame the finder
    misses borrows the nearest frame's within 12 frames. A face the finder never sees cannot be hidden: the effects sheet is checked by eye."""
    import vlog_faces
    fd = vlog_faces.finder()
    fd.setScoreThreshold(0.6)
    boxes = []
    for f in fs:
        h, w = f.shape[:2]
        fd.setInputSize((w, h))
        _, faces = fd.detect(f)
        boxes.append([[float(x / w), float(y / h), float(bw / w), float(bh / h)] for x, y, bw, bh in
                      (faces[:, :4] if faces is not None else [])])
    # a face the finder only sees for part of its time on screen (v02 C0491: a woman looking down at her
    # phone, found only once she lifted her head): from the first and last frame of each run of readings, the face is
    # followed by the ViT tracker back / forward (up to 1.5 s) while it is sure, and those frames get it too
    import vlog_track
    h0, w0 = fs[0].shape[:2]
    extra = [[] for _ in boxes]
    runs, i = [], 0
    while i < len(boxes):
        if boxes[i]:
            j = i
            while j + 1 < len(boxes) and boxes[j + 1]:
                j += 1
            runs.append((i, j))
            i = j + 1
        else:
            i += 1
    for a_, b_ in runs:
        for k, step in ((a_, -1), (b_, 1)):
            lo, hi = (max(0, k - 45), k + 1) if step < 0 else (k, min(len(fs), k + 46))
            if hi - lo < 3:
                continue
            seg = fs[lo:hi]
            for x, y, bw, bh in boxes[k]:
                try:
                    quads, scores = vlog_track.vit_follow(seg, (x * w0, y * h0, bw * w0, bh * h0), k - lo)
                except SystemExit:
                    continue
                for n, (q, sc) in enumerate(zip(quads, scores)):
                    if q is not None and sc >= 0.35 and n != k - lo:
                        qx, qy = q.min(0)
                        qw, qh = q.max(0) - q.min(0)
                        extra[lo + n].append([float(qx / w0), float(qy / h0), float(qw / w0), float(qh / h0)])
    boxes = [b + e for b, e in zip(boxes, extra)]
    # its own readings and those 2 frames either side (steady); a frame with none borrows the nearest frame that has
    # some, up to 12 frames away (0.4 s) - never every reading of 0.4 s, which smeared a trail along a walking man
    near = []
    for i in range(len(boxes)):
        own = sum(boxes[max(0, i - 2):i + 3], [])
        if not own:
            k = min((j for j in range(max(0, i - 12), min(len(boxes), i + 13)) if boxes[j]), key=lambda j: abs(j - i), default=None)
            own = boxes[k] if k is not None else []
        near.append(own)
    return {"boxes": near}


def draw_faces(f, i, data, W, H, arg=None):
    for x, y, bw, bh in data["boxes"][i]:
        cx, cy = (x + bw / 2) * W, (y + bh / 2) * H
        r = max(bw * W, bh * H) * 0.9                    # the head, a margin round the face
        x0, x1 = int(max(0, cx - r)), int(min(W, cx + r))
        y0, y1 = int(max(0, cy - r * 1.2)), int(min(H, cy + r))
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        roi = f[y0:y1, x0:x1]
        tiny = cv2.resize(roi, (6, 6), interpolation=cv2.INTER_AREA)
        f[y0:y1, x0:x1] = cv2.GaussianBlur(cv2.resize(tiny, (x1 - x0, y1 - y0), interpolation=cv2.INTER_NEAREST), (0, 0), 3)
    return f


def fx_qr(fs, W, H):
    """The same on a list of frames already at their size (tests, and any caller without the build)."""
    data = analyse_qr(fs)
    return [draw_qr(f, i, data, W, H) for i, f in enumerate(fs)]


def usable(q):
    if q is None:
        return False
    sides = [np.hypot(*(q[k] - q[(k + 1) % 4])) for k in range(4)]
    return max(sides) >= 2 and min(sides) >= 0.2 * max(sides)


def fill_gaps(quads, reach=6):
    """A frame or a few whose reading is bad (a squashed quad, nothing) between good ones get the corners blended from
    the good frames either side; at the shot's ends they take the nearest good one within 3 frames (two
    frames of the v02 QR were left sharp). A longer gap is a phone turned away: left alone."""
    ok = [usable(q) for q in quads]
    # a reading whose size or place jumps away from the frames round it is wrong too (frames 2-5 of the v02
    # QR read a box a tenth the size, 350 px off): size against the usable readings within 8 frames
    area = [abs(cv2.contourArea(np.asarray(q, np.float32))) if g else 0.0 for q, g in zip(quads, ok)]
    cen = [np.asarray(q, np.float32).mean(0) if g else None for q, g in zip(quads, ok)]
    sure = list(ok)
    for i in range(len(quads)):
        if not ok[i]:
            continue
        near = [j for j in range(max(0, i - 8), min(len(quads), i + 9)) if ok[j]]
        ma = float(np.median([area[j] for j in near]))
        close = [j for j in near if abs(j - i) <= 2]       # place: against the frames right next to it (a phone moving
        mc = np.median(np.stack([cen[j] for j in close]), 0)   # fast moves a lot in 8 frames), one code-width allowed
        if not (0.6 * ma <= area[i] <= 1.7 * ma) or np.hypot(*(cen[i] - mc)) > np.sqrt(ma):
            sure[i] = False
    ok = sure
    out = [np.asarray(q, np.float32) if g else None for q, g in zip(quads, ok)]
    good = [i for i, g in enumerate(ok) if g]
    for i in range(len(quads)):
        if ok[i]:
            continue
        a = max((j for j in good if j < i), default=None)
        b = min((j for j in good if j > i), default=None)
        if a is not None and b is not None and b - a <= reach:
            w = (i - a) / (b - a)
            out[i] = (out[a] * (1 - w) + out[b] * w).astype(np.float32)
        elif a is not None and i - a <= 3 and b is None:
            out[i] = out[a].copy()
        elif b is not None and b - i <= 3 and a is None:
            out[i] = out[b].copy()
    return out


_MAPS = {}


def _maps():
    if not _MAPS:
        src = vlog_env.LOCAL / "cg" / "map"
        for n in ("wide", "japan", "malaysia"):
            _MAPS[n] = (cv2.imread(str(src / f"{n}.png")), json.loads((src / f"{n}.json").read_text()))
    return _MAPS


def _ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _view(keys, t):
    """keys: (time, lon, lat, width in degrees); centre eased, width eased in log so the zoom feels even."""
    if t <= keys[0][0]:
        return keys[0][1:]
    for (t0, x0, y0, w0), (t1, x1, y1, w1) in zip(keys, keys[1:]):
        if t <= t1:
            p = _ease((t - t0) / (t1 - t0))
            return x0 + (x1 - x0) * p, y0 + (y1 - y0) * p, math.exp(math.log(w0) + (math.log(w1) - math.log(w0)) * p)
    return keys[-1][1:]


def _mapframe(lon, lat, wdeg, W, H):
    """Crop the sharpest base map that holds the whole view."""
    hdeg = wdeg * H / W
    best = None
    for n, (im, ext) in _maps().items():
        (a, b), (c, d) = ext["lon"], ext["lat"]
        if lon - wdeg / 2 >= a and lon + wdeg / 2 <= b and lat - hdeg / 2 >= c and lat + hdeg / 2 <= d:
            ppd = im.shape[1] / (b - a)
            if best is None or ppd > best[0]:
                best = (ppd, im, ext)
    ppd, im, ext = best or (None, *_maps()["wide"])
    a, b = ext["lon"]
    c, d = ext["lat"]
    ppd = im.shape[1] / (b - a)
    x0, y0 = (lon - wdeg / 2 - a) * ppd, (d - (lat + hdeg / 2)) * ppd
    M = np.float32([[W / (wdeg * ppd), 0, -x0 * W / (wdeg * ppd)], [0, H / (hdeg * ppd), -y0 * H / (hdeg * ppd)]])
    g = cv2.warpAffine(im, M, (W, H), flags=cv2.INTER_AREA if wdeg * ppd > W else cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

    def px(p):
        return (p[0] - (lon - wdeg / 2)) / wdeg * W, ((lat + hdeg / 2) - p[1]) / hdeg * H
    return g, px


def _pins(g, px, pins, t, W, H):
    """pins: (lon/lat, label, from, colour[, side]); a dot that pulses once, a label box beside it (side "r" or "l")."""
    im = Image.fromarray(cv2.cvtColor(g, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = max(14, H // 36)
    font = ImageFont.truetype(str(vlog_env.LOCAL / "fonts" / "NotoSansSC-Medium.ttf"), size)
    for pin in pins:
        p, text, t0, col = pin[:4]
        side = pin[4] if len(pin) > 4 else None
        a = min(1.0, max(0.0, (t - t0) / 0.4))
        if a <= 0:
            continue
        x, y = px(p)
        r = H / 90
        ring = (t - t0) % 2.0
        if ring < 1.2:
            rr = r * (1 + 3 * ring)
            d.ellipse((x - rr, y - rr, x + rr, y + rr), outline=col + (int(200 * a * (1 - ring / 1.2)),), width=max(2, H // 300))
        d.ellipse((x - r, y - r, x + r, y + r), fill=col + (int(255 * a),), outline=(255, 255, 255, int(255 * a)), width=max(2, H // 400))
        if text:
            right = side == "r" if side else x < W * 0.62
            tx = x + r * 2.2 if right else x - r * 2.2
            l, tp, rt, bt = d.textbbox((tx, y), text, font=font, anchor="lm" if right else "rm")
            m = size * 0.4
            d.rounded_rectangle((l - m, tp - m * 0.6, rt + m, bt + m * 0.6), radius=size * 0.3, fill=(28, 26, 24, int(215 * a)))
            d.text((tx, y), text, font=font, fill=(250, 247, 240, int(255 * a)), anchor="lm" if right else "rm")
    return cv2.cvtColor(np.array(Image.alpha_composite(im, layer).convert("RGB")), cv2.COLOR_RGB2BGR)


def _names(g, px, names, W, H):
    im = Image.fromarray(cv2.cvtColor(g, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(im)
    font = ImageFont.truetype(str(vlog_env.LOCAL / "fonts" / "NotoSansSC-Medium.ttf"), max(16, H // 34))
    for p, text in names:
        x, y = px(p)
        if -W * 0.1 < x < W * 1.1 and -H * 0.1 < y < H * 1.1:
            d.text((x, y), text, font=font, fill=(120, 108, 90), anchor="mm")
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


RED, BLUE = (200, 70, 50), (40, 110, 190)


def _label(g, xy, text, W, H, size=None, box=True):
    im = Image.fromarray(cv2.cvtColor(g, cv2.COLOR_BGR2RGB)).convert("RGBA")
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    size = size or max(16, H // 30)
    font = ImageFont.truetype(str(vlog_env.LOCAL / "fonts" / "NotoSansSC-Bold.ttf"), size)
    x, y = xy
    if box:
        l, tp, rt, bt = d.textbbox((x, y), text, font=font, anchor="mm")
        m = size * 0.4
        d.rounded_rectangle((l - m, tp - m * 0.6, rt + m, bt + m * 0.6), radius=size * 0.3, fill=(28, 26, 24, 200))
    else:
        d.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 150), anchor="mm")
    d.text((x, y), text, font=font, fill=(255, 255, 255, 255), anchor="mm")
    return cv2.cvtColor(np.array(Image.alpha_composite(im, layer).convert("RGB")), cv2.COLOR_RGB2BGR)


def fx_black(fs, W, H):
    """Plain black, for the end screen."""
    return [np.zeros_like(f) for f in fs]


_TRIP_FX = {}


def trip_module(trip_dir):
    """The trip's own effects, <trip>/work/fx.py (effects written for one shot live with the trip)."""
    import importlib.util
    if trip_dir is None:
        return None
    f = Path(trip_dir) / "work" / "fx.py"
    if not f.exists():
        return None
    key = (str(f), f.stat().st_mtime)
    if key not in _TRIP_FX:
        spec = importlib.util.spec_from_file_location(f"trip_fx_{Path(trip_dir).name.replace('-', '_')}", f)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _TRIP_FX[key] = mod
    return _TRIP_FX[key]


def _named(prefix, trip_dir):
    out = {k[len(prefix):]: v for k, v in globals().items() if k.startswith(prefix) and callable(v)}
    mod = trip_module(trip_dir)
    if mod is not None:
        for k, v in vars(mod).items():
            if k.startswith(prefix) and callable(v) and getattr(v, "__module__", "") == mod.__name__:
                if k[len(prefix):] in out and out[k[len(prefix):]] is not v:
                    raise SystemExit(f"fx: the trip's {k} has the same name as a shared effect")
                out[k[len(prefix):]] = v
    return out


def table(trip_dir=None):
    """Every effect by name: fx_<name> (frames in, frames out) and tracked ones (analyse_<name> + draw_<name>)."""
    t = _named("fx_", trip_dir)
    for n in tracked(trip_dir):
        t.setdefault(n, None)
    return t


def tracked(trip_dir=None):
    """{name: (analyse, draw)}: effects that look at the picture. vlog_build analyses them once on the analysis-size
    frames (steadied first if the shot is steadied) and draws them at every output size from the same data."""
    an, dr = _named("analyse_", trip_dir), _named("draw_", trip_dir)
    return {n: (an[n], dr[n]) for n in an if n in dr}


def code_hash(trip_dir=None):
    """Pieces made with an effect, steadying or tracking are keyed on this code (and the trip's fx.py)."""
    import hashlib
    h = hashlib.md5()
    here = Path(__file__).parent
    for f in ("vlog_fx.py", "vlog_track.py", "vlog_stab.py"):
        h.update((here / f).read_bytes())
    if trip_dir is not None and (Path(trip_dir) / "work" / "fx.py").exists():
        h.update((Path(trip_dir) / "work" / "fx.py").read_bytes())
    return h.hexdigest()[:10]


def apply(name, src, out, W, H, trip_dir=None):
    name, _, arg = name.partition(":")                 # "slipend:7.23" = an effect with its argument
    fs = frames(src)
    # every fx_<name> function is an effect; the table is built from them (a hand-typed table had no
    # earth1 / earth2, so v01 would have crashed on its map)
    tab = _named("fx_", trip_dir)
    if name not in tab:
        raise SystemExit(f"fx: no effect called {name!r}; known: {', '.join(sorted(table(trip_dir)))}")
    res = tab[name](fs, W, H, *([arg] if arg else []))
    del fs                                             # 4K frames are 25 MB each: never hold the shot twice longer than
    res = list(res)                                    # needed, and free each frame once it is written
    p = writer(out, W, H)                              # (MemoryError on a 4K effect shot)
    for i in range(len(res)):
        p.stdin.write(res[i].tobytes())
        res[i] = None
    p.stdin.close()
    p.wait()
