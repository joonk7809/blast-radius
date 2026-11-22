import base64
import gzip
import json
import os
import sys
import types

SRC, OUT, NPART = sys.argv[1], sys.argv[2], int(sys.argv[3])
sys.dont_write_bytecode = True
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
os.environ["BR_SRC"] = SRC
os.environ["SKIP_INTEGRATION"] = "0"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import selector

selector.preimport()
selector.install_futures()
import unittest

os.chdir(SRC)
sys.path.insert(0, SRC)
TESTS_DIR = os.path.join(SRC, "tests") + os.sep
HELPERS = os.path.join(TESTS_DIR, "helpers.py")


def snapshot(mod):
    return {k: ("obj", id(v)) if isinstance(v, (types.FunctionType, type)) else selector.support_dumps(v) for k, v in vars(mod).items() if not k.startswith("__")}


def probe(path, tids, wfd):
    import tests.helpers as helpers
    pristine = snapshot(helpers)
    calls, owner, busy, dirty = [], {}, [], []
    mon = sys.monitoring

    def on_start(code, offset):
        if busy:
            return
        name = code.co_filename
        if not name.startswith(TESTS_DIR) or os.path.basename(name).startswith("test_"):
            return mon.DISABLE
        frame = top = sys._getframe(1)
        up = frame.f_back
        while up is not None:
            if up.f_code.co_filename == name:
                top = up
            up = up.f_back
        if top in owner:
            owner[top][4].add(code.co_firstlineno)
            return
        if top is not frame or top.f_code.co_name == "<module>":
            return
        if name != HELPERS or snapshot(helpers) != pristine:
            dirty.append(1)
        blob = digest = None
        if "<" not in code.co_qualname and "." not in code.co_qualname and not code.co_flags & 12 and not code.co_posonlyargcount:
            blob = selector.support_dumps(dict(frame.f_locals))
        if blob:
            busy.append(1)
            try:
                raw = selector.support_outcome(types.FunctionType(code, frame.f_globals), blob)
            finally:
                busy.clear()
            digest = raw and selector.support_digest(raw)
        owner[top] = [os.path.relpath(name, SRC), code.co_qualname, blob and base64.b64encode(blob).decode(), digest, {code.co_firstlineno}]
        calls.append(owner[top])

    def take():
        out = [c[:4] + [sorted(c[4])] for c in calls]
        calls.clear()
        owner.clear()
        return out

    mon.use_tool_id(mon.PROFILER_ID, "helpercalls")
    mon.register_callback(mon.PROFILER_ID, mon.events.PY_START, on_start)
    mon.set_events(mon.PROFILER_ID, mon.events.PY_START)
    out = {}
    try:
        m = __import__(path[:-3].replace("/", "."), fromlist=["_"])
    except BaseException:
        m = None
    boot, boot_dirty = take(), bool(dirty)
    for tid in tids if m is not None else ():
        dirty[:] = [1] if boot_dirty else []
        try:
            _, cls, meth = tid.split("::")
            unittest.TestSuite([getattr(m, cls)(meth)]).run(unittest.TestResult())
            ok = True
        except BaseException:
            ok = False
        got = take()
        if snapshot(helpers) != pristine:
            dirty.append(1)
        out[tid] = {"calls": boot + got if ok else None, "dirty": bool(dirty)}
    mon.set_events(mon.PROFILER_ID, 0)
    with os.fdopen(wfd, "w") as fh:
        json.dump(out, fh)


def run_part(ids, path):
    out = {}
    groups = {}
    for tid in ids:
        groups.setdefault(tid.split("::")[0], []).append(tid)
    for f, tids in sorted(groups.items()):
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(r)
            try:
                probe(f, tids, w)
            finally:
                os._exit(0)
        os.close(w)
        with os.fdopen(r) as fh:
            data = fh.read()
        os.waitpid(pid, 0)
        got = json.loads(data) if data else {}
        out.update({tid: got.get(tid) for tid in tids})
    with open(path, "w") as fh:
        json.dump(out, fh)


ids = sorted(json.load(open(os.path.join(selector.HERE, "covmeta.json")))["tests"])
pids = []
for part in range(NPART):
    pid = os.fork()
    if pid == 0:
        try:
            run_part(ids[part::NPART], "%s.part%d" % (OUT, part))
        finally:
            os._exit(0)
    pids.append(pid)
for pid in pids:
    os.waitpid(pid, 0)
recs = {}
for part in range(NPART):
    with open("%s.part%d" % (OUT, part)) as fh:
        recs.update(json.load(fh))
    os.remove("%s.part%d" % (OUT, part))
table, tests, dirty = {}, {}, []
for tid, rec in sorted(recs.items()):
    if rec is not None and rec["calls"] is not None:
        tests[tid] = sorted({table.setdefault((rel, name, blob, digest, tuple(lines)), len(table)) for rel, name, blob, digest, lines in rec["calls"]})
        if rec["dirty"]:
            dirty.append(tid)
doc = {"calls": [[rel, name, blob if digest else None, digest, list(lines)] for rel, name, blob, digest, lines in sorted(table, key=table.get)], "tests": tests, "dirty": dirty}
with gzip.open(OUT, "wt", compresslevel=9) as fh:
    json.dump(doc, fh, separators=(",", ":"))
print("helpercalls", len(recs), len(tests), len(doc["calls"]), len(dirty))
