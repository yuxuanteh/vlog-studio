"""zh / en / ja subtitle files for upload, from the final render's own subtitle track (they were never
exported; the v02 teaser's were made by hand on the night it went out).

    python vlog_srt.py <trip> <id>

1. Reads <local>/render/<trip>/<id>/subs.ass (the final; falls back to <id>-phone) - the Chinese exactly as burned in,
   at the exact times.
2. Writes the spoken-language srt into publish/ (long: publish/subtitles.<lang>_<COUNTRY>.srt; short:
   publish/short/short.<lang>_<COUNTRY>.srt: the name shape Facebook asks for, vlog_env.srt_name).
3. Keeps work/subtitles/<id>.translate.tsv (start, end, zh, en, ja). New cues are added with en / ja empty; Claude
   fills them by the translation golden rule (same meaning, natural, not word for word; a line break is written \\n).
4. When every row has en and ja, writes the en / ja srt next to the zh one. If the burned-in Chinese changed since a
   row was translated, it STOPS and lists the rows, so a translation never sits under different words.
"""
import csv
import re
import sys

import vlog_env

STYLES = ("Sub", "Nar")
# the spoken language and the translated subtitle files the channel wants ([language] in vlog.toml)
SRC = vlog_env.NARRATION[:2] if vlog_env.NARRATION[:2] != "zh" else "zh"
TR = [x for x in (vlog_env.LANG.get("subtitle_second", ""), vlog_env.LANG.get("subtitle_third", "")) if x and x != SRC]


def cues(ass):
    out = []
    for line in ass.read_text(encoding="utf-8").splitlines():
        m = re.match(r"Dialogue: \d+,([\d:.]+),([\d:.]+),(\w+),(.*)$", line)
        if m and m[3] in STYLES:
            out.append((m[1], m[2], re.sub(r"\{[^}]*\}", "", m[4]).replace("\\N", "\n")))
    return out


def srt_time(t):
    h, mi, s = t.split(":")
    ms = round(float(s) * 1000)
    return f"{int(h):02d}:{int(mi):02d}:{ms // 1000:02d},{ms % 1000:03d}"


def write_srt(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{t}\n" for i, (a, b, t) in enumerate(rows, 1)),
                    encoding="utf-8")
    print("wrote", path)


def main(trip, eid):
    rd = vlog_env.LOCAL / "render" / trip
    ass = next((p for p in (rd / eid / "subs.ass", rd / f"{eid}-phone" / "subs.ass") if p.exists()), None)
    if ass is None:
        sys.exit(f"STOP: no render of {eid} yet (no subs.ass)")
    if "phone" in ass.parent.name:
        print("note: no final render yet; timing from the phone build (same edit, same times)")
    cs = cues(ass)
    tdir = vlog_env.TRIPS / trip
    edl = (tdir / "work" / "edl" / f"{eid}.py").read_text(encoding="utf-8")
    m = re.search(r"^W, H = (\d+), (\d+)", edl, re.M)
    tall = m and int(m[2]) > int(m[1])
    video = (re.search(r'^VIDEO = "([^"]+)"', edl, re.M) or [None, None])[1]
    if not video:
        video = next(p.name for p in (tdir / "videos").iterdir() if p.name.startswith(eid.split("-")[0]))
    pub = tdir / "videos" / video / "publish"
    out = (lambda lang: pub / "short" / vlog_env.srt_name(lang, short=True)) if tall else (lambda lang: pub / vlog_env.srt_name(lang))
    write_srt(out(SRC), cs)

    tsv = tdir / "work" / "subtitles" / f"{eid}.translate.tsv"
    old = {}
    if tsv.exists():
        with tsv.open(encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                old.setdefault(r[SRC], r)
    rows, stale = [], []
    for a, b, zh in cs:
        key = zh.replace("\n", "\\n")
        r = old.get(key, {})
        rows.append({"start": a, "end": b, SRC: key, **{lang: r.get(lang, "") for lang in TR}})
    gone = [k for k in old if k not in {r[SRC] for r in rows}]
    if gone:
        stale = gone
    with tsv.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["start", "end", SRC, *TR], delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    todo = [r for r in rows if any(not r[lang] for lang in TR)]
    if stale:
        print(f"note: {len(stale)} translated row(s) no longer match the burned-in subtitles and were dropped:")
        for k in stale:
            print("   ", k)
    if todo:
        sys.exit(f"STOP: {len(todo)} row(s) of {tsv.name} still need {' / '.join(TR)}; fill them, then run again")
    for lang in TR:
        write_srt(out(lang), [(r["start"], r["end"], r[lang].replace("\\n", "\n")) for r in rows])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
