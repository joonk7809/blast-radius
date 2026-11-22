import gzip
import json
import sys

parts, out = sys.argv[1:-1], sys.argv[-1]
recs = {}
for p in parts:
    recs.update(json.load(gzip.open(p)))
tabs = {"mods": {}, "code": {}, "fs": {}}


def idx(kind, xs):
    t = tabs[kind]
    return sorted(t.setdefault(x, len(t)) for x in xs)


tests = {}
for tid, r in sorted(recs.items()):
    if r is not None:
        tests[tid] = [idx("mods", r["mods"]), idx("code", r["code"]), idx("fs", [x for x in r["fs"] if not x.startswith("tests/fixtures/")]), int(r["spawn"] or not r["ok"])]
doc = {k: sorted(v, key=v.get) for k, v in tabs.items()}
doc["tests"] = tests
with gzip.open(out, "wt", compresslevel=9) as fh:
    json.dump(doc, fh, separators=(",", ":"))
print(len(tests), {k: len(v) for k, v in tabs.items()}, sum(r[3] for r in tests.values()))
