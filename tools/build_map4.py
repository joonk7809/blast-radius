import json, gzip, subprocess, sys

cov, trace, ids_path, out = sys.argv[1:5]
subprocess.run([sys.executable, __file__.replace("build_map4", "build_map3"), cov, trace, ids_path, out], check=True)
ids = open(ids_path).read().split()
idx = {t: i for i, t in enumerate(ids)}
m = json.load(gzip.open(out, "rt"))
tr = json.load(open(trace))
m["stmt_of"] = {str(idx[t]): v for t, v in tr.get("smap", {}).items() if t in idx}
tracked = {k.split("|")[0] for t, k in [(u[0], ids[u[0]] + "|" + u[1]) for u in m["units"]] if "|t:" in k}
for t in tracked:
    m["stmt_of"].setdefault(str(idx[t]), {})
with gzip.open(out, "wt") as f:
    json.dump(m, f, separators=(",", ":"))
print(len(m["stmt_of"]), "tracked tests", file=sys.stderr)
