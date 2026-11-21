import gzip
import json
import os
import pickle
import sys
import unittest
import attrtrace as AT
IDS = AT.IDS
NUM = AT.NUM
OUT = AT.OUT
_stack = []
_seen = {}
_fut = [0]
BUF = {}
ENT = {}
UNIT = {'': -1}
UNITS = ['']
PER = [dict() for _ in IDS]
FILE_BUCKET = {}
CLASS_BUCKET = {}
_state = {'phase': None, 'last_class': None, 'exec': False, 'init': False}

def _path():
    if _state['phase'] == 'setup':
        return '<setup>'
    if not _stack and _state['exec'] and (not _state['init']):
        return 'b:%d' % _fut[0]
    return '>'.join(_stack)

def _switch():
    AT.CUR = BUF.setdefault(_path(), set())
_orig_subtest = unittest.TestCase.subTest

def _subkey(msg, params):
    base = repr((None if msg is unittest.case._subtest_msg_sentinel else msg, sorted(params.items())))
    full = '>'.join(_stack + [base])
    n = _seen.get(full, 0)
    _seen[full] = n + 1
    return 's:' + base + ('#%d' % n if n else '')

class _Sub:

    def __init__(self, case, msg, params):
        was = AT.ON[0]
        AT.ON[0] = False
        try:
            self.key = _subkey(msg, params)
        finally:
            AT.ON[0] = was
        self.inner = _orig_subtest(case, msg, **params)

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
import concurrent.futures as _cf

class _Lazy:

    def __init__(self, fn, args, kwargs, k):
        self.fn, self.args, self.kwargs, self.k, self.state = (fn, args, kwargs, k, None)

    def _force(self):
        if self.state is None:
            outer = not _stack
            if outer:
                _stack.append('f:%d' % self.k)
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
        body = _state['phase'] is None and (not _stack)
        if body:
            _state['init'] = True
            _switch()
        try:
            if initializer:
                initializer(*pickle.loads(pickle.dumps(initargs)))
        finally:
            if body:
                _state['init'] = False
                _state['exec'] = True
                _switch()

    def submit(self, fn, *args, **kwargs):
        _fut[0] += 1
        _switch()
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

def _flush(idx, cls):
    d = PER[idx]
    if _state['last_class'] != cls:
        _state['last_class'] = cls
        raw = BUF.get('<setup>')
        if raw:
            CLASS_BUCKET.setdefault(cls, set()).update(AT.translate(raw))
    nsub = _fut[0]
    for path, raw in BUF.items():
        if not raw:
            continue
        if path.startswith('b:') and int(path[2:]) >= nsub:
            path = ''
        u = UNIT.get(path)
        if u is None:
            u = UNIT[path] = len(UNITS)
            UNITS.append(path)
        for e in AT.translate(raw):
            j = ENT.get(e)
            if j is None:
                j = ENT[e] = len(ENT)
            if u == -1:
                d[j] = None
            else:
                cur = d.get(j, 0)
                if cur is None:
                    continue
                if cur == 0:
                    d[j] = {u}
                else:
                    cur.add(u)
    BUF.clear()

def pytest_configure(config):
    AT.instrument()
    AT.ON[0] = True
    _switch()

def pytest_collectstart(collector):
    if collector.__class__.__name__ == 'Module':
        BUF.clear()
        _state['phase'] = None
        _stack.clear()
        _switch()

def pytest_collectreport(report):
    if report.nodeid.endswith('.py'):
        raw = set()
        for s in BUF.values():
            raw |= s
        FILE_BUCKET.setdefault(report.nodeid, set()).update(AT.translate(raw))
        BUF.clear()
        _switch()
import pytest

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    BUF.clear()
    _stack.clear()
    _seen.clear()
    _fut[0] = 0
    _state['exec'] = False
    _state['init'] = False
    _state['phase'] = 'setup'
    _switch()
    yield
    _state['phase'] = None
    _switch()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    _stack.clear()
    _state['phase'] = None
    _switch()
    yield
    _stack.clear()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    _stack.clear()
    _state['phase'] = 'setup'
    _switch()
    yield
    _state['phase'] = None
    idx = NUM.get(item.nodeid.split('[')[0])
    if idx is not None:
        _flush(idx, '::'.join(item.nodeid.split('::')[:2]))
    BUF.clear()
    _switch()

def pytest_sessionfinish(session):
    AT.ON[0] = False
    su = UNIT.setdefault('<setup>', len(UNITS))
    if su == len(UNITS):
        UNITS.append('<setup>')
    for i, t in enumerate(IDS):
        for e in CLASS_BUCKET.get('::'.join(t.split('::')[:2]), ()):
            j = ENT.get(e)
            if j is None:
                j = ENT[e] = len(ENT)
            cur = PER[i].get(j, 0)
            if cur is None:
                continue
            if cur == 0:
                PER[i][j] = {su}
            else:
                cur.add(su)
        fb = FILE_BUCKET.get(t.split('::')[0])
        if fb:
            for e in fb:
                j = ENT.get(e)
                if j is None:
                    j = ENT[e] = len(ENT)
                PER[i][j] = None
    os.makedirs(OUT, exist_ok=True)
    ents = [None] * len(ENT)
    for e, j in ENT.items():
        ents[j] = list(e)
    per = [[[j, None if v is None else sorted(v)] for j, v in d.items()] for d in PER]
    with gzip.open(os.path.join(OUT, 'reads_u.json.gz'), 'wt') as f:
        json.dump({'entries': ents, 'per': per, 'units': UNITS, 'tids': AT.TIDS}, f)
    sys.stderr.write(f'[attrtrace_u] wrote {len(ENT)} entries, {len(UNITS)} units\n')
