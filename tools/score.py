import json, math, sys
from pathlib import Path


def score(stdout: bytes, tests, answers):
    dur = {t["number"]: math.floor(t["seconds"] * 1000 + 0.5) for t in tests}
    text = stdout.decode("utf-8")
    lines = [] if text == "" else text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    seen, missed, sim, per = set(), [], 0, {}
    for n, line in enumerate(lines, 1):
        v = json.loads(line)
        if not (isinstance(v, dict) and set(v) == {"commit", "workers"} and isinstance(v["commit"], str) and isinstance(v["workers"], list)):
            return {"reject": "wrong_shape", "line": n}
        c = v["commit"]
        if c not in answers:
            return {"reject": "unknown_commit", "line": n}
        if c in seen:
            return {"reject": "repeated_commit", "line": n}
        seen.add(c)
        ws = [w for w in v["workers"] if w]
        flat = [x for w in ws for x in w]
        if any(type(x) is not int for x in flat):
            return {"reject": "wrong_shape", "line": n}
        if any(x not in dur for x in flat):
            return {"reject": "unknown_test", "line": n}
        if len(set(flat)) != len(flat):
            return {"reject": "repeated_test", "line": n}
        if len(ws) > 8:
            return {"reject": "too_many_workers", "line": n}
        cost = max(sum(dur[x] for x in w) for w in ws) + 2000 * len(ws) if ws else 0
        miss = any(f not in set(flat) for f in answers[c]["failing"])
        per[c] = (cost, miss)
        sim += cost
        if miss:
            missed.append(c)
    if any(c not in seen for c in answers):
        return {"reject": "missing_commit"}
    sim += 300000 * len(missed)
    return {"simulated_ms": sim, "missed": sorted(missed), "per_commit": per}


if __name__ == "__main__":
    data, ans, out = map(Path, sys.argv[1:4])
    tests = json.loads((data / "tests.json").read_text())["tests"]
    answers = json.loads(ans.read_text())["commits"]
    r = score(out.read_bytes(), tests, answers)
    if "reject" in r:
        print("REJECTED", r); sys.exit(1)
    cpu = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    for c, (cost, miss) in sorted(r["per_commit"].items()):
        print(f"{c} {cost/1000:8.3f}{'  MISS' if miss else ''}")
    print(f"simulated {r['simulated_ms']/1000:.3f}s  misses {len(r['missed'])} {r['missed']}  cpu {cpu:.3f}s  total {r['simulated_ms']/1000+cpu:.3f}s")
