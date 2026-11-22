import enum
import functools
import hashlib
import itertools
import os
import pickle
import logging
import re
import sys
import time
import types

KINDS = (("ds", "tpc-ds", "test_execute_tpcds", "tpcds_tables"), ("h", "tpc-h", "test_execute_tpch", "tpch_tables"))
t_TypeVar = type(__import__("typing").TypeVar("T"))
SKIP_SLOTS = ("parent", "arg_key", "index", "_hash")
POSITION = ("line", "col", "start", "end")
DERIVED = ("_DISPATCH_CACHE",)


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


def _canon(v, out, seen, depth):
    t = type(v)
    if v is None or t in (bool, int, float, str, bytes, complex):
        out.append("%s:%r" % (t.__name__, v))
        return
    if depth > 40:
        raise Opaque()
    if isinstance(v, (type, types.ModuleType)):
        out.append("T:%s.%s" % (getattr(v, "__module__", ""), getattr(v, "__qualname__", v.__name__)))
        return
    if id(v) in seen:
        out.append("cycle")
        return
    seen.add(id(v))
    try:
        if t in (list, tuple):
            out.append("%s[%d" % (t.__name__, len(v)))
            for x in v:
                _canon(x, out, seen, depth + 1)
            out.append("]")
        elif t is dict:
            out.append("dict[%d" % len(v))
            for k, x in v.items():
                _canon(k, out, seen, depth + 1)
                _canon(x, out, seen, depth + 1)
            out.append("]")
        elif t in (set, frozenset):
            parts = []
            for x in v:
                o = []
                _canon(x, o, set(seen), depth + 1)
                parts.append("\x01".join(o))
            out.append("%s{%s}" % (t.__name__, "\x02".join(sorted(parts))))
        elif isinstance(v, enum.Enum):
            out.append("E:%s.%s.%s" % (t.__module__, t.__qualname__, v.name))
        elif t is types.FunctionType:
            out.append("F:%s.%s" % (v.__module__, v.__qualname__))
            _canon(code_key(v.__code__), out, seen, depth + 1)
            _canon(v.__defaults__, out, seen, depth + 1)
            _canon(v.__kwdefaults__, out, seen, depth + 1)
            _canon(tuple(c.cell_contents if _filled(c) else Opaque for c in v.__closure__ or ()), out, seen, depth + 1)
            _canon(dict(vars(v)), out, seen, depth + 1)
        elif t in (types.BuiltinFunctionType, types.WrapperDescriptorType, types.MethodDescriptorType):
            out.append("B:%s.%s" % (getattr(v, "__module__", None) or type(getattr(v, "__self__", None)).__name__, v.__qualname__))
        elif t is types.MethodType:
            out.append("M")
            _canon(v.__func__, out, seen, depth + 1)
            _canon(v.__self__, out, seen, depth + 1)
        elif t in (staticmethod, classmethod):
            out.append("S:" + t.__name__)
            _canon(v.__func__, out, seen, depth + 1)
        elif t is property:
            out.append("P")
            _canon((v.fget, v.fset, v.fdel), out, seen, depth + 1)
        elif t in (types.MemberDescriptorType, types.GetSetDescriptorType, types.ClassMethodDescriptorType):
            out.append("D:%s" % v.__qualname__)
        elif t in (types.GenericAlias, t_TypeVar) or isinstance(v, logging.Logger):
            out.append("%s:%r" % (t.__name__, v))
        elif t in (type({}.values()), type({}.keys())):
            _canon(list(v), out, seen, depth + 1)
        elif t is re.Pattern:
            out.append("R:%r:%d" % (v.pattern, v.flags))
        elif t is functools.partial:
            out.append("partial")
            _canon((v.func, v.args, v.keywords), out, seen, depth + 1)
        elif t.__module__.startswith("sqlglot") and (hasattr(v, "__dict__") or _slots(t)):
            out.append("I:%s.%s" % (t.__module__, t.__qualname__))
            for name in _slots(t):
                _canon(getattr(v, name, Opaque), out, seen, depth + 1)
            _canon(dict(getattr(v, "__dict__", {})), out, seen, depth + 1)
        else:
            r = repr(v)
            if " at 0x" in r or not t.__module__ or t.__module__.startswith("sqlglot"):
                raise Opaque()
            out.append("r:%s.%s:%s" % (t.__module__, t.__qualname__, r))
    finally:
        seen.discard(id(v))


def _filled(cell):
    try:
        cell.cell_contents
    except ValueError:
        return False
    return True


def code_key(c):
    return (c.co_code, tuple(code_key(x) if isinstance(x, types.CodeType) else x for x in c.co_consts), c.co_names, c.co_freevars)


def keysets(mods):
    return {(mname, qual): frozenset(k for k in d if type(k) is str) for mname, qual, d in owners(mods)}


def owners(mods):
    for mname, mod in list(mods.items()):
        if mod is None or not (mname == "sqlglot" or mname.startswith("sqlglot.")):
            continue
        d = getattr(mod, "__dict__", None)
        if d is None:
            continue
        yield mname, "", d
        stack = [v for v in list(d.values()) if isinstance(v, type) and v.__module__ == mname]
        done = set()
        while stack:
            k = stack.pop()
            if id(k) in done:
                continue
            done.add(id(k))
            kd = vars(k)
            yield mname, k.__qualname__, kd
            stack.extend(v for v in list(kd.values()) if isinstance(v, type) and v.__module__ == mname and v.__qualname__.startswith(k.__qualname__ + "."))


def _hash(v):
    o = []
    try:
        _canon(v, o, set(), 0)
    except (Opaque, RecursionError):
        return None
    return hashlib.sha256("\x00".join(o).encode("utf-8", "surrogatepass")).hexdigest()


def state(names, mods, skip=()):
    out = {}
    for mname, qual, d in owners(mods):
        if mname in skip:
            continue
        for k in [k for k in d if type(k) is str and k not in DERIVED and (k in names or k.endswith("_sql") and not k.startswith("_"))]:
            v = d[k]
            if type(v) is dict and v and all(isinstance(x, type) for x in v.values()):
                out[(mname, qual, k)] = frozenset((_hash(x), _hash(y)) for x, y in v.items() if y.__module__.startswith("sqlglot"))
            else:
                out[(mname, qual, k)] = _hash(v)
    return out


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
    mon = sys.monitoring
    tool = 4
    mon.use_tool_id(tool, "memo")
    state = {"on": 0, "t": 0.0, "cpu": 0.0}
    seen = set()

    def cb(code, *a):
        if state["on"] and code.co_filename.startswith(src):
            seen.add((os.path.relpath(code.co_filename, src), code.co_qualname, code.co_firstlineno))
            return mon.DISABLE

    passes = []
    anywhere = {}
    cur = [None]

    def lcb(code, line):
        if not code.co_filename.startswith(src):
            return mon.DISABLE
        rel = os.path.relpath(code.co_filename, src)
        if state["on"]:
            passes[-1].setdefault(cur[0][0], {}).setdefault(rel, {}).setdefault(line, set()).add(cur[0][1])
            return mon.DISABLE
        anywhere.setdefault(rel, set()).add(line)

    ev = mon.events
    for e in (ev.PY_START, ev.PY_RESUME, ev.PY_THROW):
        mon.register_callback(tool, e, cb)
    mon.register_callback(tool, ev.LINE, lcb)
    mon.set_events(tool, ev.LINE)
    k.setUpClass()

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
    run = {}
    done = []
    store = {}

    def lookup(d, expression, raw):
        t = time.process_time()
        store["x"] = {drop: digest(expression, raw, drop) for drop in itertools.chain.from_iterable(itertools.combinations(POSITION, n) for n in range(len(POSITION) + 1))}
        state["cpu"] += (time.process_time() - t) * 15 / 16
        return None

    hooks = Hooks(ex, lookup, enter, leave)
    hooks.install()
    def sweep(lined):
        if lined:
            passes.append({})
        mon.set_events(tool, ev.PY_START | ev.PY_RESUME | ev.PY_THROW | (ev.LINE if lined else 0))
        for kind, word, _, attr in KINDS:
            tables = getattr(k, attr)
            sqls = k.tpch_sqls if kind == "h" else k.tpcds_sqls
            for i, (meta, sql, _) in enumerate(sqls):
                if not meta.get("execute"):
                    continue
                cur[0] = (kind, "f:%d" % i)
                if lined:
                    mon.restart_events()
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
                if lined:
                    continue
                pre.setdefault(kind, {})["f:%d" % i] = time.process_time() - t0 - state["cpu"]
                run.setdefault(kind, {})["f:%d" % i] = state["cpu"]
                if "x" in store:
                    done.append((kind, "f:%d" % i, store["x"], blob))

    sweep(True)
    sweep(False)
    sweep(True)
    lines = {}
    for kind in pre:
        everyone = set(pre[kind])
        pa, pb = passes[0].get(kind, {}), passes[1].get(kind, {})
        for rel in set(pa) | set(pb):
            a, b = pa.get(rel, {}), pb.get(rel, {})
            lines.setdefault(kind, {})[rel] = {ln: everyone if a.get(ln) != b.get(ln) else a[ln] for ln in set(a) | set(b)}
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
    keyed = {}
    for kind, key, ds, blob in done:
        d = ds[drop]
        if d:
            memo.setdefault(kind, {})[d] = blob
            keyed.setdefault(kind, {})[key] = d
    with open(out_path, "wb") as fh:
        pickle.dump({"memo": memo, "pre": pre, "exec": sorted(seen), "drop": drop, "names": sorted(names | consts), "lines": lines, "anywhere": anywhere, "run": run, "keyed": keyed}, fh)


def build_state(src, memo_path, out_path):
    sys.path.insert(0, src)
    os.chdir(src)
    import importlib
    import pkgutil
    import tests.test_executor
    import sqlglot
    from sqlglot.dialects.dialect import Dialect, Dialects
    first = keysets(sys.modules)
    for m in pkgutil.walk_packages(sqlglot.__path__, "sqlglot."):
        try:
            importlib.import_module(m.name)
        except Exception:
            pass
    for d in Dialects:
        try:
            Dialect.get_or_raise(d.value)
        except Exception:
            pass
    with open(memo_path, "rb") as fh:
        names = set(pickle.load(fh)["names"])
    keys = keysets(sys.modules)
    lazy = {o: keys[o] - ks for o, ks in first.items() if o in keys}
    with open(out_path, "wb") as fh:
        pickle.dump({"entries": state(names, sys.modules), "keys": keys, "lazy": lazy}, fh)


if __name__ == "__main__":
    if sys.argv[1] == "state":
        build_state(*sys.argv[2:])
    else:
        build(sys.argv[1], sys.argv[2])
