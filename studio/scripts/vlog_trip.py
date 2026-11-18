r"""Each trip's own settings, kept in the trip's folder (nothing written for one trip may sit in
the shared scripts, where the next trip would quietly inherit it or miss its own).

    <trip>/work/trip-settings.json
      fixes        [[heard, meant], ...]   Whisper's mishearings of this trip's places and names (filled at the start of
                                           the trip from the schedule and the papers, then while editing)
      words        [...]                   place / rock / person names the Chinese word splitter must keep whole
      take_labels  [...]                   words said only to label a take ("VLOG预告"), not counted as speech
      raw_mirrors  [...]                   local copies of raw/ on this computer (a file is used when name and size match)
      limits       {name: value}           this trip's own limits, only after the director has seen the numbers
                                           (vlog_limits.py measures the trip against the defaults below)

General things that hold for every trip (geology terms Whisper mishears, the channel's own words) stay here.
"""
import json
from pathlib import Path

DEFAULT_LIMITS = {
    "shake_stab": 0.6,        # a clip's average shake above this: the shot is stabilised (motion files, clip_motion.py)
    "shake_warn": 1.0,        # a second above this in the part used: told in the picture check
    "shake_violent": 1.6,     # a second above this: the shot slides to a calmer stretch, picks are warned
    "shake_track_stab": 1.0,  # a shot with a tracked effect is stabilised (before tracking) above this
    "similar": 0.9,           # two shots in a row this alike: told in the picture check
}

# mishearings and names that come back on every trip of this channel: [language] fixes / words in vlog.toml
import vlog_env  # noqa: E402

GENERAL_FIXES = [tuple(x) for x in vlog_env.LANG.get("fixes", [])]
GENERAL_WORDS = list(vlog_env.LANG.get("words", []))

def clip_stem(c):
    """The name a clip goes by in edit lists, sheets and work files: its file name without the ending, or the index
    entry's own "stem" when two files of a trip share a name (the re-recording Rerecord\\C0022.MP4 and the
    Day 4 recap Day4\\C0022.MP4; the camera's counter starts again, and files in raw/ are never renamed)."""
    return c.get("stem") or Path(c["file"].replace("\\", "/")).stem


def clip_table(rows):
    """name -> index entry, for the rows of footage-index.json. A clip with its own "stem" is found only under that."""
    return {clip_stem(c): c for c in rows}


_CACHE = {}
_SEEN = {}                    # file -> (when it was last looked at, its change time)


def settings(trip_dir):
    """The trip's settings file, read again only when it has changed. The file sits on Google Drive, where asking
    "has it changed?" costs about a millisecond, and the build asks thousands of times (12 of the 13 s
    the editing page took per edit on v02 went here), so the question is asked at most once every 2 seconds."""
    import time
    f = Path(trip_dir) / "work" / "trip-settings.json"
    name, now = str(f), time.monotonic()
    seen = _SEEN.get(name)
    if seen is None or now - seen[0] > 2.0:
        seen = _SEEN[name] = (now, f.stat().st_mtime if f.exists() else 0)
    key = (name, seen[1])
    if key not in _CACHE:
        _CACHE[key] = json.loads(f.read_text(encoding="utf-8")) if seen[1] else {}
    return _CACHE[key]


def fixes(trip_dir):
    return [tuple(x) for x in settings(trip_dir).get("fixes", [])] + GENERAL_FIXES


def words(trip_dir):
    return list(settings(trip_dir).get("words", [])) + GENERAL_WORDS


def take_labels(trip_dir):
    return list(settings(trip_dir).get("take_labels", []))


def mirrors(trip_dir):
    return [Path(p) for p in settings(trip_dir).get("raw_mirrors", [])]


def limit(trip_dir, name):
    if name in ("shake_stab", "shake_track_stab") and not vlog_env.cfg("look", "steady", True):
        return 1e9                                    # [look] steady = false: no shot is steadied by itself (^ still forces one)
    return float(settings(trip_dir).get("limits", {}).get(name, DEFAULT_LIMITS[name]))


def meta(trip_dir):
    """Phrases of this trip that were said to the editor, not to the viewer (cut by default)."""
    return list(settings(trip_dir).get("meta", []))


_ADDED = set()


def teach_words(trip_dir):
    """Give the Chinese word splitter this trip's names (once per process and trip). Other languages need none."""
    if not vlog_env.ZH:
        return
    import jieba
    jieba.setLogLevel(60)
    if str(trip_dir) in _ADDED:
        return
    for w in words(trip_dir):
        jieba.add_word(w)
    _ADDED.add(str(trip_dir))
