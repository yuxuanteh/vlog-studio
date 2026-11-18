"""Which clip is where, what it shows, what was said. Done once per trip.

Usage: python footage_index.py <trip> [--no-transcribe] [--redo]
  <trip> = folder under youtube/trips (e.g. 2026-05-kyoto).
Reads   <trip>/raw/**  (spot = the director's folder; files in raw/ are never moved)
        <trip>/work/labels.csv  (optional, step 3 recheck: "Day2\\C0069.MP4,车站" per line; overrides the spot)
Writes  <trip>/work/contact/<stem>.jpg     one sheet per clip: scene-change frames + even fill, mm:ss labels
        <trip>/work/transcript/<stem>.txt  Whisper, no prompt
        <trip>/work/footage-index.json + footage-index.md
        <trip>/work/mosaic/<spot>.jpg      one frame per clip per folder: read these before any single sheet
Already-done clips are skipped unless --redo, so rerunning only refreshes labels, table and mosaics.
"""
import csv
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import vlog_env

VIDEO = {".mp4", ".mov", ".mts", ".m2ts", ".m4a"}   # .m4a: phone voice memos get a transcript, no sheet
TILE_W, COLS, MAX_FRAMES = 480, 4, 12
MOS_W, MOS_H, MOS_COLS = 240, 135, 10


def start_time(path):
    """Clip start from the Sony XML (has the time zone); falls back to ffprobe's UTC date."""
    out = subprocess.run([vlog_env.EXIFTOOL, "-charset", "filename=utf8", "-j", "-CreationDateValue", "-CreateDate",
                          "-api", "QuickTimeUTC", str(path)], capture_output=True, text=True, encoding="utf-8").stdout
    tags = json.loads(out or "[{}]")[0]
    for key in ("CreationDateValue", "CreateDate"):
        v = tags.get(key)
        if isinstance(v, list):
            v = v[0]
        if v and not v.startswith("0000"):
            try:
                return datetime.strptime(v, "%Y:%m:%d %H:%M:%S%z")
            except ValueError:
                pass
    # exiftool can't open some non-Japanese folder names on this PC (层, 户); ffprobe can. Stored as UTC.
    out = subprocess.run([vlog_env.FFPROBE, "-v", "error", "-show_entries", "format_tags=creation_time", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout.strip()
    if out:
        return datetime.fromisoformat(out.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=9)))
    return None


def duration(path):
    out = subprocess.run([vlog_env.FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout
    return float(out.strip() or 0)


def frame_times(path, dur):
    """Scene-change starts first (what changed), then evenly spaced fill up to MAX_FRAMES."""
    from scenedetect import ContentDetector, detect
    try:
        cuts = [s[0].get_seconds() + 0.5 for s in detect(str(path), ContentDetector(threshold=27))]
    except Exception:
        cuts = []
    times = sorted(set(round(t, 1) for t in cuts if t < dur - 0.5))[:MAX_FRAMES]
    n = max(MAX_FRAMES - len(times), 0)
    fill = [dur * (i + 0.5) / n for i in range(n)] if n else []
    times = sorted(times + [t for t in fill if all(abs(t - c) > 1.5 for c in times)])
    return times[:MAX_FRAMES] or [0.0]


def grab(path, t):
    raw = subprocess.run([vlog_env.FFMPEG, "-v", "error", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                          "-vf", f"scale={TILE_W}:-2", "-f", "image2pipe", "-vcodec", "png", "-"],
                         capture_output=True).stdout
    return Image.open(BytesIO(raw)).convert("RGB") if raw else None


def contact_sheet(path, dur, dest):
    frames = [(t, im) for t in frame_times(path, dur) if (im := grab(path, t)) is not None]
    if not frames:
        return 0
    h = frames[0][1].height
    rows = (len(frames) + COLS - 1) // COLS
    sheet = Image.new("RGB", (TILE_W * COLS, h * rows + 28), "black")
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype("arial.ttf", 20)
    d.text((6, 4), f"{path.name}   {dur:.0f}s", fill="white", font=font)
    for i, (t, im) in enumerate(frames):
        x, y = (i % COLS) * TILE_W, (i // COLS) * h + 28
        sheet.paste(im, (x, y))
        d.rectangle([x, y, x + 64, y + 24], fill="black")
        d.text((x + 4, y + 2), f"{int(t // 60)}:{int(t % 60):02d}", fill="yellow", font=font)
    sheet.save(dest, quality=80)
    return len(frames)


def spot_of(rel, labels):
    if rel in labels:
        return labels[rel]
    parent = str(Path(rel).parent)
    return parent if ("\\" in parent or "/" in parent) else f"{parent} ({vlog_env.tr('not grouped', '未分组')})"


def mosaics(trip, rows):
    """One image per spot, one middle frame per clip, so a folder is read in one look."""
    dest = trip / "work" / "mosaic"
    dest.mkdir(exist_ok=True)
    font = ImageFont.truetype("arial.ttf", 14)
    spots = {}
    for c in rows:
        if c["frames"]:
            spots.setdefault(c["spot"], []).append(c)
    for spot, clips in spots.items():
        n_rows = (len(clips) + MOS_COLS - 1) // MOS_COLS
        out = Image.new("RGB", (MOS_W * MOS_COLS, MOS_H * n_rows), "black")
        d = ImageDraw.Draw(out)
        for i, c in enumerate(clips):
            cs = Image.open(trip / c["sheet"])
            h = (cs.height - 28) // ((c["frames"] + 3) // 4)
            col, row = (c["frames"] // 2) % 4, (c["frames"] // 2) // 4
            tile = cs.crop((col * TILE_W, 28 + row * h, (col + 1) * TILE_W, 28 + (row + 1) * h)).resize((MOS_W, MOS_H))
            x, y = (i % MOS_COLS) * MOS_W, (i // MOS_COLS) * MOS_H
            out.paste(tile, (x, y))
            d.rectangle([x, y, x + 100, y + 18], fill="black")
            d.text((x + 3, y + 1), f'{Path(c["file"]).stem} {c["duration"]:.0f}s', fill="yellow", font=font)
        out.save(dest / (re.sub(r'[\\/:*?"<>|]', "_", spot) + ".jpg"), quality=80)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    trip = vlog_env.TRIPS / args[0]
    work = trip / "work"
    (work / "contact").mkdir(parents=True, exist_ok=True)
    (work / "transcript").mkdir(parents=True, exist_ok=True)
    index_f = work / "footage-index.json"
    index = {c["file"]: c for c in json.loads(index_f.read_text(encoding="utf-8"))} if index_f.exists() else {}
    labels_f = work / "labels.csv"
    labels = {r[0].strip(): r[1].strip() for r in csv.reader(labels_f.read_text(encoding="utf-8-sig").splitlines())
              if len(r) >= 2} if labels_f.exists() else {}

    # two files of a trip can share a name (the camera's counter starts again: Rerecord\C0022 and Day4\C0022). The
    # later one gets its own name ("C0022r") for edit lists and work files, so it never overwrites the first one's
    # transcript and sheet. Files in raw/ are not renamed.
    taken = {(c.get("stem") or Path(c["file"].replace("\\", "/")).stem): c["file"] for c in index.values()}
    for p in sorted(p for p in (trip / "raw").rglob("*") if p.suffix.lower() in VIDEO):
        rel = str(p.relative_to(trip / "raw"))
        if rel in index and "--redo" not in flags:
            continue
        name = index.get(rel, {}).get("stem") or p.stem
        while taken.get(name, rel) != rel:
            name += "r"
        taken[name] = rel
        t, dur = start_time(p), duration(p)
        sheet = work / "contact" / f"{name}.jpg"
        n = contact_sheet(p, dur, sheet)
        words = ""
        if "--no-transcribe" not in flags:
            import whisper_run
            out, lines = whisper_run.run(whisper_run.decode(p))
            (work / "transcript" / f"{name}.txt").write_text("\n".join(lines), encoding="utf-8")
            words = "".join(s["text"] for s in out["segments"])
        index[rel] = {"file": rel, "start": t.isoformat() if t else None, "duration": round(dur, 1),
                      "frames": n, "sheet": str(sheet.relative_to(trip)), "said": words}
        if name != p.stem:
            index[rel]["stem"] = name
        print(f"{rel}  {t}  {dur:.0f}s  {n} frames", flush=True)
        index_f.write_text(json.dumps(list(index.values()), ensure_ascii=False, indent=1), encoding="utf-8")

    for c in index.values():
        c["spot"] = spot_of(c["file"], labels)
    rows = sorted(index.values(), key=lambda c: c["start"] or "")
    index_f.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    md = [vlog_env.tr("# Footage index", "# 素材总表"), "",
          vlog_env.tr("| # | File | Start (local time) | Length | Place | What is said (start) |", "| # | 文件 | 开始（当地时间） | 长度 | 地点 | 讲了什么（前 60 字） |"),
          "|---|---|---|---|---|---|"]
    for i, c in enumerate(rows, 1):
        st = c["start"][5:16].replace("T", " ") if c["start"] else "?"
        md.append(f"| {i} | {c['file']} | {st} | {c['duration']:.0f}s | {c['spot']} | {c['said'][:60]} |")
    (work / "footage-index.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    mosaics(trip, rows)
    print(f"{len(rows)} clips -> {work / 'footage-index.md'}")


if __name__ == "__main__":
    main()
