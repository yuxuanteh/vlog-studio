"""Overview of a trip's photos: one image per folder, name + time on each. Done once per trip.

Usage: python photo_mosaic.py <trip>      <trip> = folder under youtube/trips (e.g. 2026-05-kyoto).
Writes <trip>/work/mosaic-photos/<folder>.jpg and <trip>/work/photo-index.csv (file, taken, folder).
Already-made images are kept. Delete one to rebuild it.
"""
import csv
import re
import sys

from PIL import Image, ImageDraw, ImageFont, ImageOps

import vlog_env

PHOTO = {".jpg", ".jpeg", ".png"}   # Pillow can't open .heic: phone photos are viewed one by one through ffmpeg
W, H, COLS = 240, 240, 10
PER_SHEET = 60


def taken(im):
    v = im.getexif().get_ifd(0x8769).get(36867) or im.getexif().get(306) or ""
    return v[5:16].replace(":", "-", 1) if v else "?"


def main():
    trip = vlog_env.TRIPS / sys.argv[1]
    raw, dest = trip / "raw", trip / "work" / "mosaic-photos"
    dest.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype("arial.ttf", 13)
    groups = {}
    for p in sorted(p for p in raw.rglob("*") if p.suffix.lower() in PHOTO):
        groups.setdefault(p.parent, []).append(p)
    rows = []
    for folder, photos in groups.items():
        name = re.sub(r'[\\/:*?"<>|]', "_", str(folder.relative_to(raw)))
        for part in range(0, len(photos), PER_SHEET):
            chunk = photos[part:part + PER_SHEET]
            out = dest / f"{name}-{part // PER_SHEET + 1}.jpg"
            sheet = None if out.exists() else Image.new(
                "RGB", (W * COLS, H * ((len(chunk) + COLS - 1) // COLS)), "black")
            d = ImageDraw.Draw(sheet) if sheet else None
            for i, p in enumerate(chunk):
                with Image.open(p) as im:
                    when = taken(im)
                    rows.append([str(p.relative_to(raw)), when, str(folder.relative_to(raw))])
                    if sheet:
                        im.draft("RGB", (W * 2, H * 2))
                        t = ImageOps.exif_transpose(im).convert("RGB")
                        t.thumbnail((W, H))
                        x, y = (i % COLS) * W, (i // COLS) * H
                        sheet.paste(t, (x + (W - t.width) // 2, y + (H - t.height) // 2))
                        d.rectangle([x, y, x + 150, y + 17], fill="black")
                        d.text((x + 3, y + 1), f"{p.stem[-14:]} {when[-5:]}", fill="yellow", font=font)
            if sheet:
                sheet.save(out, quality=78)
                print(out.name, len(chunk), flush=True)
    with (trip / "work" / "photo-index.csv").open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows([["file", "taken", "folder"]] + rows)
    print(f"{len(rows)} photos")


if __name__ == "__main__":
    main()
