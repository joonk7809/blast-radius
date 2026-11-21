import importlib, json, os, pkgutil, sys

src = sys.argv[1]
sys.path.insert(0, src)
os.chdir(src)
seen = set()
M = sys.monitoring
M.use_tool_id(3, "lam")


def start(code, off):
    if code.co_name == "<lambda>" and code.co_filename.startswith(src):
        seen.add((os.path.relpath(code.co_filename, src), code.co_firstlineno))
    return M.DISABLE


M.register_callback(3, M.events.PY_START, start)
M.set_events(3, M.events.PY_START)
import sqlglot

for m in pkgutil.walk_packages(sqlglot.__path__, "sqlglot."):
    try:
        importlib.import_module(m.name)
    except Exception:
        pass
from sqlglot.dialects.dialect import Dialect, Dialects

for d in Dialects:
    try:
        Dialect.get_or_raise(d.value)
    except Exception:
        pass
for dp, dns, fns in os.walk("tests"):
    for fn in fns:
        if fn.endswith(".py"):
            try:
                importlib.import_module(os.path.join(dp, fn)[:-3].replace("/", "."))
            except Exception:
                pass
M.set_events(3, 0)
json.dump(sorted(seen), sys.stdout)
