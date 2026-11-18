"""A small editing page for the director: hear a video's voice as text, cut words, fix subtitle wording, move words
between subtitles, and save straight into the subtitle sheet the build reads (<trip>/work/subtitles/<id>.xlsx).

Usage: python vlog_editor.py [trip] [port]        then open http://localhost:8765
       (trip defaults to the newest folder in youtube/trips)

The page only edits the sheet's 字幕 column (〔〕 = cut that voice), exactly as the director would in Excel; the next
build picks it up. Every save first copies the old sheet to <studio>/editor-cache/backup.
"""
import json
import re
import shutil
import subprocess
import sys
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlparse

sys.path.insert(0, str(Path(__file__).parent))
import vlog_env      # noqa: E402
import vlog_i18n     # noqa: E402
import vlog_trip     # noqa: E402
import vlog_ff       # noqa: E402
import vlog_layout   # noqa: E402
import vlog_sheet    # noqa: E402
import vlog_review   # noqa: E402

HERE = Path(__file__).parent
CACHE = vlog_env.LOCAL / "editor-cache"
PAGE = HERE / "editor" / "index.html"
REVIEW = HERE / "editor" / "review.html"


def join(ws):
    t = "".join(ws)
    t = re.sub(r"(?<=[^\x00-\x7f])\s+|\s+(?=[^\x00-\x7f])", "", t)
    return re.sub(r"\s+", " ", t).strip()


def group_words(ws):
    """Whisper often gives Chinese one character at a time (参 / 加); join its pieces into whole words (jieba) so the
    director picks, cuts and moves 参加, not half of it. A piece that already spans two words stays one."""
    import jieba
    toks = [w[2] for w in ws]
    text = "".join(toks)
    starts, k = set(), 0
    for piece in jieba.cut(text):
        nk = k + len(piece.lstrip())
        k += len(piece)
        starts.add(nk - len(piece.lstrip()))
    out, pos = [], 0
    for w, t in zip(ws, toks):
        lead = len(t) - len(t.lstrip())
        if out and (pos + lead) not in starts and not t.startswith(" "):
            g = out[-1]
            g["t"] += t
            g["e"] = round(max(g["e"], w[1]), 3)
            g["we"] = round(w[4], 3) if len(w) > 4 else g["e"]
        else:
            out.append(dict(s=round(w[0], 3), e=round(w[1], 3), t=t,
                            ws=round(w[3], 3) if len(w) > 3 else round(w[0], 3), we=round(w[4], 3) if len(w) > 4 else round(w[1], 3)))
        pos += len(t)
    return out


class Trip:
    def __init__(self, name):
        self.dir = vlog_env.TRIPS / name
        rows = json.loads((self.dir / "work" / "footage-index.json").read_text(encoding="utf-8"))
        self.clips = vlog_trip.clip_table(rows)
        self.words_cache = {}

    def path(self, stem):
        return self.dir / "raw" / self.clips[stem]["file"]

    def words(self, stem):
        """[(start, end, text, whisper start)]: text and row ids from Whisper, times from the aligned copy (as the build)."""
        if stem not in self.words_cache:
            p = self.dir / "work" / "words" / f"{stem}.json"
            ws = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
            al = p.with_name(f"{stem}.aligned.json")
            ts = json.loads(al.read_text(encoding="utf-8")) if al.exists() else ws
            self.words_cache[stem] = [(float(a[0]), float(a[1]), w[2], float(w[0]), float(w[1])) for w, a in zip(ws, ts)]
        return self.words_cache[stem]

    def sheets(self):
        return sorted(p.stem for p in (self.dir / "work" / "subtitles").glob("*.xlsx") if not p.name.startswith("~$"))

    def sheet_path(self, vid):
        return self.dir / "work" / "subtitles" / f"{vid}.xlsx"

    def rows(self, vid):
        x = self.sheet_path(vid)
        out, prev = [], None
        for r in vlog_sheet.read_xlsx(x):
            when, cid, raw, shown, note, auto = r
            m = re.fullmatch(r"(.+)@([\d.]+)", cid.strip())
            words, voice, idx = [], None, None
            if m and m[1] in self.clips:
                voice, t0 = m[1], float(m[2])
                ws = self.words(voice)
                k = next((i for i, w in enumerate(ws) if abs(w[3] - t0) < 0.006), None)
                if k is not None:
                    want = len(re.sub(r"\s", "", raw))
                    got, j = 0, k
                    while j < len(ws) and got < want:
                        got += len(re.sub(r"\s", "", ws[j][2]))
                        j += 1
                    words = group_words(ws[k:j])
                    idx = (k, j)
            # rows of one voice whose words follow on from each other form one block: text may move between them
            block = prev["block"] + 1 if prev else 0
            if prev and voice and prev["voice"] == voice and prev["_idx"] and idx and idx[0] == prev["_idx"][1]:
                block = prev["block"]
            row = dict(when=when, cid=cid, raw=raw, shown=shown, note=note, auto=auto, voice=voice, words=words,
                       block=block, _idx=idx)
            out.append(row)
            prev = row
        # words said right after a row that no row holds: the edit list stops the recording before them. Shown greyed so
        # the director can hear what was left out (差不多6米 after 往上移了).
        used = {}
        for r in out:
            if r["_idx"]:
                used.setdefault(r["voice"], set()).update(range(*r["_idx"]))
        for r in out:
            r["tail"] = []
            if r["_idx"]:
                ws = self.words(r["voice"])
                j, tail = r["_idx"][1], []
                while j < len(ws) and j not in used[r["voice"]] and len(tail) < 40 \
                        and ws[j][0] - (tail[-1][1] if tail else ws[j - 1][1]) < 1.2:
                    tail.append(ws[j])
                    j += 1
                r["tail"] = group_words(tail) if tail else []
        for r in out:
            r.pop("_idx")
        return out, x.stat().st_mtime, self.voice_data(vid)

    def voice_file(self, vid):
        return self.dir / "work" / "subtitles" / f"{vid}.voice.json"

    def voice_data(self, vid):
        f = self.voice_file(vid)
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        return dict(restore=d.get("restore", []), cuts=d.get("cuts", []), keeps=d.get("keeps", []))

    def folded_restores(self, vid, restore, raw_of):
        """Words put back earlier that the build has since folded into their row (the row's Whisper text now holds
        them, so the page shows them as the row's own words, not as a tail to put back) stay put back: without the
        restore the edit list stops before them again."""
        raw_of = {k: re.sub(r"\s", "", v or "") for k, v in raw_of.items()}
        out = list(restore)
        for g in self.voice_data(vid)["restore"]:
            if any(x.get("voice") == g.get("voice") and abs(x.get("from", -9) - g.get("from", 0)) < 0.03 for x in out):
                continue
            w = re.sub(r"\s", "", g.get("words") or "")
            if w and w in raw_of.get(g.get("after"), ""):
                out.append(g)
            elif g.get("after") and g["after"] not in raw_of:
                # its row has a new id (re-timed words): the page cannot show it, so it cannot have been taken out
                # there; keep it (v01-short's 差不多6米 vanished this way on 11-14)
                out.append(g)
        return out

    def save(self, vid, edits, mtime, restore=None, cuts=None, keeps=None):
        x = self.sheet_path(vid)
        if abs(x.stat().st_mtime - mtime) > 0.5:
            return dict(ok=False, error=vlog_env.tr("The subtitle sheet was changed somewhere else (Excel?). Reload the page, then edit again.", "这个字幕表在别的地方被改过（Excel？）。请重新载入页面再改。"))
        rows = vlog_sheet.read_xlsx(x)
        by = {e["cid"]: e["shown"] for e in edits}
        n = 0
        for r in rows:
            if r[1] in by and r[3] != by[r[1]]:
                r[3] = by[r[1]]
                n += 1
        bk = CACHE / "backup"
        bk.mkdir(parents=True, exist_ok=True)
        shutil.copy2(x, bk / f"{vid}-{time.strftime('%Y%m%d-%H%M%S')}.xlsx")
        try:
            vlog_sheet.write_xlsx(x, rows)
        except PermissionError:
            return dict(ok=False, error=vlog_env.tr("Cannot save: the subtitle sheet is open in Excel. Close Excel, then press Save.", "存不进去：字幕表在 Excel 里开着。请先关掉 Excel 再按保存。"))
        old = self.voice_data(vid)
        if restore is not None:
            restore = self.folded_restores(vid, restore, {r[1]: r[2] for r in rows})
        new = dict(restore=old["restore"] if restore is None else restore, cuts=old["cuts"] if cuts is None else cuts,
                   keeps=old["keeps"] if keeps is None else keeps)
        if new != old:
            f = self.voice_file(vid)
            if f.exists():
                shutil.copy2(f, bk / f"{vid}-{time.strftime('%Y%m%d-%H%M%S')}.voice.json")
            f.write_text(json.dumps(dict(note="Voice decisions made on the editing page, kept apart from the edit list and applied at every build. "
                                              "restore: recording put back into the video (Whisper times); cuts: sound cut by time "
                                              "(seconds of the recording: an um Whisper never heard); keeps: sound put back by time.",
                                         **new), ensure_ascii=False, indent=1), encoding="utf-8")
            n += 1
        return dict(ok=True, changed=n, mtime=x.stat().st_mtime)

    _vb = _snap = None
    _lock = __import__("threading").Lock()
    _edits_cache = None

    def _edits(self, VB, vid):
        """Every sheet's edits, read from Drive again only when a sheet file has changed (the page asked for
        them, six Excel files, after every single edit). The caller changes the result, so it gets its own copy."""
        d = self.dir / "work" / "subtitles"
        key = (vid, tuple(sorted((p.name, p.stat().st_mtime) for p in d.iterdir() if p.suffix in (".tsv", ".xlsx"))))
        if self._edits_cache is None or self._edits_cache[0] != key:
            self._edits_cache = (key, VB.load_edits(self._vb, vid))
        src = self._edits_cache[1]
        out = VB.Edits(src)
        out.own, out.ids, out.sheet = dict(src.own), set(src.ids), dict(src.sheet)
        return out

    def keep(self, vid, rows, restore, cuts, keeps=()):
        """What the build will keep of each voice block, worked out by the build's own code (vlog_build.voice_plan) with
        the page's unsaved text, put-back words and time cuts. The page plays exactly this, so what the director hears
        is what the video gets. Returns [{voice, a, b, ranges: [[start, end] in recording seconds]}] in edit-list order."""
        import vlog_build as VB
        with self._lock:
            if self._vb is None:
                self._vb, self._snap = VB.Trip(self.dir.name), None
                self._snap = VB.Snap(self._vb)
            env = {"V": VB.V, "N": VB.N, "S": VB.S, "M": VB.M, "T": VB.T, "E": VB.E}
            exec((self.dir / "work" / "edl" / f"{vid}.py").read_text(encoding="utf-8"), env)
            fixes = list(env.get("FIX", [])) + vlog_trip.fixes(self.dir)
            edits = self._edits(VB, vid)
            for r in rows:
                cid, raw, shown, auto = r["cid"].strip(), r["raw"].strip(), r["shown"].strip(), r["auto"].strip()
                if shown != auto:
                    edits[cid] = edits.own[cid] = (raw, shown)
                else:
                    edits.pop(cid, None)
                    edits.own.pop(cid, None)
            restores = [dict(x) for x in self.folded_restores(vid, restore, {r["cid"]: r["raw"] for r in rows})]
            limit = vlog_layout.sub_chars(env["W"], env["H"])
            out = []
            for i_, b in enumerate(env["BLOCKS"]):
                if b["kind"] != "V":
                    continue
                pb = env["BLOCKS"][i_ - 1] if i_ else None          # same rule as the build: no overlap played twice
                b["_prev"] = (pb["voice"], pb["a"], pb["b"]) if pb and pb["kind"] == "V" else None
                VB.apply_restores(b, restores)
                b["_timecuts"] = cuts
                b["_keeps"] = list(keeps)
                keep = VB.voice_plan(self._vb, self._snap, b, fixes, edits, limit)[0]
                out.append(dict(voice=b["voice"], a=round(b["a"], 3), b=round(b["b"], 3),
                                ranges=[[round(b["a"] + p, 3), round(b["a"] + q, 3)] for p, q in keep]))
            return out

    def audio(self, stem):
        """The voice of one recording as a small mono file, made once."""
        CACHE.mkdir(parents=True, exist_ok=True)
        out = CACHE / f"{self.dir.name}-{stem}.m4a"
        if not out.exists():
            tmp = out.with_suffix(".part.m4a")
            vlog_ff.run([vlog_env.FFMPEG, "-v", "error", "-y", "-i", str(self.path(stem)), "-map", "0:a:0", "-ac", "1",
                            "-ar", "24000", "-c:a", "aac", "-b:a", "64k", str(tmp)], check=True)
            tmp.replace(out)
        return out


def scripts_stamp():
    """When any script or page of the tools last changed (the page restarts itself on a change)."""
    here = Path(__file__).parent
    return max(f.stat().st_mtime for f in list(here.glob("*.py")) + list((here / "editor").glob("*.html")))


STARTED = scripts_stamp()


def trips():
    return sorted(p.name for p in vlog_env.TRIPS.iterdir() if (p / "work" / "subtitles").is_dir())


def make_handler(trip):
    state = {"trip": trip}                              # the trip the pages work on, switched from the menu

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def json(self, obj, code=200):
            self.send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            u = urlparse(self.path)
            parts = [unquote(p) for p in u.path.split("/") if p]
            trip = state["trip"]
            try:
                if parts == ["api", "trips"]:
                    self.json(dict(trips=trips(), current=trip.dir.name))
                elif parts[:2] == ["api", "version"]:
                    # the scripts changed since this server started. The page says whether it holds unsaved edits:
                    # none -> the server restarts itself with the new code and the page reloads; some -> a banner, wait
                    changed = scripts_stamp() > STARTED + 1
                    dirty = "dirty=1" in (u.query or "")
                    self.json(dict(changed=changed, restart=changed and not dirty))
                    if changed and not dirty:
                        import threading
                        threading.Timer(0.5, restart_self).start()
                elif not parts:
                    self.send(200, vlog_i18n.page(PAGE.read_text(encoding="utf-8")).encode("utf-8"), "text/html; charset=utf-8")
                elif parts == ["api", "sheets"]:
                    self.json(dict(trip=trip.dir.name, sheets=trip.sheets()))
                elif parts[:2] == ["api", "sheet"] and len(parts) == 3:
                    rows, mtime, vd = trip.rows(parts[2])
                    self.json(dict(rows=rows, mtime=mtime, **vd))
                elif parts[0] == "audio" and len(parts) == 2:
                    self.send(200, trip.audio(parts[1]).read_bytes(), "audio/mp4")
                # the review page: notes on a build's phone copy (vlog_review.py)
                elif parts == ["review"]:
                    self.send(200, vlog_i18n.page(REVIEW.read_text(encoding="utf-8")).encode("utf-8"), "text/html; charset=utf-8")
                elif parts == ["api", "reviews"]:
                    self.json(dict(trip=trip.dir.name, videos=vlog_review.reviews(trip)))
                elif parts[:2] == ["api", "timeline"] and len(parts) == 3:
                    self.json(vlog_review.timeline(trip, parts[2]))
                elif parts[:2] == ["api", "notes"] and len(parts) == 3:
                    self.json(vlog_review.load_notes(trip, parts[2]))
                elif parts[0] == "video" and len(parts) == 2:
                    vlog_review.send_file(self, vlog_review.phone_file(trip, parts[1]), "video/mp4")
                elif parts[0] == "thumb" and len(parts) == 3:
                    self.send(200, vlog_review.thumb(trip, parts[1], int(parts[2])).read_bytes(), "image/jpeg")
                else:
                    self.json(dict(error="not found"), 404)
            except Exception as e:      # shown on the page, so the director can tell Claude
                self.json(dict(error=f"{type(e).__name__}: {e}"), 500)

        def do_POST(self):
            parts = [unquote(p) for p in urlparse(self.path).path.split("/") if p]
            trip = state["trip"]
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8"))
                if parts[:2] == ["api", "trip"] and len(parts) == 3:
                    if parts[2] not in trips():
                        raise SystemExit(f"no trip called {parts[2]}")
                    state["trip"] = Trip(parts[2])
                    self.json(dict(ok=True, trip=parts[2]))
                elif parts[:2] == ["api", "save"] and len(parts) == 3:
                    self.json(trip.save(parts[2], body["edits"], body["mtime"], body.get("restore"), body.get("cuts"), body.get("keeps")))
                elif parts[:2] == ["api", "check"] and len(parts) == 3:
                    import vlog_editcheck
                    self.json(dict(items=vlog_editcheck.check(trip, parts[2], body)))
                elif parts[:2] == ["api", "notes"] and len(parts) == 3:
                    self.json(vlog_review.save_notes(trip, parts[2], body))
                elif parts[:2] == ["api", "keep"] and len(parts) == 3:
                    self.json(dict(blocks=trip.keep(parts[2], body["rows"], body.get("restore", []), body.get("cuts", []),
                                                    body.get("keeps", []))))
                else:
                    self.json(dict(error="not found"), 404)
            except Exception as e:
                self.json(dict(ok=False, error=f"{type(e).__name__}: {e}"), 500)
    return H


def restart_self():
    """Start this server again with the same command line (the director's launcher's own), then end this one."""
    import os
    args = getattr(sys, "orig_argv", None) or [sys.executable] + sys.argv
    subprocess.Popen(args, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    os._exit(0)


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else max((p for p in vlog_env.TRIPS.iterdir() if (p / "work").is_dir()),
                                                      key=lambda p: p.name).name
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), make_handler(Trip(name)))
    except OSError:                                    # port taken: the editing page is most likely already running
        import urllib.request
        import webbrowser
        try:
            urllib.request.urlopen(f"http://localhost:{port}/api/sheets", timeout=5).read()
        except Exception:
            print(f"Port {port} is used by another program. Close it (or restart the computer) and try again.", flush=True)
            sys.exit(1)
        print(f"The editing page is already running: opening http://localhost:{port}", flush=True)
        webbrowser.open(f"http://localhost:{port}")
        sys.exit(0)
    print(f"editing page for {name}: http://localhost:{port}", flush=True)
    print("Keep this window open while you edit. Close it when you are done.", flush=True)
    srv.serve_forever()
