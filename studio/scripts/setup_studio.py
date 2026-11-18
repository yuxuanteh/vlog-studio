"""Install, check and remove the vlog studio's parts, one at a time. Nothing here asks questions: the setup skill asks
the person whether they need a part BEFORE it runs `install`, so nobody downloads gigabytes they will not use.

    python setup_studio.py list                      every part: what it is for, who can skip it, download size
    python setup_studio.py status                    what is installed, what is missing, disk space used
    python setup_studio.py install <part> [options]  core | fonts | whisper | privacy | music_fit | cutout | align
        whisper:  --model large-v3 | medium | small          (default large-v3)
        fonts:    --script latin | sc | tc | jp | kr         (default: from [language] narration)
    python setup_studio.py remove <part>             frees the space again
    python setup_studio.py set <section> <key> <value>       write one value into vlog.toml (value as TOML)

Runs with any Python 3.11+ (it needs none of the studio's own packages). The studio's Python lives in <studio>/.venv,
made by `install core` with uv (https://docs.astral.sh/uv/), or with `python -m venv` when uv is not there.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
VENV = STUDIO / ".venv"
ALIGN_VENV = STUDIO / ".venv-align"
WIN, MAC = os.name == "nt", sys.platform == "darwin"
BIN = "Scripts/python.exe" if WIN else "bin/python"
PY, ALIGN_PY = VENV / BIN, ALIGN_VENV / BIN
CONFIG = Path(os.environ.get("VLOG_CONFIG", STUDIO / "vlog.toml"))
REQ = STUDIO / "requirements"

PARTS = {
    "core": dict(size="about 450 MB", need="everyone",
                 what="The studio's own Python with the picture and sound packages (numpy, OpenCV, Pillow), ffmpeg, which "
                      "cuts, mixes and encodes every video, and ExifTool, which reads when and where a clip was filmed. "
                      "It also steadies shaky shots and evens out brightness from shot to shot: no extra download."),
    "fonts": dict(size="3 MB (Latin) to 45 MB (Chinese, with a handwriting-style font)", need="everyone",
                  what="Free fonts (SIL Open Font Licence) for subtitles, place tags and titles."),
    "whisper": dict(size="3.1 GB with the large-v3 model, 1.7 GB with medium, 0.7 GB with small", need="anyone who talks in their videos",
                    what="Speech recognition on your own computer. It writes down what is said in every clip, so footage can "
                         "be found by what you said, cuts land between words and subtitles are timed. Skip it only for "
                         "videos with no talking at all (music and pictures only)."),
    "privacy": dict(size="about 1 MB", need="anyone who films in public",
                    what="Finds faces of passers-by in the shots you use and stops the render until you have said, for each "
                         "one, leave / blur / cut; and follows a thing through a shot (a QR code, a ticket) so it can be "
                         "blurred or marked. Without it nothing is looked for: you check faces yourself."),
    "music_fit": dict(size="about 300 MB", need="music from a library, or your own tracks",
                      what="Finds the beats and bars of a music track so it is shortened or lengthened on bar lines and ends "
                           "on its own ending. Skip it for videos without music."),
    "cutout": dict(size="about 1.2 GB", need="thumbnails or covers with you cut out of the picture",
                   what="Cuts a person cleanly out of a frame (hair and all) for thumbnails and Reel covers. Without it, "
                        "thumbnails use whole frames with text."),
    "align": dict(size="about 3 GB (a second Python environment with PyTorch, and a 1.8 GB model)", need="people who want cuts exact to the syllable",
                  what="A forced aligner: it takes the words speech recognition wrote and finds their exact start and end. "
                       "Cuts inside sentences sound cleaner. Speech recognition alone works without it; you then fix a "
                       "clipped word end on the editing page now and then."),
}
WHISPER = {"large-v3": ("Systran/faster-whisper-large-v3", "2.9 GB"), "medium": ("Systran/faster-whisper-medium", "1.5 GB"),
           "small": ("Systran/faster-whisper-small", "0.5 GB")}
GF = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
WENKAI = "https://raw.githubusercontent.com/lxgw/LxgwWenKai/main/fonts/TTF/LXGWWenKai-Medium.ttf"
# script -> (family, variable font url, kept file, {static file: weight}, hand font (url, file, name) or None)
FONTS = {
    "latin": ("Noto Sans", GF + "notosans/NotoSans%5Bwdth%2Cwght%5D.ttf", "NotoSans-VF.ttf", {"NotoSans-Medium.ttf": 500, "NotoSans-Bold.ttf": 700}, None),
    "sc": ("Noto Sans SC", GF + "notosanssc/NotoSansSC%5Bwght%5D.ttf", "NotoSansSC-VF.ttf", {"NotoSansSC-Medium.ttf": 500, "NotoSansSC-Bold.ttf": 700},
           (WENKAI, "LXGWWenKai-Medium.ttf", "LXGW WenKai Medium")),
    "tc": ("Noto Sans TC", GF + "notosanstc/NotoSansTC%5Bwght%5D.ttf", "NotoSansTC-VF.ttf", {"NotoSansTC-Medium.ttf": 500, "NotoSansTC-Bold.ttf": 700},
           (WENKAI, "LXGWWenKai-Medium.ttf", "LXGW WenKai Medium")),
    "jp": ("Noto Sans JP", GF + "notosansjp/NotoSansJP%5Bwght%5D.ttf", "NotoSansJP-VF.ttf", {"NotoSansJP-Medium.ttf": 500, "NotoSansJP-Bold.ttf": 700}, None),
    "kr": ("Noto Sans KR", GF + "notosanskr/NotoSansKR%5Bwght%5D.ttf", "NotoSansKR-VF.ttf", {"NotoSansKR-Medium.ttf": 500, "NotoSansKR-Bold.ttf": 700}, None),
}
ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
PRIVACY = [(ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx", "face_detection_yunet_2023mar.onnx"),
           (ZOO + "object_tracking_vittrack/object_tracking_vittrack_2023sep.onnx", "object_tracking_vittrack_2023sep.onnx")]
ALIGNER = "Qwen/Qwen3-ForcedAligner-0.6B"


def say(s=""):
    print(s, flush=True)


def run(cmd, **kw):
    say("  $ " + " ".join("<script>" if "\n" in str(c) else str(c) for c in cmd))
    return subprocess.run(list(map(str, cmd)), **kw)


def cfg():
    import tomllib
    return tomllib.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}


def set_value(section, key, value):
    """Write one `key = value` line into [section] of vlog.toml, keeping every other line and comment."""
    if not CONFIG.exists():
        shutil.copy(STUDIO / "vlog.example.toml", CONFIG)
    lines = CONFIG.read_text(encoding="utf-8").splitlines()
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(f"[{section}]")), None)
    if start is None:
        lines += ["", f"[{section}]", f"{key} = {value}"]
    else:
        end = next((i for i in range(start + 1, len(lines)) if re.match(r"\s*\[", lines[i])), len(lines))
        hit = next((i for i in range(start + 1, end) if re.match(rf"\s*{re.escape(key)}\s*=", lines[i])), None)
        if hit is None:
            lines.insert(start + 1, f"{key} = {value}")
        else:
            m = re.match(r"(.*?=\s*)(\"(?:[^\"\\]|\\.)*\"|\[[^\]]*\]|[^#]*?)(\s*#.*)?$", lines[hit])
            lines[hit] = f"{key} = {value}" + (m.group(3) if m and m.group(3) else "")
    CONFIG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def pip(*args, py=None):
    py = py or PY
    uv = shutil.which("uv")
    cmd = [uv, "pip", *args[:1], "--python", py, *args[1:]] if uv else [py, "-m", "pip", *args]
    if run(cmd).returncode:
        raise SystemExit("FAILED: the package step above did not finish (see its message)")


def venv(path):
    py = path / BIN
    if py.exists():
        return
    uv = shutil.which("uv")
    if uv:
        if run([uv, "venv", path, "--python", "3.12"]).returncode:
            raise SystemExit("FAILED: uv could not make the Python environment")
    else:
        say(f"  uv is not installed ({hint('uv')}); using this Python's venv instead")
        if sys.version_info < (3, 11):
            raise SystemExit("this Python is older than 3.11: install uv, which brings its own Python")
        run([sys.executable, "-m", "venv", path], check=True)


def need_core():
    if not PY.exists():
        raise SystemExit("install `core` first (the studio's own Python)")


def download(url, dest):
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return
    say(f"  downloading {dest.name}")
    req = urllib.request.Request(url, headers={"User-Agent": "vlog-studio-setup"})
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def size(path):
    path = Path(path)
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def mb(n):
    return f"{n / 1e9:.1f} GB" if n > 1e9 else f"{n / 1e6:.0f} MB"


def hint(tool):
    h = {"ffmpeg": ("winget install Gyan.FFmpeg", "brew install ffmpeg", "sudo apt install ffmpeg"),
         "exiftool": ("winget install OliverBetz.ExifTool", "brew install exiftool", "sudo apt install libimage-exiftool-perl"),
         "uv": ("winget install astral-sh.uv", "brew install uv", "curl -LsSf https://astral.sh/uv/install.sh | sh")}[tool]
    return h[0] if WIN else h[1] if MAC else h[2]


def tool(name, key):
    """A system program: [paths] in vlog.toml first, then PATH."""
    c = cfg().get("paths", {})
    if key == "ffmpeg_bin" and c.get(key):
        f = Path(c[key]) / ("ffmpeg.exe" if WIN else "ffmpeg")
        return str(f) if f.exists() else None
    if key == "exiftool" and c.get(key):
        return c[key] if Path(c[key]).exists() else None
    return shutil.which(name)


# ------------------------------------------------------------------------------------------------ install

def install_core():
    venv(VENV)
    pip("install", "-r", REQ / "core.txt")
    if cfg().get("language", {}).get("narration", "").startswith("zh"):
        pip("install", "-r", REQ / "zh.txt")
    for d in ("models", "render", "trips", "fonts", "logs"):
        (STUDIO / d).mkdir(parents=True, exist_ok=True)
    for name, key in (("ffmpeg", "ffmpeg_bin"), ("exiftool", "exiftool")):
        if not tool(name, key):
            say(f"MISSING {name}: install it, then run `status` again:\n    {hint(name)}\n  (or put its place in [paths] {key} of vlog.toml)")
    say("core: done")


def install_fonts(script=None):
    need_core()
    lang = cfg().get("language", {}).get("narration", "en").lower()
    script = script or {"zh": "sc", "zh-cn": "sc", "zh-tw": "tc", "ja": "jp", "ko": "kr"}.get(lang, "latin")
    family, url, vf, cuts, hand = FONTS[script]
    fonts = STUDIO / "fonts"
    download(url, fonts / vf)
    code = ("import sys; from fontTools.ttLib import TTFont; from fontTools.varLib import instancer\n"
            "f = TTFont(sys.argv[1]); axes = {a.axisTag for a in f['fvar'].axes}\n"
            "loc = {'wght': float(sys.argv[3])}\n"
            "if 'wdth' in axes: loc['wdth'] = 100.0\n"
            "instancer.instantiateVariableFont(f, loc, inplace=True, updateFontNames=True); f.save(sys.argv[2])\n")
    for out, weight in cuts.items():
        if not (fonts / out).exists():
            say(f"  cutting {out} from {vf}")
            if run([PY, "-c", code, fonts / vf, fonts / out, weight]).returncode:
                raise SystemExit(f"FAILED: could not make {out}")
    (fonts / vf).unlink(missing_ok=True)                 # the variable font is only the source of the two cuts
    text, bold = list(cuts)
    set_value("fonts", "text_file", json.dumps(text))
    set_value("fonts", "text_name", json.dumps(f"{family} Medium"))
    set_value("fonts", "bold_file", json.dumps(bold))
    set_value("fonts", "bold_name", json.dumps(f"{family} Bold"))
    if hand:
        download(hand[0], fonts / hand[1])
        set_value("fonts", "hand_file", json.dumps(hand[1]))
        set_value("fonts", "hand_name", json.dumps(hand[2]))
    else:
        set_value("fonts", "hand_file", json.dumps(text))
        set_value("fonts", "hand_name", json.dumps(f"{family} Medium"))
    say(f"fonts: done ({family}; {mb(size(fonts))} in fonts/)")


def install_whisper(model="large-v3"):
    need_core()
    if model not in WHISPER:
        raise SystemExit(f"model must be one of {', '.join(WHISPER)}")
    pip("install", "-r", REQ / "whisper.txt")
    repo, sz = WHISPER[model]
    dest = STUDIO / "models" / f"faster-whisper-{model}"
    if not (dest / "model.bin").exists():
        say(f"  downloading the {model} model ({sz}); this is the long part")
        code = "import sys; from huggingface_hub import snapshot_download\nsnapshot_download(sys.argv[1], local_dir=sys.argv[2])\n"
        if run([PY, "-c", code, repo, dest]).returncode:
            raise SystemExit("FAILED: the model download did not finish; run the same command again to resume")
    set_value("whisper", "model", json.dumps(f"models/faster-whisper-{model}"))
    set_value("components", "whisper", "true")
    say(f"whisper: done ({model}, {mb(size(dest))})")


def install_privacy():
    need_core()
    for url, name in PRIVACY:
        download(url, STUDIO / "models" / "opencv" / name)
    set_value("components", "privacy", "true")
    say("privacy: done")


def install_music_fit():
    need_core()
    pip("install", "-r", REQ / "music_fit.txt")
    set_value("components", "music_fit", "true")
    say("music_fit: done")


def install_cutout():
    need_core()
    pip("install", "-r", REQ / "cutout.txt")
    home = STUDIO / "models" / "u2net"
    home.mkdir(parents=True, exist_ok=True)
    say("  downloading the cut-out model (about 970 MB)")
    code = "import os, sys\nos.environ['U2NET_HOME'] = sys.argv[1]\nfrom rembg import new_session\nnew_session('birefnet-portrait')\n"
    if run([PY, "-c", code, home]).returncode:
        raise SystemExit("FAILED: the cut-out model did not download; run the same command again")
    set_value("components", "cutout", "true")
    say(f"cutout: done ({mb(size(home))})")


def install_align():
    need_core()
    venv(ALIGN_VENV)
    pip("install", "-r", REQ / "align.txt", py=ALIGN_PY)
    dest = STUDIO / "models" / "qwen3-forced-aligner"
    if not (dest / "model.safetensors").exists():
        say("  downloading the aligner model (about 1.8 GB)")
        code = "import sys; from huggingface_hub import snapshot_download\nsnapshot_download(sys.argv[1], local_dir=sys.argv[2])\n"
        if run([ALIGN_PY, "-c", code, ALIGNER, dest]).returncode:
            raise SystemExit("FAILED: the model download did not finish; run the same command again to resume")
    set_value("components", "align", "true")
    say(f"align: done (run vlog_qalign.py with {ALIGN_PY})")


# ------------------------------------------------------------------------------------------------ remove / status

def remove(part):
    if part == "whisper":
        for d in (STUDIO / "models").glob("faster-whisper-*"):
            shutil.rmtree(d)
        pip("uninstall", "faster-whisper", "ctranslate2", "tokenizers", "av", "huggingface_hub")
    elif part == "privacy":
        shutil.rmtree(STUDIO / "models" / "opencv", ignore_errors=True)
    elif part == "music_fit":
        pip("uninstall", "librosa", "numba", "llvmlite", "scikit-learn")
    elif part == "cutout":
        shutil.rmtree(STUDIO / "models" / "u2net", ignore_errors=True)
        pip("uninstall", "rembg", "onnxruntime")
    elif part == "align":
        shutil.rmtree(ALIGN_VENV, ignore_errors=True)
        shutil.rmtree(STUDIO / "models" / "qwen3-forced-aligner", ignore_errors=True)
    elif part == "fonts":
        for f in (STUDIO / "fonts").glob("*.ttf"):
            f.unlink()
    elif part == "core":
        raise SystemExit("to remove everything, delete the studio folder itself (your trips folder is separate and is not touched)")
    else:
        raise SystemExit(f"unknown part {part}")
    if part in ("whisper", "privacy", "music_fit", "cutout", "align"):
        set_value("components", part, "false")
    say(f"{part}: removed")


def has_pkg(name, py=None):
    py = py or PY
    return py.exists() and subprocess.run([str(py), "-c", f"import {name}"], capture_output=True).returncode == 0


def status():
    c = cfg()
    comp = c.get("components", {})
    ff, ex = tool("ffmpeg", "ffmpeg_bin"), tool("exiftool", "exiftool")
    note = "; ".join(x for x in ("" if ff else f"ffmpeg missing ({hint('ffmpeg')})", "" if ex else f"ExifTool missing ({hint('exiftool')})") if x)
    rows = [("core", has_pkg("cv2") and bool(ff), size(VENV), note)]
    fonts = STUDIO / "fonts"
    want = [c.get("fonts", {}).get(k) for k in ("text_file", "bold_file", "hand_file")]
    rows.append(("fonts", all(want) and all((fonts / f).exists() for f in want), size(fonts), ""))
    model = STUDIO / c.get("whisper", {}).get("model", "models/faster-whisper-large-v3")
    rows.append(("whisper", has_pkg("faster_whisper") and (model / "model.bin").exists(), size(STUDIO / "models") - size(STUDIO / "models" / "u2net")
                 - size(STUDIO / "models" / "qwen3-forced-aligner") - size(STUDIO / "models" / "opencv"), model.name))
    rows.append(("privacy", (STUDIO / "models" / "opencv" / PRIVACY[0][1]).exists(), size(STUDIO / "models" / "opencv"), ""))
    rows.append(("music_fit", has_pkg("librosa"), 0, ""))
    rows.append(("cutout", has_pkg("rembg") and size(STUDIO / "models" / "u2net") > 1e8, size(STUDIO / "models" / "u2net"), ""))
    rows.append(("align", has_pkg("qwen_asr", ALIGN_PY) and (STUDIO / "models" / "qwen3-forced-aligner" / "model.safetensors").exists(),
                 size(ALIGN_VENV) + size(STUDIO / "models" / "qwen3-forced-aligner"), ""))
    say(f"studio: {STUDIO}\nsettings: {CONFIG}{'' if CONFIG.exists() else '  (not written yet)'}\n")
    for name, ok, sz, note in rows:
        chosen = comp.get(name, name in ("core", "fonts", "whisper"))
        state = "installed" if ok else ("not installed" if chosen else "skipped (not needed)")
        say(f"  {name:10s} {state:22s} {mb(sz) if sz else '':>8s}  {note}")
    say(f"\n  render cache: {mb(size(STUDIO / 'render'))} · 720p working copies: {mb(size(STUDIO / 'trips'))} (both safe to delete; they are made again when needed)"
        f"\n  whole studio folder: {mb(size(STUDIO))}")


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    opt = {a[i]: a[i + 1] for i in range(len(a) - 1) if a[i].startswith("--")}
    if not a or a[0] == "list":
        for name, p in PARTS.items():
            say(f"{name}\n  for: {p['need']}\n  download: {p['size']}\n  {p['what']}\n")
    elif a[0] == "status":
        status()
    elif a[0] == "set" and len(a) == 4:
        set_value(a[1], a[2], a[3])
    elif a[0] == "install" and len(a) >= 2:
        {"core": install_core, "fonts": lambda: install_fonts(opt.get("--script")),
         "whisper": lambda: install_whisper(opt.get("--model", "large-v3")), "privacy": install_privacy,
         "music_fit": install_music_fit, "cutout": install_cutout, "align": install_align}[a[1]]()
    elif a[0] == "remove" and len(a) == 2:
        remove(a[1])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
