r"""The one way to render trip videos (replaces the hand-written render-all.sh).

    python vlog_run.py <trip> <id> [<id> ...] [--final] [--accept-stills] [--selftest] [--rehearse]

In order, stopping at the first thing that is wrong, so a mistake never costs a render:
1. vlog_selftest.py: every edge case we have hit still passes. Skipped when no script, page, effect file or edit list
   has changed since it last passed (--selftest forces it); the same for a final's rehearsal (--rehearse).
2. vlog_build.py --check for every id: subtitle guard, text fit (TEXT TOO WIDE), the director's sheet.
3a. vlog_precheck.py: every shot and subtitle changed since the copy the director watched (CHANGE) and anything broken
   (WARN: a changed shot that shakes, the same words heard twice, a put-back word gone); a WARN stops the run until
   the director has seen it (--accept-warn).
3. vlog_stills.py: the stills at every overlay against the approved ones; any change stops the run until the director has
   seen it (--accept-stills after they have).
4. Each id, one at a time, under the stall watchdog (vlog_watch.py: 6 min with no CPU and no file change = frozen, the
   whole process tree is killed), phone size by default, --final for the upload files (straight into publish/).
5. After every build, a QR sheet (vlog_qrcheck.py) of every QR / ticket shot from the rendered file: Claude looks at it
   before calling the video ready. After each phone build: the picture check for that id (the director watches the copy
   on the review page). After each final: the zh subtitle file (vlog_srt.py) and the thumbnail check.
Every step prints one line starting with "=== ", "READY ", "FAILED " or "STALL ", so a monitor can follow the run and
report a freeze or a finished video at once. Logs: <local>/logs/<id>-<mode>.log.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402

PY = sys.executable
FFBIN = str(Path(vlog_env.FFMPEG).parent)
ENV = {**os.environ, "PYTHONIOENCODING": "utf-8", "PATH": FFBIN + os.pathsep + os.environ.get("PATH", "")}
LOGS = vlog_env.LOCAL / "logs"


def say(line):
    print(line, flush=True)


def step(name, cmd, log, stall=None, watch=None):
    """Run a step, log it, return (ok, output tail). Long steps run under the watchdog."""
    if stall:
        cmd = [PY, str(HERE / "vlog_watch.py"), "--stall", str(stall)] + (["--watch", str(watch)] if watch else []) + ["--"] + cmd
    with open(log, "w", encoding="utf-8") as f:
        r = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, env=ENV, cwd=HERE, stdin=subprocess.DEVNULL)
    text = Path(log).read_text(encoding="utf-8", errors="replace")
    if r.returncode == 124 or "STALL:" in text:
        say(f"STALL {name}: frozen and stopped; log {log}")
        return False, text
    if r.returncode:
        say(f"FAILED {name}: exit {r.returncode}; log {log}\n" + "\n".join(text.strip().splitlines()[-8:]))
        return False, text
    return True, text


def code_stamp(trip=None):
    """One fingerprint of every script, page and trip effect file (and, with a trip, its edit lists): the selftest and
    the rehearsal run again only when this has changed since they last passed."""
    import hashlib
    files = sorted(HERE.glob("*.py")) + sorted((HERE / "editor").glob("*.html")) + sorted(vlog_env.TRIPS.glob("*/work/fx.py"))
    if trip:
        files += sorted(f for f in (vlog_env.TRIPS / trip / "work" / "edl").glob("*.py") if f.stem.count(".") == 0)
    h = hashlib.md5()
    for f in files:
        h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


def passed(key, stamp=None):
    """Read (stamp=None) or record what last passed, in <local>/passed.json."""
    import json
    f = vlog_env.LOCAL / "passed.json"
    d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    if stamp is None:
        return d.get(key)
    d[key] = stamp
    f.write_text(json.dumps(d, indent=1), encoding="utf-8")


alive = vlog_env.pid_alive


def one_at_a_time():
    """One render on this computer at a time (a 4K final started beside the phone builds, ran out of memory,
    and froze the other's encode). A second vlog_run waits here for the first to finish."""
    lock = vlog_env.LOCAL / "render.lock"
    said = False
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            import atexit
            atexit.register(lambda: lock.unlink(missing_ok=True))
            return
        except FileExistsError:
            try:
                other = int(lock.read_text().strip() or 0)
            except (OSError, ValueError):
                other = 0
            if not other or not alive(other):
                lock.unlink(missing_ok=True)              # left by a run that was killed
                continue
            if not said:
                say(f"=== waiting: another render is running (pid {other})")
                said = True
            time.sleep(20)


def main():
    one_at_a_time()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    trip, ids = args[0], args[1:]
    final = "--final" in sys.argv
    mode = "final" if final else "phone"
    LOGS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    failed = []

    stamp = code_stamp(trip)
    if passed("selftest") == stamp and "--selftest" not in sys.argv:
        say("=== selftest: skipped, no script or edit list changed since it last passed")
    else:
        say("=== selftest")
        ok, text = step("selftest", [PY, "vlog_selftest.py"], LOGS / "selftest.log")
        if not ok:
            sys.exit(1)
        passed("selftest", stamp)

    say("=== check " + " ".join(ids))
    for eid in ids:
        ok, text = step(f"check {eid}", [PY, "vlog_build.py", trip, eid, "--check"] + ([] if final else ["--phone"]),
                        LOGS / f"{eid}-check.log", stall=6)
        if not ok:
            sys.exit(1)
        warn = [line for line in text.splitlines() if any(k in line for k in ("TEXT TOO WIDE", "STOP", "SUB ORDER", "SUB GAP"))]
        if warn:
            say(f"FAILED check {eid}:\n" + "\n".join(warn))
            sys.exit(1)
        # the build's own warnings (an edited row or a put-back word the edit list no longer reaches) were printed
        # into the log and never shown (review): they stop the run like any other warning
        lost = [line for k, line in enumerate(text.splitlines())
                if line.startswith("WARNING") or (k and text.splitlines()[k - 1].startswith("WARNING") and line.startswith("  "))]
        if lost:
            say(f"WARN check {eid}:\n" + "\n".join(lost))
            if "--accept-warn" not in sys.argv:
                say("FAILED check: the edit list leaves out something the director edited; fix the edit list, or "
                    "--accept-warn after they have answered")
                sys.exit(1)

    # what the director's edits changed since the copy they watched, and anything they broke
    say("=== side effects " + " ".join(ids))
    ok, text = step("side effects", [PY, "vlog_precheck.py", trip, *ids], LOGS / "precheck.log", stall=10)
    for line in text.splitlines():
        if line.startswith(("CHANGE", "WARN", "ASK", "OK'd", "#")):
            say("  " + line)
    found = any(line.startswith(("WARN", "ASK")) for line in text.splitlines())
    if not ok and not found:                            # the check itself broke: never waved through by --accept-warn
        say("FAILED side effects: the check did not finish (see the log), so nothing was checked")
        sys.exit(1)
    if not ok and "--accept-warn" not in sys.argv:
        say("FAILED side effects: tell the director every WARN / ASK line; once they have answered, record it with\n"
            "  vlog_precheck.py <trip> <id> --accept \"<words of that warning>\"   (or: --accept all)\n"
            "and run again: an answered warning is never asked twice")
        sys.exit(1)

    # faces a shot with a recognisable face and no decision in work/privacy.json stops
    # the run until the director has said ok / blur / cut
    face_model = vlog_env.MODELS / "opencv" / "face_detection_yunet_2023mar.onnx"
    if not (face_model.exists() and vlog_env.cfg("components", "privacy", True)):
        # the privacy part was not installed: say so every time, so nobody believes faces were looked for
        say("=== faces: SKIPPED (the privacy part is not installed: no face was looked for; check passers-by yourself)")
        ok, text = True, ""
    else:
        say("=== faces " + " ".join(ids))
        ok, text = step("faces", [PY, "vlog_faces.py", trip, *ids], LOGS / "faces.log", stall=10)
    for line in text.splitlines():
        if line.startswith(("ASK", "#")):
            say("  " + line)
    if not ok:
        say("FAILED faces: ask the director about each ASK line (sheet in send/faces-<id>.jpg), write work/privacy.json")
        sys.exit(1)

    say("=== stills " + " ".join(ids))
    ok, text = step("stills", [PY, "vlog_stills.py", trip, *ids], LOGS / "stills.log", stall=6)
    if not ok:
        sys.exit(1)
    changes = [line for line in text.splitlines() if any(k in line for k in ("CHANGED", "NEW", "GONE", "to look at"))]
    if changes and "--accept-stills" not in sys.argv:
        say("FAILED stills: on-screen text changed since the director last approved it; look first, then --accept-stills\n"
            + "\n".join(changes))
        sys.exit(1)

    # a 4K final rehearses first (full debug): the whole run at a tiny size in a sandbox, ~10-15 min,
    # so a crash or an effect that cannot follow its object shows before an hour of 4K, never after
    # Only when a script or effect file changed since this video's last passing rehearsal;
    # --rehearse forces one.
    rstamp = code_stamp()
    todo = [eid for eid in ids if passed(f"rehearsal {trip}/{eid}") != rstamp or "--rehearse" in sys.argv]
    if final and not todo:
        say("=== rehearsal: skipped, no script changed since these videos last rehearsed")
    if final and todo and "--no-rehearsal" not in sys.argv:
        say("=== rehearsal " + " ".join(todo))
        ok, text = step("rehearsal", [PY, "vlog_rehearse.py", trip, *todo, "--final-only"], LOGS / "rehearsal.log", stall=12)
        for line in text.splitlines():
            if line.startswith(("REHEARSAL", "QR SHEET")):
                say("  " + line)
        if not ok:
            say("FAILED rehearsal: fix what it found before the 4K render")
            sys.exit(1)
        for eid in todo:
            passed(f"rehearsal {trip}/{eid}", rstamp)

    for eid in ids:
        say(f"=== {mode} {eid} {time.strftime('%H:%M')}")
        work = vlog_env.LOCAL / "render" / trip / (eid + ("" if final else "-phone"))
        ok, text = step(f"{mode} {eid}", [PY, "-u", "vlog_build.py", trip, eid] + ([] if final else ["--phone"]),
                        LOGS / f"{eid}-{mode}.log", stall=10 if final else 6, watch=work)
        if not ok:
            failed.append(eid)
            continue
        made = [Path(line.strip()) for line in text.splitlines() if line.strip().endswith(".mp4") and Path(line.strip()).exists()]
        if final:
            # the zh file is written at once; en / ja wait for Claude's translations, which is expected, not a failure
            r = subprocess.run([PY, "vlog_srt.py", trip, eid], capture_output=True, text=True, encoding="utf-8",
                               errors="replace", env=ENV, cwd=HERE, stdin=subprocess.DEVNULL)
            (LOGS / f"{eid}-srt.log").write_text(r.stdout + r.stderr, encoding="utf-8")
            todo = [line for line in (r.stdout + r.stderr).splitlines() if line.startswith("STOP")]
            say(f"TODO subtitles {eid}: " + todo[0][6:] if todo else f"=== subtitles {eid}: subtitle files written")
            for f in made:
                r = subprocess.run([PY, "vlog_qrcheck.py", trip, eid, str(f)], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", env=ENV, cwd=HERE, stdin=subprocess.DEVNULL)
                for line in (r.stdout + r.stderr).splitlines():
                    if line.startswith("QR"):
                        say(line)
                say(f"READY {f}")
            # the picture check, on the review copy made from the final. The edit check is
            # not run again here: it needs no video and already ran, on the same files, in "side effects" above
            for chk in ("vlog_piccheck.py", "vlog_sharp.py"):     # vlog_sharp: the softest shots of the final at full size
                okc, tc = step(f"{chk} {eid} (final)", [PY, chk, trip, eid], LOGS / f"{eid}-{chk[:-3]}-final.log", stall=6)
                for line in tc.splitlines():
                    if line.startswith(("#", "SHARP")):
                        say(f"  {line}")
            continue
        for chk in ("vlog_piccheck.py",):
            okc, tc = step(f"{chk} {eid}", [PY, chk, trip, eid], LOGS / f"{eid}-{chk[:-3]}.log", stall=6)
            for line in tc.splitlines():
                if line.startswith("#"):
                    say(f"  {line}")
        for f in made:
            r = subprocess.run([PY, "vlog_qrcheck.py", trip, eid, str(f)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", env=ENV, cwd=HERE, stdin=subprocess.DEVNULL)
            for line in (r.stdout + r.stderr).splitlines():
                if line.startswith("QR"):
                    say(line)
            say(f"READY {f}")                              # watched on the review page (no send copies)
    say(f"=== done {(time.time() - t0) / 60:.0f} min" + (f", FAILED: {' '.join(failed)}" if failed else ""))
    if failed:                                          # a failed phone build let "&& --final" start
        sys.exit(1)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
