import hashlib
import io
import os
import pickle
import time

import ck

METHODS = ("scan", "aggregate", "join", "sort", "set_operation")


class Fallback(Exception):
    pass


class LazyReader:
    pass


class Lazy:
    def __init__(self, sig, name):
        self.sig, self.name = sig, name
        self.reader = LazyReader()
        self.range_reader = LazyReader()


def group_by_dep(node, context, owner, sigs):
    want = {sigs[d] for d in node.dependencies}
    out = {}
    for name, t in context.tables.items():
        c = [t.sig] if type(t) is Lazy else [x for x in dict.fromkeys(owner.get(id(t), ())) if x in want] or [None]
        for s in c:
            out.setdefault(s, {})[name] = t
    return out


class Recorder:
    def __init__(self, sigs, snapdir, q, cov_cb):
        self.sigs, self.snapdir, self.q, self.cov_cb = sigs, snapdir, q, cov_cb
        self.owner, self.steps = {}, {}

    def wrap(self, ex):
        for m in METHODS:
            fn = getattr(ex, m)
            setattr(ex, m, self._mk(fn))

    def _mk(self, fn):
        def w(step, context):
            s = self.sigs.get(step)
            if s is None:
                return fn(step, context)
            deps = group_by_dep(step, context, self.owner, self.sigs)
            if None in deps or not set(deps) <= {self.sigs[d] for d in step.dependencies}:
                raise SystemExit("unmapped input in query %d %s %s %s" % (self.q, type(step).__name__, sorted(map(str, deps)), sorted(self.sigs[d] for d in step.dependencies)))
            pre = {d: ck.tables_state(t) for d, t in deps.items()}
            xalias = any(ck.cross_alias(a, b) for x, a in enumerate(deps.values()) for b in list(deps.values())[x + 1:])
            self.cov_cb((self.q, s))
            t0 = time.process_time()
            out = fn(step, context)
            cost = time.process_time() - t0
            self.cov_cb(("frame", self.q))
            post = {d: ck.tables_state(t) for d, t in deps.items()}
            post_cursor = {d: {n: (vars(t.reader).get("row"), t.range_reader.range) for n, t in tabs.items()} for d, tabs in deps.items()}
            alias_of = sorted(d for d, t in deps.items() if ck.cross_alias(t, out.tables))
            alias_map = {}
            for on, ot in out.tables.items():
                for d, tabs in deps.items():
                    for dn, dt in tabs.items():
                        if dt is ot and on not in alias_map:
                            alias_map[on] = (d, dn)
            oalias = bool(alias_of)
            blob = b""
            if self.snapdir and not alias_of and not alias_map:
                blob = pickle.dumps(out.tables, protocol=5)
                with open(os.path.join(self.snapdir, "%d_%s.pkl" % (self.q, s)), "wb") as fh:
                    fh.write(blob)
            for t in out.tables.values():
                self.owner.setdefault(id(t), []).append(s)
            self.steps[s] = {"kind": type(step).__name__, "out": ck.tables_state(out.tables), "names": list(out.tables), "pre": pre, "post": post, "mut": {d: post[d] != pre[d] for d in deps}, "mutc": {d: post[d][0] != pre[d][0] for d in deps}, "xalias": xalias, "oalias": oalias, "alias_of": alias_of, "alias_map": alias_map, "post_cursor": post_cursor, "cost": cost, "bytes": len(blob), "ndeps": len(step.dependents)}
            return out
        return w


class Replayer:
    def __init__(self, rec, sigs, snapdir, q, touched, base_bad, T, stats):
        self.rec, self.sigs, self.snapdir, self.q = rec, sigs, snapdir, q
        self.touched, self.base_bad, self.T, self.stats = touched, base_bad, T, stats
        self.owner, self.eq, self.mat, self.virtual_done, self.ran, self.virtual_order = {}, {}, {}, set(), set(), {}
        self.dependents, self.aliased_by, self.base_touched = {}, {}, set()
        for node, s in sigs.items():
            self.dependents[s] = {sigs[d] for d in node.dependents}
        for s, r in rec["steps"].items():
            for d in r["alias_of"]:
                self.aliased_by.setdefault(d, set()).add(s)

    def wrap(self, ex):
        self.ex = ex
        for m in METHODS:
            setattr(ex, m, self._mk(getattr(ex, m)))

    def closure(self, s):
        out, todo = set(), [s]
        while todo:
            x = todo.pop()
            if x in out:
                continue
            out.add(x)
            todo.extend(self.rec["steps"][x]["alias_of"])
            todo.extend(self.aliased_by.get(x, ()))
        return out

    def _peek(self, s, name):
        m = self.mat.get(s)
        if m is not None:
            return m.get(name)
        am = self.rec["steps"][s]["alias_map"]
        if name in am:
            return self._peek(*am[name])
        return None

    def _load(self, s):
        r = self.mat.get(s)
        if r is not None:
            return r
        cl = self.closure(s)
        if any(self.eq.get(x) == -1 for x in cl):
            raise Fallback("stale")
        replay_cursor = []
        for x in cl:
            for y in self.dependents[x]:
                if y in self.virtual_done and self.rec["steps"][y]["mut"].get(x):
                    if x != s or self.rec["steps"][y]["mutc"].get(x):
                        raise Fallback("shared")
                    replay_cursor.append((self.virtual_order[y], y))
        rs = self.rec["steps"][s]
        am = rs["alias_map"]
        if am and len(am) == len(rs["names"]):
            r = {n: self._load(d)[dn] for n, (d, dn) in am.items()}
        elif am or rs["alias_of"]:
            raise Fallback("partialalias")
        else:
            t = time.process_time()
            with open(os.path.join(self.snapdir, "%d_%s.pkl" % (self.q, s)), "rb") as fh:
                r = pickle.load(fh)
            self.T["load"] += time.process_time() - t
        for _, y in sorted(replay_cursor):
            for n, (row, rng) in self.rec["steps"][y]["post_cursor"][s].items():
                if n not in r:
                    raise Fallback("cursorname")
                r[n].reader.row = row
                r[n].range_reader.range = rng
        self.mat[s] = r
        for x in r.values():
            self.owner.setdefault(id(x), []).append(s)
        return r

    def _hash(self, tables):
        t = time.process_time()
        r = ck.tables_state(tables)
        self.T["hash"] += time.process_time() - t
        return r

    def _mk(self, fn):
        def w(step, context):
            s = self.sigs.get(step)
            if s is None:
                return fn(step, context)
            r = self.rec["steps"][s]
            deps = group_by_dep(step, context, self.owner, self.sigs)
            if None in deps:
                raise Fallback("unmapped")
            dirty_base = not step.dependencies and isinstance(step.source, ck_exp().Expr) and (step.source.name or step.source.alias) in self.base_bad
            eqs = [self.eq.get(d, 2) for d in deps]
            if (self.q, s) not in self.touched and not dirty_base and not step.offset and all(e >= 1 for e in eqs):
                for d, tabs in deps.items():
                    if r["mut"].get(d):
                        cl = self.closure(d)
                        if any(type(t) is not Lazy for t in tabs.values()) or cl & set(self.mat):
                            if r["mutc"].get(d):
                                for x in cl:
                                    self.eq[x] = -1
                                continue
                            for n, t in tabs.items():
                                o = self._peek(t.sig, t.name) if type(t) is Lazy else t
                                if o is None:
                                    if cl & set(self.mat):
                                        for x in cl:
                                            self.eq[x] = -1
                                    break
                                row, rng = r["post_cursor"][d][n]
                                o.reader.row = row
                                o.range_reader.range = rng
                self.eq[s] = min(eqs, default=2)
                self.virtual_done.add(s)
                self.virtual_order[s] = len(self.virtual_order)
                self.stats["virtual"] += 1
                return self.ex.context({name: Lazy(s, name) for name in r["names"]})
            if any(e < 0 for e in eqs):
                raise Fallback("stale")
            if r["xalias"] and any(type(t) is Lazy for t in context.tables.values()) and any(type(t) is not Lazy for t in context.tables.values()):
                raise Fallback("xalias")
            if any(type(t) is Lazy for t in context.tables.values()):
                context = self.ex.context({name: self._load(t.sig)[t.name] if type(t) is Lazy else t for name, t in context.tables.items()})
                deps = group_by_dep(step, context, self.owner, self.sigs)
            self.stats["realsteps"] += 1
            self.ran.add(s)
            if not step.dependencies:
                self.stats["basescan"] = self.stats.get("basescan", 0) + 1
                self.base_touched.add(step.source.name or step.source.alias if isinstance(step.source, ck_exp().Expr) else None)
            t0 = time.process_time()
            try:
                out = fn(step, context)
            finally:
                self.T["real"] += time.process_time() - t0
            oc = self._hash(out.tables)
            self.eq[s] = 2 if oc == tuple(r["out"]) else 1 if oc[0] == r["out"][0] else 0
            for d, tabs in deps.items():
                pc = self._hash(tabs)
                want = r["post"].get(d)
                if want is None:
                    raise Fallback("dep")
                if pc == tuple(want):
                    continue
                for x in self.closure(d):
                    self.eq[x] = min(self.eq.get(x, 2), 1 if pc[0] == want[0] else 0)
            for t in out.tables.values():
                self.owner.setdefault(id(t), []).append(s)
            return out
        return w


def ck_exp():
    from sqlglot import exp
    return exp
