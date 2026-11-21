import ast
import builtins
import gc
import importlib
import io
import os
import pkgutil
import sys
import types

WARM_OPENED = set()


def warm(src, ids, prewarm=True):
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
    if not prewarm:
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
        import tests.test_executor as te

        te.TestExecutor.setUpClass()
        te.TestExecutor._prewarmed = True
    except Exception:
        pass
    finally:
        builtins.open = real_open
        io.open = real_open


def code_index():
    idx = {}
    for o in gc.get_objects():
        if isinstance(o, types.FunctionType):
            c = o.__code__
            idx.setdefault((c.co_filename, c.co_qualname, c.co_firstlineno), []).append(o)
    return idx


def body_spans(tree):
    spans = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            spans.append((node.body[0].lineno, node.end_lineno))
    return spans


def _pair(old, new, out):
    if old.co_name != new.co_name or old.co_freevars != new.co_freevars:
        return False
    oc = [c for c in old.co_consts if isinstance(c, types.CodeType)]
    nc = [c for c in new.co_consts if isinstance(c, types.CodeType)]
    if len(oc) != len(nc):
        return False
    out.append((old, new))
    return all(_pair(a, b, out) for a, b in zip(oc, nc))


def swap_plan(src, path, old_text, new_text, changed, warm_lines):
    name = path[:-3].replace("/", ".")
    if name.endswith(".__init__"):
        name = name[:-9]
    if name not in sys.modules:
        return None
    if changed & warm_lines.get(path, set()):
        return None
    try:
        tree = ast.parse(old_text)
    except SyntaxError:
        return None
    spans = body_spans(tree)
    if not all(any(a <= ln <= b for a, b in spans) for ln in changed):
        return None
    fn = os.path.join(src, path)
    try:
        oldc = compile(old_text, fn, "exec")
        newc = compile(new_text, fn, "exec")
    except SyntaxError:
        return None
    pairs = []
    if not _pair(oldc, newc, pairs):
        return None
    return [(o, n) for o, n in pairs[1:] if not (o.co_code == n.co_code and _key(o.co_consts) == _key(n.co_consts) and o.co_names == n.co_names)]


def _key(c):
    if isinstance(c, types.CodeType):
        return (c.co_code, _key(c.co_consts), c.co_names)
    if isinstance(c, (tuple, frozenset)):
        return (type(c).__name__, tuple(sorted(map(_key, c), key=repr)) if isinstance(c, frozenset) else tuple(map(_key, c)))
    return (type(c).__name__, repr(c))


def apply_swaps(plans, idx):
    n = 0
    for pairs in plans:
        for o, new in pairs:
            for f in idx.get((o.co_filename, o.co_qualname, o.co_firstlineno), []):
                f.__code__ = new
                n += 1
    return n
