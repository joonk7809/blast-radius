import importlib, json, os, pkgutil, signal, sys, time, unittest

src, app, ids_path, out_dir = sys.argv[1:5]
nproc = int(sys.argv[5]) if len(sys.argv) > 5 else 4
sys.path[:0] = [src, app]
os.chdir(src)
os.environ["SKIP_INTEGRATION"] = "0"
import selector
selector.install_futures()
import sqlglot

for m in pkgutil.walk_packages(sqlglot.__path__, "sqlglot."):
    try:
        importlib.import_module(m.name)
    except Exception:
        pass
ids = open(ids_path).read().split()
for mod in sorted({t.split("::")[0][:-3].replace("/", ".") for t in ids}):
    try:
        importlib.import_module(mod)
    except Exception:
        pass
os.makedirs(out_dir, exist_ok=True)
pre = os.path.join(src, "sqlglot") + "/"


def child(i, tid):
    path, cls, meth = tid.split("::")
    hits = set()
    mon = sys.monitoring

    def on_line(code, line):
        if code.co_filename.startswith(pre):
            hits.add((code.co_filename[len(src) + 1:], line))
        return mon.DISABLE

    mon.use_tool_id(5, "cold")
    mon.register_callback(5, mon.events.LINE, on_line)
    signal.alarm(600)
    try:
        case = getattr(sys.modules[path[:-3].replace("/", ".")], cls)(meth)
        mon.set_events(5, mon.events.LINE)
        unittest.TestSuite([case]).run(unittest.TestResult())
    except BaseException:
        pass
    mon.set_events(5, 0)
    files = {}
    for f, ln in hits:
        files.setdefault(f, []).append(ln)
    with open(os.path.join(out_dir, "%d.json" % i), "w") as fh:
        json.dump({"id": tid, "files": {f: sorted(v) for f, v in files.items()}}, fh)


todo = [(i, t) for i, t in enumerate(ids) if not os.path.exists(os.path.join(out_dir, "%d.json" % i))]
todo.sort(key=lambda it: not it[1].startswith("tests/test_executor.py"))
running = {}
t0 = time.monotonic()
while todo or running:
    while todo and len(running) < nproc:
        i, tid = todo.pop(0)
        pid = os.fork()
        if pid == 0:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, 1)
            os.dup2(devnull, 2)
            try:
                child(i, tid)
            finally:
                os._exit(0)
        running[pid] = tid
    pid, _ = os.wait()
    running.pop(pid, None)
print("done %d tests %.0fs" % (len(ids), time.monotonic() - t0), file=sys.stderr)
