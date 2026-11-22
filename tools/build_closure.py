import builtins
import gzip
import io
import json
import os
import sys

SRC, APP, IDS, OUT = sys.argv[1:5]
PART, NPART = int(sys.argv[5]), int(sys.argv[6])
sys.path.insert(0, APP)
import selector

selector.preimport()
selector.install_futures()
import subprocess
import unittest

os.chdir(SRC)
sys.path.insert(0, SRC)
os.environ["SKIP_INTEGRATION"] = "0"
TESTS_DIR = os.path.join(SRC, "tests") + os.sep


def probe(tid, wfd):
    codes = set()
    executed = set()
    spawned = []
    mon = sys.monitoring

    def on_start(code, offset):
        if code.co_filename.startswith(TESTS_DIR):
            codes.add("%s:%d" % (os.path.relpath(code.co_filename, SRC), code.co_firstlineno))
        if code.co_name == "<module>" and code.co_filename.startswith(SRC + os.sep) and code.co_filename.endswith(".py"):
            rel = os.path.relpath(code.co_filename, SRC)[:-3].replace(os.sep, ".")
            executed.add(rel[:-9] if rel.endswith(".__init__") else rel)
        return mon.DISABLE

    real_init = subprocess.Popen.__init__

    def popen(self, *a, **k):
        spawned.append(1)
        return real_init(self, *a, **k)

    subprocess.Popen.__init__ = popen
    touched = set()

    def note(x):
        try:
            full = os.path.abspath(os.fspath(x))
        except TypeError:
            return
        if full.startswith(SRC + os.sep):
            touched.add(os.path.relpath(full, SRC))

    def wrap(owner, name):
        real = getattr(owner, name)

        def f(p=".", *a, **k):
            note(p)
            return real(p, *a, **k)

        setattr(owner, name, f)

    for owner, name in ((os, "listdir"), (os, "scandir"), (builtins, "open"), (io, "open")):
        wrap(owner, name)
    os.system = lambda *a: spawned.append(1)
    mon.use_tool_id(mon.PROFILER_ID, "closure")
    mon.register_callback(mon.PROFILER_ID, mon.events.PY_START, on_start)
    mon.set_events(mon.PROFILER_ID, mon.events.PY_START)
    ok = True
    try:
        path, cls, meth = tid.split("::")
        m = __import__(path[:-3].replace("/", "."), fromlist=["_"])
        unittest.TestSuite([getattr(m, cls)(meth)]).run(unittest.TestResult())
    except BaseException:
        ok = False
    mon.set_events(mon.PROFILER_ID, 0)
    mods = sorted(executed | {k for k in sys.modules if k == "sqlglot" or k.startswith(("sqlglot.", "tests"))})
    with os.fdopen(wfd, "w") as fh:
        json.dump({"mods": mods, "code": sorted(codes), "spawn": bool(spawned), "fs": sorted(touched), "ok": ok}, fh)


ids = [l.strip() for l in open(IDS) if l.strip()][PART::NPART]
out = {}
for tid in ids:
    r, w = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(r)
        try:
            probe(tid, w)
        finally:
            os._exit(0)
    os.close(w)
    with os.fdopen(r) as fh:
        data = fh.read()
    os.waitpid(pid, 0)
    out[tid] = json.loads(data) if data else None
    print(PART, len(out), tid, file=sys.stderr, flush=True)
with gzip.open(OUT, "wt") as fh:
    json.dump(out, fh)
