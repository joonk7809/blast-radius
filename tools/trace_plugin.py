import builtins, io, json, os, time
_cur = [None]
_opens = {}
_dur = {}
_orig_open = builtins.open
_orig_io_open = io.open
def _rec(f):
    try:
        p = os.path.abspath(os.fspath(f))
    except Exception:
        return
    if _cur[0] and p.startswith("/sqlglot/") and not p.endswith((".py", ".pyc")):
        _opens.setdefault(_cur[0], set()).add(p[len("/sqlglot/"):])
def _open(f, *a, **k):
    _rec(f); return _orig_open(f, *a, **k)
builtins.open = _open
io.open = _open
import pathlib
_orig_read_text = pathlib.Path.read_text
def pytest_runtest_setup(item):
    _cur[0] = item.nodeid
def pytest_runtest_call(item):
    _cur[0] = item.nodeid
def pytest_runtest_logreport(report):
    if report.when == "call":
        _dur[report.nodeid] = (report.duration, report.outcome)
def pytest_sessionfinish(session):
    out = os.environ.get("TRACE_OUT", "/out/trace.json")
    json.dump({"opens": {k: sorted(v) for k, v in _opens.items()}, "dur": _dur}, _orig_open(out, "w"))
import concurrent.futures as _cf
import pickle


class _SyncExecutor:
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kw):
        if initializer:
            initializer(*pickle.loads(pickle.dumps(initargs)))

    def submit(self, fn, *args, **kwargs):
        fut = _cf.Future()
        try:
            args, kwargs = pickle.loads(pickle.dumps((args, kwargs)))
            fut.set_result(pickle.loads(pickle.dumps(fn(*args, **kwargs))))
        except BaseException as e:
            fut.set_exception(e)
        return fut

    def map(self, fn, *iterables, **kw):
        return map(fn, *iterables)

    def shutdown(self, wait=True, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


_cf.ProcessPoolExecutor = _SyncExecutor
