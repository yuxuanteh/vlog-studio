"""What this computer is, how fast it is, and about how long each step of making a vlog will take on it.

    python probe.py [--minutes 8] [--short 1] [--footage 2] [--talk 0.5] [--model large-v3|medium|small] [--json]
        --minutes  length of a usual long video     --short    length of a usual vertical video (minutes)
        --footage  hours filmed on a usual trip     --talk     hours of that with talking in it

Runs BEFORE anything is installed (Python's standard library only), so the person can decide what to install and
whether finished videos should be 4K or 1080p knowing what it costs in time and disk space. It reads the processor,
memory, graphics card and free disk space, runs two short speed tests (one processor core; and, when ffmpeg is
already there, a real video encode on all cores), and scales timings measured on a reference computer.

The reference computer: Intel Core Ultra 7 155H laptop (16 cores / 22 threads), 16 GB memory, no separate graphics
card, Windows 11, footage from a 4K camera. Its timings are in REF below. The estimates are rough (expect half to
double): how many shots are steadied or carry an effect, and how the footage was filmed, all move them.
"""
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent
WIN, MAC = os.name == "nt", sys.platform == "darwin"

# Measured on the reference computer (2026-11), with it otherwise idle. Seconds of computing per second of material.
REF = {
    "single": 2000.0,            # SHA-256 MB/s of one core
    "encode_fps": 115.0,         # libx264 medium, 1080p test pattern, frames per second
    "eff_threads": 9.5,          # 22 threads counted as min(threads, 16) ** 0.8
    "whisper": {"large-v3": 0.70, "medium": 0.35, "small": 0.13},   # per second of footage with talking, CPU int8
    #                              (large-v3 measured; medium and small scaled from their size)
    "whisper_load": 25,          # seconds to load the speech model, once per run
    "look": 0.25,                # contact sheets, scene changes, shake and sharpness: per second of footage
    "proxy": 0.35,               # a 720p working copy of 4K footage: per second of footage (an estimate)
    "copy": 2.0,                 # a checking copy (480p) of a video: per second of video
    "final_1080": 4.0,           # a 1080p final, wide or tall: per second of video
    "final_4k": 12.5,            # a 4K final: per second of video (measured: a 3.5-minute video in 44 minutes)
    "checks": 150,               # self-test, edit check, side effects, faces, stills: seconds per run, flat
    "rehearsal": 200,            # a final rehearses first at a tiny size: seconds, flat
    "gb_per_hour_4k": 45,        # disk: an hour of 4K camera footage
    "proxy_gb_per_hour": 0.9,    # disk: its 720p working copies
    "cache_gb_per_min_4k": 3.4,  # disk: render cache of a 4K final, per minute of video (a quarter of that at 1080p)
}


def sh(cmd, timeout=20):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace").stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def hardware():
    h = {"os": f"{platform.system()} {platform.release()}", "arch": platform.machine(), "threads": os.cpu_count() or 1,
         "cpu": platform.processor() or "", "cores": None, "ram_gb": None, "gpu": [], "nvidia_gb": None}
    if WIN:
        out = sh(["powershell", "-NoProfile", "-Command",
                  "$c = Get-CimInstance Win32_Processor | Select-Object -First 1; $c.Name; $c.NumberOfCores; "
                  "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB,1); "
                  "(Get-CimInstance Win32_VideoController).Name"], 40).splitlines()
        if len(out) >= 3:
            h["cpu"], h["cores"] = out[0].strip(), int(out[1] or 0) or None
            h["ram_gb"], h["gpu"] = float(out[2].replace(",", ".") or 0) or None, [g.strip() for g in out[3:] if g.strip()]
    elif MAC:
        h["cpu"] = sh(["sysctl", "-n", "machdep.cpu.brand_string"]) or h["cpu"]
        h["cores"] = int(sh(["sysctl", "-n", "hw.physicalcpu"]) or 0) or None
        h["ram_gb"] = round(int(sh(["sysctl", "-n", "hw.memsize"]) or 0) / 2 ** 30, 1) or None
        h["gpu"] = [l.split(":", 1)[1].strip() for l in sh(["system_profiler", "SPDisplaysDataType"], 40).splitlines() if "Chipset Model" in l]
    else:
        info = Path("/proc/cpuinfo").read_text(errors="replace") if Path("/proc/cpuinfo").exists() else ""
        h["cpu"] = next((l.split(":", 1)[1].strip() for l in info.splitlines() if l.startswith("model name")), h["cpu"])
        mem = Path("/proc/meminfo").read_text(errors="replace") if Path("/proc/meminfo").exists() else ""
        h["ram_gb"] = round(next((int(l.split()[1]) for l in mem.splitlines() if l.startswith("MemTotal")), 0) / 2 ** 20, 1) or None
        h["gpu"] = [l.split(":", 2)[-1].strip() for l in sh(["lspci"]).splitlines() if "VGA" in l or "3D controller" in l]
    nv = sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"])
    if nv:
        name, memmb = [x.strip() for x in nv.splitlines()[0].split(",")][:2]
        h["nvidia_gb"] = round(float(memmb) / 1024, 1)
        if name not in h["gpu"]:
            h["gpu"].append(name)
    try:
        h["free_gb"] = round(shutil.disk_usage(STUDIO).free / 1e9, 1)
    except OSError:
        h["free_gb"] = None
    return h


def bench_single(seconds=0.7, rounds=3):
    """SHA-256 over memory on one core, MB per second. Best of three short rounds, so a busy moment does not drag it down."""
    block, best = bytes(4 << 20), 0.0
    for _ in range(rounds):
        hsh, n, t0 = hashlib.sha256(), 0, time.perf_counter()
        while time.perf_counter() - t0 < seconds:
            hsh.update(block)
            n += 4
        best = max(best, n / (time.perf_counter() - t0))
    return best


def find_ffmpeg():
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        import tomllib
        b = tomllib.loads((STUDIO / "vlog.toml").read_text(encoding="utf-8")).get("paths", {}).get("ffmpeg_bin", "")
        f = Path(b) / ("ffmpeg.exe" if WIN else "ffmpeg")
        return str(f) if b and f.exists() else None
    except (OSError, ValueError):
        return None


def bench_encode(ffmpeg):
    """Encode 6 s of a moving 1080p test pattern with libx264 on all cores: frames per second."""
    out = Path(tempfile.gettempdir()) / "vlog-studio-probe.mp4"
    t0 = time.perf_counter()
    r = subprocess.run([ffmpeg, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1920x1080:r=30:d=6", "-c:v", "libx264",
                        "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", str(out)], capture_output=True, timeout=600)
    dt = time.perf_counter() - t0
    out.unlink(missing_ok=True)
    return 180 / dt if r.returncode == 0 else None


def fmt(sec):
    if sec < 90:
        return f"{max(sec, 1):.0f} s"
    if sec < 5400:
        return f"{sec / 60:.0f} min"
    return f"{sec / 3600:.1f} h"


def estimate(h, single, enc_fps, minutes, short, footage, talk, model):
    eff = min(h["threads"], 16) ** 0.8
    cpu = (REF["single"] / single) * (REF["eff_threads"] / eff)          # > 1 = slower than the reference
    video = (REF["encode_fps"] / enc_fps) if enc_fps else cpu
    gpu = bool(h["nvidia_gb"] and h["nvidia_gb"] >= (5 if model == "large-v3" else 3))
    w = REF["whisper"][model] * (0.08 if gpu else cpu)
    F, T, L, S = footage * 3600, talk * 3600, minutes * 60, short * 60
    once = [
        ("Write down everything said in the footage (speech recognition)", T * w + REF["whisper_load"] * cpu, "whisper"),
        ("Look through the footage: contact sheets, shake, sharpness", F * REF["look"] * video, "core"),
        ("720p working copies of the footage", F * REF["proxy"] * video, "core"),
    ]
    per = [
        (f"Checking copy of a {minutes:g}-minute video (each review round)", L * REF["copy"] * video + REF["checks"] * cpu),
        (f"Final of that video at 1080p", L * REF["final_1080"] * video + (REF["checks"] + REF["rehearsal"]) * cpu),
        (f"Final of that video at 4K", L * REF["final_4k"] * video + (REF["checks"] + REF["rehearsal"]) * cpu),
        (f"Checking copy of a {short:g}-minute vertical video", S * REF["copy"] * video + REF["checks"] * cpu),
        (f"Final of that vertical video (1080 x 1920)", S * REF["final_1080"] * video + (REF["checks"] + REF["rehearsal"]) * cpu),
    ]
    disk = {"footage_4k_gb": round(footage * REF["gb_per_hour_4k"]), "working_copies_gb": round(footage * REF["proxy_gb_per_hour"], 1),
            "cache_4k_gb": round(minutes * REF["cache_gb_per_min_4k"], 1), "cache_1080_gb": round(minutes * REF["cache_gb_per_min_4k"] / 4, 1)}
    return once, per, disk, {"cpu_factor": round(cpu, 2), "video_factor": round(video, 2), "whisper_on_gpu": gpu}


def advice(h, enc_fps, model, disk, footage):
    out = []
    ram = h["ram_gb"] or 0
    if ram and ram < 8:
        out.append(f"Memory is {ram} GB. The large-v3 speech model wants about 4 GB free and a 4K render more: choose the `small` or "
                   "`medium` model and 1080p finals, and close other programs while rendering.")
    elif ram and ram < 16:
        out.append(f"Memory is {ram} GB: 4K finals will work only with everything else closed; 1080p is the comfortable choice.")
    if h["nvidia_gb"]:
        out.append(f"NVIDIA graphics card with {h['nvidia_gb']} GB: speech recognition can run on it, about ten times faster "
                   "([whisper] device = \"cuda\", compute_type = \"float16\"; needs NVIDIA's cuBLAS and cuDNN libraries).")
    free = h.get("free_gb")
    need = disk["working_copies_gb"] + disk["cache_4k_gb"] + 5
    if free is not None and free < need * 2:
        out.append(f"{free} GB free where the studio is. A trip of {footage:g} h needs about {disk['working_copies_gb']} GB of working "
                   f"copies and up to {disk['cache_4k_gb']} GB of render cache per 4K video, on top of 1-6 GB for the studio itself.")
    out.append(f"Disk, for a trip of {footage:g} hours: about {disk['footage_4k_gb']} GB of 4K camera footage (yours, in the trips folder); "
               f"{disk['working_copies_gb']} GB of 720p working copies and {disk['cache_1080_gb']}-{disk['cache_4k_gb']} GB of render cache per video "
               "in the studio folder (both can be deleted when a trip is finished).")
    if enc_fps is None:
        out.append("ffmpeg is not installed yet, so the video-encode test was skipped and the estimates lean on the processor "
                   "test alone. Run this again after `setup_studio.py install core` for better numbers.")
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    a = sys.argv[1:]
    opt = {a[i]: a[i + 1] for i in range(len(a) - 1) if a[i].startswith("--")}
    minutes, short = float(opt.get("--minutes", 8)), float(opt.get("--short", 1))
    footage = float(opt.get("--footage", 2))
    talk = float(opt.get("--talk", footage / 4))
    model = opt.get("--model", "large-v3")
    h = hardware()
    single = bench_single()
    ff = find_ffmpeg()
    enc = bench_encode(ff) if ff else None
    once, per, disk, factors = estimate(h, single, enc, minutes, short, footage, talk, model)
    tips = advice(h, enc, model, disk, footage)
    if "--json" in a:
        print(json.dumps({"hardware": h, "single_mb_s": round(single), "encode_fps": enc and round(enc, 1), "factors": factors,
                          "once_per_trip": [{"step": s, "seconds": round(t), "part": p} for s, t, p in once],
                          "per_video": [{"step": s, "seconds": round(t)} for s, t in per], "disk": disk, "advice": tips},
                         ensure_ascii=False, indent=1))
        return
    print("THIS COMPUTER")
    print(f"  processor   {h['cpu']}  ({h['cores'] or '?'} cores, {h['threads']} threads)")
    print(f"  memory      {h['ram_gb'] or '?'} GB")
    print(f"  graphics    {', '.join(h['gpu']) or 'not detected'}" + (f"  (NVIDIA, {h['nvidia_gb']} GB)" if h["nvidia_gb"] else ""))
    print(f"  free disk   {h.get('free_gb')} GB where the studio is")
    print(f"  system      {h['os']} {h['arch']}")
    print("\nSPEED TESTS (reference laptop = 100 %)")
    print(f"  one processor core   {single / REF['single']:.0%}")
    print("  video encode         " + (f"{enc / REF['encode_fps']:.0%}  ({enc:.0f} frames per second at 1080p)" if enc else "not tested (no ffmpeg yet)"))
    print(f"\nONCE PER TRIP, for {footage:g} hours of footage, {talk:g} of them with talking (speech model: {model})")
    for step, t, _ in once:
        print(f"  {fmt(t):>8s}   {step}")
    print("\nPER VIDEO")
    for step, t in per:
        print(f"  {fmt(t):>8s}   {step}")
    print("  Rough numbers: expect anything from half to double. Close other heavy programs before a render: a busy")
    print("  computer can take twice as long, and this test itself reads low when something else is running.")
    print("\nWORTH KNOWING")
    for t in tips:
        print("  - " + t)


if __name__ == "__main__":
    main()
