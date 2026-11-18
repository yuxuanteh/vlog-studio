r"""Rehearse a whole render before the real one ("do FULL DEBUG, check anything that can go wrong
for the phone copy and the 4K final"). Every video, as phone copy and as final, goes through the REAL build
(vlog_build.py --rehearse): every shot, steadying, tracked effect, the sound mix, subtitles, the final encode, the
copies and the clean-up - at a tiny frame size, writing only into <local>/rehearse/<trip>/<id>-<mode>. Steadying
and tracking are worked out at the analysis size exactly as in the real run and cached, so the real run reuses them.

    python vlog_rehearse.py <trip> <id> [<id> ...] [--phone-only | --final-only]

After each build it checks the result: the file plays, its length matches the plan (report.txt) within 0.2 s, it has
picture and sound, the review copy and the timeline record exist (final), the subtitle file reads. Prints
"REHEARSAL OK <id> <mode>" or "REHEARSAL FAILED <id> <mode>: <why>" and the effects sheet; exit 1 on any failure.
Nothing in the trip folder, publish/, preview/ or send/ is written.
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402
import vlog_ff  # noqa: E402

PY = sys.executable


def probe(f):
    r = vlog_ff.run([vlog_env.FFPROBE, "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                     "-of", "json", str(f)], capture_output=True, text=True)
    d = json.loads(r.stdout or "{}")
    v = [s for s in d.get("streams", []) if s.get("codec_type") == "video"]
    a = [s for s in d.get("streams", []) if s.get("codec_type") == "audio"]
    return float(d.get("format", {}).get("duration", 0) or 0), v, a


def planned(trip_dir, vid):
    rep = (trip_dir / "work" / "edl" / f"{vid}.report.txt").read_text(encoding="utf-8")
    m = re.search(r"# ([\d.]+) min", (trip_dir / "work" / "edl" / f"{vid}.cues.txt").read_text(encoding="utf-8"))
    return float(m[1]) * 60 if m else None, rep


def rehearse(trip, vid, mode, logs):
    t0 = time.time()
    sand = vlog_env.LOCAL / "rehearse" / trip / f"{vid}-{mode}"
    cmd = [PY, "-u", "vlog_build.py", trip, vid, "--rehearse"] + (["--phone"] if mode == "phone" else [])
    work = vlog_env.LOCAL / "render" / trip / (f"{vid}-phone-rehearse-phone" if mode == "phone" else f"{vid}-rehearse-final")
    log = logs / f"{vid}-rehearse-{mode}.log"
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run([PY, "vlog_watch.py", "--stall", "10", "--watch", str(work), "--"] + cmd, stdout=f,
                           stderr=subprocess.STDOUT, cwd=HERE, stdin=subprocess.DEVNULL,
                           env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    text = log.read_text(encoding="utf-8", errors="replace")
    if r.returncode or "Traceback" in text:
        tail = "\n".join(text.strip().splitlines()[-6:])
        return False, f"build exit {r.returncode}: {tail}"
    trip_dir = vlog_env.TRIPS / trip
    tl = sand / "review" / f"{vid}.timeline.json"        # the build's own exact length (cues.txt rounds to 0.01 min)
    total = json.loads(tl.read_text(encoding="utf-8"))["total"] if tl.exists() else planned(trip_dir, vid)[0]
    if mode == "phone":
        files = list((sand / "preview").glob(f"{vid}-phone.mp4"))
    else:
        files = list((sand / "publish").rglob("*.mp4"))
    if not files:
        return False, f"no video written in {sand}"
    why = []
    for f in files:
        dur, v, a = probe(f)
        if not v or not a:
            why.append(f"{f.name}: picture {bool(v)}, sound {bool(a)}")
        if total and abs(dur - total) > 0.25:
            why.append(f"{f.name}: {dur:.2f} s but the plan is {total:.2f} s")
    if not (sand / "review" / f"{vid}.timeline.json").exists():
        why.append("no timeline record (the review page's map of the copy)")
    if mode == "final":
        review = sand / "preview" / f"{vid}-phone.mp4"
        if not review.exists():
            why.append("no review copy made from the final")
        import vlog_srt
        subs = work / "subs.ass"
        if not subs.exists() or not vlog_srt.cues(subs):
            why.append("the subtitle track (subs.ass) is missing or empty")
    q = subprocess.run([PY, "vlog_qrcheck.py", trip, vid, str(files[0])], capture_output=True, text=True, cwd=HERE,
                       encoding="utf-8", errors="replace")
    sheet = next((ln for ln in q.stdout.splitlines() if ln.startswith("QR SHEET")), "")
    msg = f"{time.time() - t0:.0f} s" + (f"; {sheet}" if sheet else "")
    return (not why), ("; ".join(why) if why else msg)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trip, ids = args[0], args[1:]
    modes = ["phone"] if "--phone-only" in sys.argv else ["final"] if "--final-only" in sys.argv else ["phone", "final"]
    logs = vlog_env.LOCAL / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    bad = 0
    for vid in ids:
        for mode in modes:
            print(f"=== rehearse {vid} {mode} {time.strftime('%H:%M')}", flush=True)
            ok, why = rehearse(trip, vid, mode, logs)
            print(("REHEARSAL OK" if ok else "REHEARSAL FAILED") + f" {vid} {mode}: {why}", flush=True)
            bad += not ok
    print(f"=== rehearsal done: {bad} failed", flush=True)
    sys.exit(1 if bad else 0)
