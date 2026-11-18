r"""Every name a script uses must exist (full debug: apply() lost "arg" and crashed every plain effect, only
found by a render). Python's own symbol tables, per function: a name read but never set there, not an argument, not a
module-level name, import or builtin, is reported. Covers the pipeline scripts and each trip's work/fx.py.

    python vlog_lint.py            exit 1 when anything is found
"""
import builtins
import importlib
import symtable
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import vlog_env  # noqa: E402

B = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__builtins__", "__spec__", "__loader__", "__package__"}


def module_names(top, src_path):
    names = set()
    for s in top.get_symbols():
        if s.is_assigned() or s.is_imported() or s.is_namespace():
            names.add(s.get_name())
    text = src_path.read_text(encoding="utf-8")
    if "import *" in text:                              # "from vlog_fx import *": everything public of that module
        import re
        for mod in re.findall(r"^from (\S+) import \*", text, flags=re.M):
                try:
                    m = importlib.import_module(mod)
                    names |= {n for n in dir(m) if not n.startswith("_")}
                except Exception as e:                  # noqa: BLE001
                    print(f"  (could not import {mod} for {src_path.name}: {e})")
    return names


def check(path):
    src = path.read_text(encoding="utf-8")
    top = symtable.symtable(src, str(path), "exec")
    mod = module_names(top, path)
    bad = []

    def walk(t):
        for s in t.get_symbols():
            n = s.get_name()
            if not s.is_referenced():
                continue
            if s.is_global() and not s.is_assigned() and n not in mod and n not in B:
                bad.append((t.get_name(), t.get_lineno(), n))
        for c in t.get_children():
            walk(c)

    for c in top.get_children():
        walk(c)
    for s in top.get_symbols():                          # module level: read but never set or imported
        n = s.get_name()
        if s.is_referenced() and not (s.is_assigned() or s.is_imported()) and n not in B and n not in mod:
            bad.append(("<module>", 0, n))
    return bad


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = sorted(HERE.glob("*.py")) + sorted(vlog_env.TRIPS.glob("*/work/fx.py"))
    total = 0
    for f in files:
        try:
            bad = check(f)
        except SyntaxError as e:
            print(f"SYNTAX {f.name}: {e}")
            total += 1
            continue
        for fn, line, n in bad:
            print(f"UNDEFINED {f.relative_to(f.parents[2]) if 'trips' in str(f) else f.name}: {n!r} in {fn} (line {line})")
        total += len(bad)
    print(f"# {len(files)} files, {total} undefined name(s)")
    sys.exit(1 if total else 0)
