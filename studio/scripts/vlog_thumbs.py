r"""Thumbnails and Reel covers for trip videos (style set with the director:
the cheap-looking first drafts had a tilted instant photo and a ticket stub; now the director is cut out).

Tools:
    python vlog_thumbs.py <trip> grab C0394:15.2 C0287:46 ...   4K stills from raw/ -> work/thumbs/src/<stem>-<t>.png
    python vlog_thumbs.py <trip> cut src/C0394-15.2.png ...      cut the director out (BiRefNet) -> work/thumbs/cut/<name>.png
    python vlog_thumbs.py <trip> check                           sizes and file limits of everything in work/thumbs/out
Designs live with the trip, in work/thumbs/layout.py: `from vlog_thumbs import *`, `use("<trip>")`, then one block per
picture ending in save(im, name). Pick frames from mosaics / proxies, never by guessing a time (a tile's time can be off
by a second; pull and look).

Look: one real place, graded punchy and softly blurred behind the subject; the director cut out large with a white
outline, a soft shadow and a faint warm rim; 2-4 words in Noto Sans SC Black (white, thick black stroke, key word
yellow); one hand-drawn blue mark. Long videos 1280x720; Reel covers 1080x1920 with everything inside the centre
1080x1350 (Instagram's 3:4 grid crop) and text >= 80 px.
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

import sys

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env  # noqa: E402
import vlog_layout  # noqa: E402

SRC = CUT = OUT = None
BLACK = str(vlog_env.FONT_DIR / vlog_layout.FONT_FILE["bold"])   # the heaviest font the studio has


def use(trip):
    """Point the tools at a trip's work/thumbs folders."""
    global SRC, CUT, OUT
    base = vlog_env.TRIPS / trip / "work" / "thumbs"
    SRC, CUT, OUT = base / "src", base / "cut", base / "out"
    for d in (SRC, CUT, OUT):
        d.mkdir(parents=True, exist_ok=True)
BLUE, YELLOW, INK = (40, 120, 255), (255, 214, 0), (12, 10, 8)


# ---------------------------------------------------------------- picture
def cover(img, W, H, cx=0.5, cy=0.5, zoom=1.0):
    s = max(W / img.width, H / img.height) * zoom
    im = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x, y = round((im.width - W) * cx), round((im.height - H) * cy)
    return im.crop((x, y, x + W, y + H))


def grade(im, contrast=1.15, sat=1.25, bright=1.0, blur=0, vignette=0.55):
    im = ImageEnhance.Contrast(im.convert("RGB")).enhance(contrast)
    im = ImageEnhance.Color(im).enhance(sat)
    im = ImageEnhance.Brightness(im).enhance(bright)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur))
    W, H = im.size
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).ellipse((-W * 0.2, -H * 0.25, W * 1.2, H * 1.25), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(W // 7))
    return Image.composite(im, ImageEnhance.Brightness(im).enhance(1 - vignette), m).convert("RGBA")


def subject(base, name, height, anchor, outline=9, rim=(255, 236, 200), crop_bottom=0.0, crop=None):
    """Paste a cut-out: scaled to `height` px, bottom-centre at `anchor` (x, y); white outline, shadow, warm rim."""
    cut = Image.open(CUT / f"{name}.png").convert("RGBA")
    if crop:                                          # (x0, y0, x1, y1) as fractions of the cut-out
        cut = cut.crop((round(crop[0] * cut.width), round(crop[1] * cut.height), round(crop[2] * cut.width), round(crop[3] * cut.height)))
    if crop_bottom:
        cut = cut.crop((0, 0, cut.width, round(cut.height * (1 - crop_bottom))))
    s = height / cut.height
    cut = cut.resize((round(cut.width * s), round(cut.height * s)), Image.LANCZOS)
    cut = ImageEnhance.Contrast(cut).enhance(1.08)
    cut = cut.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    a = cut.getchannel("A")
    x, y = round(anchor[0] - cut.width / 2), round(anchor[1] - cut.height)
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    big = Image.new("L", base.size, 0)
    big.paste(a, (x, y))
    sh = big.filter(ImageFilter.GaussianBlur(22)).point(lambda v: v * 0.75)
    base = Image.alpha_composite(base, Image.merge("RGBA", (*[Image.new("L", base.size, 0)] * 3, sh)))
    ring = big.filter(ImageFilter.MaxFilter(outline * 2 + 1))
    glow = ring.filter(ImageFilter.GaussianBlur(outline * 2)).point(lambda v: v * 0.55)
    base = Image.alpha_composite(base, Image.merge("RGBA", (*[Image.new("L", base.size, 255)] * 3, glow)))
    base = Image.alpha_composite(base, Image.merge("RGBA", (*[Image.new("L", base.size, 255)] * 3, ring)))
    # warm rim on the subject's edge (a light from behind)
    inner = ImageChops.subtract(a, a.filter(ImageFilter.MinFilter(9))).filter(ImageFilter.GaussianBlur(3))
    rimmed = Image.composite(Image.new("RGBA", cut.size, rim + (255,)), cut, inner.point(lambda v: v * 0.45))
    rimmed.putalpha(a)
    lay.paste(rimmed, (x, y), rimmed)
    return Image.alpha_composite(base, lay)


# ---------------------------------------------------------------- type and marks
def words(base, lines, xy, size, anchor="l", hl="", stroke=None, rot=0, box_hl=False):
    """Heavy white words with a black stroke and shadow; characters in `hl` are yellow (or on a yellow box)."""
    font = ImageFont.truetype(BLACK, size)
    stroke = stroke or max(8, size // 7)
    W, H = base.size
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(lay), ImageDraw.Draw(sh)
    x0, y = xy
    for line in lines:
        w = d.textlength(line, font=font)
        x = {"l": x0, "m": x0 - w / 2, "r": x0 - w}[anchor]
        ds.text((x + size * 0.04, y + size * 0.08), line, font=font, fill=(0, 0, 0, 200), stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        cx = x
        for ch in line:
            cw = d.textlength(ch, font=font)
            if ch in hl and box_hl:
                d.rectangle((cx - 4, y + size * 0.12, cx + cw + 4, y + size * 1.18), fill=YELLOW + (255,))
                d.text((cx, y), ch, font=font, fill=INK)
            else:
                d.text((cx, y), ch, font=font, fill=YELLOW if ch in hl else (255, 255, 255), stroke_width=stroke, stroke_fill=INK)
            cx += cw
        y += size * 1.08
    sh = sh.filter(ImageFilter.GaussianBlur(size // 10))
    out = Image.alpha_composite(sh, lay)
    if rot:
        out = out.rotate(rot, resample=Image.BICUBIC, center=xy)
    return Image.alpha_composite(base, out)


def _stroke_path(base, pts, width, heads=()):
    lay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    for col, wd in (((255, 255, 255, 255), width + 12), (BLUE + (255,), width)):
        d.line(pts, fill=col, width=wd, joint="curve")
        for h in heads:
            d.line(h, fill=col, width=wd, joint="curve")
        for p in (pts[0], pts[-1]):
            d.ellipse((p[0] - wd / 2, p[1] - wd / 2, p[0] + wd / 2, p[1] + wd / 2), fill=col)
    sh = lay.getchannel("A").filter(ImageFilter.GaussianBlur(8)).point(lambda v: v * 0.5)
    base = Image.alpha_composite(base, Image.merge("RGBA", (*[Image.new("L", base.size, 0)] * 3, sh)))
    return Image.alpha_composite(base, lay)


def arrow(base, p0, p1, width=16, bend=0.18):
    mx = (p0[0] + p1[0]) / 2 + (p1[1] - p0[1]) * bend
    my = (p0[1] + p1[1]) / 2 - (p1[0] - p0[0]) * bend
    pts = [((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * mx + t * t * p1[0], (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * my + t * t * p1[1])
           for t in [i / 50 for i in range(51)]]
    ang = math.atan2(p1[1] - pts[-5][1], p1[0] - pts[-5][0])
    L = width * 3.4
    head = [(p1[0] - L * math.cos(ang - 0.5), p1[1] - L * math.sin(ang - 0.5)), p1,
            (p1[0] - L * math.cos(ang + 0.5), p1[1] - L * math.sin(ang + 0.5))]
    return _stroke_path(base, pts, width, heads=[head])


def loop(base, box, width=14, seed=4):
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    cx, cy, rx, ry = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    pts = [(cx + rx * (1 + 0.03 * math.sin(3 * t + 1)) * math.cos(t), cy + ry * (1 + 0.03 * math.sin(2 * t)) * math.sin(t))
           for t in [-0.5 + i / 160 * (2 * math.pi + 0.8) for i in range(161)]]
    return _stroke_path(base, pts, width)


def check(base, xy, size, width=18):
    x, y = xy
    return _stroke_path(base, [(x, y + size * 0.55), (x + size * 0.36, y + size * 0.92), (x + size, y)], width)


def src(name):
    return Image.open(SRC / f"{name}.png").convert("RGB")


def save(im, name):
    im = im.convert("RGB")
    im.save(OUT / f"{name}.jpg", quality=93)
    im.save(OUT / f"{name}.png", optimize=True)
    small = im.resize((im.width // 4, im.height // 4), Image.LANCZOS)     # phone-size check copy
    small.save(OUT / f"{name}-small.jpg", quality=85)




# ---------------------------------------------------------------- tools
def grab(trip, specs):
    import subprocess
    import vlog_ff
    use(trip)
    tdir = vlog_env.TRIPS / trip
    paths = {}
    for line in (tdir / "work" / "catalogue" / "catalogue.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        rel = line.split("\t")[0].replace("\\", "/")
        paths[Path(rel).stem] = tdir / "raw" / rel
    for spec in specs:
        stem, t = spec.split(":")
        dest = SRC / f"{stem}-{t}.png"
        r = vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", "-ss", t, "-i", str(paths[stem]), "-frames:v", "1", str(dest)],
                        timeout=300)
        print(stem, t, "ok" if r.returncode == 0 and dest.exists() else "FAILED")


def cutout(trip, files):
    """BiRefNet portrait (rembg). The model works at 1024 px, so the mask is made on a 1600 px copy and scaled back
    (the full 4K frame ran out of RAM, "bad allocation"); no memory arena for the same reason."""
    import os
    os.environ.setdefault("U2NET_HOME", str(vlog_env.MODELS / "u2net"))
    import onnxruntime as ort
    from rembg import new_session, remove
    use(trip)
    so = ort.SessionOptions()
    so.enable_cpu_mem_arena = False
    so.enable_mem_pattern = False
    so.intra_op_num_threads = 4
    session = new_session("birefnet-portrait", sess_opts=so)
    for f in files:
        im = Image.open(SRC.parent / f).convert("RGB")
        small = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
        mask = remove(small, session=session, only_mask=True).resize(im.size, Image.LANCZOS)
        im.putalpha(mask)
        box = mask.point(lambda a: 255 if a > 8 else 0).getbbox()
        im.crop(box).save(CUT / (Path(f).stem + ".png"))
        print(Path(f).stem, "cut")


def check_files(trip):
    """Thumbnails 1280x720 under 2 MB; covers 1080x1920 (layout numbers from vlog_layout)."""
    use(trip)
    bad = []
    for f in sorted(OUT.glob("*.jpg")):
        if f.stem.endswith("-small"):
            continue
        w, h = Image.open(f).size
        want = vlog_layout.COVER if h > w else vlog_layout.THUMB
        if (w, h) != want:
            bad.append(f"{f.name}: {w}x{h}, should be {want[0]}x{want[1]}")
        if w > h and f.stat().st_size > vlog_layout.THUMB_MAX_BYTES:
            bad.append(f"{f.name}: {f.stat().st_size / 1e6:.1f} MB, YouTube takes at most 2 MB")
    print("\n".join(bad) if bad else "thumbs: all good")
    return not bad


if __name__ == "__main__":
    trip, cmd, *rest = sys.argv[1:]
    {"grab": lambda: grab(trip, rest), "cut": lambda: cutout(trip, rest), "check": lambda: check_files(trip)}[cmd]()
