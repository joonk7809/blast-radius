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


def _ctx():
    if _cur[0] is None:
        return ""
    return _cur[0] + ("|" + ">".join(_stack) if _stack else "")


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
    _switch()


def pytest_runtest_teardown(item):
    _stack.clear()


def pytest_runtest_logreport(report):
    if report.when == "call":
        _dur[report.nodeid] = (report.duration, report.outcome)
    if report.when == "teardown":
        _cur[0] = None
        _switch()


def pytest_sessionfinish(session):
    out = os.environ.get("TRACE_OUT", "/out/trace.json")
    json.dump({"opens": {k: sorted(v) for k, v in _opens.items()}, "dur": _dur}, _orig_open(out, "w"))
