import os
import pickle
import sys
import time

SRC, OUT = sys.argv[1], sys.argv[2]
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SRC)
os.chdir(SRC)
os.environ["SKIP_INTEGRATION"] = "0"
mon = sys.monitoring
tool = 3
mon.use_tool_id(tool, "ck")
cur = [("import", -1)]
cov = [{}]
lined = [True]


def lcb(code, line):
    f = code.co_filename
    if not f.startswith(SRC + "/sqlglot/"):
        return mon.DISABLE
    if cur[0] is not None:
        cov[-1].setdefault((os.path.relpath(f, SRC), line), set()).add(cur[0])
    return mon.DISABLE


mon.register_callback(tool, mon.events.LINE, lcb)
mon.set_events(tool, mon.events.LINE)
import importlib
import pkgutil
import ck
import ck2
import memo
import sqlglot
import tests.test_executor as te
import sqlglot.executor as sx
from sqlglot.dialects.dialect import Dialect, Dialects

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
import_cov = cov.pop()
mon.set_events(tool, 0)
cur[0] = None
lined[0] = False
k = te.TestExecutor
k.setUpClass()
def setcur(x):
    cur[0] = x
    if lined[0]:
        mon.restart_events()


snapdir = os.path.join(OUT, "snap2")
os.makedirs(snapdir, exist_ok=True)
real_opt, real_plan, real_px, real_et, real_es = sx.optimize, sx.Plan, sx.PythonExecutor, sx.ensure_tables, sx.ensure_schema
state = {}


def h_et(*a, **kw):
    setcur(("frame", state["q"]))
    return real_et(*a, **kw)


def h_es(schema, *a, **kw):
    state["raw_schema"] = (schema, a, sorted(kw.items()))
    return real_es(schema, *a, **kw)


def h_opt(expression, schema, **kw):
    state["pdig"] = memo.digest(expression, {})
    state["schema"] = memo._hash(state["raw_schema"])
    state["kw"] = repr(sorted(kw.items()))
    setcur(("opt", state["q"]))
    o = real_opt(expression, schema, **kw)
    setcur(("frame", state["q"]))
    state["o"] = ck.dumps(o)
    o = pickle.loads(state["o"])
    state["osql"] = o.sql(pretty=True)
    return o


def h_plan(expression):
    setcur(("plan", state["q"]))
    p = real_plan(expression)
    setcur(("frame", state["q"]))
    state["plan"] = p
    return p


class HPX:
    def __init__(self, tables=None, **kw):
        setcur(("frame", state["q"]))
        self.ex = real_px(tables=tables, **kw)

    def execute(self, plan):
        sigs = ck.step_sigs(plan)
        recd = ck2.Recorder(sigs, snapdir if state["record"] else None, state["q"], setcur)
        recd.wrap(self.ex)
        try:
            return self.ex.execute(plan)
        finally:
            state["recd"], state["sigs"] = recd, sigs


setup_cov = {}
for _ in range(2):
    cov.append({})
    lined[0] = True
    mon.set_events(tool, mon.events.LINE)
    setcur(("setup", -1))
    k.setUpClass()
    setcur(None)
    mon.set_events(tool, 0)
    for key in cov.pop():
        setup_cov[key] = {("setup", -1)}
sx.optimize, sx.Plan, sx.PythonExecutor, sx.ensure_tables, sx.ensure_schema = h_opt, h_plan, HPX, h_et, h_es
queries = {}


def sweep(lin, record):
    lined[0] = lin
    state["record"] = record
    if lin:
        cov.append({})
    mon.set_events(tool, mon.events.LINE if lin else 0)
    for i, (meta, sql, _) in enumerate(k.tpcds_sqls):
        if not meta.get("execute"):
            continue
        e = pickle.loads(pickle.dumps(te.parse_one(sql)))
        arg = {x.name: k.tpcds_tables[x.name] for x in te.find_tables(e)}
        state["q"] = i
        t0 = time.process_time()
        res = sx.execute(e, schema=te.TPCDS_SCHEMA, tables=arg)
        setcur(None)
        if record:
            qt = time.process_time() - t0
            pn = real_plan(real_opt(pickle.loads(pickle.dumps(te.parse_one(sql))), te.TPCDS_SCHEMA, leave_tables_isolated=True))
            pp = real_plan(pickle.loads(state["o"]))
            ns, ps = ck.step_sigs(pn), ck.step_sigs(pp)
            if sorted(ns.values()) != sorted(ps.values()) or ns[pn.root] != ps[pp.root] or ck.plan_ctes(pn) != ck.plan_ctes(pp) or sorted(ps.values()) != sorted(state["sigs"].values()):
                raise SystemExit("pinned AST plan differs on query %d" % i)
            recd = state["recd"]
            queries[i] = {"planblob": ck.dumps((pp, ps)), "root": ps[pp.root], "ctes": ck.plan_ctes(pp), "pdig": state["pdig"], "schema": state["schema"], "kw": state["kw"], "opt": state["o"], "osql": state["osql"], "sigs": sorted(state["sigs"].values()), "steps": recd.steps, "result": pickle.dumps(res, protocol=5), "qtime": qt, "tables": sorted(arg)}


rec = os.path.join(OUT, "rec.pkl")
pid = os.fork()
if pid == 0:
    sweep(False, True)
    with open(rec, "wb") as fh:
        pickle.dump(queries, fh, protocol=5)
    os._exit(0)
sweep(True, False)
sweep(True, False)
if os.waitpid(pid, 0)[1]:
    raise SystemExit("record sweep failed")
with open(rec, "rb") as fh:
    queries = pickle.load(fh)
os.remove(rec)
a, b = cov
lines = {}
for key in set(a) | set(b):
    va, vb = a.get(key), b.get(key)
    if va == vb:
        lines[key] = va
    elif all(x[0] == "opt" for x in (va or set()) | (vb or set())):
        lines[key] = "OPTALL"
    else:
        lines[key] = "ALL"
for key in import_cov:
    lines[key] = "IMPORT"
for key, v in setup_cov.items():
    if lines.get(key) in ("ALL", "OPTALL"):
        continue
    lines[key] = (lines.get(key) or set()) | v
mon.set_events(tool, 0)
mon.free_tool_id(tool)
base = {n: ck.content_state(t) for n, t in k.tpcds_tables.items()}
with open(os.path.join(OUT, "ck2.pkl"), "wb") as fh:
    pickle.dump({"queries": queries, "lines": lines, "base": base}, fh, protocol=5)
with open(os.path.join(OUT, "lines.pkl"), "wb") as fh:
    pickle.dump((lines, sorted(queries)), fh, protocol=5)
st = [r for q in queries.values() for r in q["steps"].values()]
print("queries", len(queries), "steps", len(st), "snapMB", sum(r["bytes"] for r in st) / 1e6, "ALL", sum(1 for v in lines.values() if v == "ALL"), "OPTALL", sum(1 for v in lines.values() if v == "OPTALL"), "IMPORT", sum(1 for v in lines.values() if v == "IMPORT"), "oalias", sum(r["oalias"] for r in st), "shared", sum(r["ndeps"] > 1 for r in st))
