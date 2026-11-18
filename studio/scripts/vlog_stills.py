r"""Overlay stills check: before any render, redraw a still at every on-screen text of a video (source lines,
place tags, name tag, title, end card, the first subtitle of each block) with the CURRENT code and edit list, over the
pieces already cached, and compare each with the still the director last approved. A change meant for one thing that
moves another shows up here in seconds, instead of after a render.

    python vlog_stills.py <trip> <id> [<id> ...]            draw + compare; prints CHANGED / NEW / GONE, writes a sheet
    python vlog_stills.py <trip> <id> [<id> ...] --approve  take the current stills as the approved ones

Stills: <trip>/work/review/stills/<id>/<kind>-<t>.png (current), .../stills-approved/<id>/ (approved);
changes sheet: <trip>/work/review/stills/<id>-changes.jpg. Uses the phone build's cached pieces (fast); a video with no
phone build yet is skipped with a note. A still counts as changed when more than 0.5 % of its pixels differ visibly.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402
import vlog_ff  # noqa: E402

KINDS = ("Src", "Cap", "Tag", "Name", "Title", "EndHead", "Credit")
FONTS = vlog_env.LOCAL / "fonts"


def clock(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def events(ass):
    out, seen_block = [], -9.0
    for line in ass.read_text(encoding="utf-8").splitlines():
        m = re.match(r"Dialogue: \d+,([\d:.]+),([\d:.]+),(\w+),", line)
        if not m:
            continue
        a, b, k = clock(m[1]), clock(m[2]), m[3]
        if k in KINDS:
            out.append((k, (a + b) / 2))
        elif k == "Sub" and a - seen_block > 20:          # one subtitle every ~20 s: line breaks and size
            out.append(("Sub", (a + b) / 2))
            seen_block = a
    return out


def draw(trip, eid):
    env = dict(PYTHONIOENCODING="utf-8")
    import os
    env = {**os.environ, **env}
    r = subprocess.run([sys.executable, str(HERE / "vlog_build.py"), trip, eid, "--phone", "--check"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=1800,
                       stdin=subprocess.DEVNULL)
    if r.returncode:
        raise SystemExit(f"STOP: {eid} --check failed:\n{r.stdout[-1500:]}{r.stderr[-1500:]}")
    for line in r.stdout.splitlines():
        if "TEXT TOO WIDE" in line or line.startswith("#"):
            print("  ", line)
    ass = Path(tempfile.gettempdir()) / f"{eid}-check.ass"
    work = vlog_env.LOCAL / "render" / trip / f"{eid}-phone"
    if not (work / "list.txt").exists():
        print(f"{eid}: no phone build yet, nothing to draw on (skipped)")
        return None
    shutil.copyfile(ass, work / "stills.ass")
    out = vlog_env.TRIPS / trip / "work" / "review" / "stills" / eid
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    fdir = FONTS.as_posix().replace(":", "\\:")
    for k, t in events(ass):
        dest = out / f"{k}-{t:07.2f}.png"
        vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", "-ss", f"{t:.2f}", "-f", "concat", "-safe", "0", "-i", "list.txt",
                     "-frames:v", "1", "-vf", f"setpts=PTS+{t:.2f}/TB,subtitles=stills.ass:fontsdir='{fdir}'", str(dest)],
                    cwd=work, timeout=120)
    return out


def compare(trip, eid, cur):
    appr = vlog_env.TRIPS / trip / "work" / "review" / "stills-approved" / eid
    if not appr.exists():
        print(f"{eid}: no approved stills yet; look at {cur} and run with --approve")
        return
    a_names = {p.name for p in appr.glob("*.png")}
    c_names = {p.name for p in cur.glob("*.png")}
    changed = []
    for n in sorted(a_names & c_names):
        x = np.asarray(Image.open(appr / n).convert("L"), dtype=np.int16)
        y = np.asarray(Image.open(cur / n).convert("L"), dtype=np.int16)
        if x.shape != y.shape or (np.abs(x - y) > 24).mean() > 0.005:
            changed.append(n)
    new, gone = sorted(c_names - a_names), sorted(a_names - c_names)
    for tag, ns in (("CHANGED", changed), ("NEW", new), ("GONE", gone)):
        for n in ns:
            print(f"{eid}: {tag} {n}")
    show = [(appr / n, cur / n) for n in changed] + [(None, cur / n) for n in new]
    if show:
        tiles = []
        for before, after in show:
            a = Image.open(after).convert("RGB")
            b = Image.open(before).convert("RGB") if before else Image.new("RGB", a.size, (60, 60, 60))
            t = Image.new("RGB", (a.width * 2 + 10, a.height + 22), "white")
            t.paste(b, (0, 22))
            t.paste(a, (a.width + 10, 22))
            ImageDraw.Draw(t).text((4, 4), f"{after.name}: approved | now", fill="black")
            tiles.append(t)
        sheet = Image.new("RGB", (max(t.width for t in tiles), sum(t.height for t in tiles)), "white")
        y = 0
        for t in tiles:
            sheet.paste(t, (0, y))
            y += t.height
        p = cur.parent / f"{eid}-changes.jpg"
        sheet.save(p, quality=85)
        print(f"{eid}: {len(show)} still(s) to look at -> {p}")
    else:
        print(f"{eid}: all {len(c_names)} stills match the approved ones")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trip, ids = args[0], args[1:]
    for eid in ids:
        cur = draw(trip, eid)
        if cur is None:
            continue
        if "--approve" in sys.argv:
            appr = vlog_env.TRIPS / trip / "work" / "review" / "stills-approved" / eid
            shutil.rmtree(appr, ignore_errors=True)
            shutil.copytree(cur, appr)
            print(f"{eid}: {len(list(cur.glob('*.png')))} stills approved")
        else:
            compare(trip, eid, cur)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
