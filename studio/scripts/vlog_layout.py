"""One home for every size, margin and layout number of the trip pipeline ("dont because of just
changing one thing, then everything has problem"). Build, cut, check, editor page, fx and thumbnails read these; nothing
else types a frame size or a font size. Change a number here and every script follows.

Sizes are given for the frame they are used in, or as fractions of it, so 16:9 and 9:16, phone checks and 4K finals
all come from the same rules.
"""

# ---------------------------------------------------------------- frames
# phone = the small checking copies while editing; final = what is uploaded
# (decisions long videos 4K, shorts 1080x1920). vlog_build had the final at the edit list's
# 1920x1080, out of step with vlog_cut's 4K; both now read this.
from pathlib import Path  # noqa: E402

import vlog_env  # noqa: E402

_F = vlog_env.CFG.get("fonts", {})
_CJK_FONTS = {"text": "NotoSansSC-Medium.ttf", "bold": "NotoSansSC-Bold.ttf", "hand": "LXGWWenKai-Medium.ttf"}
_LATIN_FONTS = {"text": "NotoSans-Medium.ttf", "bold": "NotoSans-Bold.ttf", "hand": "NotoSans-Medium.ttf"}
_DEF = _CJK_FONTS if vlog_env.CJK else _LATIN_FONTS
# font files in <studio>/fonts and their names as ffmpeg knows them ([fonts] in vlog.toml, written by the installer)
FONT_FILE = {k: _F.get(f"{k}_file", _DEF[k]) for k in _DEF}
_NAMES = {"NotoSansSC-Medium.ttf": "Noto Sans SC Medium", "NotoSansSC-Bold.ttf": "Noto Sans SC Bold", "LXGWWenKai-Medium.ttf": "LXGW WenKai Medium",
          "NotoSans-Medium.ttf": "Noto Sans Medium", "NotoSans-Bold.ttf": "Noto Sans Bold"}
FONT_NAME = {k: _F.get(f"{k}_name", _NAMES.get(FONT_FILE[k], Path(FONT_FILE[k]).stem.replace("-", " "))) for k in _DEF}
_FINAL_WIDE = (1920, 1080) if str(vlog_env.FORMATS.get("final_wide", "4k")).lower().startswith("1080") else (3840, 2160)

FRAMES = {
    "phone": {"wide": (854, 480), "tall": (480, 854)},
    # the final size of 16:9 videos is the channel's choice ([formats] final_wide = "4k" | "1080p" in vlog.toml)
    "final": {"wide": _FINAL_WIDE, "tall": (1080, 1920)},
    "edit": {"wide": (1920, 1080), "tall": (1080, 1920)},     # the edit lists' own W, H (720p proxies are scaled to it)
}


def is_wide(W, H):
    return W > H


def frame(mode, W, H):
    """The frame size for `mode` ("phone" / "final" / "edit") of a video whose edit list says W x H."""
    return FRAMES[mode]["wide" if is_wide(W, H) else "tall"]


# ---------------------------------------------------------------- subtitles
SUB_CHARS = {"wide": 20, "tall": 24}          # most units on one subtitle line (vlog_build.units: a Chinese character = 1,
#                                               about two letters = 1), for the build and the editing page


def sub_chars(W, H):
    return SUB_CHARS["wide" if is_wide(W, H) else "tall"]


def sub_size(W, H):
    """Subtitle font size in px: every other text style is a fraction of it (STYLE_REL)."""
    return H // 14 if is_wide(W, H) else W // 13


def sub_margin_v(W, H):
    """Subtitle distance from the bottom: low on 16:9, above the Shorts / Reels buttons on 9:16."""
    return int(H * 0.075) if is_wide(W, H) else int(H * 0.31)


# ---------------------------------------------------------------- other text styles
# style: (font file, size as a fraction of sub_size). write_ass builds the ASS styles from this table and the text-fit
# check measures with the same numbers, so the two can never disagree again.
STYLE = {
    "Tag": (FONT_FILE["text"], 0.40),
    "Src": (FONT_FILE["hand"], 0.40),
    "Cap": (FONT_FILE["bold"], 0.46),
    "Name": (FONT_FILE["hand"], 0.62),
    "Title": (FONT_FILE["hand"], 1.25),
    "EndHead": (FONT_FILE["hand"], 1.00),
    "EndNext": (FONT_FILE["hand"], 0.62),
    "Credit": (FONT_FILE["text"], 0.36),
}


def style_size(name, W, H):
    return round(sub_size(W, H) * STYLE[name][1])


SRC_MARGIN_X = 1 / 40          # source line: right margin, fraction of W
SRC_TOP = 0.12                 # source line: top, fraction of H
TEXT_FIT = 0.92                # boxed text may use at most this fraction of the frame width


# ---------------------------------------------------------------- YouTube end screen
# slots measured at 1080p in YouTube Studio (visuals.md): two videos and the subscribe button
END_SLOTS_1080 = [(1876 - 628, 136, 628, 353), (1876 - 628, 916 - 353, 628, 353), (40, 916 - 304, 304, 304)]


def end_slots(W, H):
    s = W / 1920
    return [tuple(int(v * s) for v in box) for box in END_SLOTS_1080]


# ---------------------------------------------------------------- thumbnails and covers
THUMB = (1280, 720)            # YouTube thumbnail, under 2 MB
COVER = (1080, 1920)           # Reel cover
COVER_SAFE = (1080, 1350)      # what Instagram's 3:4 profile grid keeps, centred: words and subject go inside
COVER_MIN_TEXT = 80            # px, smallest readable cover text
THUMB_MAX_BYTES = 2_000_000
