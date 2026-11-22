import enum
import hashlib
import itertools
import os
import pickle
import sys
import time
import types

KINDS = (("ds", "tpc-ds", "test_execute_tpcds", "tpcds_tables"), ("h", "tpc-h", "test_execute_tpch", "tpch_tables"))
SKIP_SLOTS = ("parent", "arg_key", "index", "_hash")
POSITION = ("line", "col", "start", "end")


class Opaque(Exception):
    pass


def _slots(cls):
    out = []
    for k in cls.__mro__:
        s = vars(k).get("__slots__", ())
        out.extend((s,) if isinstance(s, str) else s)
    return out


def dump(obj, out, exp, drop=()):
    t = type(obj)
    if obj is None or t in (bool, int, float, str, bytes):
        out.append("%s:%r" % (t.__name__, obj))
    elif t in (list, tuple):
        out.append("%s[%d" % (t.__name__, len(obj)))
        for v in obj:
            dump(v, out, exp, drop)
        out.append("]")
    elif t is dict:
        out.append("dict[%d" % len(obj))
        for k, v in obj.items():
            dump(k, out, exp, drop)
            dump(v, out, exp, drop)
        out.append("]")
    elif isinstance(obj, enum.Enum):
        out.append("enum:%s.%s:%s" % (t.__module__, t.__qualname__, obj.name))
    elif isinstance(obj, exp.Expr):
        out.append("e:%s.%s:%s" % (t.__module__, t.__qualname__, obj._hash is not None))
        for name in _slots(t):
            if name in SKIP_SLOTS:
                continue
            out.append("." + name)
            v = getattr(obj, name, Opaque)
            if name == "_meta" and drop and type(v) is dict:
                v = {k: x for k, x in v.items() if k not in drop} or None
            if v is Opaque:
                out.append("unset")
            else:
                dump(v, out, exp, drop)
        d = getattr(obj, "__dict__", None)
        if d:
            out.append(".__dict__")
            dump(d, out, exp, drop)
        args = getattr(obj, "args", None)
        if type(args) is dict:
            for k, v in args.items():
                for i, c in enumerate(v if type(v) is list else (v,)):
                    if isinstance(c, exp.Expr) and (c.parent is not obj or c.arg_key != k or c.index != (i if type(v) is list else None)):
                        raise Opaque()
    else:
        raise Opaque()


def tables_key(tables):
    out = []
    for k, v in tables.items():
        if type(k) is not str or type(v).__name__ != "Table" or type(v).__module__ != "sqlglot.executor.table" or set(vars(v)) != {"columns", "column_range", "reader", "rows", "range_reader"} or v.column_range is not None:
            raise Opaque()
        rows = v.rows
        out.append((k, tuple(v.columns), len(rows), repr(rows[:1]), repr(rows[-1:])))
    return repr(sorted(out))


def digest(expression, tables, drop=()):
    from sqlglot import exp
    out = []
    try:
        dump(expression, out, exp, drop)
        out.append(tables_key(tables))
    except (Opaque, RecursionError):
        return None
    return hashlib.sha256("\x00".join(out).encode("utf-8", "surrogatepass")).hexdigest()


class Hooks:
    def __init__(self, ex, lookup, on_enter=None, on_exit=None, drop=()):
        self.ex, self.lookup, self.drop = ex, lookup, drop
        self.on_enter, self.on_exit = on_enter, on_exit
        self.real = (ex.ensure_tables, ex.Plan, ex.PythonExecutor)
        self.tables = None
        hooks = self

        def ensure_tables(d, *a, **k):
            hooks.tables = d if not a and k in ({}, {"dialect": None}) else None
            return hooks.phase(hooks.real[0], d, *a, **k)

        class Pending:
            def __init__(self, expression):
                self.expression = expression

        class Executor:
            def __init__(self, tables=None, **kw):
                self.tables, self.kw = tables, kw

            def execute(self, pending):
                return hooks.run(pending.expression, self.tables, self.kw)

        self.fns = (ensure_tables, Pending, Executor)

    def phase(self, fn, *a, **k):
        if self.on_enter:
            self.on_enter()
        try:
            return fn(*a, **k)
        finally:
            if self.on_exit:
                self.on_exit()

    def run(self, expression, tables_, kw):
        raw, self.tables = self.tables, None
        d = digest(expression, raw, self.drop) if type(raw) is dict and not kw else None
        hit = self.lookup(d, expression, raw)
        if hit is not None:
            return pickle.loads(hit)

        def real():
            return self.real[2](tables=tables_, **kw).execute(self.real[1](expression))

        return self.phase(real)

    def install(self):
        self.ex.ensure_tables, self.ex.Plan, self.ex.PythonExecutor = self.fns

    def remove(self):
        self.ex.ensure_tables, self.ex.Plan, self.ex.PythonExecutor = self.real


def build(src, out_path):
    sys.path.insert(0, src)
    os.chdir(src)
    os.environ["SKIP_INTEGRATION"] = "0"
    import tests.test_executor as te
    import sqlglot.executor as ex
    k = te.TestExecutor
    k.setUpClass()
    mon = sys.monitoring
    tool = 4
    mon.use_tool_id(tool, "memo")
    state = {"on": 0, "t": 0.0, "cpu": 0.0}
    seen = set()

    def cb(code, *a):
        if state["on"] and code.co_filename.startswith(src):
            seen.add((os.path.relpath(code.co_filename, src), code.co_qualname, code.co_firstlineno))
            return mon.DISABLE

    ev = mon.events
    for e in (ev.PY_START, ev.PY_RESUME, ev.PY_THROW):
        mon.register_callback(tool, e, cb)
    mon.set_events(tool, ev.PY_START | ev.PY_RESUME | ev.PY_THROW)

    def enter():
        if not state["on"]:
            state["t"] = time.process_time()
        state["on"] += 1

    def leave():
        state["on"] -= 1
        if not state["on"]:
            state["cpu"] += time.process_time() - state["t"]

    memo = {}
    pre = {}
    done = []
    store = {}

    def lookup(d, expression, raw):
        t = time.process_time()
        store["x"] = {drop: digest(expression, raw, drop) for drop in itertools.chain.from_iterable(itertools.combinations(POSITION, n) for n in range(len(POSITION) + 1))}
        state["cpu"] += (time.process_time() - t) * 15 / 16
        return None

    hooks = Hooks(ex, lookup, enter, leave)
    hooks.install()
    for kind, word, _, attr in KINDS:
        tables = getattr(k, attr)
        sqls = k.tpch_sqls if kind == "h" else k.tpcds_sqls
        for i, (meta, sql, _) in enumerate(sqls):
            if not meta.get("execute"):
                continue
            t0 = time.process_time()
            state["cpu"] = 0.0
            store.clear()
            try:
                expression = pickle.loads(pickle.dumps(te.parse_one(sql)))
                arg = {t.name: tables[t.name] for t in te.find_tables(expression)}
                result = te.execute(expression, schema=te.TPCH_SCHEMA if kind == "h" else te.TPCDS_SCHEMA, tables=arg)
                blob = pickle.dumps(result)
                enter()
                try:
                    pickle.loads(blob)
                finally:
                    leave()
            except Exception:
                continue
            pre.setdefault(kind, {})["f:%d" % i] = time.process_time() - t0 - state["cpu"]
            if "x" in store:
                done.append((kind, store["x"], blob))
    hooks.remove()
    mon.set_events(tool, 0)
    mon.free_tool_id(tool)
    names, consts = set(), set()
    for rel in {r for r, _, _ in seen}:
        with open(os.path.join(src, rel), encoding="utf-8") as fh:
            stack = [compile(fh.read(), os.path.join(src, rel), "exec")]
        while stack:
            c = stack.pop()
            stack.extend(x for x in c.co_consts if isinstance(x, types.CodeType))
            if (rel, c.co_qualname, c.co_firstlineno) in seen:
                names.update(c.co_names)
                consts.update(x for x in c.co_consts if isinstance(x, str))
    drop = () if "POSITION_META_KEYS" in names else tuple(k for k in POSITION if k not in consts)
    for kind, ds, blob in done:
        d = ds[drop]
        if d:
            memo.setdefault(kind, {})[d] = blob
    with open(out_path, "wb") as fh:
        pickle.dump({"memo": memo, "pre": pre, "exec": sorted(seen), "drop": drop}, fh)


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2])
