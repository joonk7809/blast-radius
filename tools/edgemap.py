import gc, glob, importlib, json, os, pkgutil, sys, types

SRC = sys.argv[1]
sys.path.insert(0, SRC)
os.chdir(SRC)
os.environ["SKIP_INTEGRATION"] = "0"
import builtins

IMP = set()
_imp = builtins.__import__


def _hook(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _imp(name, globals, locals, fromlist, level)
    try:
        full = importlib.util.resolve_name("." * level + name, (globals or {}).get("__package__") or "") if level else name
    except Exception:
        full = name
    _record(full, fromlist)
    return mod


def _record(full, fromlist):
    parts = full.split(".")
    tgts = {".".join(parts[: i + 1]) for i in range(len(parts))}
    tgts.update(full + "." + x for x in fromlist or () if isinstance(x, str) and full + "." + x in sys.modules)
    f = sys._getframe(2)
    while f is not None:
        if f.f_code.co_name == "<module>":
            src = f.f_globals.get("__name__")
            if isinstance(src, str):
                IMP.update((src, t) for t in tgts if t != src)
        f = f.f_back


_imod = importlib.import_module


def _hook2(name, package=None):
    mod = _imod(name, package)
    _record(mod.__name__, ())
    return mod


builtins.__import__ = _hook
importlib.import_module = _hook2
import importlib.util
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
for f in sorted(glob.glob("tests/**/*.py", recursive=True)):
    try:
        importlib.import_module(f[:-3].replace("/", ".").removesuffix(".__init__"))
    except Exception:
        pass
try:
    import tests.test_executor as te

    te.TestExecutor.setUpClass()
except Exception:
    pass
ours = {n: m for n, m in sys.modules.items() if m is not None and (n == "sqlglot" or n.startswith(("sqlglot.", "tests")))}
mods = {id(m): n for n, m in ours.items()}
FT = (type, types.FunctionType)
STOP = (str, int, float, bytes, bool, type(None), types.CodeType)


def own(o):
    if id(o) in mods:
        return mods[id(o)]
    if isinstance(o, FT):
        mm = getattr(o, "__module__", None)
        return mm if mm in ours else ""
    return None


def healed(n, w, path):
    if len(path) == 1:
        if "__getattr__" in vars(ours[n]):
            return True
        if isinstance(ours.get(w), types.ModuleType) and w == n + "." + path[0] and ours[w] is vars(ours[n]).get(path[0]):
            return True
    return n == "sqlglot.dialects.dialect" and path[:3] == ["_Dialect", "dict", "_classes"]


rev = {}
for n, m in ours.items():
    seen = {id(m)}
    stack = [(m.__dict__, [])]
    while stack:
        o, path = stack.pop()
        items = [(k if isinstance(k, str) else "", v) for k, v in list(o.items())] if isinstance(o, dict) else [(type(r).__name__, r) for r in gc.get_referents(o)]
        for lab, r in items:
            if isinstance(r, STOP) or id(r) in seen:
                continue
            seen.add(id(r))
            if isinstance(r, types.ModuleType) and id(r) not in mods:
                continue
            w = own(r)
            if w == "":
                continue
            if w is not None and w != n:
                if not healed(n, w, path + [lab]):
                    rev.setdefault(w, set()).add(n)
                continue
            stack.append((r, path + [lab]))
builtins.__import__ = _imp
importlib.import_module = _imod
for src, t in IMP:
    if src in ours and t in ours:
        rev.setdefault(t, set()).add(src)
json.dump({"nodes": sorted(ours), "rev": {k: sorted(v) for k, v in sorted(rev.items())}}, open(sys.argv[2], "w"))
