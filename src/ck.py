import io
import hashlib
import pickle


def _dump_val(v, exp, out):
    t = type(v)
    if v is None or t in (bool, int, float, str):
        out.append("%s:%r" % (t.__name__, v))
    elif t in (list, tuple):
        out.append("%s[%d" % (t.__name__, len(v)))
        for x in v:
            _dump_val(x, exp, out)
        out.append("]")
    elif t is dict:
        out.append("dict[%d" % len(v))
        for a, b in v.items():
            _dump_val(a, exp, out)
            _dump_val(b, exp, out)
        out.append("]")
    elif isinstance(v, type):
        out.append("T:%s.%s" % (v.__module__, v.__qualname__))
    elif isinstance(v, exp.Expr):
        import memo
        memo.dump(v, out, exp)
    else:
        raise memo_opaque()


def memo_opaque():
    import memo
    return memo.Opaque()


SKIP_STEP = ("dependencies", "dependents")


def step_sigs(plan):
    from sqlglot import exp
    sigs = {}

    def sig(s):
        r = sigs.get(s)
        if r is None:
            out = ["S:%s.%s" % (type(s).__module__, type(s).__qualname__)]
            for k in sorted(vars(s)):
                if k in SKIP_STEP:
                    continue
                out.append("." + k)
                _dump_val(vars(s)[k], exp, out)
            out.append("deps:" + ",".join(sorted(sig(d) for d in s.dependencies)))
            out.append("ndependents:%d" % len(s.dependents))
            r = sigs[s] = hashlib.sha256("\x00".join(out).encode("utf-8", "surrogatepass")).hexdigest()[:24]
        return r

    for s in plan.dag:
        sig(s)
    for s in plan.dag:
        for d in s.dependents:
            if d not in sigs:
                raise memo_opaque()
    up = {}

    def key(s):
        r = up.get(s)
        if r is None:
            r = up[s] = hashlib.sha256((sigs[s] + "|" + ",".join(sorted(key(d) for d in s.dependents))).encode()).hexdigest()[:24]
        return r

    seen = {}
    out = {}
    for s in sorted(plan.dag, key=lambda s: (key(s), sigs[s])):
        k = key(s)
        n = seen[k] = seen.get(k, -1) + 1
        out[s] = k if not n else "%s#%d" % (k, n)
    return out


def _fast(obj):
    buf = io.BytesIO()
    p = pickle.Pickler(buf, protocol=5)
    p.fast = True
    p.dump(obj)
    return buf.getvalue()


def tables_state(tables):
    ids = {}
    shape, cursor = [], []
    h = hashlib.sha256()
    for name, t in tables.items():
        shape.append((name, type(t).__module__, type(t).__qualname__, ids.setdefault(id(t), len(ids)), ids.setdefault(id(t.rows), len(ids)), t.columns, t.column_range, sorted(vars(t)), type(t.reader).__qualname__, t.reader.columns, sorted(vars(t.reader)), type(t.range_reader).__qualname__, t.range_reader.table is t, sorted(vars(t.range_reader))))
        cursor.append((vars(t.reader).get("row"), t.range_reader.range))
        h.update(_fast(t.rows))
    h.update(_fast(shape))
    return h.hexdigest(), hashlib.sha256(_fast(cursor)).hexdigest()


def content_state(t):
    buf = io.BytesIO()
    p = pickle.Pickler(buf, protocol=5)
    p.fast = True
    p.dump((t.columns, t.column_range, t.rows))
    return hashlib.sha256(buf.getvalue()).hexdigest()


def cross_alias(a, b):
    ia = {id(x) for t in a.values() for x in (t, t.rows)}
    return any(id(x) in ia for t in b.values() for x in (t, t.rows))
