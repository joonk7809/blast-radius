import json, os, subprocess, sys

tests = json.load(open("/data/tests.json"))["tests"]
mods = sorted({t["id"].split("::")[0][:-3].replace("/", ".") for t in tests})
probe = r'''
import importlib, json, sys
import coverage
sys.path.insert(0, "/app")
sys.path.insert(0, "/sqlglot")
import selector
selector.preimport()
selector.install_futures()
cov = coverage.Coverage(source=["/sqlglot/sqlglot", "/sqlglot/tests"], data_file=None)
cov.start()
try:
    importlib.import_module(sys.argv[1])
except BaseException:
    pass
cov.stop()
d = cov.get_data()
json.dump({f.replace("/sqlglot/", "", 1): sorted(d.lines(f) or []) for f in d.measured_files()}, sys.stdout)
'''
out = {}
for i, m in enumerate(mods):
    r = subprocess.run([sys.executable, "-c", probe, m], capture_output=True, text=True, cwd="/sqlglot")
    for f, lines in json.loads(r.stdout).items():
        fm = out.setdefault(f, {})
        for ln in lines:
            fm[ln] = fm.get(ln, 0) | (1 << i)
    print(i, m, len(r.stdout), file=sys.stderr)
json.dump({"modules": mods, "files": out}, open(sys.argv[1], "w"), separators=(",", ":"))
