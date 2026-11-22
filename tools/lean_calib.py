import json
import os
import subprocess
import sys
import tempfile

APP, SETS = sys.argv[1], sys.argv[2:]
TPCDS = "tests/test_executor.py::TestExecutor::test_execute_tpcds"
PY = os.environ.get("BR_PY", "/home/user/venv/bin/python")
SRC = os.environ.get("BR_SRC", "/home/user/sq")
MODES = ["all", "K0", "K2", "K4", "K8", "K0+sib", "K2+sib", "K4+sib", "K8+sib"]


def run(data):
    with tempfile.TemporaryDirectory() as tmp:
        env = {"PATH": "/usr/bin:/bin", "HOME": tmp, "SKIP_INTEGRATION": "0", "PYTHONDONTWRITEBYTECODE": "1", "BR_SRC": SRC, "BR_DATA": data, "BR_TMP": tmp, "BR_LEANCAL": "1", "BR_CANARY": "all"}
        err = subprocess.run([PY, os.path.join(APP, "selector.py")], cwd="/", env=env, capture_output=True, text=True).stderr
    out = {}
    for line in err.splitlines():
        parts = line.split(" ", 2)
        if len(parts) == 3 and parts[1] == "leancal":
            out[parts[0]] = json.loads(parts[2])
    return out


def verdicts(r):
    full = set() if r["full"] in (None, "-") else {int(x) for x in r["full"].split(",")}
    v = {"all": bool(full) or r["status"] != "P"}
    for k in (0, 2, 4, 8):
        hit = bool(full & set(r["picks"][str(k)]))
        v["K%d" % k] = hit
        v["K%d+sib" % k] = hit or bool(r["other"])
    return v


rows = []
for data in SETS:
    tests = json.load(open(os.path.join(data, "tests.json")))["tests"]
    tp = next(t["number"] for t in tests if t["id"] == TPCDS)
    answers = json.load(open(os.path.join(data, "answers.json")))["commits"]
    res = run(data)
    fails = [c for c, a in answers.items() if tp in a["failing"]]
    stat = {m: [0, 0, 0] for m in MODES}
    for cid, r in sorted(res.items()):
        bad = tp in answers[cid]["failing"]
        v = verdicts(r)
        for m in MODES:
            stat[m][0] += bad and not v[m]
            stat[m][1] += not bad and v[m]
        print(os.path.basename(data.rstrip("/")), cid, "tpcds_fails" if bad else "tpcds_passes", " ".join("%s=%s" % (m, "D" if v[m] else "-") for m in MODES), "cpu=%s" % r["cpu"], flush=True)
    gated_bad = sum(1 for c in res if tp in answers[c]["failing"])
    rows.append((os.path.basename(data.rstrip("/")), len(answers), len(res), gated_bad, len(fails), stat))
print()
print("%-8s %5s %5s %9s  " % ("set", "n", "gated", "gfail/all") + "  ".join("%-12s" % m for m in MODES))
for name, n, g, gb, fb, stat in rows:
    print("%-8s %5d %5d %4d/%-4d  " % (name, n, g, gb, fb) + "  ".join("%-12s" % ("%d/%d e=%.0f%%" % (stat[m][0], gb, 100.0 * stat[m][0] / gb if gb else 0)) for m in MODES))
print("cell = escapes/gated tpcds failures, e = escape rate; false alarms per mode:", {m: sum(r[5][m][1] for r in rows) for m in MODES})
