"""Start a trip, or a video of a trip, with the folders and edit lists the tools expect.

    python vlog_new.py trip <trip>                                   e.g. 2026-05-kyoto
        -> <trips>/<trip>/raw/ (put the footage here, in day / place folders as far as you can), work/, videos/,
           decisions.md (the one checklist of the trip), work/trip-settings.json
    python vlog_new.py video <trip> <vNN-slug> [--format wide|tall|both]   e.g. v01-old-town
        -> work/edl/<vNN-slug>.py (16:9) and / or work/edl/<vNN-slug>-short.py (9:16), empty edit lists to fill in
           (no --format: [formats] default in vlog.toml, which holds what the channel makes)

The edit list is a small Python file of blocks (see vlog_build.py's first lines, or the skill's editing reference).
"""
import datetime
import json
import re
import sys

import vlog_env

L = vlog_env.tr
EDL = '''# {title}
# Spine: (the one question this video answers at the end, in the viewer's words)
W, H = {w}, {h}
VIDEO = "{video}"
BLOCKS = [
    # V("<recording>", from, to, ["<clip>@<second>+<length>", ...], cap="place tag")   your voice over pictures
    # S(["<clip>@<second>+<length>"], gain=0.9)                                        pictures with their own sound
    # M([...])  montage on music    T("title", [...])  title moment    E([...])  end card, 12 s (16:9 only)
]
TRACKS = []            # music: [(block number, "Track Title"), ...]; empty = no music
'''


def trip(name):
    d = vlog_env.TRIPS / name
    if (d / "work").exists():
        raise SystemExit(f"{d} already exists")
    for sub in ("raw", "work/edl", "work/story", "videos"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    steps = [
        L("1 Plan: sources, shot list, talking points → approved (skip for footage you already have)", "1 行程计划：资料、拍摄清单、现场要讲的 → 确认（已经拍好的素材可以跳过）"),
        L("2 Filming, with a recap every evening (skip for footage you already have)", "2 拍摄，每天晚上录感想（已经拍好的素材可以跳过）"),
        L("3 Index, look through the footage, video plan → approved", "3 素材总表、看过素材、影片计划 → 确认"),
        L("4 Viewer questions, facts, a story plan per video → approved", "4 观众的问题、事实核查、每支影片的故事计划 → 确认"),
        L("5 Lines to re-record (only what the footage lacks) → approved", "5 要补录的句子（只补素材没有的）→ 确认"),
        L("6 Re-recording and intake", "6 补录、整理录音"),
        L("7 First cut (checking copy) → approved: story and pacing locked", "7 初剪（检查版）→ 确认：故事和节奏锁定"),
        L("8 Cut with music, place tags, privacy pass → approved", "8 加配乐、地点标签、隐私检查 → 确认"),
        L("9 Final, translated subtitles, upload package per platform → approved", "9 成片、翻译字幕、各平台的上传包 → 确认"),
    ]
    (d / "decisions.md").write_text(
        f"# {name}\n\n" + L("## Progress (tick only after approval)", "## 进度（确认后才打勾）") + "\n"
        + "\n".join(f"- [ ] {s}" for s in steps) + "\n\n" + L("## Decisions", "## 决定记录") + f"\n- {today} " + L("trip opened.", "开这一趟。") + "\n",
        encoding="utf-8")
    (d / "work" / "trip-settings.json").write_text(json.dumps({
        "note": "This trip's own settings. fixes: words the speech model mishears on this trip [[heard, meant]]; words: names a Chinese "
                "word splitter keeps whole; take_labels: words said only to label a take; meta: things said to the editor, not the "
                "viewer (cut by default); raw_mirrors: local copies of raw/ on this computer; limits: this trip's own shake limits.",
        "fixes": [], "words": [], "take_labels": [], "meta": [], "raw_mirrors": [], "limits": {}}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"created {d}\nput the footage into {d / 'raw'} (day / place folders as far as you can), then: python footage_index.py {name}")


def video(trip_name, vid, fmt):
    d = vlog_env.TRIPS / trip_name / "work" / "edl"
    if not d.parent.exists():
        raise SystemExit(f"no trip {trip_name}: python vlog_new.py trip {trip_name}")
    if not re.fullmatch(r"v\d{2}-[a-z0-9]+(-[a-z0-9]+)*", vid):
        raise SystemExit("a video id is v + two digits + a lower-case english slug, e.g. v01-old-town")
    d.mkdir(parents=True, exist_ok=True)
    fmt = fmt or vlog_env.FORMATS.get("default", "wide")
    made = []
    for kind, name, (w, h) in (("wide", vid, (1920, 1080)), ("tall", f"{vid}-short", (1080, 1920))):
        if fmt not in (kind, "both"):
            continue
        f = d / f"{name}.py"
        if f.exists():
            print(f"exists, kept: {f}")
            continue
        f.write_text(EDL.format(title=f"{name} ({'16:9' if kind == 'wide' else '9:16'})", w=w, h=h, video=vid), encoding="utf-8")
        made.append(str(f))
    (vlog_env.TRIPS / trip_name / "videos" / vid / "preview").mkdir(parents=True, exist_ok=True)
    (vlog_env.TRIPS / trip_name / "videos" / vid / "publish").mkdir(parents=True, exist_ok=True)
    print("\n".join(f"created {m}" for m in made) or "nothing new")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    fmt = next((sys.argv[i + 1] for i, x in enumerate(sys.argv) if x == "--format" and i + 1 < len(sys.argv)), None)
    a = [x for x in a if x != fmt]
    if len(a) == 2 and a[0] == "trip":
        trip(a[1])
    elif len(a) == 3 and a[0] == "video":
        video(a[1], a[2], fmt)
    else:
        print(__doc__)
