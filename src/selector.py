import ast
import gzip
import json
import os
import pickle
import re
import select
import signal
import sys
import time

DATA = os.environ.get("BR_DATA", "/data")
SRC = os.environ.get("BR_SRC", "/sqlglot")
TMP = os.environ.get("BR_TMP", "/tmp")
HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.environ.get("BR_MAP", os.path.join(HERE, "covmeta.json"))
PARALLEL = int(os.environ.get("BR_PARALLEL", "2"))
HEAVY_MS = int(os.environ.get("BR_HEAVY_MS", "1000000"))
DEBUG = os.environ.get("BR_DEBUG", "0") == "1"
ZYGOTE = os.environ.get("BR_ZYGOTE", "1") == "1"
UNITEST = os.environ.get("BR_UNITEST", "0") == "1"
UNITS = os.environ.get("BR_UNITS", "1") == "1"
CANON = os.environ.get("BR_CANON", "1") == "1"
LISTRULE = os.environ.get("BR_LISTRULE", "1") == "1"
FAILFAST = os.environ.get("BR_FAILFAST", "1") == "1"
BUDGET_S = float(os.environ.get("BR_BUDGET_S", "150"))
T0 = time.monotonic()


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def parse_patch(text):
    files = []
    cur = None
    hunk = None
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            cur = {"old": m.group(1), "path": m.group(2), "hunks": [], "new_file": False, "deleted": False}
            files.append(cur)
            hunk = None
            continue
        if cur is None:
            continue
        if hunk is None:
            if line.startswith("new file mode"):
                cur["new_file"] = True
            elif line.startswith("deleted file mode"):
                cur["deleted"] = True
            elif line.startswith("--- ") or line.startswith("+++ ") or line.startswith("index ") or line.startswith("similarity") or line.startswith("rename "):
                pass
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            hunk = {"old_start": int(m.group(1)), "old_len": int(m.group(2) or 1), "lines": []}
            cur["hunks"].append(hunk)
            continue
        if hunk is None:
            continue
        if line.startswith("\\"):
            if hunk["lines"]:
                tag, body = hunk["lines"][-1]
                hunk["lines"][-1] = (tag, body.rstrip("\n").rstrip("\r") if body.endswith("\n") else body)
            continue
        tag = line[:1]
        if tag in " -+":
            hunk["lines"].append((tag, line[1:]))
        elif line in ("\n", "\r\n"):
            hunk["lines"].append((" ", line))
    return files


def apply_file(old_text, hunks):
    old = old_text.splitlines(keepends=True)
    out = []
    pos = 0
    for h in hunks:
        start = h["old_start"] - 1 if h["old_len"] else h["old_start"]
        out.extend(old[pos:start])
        pos = start
        for tag, body in h["lines"]:
            if tag == " ":
                out.append(old[pos])
                pos += 1
            elif tag == "-":
                pos += 1
            else:
                out.append(body)
    out.extend(old[pos:])
    return "".join(out)


def changed_old_lines(hunks):
    removed, anchors = set(), set()
    for h in hunks:
        ln = h["old_start"] if h["old_len"] else h["old_start"] + 1
        for tag, _ in h["lines"]:
            if tag == "-":
                removed.add(ln)
                ln += 1
            elif tag == "+":
                anchors.add(ln - 1)
                anchors.add(ln)
            else:
                ln += 1
    return removed, anchors


def _identity_safe(node):
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    return (
        isinstance(node, ast.Attribute)
        and node.attr.isupper()
        and isinstance(node.value, (ast.Name, ast.Attribute))
        and (node.value.id if isinstance(node.value, ast.Name) else node.value.attr)[:1].isupper()
    )


class _Canon(ast.NodeTransformer):
    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and _identity_safe(node.comparators[0]):
            if isinstance(node.ops[0], ast.Is):
                node.ops = [ast.Eq()]
            elif isinstance(node.ops[0], ast.IsNot):
                node.ops = [ast.NotEq()]
        return node


def strip_ast(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    if CANON:
        tree = _Canon().visit(tree)
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


class Units:
    def __init__(self, text):
        self.tree = ast.parse(text)
        self.spans = []
        self._walk(self.tree, False, [])

    def _walk(self, node, runtime, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.stmt, ast.Lambda, ast.comprehension)) and hasattr(child, "lineno"):
                is_fn = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                head_end = child.end_lineno
                body = getattr(child, "body", None)
                if isinstance(body, list) and body and isinstance(child, ast.stmt):
                    head_end = max(child.lineno, body[0].lineno - 1)
                    first = child.lineno
                    for d in getattr(child, "decorator_list", []):
                        first = min(first, d.lineno)
                    self.spans.append((first, head_end, child.end_lineno, runtime, child))
                else:
                    self.spans.append((child.lineno, child.end_lineno, child.end_lineno, runtime, child))
                self._walk(child, runtime or is_fn, stack)
            else:
                self._walk(child, runtime, stack)

    def unit_for(self, line):
        best = None
        for first, head_end, end, runtime, node in self.spans:
            if first <= line <= end:
                inner = first <= line <= head_end
                size = (head_end if inner else end) - first
                if inner and (best is None or size <= best[0]):
                    best = (size, first, head_end, runtime, node)
        return best


def merge(a, b):
    for n, keys in b.items():
        if n in a:
            if a[n] is None or keys is None:
                a[n] = None
            else:
                a[n] = a[n] | keys
        else:
            a[n] = None if keys is None else set(keys)
    return a


def full(nums):
    return {n: None for n in nums}


class CovMap:
    def __init__(self, path, id_to_num):
        with open(path) as fh:
            m = json.load(fh)
        with open(os.path.join(os.path.dirname(path), "covsets.bin"), "rb") as fh:
            raw = fh.read()
        n = int.from_bytes(raw[:4], "little")
        self._offs = memoryview(raw)[4:4 + 4 * n].cast("I")
        self._data = memoryview(raw)[4 + 4 * n:].cast("H")
        self._cache = {}
        self.idx_to_num = [id_to_num.get(t) for t in m["tests"]]
        self.units = [(self.idx_to_num[t], k if UNITS else "") for t, k in m.get("units", [[i, ""] for i in range(len(m["tests"]))])]
        self.nunits = {self.idx_to_num[int(t)]: c for t, c in m.get("nunits", {}).items()}
        self.files = m["files"]
        self.fixtures = m["fixtures"]
        self.by_file = {}
        for i, t in enumerate(m["tests"]):
            n = self.idx_to_num[i]
            if n is not None:
                self.by_file.setdefault(t.split("::")[0], []).append(n)

    def set(self, i):
        r = self._cache.get(i)
        if r is None:
            r = self._cache[i] = self._data[self._offs[i]:self._offs[i + 1]].tolist()
        return r

    def _from_units(self, us):
        out = {}
        for u in us:
            n, k = self.units[u]
            if n is None:
                continue
            if not k:
                out[n] = None
            elif out.get(n, 0) is not None:
                out.setdefault(n, set()).add(k)
        return out

    def tests_for_lines(self, path, lines):
        fm = self.files.get(path)
        if not fm:
            return {}
        lm = fm["lines"]
        us = set()
        for ln in lines:
            s = lm.get(str(ln))
            if s is not None:
                us.update(self.set(s))
        return self._from_units(us)

    def tests_touching_file(self, path):
        fm = self.files.get(path)
        if not fm:
            return {}
        us = set()
        for s in set(fm["lines"].values()):
            us.update(self.set(s))
        return full(self._from_units(us))


def module_test_files(path, cov):
    stem = os.path.splitext(os.path.basename(path))[0]
    out = set()
    for cand in (f"tests/dialects/test_{stem}.py", f"tests/test_{stem}.py"):
        out.update(cov.by_file.get(cand, []))
    return out


def candidates_for(f, old_text, new_text, cov, notes):
    r = _candidates_for(f, old_text, new_text, cov, notes)
    return r if isinstance(r, dict) else full(r)


def _candidates_for(f, old_text, new_text, cov, notes):
    path = f["path"]
    if path.startswith("sqlglot/") and path.endswith(".py"):
        if old_text is not None and new_text is not None:
            a, b = strip_ast(old_text), strip_ast(new_text)
            if a is not None and a == b:
                notes.append("ast-noop")
                return set()
        if old_text is None or f["deleted"]:
            notes.append("newfile-or-deleted")
            return merge(cov.tests_touching_file(path), full(module_test_files(path, cov)))
        removed, anchors = changed_old_lines(f["hunks"])
        try:
            units = Units(old_text)
        except SyntaxError:
            notes.append("old-unparsable")
            return cov.tests_touching_file(path)
        out = {}
        importtime = False
        for ln in sorted(removed | anchors):
            u = units.unit_for(ln)
            if u is None:
                continue
            _, first, last, runtime, node = u
            merge(out, cov.tests_for_lines(path, range(first, last + 1)))
            if not runtime:
                importtime = True
        if importtime:
            notes.append("importtime")
            merge(out, cov.tests_touching_file(path))
            merge(out, full(module_test_files(path, cov)))
        return out
    if path.startswith("tests/") and path.endswith(".py"):
        if os.path.basename(path).startswith("test_"):
            notes.append("testfile")
            return set(cov.by_file.get(path, []))
        notes.append("test-support")
        return {n for p, ns in cov.by_file.items() for n in ns}
    if path.startswith("tests/"):
        if path in cov.fixtures:
            notes.append("fixture")
            return {cov.idx_to_num[i] for i in cov.fixtures[path] if cov.idx_to_num[i] is not None}
        notes.append("unmapped-fixture")
        base = os.path.basename(path)
        out = set()
        for tf, nums in cov.by_file.items():
            try:
                with open(os.path.join(SRC, tf), encoding="utf-8") as fh:
                    if base in fh.read() or os.path.splitext(base)[0] in fh.read():
                        out.update(nums)
            except OSError:
                pass
        return out
    notes.append("other:" + path)
    return set()


def _materialize(dst, src):
    os.makedirs(dst)
    if os.path.isdir(src):
        for e in os.listdir(src):
            os.symlink(os.path.join(src, e), os.path.join(dst, e))


def build_overlay(root, patched):
    if not os.path.isdir(root):
        _materialize(root, SRC)
    for rel, content in patched.items():
        parts = rel.split("/")
        dst, src = root, SRC
        for part in parts[:-1]:
            dst, src = os.path.join(dst, part), os.path.join(src, part)
            if os.path.islink(dst):
                os.unlink(dst)
                _materialize(dst, src)
            elif not os.path.exists(dst):
                _materialize(dst, src)
        target = os.path.join(dst, parts[-1])
        if os.path.lexists(target):
            os.unlink(target)
        if content is not None:
            with open(target, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)


def rmtree(path):
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
        return
    for e in os.listdir(path):
        rmtree(os.path.join(path, e))
    os.rmdir(path)


def preimport():
    import concurrent.futures
    import unittest
    import unittest.mock
    import multiprocessing
    import tracemalloc
    import csv
    import datetime
    import decimal
    import gc
    for name in ("duckdb", "numpy", "pandas", "pandas.testing"):
        try:
            __import__(name)
        except Exception:
            pass


class LazyFuture:
    def __init__(self, fn, args, kwargs):
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.state = None

    def _force(self):
        if self.state is None:
            try:
                args, kwargs = pickle.loads(pickle.dumps((self.args, self.kwargs)))
                self.state = (True, pickle.loads(pickle.dumps(self.fn(*args, **kwargs))))
            except BaseException as e:
                self.state = (False, e)
        return self.state

    def result(self, timeout=None):
        ok, v = self._force()
        if ok:
            return v
        raise v

    def exception(self, timeout=None):
        ok, v = self._force()
        return None if ok else v

    def done(self):
        return True

    def cancel(self):
        return False

    def cancelled(self):
        return False

    def add_done_callback(self, fn):
        fn(self)


class SyncExecutor:
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kw):
        if initializer:
            initializer(*pickle.loads(pickle.dumps(initargs)))

    def submit(self, fn, *args, **kwargs):
        return LazyFuture(fn, args, kwargs)

    def map(self, fn, *iterables, **kw):
        return map(fn, *iterables)

    def shutdown(self, wait=True, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.shutdown()
        return False


def lazy_wait(fs, timeout=None, return_when=None):
    import concurrent.futures
    return concurrent.futures._base.DoneAndNotDoneFutures(set(fs), set())


def lazy_as_completed(fs, timeout=None):
    return iter(list(fs))


def install_futures():
    import concurrent.futures
    concurrent.futures.ProcessPoolExecutor = SyncExecutor
    concurrent.futures.wait = lazy_wait
    concurrent.futures.as_completed = lazy_as_completed


def child_run(root, test_ids, timeouts, wfd, sel, mode=None):
    if DEBUG:
        import faulthandler
        faulthandler.enable()
    import unittest
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    if not DEBUG:
        os.dup2(devnull, 2)
    os.environ["SKIP_INTEGRATION"] = "0"
    install_futures()
    if mode is not None and mode[0] == "swap":
        import builtins
        import io
        import zygote
        plans = [zygote.swap_plan(SRC, rel, old, new, changed, {}) for rel, old, new, changed in mode[1]]
        zygote.apply_swaps(plans, mode[2])
        for m in list(sys.modules.values()):
            for v in list(vars(m).values()) if m is not None and getattr(m, "__name__", "").startswith("tests") else []:
                if isinstance(v, type) and vars(v).get("_prewarmed"):
                    v.setUpClass = classmethod(lambda cls: None)
                    v.tearDownClass = classmethod(lambda cls: None)
        redirect = {os.path.join(SRC, rel): os.path.join(root, rel) for rel in mode[3]}
        if redirect:
            real_open = builtins.open

            def ropen(file, *a, **k):
                try:
                    key = os.path.abspath(os.fspath(file))
                except TypeError:
                    return real_open(file, *a, **k)
                return real_open(redirect.get(key, file), *a, **k)

            builtins.open = ropen
            io.open = ropen
        os.chdir(SRC)
    else:
        if mode is not None:
            for m in [m for m in sys.modules if m == "sqlglot" or m.startswith(("sqlglot.", "tests"))]:
                del sys.modules[m]
            if SRC in sys.path:
                sys.path.remove(SRC)
        os.chdir(root)
        sys.path.insert(0, root)
    out = os.fdopen(wfd, "w", buffering=1)

    def emit(tag, tid):
        out.write(f"{tag} {tid}\n")

    class Timeout(Exception):
        pass

    def on_alarm(signum, frame):
        raise Timeout()

    signal.signal(signal.SIGALRM, on_alarm)
    case_to_id = {}
    failed = set()
    cases = []
    for tid in test_ids:
        path, cls, meth = tid.split("::")
        mod = path[:-3].replace("/", ".")
        try:
            m = __import__(mod, fromlist=["_"])
            c = getattr(m, cls)(meth)
        except BaseException:
            emit("F", tid)
            continue
        case_to_id[id(c)] = tid
        cases.append(c)

    class Result(unittest.TestResult):
        def startTest(self, test):
            super().startTest(test)
            tid = case_to_id.get(id(test))
            ustate.update(tid=tid, allowed=sel.get(tid), stack=[], seen={}, fut=0)
            if tid:
                emit("S", tid)
                self.t0 = time.process_time()
                signal.setitimer(signal.ITIMER_REAL, timeouts.get(tid, 10.0))

        def stopTest(self, test):
            signal.setitimer(signal.ITIMER_REAL, 0)
            tid = case_to_id.get(id(test))
            if tid:
                emit("F" if tid in failed else "P", tid)
                emit("C", "%s %.3f" % (tid, time.process_time() - getattr(self, "t0", time.process_time())))
            super().stopTest(test)

        def _fail(self, test):
            tid = case_to_id.get(id(test))
            if tid:
                failed.add(tid)
                return
            desc = str(test)
            for c in cases:
                ctid = case_to_id[id(c)]
                cname = type(c).__module__ + "." + type(c).__qualname__
                if cname in desc or type(c).__module__ in desc:
                    failed.add(ctid)
                    emit("F", ctid)

        def addError(self, test, err):
            self._dbg(test, err)
            self._fail(test)

        def addFailure(self, test, err):
            self._dbg(test, err)
            self._fail(test)

        def _dbg(self, test, err):
            if DEBUG:
                import traceback
                sys.stderr.write("DBG %s\n%s\n" % (test, "".join(traceback.format_exception(*err))[-1500:]))

        def addSubTest(self, test, subtest, err):
            if err is not None:
                self._dbg(test, err)
                self._fail(test)

        def addUnexpectedSuccess(self, test):
            self._fail(test)

    orig_subtest = unittest.TestCase.subTest
    stop = {}
    ustate = {"tid": None, "allowed": None, "stack": [], "seen": {}, "fut": 0}
    for tid, keys in sel.items():
        if keys is not None:
            closed = set()
            for k in keys:
                parts = k.split(">")
                for i in range(1, len(parts) + 1):
                    closed.add(">".join(parts[:i]))
            sel[tid] = closed

    class SkipBody(Exception):
        pass

    class UnitSub:
        def __init__(self, case, msg, params):
            base = repr((None if msg is unittest.case._subtest_msg_sentinel else msg, sorted(params.items())))
            fullk = ">".join(ustate["stack"] + [base])
            n = ustate["seen"].get(fullk, 0)
            ustate["seen"][fullk] = n + 1
            self.key = "s:" + base + ("#%d" % n if n else "")
            self.path = ">".join(ustate["stack"] + [self.key])
            self.skip = ustate["allowed"] is not None and self.path not in ustate["allowed"]
            self.inner = None if self.skip else orig_subtest(case, msg, **params)

        def __enter__(self):
            ustate["stack"].append(self.key)
            if self.skip:
                sys.settrace(lambda *a: None)
                frame = sys._getframe(1)

                def tracer(fr, ev, arg):
                    raise SkipBody()

                frame.f_trace = tracer
                return None
            return self.inner.__enter__()

        def __exit__(self, et, ev, tb):
            ustate["stack"].pop()
            if self.skip:
                sys.settrace(None)
                sys._getframe(1).f_trace = None
                return et is SkipBody
            return self.inner.__exit__(et, ev, tb)

    def unit_subtest(self, msg=unittest.case._subtest_msg_sentinel, **params):
        if stop.get(id(self)):
            raise StopTest()
        return UnitSub(self, msg, params)

    def lazy_submit(self, fn, *args, **kwargs):
        k = ustate["fut"]
        ustate["fut"] += 1
        f = LazyFuture(fn, args, kwargs)
        if ustate["allowed"] is not None and ("f:%d" % k) not in ustate["allowed"]:
            f.skip_outer = True
        return f

    SyncExecutor.submit = lazy_submit
    orig_force = LazyFuture._force

    def force(self):
        if getattr(self, "skip_outer", False) and not ustate["stack"] and self.state is None:
            self.state = (True, None)
        return orig_force(self)

    LazyFuture._force = force

    class StopTest(Exception):
        pass

    def subtest(self, msg=unittest.case._subtest_msg_sentinel, **params):
        if stop.get(id(self)):
            raise StopTest()
        return orig_subtest(self, msg, **params)

    if UNITS:
        unittest.TestCase.subTest = unit_subtest
    elif FAILFAST:
        unittest.TestCase.subTest = subtest
    if FAILFAST:
        orig_add_subtest = Result.addSubTest

        def add_subtest(self, test, sub, err):
            if err is not None:
                stop[id(test)] = True
            orig_add_subtest(self, test, sub, err)

        Result.addSubTest = add_subtest
    suite = unittest.TestSuite(cases)
    try:
        suite.run(Result())
    except BaseException:
        pass
    emit("D", "-")
    out.flush()
    os._exit(0)


class Job:
    def __init__(self, cid, root, tests, timeouts, deadline, sel=None, mode=None):
        self.cid = cid
        self.root = root
        self.tests = tests
        self.timeouts = timeouts
        self.deadline = deadline
        self.status = {}
        self.tcpu = {}
        self.current = None
        self.done = False
        self.buf = b""
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(r)
            try:
                child_run(root, tests, timeouts, w, sel or {}, mode)
            except BaseException:
                if DEBUG:
                    import traceback
                    traceback.print_exc()
            finally:
                os._exit(1)
        os.close(w)
        self.pid = pid
        self.fd = r

    def feed(self):
        data = os.read(self.fd, 65536)
        if not data:
            self.finish()
            return
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            tag, tid = line.decode().split(" ", 1)
            if tag == "S":
                self.current = tid
            elif tag in ("P", "F"):
                self.status[tid] = tag
                self.current = None
            elif tag == "C":
                t, c = tid.rsplit(" ", 1)
                self.tcpu[t] = float(c)
            elif tag == "D":
                pass

    def kill(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.finish()

    def finish(self):
        if self.done:
            return
        self.done = True
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.cpu = 0.0
        try:
            _, st, ru = os.wait4(self.pid, 0)
            self.cpu = ru.ru_utime + ru.ru_stime
            self.exit = st
        except ChildProcessError:
            pass

    def unresolved(self):
        return [t for t in self.tests if t not in self.status]


def main():
    tests_doc = json.load(open(os.path.join(DATA, "tests.json")))
    tests = tests_doc["tests"]
    id_to_num = {t["id"]: t["number"] for t in tests}
    num_to_id = {t["number"]: t["id"] for t in tests}
    ms = {t["number"]: int(t["seconds"] * 1000 + 0.5) for t in tests}
    cov = CovMap(MAP_PATH, id_to_num)
    log("map loaded cpu=%.2f" % time.process_time())
    runcpu = json.load(open(os.path.join(HERE, "runcpu.json")))
    sys.path.insert(0, HERE)
    from split import split

    commits = sorted(p[:-6] for p in os.listdir(os.path.join(DATA, "commits")) if p.endswith(".patch"))
    plans = []
    for cid in commits:
        text = open(os.path.join(DATA, "commits", cid + ".patch"), encoding="utf-8", errors="surrogateescape").read()
        notes = []
        cands = {}
        patched = {}
        hunks_by = {}
        old_by = {}
        ok = True
        try:
            files = parse_patch(text)
            for f in files:
                src = os.path.join(SRC, f["old"])
                old_text = None
                if not f["new_file"] and os.path.exists(src):
                    with open(src, encoding="utf-8", newline="") as fh:
                        old_text = fh.read()
                new_text = None if f["deleted"] else apply_file(old_text or "", f["hunks"])
                patched[f["path"]] = new_text
                hunks_by[f["path"]] = f["hunks"]
                old_by[f["path"]] = old_text
                if f["old"] != f["path"]:
                    patched[f["old"]] = None
                merge(cands, candidates_for(f, old_text, new_text, cov, notes))
        except Exception as e:
            ok = False
            notes.append(f"error:{type(e).__name__}:{e}")
            cands = full(num_to_id)
        def est(n):
            c = runcpu.get(num_to_id[n], 0)
            if not UNITEST or cands[n] is None or not cov.nunits.get(n):
                return c
            return c * min(1.0, len(cands[n]) / cov.nunits[n])

        heavy = {n for n in cands if ms[n] >= HEAVY_MS or (LISTRULE and est(n) * 1000 > ms[n] + 2000)}
        light = sorted(set(cands) - heavy)
        sel = {num_to_id[n]: (None if cands[n] is None else sorted(cands[n])) for n in light}
        plans.append({"cid": cid, "hunks": hunks_by, "old": old_by, "patched": patched, "light": light, "heavy": heavy, "notes": notes, "ok": ok, "sel": sel})
        log(cid, "cands", len(cands), "partial", sum(1 for n in light if cands[n] is not None), "heavy", sorted(heavy), "est_cpu %.2f" % sum(est(n) for n in light), notes[:4])

    log("planned cpu=%.2f" % time.process_time())
    preimport()
    log("preimported cpu=%.2f" % time.process_time())
    zyg = None
    if ZYGOTE:
        import zygote
        install_futures()
        zygote.warm(SRC, sorted({num_to_id[n] for p in plans for n in p["light"]}))
        warm_lines = {p: set(v) for p, v in json.load(open(os.path.join(HERE, "warmmap.json"))).items()}
        code_idx = zygote.code_index()
        zyg = (zygote, warm_lines, code_idx)
        log("zygote warm done t=%.1f cpu=%.2f" % (time.monotonic() - T0, time.process_time()))
    results = {}
    pending = [p for p in plans if p["light"]]
    for p in plans:
        if not p["light"]:
            results[p["cid"]] = set(p["heavy"])
    pending.sort(key=lambda p: -sum(ms[n] for n in p["light"]))
    running = []
    queue = list(pending)
    while queue or running:
        while queue and len(running) < PARALLEL:
            p = queue.pop(0)
            if time.monotonic() - T0 > BUDGET_S:
                results[p["cid"]] = set(p["heavy"]) | set(p["light"])
                continue
            root = os.path.join(TMP, "ov", p["cid"])
            rmtree(root)
            build_overlay(root, p["patched"])
            ids = [num_to_id[n] for n in p["light"]]
            timeouts = {num_to_id[n]: max(3.0, ms[n] / 1000 * 10 + 2) for n in p["light"]}
            budget = sum(timeouts.values()) + 30
            mode = None
            if zyg is not None:
                mode = ("reimport",)
                zmod, warm_lines, code_idx = zyg
                swaps, nonpy, ok = [], [], True
                for rel, content in p["patched"].items():
                    if content is None or p["old"].get(rel) is None:
                        ok = False
                    elif rel.endswith(".py"):
                        removed, anchors = changed_old_lines(p["hunks"][rel])
                        plan = zmod.swap_plan(SRC, rel, p["old"][rel], content, removed | anchors, warm_lines)
                        if plan is None:
                            ok = False
                        else:
                            swaps.append((rel, p["old"][rel], content, removed | anchors))
                    else:
                        if rel in zmod.WARM_OPENED:
                            ok = False
                        nonpy.append(rel)
                if ok:
                    mode = ("swap", swaps, code_idx, nonpy)
                log(p["cid"], "mode", mode[0])
            p["job"] = Job(p["cid"], root, ids, timeouts, time.monotonic() + budget, p["sel"], mode)
            p["root"] = root
            running.append(p)
        fds = [p["job"].fd for p in running]
        r, _, _ = select.select(fds, [], [], 0.5)
        for p in list(running):
            job = p["job"]
            if job.fd in r:
                job.feed()
            if not job.done and time.monotonic() > job.deadline:
                job.kill()
            if job.done:
                running.remove(p)
                fail = {id_to_num[t] for t, s in job.status.items() if s == "F"}
                unresolved = job.unresolved()
                if unresolved:
                    log(p["cid"], "unresolved", len(unresolved), "current", job.current, "exit", getattr(job, "exit", None))
                    fail |= {id_to_num[t] for t in unresolved}
                results[p["cid"]] = fail | set(p["heavy"])
                rmtree(p["root"])
                top = sorted(job.tcpu.items(), key=lambda kv: -kv[1])[:4]
                log(p["cid"], "testcpu=%.2f" % sum(job.tcpu.values()), "top", " ".join("%s:%.2f" % (t.split("::")[-1], c) for t, c in top))
                log(p["cid"], "fail", sorted(fail), "heavy", sorted(p["heavy"]), "cpu=%.2f" % job.cpu, "t=%.1f" % (time.monotonic() - T0))
    for cid in commits:
        workers = split(sorted(results.get(cid, set())), ms)
        sys.stdout.write(json.dumps({"commit": cid, "workers": workers}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
