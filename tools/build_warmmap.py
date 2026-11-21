import json, sys
import coverage
sys.path.insert(0, "/app")
cov = coverage.Coverage(source=["/sqlglot/sqlglot", "/sqlglot/tests"], data_file=None)
cov.start()
import selector, zygote
selector.preimport()
selector.install_futures()
tests = json.load(open("/data/tests.json"))["tests"]
zygote.warm("/sqlglot", [t["id"] for t in tests])
cov.stop()
data = cov.get_data()
out = {}
for f in data.measured_files():
    rel = f.replace("/sqlglot/", "", 1)
    out[rel] = sorted(data.lines(f) or [])
json.dump(out, open(sys.argv[1], "w"))
print(len(out), sum(len(v) for v in out.values()), sorted(zygote.WARM_OPENED)[:5], len(zygote.WARM_OPENED))
