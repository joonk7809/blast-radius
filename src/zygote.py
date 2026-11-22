import ast
import builtins
import gc
import importlib
import importlib.util
import io
import marshal
import os
import pkgutil
import sys
import types

WARM_OPENED = set()


def warm(src, ids, prewarm=True, optwarm=False):
    sys.path.insert(0, src)
    os.chdir(src)
    import sqlglot

    if os.environ.get("BR_WARMALL", "1") == "1":
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
    for mod in sorted({t.split("::")[0][:-3].replace("/", ".") for t in ids}):
        try:
            importlib.import_module(mod)
        except Exception:
            pass
    if not prewarm and not optwarm:
        return
    real_open = builtins.open

    def rec_open(file, *a, **k):
        try:
            WARM_OPENED.add(os.path.relpath(os.path.abspath(os.fspath(file)), src))
        except Exception:
            pass
        return real_open(file, *a, **k)

    builtins.open = rec_open
    io.open = rec_open
    try:
        for on, name, cname in ((optwarm, "tests.test_optimizer", "TestOptimizer"), (prewarm, "tests.test_executor", "TestExecutor")):
            try:
                if on:
                    klass = getattr(importlib.import_module(name), cname)
                    klass.setUpClass()
                    klass._prewarmed = True
            except Exception:
                pass
    finally:
        builtins.open = real_open
        io.open = real_open


def code_index(files):
    idx = {}
    if not files:
        return idx
    fn_type = types.FunctionType
    for o in gc.get_objects():
        if type(o) is fn_type and o.__code__.co_filename in files:
            c = o.__code__
            idx.setdefault((c.co_filename, c.co_qualname, c.co_firstlineno), []).append(o)
    return idx


def in_body(nodes, ln):
    for node in nodes:
        if getattr(node, "lineno", ln + 1) <= ln <= getattr(node, "end_lineno", -1):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.body[0].lineno <= ln:
                return True
            return in_body(ast.iter_child_nodes(node), ln)
    return False


def old_code(fn, old_text):
    pyc = importlib.util.cache_from_source(fn)
    try:
        with open(pyc, "rb") as fh:
            data = fh.read()
        st = os.stat(fn)
    except OSError:
        data = b""
    if len(data) > 16 and int.from_bytes(data[4:8], "little") == 0 and int.from_bytes(data[8:12], "little") == int(st.st_mtime) & 0xFFFFFFFF and int.from_bytes(data[12:16], "little") == len(old_text.encode("utf-8")) == st.st_size:
        return marshal.loads(data[16:])
    return compile(old_text.encode("utf-8", "surrogateescape"), fn, "exec")


def _pair(old, new, out):
    if old.co_name != new.co_name or old.co_freevars != new.co_freevars:
        return False
    oc = [c for c in old.co_consts if isinstance(c, types.CodeType)]
    nc = [c for c in new.co_consts if isinstance(c, types.CodeType)]
    if len(oc) != len(nc):
        return False
    out.append((old, new))
    return all(_pair(a, b, out) for a, b in zip(oc, nc))


def swap_plan(src, path, old_text, new_text, changed, warm_lines, tree):
    name = path[:-3].replace("/", ".")
    if name.endswith(".__init__"):
        name = name[:-9]
    if name not in sys.modules:
        return None
    if changed & warm_lines.get(path, set()):
        return None
    if not all(in_body(tree.body, ln) for ln in changed):
        return None
    fn = os.path.join(src, path)
    try:
        oldc = old_code(fn, old_text)
        newc = compile(new_text.encode("utf-8", "surrogateescape"), fn, "exec")
    except SyntaxError:
        return None
    pairs = []
    if not _pair(oldc, newc, pairs):
        return None
    return [((fn, o.co_qualname, o.co_firstlineno), n) for o, n in pairs[1:] if not (o.co_code == n.co_code and _key(o.co_consts) == _key(n.co_consts) and o.co_names == n.co_names)]


def _key(c):
    if isinstance(c, types.CodeType):
        return (c.co_code, _key(c.co_consts), c.co_names)
    if isinstance(c, (tuple, frozenset)):
        return (type(c).__name__, tuple(sorted(map(_key, c), key=repr)) if isinstance(c, frozenset) else tuple(map(_key, c)))
    return (type(c).__name__, repr(c))


def apply_swaps(plans, idx):
    n = 0
    for pairs in plans:
        for key, new in pairs:
            for f in idx.get(key, []):
                f.__code__ = new
                n += 1
    return n
