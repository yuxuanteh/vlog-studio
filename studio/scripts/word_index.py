"""Exact word times for voice sources, so cuts go from one word to another. Run once per source.

Usage: python word_index.py <trip> <stem> [<stem> ...]
Writes <trip>/work/words/<stem>.json (list of [start, end, word, probability]) and <stem>.txt (readable, one phrase per line).
"""
import json
import sys

import numpy as np

import vlog_env
import whisper_run


def path_of(trip, stem):
    rows = json.loads((trip / "work" / "footage-index.json").read_text(encoding="utf-8"))
    rel = next(c["file"] for c in rows if (c.get("stem") or c["file"].rsplit("\\", 1)[-1].rsplit(".", 1)[0]) == stem)
    return trip / "raw" / rel


def main():
    trip = vlog_env.TRIPS / sys.argv[1]
    out = trip / "work" / "words"
    out.mkdir(exist_ok=True)
    for stem in sys.argv[2:]:
        f = out / f"{stem}.json"
        if f.exists():
            continue
        audio = whisper_run.decode(path_of(trip, stem))
        res, _ = whisper_run.run(audio)
        words, lines = [], []
        for s in res["segments"]:
            words += [[round(w["start"], 3), round(w["end"], 3), w["word"], round(w["p"], 3)] for w in s["words"]]
            lines.append(f"{s['start']:8.2f} " + " ".join(f"{w['word']}" for w in s["words"]))
        f.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
        (out / f"{stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        print(stem, len(words), "words", flush=True)


if __name__ == "__main__":
    main()
