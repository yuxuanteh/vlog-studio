r"""Edge-case tests for the trip pipeline: every bug we have hit gets a case here, so it cannot come back unseen
(robustness work). Runs in well under a minute, no rendering.

    python vlog_selftest.py

Run it after any change to a script in this folder; vlog_run.py runs it before every render.
"""
import json

import numpy as np
import re
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

import os

os.environ["VLOG_SELFTEST"] = "1"      # the cases are written with Chinese lines: run them as a Chinese studio
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402
import vlog_layout  # noqa: E402

RESULTS = []


def case(fn):
    try:
        fn()
        RESULTS.append((fn.__name__, None))
    except Exception as e:                       # a failed case is reported, the others still run
        RESULTS.append((fn.__name__, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=2)}"))
    return fn


# ---------------------------------------------------------------- layout: one home for sizes
@case
def frames_and_finals():
    assert vlog_layout.frame("phone", 1920, 1080) == (854, 480)
    assert vlog_layout.frame("phone", 1080, 1920) == (480, 854)
    # vlog_build rendered long finals at 1920x1080 while the rule (and vlog_cut) said 4K
    assert vlog_layout.frame("final", 1920, 1080) in ((3840, 2160), (1920, 1080))     # the channel's choice
    assert vlog_layout.frame("final", 1080, 1920) == (1080, 1920)
    assert vlog_layout.sub_chars(1920, 1080) == 20 and vlog_layout.sub_chars(1080, 1920) == 24


@case
def no_size_typed_twice():
    """No script outside vlog_layout types a frame size or a style's size again."""
    bad = []
    for f in HERE.glob("vlog_*.py"):
        if f.name in ("vlog_layout.py", "vlog_selftest.py"):
            continue
        s = f.read_text(encoding="utf-8")
        for pat in (r"\(854, 480\)", r"\(480, 854\)", r"\(3840, 2160\)", r"24 if .*vertical.* else 20",
                    r"size \* 0\.(4|46|62|36):", r"H // 14 if"):
            if re.search(pat, s):
                bad.append(f"{f.name}: {pat}")
    assert not bad, bad


# ---------------------------------------------------------------- subtitles and overlays
import vlog_build as B  # noqa: E402


@case
def source_line_break_marks():
    r"""edit lists write the break as \N; the plate code looked for a newline and drew one line."""
    font = B.ass_font("LXGWWenKai-Medium.ttf", 14)
    assert B.wrap_px("第一行\\N第二行", font, 400) == ["第一行", "第二行"]
    assert B.wrap_px("第一行\n第二行", font, 400) == ["第一行", "第二行"]


@case
def source_line_fits_9x16():
    """The long v02-teaser source line must wrap inside a 480 px frame and its plate must hug both lines."""
    W, H = 480, 854
    text = "手机版（CentX）只能在名铁名古屋站、犬山站进出；纸本版可以坐到犬山遊園\\N来源：名古屋铁道（2026 查阅）"
    B.TEXT_WARN.clear()
    out = Path(tempfile.gettempdir()) / "selftest.ass"
    B.write_ass(out, [("Src", 1.0, 5.0, text)], W, H)
    ass = out.read_text(encoding="utf-8")
    assert not B.TEXT_WARN, B.TEXT_WARN
    plate = re.search(r",Plate,.*?\\p1\}(m [^{]+)\{", ass)[1]
    xs = [float(v) for v in re.findall(r"(-?[\d.]+) -?[\d.]+", plate)]
    assert min(xs) >= 0 and max(xs) <= W, f"plate leaves the frame: {plate}"
    assert len(re.findall(r" l ", plate)) >= 5, "plate should step around 2+ lines"


@case
def boxed_text_too_wide_is_reported():
    B.TEXT_WARN.clear()
    B.write_ass(Path(tempfile.gettempdir()) / "selftest2.ass", [("Cap", 1.0, 3.0, "这" * 40)], 480, 854)
    assert B.TEXT_WARN, "a place tag wider than a 9:16 frame was not reported"


@case
def source_line_after_a_place_tag():
    """the style table and the fit check shared a name; a source line after a place tag crashed."""
    B.write_ass(Path(tempfile.gettempdir()) / "selftest3.ass",
                [("Cap", 1.0, 3.0, "爱知县 · 犬山"), ("Src", 4.0, 6.0, "来源：某某（2026）")], 1920, 1080)


@case
def plus_joins_across_recordings():
    ev = [("Sub", 0.0, 1.0, "我去了犬山＋"), ("Sub", 1.2, 2.0, "城下町"), ("Sub", 3.0, 4.0, "＋走了一圈"), ("Cap", 0, 1, "x")]
    subs = [e for e in B.join_marks(ev) if e[0] == "Sub"]
    assert [s[3] for s in subs] == ["我去了犬山城下町走了一圈"], subs


def W_(s, e, t):                                   # a word as the build holds it: (start, end, text, whisper start, end)
    return (s, e, t, s, e)


@case
def subtitles_follow_the_sheet_exactly():
    """short rows were joined to a neighbour and a / inside one Whisper word did not split."""
    ws = [W_(0.0, 0.4, "都是"), W_(0.4, 0.6, "人"), W_(1.0, 2.0, "晚上的时候")]
    out = B.retime([(ws[:2], "都是人"), (ws[2:], "晚上的时候")], 18)
    assert [c[2] for c in out] == ["都是人", "晚上的时候"], out          # a 3-letter row stays its own subtitle
    out = B.retime([([W_(0.0, 1.2, "这些地方所以")], "这些地方/所以")], 18)
    assert [c[2] for c in out] == ["这些地方", "所以"], out              # / splits inside one word
    assert out[0][1] <= out[1][0] + 1e-6 and out[1][0] > 0.5, out       # each part on its own letters' time
    out = B.retime([([W_(0.0, 1.0, "一二三四")], "一二三四"), ([W_(1.0, 1.4, "五")], "五〇")], 18)
    assert [c[2] for c in out] == ["一二三四", "五〇"], out              # typed text keeps its place
    ws = [W_(0.0, 0.8, "马来西亚的"), W_(0.8, 1.0, "S"), W_(1.0, 1.2, "K"), W_(1.2, 2.0, "发生的")]
    out = B.retime([(ws, "Malaysia Segamat发生的")], 18)
    assert out[0][0] == 0.0, out                                         # English typed over Chinese starts on time


@case
def subtitle_audit_reports_order_and_gaps():
    sheet = [(0, "a@0", "", "一二三/四五", "", ""), (0, "a@2", "", "六七", "", "")]
    ev = [("Sub", 0.0, 1.0, "一二三"), ("Sub", 1.0, 2.0, "四五"), ("Sub", 2.0, 3.0, "六七")]
    assert B.sub_audit(ev, sheet, []) == []
    bad = B.sub_audit([("Sub", 0.0, 2.0, "一二三四五"), ("Sub", 2.0, 3.0, "六七")], sheet, [])
    assert bad and bad[0].startswith("SUB ORDER"), bad
    rows = [dict(kw=[(3.2, 3.9, "八九")])]
    bad = B.sub_audit(ev, sheet, rows)
    assert any(x.startswith("SUB GAP") for x in bad), bad


@case
def pinned_starts_and_set_lengths_stay():
    """the director's "start from 4.0 s" slid to 0.2 s (shake avoider), and a 1.5 s QR shot swallowed the
    next shot because the planner dropped shots under 2.5 s each."""
    p = B.parse_pic("C0106@4=+6>12.5^!qr")
    assert (p["start"], p["fixed"], p["anchor"], p["stab"], p["fx"], p["pinned"]) == (4.0, 6.0, 12.5, "^", "qr", True), p
    assert not B.parse_pic("C0106@4+6")["pinned"] and B.parse_pic("P:DSC08547+5")["stem"] == "P:DSC08547"

    class T:
        def length(self, stem):
            return 20.0
    items = [dict(stem="A", start=8.8, fixed=1.5, speed=1.0), dict(stem="B", start=3.5, fixed=6.0, speed=1.0)]
    got = B.share(T(), items, 4.2, B.MIN_SHOT)
    assert [it["stem"] for it in got] == ["A", "B"] and abs(got[0]["d"] - 1.5) < 0.01, got


@case
def same_recording_never_plays_twice():
    """啦 twice at 12:11, a piece began 0.13 s before the piece before it (same recording) stopped."""
    src = (HERE / "vlog_build.py").read_text(encoding="utf-8")
    assert 'pv[1] < a < pv[2]' in src and 'b["_prev"] = (pb["voice"], pb["a"], pb["b"])' in src
    assert 'b["_prev"]' in (HERE / "vlog_editor.py").read_text(encoding="utf-8")   # the page plays the same


def heard_python(s):
    t = B.norm_marks(s)
    return re.sub(r"〔[^〕]*〕", "", t)


def heard_page(samples):
    html = (HERE / "editor" / "index.html").read_text(encoding="utf-8")
    fn = re.search(r"function parse\(shown\)\{.*?\n\}", html, re.S)[0]
    js = fn + "\nconst S = " + json.dumps(samples, ensure_ascii=False) + ";\n" \
        "console.log(JSON.stringify(S.map(s => parse(s).filter(c => !c.cut && !c.note).map(c => c.ch).join(''))));"
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, encoding="utf-8", timeout=60)
    return json.loads(out.stdout)


@case
def page_and_build_hear_the_same():
    """The editing page (JavaScript) and the build (Python) each read 〔〕 [] （） marks: same words heard, every case."""
    samples = ["我〔其实〕去了", "我[其实]去了", "我［其实］去了", "我去了（这里拍到）犬山", "我去了(note)犬山",
               "〔开头剪掉〕后面留", "后面〔一直剪到最后", "笔记没关（到最后", "a（b〔c）d〕e", "〔ab（c）d〕e", "（a[b]c）d"]
    page = heard_page(samples)
    diff = [(s, p, heard_python(s)) for s, p in zip(samples, page) if p != heard_python(s)]
    assert not diff, "page vs build: " + "; ".join(f"{s!r}: page {p!r}, build {b!r}" for s, p, b in diff)


# ---------------------------------------------------------------- effects
import vlog_ff  # noqa: E402,F811
import vlog_fx  # noqa: E402


@case
def every_effect_in_the_edit_lists_exists():
    """the effect table was typed by hand and had no earth1 / earth2 (v01 would have crashed). Each trip's
    edit lists may use the shared effects and that trip's own work/fx.py."""
    for trip_dir in [p for p in vlog_env.TRIPS.iterdir() if (p / "work" / "edl").is_dir()]:
        fx = set(vlog_fx.table(trip_dir))
        used = set()
        for edl in (trip_dir / "work" / "edl").glob("*.py"):
            used |= {m.split(":")[0] for m in re.findall(r"!([a-z0-9_]+(?::[\d.]+)?)", edl.read_text(encoding="utf-8"))}
        assert used <= fx, f"{trip_dir.name}: edit lists use effects that don't exist: {sorted(used - fx)}"


@case
def every_name_used_exists():
    """apply() used "arg" after the line setting it was lost; found only by a render. vlog_lint reads every
    script's symbol tables (and each trip's work/fx.py)."""
    import vlog_lint
    files = sorted(HERE.glob("*.py")) + sorted(vlog_env.TRIPS.glob("*/work/fx.py"))
    bad = [(f.name, x) for f in files for x in vlog_lint.check(f)]
    assert not bad, f"undefined names: {bad[:8]}"


@case
def every_effect_runs_through_apply():
    """apply() lost the line that splits "slipend:7.23" and every plain effect crashed in the v02 phone
    build. Each plain (not tracked) effect an edit list uses, with its argument, is run once on a tiny clip."""
    clip = Path(tempfile.gettempdir()) / "selftest-fx.mp4"
    vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=320x180:rate=30:duration=0.2",
                 "-pix_fmt", "yuv420p", str(clip)], check=True, timeout=60)
    for trip_dir in [p for p in vlog_env.TRIPS.iterdir() if (p / "work" / "edl").is_dir()]:
        tracked = set(vlog_fx.tracked(trip_dir))
        used = set()
        for edl in (trip_dir / "work" / "edl").glob("*.py"):
            used |= set(re.findall(r"!([a-z0-9_]+(?::[\d.]+)?)", edl.read_text(encoding="utf-8")))
        for fx in sorted(used):
            if fx.split(":")[0] in tracked:
                continue
            out = Path(tempfile.gettempdir()) / f"selftest-fx-{fx.replace(':', '_')}.mp4"
            vlog_fx.apply(fx, clip, out, 320, 180, trip_dir)
            assert out.exists() and out.stat().st_size > 0, f"{trip_dir.name}: effect {fx} wrote nothing"


@case
def every_tracked_effect_renders_through_segment():
    """the ticket's drawing crashed in the v02 phone build (64-bit corners) - the tests had run the analyse
    half only. The first use of each tracked effect in each trip's edit lists goes through the real segment() at a small
    size; the analysis is shared with every size and cached, so this is quick after the first run."""
    import vlog_build as VB
    for trip_dir in [p for p in vlog_env.TRIPS.iterdir() if (p / "work" / "edl").is_dir()]:
        tracked = set(vlog_fx.tracked(trip_dir))
        trip_ = VB.Trip(trip_dir.name)
        seen = set()
        for edl in sorted((trip_dir / "work" / "edl").glob("*.py")):
            steady = "vidstab" if 'STEADY = "vidstab"' in edl.read_text(encoding="utf-8") else ""
            for pic in re.findall(r'"([^"]+![a-z0-9_]+[^"]*)"', edl.read_text(encoding="utf-8")):
                it = VB.parse_pic(pic)
                if it["fx"] not in tracked or it["fx"] in seen or it["stem"].startswith("P:"):
                    continue
                seen.add(it["fx"])
                it.update(d=min(it["fixed"] or 2.0, 2.0), steady=steady)
                out = VB.segment(trip_, it, 320, 180, [], vlog_env.LOCAL / "selftest" / "segtest-small")
                assert out.exists() and out.stat().st_size > 0, f"{trip_dir.name}: {pic} wrote nothing"


@case
def tracked_effects_analyse_once_and_match_at_every_size():
    """the QR blur worked at 1920 and 854 but not on 3840-wide frames. Now steadying and tracking are worked
    out once on the analysis-size frames (vlog_build.analysis) and drawn at any size from the same fractions."""
    import cv2
    assert "qr" in set(vlog_fx.tracked(None))
    src = (HERE / "vlog_build.py").read_text(encoding="utf-8")
    assert 'vlog_layout.frame("edit", W, H)' in src and "def analysis(" in src
    seg = src.split("def segment(")[1].split("SEG_CODE =")[0]
    assert "vidstab=legacy and stab" in seg and 'legacy = it.get("steady") == "vidstab"' in seg,         "ffmpeg steadying only for a video approved with it (edit list STEADY = \"vidstab\")"
    full = vlog_env.LOCAL / "selftest" / "qr-full-graded.mp4"       # C0073 8.8-13.1 s, graded, at the edit size
    if full.exists():
        fsf = vlog_fx.frames(full)
        data = vlog_fx.analyse_qr([f.copy() for f in fsf[:45]])     # the 1.5 s shot: every frame has its corners
        assert all(q is not None for q in data["quads"]), "a frame of the QR shot has no blur"
        # the same corners drawn at phone size and at 4K land on the same place (fractions)
        q = np.float32(data["quads"][20])
        small = vlog_fx.draw_qr(cv2.resize(fsf[20], (854, 480)), 20, data, 854, 480)
        big = vlog_fx.draw_qr(cv2.resize(fsf[20], (3840, 2160)), 20, data, 3840, 2160)
        d = np.abs(cv2.resize(big, (854, 480), interpolation=cv2.INTER_AREA).astype(int) - small.astype(int)).mean()
        assert d < 6, f"the blur differs between phone and 4K ({d:.1f})"
        try:                                     # the old 4.2 s shot (the code lost from 10.3 s): must stop the build
            vlog_fx.analyse_qr([f.copy() for f in fsf])
            raise AssertionError("a QR shot with frames it cannot follow was let through")
        except SystemExit as e:
            assert "TRACK UNSURE" in str(e), e


@case
def no_flash_of_the_speaker_or_a_short_piece():
    """v01 1:01 / 1:15 showed the director for 0.2 s between cutaways; v02 7:48 showed C0417 for 0.59 s."""
    cut = dict(stem="C0309", start=0.5, d=5.5, speed=1.0)
    out = B.no_flash([dict(cut), dict(stem="C0287", start=18.6, d=0.2, speed=1.0, self=True),
                      dict(stem="C0287", start=19.2, d=1.9, speed=1.0, self=True)])
    assert [o["stem"] for o in out] == ["C0309", "C0287"] and abs(out[0]["d"] - 5.7) < 1e-6, out
    out = B.no_flash([dict(stem="C0287", start=1.1, d=0.2, speed=1.0, self=True),
                      dict(stem="C0287", start=3.7, d=2.1, speed=1.0, self=True)])
    assert len(out) == 1 and abs(out[0]["start"] - 3.5) < 1e-6 and abs(out[0]["d"] - 2.3) < 1e-6, out
    import vlog_precheck as P
    shots = [dict(t=0, stem="A", src=0, d=3), dict(t=3, stem="B", src=4, d=0.59), dict(t=3.59, stem="C", src=0, d=3)]
    assert P.flashes(shots), "a 0.59 s jump must be warned before rendering"
    shots[1] = dict(t=3, stem="C", src=0, d=0.6)
    shots[2] = dict(t=3.6, stem="C", src=0.6, d=2.6)
    assert not P.flashes(shots), "a shot carrying on into the next one is not a flash"
    src = (HERE / "vlog_build.py").read_text(encoding="utf-8")
    assert "def sheet_notes(" in (HERE / "vlog_precheck.py").read_text(encoding="utf-8"), "bracketed sheet notes must be asked"


@case
def steadying_never_shows_the_edge():
    """steadied frames showed mirrored copies at the edges. Every correction stays inside the zoom."""
    import cv2
    import vlog_stab
    rng = np.random.default_rng(1)
    W, H = 640, 360
    base = (rng.random((H, W, 3)) * 255).astype(np.uint8)
    fs = []
    for i in range(60):                           # a violently shaking clip
        m = np.float32([[1, 0, rng.normal(0, 25)], [0, 1, rng.normal(0, 25)]])
        fs.append(cv2.warpAffine(base, m, (W, H), borderMode=cv2.BORDER_REFLECT))
    corr, _ = vlog_stab.analyse(fs)
    white = np.full((H, W), 255, np.uint8)
    for c in corr:
        w = cv2.warpAffine(white, vlog_stab.matrix(c, W, H), (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        assert (w < 128).sum() == 0, f"an edge shows after steadying ({c})"


# ---------------------------------------------------------------- ffmpeg runner
import vlog_ff  # noqa: E402


@case
def ffmpeg_never_waits_for_keyboard():
    r = vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-f", "lavfi", "-i", "anullsrc", "-t", "0.1", "-f", "null", "-"],
                    capture_output=True)
    assert r.returncode == 0
    assert "-nostdin" in r.args, r.args


@case
def ffmpeg_errors_say_why():
    try:
        vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-i", "no-such-file.mp4", "-f", "null", "-"], check=True)
    except subprocess.CalledProcessError as e:
        assert "no-such-file" in (e.stderr or ""), e.stderr
    else:
        raise AssertionError("a missing input did not fail")


@case
def final_encode_reads_every_input():
    """an input the filter graph never read (the seal) froze ffmpeg for 1 h 40 min."""
    s = (HERE / "vlog_build.py").read_text(encoding="utf-8")
    assert 'seal_in = ["-loop", "1"' in s and 'if any("[3:v]" in f for f in fc) else []' in s


# ---------------------------------------------------------------- subtitle files
import vlog_srt  # noqa: E402


@case
def srt_times_and_breaks():
    assert vlog_srt.srt_time("0:00:31.19") == "00:00:31,190"
    assert vlog_srt.srt_time("1:02:03.999") == "01:02:03,999"
    p = Path(tempfile.gettempdir()) / "selftest-srt.ass"
    p.write_text("Dialogue: 1,0:00:01.00,0:00:02.00,Sub,{\\fad(1,1)}上一行\\N下一行\nDialogue: 1,0:00:01.00,0:00:02.00,Src,x\n",
                 encoding="utf-8")
    assert vlog_srt.cues(p) == [("0:00:01.00", "0:00:02.00", "上一行\n下一行")]


@case
def effect_with_a_start_second_parses():
    """v03's 16 s animation ran out of memory at 4K as one piece; it is now four pieces, the later ones
    written !accretionend:<second>. Old forms must read exactly as before."""
    import vlog_build as B
    assert B.parse_pic("C0239@5+4!accretionend:4")["fx"] == "accretionend:4"
    assert B.parse_pic("C0239@1+4!accretion")["fx"] == "accretion"
    p = B.parse_pic("C0633@0*0.45>9.8!paneltop")
    assert (p["stem"], p["speed"], p["anchor"], p["fx"]) == ("C0633", 0.45, 9.8, "paneltop")
    assert B.parse_pic("C0211@0+6")["fx"] is None


@case
def montage_music_fits_any_length():
    """the opening montage's music crashed for some lengths (two roundings made it one sample too long for
    its reverb tail: v03-pilot after its montage clips changed). Every start and length must give body + 3.5 s exactly."""
    import vlog_tracks
    sr = vlog_tracks.SR
    x = (np.random.default_rng(1).standard_normal((int(30 * sr), 2)) * 0.1).astype(np.float32)
    for s0 in (0.0, 0.37, 1.2345, 7.77):
        for dur in (13.19, 13.43, 12.6667, 14.0):
            y = vlog_tracks.montage_audio(x, s0, dur)
            assert len(y) == int(dur * sr) + int(3.5 * sr), (s0, dur, len(y))
    y = vlog_tracks.montage_audio(x[: int(5 * sr)], 0.0, 13.43)          # a track shorter than the montage
    assert len(y) == int(13.43 * sr) + int(3.5 * sr)


# ---------------------------------------------------------------- report
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    bad = [(n, e) for n, e in RESULTS if e]
    for n, e in RESULTS:
        print(("FAIL " if e else "ok   ") + n)
    for n, e in bad:
        print(f"\n--- {n}\n{e}")
    print(f"\n{len(RESULTS) - len(bad)} of {len(RESULTS)} passed")
    sys.exit(1 if bad else 0)
