import gzip, json, sqlite3, sys
from coverage.numbits import numbits_to_nums

cov, trace, ids_path, out = sys.argv[1:5]
ids = open(ids_path).read().split()
ctx2idx = {}
for i, tid in enumerate(ids):
    path, cls, meth = tid.split("::")
    mod = path[:-3].replace("/", ".")
    ctx2idx[f"{mod}.{cls}.{meth}"] = i
db = sqlite3.connect(cov)
contexts = dict(db.execute("select id, context from context"))
files = dict(db.execute("select id, path from file"))
per = {}  # file -> line -> set(test)
imp = {}
unknown = set()
for fid, cid, bits in db.execute("select file_id, context_id, numbits from line_bits"):
    path = files[fid].replace("/sqlglot/", "", 1)
    ctx = contexts[cid]
    lines = numbits_to_nums(bits)
    if ctx == "":
        imp.setdefault(path, set()).update(lines)
        continue
    t = ctx2idx.get(ctx)
    if t is None:
        unknown.add(ctx); continue
    d = per.setdefault(path, {})
    for ln in lines:
        d.setdefault(ln, set()).add(t)
print("unknown contexts", len(unknown), list(unknown)[:5], file=sys.stderr)
sets, setidx = [], {}
fout = {}
for path in sorted(set(per) | set(imp)):
    lm = {}
    for ln, s in per.get(path, {}).items():
        key = tuple(sorted(s))
        if key not in setidx:
            setidx[key] = len(sets); sets.append(list(key))
        lm[ln] = setidx[key]
    fout[path] = {"lines": lm, "import": sorted(imp.get(path, ()))}
tr = json.load(open(trace))
fx = {}
for tid, fl in tr["opens"].items():
    for f in fl:
        fx.setdefault(f, set()).add(ids.index(tid))
dur = {ids.index(k): round(v[0], 3) for k, v in tr["dur"].items() if k in ids}
data = {"tests": ids, "sets": sets, "files": fout, "fixtures": {k: sorted(v) for k, v in fx.items()}, "dur": [dur.get(i, 0) for i in range(len(ids))]}
with gzip.open(out, "wt") as f:
    json.dump(data, f, separators=(",", ":"))
print(len(sets), "sets;", len(fout), "files", file=sys.stderr)
