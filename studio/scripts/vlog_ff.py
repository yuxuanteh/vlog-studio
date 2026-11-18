"""The one way the trip pipeline runs ffmpeg / ffprobe.

A drop-in for subprocess.run: same arguments, same return value. It adds what every call needs and some lacked:
- `-nostdin` and no stdin, so ffmpeg can never sit waiting for keyboard input (unless the call feeds stdin itself);
- a time limit (`timeout`, default 3 h for ffmpeg, 2 min for ffprobe), so a frozen call ends instead of hanging;
- on failure with check=True, the last lines of ffmpeg's error output in the exception, so the log says why.
The stall watchdog (vlog_watch.py) still guards whole runs; this guards each call.
"""
import subprocess

import vlog_env

DEFAULT_TIMEOUT = {vlog_env.FFMPEG: 3 * 3600, vlog_env.FFPROBE: 120}


def _feeds_stdin(cmd, kw):
    return "input" in kw or "stdin" in kw or any(a in ("-", "pipe:", "pipe:0") for i, a in enumerate(cmd[1:])
                                                  if i > 0 and cmd[i] == "-i")


def run(cmd, **kw):
    cmd = [str(c) for c in cmd]
    exe = cmd[0]
    if exe == vlog_env.FFMPEG and "-nostdin" not in cmd and not _feeds_stdin(cmd, kw):
        cmd = [exe, "-nostdin"] + cmd[1:]
    if not _feeds_stdin(cmd, kw):
        kw.setdefault("stdin", subprocess.DEVNULL)
    kw.setdefault("timeout", DEFAULT_TIMEOUT.get(exe, 3 * 3600))
    check = kw.pop("check", False)
    if check and not kw.get("capture_output") and "stderr" not in kw:
        kw["stderr"] = subprocess.PIPE                 # keep the error text so the exception can show it
        r = subprocess.run(cmd, **kw)
        if r.returncode:
            err = r.stderr or b""
            tail = (err if isinstance(err, str) else err.decode("utf-8", "replace")).strip().splitlines()[-6:]
            raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, "\n".join(tail))
        return r
    r = subprocess.run(cmd, **kw)
    if check and r.returncode:
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)
    return r
