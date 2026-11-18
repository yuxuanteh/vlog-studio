r"""What the director's edits changed, and anything they broke, before a render ("catch any problem
or side effect after my edit before rendering videos").

    python vlog_precheck.py <trip> <id> [<id> ...]

Run after vlog_build.py --check (it reads the check's report.txt, cues.txt and rows.json). Compares with the copy the
director last watched (work/review/<id>.timeline.json, written by every real build) and prints:
  CHANGE  every shot added, removed or changed and every subtitle changed, with its time, so he can see that only what
          they asked for moved (anything else is a side effect);
  WARN    a changed shot that shakes or runs past its clip (vlog_pick), two pieces of one recording that overlap (the same
          words heard twice), and a word he put back on the editing page that has gone missing since that copy.
vlog_run.py runs it before every render and stops on any WARN until they have seen it (--accept-warn).
"""
import difflib
import glob
import inspect
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402

LINE = re.compile(r"^(\S+) (\w) (\S+?)@([\d.]+) ([\d.]+)s")


def clock(t):
    return f"{int(t // 60)}:{t % 60:05.2f}"


def to_sec(c):
    h, m, s = c.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def shots_now(edl, vid):
    out = []
    for line in (edl / f"{vid}.report.txt").read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if m:
            out.append(dict(t=to_sec(m[1]), kind=m[2], stem=m[3], src=float(m[4]), d=float(m[5]),
                            fx=(re.search(r"fx=(\w+)", line) or [None, ""])[1]))
    return out


def subs_now(edl, vid):
    out = []
    for line in (edl / f"{vid}.cues.txt").read_text(encoding="utf-8").splitlines():
        m = re.match(r"(\S+) (\S+) (Sub|Nar)\s+(.*)$", line)
        if m:
            out.append(dict(s=to_sec(m[1]), e=to_sec(m[2]), text=m[4].replace("\\N", "")))
    return out


def key(s):
    return (s["stem"], round(s["src"], 1), round(s["d"], 1))


def diff_shots(old, new):
    lines = []
    sm = difflib.SequenceMatcher(None, [key(s) for s in old], [key(s) for s in new], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        was = ", ".join(f"{s['stem']}@{s['src']:.1f} {s['d']:.1f}s" for s in old[i1:i2]) or "-"
        now = ", ".join(f"{s['stem']}@{s['src']:.1f} {s['d']:.1f}s" for s in new[j1:j2]) or "-"
        at = clock(new[j1]["t"]) if j1 < len(new) else clock(new[-1]["t"])
        lines.append(f"CHANGE picture {at}: {was}  →  {now}")
    return lines, [new[j] for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal" for j in range(j1, j2)]


def diff_subs(old, new):
    lines = []
    old = [dict(s, text=s["text"].replace("\\N", "")) for s in old]       # a 9:16 line break is not a change
    flat = lambda x: re.sub(r"\s", "", x)
    sm = difflib.SequenceMatcher(None, [flat(s["text"]) for s in old], [flat(s["text"]) for s in new], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        at = clock(new[j1]["s"]) if j1 < len(new) else "end"
        lines.append(f"CHANGE subtitle {at}: {' | '.join(s['text'] for s in old[i1:i2]) or '-'}  →  "
                     f"{' | '.join(s['text'] for s in new[j1:j2]) or '-'}")
    return lines


def lost_putbacks(trip_dir, vid, since):
    """Words put back on the page (voice.json restore) seen in a backup newer than the watched copy, gone now."""
    cur_f = trip_dir / "work" / "subtitles" / f"{vid}.voice.json"
    cur = json.loads(cur_f.read_text(encoding="utf-8")).get("restore", []) if cur_f.exists() else []
    now = {(g["voice"], round(g["from"], 2)) for g in cur}
    seen = {}
    for f in sorted(glob.glob(str(vlog_env.LOCAL / "editor-cache" / "backup" / f"{vid}-2*.voice.json"))):
        if Path(f).stat().st_mtime < since:
            continue
        for g in json.loads(Path(f).read_text(encoding="utf-8")).get("restore", []):
            seen[(g["voice"], round(g["from"], 2))] = g
    return [f"WARN put-back gone: {g.get('words')} ({k[0]} {k[1]:.2f} s, after {g.get('after')}) was put back on the "
            f"editing page and is not any more" for k, g in seen.items() if k not in now]


def overlaps(trip_name, vid):
    import vlog_editor as E
    cls = [c for _, c in inspect.getmembers(E, inspect.isclass) if hasattr(c, "keep") and hasattr(c, "rows")][0]
    t = cls(vlog_env.TRIPS / trip_name)
    rows, _, vd = t.rows(vid)
    out = t.keep(vid, [dict(cid=r["cid"], raw=r["raw"], shown=r["shown"], auto=r["auto"]) for r in rows], vd["restore"],
                 vd["cuts"], keeps=vd["keeps"])
    bad, prev = [], None
    for b in out:
        if prev and prev["voice"] == b["voice"] and b["ranges"] and prev["ranges"] \
                and prev["ranges"][0][0] < b["ranges"][0][0] < prev["ranges"][-1][1] - 0.005:
            bad.append(f"WARN voice twice: {b['voice']} {b['ranges'][0][0]:.2f}-{prev['ranges'][-1][1]:.2f} s is in two pieces")
        prev = b
    return bad


def run(trip_name, vid):
    import vlog_build as B
    import vlog_pick
    trip = B.Trip(trip_name)
    edl = trip.dir / "work" / "edl"
    tl_f = trip.dir / "work" / "review" / f"{vid}.timeline.json"
    out = []
    new_shots, new_subs = shots_now(edl, vid), subs_now(edl, vid)
    if tl_f.exists():
        tl = json.loads(tl_f.read_text(encoding="utf-8"))
        old_shots = [dict(t=s["t"], stem=s["stem"], src=s["src"] if s["src"] is not None else 0.0, d=s["d"]) for s in tl["shots"]]
        old_subs = [dict(s=x["s"], e=x["e"], text=x["text"]) for x in tl["subs"]]
        ls, changed = diff_shots(old_shots, new_shots)
        out += ls + diff_subs(old_subs, new_subs)
        since = tl_f.stat().st_mtime
        out.append(f"# {vid}: compared with the copy built {Path(tl_f).stat().st_mtime and __import__('time').strftime('%m-%d %H:%M', __import__('time').localtime(since))}"
                   f"; {len(new_shots)} shots, {len(new_subs)} subtitles, {new_shots[-1]['t'] + new_shots[-1]['d'] if new_shots else 0:.1f} s")
    else:
        changed, since = new_shots, 0
        out.append(f"# {vid}: no watched copy yet; every shot checked")
    import re as _re
    speakers = set(_re.findall(r'V\("([^"]+)"', (edl / f"{vid}.py").read_text(encoding="utf-8")))
    for s in changed:
        if s["stem"].startswith("P:") or s["stem"] in speakers:
            continue                                    # the speaker's own take sways by nature (as the picture check)
        for line in vlog_pick.check(trip, vid, f"{s['stem']}@{s['src']}+{s['d']}"):
            if line.startswith("WARN") and "already used" not in line:      # reuse is judged on the planned shots, below
                out.append(f"WARN shot {clock(s['t'])}: " + line[5:])
    out += reused(new_shots, changed, speakers)
    out += lookalike(trip, new_shots, changed, speakers)
    out += lost_putbacks(trip.dir, vid, since)
    out += overlaps(trip_name, vid)
    out += flashes(new_shots)
    out += voice_problems(trip, vid, new_subs)
    out += sheet_notes(trip, vid)
    return answered(trip, vid, out)


def wkey(line):
    """A warning without its place in the video (m:ss.xx), so it is the same warning after the cut around it moves."""
    return re.sub(r"\s+", " ", re.sub(r"\b\d+:\d\d\.\d+:?", "", line.split(" ", 1)[1] if " " in line else line)).strip()


def accepted_file(trip, vid):
    return trip.dir / "work" / "review" / f"{vid}.accepted.json"


def answered(trip, vid, lines):
    """Warnings the director has already answered (work/review/<id>.accepted.json) are not asked again (the same half second at 11:50 of v02 was asked three times in one evening). They are still printed, as "OK'd"."""
    f = accepted_file(trip, vid)
    ok = set(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else set()
    return [("OK'd " + x if x.startswith(("WARN", "ASK")) and wkey(x) in ok else x) for x in lines]


def accept(trip, vid, lines, what):
    """Write the director's yes: every open warning whose text holds `what` ("all" = every one) is remembered."""
    f = accepted_file(trip, vid)
    ok = set(json.loads(f.read_text(encoding="utf-8"))) if f.exists() else set()
    new = [wkey(x) for x in lines if x.startswith(("WARN", "ASK")) and (what == "all" or what in x)]
    f.write_text(json.dumps(sorted(ok | set(new)), ensure_ascii=False, indent=1), encoding="utf-8")
    return new


def reused(shots, changed, speakers):
    """A changed shot that shows a stretch of its clip another shot of this video already shows (tell me before rendering). The opening montage previews later shots on purpose; a take carrying on is one shot."""
    out = []
    shown = ("", "toptight", "dim", "zoomin", "faces", "blur", "qr")     # effects that still show the clip's own picture;
    for s in changed:                                                     # a map or CG shot only borrows a clip to draw over
        if s["stem"].startswith("P:") or s["stem"] in speakers or s.get("kind") == "M" or (s.get("fx") or "") not in shown:
            continue
        a, b = s["src"], s["src"] + s["d"]
        for o in shots:
            if o is s or o["stem"] != s["stem"] or o.get("kind") == "M" or (o.get("fx") or "") not in shown:
                continue
            p, q = o["src"], o["src"] + o["d"]
            if min(b, q) - max(a, p) > 0.5:
                out.append(f"WARN shot {clock(s['t'])}: {s['stem']}@{s['src']:.1f} {s['d']:.1f}s shows the same part of the "
                           f"clip as the shot at {clock(o['t'])} ({max(a, p):.1f}-{min(b, q):.1f} s of the clip)")
                break
    return out


def lookalike(trip, shots, changed, speakers):
    """A changed shot that looks like the shot right before or after it (tell me before rendering).
    Judged on a frame from the middle of each shot's stretch of its 720p copy, the picture check's own measure."""
    import vlog_piccheck
    import vlog_trip
    proxy = vlog_env.LOCAL / "trips" / trip.dir.name / "proxy"
    limit = vlog_trip.limit(trip.dir, "similar")
    seen = {}

    def look(s):
        k = (s["stem"], round(s["src"], 1), round(s["d"], 1))
        if k not in seen:
            seen[k] = None
            rel = trip.clips.get(s["stem"], {}).get("file")
            f = (proxy / rel).with_suffix(".mp4") if rel else None
            if f is not None and f.exists() and not (s["fx"] or ""):
                seen[k] = vlog_piccheck.frame(f, s["src"] + s["d"] / 2)
        return seen[k]

    import cv2
    out, told = [], set()
    for s in changed:
        k = next(i for i, x in enumerate(shots) if x is s)
        for j in (k - 1, k + 1):
            if not 0 <= j < len(shots) or (min(j, k), max(j, k)) in told:
                continue
            o = shots[j]
            first, second = (o, s) if j < k else (s, o)
            if first["stem"] == second["stem"] and abs(first["src"] + first["d"] - second["src"]) < 1.0:
                continue                                # the same take carrying on
            if any(x["stem"].startswith("P:") or x["stem"] in speakers or x.get("kind") == "M" for x in (s, o)):
                continue
            fa, fb = look(first), look(second)
            if fa is None or fb is None:
                continue
            c = float(cv2.compareHist(fa, fb, cv2.HISTCMP_CORREL))
            if c > limit:
                told.add((min(j, k), max(j, k)))
                out.append(f"WARN shot {clock(second['t'])}: {second['stem']}@{second['src']:.1f} looks like the shot before "
                           f"it ({first['stem']}@{first['src']:.1f}, similarity {c:.2f})")
    return out


def sheet_notes(trip, vid):
    """The director's notes written in the subtitle sheet in brackets - (..) / （..） - are instructions to Claude; the
    build strips them from the screen, so without this they are never seen ("(I hear 你可以用这样子, which
    is diff with what I want)" sat in v02's sheet since 11-13). Each one is asked about until it is marked handled in
    work/review/<id>.sheet-notes-done.json ({"<row id>": "<the note>"} - Claude adds it once the director has agreed)."""
    import vlog_sheet
    x = trip.dir / "work" / "subtitles" / f"{vid}.xlsx"
    done_f = trip.dir / "work" / "review" / f"{vid}.sheet-notes-done.json"
    done = json.loads(done_f.read_text(encoding="utf-8")) if done_f.exists() else {}
    out = []
    for r in vlog_sheet.read_xlsx(x) if x.exists() else []:
        for note in re.findall(r"[（(]([^）)]*)[）)]?", r[3]):
            if note.strip() and done.get(r[1]) != note.strip():
                out.append(f"ASK sheet note {r[1]} ({r[0]}): {note.strip()}")
    return out


def flashes(shots):
    """A shot under vlog_build.FLASH that jumps to other picture (not the same clip carrying on) - before rendering
    (v02 7:48 C0417 0.59 s was found only after the final, among 64 notes)."""
    import vlog_build as B
    out = []
    for k, s in enumerate(shots):
        if s["d"] >= B.FLASH:
            continue
        prv = shots[k - 1] if k else None
        nxt = shots[k + 1] if k + 1 < len(shots) else None
        if (prv and prv["stem"] == s["stem"] and abs(prv["src"] + prv["d"] - s["src"]) < 0.3) or                 (nxt and nxt["stem"] == s["stem"] and abs(s["src"] + s["d"] - nxt["src"]) < 0.3):
            continue                                    # the same take carrying on, before or after: no jump
        out.append(f"WARN shot {clock(s['t'])}: {s['stem']}@{s['src']:.1f} only {s['d']:.2f} s on screen (flash)")
    return out


def voice_problems(trip, vid, subs):
    """The edit check (kept word not heard, cut word still heard, voice lost, time cut still heard) on the plan, before
    rendering - it needs no video (run only after renders, so its finds cost a render)."""
    import vlog_editcheck
    import vlog_editor as E
    cls = [c for _, c in inspect.getmembers(E, inspect.isclass) if hasattr(c, "keep") and hasattr(c, "rows")][0]
    items = vlog_editcheck.check(cls(trip.dir.name), vid)
    out = []
    for it in items:
        text = it if isinstance(it, str) else " ".join(str(v) for v in (it.values() if isinstance(it, dict) else it))
        out.append(f"WARN voice {text}")
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = sys.argv[1:]
    what = None
    if "--accept" in args:                              # vlog_precheck.py <trip> <id> --accept "<words of the warning>" | all
        k = args.index("--accept")
        what = args[k + 1]
        del args[k:k + 2]
    warn = False
    for v in args[1:]:
        lines = run(args[0], v)
        if what is not None:
            import vlog_build as B
            for x in accept(B.Trip(args[0]), v, lines, what):
                print(f"remembered as answered ({v}): {x}")
            lines = run(args[0], v)
        warn |= any(x.startswith(("WARN", "ASK")) for x in lines)
        print("\n".join(lines))
    sys.exit(2 if warn else 0)
