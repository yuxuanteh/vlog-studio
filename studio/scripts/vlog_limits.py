r"""This trip's footage against the default limits (limits were tuned on one trip; at the
start of each trip's edit, measure the trip and tell the director before any limit changes).

    python vlog_limits.py <trip>

Reads work/motion/*.json (clip_motion.py) and clip-scores.json; prints how many clips / seconds sit above each shake
limit, against the default limits, and what the limits would be at the same share of footage. Nothing changes:
a trip's own limits go into work/trip-settings.json "limits" only after the director agrees.
"""
import json
import sys

import numpy as np

import vlog_env
import vlog_trip

NAGOYA = {"clips_avg_above_stab": 0.36, "seconds_above_warn": 0.18, "seconds_above_violent": 0.12}   # measured on its 645 clips


def main(trip):
    d = vlog_env.TRIPS / trip
    secs, avg = [], []
    for f in (d / "work" / "motion").glob("*.json"):
        sh = json.loads(f.read_text(encoding="utf-8")).get("shake") or []
        if sh:
            secs += sh
            avg.append(float(np.mean(sh)))
    if not secs:
        raise SystemExit("no motion files yet (run clip_motion.py)")
    secs, avg = np.array(secs), np.array(avg)
    L = {k: vlog_trip.limit(d, k) for k in ("shake_stab", "shake_warn", "shake_violent")}
    share = {"clips_avg_above_stab": float((avg > L["shake_stab"]).mean()),
             "seconds_above_warn": float((secs >= L["shake_warn"]).mean()),
             "seconds_above_violent": float((secs >= L["shake_violent"]).mean())}
    print(f"{trip}: {len(avg)} clips, {len(secs)} seconds measured; limits now {L}")
    for k, v in share.items():
        ref = NAGOYA[k]
        flag = "  <- very different from an earlier trip: tell the director" if v > 2 * ref or v < ref / 2 else ""
        print(f"  {k}: {v * 100:.0f}% (an earlier trip {ref * 100:.0f}%){flag}")
    print(f"  limits at an earlier trip's shares: shake_warn {np.quantile(secs, 1 - NAGOYA['seconds_above_warn']):.2f}, "
          f"shake_violent {np.quantile(secs, 1 - NAGOYA['seconds_above_violent']):.2f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main(sys.argv[1])
