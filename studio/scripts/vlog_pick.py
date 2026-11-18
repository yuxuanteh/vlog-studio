r"""Check the director's own picks before they go into an edit list ("everytime i tell you to use
a specific clip or time, warn me about shaking, too short for the timeline, etc. — I may miss these details").

    python vlog_pick.py <trip> <video id> "C0086@0+3.2" ["C0081@1=+3.2" ...]

For each pick: the clip's length and whether the shot fits in it; the shaking (work/motion, the same measure and limit
the build's shake avoider uses) second by second over the shot, and the calmest start nearby if it shakes; the same
stretch already used elsewhere in this video's edit list; a shot under the build's 2.5 s minimum for talking blocks.
Every line that needs the director's eye starts with "WARN". Nothing is changed.
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_build as B  # noqa: E402
import vlog_trip  # noqa: E402



def used_elsewhere(trip, vid, stem, a, b):
    """(line, start, end) of every other use of this clip in the edit list that overlaps a..b."""
    out = []
    edl = (trip.dir / "work" / "edl" / f"{vid}.py").read_text(encoding="utf-8").splitlines()
    for n, line in enumerate(edl, 1):
        if line.lstrip().startswith("#"):
            continue
        for p in re.findall(r'"([^"]*)"', line):
            try:
                it = B.parse_pic(p)
            except SystemExit:
                continue
            if it["stem"] != stem:
                continue
            s = it["start"]
            e = s + (it["fixed"] or 4.0)
            if s < b and e > a:
                out.append((n, s, e, p))
    return out


def check(trip, vid, pick):
    it = B.parse_pic(pick)
    stem, s, d = it["stem"], it["start"], it["fixed"]
    lines = []
    if stem.startswith("P:"):
        return [f"{pick}: photo, nothing to check"]
    try:
        L = trip.length(stem)
    except Exception as e:                   # noqa: BLE001
        return [f"WARN {pick}: clip not found ({e})"]
    room = L - s - 0.05
    span = d if d else room
    lines.append(f"{pick}: clip {L:.1f} s, from {s:.1f} s there are {room:.1f} s")
    if d and d > room:
        lines.append(f"WARN {pick}: wants {d:.1f} s but the clip ends {room:.1f} s after {s:.1f} s")
    if d and d < B.MIN_SHOT:
        lines.append(f"  note: {d:.1f} s is under the {B.MIN_SHOT} s minimum for a talking block "
                     f"(fine in a breathing / montage block)")
    f = trip.dir / "work" / "motion" / f"{stem}.json"
    SHAKE = vlog_trip.limit(trip.dir, "shake_violent")      # = calm_starts in the build
    if f.exists():
        sh = json.loads(f.read_text(encoding="utf-8"))["shake"]
        win = sh[int(s):max(int(s) + 1, int(s + span + 0.999))]
        worst = max(win or [0])
        lines.append(f"  shake per second {int(s)}-{int(s + span + 0.999)} s: {' '.join(f'{x:.1f}' for x in win)}")
        if worst >= SHAKE:
            bad = [int(s) + k for k, x in enumerate(win) if x >= SHAKE]
            calm = [c / 4 for c in range(0, int((L - span) * 4) + 1)
                    if max(sh[int(c / 4):max(int(c / 4) + 1, int(c / 4 + span + 0.999))] or [0]) < SHAKE]
            near = min(calm, key=lambda c: abs(c - s)) if calm else None
            lines.append(f"WARN {pick}: shaking at {', '.join(f'{x} s' for x in bad)}"
                         + (f"; calmest start nearby {near:.2f} s" if near is not None else "; no calm stretch this long"))
    else:
        lines.append(f"  (no motion file for {stem}: shaking not measured)")
    for n, a, b, p in used_elsewhere(trip, vid, stem, s, s + span):
        if abs(a - s) > 0.01:                          # the pick's own line (already in the list) starts where it does
            lines.append(f"WARN {pick}: the same stretch is already used on line {n} ({p}, {a:.1f}-{b:.1f} s)")
    return lines


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    trip = B.Trip(sys.argv[1])
    for pk in sys.argv[3:]:
        print("\n".join(check(trip, sys.argv[2], pk)))
