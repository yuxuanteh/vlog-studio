"""720p working copies of a trip's clips on C:, so editing doesn't pull 4K off Drive. Done once per trip.

Usage: python footage_proxy.py <trip>      <trip> = folder under youtube/trips (e.g. 2026-05-kyoto).
Writes <studio>/trips/<trip>/proxy/<same folders as raw>/<stem>.mp4
Same frame rate and audio as the original, so times match. Originals stay on Drive for the 4K final.
Already-done clips are skipped; a half-written copy is never left under the final name.
"""
import subprocess
import sys

import vlog_env

VIDEO = {".mp4", ".mov", ".mts", ".m2ts"}


def main():
    raw = vlog_env.TRIPS / sys.argv[1] / "raw"
    dest = vlog_env.LOCAL / "trips" / sys.argv[1] / "proxy"
    clips = sorted(p for p in raw.rglob("*") if p.suffix.lower() in VIDEO)
    done = 0
    for i, p in enumerate(clips, 1):
        out = dest / p.relative_to(raw).with_suffix(".mp4")
        if out.exists():
            done += 1
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.stem + ".part.mp4")
        r = subprocess.run([vlog_env.FFMPEG, "-y", "-v", "error", "-i", str(p), "-vf", "scale=-2:720",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k",
                            "-map_metadata", "0", str(tmp)])
        if r.returncode == 0:
            tmp.replace(out)
            done += 1
            print(f"{i}/{len(clips)} {p.name}", flush=True)
        else:
            tmp.unlink(missing_ok=True)
            print(f"{i}/{len(clips)} FAILED {p}", flush=True)
    print(f"{done}/{len(clips)} copies ready")


if __name__ == "__main__":
    main()
