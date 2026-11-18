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


# Subtitle files are named <name>.<language>_<COUNTRY>.srt (subtitles.en_GB.srt, short.zh_CN.srt): Facebook accepts
# no other shape, and only these language and country pairs (its help page "What is the naming convention for SubRip
# (.srt) files?", read 2026-11-18). YouTube takes the same files. [language] subtitle_locales = {en = "en_IN"} overrides.
FB_LOCALES = ("en_GB en_US af_ZA ar_AR ay_BO az_AZ be_BY bg_BG bn_IN bs_BA ca_ES ck_US cs_CZ cx_PH cy_GB da_DK de_DE el_GR en_IN eo_EO es_CL es_CO es_ES es_LA es_MX es_VE et_EE eu_ES fa_IR fi_FI fo_FO fr_CA fr_FR fy_NL ga_IE gl_ES gn_PY gu_IN gx_GR he_IL hi_IN hr_HR hu_HU hy_AM id_ID is_IS it_IT ja_JP jv_ID ka_GE kk_KZ km_KH kn_IN ko_KR ku_TR la_VA li_NL lt_LT lv_LV mg_MG mk_MK ml_IN mn_MN mr_IN ms_MY mt_MT nb_NO ne_NP nl_BE nl_NL nn_NO pa_IN pl_PL ps_AF pt_BR pt_PT qu_PE rm_CH ro_RO ru_RU sa_IN se_NO sk_SK sl_SI so_SO sq_AL sr_RS sv_SE sw_KE sy_SY ta_IN te_IN tg_TJ th_TH tl_PH tr_TR tt_RU uk_UA ur_PK uz_UZ vi_VN xh_ZA yi_DE zh_CN zh_HK zh_TW zu_ZA").split()
_FIRST = {"en": "en_US", "es": "es_ES", "fr": "fr_FR", "nl": "nl_NL", "pt": "pt_BR", "zh": "zh_CN"}


def locale(lang):
    """A language code as the locale subtitle files are named with: en -> en_US (en_GB with British spelling)."""
    own = LANG.get("subtitle_locales", {})
    if lang in own:
        return own[lang]
    lang = lang.replace("-", "_")
    if "_" in lang:
        a, b = lang.split("_", 1)
        return f"{a.lower()}_{b.upper()}"
    if lang == "en" and LANG.get("british_spelling"):
        return "en_GB"
    return _FIRST.get(lang) or next((c for c in FB_LOCALES if c.startswith(lang + "_")), f"{lang}_{lang.upper()}")


def srt_name(lang, short=False):
    return f"{'short' if short else 'subtitles'}.{locale(lang)}.srt"


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
