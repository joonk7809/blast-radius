import ast
import os
import pickle
import time

import ck
import ck2
import memo
import selector
import zygote


class Budget(Exception):
    pass


def check_lines(patch_text, pristine):
    out, imp, files = set(), set(), set()
    for f in selector.parse_patch(patch_text):
        rel = f["old"]
        files.add(rel)
        files.add(f["path"])
        if not (rel.startswith("sqlglot/") and rel.endswith(".py")):
            continue
        if f["new_file"] or f["deleted"] or f["old"] != f["path"]:
            return None, {rel}, files
        with open(os.path.join(pristine, rel), encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
        stmts = [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]
        removed, anchors = selector.changed_old_lines(f["hunks"])
        _, inserts = selector._replaced_lines(f["hunks"])
        head = {ln for ln in inserts if selector.LEANHDR and ln - 1 not in removed and any(n.body[0].lineno == ln > n.lineno and not selector._isdoc(n.body[0]) for n in stmts if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)))}
        check = anchors - {ln - 1 for ln in head}
        for ln in removed:
            for a, b in selector._stmt_span(stmts, ln):
                check.update(range(a, b + 1))
        for ln in inserts:
            check |= selector._insert_lines(stmts, ln)
        for ln in removed:
            if not zygote.in_body(tree.body, ln):
                imp.add((rel, ln))
        for ln in inserts - head:
            if not (zygote.in_body(tree.body, ln - 1) and zygote.in_body(tree.body, ln)):
                imp.add((rel, ln))
        out.update((rel, ln) for ln in check)
    return out, imp, files


class Reach:
    def __init__(self, lines, queries, patch_text, pristine):
        chk, imp, self.files = check_lines(patch_text, pristine)
        self.touched, self.frame, self.plan_q, self.opt_q = set(), set(), set(), set()
        self.setup_hit, allq = False, chk is None
        for key in chk or ():
            v = lines.get(key)
            if v is None:
                if key[0] == "sqlglot/executor/__init__.py":
                    self.frame.update(queries)
                continue
            if v == "ALL":
                allq = True
            elif v == "IMPORT":
                imp.add(key)
            elif v == "OPTALL":
                self.opt_q.update(queries)
            else:
                for x in v:
                    if x[0] == "setup":
                        self.setup_hit = True
                    elif x[0] == "frame":
                        self.frame.add(x[1])
                    elif x[0] == "plan":
                        self.plan_q.add(x[1])
                    elif x[0] == "opt":
                        self.opt_q.add(x[1])
                    else:
                        self.touched.add(x)
        self.allq, self.imp = allq, bool(imp)
        self.only_sqlglot = all(f.startswith("sqlglot/") for f in self.files)

    def hot(self):
        return {q for q, _ in self.touched} | self.plan_q | self.frame | self.opt_q


class Session(Reach):
    def __init__(self, store, pristine, patch_text, budget=None, force_native=False):
        with open(os.path.join(store, "ck2.pkl"), "rb") as fh:
            self.D = pickle.load(fh)
        self.store, self.budget = store, budget
        self.Q = self.D["queries"]
        self.by_pdig = {r["pdig"]: i for i, r in self.Q.items()}
        Reach.__init__(self, self.D["lines"], self.Q, patch_text, pristine)
        self.nogo = self.allq or self.imp or force_native
        self.T = {k: 0.0 for k in ("opt", "base", "plan", "replay", "real", "native", "load", "hash")}
        self.stats = {"virtual": 0, "realsteps": 0, "untouched": 0, "optskip": 0, "replayed": 0, "native": 0}
        self.fb = []
        self.st, self.sch, self.base = {}, {}, {}
        self.base_dirty = False
        self.spent = 0.0

    def order_hint(self, sentinels=(8, 5, 96)):
        hot = sorted(self.hot())
        return [q for q in sentinels if q in self.Q] + [q for q in hot if q not in sentinels]

    def _charge(self, t0):
        self.spent += time.process_time() - t0
        if self.budget is not None and self.spent > self.budget:
            raise Budget("checkpoint budget %.2f s spent" % self.spent)

    def install(self, sx):
        S = self
        real_opt, real_plan, real_px, real_es = sx.optimize, sx.Plan, sx.PythonExecutor, sx.ensure_schema
        Q = self.Q

        def h_es(schema, *a, **kw):
            key = (id(schema), a, tuple(sorted(kw.items())))
            h = S.sch.get(key)
            if h is None or h[0] is not schema:
                h = S.sch[key] = (schema, memo._hash((schema, a, sorted(kw.items()))))
            S.st["schema"] = h[1]
            return real_es(schema, *a, **kw)

        class Marker:
            def __init__(self, q):
                self.q, self.ast = q, None

            def sql(self, *a, **kw):
                if not a and kw == {"pretty": True}:
                    return Q[self.q]["osql"]
                return self.get().sql(*a, **kw)

            def get(self):
                if self.ast is None:
                    self.ast = pickle.loads(Q[self.q]["opt"])
                return self.ast

            def __getattr__(self, name):
                return getattr(self.get(), name)

        def h_opt(expression, schema, **kw):
            t = time.process_time()
            q = S.by_pdig.get(memo.digest(expression, {}))
            S.st["q"], S.st["optskip"], S.st["opt_same"] = q, False, False
            try:
                if q is not None and not S.nogo and q not in S.opt_q and q not in S.frame and repr(sorted(kw.items())) == Q[q]["kw"] and S.st.pop("schema", None) == Q[q]["schema"]:
                    S.st["optskip"] = True
                    S.stats["optskip"] += 1
                    return Marker(q)
                o = real_opt(expression, schema, **kw)
                S.st["opt_same"] = q is not None and memo.digest(o, {}) == memo.digest(pickle.loads(Q[q]["opt"]), {})
                return o
            finally:
                S.T["opt"] += time.process_time() - t

        class Pending:
            def __init__(self, expression):
                self.expression = expression

        class HPX:
            def __init__(self, tables=None, **kw):
                self.tables, self.kw = tables, kw

            def native(self, expression, q=None):
                S.base_dirty = True
                if q is None:
                    S.base.clear()
                else:
                    for n in Q[q]["tables"]:
                        S.base.pop(id(self.tables.find(sx.exp.to_table(n))), None)
                S.stats["native"] += 1
                t = time.process_time()
                try:
                    return real_px(tables=self.tables, **self.kw).execute(real_plan(expression))
                finally:
                    S.T["native"] += time.process_time() - t
                    S._charge(t)

            def execute(self, pending):
                q = S.st.get("q")
                expression = pending.expression
                marker = expression if type(expression) is Marker else None
                if S.nogo or q is None or self.kw or not (S.st.get("optskip") or S.st.get("opt_same")) or q in S.frame:
                    if q is not None and not S.nogo:
                        S.fb.append((q + 1, "pre"))
                    return self.native(marker.get() if marker else expression, q)
                r = Q[q]
                t = time.process_time()
                bad = set()
                if S.setup_hit or S.base_dirty or not S.only_sqlglot:
                    for n in r["tables"]:
                        tb = self.tables.find(sx.exp.to_table(n))
                        h = S.base.get(id(tb))
                        if h is None:
                            h = S.base[id(tb)] = ck.content_state(tb)
                        if h != S.D["base"][n]:
                            bad.add(n)
                S.T["base"] += time.process_time() - t
                if not bad and q not in S.plan_q and not any(x[0] == q for x in S.touched):
                    S.stats["untouched"] += 1
                    return pickle.loads(r["result"])
                t = time.process_time()
                if q not in S.plan_q and marker:
                    plan, sigs = pickle.loads(r["planblob"])
                else:
                    if marker:
                        expression = marker.get()
                    plan = real_plan(expression)
                    sigs = ck.step_sigs(plan)
                S.T["plan"] += time.process_time() - t
                if sorted(sigs.values()) != r["sigs"]:
                    S.fb.append((q + 1, "plan"))
                    return self.native(marker.get() if marker else expression, q)
                S.stats["replayed"] += 1
                t = time.process_time()
                ex = real_px(tables=self.tables)
                rp = ck2.Replayer(r, sigs, os.path.join(S.store, "snap2"), q, S.touched, bad, S.T, S.stats)
                rp.wrap(ex)
                try:
                    res = ex.execute(plan)
                except sx.ExecuteError as e:
                    S.T["replay"] += time.process_time() - t
                    if isinstance(e.__cause__, ck2.Fallback):
                        S.fb.append((q + 1, str(e.__cause__)))
                        return self.native(marker.get() if marker else expression, q)
                    raise
                S.T["replay"] += time.process_time() - t
                S._charge(t)
                if rp.base_touched:
                    S.base_dirty = True
                    for n in rp.base_touched:
                        if n is None:
                            S.base.clear()
                        else:
                            S.base.pop(id(self.tables.find(sx.exp.to_table(n))), None)
                return pickle.loads(r["result"]) if type(res) is ck2.Lazy else res

        sx.optimize, sx.Plan, sx.PythonExecutor, sx.ensure_schema = h_opt, Pending, HPX, h_es
        self.restore = lambda: setattr(sx, "optimize", real_opt) or setattr(sx, "Plan", real_plan) or setattr(sx, "PythonExecutor", real_px) or setattr(sx, "ensure_schema", real_es)
