import gzip, json, sqlite3, sys
from coverage.numbits import numbits_to_nums

cov, trace, ids_path, out = sys.argv[1:5]
ids = open(ids_path).read().split()
idx = {t: i for i, t in enumerate(ids)}
db = sqlite3.connect(cov)
contexts = dict(db.execute("select id, context from context"))
files = dict(db.execute("select id, path from file"))
units, unit_idx = [], {}
test_units = {}


def unit_of(ctx):
    if ctx in unit_idx:
        return unit_idx[ctx]
    test, _, key = ctx.partition("|")
    t = idx.get(test)
    if t is None:
        unit_idx[ctx] = None
        return None
    u = len(units)
    units.append([t, key])
    unit_idx[ctx] = u
    if key:
        test_units.setdefault(t, set()).add(key)
    return u


per, imp = {}, {}
for fid, cid, bits in db.execute("select file_id, context_id, numbits from line_bits"):
    path = files[fid].replace("/sqlglot/", "", 1)
    ctx = contexts[cid]
    lines = numbits_to_nums(bits)
    if ctx == "":
        imp.setdefault(path, set()).update(lines)
        continue
    u = unit_of(ctx)
    if u is None:
        print("unknown ctx", ctx[:80], file=sys.stderr)
        continue
    d = per.setdefault(path, {})
    for ln in lines:
        d.setdefault(ln, set()).add(u)
sets, setidx, fout = [], {}, {}
for path in sorted(set(per) | set(imp)):
    lm = {}
    for ln, s in per.get(path, {}).items():
        key = tuple(sorted(s))
        if key not in setidx:
            setidx[key] = len(sets)
            sets.append(list(key))
        lm[ln] = setidx[key]
    fout[path] = {"lines": lm, "import": sorted(imp.get(path, ()))}
tr = json.load(open(trace))
fx = {}
for tid, fl in tr["opens"].items():
    for f in fl:
        fx.setdefault(f, set()).add(idx[tid])
data = {
    "tests": ids,
    "units": units,
    "nunits": {str(t): len(k) for t, k in test_units.items()},
    "sets": sets,
    "files": fout,
    "fixtures": {k: sorted(v) for k, v in fx.items()},
}
with gzip.open(out, "wt") as f:
    json.dump(data, f, separators=(",", ":"))
print(len(units), "units;", len(sets), "sets;", len(fout), "files", file=sys.stderr)
