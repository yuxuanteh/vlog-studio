"""Run a long command under a stall watchdog (a frozen render must be noticed at once, not after
hours).

    python vlog_watch.py [--stall MIN] [--watch DIR] [--status FILE] -- <command ...>

Every 20 s it measures the command's whole process tree (CPU time of python, ffmpeg and every child) and the newest
file change under --watch. Either one moving = progress. No progress for --stall minutes (default 6) = frozen: the
whole tree is killed (taskkill /T, so no orphan keeps writing) and it prints "STALL: ..." and exits 124.
A one-line heartbeat goes to --status (default <studio>/status.txt): elapsed, CPU, last output line.
The command's own output passes through unchanged.
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

PS = ("$t=@{%d=1};$a=Get-CimInstance Win32_Process;do{$n=0;foreach($p in $a){if($t[[int]$p.ParentProcessId] -and "
      "-not $t[[int]$p.ProcessId]){$t[[int]$p.ProcessId]=1;$n++}}}while($n);$c=0;foreach($p in $a){if($t[[int]$p.ProcessId])"
      "{$c+=$p.KernelModeTime+$p.UserModeTime}};$c/1e7")


def tree_cpu_posix(pid):
    """CPU seconds of a process and all its children, from `ps` (macOS / Linux)."""
    try:
        rows = [l.split(None, 2) for l in subprocess.run(["ps", "-axo", "pid=,ppid=,time="], capture_output=True, text=True).stdout.splitlines()]
        kids, tree, n = {}, {int(pid)}, 0
        for p, pp, _ in rows:
            kids.setdefault(int(pp), []).append(int(p))
        while len(tree) != n:
            n = len(tree)
            for q in list(tree):
                tree.update(kids.get(q, []))
        def secs(t):
            d, _, r = t.partition("-")
            parts = [float(x) for x in (r or d).split(":")]
            return (int(d) * 86400 if r else 0) + sum(v * 60 ** k for k, v in enumerate(reversed(parts)))
        return sum(secs(t) for p, _, t in rows if int(p) in tree)
    except Exception:
        return 0.0


def kill_tree(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True)
        return
    subprocess.run(["pkill", "-TERM", "-P", str(pid)], capture_output=True)
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def tree_cpu(pid):
    if os.name != "nt":
        return tree_cpu_posix(pid)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", PS % pid], capture_output=True, text=True,
                             timeout=60, stdin=subprocess.DEVNULL).stdout.strip()
        return float(out.splitlines()[-1].replace(",", "."))
    except Exception as e:                      # a failed probe is not progress, but it is reported
        print(f"[watch] cpu probe failed: {e}", flush=True)
        return None


def newest(d):
    best = 0.0
    if d and d.exists():
        for p in d.rglob("*"):
            try:
                st = p.stat()
                best = max(best, st.st_mtime + st.st_size * 1e-12)
            except OSError:
                pass
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stall", type=float, default=6.0)
    ap.add_argument("--watch", type=Path)
    ap.add_argument("--status", type=Path, default=Path(__file__).resolve().parent.parent / "status.txt")
    ap.add_argument("cmd", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    cmd = a.cmd[1:] if a.cmd and a.cmd[0] == "--" else a.cmd
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
    last = [""]

    def pump():
        for line in proc.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            if line.strip():
                last[0] = line.strip()[:160]

    th = threading.Thread(target=pump, daemon=True)
    th.start()
    cpu0, files0, moved = -1.0, -1.0, time.time()
    while proc.poll() is None:
        time.sleep(20)
        if proc.poll() is not None:
            break
        cpu, files = tree_cpu(proc.pid), newest(a.watch)
        if (cpu is not None and cpu > cpu0 + 2.0) or files > files0:
            moved = time.time()
        cpu0 = cpu if cpu is not None else cpu0
        files0 = max(files0, files)
        idle = (time.time() - moved) / 60
        try:
            a.status.write_text(f"{time.strftime('%H:%M:%S')} running {(time.time() - t0) / 60:.1f} min, cpu {cpu0:.0f} s, "
                                f"idle {idle:.1f} min | {' '.join(cmd[-3:])} | {last[0]}\n", encoding="utf-8")
        except OSError:
            pass
        if idle >= a.stall:
            print(f"STALL: no CPU and no file change for {idle:.1f} min; last output: {last[0]}", flush=True)
            kill_tree(proc.pid)
            th.join(5)
            sys.exit(124)
    th.join(5)
    sys.exit(proc.returncode)


if __name__ == "__main__":
    main()
