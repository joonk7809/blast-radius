import enum
import gzip
import json
import os
import sys
import types
sys.path.insert(0, os.environ.get('IT_DIR', '/it'))
import importtime as IT
OUT = os.environ.get('TRACE_OUT', '/out')
IDS = [l.strip() for l in open(os.environ.get('IDS', '/it/ids.txt'))]
NUM = {t: i for i, t in enumerate(IDS)}
CUR = set()
ON = [False]
REG = {}
UNREG = {}

class Desc:
    __slots__ = ('cn', 'a', 'v')

    def __init__(self, cn, a, v):
        self.cn, self.a, self.v = (cn, a, v)

    def __get__(self, inst, owner=None):
        if ON[0]:
            o = id(owner)
            if o not in REG:
                UNREG[o] = owner
            CUR.add((self, o))
        return self.v

    def __repr__(self):
        return f'<traced {self.cn}.{self.a}>'

def _rec(tid, k):
    if ON[0]:
        try:
            CUR.add((tid, k))
        except TypeError:
            pass
STAR = '\x01*'

class TDict(dict):
    __slots__ = ('_tid',)

    def __getitem__(self, k):
        _rec(self._tid, k)
        return dict.__getitem__(self, k)

    def get(self, k, d=None):
        _rec(self._tid, k)
        return dict.get(self, k, d)

    def __contains__(self, k):
        _rec(self._tid, k)
        return dict.__contains__(self, k)

    def __iter__(self):
        _rec(self._tid, STAR)
        return dict.__iter__(self)

    def keys(self):
        _rec(self._tid, STAR)
        return dict.keys(self)

    def values(self):
        _rec(self._tid, STAR)
        return dict.values(self)

    def items(self):
        _rec(self._tid, STAR)
        return dict.items(self)

    def copy(self):
        _rec(self._tid, STAR)
        return dict.copy(self)

    def __or__(self, o):
        _rec(self._tid, STAR)
        return dict.__or__(dict(dict.items(self)), o)

    def __ror__(self, o):
        _rec(self._tid, STAR)
        return dict.__ror__(dict(dict.items(self)), o)

    def __reversed__(self):
        _rec(self._tid, STAR)
        return dict.__reversed__(self)

    def __eq__(self, o):
        _rec(self._tid, STAR)
        return dict.__eq__(self, o)

    def __len__(self):
        return dict.__len__(self)
    __hash__ = None

    def __reduce__(self):
        return (dict, (dict(dict.items(self)),))

def _set_methods(base):
    ns = {'__slots__': ('_tid',)}

    def contains(self, k):
        _rec(self._tid, k)
        return base.__contains__(self, k)
    ns['__contains__'] = contains

    def mk(name):
        f = getattr(base, name)

        def m(self, *a):
            _rec(self._tid, STAR)
            return f(base(base.__iter__(self)), *a)
        return m
    for name in ('__or__', '__and__', '__sub__', '__xor__', '__ror__', '__rand__', '__rsub__', '__rxor__', 'union', 'intersection', 'difference', 'symmetric_difference', 'issubset', 'issuperset', 'isdisjoint', '__le__', '__lt__', '__ge__', '__gt__', '__eq__', '__ne__', 'copy'):
        if hasattr(base, name):
            ns[name] = mk(name)

    def it(self):
        _rec(self._tid, STAR)
        return base.__iter__(self)
    ns['__iter__'] = it
    ns['__hash__'] = base.__hash__ if base is frozenset else None
    ns['__reduce__'] = lambda self: (base, (list(base.__iter__(self)),))
    return ns
TSet = type('TSet', (set,), _set_methods(set))
TFrozen = type('TFrozen', (frozenset,), _set_methods(frozenset))

def wrap_value(v, tid):
    if type(v) is dict:
        w = TDict(v)
    elif type(v) is set:
        w = TSet(v)
    elif type(v) is frozenset:
        w = TFrozen(v)
    else:
        return v
    w._tid = tid
    return w
TIDS = {}

def instrument():
    global REG
    names = IT.module_names(os.environ.get('SQLGLOT_ROOT', '/sqlglot'))
    IT.import_all(names)
    reg, classes = IT.build_registry(names)
    REG.update(reg)
    nwrapped = 0
    for name, cls in classes:
        if issubclass(cls, enum.Enum):
            continue
        for k, v in list(cls.__dict__.items()):
            if k in IT.SKIP_CLASS_KEYS or (k.startswith('__') and k.endswith('__')):
                continue
            if isinstance(v, (type, types.ModuleType)) or callable(v) or hasattr(type(v), '__get__'):
                continue
            try:
                setattr(cls, k, Desc(name, k, wrap_value(v, f'{name}|{k}')))
                nwrapped += 1
            except Exception:
                pass
    byid = {}
    for n in names:
        m = sys.modules.get(n)
        if m is None:
            continue
        for k, v in list(vars(m).items()):
            if k.startswith('__') or type(v) not in (dict, set, frozenset) or 'CACHE' in k.upper():
                continue
            byid.setdefault(id(v), (v, []))[1].append((n, k))
    for _, (v, binds) in byid.items():
        tid = f'M|{binds[0][0]}|{binds[0][1]}'
        TIDS[tid] = [f'M|{a}|{b}' for a, b in binds]
        w = wrap_value(v, tid)
        for n, k in binds:
            setattr(sys.modules[n], k, w)
    import sqlglot.generator as G
    orig = G._build_dispatch

    def build_dispatch(cls):
        was = ON[0]
        ON[0] = False
        try:
            d = orig(cls)
        finally:
            ON[0] = was
        w = TDict(d)
        c = cls
        nm = REG.get(id(c))
        while nm is None and c is not object:
            c = c.__mro__[1]
            nm = REG.get(id(c))
        w._tid = f'D|{nm}'
        return w
    G._build_dispatch = build_dispatch
    G._DISPATCH_CACHE.clear()
    sys.stderr.write(f'[attrtrace] classes={len(classes)} wrapped={nwrapped} globals={len(byid)}\n')
    return (reg, classes)

def recv_name(oid):
    n = REG.get(oid)
    if n is not None:
        return n
    c = UNREG.get(oid)
    if c is None:
        return '?'
    for b in getattr(c, '__mro__', ())[1:]:
        n = REG.get(id(b))
        if n is not None:
            return n
    return '?'

def translate(raw):
    was = ON[0]
    ON[0] = False
    try:
        return _translate(list(raw))
    finally:
        ON[0] = was

def _translate(raw):
    out = set()
    for a, b in raw:
        if type(a) is Desc:
            out.add(('A', a.cn, a.a, recv_name(b)))
        else:
            out.add(('K', a, STAR if b == STAR else IT.kname(b, REG)))
    return out
ENT = {}
PER = [set() for _ in IDS]
BUCKET_CLASS = {}
BUCKET_FILE = {}
_state = {'last_class': None, 'collect': None}

def add_entries(entries, idx):
    s = PER[idx]
    for e in entries:
        j = ENT.get(e)
        if j is None:
            j = ENT[e] = len(ENT)
        s.add(j)

def pytest_configure(config):
    instrument()
    ON[0] = True

def pytest_collectstart(collector):
    if collector.__class__.__name__ == 'Module':
        CUR.clear()
        _state['collect'] = str(collector.path)

def pytest_collectreport(report):
    if _state['collect'] and report.nodeid.endswith('.py'):
        f = report.nodeid
        BUCKET_FILE.setdefault(f, set()).update(translate(CUR))
        CUR.clear()
        _state['collect'] = None
import pytest

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_setup(item):
    CUR.clear()
    yield
    cls = '::'.join(item.nodeid.split('::')[:2])
    ents = translate(CUR)
    if _state['last_class'] != cls:
        _state['last_class'] = cls
        BUCKET_CLASS.setdefault(cls, set()).update(ents)
    item._it_setup = ents
    CUR.clear()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    CUR.clear()
    yield
    item._it_call = translate(CUR)
    CUR.clear()

@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_teardown(item, nextitem):
    CUR.clear()
    yield
    ents = translate(CUR)
    CUR.clear()
    nid = item.nodeid.split('[')[0]
    idx = NUM.get(nid)
    if idx is None:
        return
    ents |= getattr(item, '_it_setup', set()) | getattr(item, '_it_call', set())
    add_entries(ents, idx)

def pytest_sessionfinish(session):
    ON[0] = False
    for i, t in enumerate(IDS):
        parts = t.split('::')
        cb = BUCKET_CLASS.get('::'.join(parts[:2]))
        if cb:
            add_entries(cb, i)
        fb = BUCKET_FILE.get(parts[0])
        if fb:
            add_entries(fb, i)
    os.makedirs(OUT, exist_ok=True)
    with gzip.open(os.path.join(OUT, 'reads.json.gz'), 'wt') as f:
        ents = [None] * len(ENT)
        for e, j in ENT.items():
            ents[j] = list(e)
        json.dump({'entries': ents, 'per': [sorted(p) for p in PER], 'tids': TIDS}, f)
    sys.stderr.write(f'[attrtrace] wrote {len(ENT)} entries\n')
import concurrent.futures as _cf

class _SyncExecutor:

    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kw):
        if initializer:
            initializer(*initargs)

    def submit(self, fn, *args, **kwargs):
        fut = _cf.Future()
        try:
            fut.set_result(fn(*args, **kwargs))
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
