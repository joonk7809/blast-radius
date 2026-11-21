import concurrent.futures as cf
import json
import os
import pickle
import sys
import unittest
os.environ['SKIP_INTEGRATION'] = '0'
sys.path.insert(0, os.getcwd())
sel = json.load(open(sys.argv[1]))

class LazyFuture:

    def __init__(self, fn, args, kwargs):
        self.fn, self.args, self.kwargs = (fn, args, kwargs)
        self.state = None

    def _force(self):
        if getattr(self, 'skip_outer', False) and (not ustate['stack']) and (self.state is None):
            self.state = (True, None)
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
        k = ustate['fut']
        ustate['fut'] += 1
        f = LazyFuture(fn, args, kwargs)
        if ustate['allowed'] is not None and 'f:%d' % k not in ustate['allowed']:
            f.skip_outer = True
        return f

    def map(self, fn, *iterables, **kw):
        return map(fn, *iterables)

    def shutdown(self, wait=True, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False
cf.ProcessPoolExecutor = SyncExecutor
cf.wait = lambda fs, timeout=None, return_when=None: cf._base.DoneAndNotDoneFutures(set(fs), set())
cf.as_completed = lambda fs, timeout=None: iter(list(fs))
ustate = {'tid': None, 'allowed': None, 'stack': [], 'seen': {}, 'fut': 0}
closed_sel = {}
for tid, keys in sel.items():
    if keys is None:
        closed_sel[tid] = None
    else:
        closed = set()
        for k in keys:
            parts = k.split('>')
            for i in range(1, len(parts) + 1):
                closed.add('>'.join(parts[:i]))
        closed_sel[tid] = closed
orig_subtest = unittest.TestCase.subTest

class SkipBody(Exception):
    pass

class UnitSub:

    def __init__(self, case, msg, params):
        base = repr((None if msg is unittest.case._subtest_msg_sentinel else msg, sorted(params.items())))
        fullk = '>'.join(ustate['stack'] + [base])
        n = ustate['seen'].get(fullk, 0)
        ustate['seen'][fullk] = n + 1
        self.key = 's:' + base + ('#%d' % n if n else '')
        self.path = '>'.join(ustate['stack'] + [self.key])
        self.skip = ustate['allowed'] is not None and self.path not in ustate['allowed']
        self.inner = None if self.skip else orig_subtest(case, msg, **params)

    def __enter__(self):
        ustate['stack'].append(self.key)
        if self.skip:
            sys.settrace(lambda *a: None)
            frame = sys._getframe(1)

            def tracer(fr, ev, arg):
                raise SkipBody()
            frame.f_trace = tracer
            return None
        return self.inner.__enter__()

    def __exit__(self, et, ev, tb):
        ustate['stack'].pop()
        if self.skip:
            sys.settrace(None)
            sys._getframe(1).f_trace = None
            return et is SkipBody
        return self.inner.__exit__(et, ev, tb)
unittest.TestCase.subTest = lambda self, msg=unittest.case._subtest_msg_sentinel, **params: UnitSub(self, msg, params)
cases, case_to_id = ([], {})
failed = {}
for tid in sel:
    path, cls, meth = tid.split('::')
    try:
        m = __import__(path[:-3].replace('/', '.'), fromlist=['_'])
        c = getattr(m, cls)(meth)
    except BaseException:
        failed[tid] = True
        continue
    case_to_id[id(c)] = tid
    cases.append(c)

class Result(unittest.TestResult):

    def startTest(self, test):
        super().startTest(test)
        tid = case_to_id.get(id(test))
        ustate.update(tid=tid, allowed=closed_sel.get(tid), stack=[], seen={}, fut=0)
        if tid:
            failed.setdefault(tid, False)

    def _fail(self, test):
        tid = case_to_id.get(id(test))
        if tid:
            failed[tid] = True
            return
        desc = str(test)
        for c in cases:
            if type(c).__module__ in desc:
                failed[case_to_id[id(c)]] = True

    def addError(self, test, err):
        self._fail(test)

    def addFailure(self, test, err):
        self._fail(test)

    def addSubTest(self, test, subtest, err):
        if err is not None:
            self._fail(test)

    def addUnexpectedSuccess(self, test):
        self._fail(test)
try:
    unittest.TestSuite(cases).run(Result())
except BaseException:
    pass
json.dump(failed, open(sys.argv[2], 'w'))
