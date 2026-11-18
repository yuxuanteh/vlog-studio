"""Paths and settings of the vlog studio, from <studio>/vlog.toml (or the file named by VLOG_CONFIG).

The studio folder is the parent of this scripts/ folder: tools, the Python environment, models, 720p working copies
and the render cache (local, not synced). The trips folder holds the footage, the work files and the finished
videos (it may be a synced folder or an external drive).
"""
import os
import shutil
import tomllib
from pathlib import Path

LOCAL = Path(__file__).resolve().parent.parent          # the studio folder (not synced)
STUDIO = LOCAL
CONFIG_FILE = Path(os.environ.get("VLOG_CONFIG", LOCAL / "vlog.toml"))
if not CONFIG_FILE.exists():
    raise SystemExit(f"studio settings not found: {CONFIG_FILE}\n"
                     f"copy {LOCAL / 'vlog.example.toml'} to vlog.toml and set [paths] trips")
CFG = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def cfg(section, key, default=None):
    return CFG.get(section, {}).get(key, default)


def _path(value, base=LOCAL):
    p = Path(os.path.expandvars(os.path.expanduser(str(value))))
    return p if p.is_absolute() else base / p


TRIPS = _path(cfg("paths", "trips", "trips"))            # <trips>/<trip>/raw, work, videos/<id>/{preview,publish}
WHISPER_MODEL = _path(cfg("whisper", "model", "models/faster-whisper-large-v3"))
MODELS = _path(cfg("paths", "models", "models"))
MUSIC = _path(cfg("paths", "music_library", "") or TRIPS.parent / "music")
MUSIC_USED = _path(cfg("paths", "music_used", "") or TRIPS.parent / "music-used.md")
FONT_DIR = LOCAL / "fonts"

_exe = ".exe" if os.name == "nt" else ""
_bin = cfg("paths", "ffmpeg_bin", "")
if _bin:
    FFMPEG, FFPROBE = str(_path(_bin) / f"ffmpeg{_exe}"), str(_path(_bin) / f"ffprobe{_exe}")
    if str(_path(_bin)) not in os.environ.get("PATH", ""):
        os.environ["PATH"] = str(_path(_bin)) + os.pathsep + os.environ.get("PATH", "")
else:
    FFMPEG, FFPROBE = shutil.which("ffmpeg") or "ffmpeg", shutil.which("ffprobe") or "ffprobe"
EXIFTOOL = cfg("paths", "exiftool", "") or shutil.which("exiftool") or "exiftool"

CHANNEL = CFG.get("channel", {})
LANG = CFG.get("language", {})
NARRATION = "zh" if os.environ.get("VLOG_SELFTEST") else LANG.get("narration", "zh")
ZH = NARRATION.startswith("zh")
CJK = bool(os.environ.get("VLOG_SELFTEST")) or LANG.get("length_unit", "cjk" if NARRATION[:2] in ("zh", "ja") else "words") == "cjk"
UI = cfg("ui", "language", "en")
FORMATS = CFG.get("formats", {})                         # wide / tall videos, the final size
PLATFORMS = list(cfg("platforms", "post_to", ["youtube"]))


def tr(en, zh):
    """A line of a report or a page in the studio's own language ([ui] language = "en" | "zh")."""
    return zh if UI == "zh" else en


def pid_alive(pid):
    import subprocess
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, errors="replace")
        return str(pid) in r.stdout
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def kill_tree(pid):
    import subprocess
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    else:
        subprocess.run(["pkill", "-TERM", "-P", str(pid)], capture_output=True)
        try:
            os.kill(pid, 9)
        except OSError:
            pass
