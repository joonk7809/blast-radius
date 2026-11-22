import json
import os
import pickle
import sys
import time

SRC, STORE, PATCH = sys.argv[1], sys.argv[2], sys.argv[3]
MODE = sys.argv[4] if len(sys.argv) > 4 else "ck"
BUDGET = float(sys.argv[5]) if len(sys.argv) > 5 and sys.argv[5] != "-" else None
HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, HERE)
import ckhooks

PRISTINE = os.environ.get("CK_PRISTINE", "/sqlglot")
with open(PATCH, encoding="utf-8", errors="replace") as fh:
    S = ckhooks.Session(STORE, PRISTINE, fh.read(), BUDGET, MODE == "real")
sys.path.insert(0, SRC)
os.chdir(SRC)
os.environ["SKIP_INTEGRATION"] = "0"
import tests.test_executor as te
import sqlglot.executor as sx

T = {"setup": 0.0, "parse": 0.0, "cmp": 0.0}
k = te.TestExecutor
t0 = time.process_time()
setup_err = None
try:
    k.setUpClass()
except Exception as e:
    setup_err = repr(e)[:200]
T["setup"] = time.process_time() - t0
S.install(sx)
fails, modes, budget_hit = [], {}, False
if setup_err is None:
    fr = S.frames()
    if fr is not None:
        k.cache = fr
    inst = k("test_execute_tpcds")
    te._schema, te._tables = te.TPCDS_SCHEMA, k.tpcds_tables
    parsed = []
    for i, (meta, sql, _) in enumerate(k.tpcds_sqls):
        t = time.process_time()
        parsed.append(pickle.loads(pickle.dumps(te.parse_one(sql))))
        T["parse"] += time.process_time() - t
    order = S.order_hint() if MODE == "sentinel" else range(len(k.tpcds_sqls))
    order = list(order) + [i for i in range(len(k.tpcds_sqls)) if i not in set(order)]
    for i in order:
        meta = k.tpcds_sqls[i][0]
        if not meta.get("execute"):
            continue
        try:
            table = te.mp_execute(parsed[i], meta)
        except ckhooks.Budget:
            budget_hit = True
            break
        except Exception as ex_:
            fails.append(i + 1)
            modes[i + 1] = "error:" + repr(ex_)[:100]
            if MODE == "sentinel":
                break
            continue
        t = time.process_time()
        try:
            inst.subtestHelper(i, table, tpch=False)
        except Exception as ex_:
            fails.append(i + 1)
            modes[i + 1] = "mismatch:" + repr(ex_)[:100]
        T["cmp"] += time.process_time() - t
        if fails and MODE == "sentinel":
            break
T.update(S.T)
print(json.dumps({"patch": os.path.basename(PATCH), "mode": MODE, "setup_err": setup_err, "fail": setup_err is not None or bool(fails), "budget_hit": budget_hit, "spent": round(S.spent, 3), "fails": fails, "allq": S.allq, "imp": S.imp, "frame": len(S.frame), "plan_q": len(S.plan_q), "opt_q": len(S.opt_q), "touched": len(S.touched), "setup_hit": S.setup_hit, "T": {a: round(b, 3) for a, b in T.items()}, "stats": S.stats, "fb": S.fb[:6], "modes": dict(list(modes.items())[:3])}))
