"""Check a finished video (and its cover) against the rules of the platforms you post to.

    python vlog_platform.py list                          the platforms in platforms.toml, and which ones you post to
    python vlog_platform.py check <video.mp4> [platform ...] [--cover cover.png] [--text caption.txt]
        (no platform given: every platform in [platforms] post_to of vlog.toml whose shape fits this video)

For each platform: the shape (16:9 or 9:16), the length, the cover or thumbnail size and file size, where the cover's
safe area is, the length of the title / caption, the number of hashtags, and links in a text where they cannot be
clicked. Prints OK / WARN lines; exit code 1 when something breaks a rule. The rules live in <studio>/platforms.toml
with the month they were last checked: platforms change them often, so a WARN is a reason to look at the platform's
own help page, and to correct the file.
"""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import vlog_env

RULES = tomllib.loads((vlog_env.LOCAL / "platforms.toml").read_text(encoding="utf-8"))


def probe(f):
    r = subprocess.run([vlog_env.FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration,size",
                        "-of", "json", str(f)], capture_output=True, text=True)
    d = json.loads(r.stdout)
    s = d["streams"][0]
    return int(s["width"]), int(s["height"]), float(d["format"]["duration"]), int(d["format"]["size"])


def check(video, names, cover=None, text=None):
    w, h, dur, size = probe(video)
    shape = "wide" if w > h else "tall"
    out, bad = [f"{Path(video).name}: {w}x{h} ({'16:9' if shape == 'wide' else '9:16'}-ish), {dur:.1f} s, {size / 1e6:.0f} MB"], 0
    names = names or [n for n in vlog_env.PLATFORMS if RULES.get(n, {}).get("shape") == shape]
    if not names:
        out.append(f"WARN none of the platforms you post to ({', '.join(vlog_env.PLATFORMS)}) takes a {shape} video")
    for n in names:
        R = RULES.get(n)
        if not R:
            out.append(f"WARN {n}: not in platforms.toml (add its rules there)")
            bad += 1
            continue
        probs = []
        if R.get("shape") != shape:
            probs.append(f"wants a {R['shape']} video, this one is {shape}")
        if dur > R.get("max_seconds", 1e9):
            probs.append(f"{dur:.0f} s is over the {R['max_seconds']} s limit")
        if cover:
            from PIL import Image
            cw, ch = Image.open(cover).size
            want = R.get("thumbnail") or R.get("cover")
            if want and (cw, ch) != tuple(want):
                probs.append(f"cover is {cw}x{ch}, wanted {want[0]}x{want[1]}")
            if R.get("thumbnail_max_bytes") and Path(cover).stat().st_size > R["thumbnail_max_bytes"]:
                probs.append(f"cover file is {Path(cover).stat().st_size / 1e6:.1f} MB, over {R['thumbnail_max_bytes'] / 1e6:.0f} MB")
        if text:
            t = Path(text).read_text(encoding="utf-8")
            if len(t) > R.get("text_max", 1e9):
                probs.append(f"text is {len(t)} characters, over {R['text_max']}")
            tags = re.findall(r"#\S+", t)
            if len(tags) > R.get("hashtags_max", 1e9):
                probs.append(f"{len(tags)} hashtags, over {R['hashtags_max']}")
            if not R.get("links_in_text", True) and re.search(r"https?://|www\.", t):
                probs.append("the text holds a link, which cannot be clicked here: point to the profile or name the video instead")
        note = []
        if R.get("cover_safe"):
            note.append(f"cover: keep words and faces inside the centred {R['cover_safe'][0]}x{R['cover_safe'][1]}")
        if R.get("safe_bottom"):
            note.append(f"the bottom {R['safe_bottom']:.0%} and the right {R.get('safe_right', 0):.0%} are covered by buttons")
        out.append((f"WARN {R['name']}: " + "; ".join(probs)) if probs else f"OK   {R['name']}")
        out.append(f"       (rules checked {R.get('checked', '?')}" + ("; " + "; ".join(note) if note else "") + ")")
        bad += bool(probs)
    return out, bad


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    if not a or a[0] == "list":
        for n, R in RULES.items():
            mark = "*" if n in vlog_env.PLATFORMS else " "
            print(f"{mark} {n:16s} {R['name']:24s} {R['shape']:5s} up to {R.get('max_seconds', 0) // 60} min  (checked {R.get('checked', '?')})")
        print("\n* = you post there ([platforms] post_to in vlog.toml)")
        return
    if a[0] != "check" or len(a) < 2:
        print(__doc__)
        return
    opt = {a[i]: a[i + 1] for i in range(len(a) - 1) if a[i].startswith("--")}
    names = [x for x in a[2:] if not x.startswith("--") and x not in opt.values()]
    out, bad = check(a[1], names, opt.get("--cover"), opt.get("--text"))
    print("\n".join(out))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
