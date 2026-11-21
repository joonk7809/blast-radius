import builtins, io, json, os, pickle, sys, unittest
import concurrent.futures as _cf
import coverage

_cov = None
_cur = [None]
_stack = []
_seen = {}
_fut = [0]
_opens = {}
_dur = {}
_orig_open = builtins.open


_stmt = [None]
_smap = {}
STMT_MIN = int(os.environ.get("STMT_MIN", "20"))
TOOL = 4


def _ctx():
    if _cur[0] is None:
        return ""
    if _stack:
        return _cur[0] + "|" + ">".join(_stack)
    if _stmt[0] is not None:
        return _cur[0] + "|t:%d" % _stmt[0]
    return _cur[0]


_ranges = {}
_trees = {}


def _on_line(code, line):
    r = _ranges.get(code)
    if r is None:
        return
    for i, (a, b) in enumerate(r):
        if a <= line <= b:
            if _stmt[0] != i:
                _stmt[0] = i
                if not _stack:
                    _switch()
            return


sys.monitoring.use_tool_id(TOOL, "stmtctx")
sys.monitoring.register_callback(TOOL, sys.monitoring.events.LINE, _on_line)


def stmt_ranges(fn):
    import ast
    code = fn.__code__
    try:
        tree = _trees.get(code.co_filename)
        if tree is None:
            tree = _trees[code.co_filename] = ast.parse(_orig_open(code.co_filename).read())
    except Exception:
        return None
    node = None
    for n in ast.walk(tree):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == code.co_name and (n.decorator_list[0].lineno if n.decorator_list else n.lineno) == code.co_firstlineno:
            node = n
            break
    if not isinstance(node, ast.FunctionDef) or node.decorator_list or len(node.body) < STMT_MIN:
        return None
    start = 1
    return [(st.lineno + start - 1, st.end_lineno + start - 1) for st in node.body]


def _switch():
    global _cov
    if _cov is None:
        _cov = coverage.Coverage.current()
    if _cov is not None:
        _cov.switch_context(_ctx())


def _rec(f):
    try:
        p = os.path.abspath(os.fspath(f))
    except Exception:
        return
    if _cur[0] and p.startswith("/sqlglot/") and not p.endswith((".py", ".pyc")):
        _opens.setdefault(_cur[0], set()).add(p[len("/sqlglot/"):])


def _open(f, *a, **k):
    _rec(f)
    return _orig_open(f, *a, **k)


builtins.open = _open
io.open = _open

_orig_subtest = unittest.TestCase.subTest


def _subkey(msg, params):
    base = repr((None if msg is unittest.case._subtest_msg_sentinel else msg, sorted(params.items())))
    full = ">".join(_stack + [base])
    n = _seen.get(full, 0)
    _seen[full] = n + 1
    return "s:" + base + ("#%d" % n if n else "")


class _Sub:
    def __init__(self, case, msg, params):
        self.inner = _orig_subtest(case, msg, **params)
        self.key = _subkey(msg, params)

    def __enter__(self):
        if not _stack and _stmt[0] is not None and _cur[0]:
            _smap.setdefault(_cur[0], {})[self.key] = _stmt[0]
        _stack.append(self.key)
        _switch()
        return self.inner.__enter__()

    def __exit__(self, *exc):
        try:
            return self.inner.__exit__(*exc)
        finally:
            _stack.pop()
            _switch()


def _subtest(self, msg=unittest.case._subtest_msg_sentinel, **params):
    return _Sub(self, msg, params)


unittest.TestCase.subTest = _subtest


class _Lazy:
    def __init__(self, fn, args, kwargs, k):
        self.fn, self.args, self.kwargs, self.k, self.state = fn, args, kwargs, k, None

    def _force(self):
        if self.state is None:
            outer = not _stack
            if outer:
                _stack.append("f:%d" % self.k)
                _switch()
            try:
                args, kwargs = pickle.loads(pickle.dumps((self.args, self.kwargs)))
                self.state = (True, pickle.loads(pickle.dumps(self.fn(*args, **kwargs))))
            except BaseException as e:
                self.state = (False, e)
            finally:
                if outer:
                    _stack.pop()
                    _switch()
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

    def add_done_callback(self, fn):
        fn(self)


class _SyncExecutor:
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kw):
        if initializer:
            initializer(*pickle.loads(pickle.dumps(initargs)))

    def submit(self, fn, *args, **kwargs):
        _fut[0] += 1
        return _Lazy(fn, args, kwargs, _fut[0] - 1)

    def map(self, fn, *iterables, **kw):
        return map(fn, *iterables)

    def shutdown(self, wait=True, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_cf.ProcessPoolExecutor = _SyncExecutor
_cf.wait = lambda fs, timeout=None, return_when=None: _cf._base.DoneAndNotDoneFutures(set(fs), set())
_cf.as_completed = lambda fs, timeout=None: iter(list(fs))


def pytest_runtest_setup(item):
    _cur[0] = item.nodeid
    _stack.clear()
    _seen.clear()
    _fut[0] = 0
    _stmt[0] = None
    _switch()


def pytest_runtest_call(item):
    fn = getattr(item, "obj", None)
    fn = getattr(fn, "__func__", fn)
    code = getattr(fn, "__code__", None)
    if code is None:
        return
    r = stmt_ranges(fn)
    if r:
        _ranges[code] = r
        sys.monitoring.set_local_events(TOOL, code, sys.monitoring.events.LINE)


def pytest_runtest_teardown(item):
    _stack.clear()
    if _stmt[0] is not None:
        _stmt[0] = None
        _switch()


def pytest_runtest_logreport(report):
    if report.when == "call":
        _dur[report.nodeid] = (report.duration, report.outcome)
    if report.when == "teardown":
        _cur[0] = None
        _switch()


def pytest_sessionfinish(session):
    out = os.environ.get("TRACE_OUT", "/out/trace.json")
    json.dump({"opens": {k: sorted(v) for k, v in _opens.items()}, "dur": _dur, "smap": _smap, "ranges": {c.co_filename + ":" + c.co_qualname: r for c, r in _ranges.items()}}, _orig_open(out, "w"))
