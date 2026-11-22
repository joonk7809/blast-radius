import ast
import bisect
import builtins
import enum
import gc
import gzip
import importlib
import json
import logging
import marshal
import os
import pickle
import re
import select
import signal
import sys
import time
import types

DATA = os.environ.get("BR_DATA", "/data")
SRC = os.environ.get("BR_SRC", "/sqlglot")
TMP = os.environ.get("BR_TMP", "/tmp")
HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.environ.get("BR_MAP", os.path.join(HERE, "covmeta.json"))
PARALLEL = int(os.environ.get("BR_PARALLEL", "2"))
HEAVY_MS = int(os.environ.get("BR_HEAVY_MS", "1000000"))
DEBUG = os.environ.get("BR_DEBUG", "0") == "1"
ZYGOTE = os.environ.get("BR_ZYGOTE", "1") == "1"
UNITEST = os.environ.get("BR_UNITEST", "1") == "1"
PARTIAL = os.environ.get("BR_PARTIAL", "1") == "1"
GAPS = os.environ.get("BR_GAPS", "1") == "1"
FIXLIST = os.environ.get("BR_FIXLIST", "1") == "1"
LEANIMP = os.environ.get("BR_LEANIMP", "0") == "1"
LAZYPANDAS = os.environ.get("BR_LAZYPANDAS", "1") == "1"
STMTSEL = os.environ.get("BR_STMTSEL", "1") == "1"
ALPHA = os.environ.get("BR_ALPHA", "1") == "1"
NESTALPHA = os.environ.get("BR_NESTALPHA", "1") == "1"
LAMBDAS = os.environ.get("BR_LAMBDAS", "1") == "1"
SHARED = os.environ.get("BR_SHARED", "1") == "1"
LAZYTABLES = os.environ.get("BR_LAZYTABLES", "1") == "1"
TPCQ2 = os.environ.get("BR_TPCQ2", "1") == "1"
TPCREF = os.environ.get("BR_TPCREF", "1") == "1"
TPCWARM = os.environ.get("BR_TPCWARM", "0") == "1"
TPCPARSE = os.environ.get("BR_TPCPARSE", "1") == "1"
UNITCOST = os.environ.get("BR_UNITCOST", "1") == "1"
UNIT_K = float(os.environ.get("BR_UNIT_K", "2.0"))
GCFREEZE = os.environ.get("BR_GCFREEZE", "0") == "1"
LAZYEXEC = os.environ.get("BR_LAZYEXEC", "1") == "1"
LAZYUNITS = os.environ.get("BR_LAZYUNITS", "1") == "1"
DEBUG_N = int(os.environ.get("BR_DEBUG_N", "-1"))
UNITS = os.environ.get("BR_UNITS", "1") == "1"
CANON = os.environ.get("BR_CANON", "1") == "1"
DOCSTRIP = os.environ.get("BR_DOCSTRIP", "1") == "1"
DOC = [False]
REUSEOV = os.environ.get("BR_REUSEOV", "1") == "1"
THINOV = os.environ.get("BR_THINOV", "1") == "1"
OPTWARM = os.environ.get("BR_OPTWARM", "1") == "1"
SEGPARSE = os.environ.get("BR_SEGPARSE", "1") == "1"
LISTRULE = os.environ.get("BR_LISTRULE", "1") == "1"
FAILFAST = os.environ.get("BR_FAILFAST", "1") == "1"
RUN_K = float(os.environ.get("BR_RUN_K", "1.0"))
RUN_O = float(os.environ.get("BR_RUN_O", "0.0"))
RUN_O_RE = float(os.environ.get("BR_RUN_O_RE", "0.0"))
STATIC = os.environ.get("BR_STATIC", "0") == "1"
ITF_UNITS = os.environ.get("BR_ITF_UNITS", "1") == "1"
FRAC_K = float(os.environ.get("BR_FRAC_K", "1.33"))
FRAC_C = float(os.environ.get("BR_FRAC_C", "0.5"))
FASTNOOP = os.environ.get("BR_FASTNOOP", "1") == "1"
SETUP_ATTRS = os.environ.get("BR_SETUP_ATTRS", "1") == "1"
NEWTOP = os.environ.get("BR_NEWTOP", "1") == "1"
TPCQ = os.environ.get("BR_TPCQ", "1") == "1"
MEMO = os.environ.get("BR_MEMO", "1") == "1"
MEMO_K = float(os.environ.get("BR_MEMO_K", "1.0"))
MEMO_MISS = float(os.environ.get("BR_MEMO_MISS", "0.8"))
PROBE = os.environ.get("BR_PROBE", "1") == "1"
COLLECT = os.environ.get("BR_COLLECT", "1") == "1"
IMPORTT = os.environ.get("BR_IMPORTT", "1") == "1"
CLOSURE = os.environ.get("BR_CLOSURE", "1") == "1"
IMPORTBODY = os.environ.get("BR_IMPORTBODY", "1") == "1"
CACHESITE = os.environ.get("BR_CACHESITE", "1") == "1"
BUDGET_FRAC = float(os.environ.get("BR_BUDGET_FRAC", "0.75"))
DEBUGLOG = os.environ.get("BR_DEBUGLOG", "1") == "1"
LEAN = os.environ.get("BR_LEAN", "1") == "1"
CANARY_K = int(os.environ.get("BR_CANARY_K", "0"))
CANARY_SCALE = float(os.environ.get("BR_CANARY_SCALE", "0.65"))
LEAN_COST = float(os.environ.get("BR_LEAN_COST", "15.5"))
LEAN_SCALE = float(os.environ.get("BR_LEAN_SCALE", "1.3"))
BUDGET_K = float(os.environ.get("BR_LEAN_BUDGET_K", "3.0"))
BUDGET_C = float(os.environ.get("BR_LEAN_BUDGET_C", "0.3"))
LEAN_ROOM = float(os.environ.get("BR_LEAN_ROOM", "0.5"))
LEANCAL = os.environ.get("BR_LEANCAL", "0") == "1"
LIGHTFIRST = os.environ.get("BR_LIGHTFIRST", "0")
LEAN_SEED = [int(x) for x in os.environ.get("BR_LEAN_SEED", "8,5,96").split(",") if x]
LEAN_MEM = int(float(os.environ.get("BR_LEAN_MEM_MB", "512")) * 1048576)
LEAN_WALL = float(os.environ.get("BR_LEAN_WALL", "90"))
LEAN_OPT_COST = float(os.environ.get("BR_LEAN_OPT_COST", "12.0"))
T0 = time.monotonic()
GCOFF = os.environ.get("BR_GCOFF", "1") == "1"
PATHRULES = os.environ.get("BR_PATHRULES", "1") == "1"
TESTSIDE = os.environ.get("BR_TESTSIDE", "1") == "1"
LAZYGONE = os.environ.get("BR_LAZYGONE", "1") == "1"
INERT = os.environ.get("BR_INERT", "1") == "1"
RAWBIN = os.environ.get("BR_RAWBIN", "1") == "1"
PYTEST_CFG = ("conftest.py", "pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini")
PYTEST_DIRS = ("", "tests", "tests/dialects")
if GCOFF:
    gc.disable()


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def _unquote(s):
    if len(s) > 1 and s[0] == '"' and s[-1] == '"':
        return ast.literal_eval("b" + s.encode("utf-8", "surrogateescape").decode("latin-1")).decode("utf-8", "surrogateescape")
    return s


def _header_paths(rest):
    m = re.fullmatch(r'("(?:[^"\\]|\\.)*"|a/\S+) ("(?:[^"\\]|\\.)*"|b/\S+)', rest)
    if m:
        a, b = _unquote(m.group(1)), _unquote(m.group(2))
        return a[2:], b[2:]
    half = (len(rest) - 1) // 2
    if rest[:2] == "a/" and rest[half:half + 3] == " b/" and rest[2:half] == rest[half + 3:]:
        return rest[2:half], rest[2:half]
    raise ValueError("bad diff header")


def parse_patch(text):
    files = []
    cur = None
    hunk = None
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if RAWBIN:
                old, new = _header_paths(line[11:].rstrip("\n").rstrip("\r"))
            else:
                m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
                old, new = m.group(1), m.group(2)
            cur = {"old": old, "path": new, "hunks": [], "new_file": False, "deleted": False}
            files.append(cur)
            hunk = None
            continue
        if cur is None:
            continue
        if hunk is None:
            if line.startswith("new file mode"):
                cur["new_file"] = True
            elif line.startswith("deleted file mode"):
                cur["deleted"] = True
            elif RAWBIN and (line.startswith("GIT binary patch") or line.startswith("Binary files ")):
                cur["binary"] = True
            elif line.startswith("--- ") or line.startswith("+++ ") or line.startswith("index ") or line.startswith("similarity") or line.startswith("rename "):
                pass
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
        if m:
            hunk = {"old_start": int(m.group(1)), "old_len": int(m.group(2) or 1), "new_start": int(m.group(3)), "lines": []}
            cur["hunks"].append(hunk)
            continue
        if hunk is None:
            continue
        if line.startswith("\\"):
            if hunk["lines"]:
                tag, body = hunk["lines"][-1]
                hunk["lines"][-1] = (tag, body.rstrip("\n").rstrip("\r") if body.endswith("\n") else body)
            continue
        tag = line[:1]
        if tag in " -+":
            hunk["lines"].append((tag, line[1:]))
        elif line in ("\n", "\r\n"):
            hunk["lines"].append((" ", line))
    return files


def apply_file(old_text, hunks):
    old = old_text.splitlines(keepends=True)
    out = []
    pos = 0
    for h in hunks:
        start = h["old_start"] - 1 if h["old_len"] else h["old_start"]
        out.extend(old[pos:start])
        pos = start
        for tag, body in h["lines"]:
            if tag == " ":
                out.append(old[pos])
                pos += 1
            elif tag == "-":
                pos += 1
            else:
                out.append(body)
    out.extend(old[pos:])
    return "".join(out)


def added_new_lines(hunks):
    out = []
    for h in hunks:
        ln = h["new_start"]
        for tag, _ in h["lines"]:
            if tag == "+":
                out.append(ln)
                ln += 1
            elif tag == " ":
                ln += 1
    return out


def changed_old_lines(hunks):
    removed, anchors = set(), set()
    for h in hunks:
        ln = h["old_start"] if h["old_len"] else h["old_start"] + 1
        for tag, _ in h["lines"]:
            if tag == "-":
                removed.add(ln)
                ln += 1
            elif tag == "+":
                anchors.add(ln - 1)
                anchors.add(ln)
            else:
                ln += 1
    return removed, anchors


def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return parts[::-1]


def _identity_safe(node, resolve):
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    names = _dotted(node) if isinstance(node, ast.Attribute) else None
    if not names or resolve is None:
        return False
    obj = resolve(names)
    return isinstance(obj, enum.Enum)


class _Canon(ast.NodeTransformer):
    def __init__(self, resolve):
        self.resolve = resolve
        self.undo = []

    def visit_Compare(self, node):
        self.generic_visit(node)
        if len(node.ops) == 1 and isinstance(node.ops[0], (ast.Is, ast.IsNot)) and _identity_safe(node.comparators[0], self.resolve):
            self.undo.append((node, "ops", node.ops))
            node.ops = [ast.Eq() if isinstance(node.ops[0], ast.Is) else ast.NotEq()]
        return node

    def visit_Call(self, node):
        self.generic_visit(node)
        f = node.func
        if DEBUGLOG and isinstance(f, ast.Attribute) and f.attr == "debug" and isinstance(f.value, ast.Name) and f.value.id in _pinned_of(self.resolve) and any(isinstance(a, ast.Constant) for a in node.args):
            obj = self.resolve([f.value.id])
            if type(obj) is logging.Logger and not obj.isEnabledFor(logging.DEBUG) and logging.getLogger(obj.name) is obj:
                self.undo.append((node, "args", node.args))
                node.args = [ast.Constant(None) if isinstance(a, ast.Constant) else a for a in node.args]
        return node


def module_resolver(path):
    name = path[:-3].replace("/", ".")
    if name.endswith(".__init__"):
        name = name[:-9]
    miss = object()

    def resolve(names):
        if SRC not in sys.path:
            sys.path.insert(0, SRC)
        try:
            obj = vars(importlib.import_module(name)).get(names[0], miss)
            for a in names[1:]:
                obj = getattr(obj, a, miss)
            return obj
        except Exception:
            return miss

    return resolve


_PARSED = {}


def parse_cached(text):
    t = _PARSED.get(text)
    if t is None:
        try:
            t = ast.parse(text)
        except UnicodeEncodeError:
            if not RAWBIN:
                raise
            t = ast.parse(text.encode("utf-8", "surrogateescape"))
        _PARSED[text] = t
    return t


def _isdoc(st):
    return isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant) and isinstance(st.value.value, str)


def _undoc(node):
    undo = []
    for n in ast.walk(node):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body and _isdoc(n.body[0]):
            undo.append((n, n.body))
            n.body = n.body[1:] or [ast.Pass()]
    return undo


def _canon_dump(node, resolve):
    if DOC[0]:
        undo = _undoc(node)
        try:
            return _canon_dump1(node, resolve)
        finally:
            for n, body in reversed(undo):
                n.body = body
    return _canon_dump1(node, resolve)


def _canon_dump1(node, resolve):
    if not CANON:
        return ast.dump(node, annotate_fields=False, include_attributes=False)
    canon = _Canon(resolve)
    try:
        canon.visit(node)
        return ast.dump(node, annotate_fields=False, include_attributes=False)
    finally:
        for n, field, value in reversed(canon.undo):
            setattr(n, field, value)


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
_FRAME_CALLS = {"locals", "vars", "eval", "exec", "globals", "dir", "currentframe"}


def _frame_call(n):
    return isinstance(n, ast.Call) and (isinstance(n.func, ast.Name) and n.func.id in _FRAME_CALLS or isinstance(n.func, ast.Attribute) and n.func.attr == "_getframe")


def _outer_binds(fn):
    params = {a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg)}
    order, nested, decl = [], set(), set()
    todo = list(reversed(fn.body))
    while todo:
        n = todo.pop()
        if isinstance(n, (ast.Global, ast.Nonlocal)) and NESTALPHA:
            decl.update(n.names)
            continue
        if isinstance(n, (ast.Global, ast.Nonlocal, ast.ClassDef)) or _frame_call(n):
            return None
        if isinstance(n, _SCOPES):
            for x in ast.walk(n):
                if isinstance(x, (ast.Global, ast.Nonlocal)) and NESTALPHA:
                    decl.update(x.names)
                elif isinstance(x, (ast.Global, ast.Nonlocal, ast.ClassDef)) and x is not n or isinstance(n, ast.ClassDef) or NESTALPHA and _frame_call(x):
                    return None
                elif isinstance(x, ast.arg):
                    nested.add(x.arg)
                elif isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)):
                    nested.add(x.id)
            continue
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)) and n.id not in params and n.id not in order:
            order.append(n.id)
        todo.extend(reversed(list(ast.iter_child_nodes(n))))
    order = [x for x in order if x not in decl]
    if (nested | _string_binds(fn.body)) & set(order):
        return None
    return {name: "\0L%d" % i for i, name in enumerate(order)}, decl


def _string_binds(body):
    strb = set()
    for st in body:
        for x in ast.walk(st):
            if isinstance(x, (ast.ExceptHandler, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.MatchAs, ast.MatchStar)) and x.name:
                strb.add(x.name)
            elif isinstance(x, ast.MatchMapping) and x.rest:
                strb.add(x.rest)
            elif isinstance(x, ast.alias):
                strb.add(x.asname or x.name.split(".")[0])
    return strb


def _inner_hits(g, k, decl):
    params = {a.arg for a in ast.walk(g.args) if isinstance(a, ast.arg)}
    order, inner, own = [], set(), []
    todo = list(reversed(g.body))
    while todo:
        n = todo.pop()
        if isinstance(n, _SCOPES):
            inner.update(x.id if isinstance(x, ast.Name) else x.arg for x in ast.walk(n) if isinstance(x, (ast.Name, ast.arg)))
            continue
        if isinstance(n, ast.Name):
            own.append(n)
            if isinstance(n.ctx, (ast.Store, ast.Del)) and n.id not in params and n.id not in order:
                order.append(n.id)
        todo.extend(reversed(list(ast.iter_child_nodes(n))))
    blocked = inner | decl | _string_binds(g.body)
    ren = {x: "\0N%d_%d" % (k, i) for i, x in enumerate(x for x in order if x not in blocked)}
    return [(n, ren[n.id]) for n in own if n.id in ren]


def _alpha_dump(fn, resolve):
    binds = _outer_binds(fn)
    if binds is None:
        return None
    names, decl = binds
    hits = [(n, names[n.id]) for st in fn.body for n in ast.walk(st) if isinstance(n, ast.Name) and n.id in names]
    if NESTALPHA:
        for k, g in enumerate(x for st in fn.body for x in ast.walk(st) if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))):
            hits += _inner_hits(g, k, decl)
    if not hits:
        return None
    back = [n.id for n, _ in hits]
    for n, new in hits:
        n.id = new
    try:
        return _canon_dump(fn, resolve)
    finally:
        for (n, _), b in zip(hits, back):
            n.id = b


def _class_head(node, resolve):
    return (node.name, [_canon_dump(b, resolve) for b in node.bases], [_canon_dump(k, resolve) for k in node.keywords], [_canon_dump(d, resolve) for d in node.decorator_list])


def _same_body(a_body, b_body, oc, nc, resolve):
    if DOC[0]:
        a_body = a_body[1:] if a_body and _isdoc(a_body[0]) else a_body
        b_body = b_body[1:] if b_body and _isdoc(b_body[0]) else b_body
    if len(a_body) != len(b_body):
        return False
    for x, y in zip(a_body, b_body):
        tx = any(x.lineno <= ln <= x.end_lineno for ln in oc)
        ty = any(y.lineno <= ln <= y.end_lineno for ln in nc)
        if not tx and not ty:
            continue
        if type(x) is not type(y):
            return False
        if isinstance(x, ast.ClassDef):
            if _class_head(x, resolve) != _class_head(y, resolve) or not _same_body(x.body, y.body, oc, nc, resolve):
                return False
        elif _canon_dump(x, resolve) != _canon_dump(y, resolve):
            if not (ALPHA and isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef))):
                return False
            ax = _alpha_dump(x, resolve)
            if ax is None or ax != _alpha_dump(y, resolve):
                return False
    return True


def _binds(n):
    if isinstance(n, ast.Name):
        return () if isinstance(n.ctx, ast.Load) else (n.id,)
    if isinstance(n, ast.arg):
        return (n.arg,)
    if isinstance(n, ast.alias):
        return ((n.asname or n.name).split(".")[0],)
    if isinstance(n, (ast.Global, ast.Nonlocal)):
        return tuple(n.names)
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return (n.name,)
    if isinstance(n, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return (n.name,) if n.name else ()
    if isinstance(n, ast.MatchMapping):
        return (n.rest,) if n.rest else ()
    return ()


def _pinned_of(resolve):
    if resolve is None:
        return set()
    if not hasattr(resolve, "pinned"):
        trees = getattr(resolve, "trees", None)
        resolve.pinned = _pinned(trees[0]) & _pinned(trees[1]) if trees else set()
    return resolve.pinned


def _pinned(tree):
    count = {}
    for n in ast.walk(tree):
        for x in _binds(n):
            count[x] = count.get(x, 0) + 1
    return {st.targets[0].id for st in tree.body if isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and count[st.targets[0].id] == 1}


def ast_noop(old_text, new_text, hunks, resolve):
    try:
        a, b = parse_cached(old_text), parse_cached(new_text)
    except SyntaxError:
        return False
    removed, anchors = changed_old_lines(hunks)
    if resolve is not None:
        resolve.trees = (a, b)
    return _same_body(a.body, b.body, removed | anchors, new_side_lines(hunks), resolve)


def new_side_lines(hunks):
    out = set()
    for h in hunks:
        ln = h["new_start"]
        for tag, _ in h["lines"]:
            if tag == "+":
                out.add(ln)
                ln += 1
            elif tag == "-":
                out.add(ln)
                out.add(ln - 1)
            else:
                ln += 1
    return out


def strip_ast(text, resolve=None):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    if DOC[0]:
        _undoc(tree)
    if CANON:
        tree = _Canon(resolve).visit(tree)
    return ast.dump(tree, annotate_fields=False, include_attributes=False)


class Units:
    def __init__(self, text, lines=None):
        self.tree = parse_cached(text)
        self.spans = []
        self.lines = None if lines is None or not LAZYUNITS else sorted(lines)
        self._walk(self.tree, False, [])

    def _wanted(self, first, last):
        if self.lines is None:
            return True
        i = bisect.bisect_left(self.lines, first)
        return i < len(self.lines) and self.lines[i] <= last

    def _walk(self, node, runtime, stack):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.stmt, ast.Lambda, ast.comprehension)) and hasattr(child, "lineno"):
                is_fn = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
                head_end = child.end_lineno
                body = getattr(child, "body", None)
                first = child.lineno
                if isinstance(body, list) and body and isinstance(child, ast.stmt):
                    head_end = max(child.lineno, body[0].lineno - 1)
                    for d in getattr(child, "decorator_list", []):
                        first = min(first, d.lineno)
                    self.spans.append((first, head_end, child.end_lineno, runtime, child))
                else:
                    self.spans.append((child.lineno, child.end_lineno, child.end_lineno, runtime, child))
                if self._wanted(first, child.end_lineno):
                    self._walk(child, runtime or is_fn, stack)
            elif self.lines is None or not hasattr(child, "lineno") or self._wanted(child.lineno, child.end_lineno or child.lineno):
                self._walk(child, runtime, stack)

    def unit_for(self, line):
        best = None
        for first, head_end, end, runtime, node in self.spans:
            if first <= line <= end:
                inner = first <= line <= head_end
                size = (head_end if inner else end) - first
                if inner and (best is None or size <= best[0]):
                    best = (size, first, head_end, runtime, node)
        return best

    def gap_units(self, line):
        enc = min((s for s in self.spans if s[0] <= line <= s[2]), key=lambda s: s[2] - s[0], default=None)
        if enc is None or not (enc[3] or isinstance(enc[4], (ast.FunctionDef, ast.AsyncFunctionDef))):
            return []
        lo, hi = enc[0], enc[2]
        inside = [s for s in self.spans if lo <= s[0] and s[2] <= hi and s is not enc]
        prev = max((s for s in inside if s[2] < line), key=lambda s: s[2], default=None)
        nxt = min((s for s in inside if s[0] > line), key=lambda s: s[0], default=None)
        out = [(s[1] - s[0], s[0], s[1], s[3], s[4]) for s in (prev, nxt) if s]
        return out or [(0, enc[0], enc[1], enc[3], enc[4])]


CACHE_SITES = json.load(open(os.path.join(HERE, "cachesites.json"))) if CACHESITE else {}
IMPORT_LAMBDAS = {tuple(x) for x in json.load(open(os.path.join(HERE, "importlambdas.json")))} if LAMBDAS else set()


def _strip(node, called=False):
    if isinstance(node, ast.Lambda) and not called:
        return ("Lambda", _strip(node.args))
    if isinstance(node, ast.Call):
        return ("Call", _strip(node.func, True), tuple(_strip(a, True) for a in node.args), tuple(_strip(k, True) for k in node.keywords))
    if isinstance(node, ast.keyword):
        return ("keyword", node.arg, _strip(node.value, called))
    if isinstance(node, ast.AST):
        return (type(node).__name__,) + tuple(_strip(getattr(node, k, None)) for k in node._fields)
    if isinstance(node, list):
        return tuple(map(_strip, node))
    return (type(node).__name__, node)


def _enclosing_stmt(units, ln):
    return min((sp for sp in units.spans if isinstance(sp[4], ast.stmt) and sp[0] <= ln <= sp[2]), key=lambda sp: sp[2] - sp[0], default=(0, 0, 0, 0, None))[4]


def lambda_only(path, old_units, new_units, hunks):
    olds, news = {}, {}
    for h in hunks:
        hr, ha = changed_old_lines([h])
        for units, lines, acc in ((old_units, hr or ha, olds), (new_units, added_new_lines([h]), news)):
            for ln in lines:
                u = units.unit_for(ln)
                if u is None or u[3]:
                    continue
                if not isinstance(u[4], ast.Lambda) or units is old_units and (path, u[4].lineno) in IMPORT_LAMBDAS:
                    return False
                st = _enclosing_stmt(units, ln)
                if st is None:
                    return False
                acc[id(st)] = st
    if not olds or len(olds) != len(news):
        return False
    return all(_strip(a) == _strip(b) for a, b in zip(sorted(olds.values(), key=lambda n: n.lineno), sorted(news.values(), key=lambda n: n.lineno)))


def merge(a, b):
    for n, keys in b.items():
        if n in a:
            if a[n] is None or keys is None:
                a[n] = None
            else:
                a[n] = a[n] | keys
        else:
            a[n] = None if keys is None else set(keys)
    return a


def full(nums):
    return {n: None for n in nums}


class CovMap:
    def __init__(self, path, id_to_num):
        with open(path) as fh:
            m = json.load(fh)
        with open(os.path.join(os.path.dirname(path), "covsets.bin"), "rb") as fh:
            raw = fh.read()
        n = int.from_bytes(raw[:4], "little")
        self._offs = memoryview(raw)[4:4 + 4 * n].cast("I")
        self._data = memoryview(raw)[4 + 4 * n:].cast("H")
        self._cache = {}
        self.idx_to_num = [id_to_num.get(t) for t in m["tests"]]
        self.units = [(self.idx_to_num[t], k if UNITS else "") for t, k in m.get("units", [[i, ""] for i in range(len(m["tests"]))])]
        self.nunits = {self.idx_to_num[int(t)]: c for t, c in m.get("nunits", {}).items()}
        self.files = m["files"]
        self.fixtures = m["fixtures"]
        STMT_OF.update((m["tests"][int(t)], v) for t, v in m.get("stmt_of", {}).items())
        self.by_file = {}
        self.ids = {}
        for i, t in enumerate(m["tests"]):
            n = self.idx_to_num[i]
            if n is not None:
                self.by_file.setdefault(t.split("::")[0], []).append(n)
                self.ids[n] = t

    def num_id(self, n):
        return self.ids.get(n, "")

    def set(self, i):
        r = self._cache.get(i)
        if r is None:
            r = self._cache[i] = self._data[self._offs[i]:self._offs[i + 1]].tolist()
        return r

    def _from_units(self, us):
        out = {}
        for u in us:
            n, k = self.units[u]
            if n is None:
                continue
            if not k:
                out[n] = None
            elif out.get(n, 0) is not None:
                out.setdefault(n, set()).add(k)
        return out

    def tests_for_lines(self, path, lines):
        fm = self.files.get(path)
        if not fm:
            return {}
        lm = fm["lines"]
        us = set()
        for ln in lines:
            s = lm.get(str(ln))
            if s is not None:
                us.update(self.set(s))
        return self._from_units(us)

    def tests_touching_file(self, path):
        fm = self.files.get(path)
        if not fm:
            return {}
        us = set()
        for s in set(fm["lines"].values()):
            us.update(self.set(s))
        return full(self._from_units(us))


def module_test_files(path, cov):
    stem = os.path.splitext(os.path.basename(path))[0]
    out = set()
    for cand in (f"tests/dialects/test_{stem}.py", f"tests/test_{stem}.py"):
        out.update(cov.by_file.get(cand, []))
    return out


def candidates_for(f, old_text, new_text, cov, notes):
    r = _candidates_for(f, old_text, new_text, cov, notes)
    r = r if isinstance(r, dict) else full(r)
    if FIXLIST and f["path"].startswith("tests/") and not f["path"].endswith(".py") and "/tpc-" not in f["path"]:
        FORCE_LIST.update(n for n in r if n not in FRACTION_OK)
    return r


FRACTION_OK = set()
FORCE_LIST = set()
_QKEY = re.compile(r"^s:\('(\S+) (\d+)', \[\]\)$")
_QKEY2 = re.compile(r"""^s:\((["'])(\d+), """)


def _pairs(text):
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    from tests import helpers
    stmts = helpers._filter_comments(text).split(";")
    return [(helpers._extract_meta(stmts[i].strip()), stmts[i + 1].strip()) for i in range(0, len(stmts) - 1, 2)]


def changed_query_indices(path, old_text, new_text):
    folder = os.path.dirname(path)
    sql_path = os.path.join(folder, os.path.basename(folder) + ".sql")
    if not path.startswith("tests/fixtures/") or not os.path.exists(os.path.join(SRC, sql_path)):
        return None
    try:
        if path == sql_path:
            if old_text is None or new_text is None:
                return None
            a, b = _pairs(old_text), _pairs(new_text)
            if len(a) != len(b):
                return None
            return {i + 1 for i in range(len(a)) if a[i] != b[i]}
        table = os.path.basename(path).split(".")[0]
        if not table:
            return None
        with open(os.path.join(SRC, sql_path), encoding="utf-8") as fh:
            pairs = _pairs(fh.read())
        word = re.compile(r"\b%s\b" % re.escape(table), re.I)
        return {i + 1 for i, ((sql, _), _) in enumerate(pairs) if word.search(sql)}
    except Exception:
        return None


def query_unit_keys(cov, n, idx, word):
    keys = [k for m, k in cov.units if m == n and k]
    sub = [k for k in keys if k.startswith("s:")]
    tid = cov.num_id(n)
    own = "tpc-ds" if "tpcds" in tid else "tpc-h" if "tpch" in tid else None
    if TPCQ2 and sub and own and all(_QKEY2.match(k) for k in sub) and all(not k.startswith("f:") for k in keys):
        if own != word:
            return set()
        return {"q:%s" % _QKEY2.match(k).group(2) for k in sub if int(_QKEY2.match(k).group(2)) in idx}
    if not sub or not all(_QKEY.match(k) for k in sub):
        return None
    words = {_QKEY.match(k).group(1) for k in sub}
    if word not in words:
        return set()
    if words != {word}:
        return None
    out = set()
    for k in keys:
        m = _QKEY.match(k)
        if m and int(m.group(2)) in idx:
            out.add(k)
        elif k.startswith("f:") and int(k[2:]) + 1 in idx:
            out.add(k)
    return out


_MP_TESTS = {"test_execute_tpcds": "tpc-ds", "test_execute_tpch": "tpc-h"}


_SETUP_INDEX = []


def _setup_raw(tf):
    entry = _read_tree(os.path.join(SRC, tf))
    if entry[1] is None:
        try:
            entry[1] = ast.parse(entry[0])
        except SyntaxError:
            entry[1] = False
    tree = entry[1]
    if tree is False:
        return None
    consts, loose = {}, []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef, ast.Import, ast.ImportFrom)):
            continue
        strs = [n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if not strs:
            continue
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    consts[t.id] = strs
        else:
            loose.extend(strs)
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        methods = {fn.name: fn for fn in node.body if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))}
        setup = methods.get("setUpClass")
        if setup is None:
            continue
        stmts = []
        for st in setup.body:
            strs = [n.value for n in ast.walk(st) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
            for n in ast.walk(st):
                if isinstance(n, ast.Name) and n.id in consts:
                    strs.extend(consts[n.id])
            attrs = {n.attr for n in ast.walk(st) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "cls"}
            stmts.append((strs, attrs))
        direct = {name: {n.attr for n in ast.walk(fn) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"} for name, fn in methods.items()}
        reach = {}
        for name in methods:
            seen, todo, acc = {name}, [name], set()
            while todo:
                m = todo.pop()
                for a in direct[m]:
                    acc.add(a)
                    if a in methods and a not in seen:
                        seen.add(a)
                        todo.append(a)
            reach[name] = acc
        classes.append((node.name, stmts, reach))
    return loose, classes


def build_setup_cache(path, files):
    with open(path, "wb") as fh:
        pickle.dump({tf: _setup_raw(tf) for tf in files}, fh)


def _setup_index(cov):
    if _SETUP_INDEX:
        return _SETUP_INDEX
    cache = {}
    try:
        with open(os.path.join(HERE, "setupidx.pkl"), "rb") as fh:
            cache = pickle.load(fh)
    except OSError:
        pass
    for tf, nums in cov.by_file.items():
        raw = cache[tf] if tf in cache else _setup_raw(tf)
        if raw is None:
            continue
        loose, raw_classes = raw
        classes = []
        for cname, stmts, reach in raw_classes:
            prefix = "%s::%s::" % (tf, cname)
            cnums = [x for x in nums if cov.num_id(x).startswith(prefix)]
            tattrs = {x: reach.get(cov.num_id(x)[len(prefix):], None) for x in cnums}
            classes.append((cnums, stmts, tattrs))
        _SETUP_INDEX.append((nums, loose, classes))
    return _SETUP_INDEX


def tpc_lazy(patched):
    return LAZYEXEC and not any(r in ("tests/helpers.py", "sqlglot/executor/table.py", "tests/test_executor.py") or "/tpc-" in r and not (LAZYTABLES and r.endswith(".sql") and fixture_loads(r, c)) for r, c in patched.items())


def fixture_loads(path, text):
    if text is None or not path.endswith(".sql"):
        return False
    try:
        text.encode("utf-8")
        if SRC not in sys.path:
            sys.path.insert(0, SRC)
        from tests import helpers
        _pairs(text)
        lines = []
        for line in helpers._filter_comments(text).splitlines():
            lines.append(line)
        return True
    except Exception:
        return False


def class_setup_readers(path, cov, narrow=True):
    folder = os.path.dirname(path)

    def hit(strs):
        for v in strs:
            c = v.strip("/")
            if c and (path.endswith("/" + c) or folder.endswith("/" + c)):
                return True
        return False

    out = set()
    for nums, loose, classes in _setup_index(cov):
        if hit(loose):
            out.update(nums)
        for cnums, stmts, tattrs in classes:
            attrs, any_hit = set(), False
            for strs, st_attrs in stmts:
                if hit(strs):
                    any_hit = True
                    attrs |= st_attrs
            if not any_hit:
                continue
            if not attrs or not SETUP_ATTRS or not narrow:
                out.update(cnums)
                continue
            out.update(x for x in cnums if tattrs[x] is None or tattrs[x] & attrs)
    return out


def modname_of(path):
    name = path[:-3].replace("/", ".")
    return name[:-9] if name.endswith(".__init__") else name


def top_names(tree):
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in node.targets if isinstance(node, ast.Assign) else [node.target]:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        out[n.id] = (node.lineno, node.end_lineno)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                out[(a.asname or a.name).split(".")[0]] = (node.lineno, node.end_lineno)
    return out


_MUTATORS = {"clear", "pop", "popitem", "update", "append", "extend", "setdefault", "add", "remove", "discard", "insert", "__setitem__"}


_SELF_SHARED = {"__class__", "__dict__", "dialect", "_dispatch", "tokenizer", "parser_class", "generator_class", "tokenizer_class"}


_SELF_ALIAS = re.compile(r"self\.(\w+)\s*(?::[^=\n]*)?=\s*(?:self\.(?:[A-Z_][A-Z0-9_]*\b|_dispatch|dialect|__class__|__dict__|\w+_class)|\w*\(\s*self\.dialect|cls\b|vars\()")


class _Shared:
    def fname(self, f):
        if isinstance(f, ast.Name):
            return self.bi.get(f.id, f.id)
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "builtins":
            return f.attr
        return None

    def __init__(self, tree, text):
        self.mod = set(top_names(tree))
        self.bi = {a.asname or a.name: a.name for st in tree.body if isinstance(st, ast.ImportFrom) and st.module == "builtins" for a in st.names}
        self.sattrs = set(_SELF_ALIAS.findall(text))
        self.cattrs = set()
        todo = [c for c in tree.body if isinstance(c, ast.ClassDef)]
        while todo:
            for st in todo.pop().body:
                if isinstance(st, ast.ClassDef):
                    todo.append(st)
                elif isinstance(st, ast.Assign) or isinstance(st, ast.AnnAssign) and st.value is not None:
                    self.cattrs.update(t.id for t in (st.targets if isinstance(st, ast.Assign) else [st.target]) if isinstance(t, ast.Name))

    def base(self, e, local, alias):
        if isinstance(e, ast.Name):
            return e.id in alias or e.id == "cls" or e.id in self.mod and e.id not in local
        if isinstance(e, ast.Attribute):
            if isinstance(e.value, ast.Name) and e.value.id == "self":
                return e.attr in _SELF_SHARED or e.attr in self.cattrs or e.attr in self.sattrs or e.attr.isupper()
            return self.base(e.value, local, alias)
        if isinstance(e, ast.Subscript):
            return self.base(e.value, local, alias)
        if isinstance(e, ast.Call):
            fn = self.fname(e.func)
            if fn in ("type", "vars"):
                return True
            if fn == "getattr" and e.args:
                return self.base(e.args[0], local, alias)
        return False

    def scope(self, fn, outer):
        params = {a.arg for a in ast.walk(fn.args) if isinstance(a, ast.arg)}
        local = set(params)
        local.update(x.id for x in ast.walk(fn) if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store))
        alias = set(outer)
        while True:
            more = {t.id for st in ast.walk(fn) if isinstance(st, (ast.Assign, ast.AnnAssign, ast.NamedExpr)) and st.value is not None and self.base(st.value, local, alias) for t in (st.targets if isinstance(st, ast.Assign) else [st.target]) if isinstance(t, ast.Name)} - alias
            if not more:
                return local, alias, params - {"self"}
            alias |= more

    def writes(self, n, local, alias, params):
        if isinstance(n, ast.Global):
            return True
        targets = n.targets if isinstance(n, (ast.Assign, ast.Delete)) else [n.target] if isinstance(n, (ast.AugAssign, ast.AnnAssign)) else []
        if any(isinstance(t, (ast.Attribute, ast.Subscript)) and self.base(t.value, local, alias) for t in targets):
            return True
        for x in ast.walk(n) if not isinstance(n, (ast.If, ast.For, ast.While, ast.With, ast.Try, ast.Match)) else ():
            if not isinstance(x, ast.Call):
                continue
            f = x.func
            if isinstance(f, ast.Attribute) and f.attr in _MUTATORS and self.base(f.value, local, alias):
                return True
            if (self.fname(f) in ("setattr", "delattr") or isinstance(f, ast.Attribute) and f.attr in ("__setattr__", "__delattr__") and isinstance(f.value, ast.Name) and f.value.id in ("object", "type")) and x.args:
                obj = x.args[0]
                if not (isinstance(obj, ast.Name) and obj.id == "self") and (self.base(obj, local, alias) or not isinstance(obj, ast.Name) or obj.id in params or obj.id not in local):
                    return True
        return False


def shared_writes(tree, lines, text):
    sh = _Shared(tree, text)
    todo = [(n, None, None, None) for n in tree.body]
    while todo:
        n, local, alias, params = todo.pop()
        if not isinstance(n, ast.stmt) or not any(n.lineno <= ln <= n.end_lineno for ln in lines):
            continue
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            l2, a2, p2 = sh.scope(n, alias or ())
            todo.extend((c, l2, a2, p2) for c in n.body)
            continue
        if isinstance(n, ast.ClassDef) or local is None:
            todo.extend((c, local, alias, params) for c in ast.iter_child_nodes(n) if isinstance(c, ast.stmt))
            continue
        if sh.writes(n, local, alias, params):
            return True
        todo.extend((c, local, alias, params) for c in ast.iter_child_nodes(n) if isinstance(c, ast.stmt))
    return False


_SRC_CACHE = {}


def _read_tree(full_path):
    r = _SRC_CACHE.get(full_path)
    if r is None:
        try:
            with open(full_path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            text = ""
        r = _SRC_CACHE[full_path] = [text, None]
    return r


def importers(mod, names, root_dir):
    leaf = mod.rsplit(".", 1)[-1]
    out = {}
    for dp, dns, fns in os.walk(os.path.join(SRC, root_dir)):
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in fns:
            if not fn.endswith(".py"):
                continue
            full_path = os.path.join(dp, fn)
            rel = os.path.relpath(full_path, SRC)
            entry = _read_tree(full_path)
            text = entry[0]
            if leaf not in text or (names is not None and not any(n in text for n in names)):
                continue
            if entry[1] is None:
                try:
                    entry[1] = ast.parse(text)
                except SyntaxError:
                    entry[1] = False
            tree = entry[1]
            if tree is False:
                continue
            pkg = modname_of(rel).split(".")
            if not rel.endswith("__init__.py"):
                pkg = pkg[:-1]
            used = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    base = pkg[: len(pkg) - node.level + 1] if node.level else []
                    m = ".".join(base + ([node.module] if node.module else []))
                    for a in node.names:
                        if m == mod:
                            used.add(a.name)
                        elif m + "." + a.name == mod:
                            used.add("*")
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name == mod or a.name.startswith(mod + "."):
                            used.add("*")
            if used and (names is None or "*" in used or used & names):
                out[rel] = used
    return out


def test_dependents(path, f, old_text, new_text):
    first = importers(modname_of(path), None, "tests")
    if not first:
        return set()
    try:
        names = top_names(parse_cached(old_text)) if old_text is not None else {}
        newn = set(top_names(parse_cached(new_text))) if new_text is not None else set()
    except SyntaxError:
        names, newn = {}, set()
    removed, anchors = changed_old_lines(f["hunks"])
    changed = removed | anchors
    touched = {n for n, (a, b) in names.items() if any(a <= ln <= b for ln in changed)} | (set(names) - newn)
    covered = set().union(*[range(a, b + 1) for a, b in names.values()]) if names else set()
    loose = any(ln not in covered for ln in changed)
    hit = {tf for tf, used in first.items() if loose or "*" in used or used & touched or not names}
    todo = list(hit)
    while todo:
        tf = todo.pop()
        for g in importers(modname_of(tf), None, "tests"):
            if g not in hit:
                hit.add(g)
                todo.append(g)
    hit.discard(path)
    return hit


COOKIE = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*([-\w.]+)")


def _cookie(text):
    for line in text.split("\n", 2)[:2]:
        m = COOKIE.match(line)
        if m:
            return m[1]
    return None


def package_scanners(cov):
    out = set()
    for tf, nums in cov.by_file.items():
        try:
            text = _read_tree(os.path.join(SRC, tf))[0]
        except OSError:
            continue
        if "iter_modules(" in text or "walk_packages(" in text:
            out.update(nums)
    return out


_CLOSURE = []


def closure_hits(cov, hit):
    if not _CLOSURE:
        try:
            with gzip.open(os.path.join(HERE, "closure.json.gz"), "rt") as fh:
                _CLOSURE.append(json.load(fh))
        except OSError:
            _CLOSURE.append(None)
    m = _CLOSURE[0]
    if m is None:
        return None
    out = set()
    for n, tid in cov.ids.items():
        rec = m["tests"].get(tid)
        if rec is None or rec[3] or hit(m, rec):
            out.add(n)
    return out


def gone_dependents(old, cov):
    if not old.endswith(".py") or old.endswith("__init__.py"):
        return None
    mod, folder = modname_of(old), os.path.dirname(old)
    return closure_hits(cov, lambda m, rec: any(m["mods"][i] == mod for i in rec[0]) or any(m["fs"][i] in (old, folder) for i in rec[2]))


def _fn_head(node):
    return ast.dump(type(node)(**{**{k: getattr(node, k, None) for k in node._fields}, "body": []}))


def support_dependents(path, old_text, new_text, cov):
    if old_text is None or new_text is None:
        return None
    try:
        a, b = parse_cached(old_text), parse_cached(new_text)
    except SyntaxError:
        return None
    if len(a.body) != len(b.body):
        return None
    spans = []
    for x, y in zip(a.body, b.body):
        if ast.dump(x) == ast.dump(y):
            continue
        if not isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)) or type(x) is not type(y) or _fn_head(x) != _fn_head(y):
            return None
        if shared_writes(a, set(range(x.lineno, x.end_lineno + 1)), old_text) or shared_writes(b, set(range(y.lineno, y.end_lineno + 1)), new_text):
            return None
        spans.append((min([x.lineno] + [d.lineno for d in x.decorator_list]), x.end_lineno))

    def hit(m, rec):
        for i in rec[1]:
            f, _, ln = m["code"][i].rpartition(":")
            if f == path and any(lo <= int(ln) <= hi for lo, hi in spans):
                return True
        return False

    return closure_hits(cov, hit)


def _exported(tree):
    out = set(top_names(tree))
    if LAZYGONE and any(isinstance(n, ast.FunctionDef) and n.name == "__getattr__" for n in tree.body):
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
                out.update(n.value for n in ast.walk(node.value) if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.isidentifier())
    return out


def _plain_def(node, lazy):
    if not isinstance(node, ast.FunctionDef) or node.decorator_list:
        return False
    a = node.args
    if not all(isinstance(d, ast.Constant) for d in a.defaults + [d for d in a.kw_defaults if d is not None]):
        return False
    return lazy or (node.returns is None and all(x.annotation is None for x in a.posonlyargs + a.args + a.kwonlyargs + [a.vararg, a.kwarg] if x is not None))


def _inert_change(old_text, new_text):
    try:
        a, b = ast.parse(old_text), ast.parse(new_text)
    except (SyntaxError, ValueError):
        return False
    if any(isinstance(n, ast.ImportFrom) and any(x.name == "*" for x in n.names) for n in a.body):
        return False
    da = [ast.dump(n) for n in a.body]
    lazy = any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(x.name == "annotations" for x in n.names) for n in b.body)
    taken = set(top_names(a)) | set(dir(builtins))
    i = 0
    for node in b.body:
        if i < len(da) and ast.dump(node) == da[i]:
            i += 1
        elif not _plain_def(node, lazy) or node.name in taken or node.name.startswith("__"):
            return False
        else:
            taken.add(node.name)
    return i == len(da)


def _risky(node):
    if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.Pass)):
        return False
    if isinstance(node, ast.ClassDef):
        return any(_risky(n) for n in node.body)
    if isinstance(node, ast.Expr):
        return not isinstance(node.value, ast.Constant)
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return not all(isinstance(x, (ast.Name, ast.Tuple, ast.List, ast.Starred, ast.expr_context)) for t in targets for x in ast.walk(t))
    if isinstance(node, ast.If):
        test = ast.dump(node.test)
        if "'__name__'" in test and "'__main__'" in test:
            return False
        return any(isinstance(n, ast.Call) for n in ast.walk(node.test)) or any(_risky(n) for n in node.body + node.orelse)
    return True


def _side_effects(text):
    if text is None:
        return []
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return []
    return sorted(ast.dump(n) for n in tree.body if _risky(n))


def _pytest_config(path, old_text, new_text):
    folder, base = os.path.split(path)
    if folder not in PYTEST_DIRS:
        return False
    if base in PYTEST_CFG:
        return True
    marker = {"setup.cfg": "[tool:pytest]", "pyproject.toml": "[tool.pytest"}.get(base)
    return bool(marker) and any(marker in (t or "") for t in (old_text, new_text))


def _candidates_for(f, old_text, new_text, cov, notes):
    path = f["path"]
    if PATHRULES and _pytest_config(path, old_text, new_text):
        notes.append("pytest-config")
        every = full(n for n in cov.idx_to_num if n is not None)
        FORCE_LIST.update(every)
        return every
    if path.startswith("sqlglot/") and path.endswith(".py") or CLOSURE and f["old"].startswith("sqlglot/") and f["old"].endswith(".py"):
        if f["deleted"] or (f["old"] and f["old"] != path):
            gone = gone_dependents(f["old"], cov) if CLOSURE else None
            if gone is not None:
                notes.extend(("closure-gone:%d" % len(gone), "gone:" + f["old"], "gone:" + path))
                return merge(merge(full(gone), full(module_test_files(path, cov))), full(package_scanners(cov)))
            notes.append("deleted-or-renamed")
            return full(n for n in cov.idx_to_num if n is not None)
        if new_text is not None:
            try:
                parse_cached(new_text)
            except SyntaxError:
                notes.append("new-unparsable")
                return full(n for n in cov.idx_to_num if n is not None)
            if _cookie(new_text) != _cookie(old_text or ""):
                try:
                    ast.parse(new_text.encode("utf-8", "surrogateescape"))
                except (SyntaxError, LookupError, UnicodeError, ValueError):
                    notes.append("bad-coding")
                    return full(n for n in cov.idx_to_num if n is not None)
        extra = {}
        if old_text is not None and new_text is not None:
            try:
                gone = _exported(parse_cached(old_text)) - _exported(parse_cached(new_text))
            except SyntaxError:
                gone = set()
            if gone:
                mod = modname_of(path)
                if importers(mod, gone, "sqlglot"):
                    notes.append("toplevel-gone-internal")
                    return full(n for n in cov.idx_to_num if n is not None)
                hit = importers(mod, gone, "tests")
                if hit:
                    notes.append("toplevel-gone:%d" % len(hit))
                    extra = full(n for tf in hit for n in cov.by_file.get(tf, []))
        if old_text is not None and new_text is not None:
            res = module_resolver(path)
            DOC[0] = DOCSTRIP and not path.startswith("sqlglot/typing/")
            if FASTNOOP:
                same = ast_noop(old_text, new_text, f["hunks"], res)
            else:
                a, b = strip_ast(old_text, res), strip_ast(new_text, res)
                same = a is not None and a == b
            DOC[0] = False
            if same:
                notes.append("ast-noop")
                notes.append("noop:" + path)
                return extra
        if old_text is None:
            notes.append("newfile")
            return merge(merge(cov.tests_touching_file(path), full(module_test_files(path, cov))), full(package_scanners(cov)))
        try:
            units = Units(old_text, {ln for h in f["hunks"] for part in changed_old_lines([h]) for ln in part})
        except SyntaxError:
            notes.append("old-unparsable")
            return merge(cov.tests_touching_file(path), extra)
        out = {}
        importtime = False
        at_import = set(cov.files.get(path, {}).get("import", ())) if IMPORTBODY else set()
        body = False
        try:
            new_units = Units(new_text, added_new_lines(f["hunks"]))
        except SyntaxError:
            new_units = None
        lam = LAMBDAS and new_units is not None and lambda_only(path, units, new_units, f["hunks"])
        if lam:
            notes.append("lambda-only")
        site = CACHE_SITES.get(path)
        if site:
            touched = {ln for h in f["hunks"] for part in changed_old_lines([h]) for ln in part}
            if any(a <= ln <= b for a, b in site["lazy"] for ln in touched):
                notes.append("lazy-getattr")
                every = full(n for n in cov.idx_to_num if n is not None)
                FORCE_LIST.update(every)
                return every
            for fill, readers in site["memo"]:
                if any(a <= ln <= b for a, b in fill for ln in touched):
                    notes.append("memo-site")
                    merge(out, full(cov.tests_for_lines(path, readers)))
        for h in f["hunks"]:
            hr, ha = changed_old_lines([h])
            found = {ln: units.unit_for(ln) for ln in sorted(hr | ha)}
            gap = GAPS and not any(found.values())
            for ln, u in found.items():
                for _, first, last, runtime, node in [u] if u else units.gap_units(ln) if gap else ():
                    merge(out, cov.tests_for_lines(path, range(first, last + 1)))
                    if not runtime and not (lam and isinstance(node, ast.Lambda)):
                        importtime = True
                    elif runtime and not at_import.isdisjoint(range(first, last + 1)):
                        body = True
        for ln in added_new_lines(f["hunks"]) if new_units is not None else ():
            u = new_units.unit_for(ln)
            if u is None or u[3] or lam and isinstance(u[4], ast.Lambda):
                continue
            importtime = True
            notes.append("newtop:" + path)
            if not isinstance(u[4], (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Assign, ast.AnnAssign, ast.Import, ast.ImportFrom)) or isinstance(u[4], ast.ClassDef) and u[4].decorator_list:
                notes.append("toplevel-exec")
                merge(out, cov.tests_touching_file(path))
                merge(out, full(module_test_files(path, cov)))
        if SHARED and new_units is not None and shared_writes(parse_cached(new_text), set(added_new_lines(f["hunks"])), new_text):
            notes.append("shared-write")
            return full(n for n in cov.idx_to_num if n is not None)
        if body:
            notes.append("import-body")
        if importtime or body:
            notes.append("importtime")
            if not IMPORTT:
                merge(out, cov.tests_touching_file(path))
                merge(out, full(module_test_files(path, cov)))
        return merge(out, extra)
    if path.startswith("tests/") and path.endswith(".py"):
        if os.path.basename(path).startswith("test_"):
            notes.append("testfile")
            if TESTSIDE and _side_effects(old_text) != _side_effects(new_text):
                notes.append("test-side-effect")
                every = full(n for n in cov.idx_to_num if n is not None)
                FORCE_LIST.update(every)
                return every
            out = set(cov.by_file.get(path, []))
            if any(tag == "+" and "xfail" in line for h in f["hunks"] for tag, line in h["lines"]):
                notes.append("xfail")
                FORCE_LIST.update(out)
            hit = test_dependents(path, f, old_text, new_text)
            if hit:
                notes.append("test-dependents:%d" % len(hit))
                out.update(n for tf in hit for n in cov.by_file.get(tf, []))
            return out
        if INERT and old_text is not None and new_text is not None and _inert_change(old_text, new_text):
            notes.append("test-support-inert")
            return set()
        if INERT and os.path.basename(path) != "__init__.py" and not importers(modname_of(path), None, "tests") and not importers(modname_of(path), None, "sqlglot"):
            notes.append("test-support-unimported")
            return set()
        dep = support_dependents(path, old_text, new_text, cov) if CLOSURE and f["old"] == path and not f["deleted"] and not f["new_file"] else None
        if dep is not None:
            notes.append("closure-support:%d" % len(dep))
            return dep
        notes.append("test-support")
        return {n for p, ns in cov.by_file.items() for n in ns}
    if path.startswith("tests/"):
        if path in cov.fixtures:
            notes.append("fixture")
            out = {cov.idx_to_num[i] for i in cov.fixtures[path] if cov.idx_to_num[i] is not None}
            extra = class_setup_readers(path, cov, fixture_loads(path, new_text))
            if extra - out:
                notes.append("setupclass")
            res = full(out | extra)
            idx = changed_query_indices(path, old_text, new_text) if TPCQ else None
            if idx is not None:
                for n in (extra | out) if TPCQ2 else extra - out:
                    keys = query_unit_keys(cov, n, idx, os.path.basename(os.path.dirname(path)))
                    if keys is not None:
                        res[n] = keys
                        FRACTION_OK.add(n)
                notes.append("queries:%d" % len(idx))
            return res
        notes.append("unmapped-fixture")
        base = os.path.basename(path)
        out = set()
        for tf, nums in cov.by_file.items():
            try:
                with open(os.path.join(SRC, tf), encoding="utf-8") as fh:
                    if base in fh.read() or os.path.splitext(base)[0] in fh.read():
                        out.update(nums)
            except OSError:
                pass
        return out
    notes.append("other:" + path)
    if PATHRULES and path.startswith("sqlglotc/"):
        r = set(cov.by_file.get("tests/test_sqlglotc.py", []))
        FORCE_LIST.update(r)
        return r
    return set()


_FILLER = re.compile(r"cache|memo|lru|global |nonlocal |setdefault|__dict__|setattr|_registry", re.I)
_CLASSTIME = {"__reduce__", "__reduce_ex__", "__getstate__", "__setstate__", "__getnewargs__", "__getnewargs_ex__", "__copy__", "__deepcopy__", "__init_subclass__", "__set_name__", "__class_getitem__", "__del__"}
_WARM = []
_LEAN = []


def _lean_meta():
    if not _LEAN:
        try:
            with open(os.path.join(HERE, "tpc", "lean.json")) as fh:
                _LEAN.append(json.load(fh))
        except (OSError, ValueError):
            _LEAN.append({})
    return _LEAN[0]


def _outer_fns(nodes, pre=""):
    out = []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append((pre + node.name, node))
        elif isinstance(node, ast.ClassDef):
            out.extend(_outer_fns(node.body, pre + node.name + "."))
        elif not isinstance(node, ast.Lambda):
            out.extend(_outer_fns(ast.iter_child_nodes(node), pre))
    return out


def _fn_at(fns, ln):
    for q, fn in fns:
        if fn.body[0].lineno <= ln <= fn.end_lineno:
            return q, fn
    return None


def lean_gate(notes, patched, old_by, hunks_by):
    if any(x != "ast-noop" and not x.startswith(("noop:", "memo:")) for x in notes):
        return False
    if not _WARM:
        with open(os.path.join(HERE, "warmmap.json")) as fh:
            _WARM.append({p: set(v) for p, v in json.load(fh).items()})
    live = 0
    for rel, new in patched.items():
        old = old_by.get(rel)
        if new is None or old is None or not rel.endswith(".py"):
            return False
        if "noop:" + rel in notes:
            continue
        if not (rel.startswith("sqlglot/executor/") or rel == "sqlglot/planner.py") or rel not in _WARM[0]:
            return False
        live += 1
        warm = _WARM[0][rel]
        removed, anchors = changed_old_lines(hunks_by[rel])
        old_fns = _outer_fns(parse_cached(old).body)
        by_q = dict(old_fns)
        for text, lines, fns in ((old, removed | anchors, old_fns), (new, new_side_lines(hunks_by[rel]), None)):
            src = text.split("\n")
            fns = fns or _outer_fns(parse_cached(text).body)
            for ln in lines:
                hit = _fn_at(fns, ln)
                if hit is None:
                    if 0 < ln <= len(src) and src[ln - 1].strip():
                        return False
                    continue
                q, fn = hit
                base = by_q.get(q)
                if base is None or any(part in _CLASSTIME for part in q.split(".")):
                    return False
                if warm & set(range(base.body[0].lineno, base.end_lineno + 1)):
                    return False
                first = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
                if _FILLER.search("\n".join(src[first - 1:fn.end_lineno])):
                    return False
    return live > 0


def lean_cost():
    d = memo_data()
    if d is None or len(d["keyed"].get("ds", {})) != len(d["pre"].get("ds", {})):
        return None
    pre, run = d["pre"]["ds"], d["run"]["ds"]
    return {k: pre[k] + run.get(k, 0) for k in pre}


def lean_need(cov, tp, patched, hunks_by, notes, cpu):
    lines = memo_data()["lines"].get("ds", {})
    need = []
    for rel in patched:
        if "noop:" + rel in notes:
            continue
        removed, anchors = changed_old_lines(hunks_by[rel])
        for ln in sorted(removed | anchors):
            keys = cov.tests_for_lines(rel, [ln]).get(tp, ())
            qs = set(cpu) if keys is None else {k for k in keys if k in cpu}
            qs |= set(lines.get(rel, {}).get(ln, ())) & set(cpu)
            if qs:
                need.append(qs)
    return need


def lean_order(need, cpu, chosen=None):
    pool = set(cpu) if chosen is None else set(chosen)
    hot = set().union(*need) & pool if need else set()
    seed = ["f:%d" % i for i in LEAN_SEED]
    return [int(k[2:]) for k in sorted(pool, key=lambda k: (seed.index(k) if k in seed else len(seed), k not in hot, cpu[k], int(k[2:])))]


def canary_pick(need, cpu, k):
    live = sorted(cpu, key=lambda q: (cpu[q], int(q[2:])))
    chosen = [q for q in ("f:%d" % i for i in LEAN_SEED) if q in cpu]
    extra = 0
    while extra < k:
        open_ = [s for s in need if not s & set(chosen)]
        if not open_:
            break
        chosen.append(max(live, key=lambda q: (sum(1 for s in open_ if q in s), -cpu[q], -int(q[2:]))))
        extra += 1
    return chosen


def _materialize(dst, src):
    os.makedirs(dst)
    if os.path.isdir(src):
        for e in os.listdir(src):
            os.symlink(os.path.join(src, e), os.path.join(dst, e))


def build_overlay(root, patched):
    if not os.path.isdir(root):
        _materialize(root, SRC)
    for rel, content in patched.items():
        parts = rel.split("/")
        dst, src = root, SRC
        for part in parts[:-1]:
            dst, src = os.path.join(dst, part), os.path.join(src, part)
            if os.path.islink(dst):
                os.unlink(dst)
                _materialize(dst, src)
            elif not os.path.exists(dst):
                _materialize(dst, src)
        target = os.path.join(dst, parts[-1])
        if os.path.lexists(target):
            os.unlink(target)
        if content is not None:
            with open(target, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
                fh.write(content)


SLOTS = []


def _clean_view(d, s):
    with os.scandir(d) as it:
        entries = list(it)
    if sorted(e.name for e in entries) != sorted(os.listdir(s)):
        return False
    return all(e.is_symlink() or (e.is_dir(follow_symlinks=False) and _clean_view(e.path, os.path.join(s, e.name))) for e in entries)


def release_slot(root, patched):
    try:
        for rel in patched:
            target, src = os.path.join(root, rel), os.path.join(SRC, rel)
            if os.path.lexists(target):
                os.unlink(target)
            if os.path.lexists(src):
                os.symlink(src, target)
        if _clean_view(root, SRC):
            SLOTS.append(root)
            return
    except OSError:
        pass
    rmtree(root)


def rmtree(path):
    if not os.path.lexists(path):
        return
    if os.path.islink(path) or not os.path.isdir(path):
        os.unlink(path)
        return
    for e in os.listdir(path):
        rmtree(os.path.join(path, e))
    os.rmdir(path)


class _LazyPandasTesting(types.ModuleType):
    def _real(self):
        if sys.modules.get("pandas.testing") is self:
            del sys.modules["pandas.testing"]
        return importlib.import_module("pandas.testing")

    def assert_frame_equal(self, *a, **k):
        return self._real().assert_frame_equal(*a, **k)

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return getattr(self._real(), name)


def preimport(libs=True):
    import concurrent.futures
    import unittest
    import unittest.mock
    import multiprocessing
    import tracemalloc
    import csv
    import datetime
    import decimal
    import gc
    for name in ("duckdb", "numpy", "pandas", "pandas.testing") if libs else ():
        try:
            __import__(name)
        except Exception:
            pass


class LazyFuture:
    def __init__(self, fn, args, kwargs):
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.state = None

    def _force(self):
        if self.state is None:
            try:
                args, kwargs = pickle.loads(pickle.dumps((self.args, self.kwargs)))
                self.state = (True, pickle.loads(pickle.dumps(self.fn(*args, **kwargs))))
            except BaseException as e:
                self.state = (False, e)
        return self.state

    def result(self, timeout=None):
        ok, v = self._force()
        if ok:
            return v
        raise v

    def exception(self, timeout=None):
        ok, v = self._force()
        return None if ok else v

    def done(self):
        return True

    def cancel(self):
        return False

    def cancelled(self):
        return False

    def add_done_callback(self, fn):
        fn(self)


class SyncExecutor:
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kw):
        if initializer:
            initializer(*pickle.loads(pickle.dumps(initargs)))

    def submit(self, fn, *args, **kwargs):
        return LazyFuture(fn, args, kwargs)

    def map(self, fn, *iterables, **kw):
        return map(fn, *iterables)

    def shutdown(self, wait=True, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.shutdown()
        return False


def lazy_wait(fs, timeout=None, return_when=None):
    import concurrent.futures
    return concurrent.futures._base.DoneAndNotDoneFutures(set(fs), set())


def lazy_as_completed(fs, timeout=None):
    return iter(list(fs))


def install_futures():
    import concurrent.futures
    concurrent.futures.ProcessPoolExecutor = SyncExecutor
    concurrent.futures.wait = lazy_wait
    concurrent.futures.as_completed = lazy_as_completed


CHILD_LAZY = False
CHILD_PATCHED = []
_EDGES = []


def load_edges():
    if not _EDGES:
        try:
            with open(os.path.join(HERE, "edges.json")) as fh:
                e = json.load(fh)
            _EDGES.append((set(e["nodes"]), e["rev"]))
        except Exception:
            _EDGES.append(None)
    return _EDGES[0]


def partial_purge(root):
    edges = load_edges()
    rels = CHILD_PATCHED
    if edges is None or not rels or not all(r.endswith(".py") and r.startswith(("sqlglot/", "tests/")) for r in rels):
        return None
    nodes, rev = edges
    ours = {n for n, m in sys.modules.items() if m is not None and (n == "sqlglot" or n.startswith(("sqlglot.", "tests")))}
    if ours - nodes:
        return None
    if not all(os.path.exists(os.path.join(root, r)) and os.path.exists(os.path.join(SRC, r)) for r in rels):
        return None
    gone = set()
    dead = {modname_of(r) for r in rels}
    todo = list(dead)
    while todo:
        for h in rev.get(todo.pop(), ()):
            if h not in dead:
                dead.add(h)
                todo.append(h)
    mods = {id(sys.modules[n]): n for n in ours}
    fns = (type, types.FunctionType)
    cut = []
    for n in ours - dead:
        g = vars(sys.modules[n])
        lazy = "__getattr__" in g
        for k, v in g.items():
            w = mods.get(id(v)) or (getattr(v, "__module__", None) if isinstance(v, fns) else None)
            if w in dead:
                if not (w == n + "." + k and w not in gone and isinstance(v, types.ModuleType)) and not lazy:
                    return None
                cut.append((g, k))
    for g, k in cut:
        del g[k]
    dd = sys.modules.get("sqlglot.dialects.dialect")
    if dd is not None and "sqlglot.dialects.dialect" not in dead:
        reg = dd._Dialect._classes
        for k in [k for k, v in reg.items() if getattr(v, "__module__", None) in dead]:
            del reg[k]
    pre = SRC + "/"
    for n in ours - dead:
        m = sys.modules[n]
        path = getattr(m, "__path__", None)
        if path is not None:
            m.__path__ = [os.path.join(root, x[len(pre):]) if x.startswith(pre) else x for x in path]
            if m.__spec__ is not None and m.__spec__.submodule_search_locations is not None:
                m.__spec__.submodule_search_locations = m.__path__
        for v in list(vars(m).values()) if n.startswith("tests") else ():
            if isinstance(v, type) and vars(v).get("_prewarmed"):
                v.setUpClass = classmethod(lambda cls: None)
                v.tearDownClass = classmethod(lambda cls: None)
    for n in dead & ours:
        del sys.modules[n]
    return sorted((dead & ours) - gone - {n for n in dead if n.startswith("tests")}, key=lambda n: n.count("."))


CHILD_MEMO = None
_MEMO = []
MEMO_TEST = "tests/test_executor.py::TestExecutor::test_execute_tpcds"
MEMO_BAD = ("shared-write", "toplevel", "newfile", "deleted-or-renamed", "unparsable", "bad-coding", "error:", "itf-error")
MEMO_IMPORT = ("importtime", "newtop:", "itf")


def memo_data():
    if not _MEMO:
        try:
            with open(os.path.join(HERE, "tpc", "memo.pkl"), "rb") as fh:
                d = pickle.load(fh)
            d["exec"] = set(map(tuple, d["exec"]))
            _MEMO.append(d)
        except (OSError, pickle.UnpicklingError, EOFError, KeyError):
            _MEMO.append(None)
    return _MEMO[0]


def memo_blobs(touched):
    d = memo_data()
    gone = {d["keyed"]["ds"][k] for k in touched if k in d["keyed"]["ds"]}
    return {k: v for k, v in d["memo"].get("ds", {}).items() if k not in gone}


def memo_state():
    d = memo_data()
    with open(os.path.join(HERE, "tpc", "state.pkl"), "rb") as fh:
        return (set(d["names"]), pickle.load(fh))


def _code_spans(code, out):
    lines = [ln for _, _, ln in code.co_lines() if ln is not None]
    out.append((code.co_qualname, code.co_firstlineno, max(lines + [code.co_firstlineno])))
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            _code_spans(c, out)
    return out


def memo_ok(patched, hunks_by, old_by, notes, warm_lines):
    d = memo_data()
    if d is None or any(n.startswith(MEMO_BAD) for n in notes):
        return False
    import zygote
    mode = "state" if any(n.startswith(MEMO_IMPORT) for n in notes) else "plain"
    touched = set()
    for rel, content in patched.items():
        old = old_by.get(rel)
        if "noop:" + rel in notes:
            continue
        if rel.startswith("sqlglot/") and rel.endswith(".py"):
            if content is None or old is None:
                return False
            removed, anchors = changed_old_lines(hunks_by[rel])
            changed = removed | anchors
            try:
                tree = parse_cached(old)
                spans = _code_spans(compile(old, os.path.join(SRC, rel), "exec"), [])
            except (SyntaxError, ValueError):
                return False
            if changed & warm_lines.get(rel, set()) or not all(zygote.in_body(tree.body, ln) for ln in changed):
                mode = "state"
            hit = set()
            removed, inserts = _replaced_lines(hunks_by[rel])
            for q, first, last in spans:
                if (rel, q, first) in d["exec"]:
                    inside = {ln for ln in changed if first <= ln <= last}
                    if inside and (q == "<module>" or not all(zygote.in_body(tree.body, ln) for ln in inside)):
                        return False
                    hit |= inside
            if hit:
                seen = d["lines"].get("ds", {}).get(rel, {})
                ran = d["anywhere"].get(rel, set())
                stmts = [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]
                check = set()
                for ln in hit & removed:
                    for a, b in _stmt_span(stmts, ln):
                        check.update(range(a, b + 1))
                for ln in inserts:
                    if ln in hit or ln - 1 in hit:
                        check |= _insert_lines(stmts, ln)
                for x in check:
                    q = seen.get(x)
                    if q:
                        touched |= q
                    elif x in ran:
                        touched |= set(d["pre"]["ds"])
        elif rel == "tests/fixtures/optimizer/tpc-ds/tpc-ds.sql":
            if content is None or old is None:
                return False
        elif rel.startswith("tests/fixtures/") and "/tpc-" not in rel:
            continue
        elif rel.startswith("tests/") and os.path.basename(rel).startswith("test_") and rel.endswith(".py") and rel != "tests/test_executor.py":
            continue
        else:
            return False
    if mode == "state" and not os.path.exists(os.path.join(HERE, "tpc", "state.pkl")):
        return False
    return mode, touched


def _replaced_lines(hunks):
    removed, inserts = set(), set()
    for h in hunks:
        ln = h["old_start"] if h["old_len"] else h["old_start"] + 1
        repl = False
        for tag, _ in h["lines"]:
            if tag == "-":
                removed.add(ln)
                ln += 1
                repl = True
            elif tag == "+":
                if not repl:
                    inserts.add(ln)
            else:
                ln += 1
                repl = False
    return removed, inserts


def _insert_lines(stmts, ln):
    funcs = [n for n in stmts if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.lineno < ln <= n.end_lineno + 1]
    if not funcs:
        return {ln - 1, ln}
    f = max(funcs, key=lambda n: n.lineno)
    starts = {n.lineno for n in stmts}
    if ln > f.end_lineno or ln not in starts:
        return set(range(f.lineno, f.end_lineno + 1))
    out = set()
    for a, b in _stmt_span(stmts, ln):
        out.update(range(a, b + 1))
    prev = max((n.end_lineno for n in stmts if f.lineno < n.lineno and n.end_lineno < ln), default=None)
    for n in stmts:
        if prev is not None and n.end_lineno == prev and f.lineno < n.lineno:
            for a, b in _stmt_span(stmts, n.lineno):
                out.update(range(a, b + 1))
    return out


def _stmt_span(stmts, ln):
    inner = [n for n in stmts if n.lineno <= ln <= n.end_lineno]
    if not inner:
        return [(ln, ln)]
    best = max(inner, key=lambda n: (n.lineno, -n.end_lineno))
    blocks = [b for f in ("body", "orelse", "finalbody", "handlers", "cases") for b in [getattr(best, f, None)] if b]
    if not blocks:
        return [(best.lineno, best.end_lineno)]
    first = min(b[0].lineno for b in blocks)
    if ln < first:
        return [(best.lineno, first - 1)]
    return [(best.lineno, best.end_lineno)]


def state_diff(names, pristine, checked):
    import memo
    mods = {m: v for m, v in sys.modules.items() if m not in checked and (m == "sqlglot" or m.startswith("sqlglot.")) and v is not None}
    if not mods:
        return False
    checked.update(mods)
    entries, keys, lazy = pristine["entries"], pristine["keys"], pristine["lazy"]
    known = {k[0] for k in keys}
    if any(m not in known for m in mods):
        return True
    now = memo.state(names, mods)
    for k, h in now.items():
        p = entries.get(k)
        if h is None or (p != h if type(h) is not frozenset or type(p) is not frozenset else not h <= p):
            if DEBUG:
                log("state differs", k)
            return True
    have = memo.keysets(mods)
    for o, ks in keys.items():
        if o[0] in mods and o in have and ks - have[o] - lazy.get(o, frozenset()):
            if DEBUG:
                log("state keys missing", o, sorted(ks - have[o] - lazy.get(o, frozenset()))[:5])
            return True
    return False


def install_memo(blobs, drop, check, strict, ustate):
    import sqlglot.executor as ex
    sys.path.insert(0, HERE)
    import memo
    spent = [0.0]
    checked = set()
    bad = []

    def lookup(d, expression, raw):
        if ustate.get("tid") != MEMO_TEST:
            return None
        if check is not None and not bad and state_diff(check[0], check[1], checked):
            bad.append(1)
        hit = blobs.get(d) if d and not bad else None
        if hit is None and strict:
            if spent[0] > strict or bad:
                ustate["skipped"] = False
                raise RuntimeError("memo budget")
            hooks.t0 = time.process_time()
        return hit

    def leave():
        if getattr(hooks, "t0", None) is not None:
            spent[0] += time.process_time() - hooks.t0
            hooks.t0 = None

    hooks = memo.Hooks(ex, lookup, None, leave, drop)
    hooks.install()
STMT_OF = {}
_STMT_TREES = {}
_STMT_LINES = {}


def _stmt_tree(path):
    t = _STMT_TREES.get(path)
    if t is None:
        with open(path, encoding="utf-8") as fh:
            t = _STMT_TREES[path] = ast.parse(fh.read())
    return t


def _stmt_lines(path):
    t = _STMT_LINES.get(path)
    if t is None:
        with open(path, encoding="utf-8") as fh:
            t = _STMT_LINES[path] = fh.readlines()
    return t


def _code_end(code):
    end = max((p[1] for p in code.co_positions() if p[1] is not None), default=code.co_firstlineno)
    return max([end] + [_code_end(c) for c in code.co_consts if isinstance(c, types.CodeType)])


def _stmt_node(path, cls, meth, code):
    line = code.co_firstlineno
    if SEGPARSE and code.co_qualname == cls + "." + meth and code.co_filename.endswith("/" + path):
        try:
            lines = _stmt_lines(os.path.join(SRC, path))
            end = _code_end(code)
            indent = len(lines[line - 1]) - len(lines[line - 1].lstrip())
            rest = next((x for x in lines[end:] if x.strip() and not x.lstrip().startswith("#")), "")
            if rest and len(rest) - len(rest.lstrip()) > indent:
                import inspect
                end = line - 1 + len(inspect.getblock(lines[line - 1:]))
            tree = ast.parse("\n" * (line - 2) + "class _:\n" + "".join(lines[line - 1:end]))
            f = tree.body[0].body[0]
            if len(tree.body) == 1 and len(tree.body[0].body) == 1 and isinstance(f, ast.FunctionDef) and f.name == meth:
                return None if f.decorator_list or f.lineno != line else f
        except Exception:
            pass
    node = None
    for c in _stmt_tree(os.path.join(SRC, path)).body:
        if isinstance(c, ast.ClassDef) and c.name == cls:
            for f in c.body:
                if isinstance(f, ast.FunctionDef) and f.name == meth and not f.decorator_list and f.lineno == line:
                    node = f
    return node


def _scan(node):
    ids, stores = set(), set()
    stack = [node]
    while stack:
        n = stack.pop()
        if type(n) is ast.Name:
            ids.add(n.id)
            if isinstance(n.ctx, (ast.Store, ast.Del)):
                stores.add(n.id)
        for f in n._fields:
            v = getattr(n, f, None)
            if type(v) is list:
                stack.extend(x for x in v if isinstance(x, ast.AST))
            elif isinstance(v, ast.AST):
                stack.append(v)
    return ids, stores


def _skippable(st, ids, local):
    if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
        return False
    f = st.value.func
    if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "self"):
        return False
    return not ids & local


def stmt_filter(case, tid, allowed, patched):
    smap = STMT_OF.get(tid)
    if smap is None or "" in allowed or any(k.startswith("f:") or "#" in k for k in allowed):
        return False
    path, cls, meth = tid.split("::")
    if path in patched:
        return False
    fn = getattr(type(case), meth, None)
    code = getattr(fn, "__code__", None)
    if code is None or code.co_freevars or "super" in code.co_names or "__class__" in code.co_names:
        return False
    node = _stmt_node(path, cls, meth, code)
    if node is None:
        return False
    need = {int(k[2:]) for k in allowed if k.startswith("t:")} | {smap[k] for k in allowed if k in smap}
    scans = [_scan(st) for st in node.body]
    local = {a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg) and a.arg != "self"}
    local |= {n for part in (node.args, node.returns) if part is not None for n in _scan(part)[1]}
    local |= {n for _, stores in scans for n in stores}
    body = []
    for i, st in enumerate(node.body):
        if i in need or not _skippable(st, scans[i][0], local):
            body.append(st)
        else:
            body.append(ast.copy_location(ast.Pass(), st))
    new = ast.FunctionDef(name=node.name, args=node.args, body=body, decorator_list=[], returns=node.returns, type_comment=None, type_params=[])
    ast.copy_location(new, node)
    mod = ast.Module(body=[new], type_ignores=[])
    ns = {}
    exec(compile(mod, code.co_filename, "exec"), sys.modules[type(case).__module__].__dict__, ns)
    setattr(case, meth, types.MethodType(ns[meth], case))
    return True


_TPC_CACHE = {}


class LazyTables(dict):
    def __init__(self, kind, directory=None, schema=None, items=()):
        super().__init__(items)
        self.kind = kind
        if directory is not None:
            _TPC_CACHE.setdefault(("meta", kind), (directory, schema))

    def __missing__(self, name):
        key = (self.kind, name)
        if key not in _TPC_CACHE:
            directory, schema = _TPC_CACHE[("meta", self.kind)]
            if name not in schema:
                raise KeyError(name)
            _TPC_CACHE[key] = _tpc_table(directory, name, schema[name])
        self[name] = _TPC_CACHE[key]
        return self[name]

    def __reduce__(self):
        return (LazyTables, (self.kind, None, None, list(self.items())))


def build_tpc_cache(path):
    sys.path.insert(0, SRC)
    os.chdir(SRC)
    import tests.test_executor as te
    te.TestExecutor.setUpClass()
    k = te.TestExecutor
    ref = {}
    for kind, conn, sqls, tables in (("h", k.tpch_conn, k.tpch_sqls, k.tpch_tables), ("ds", k.tpcds_conn, k.tpcds_sqls, k.tpcds_tables)):
        for name, table in tables.items():
            with open(os.path.join(path, "%s.%s.m" % (kind, name)), "wb") as fh:
                marshal.dump(table.rows, fh)
        out = ref[kind] = {}
        for _, sql, optimized in sqls:
            for q in (sql, optimized) if kind == "h" else (sql,):
                d = te.transpile(q, write="duckdb")[0]
                try:
                    a, b = conn.execute(d).fetchdf(), conn.execute(d).fetchdf()
                except Exception:
                    continue
                blob = pickle.dumps(a)
                if a.equals(b) and blob == pickle.dumps(b):
                    out[d] = blob
    lean = lean_reference(te, k)
    with open(os.path.join(path, "lean.pkl"), "wb") as fh:
        pickle.dump(lean, fh)
    with open(os.path.join(path, "lean.json"), "w") as fh:
        json.dump({"optfiles": lean["optfiles"]} if lean else {}, fh)
    with open(os.path.join(path, "ref.pkl"), "wb") as fh:
        pickle.dump(ref, fh)


def _outcome(run):
    try:
        r = run()
        return ("ok", r.columns, r.rows)
    except BaseException as e:
        return ("err", type(e).__name__, re.sub(r"0x[0-9a-fA-F]+|\d{6,}", "#", str(e)))


def lean_reference(te, k):
    import sqlglot.executor as X
    real = X.optimize
    opt, files = {}, set()

    def prof(frame, event, arg):
        if event == "call":
            files.add(frame.f_code.co_filename)

    def record(*a, **kw):
        key = pickle.dumps((a, kw))
        sys.setprofile(prof)
        try:
            out = real(*a, **kw)
        finally:
            sys.setprofile(None)
        opt[key] = pickle.dumps(out)
        return out

    queries = {}
    X.optimize = record
    try:
        for i, (meta, sql, _) in enumerate(k.tpcds_sqls):
            if not meta.get("execute"):
                continue
            queries[i] = sql
            expression = pickle.loads(pickle.dumps(te.parse_one(sql)))
            te.execute(expression, schema=te.TPCDS_SCHEMA, tables={t.name: k.tpcds_tables[t.name] for t in te.find_tables(expression)})
    finally:
        X.optimize = real
    root = os.path.abspath(SRC) + os.sep
    return {"schema": te.TPCDS_SCHEMA, "hschema": te.TPCH_SCHEMA, "queries": queries, "opt": opt, "optfiles": sorted(os.path.relpath(f, root) for f in files if os.path.abspath(f).startswith(root) and os.path.isfile(f))}


def _same(a, b):
    if type(a) is not type(b):
        return False
    if type(a) in (tuple, list):
        return len(a) == len(b) and all(map(_same, a, b))
    if type(a) is float and a != a:
        return b != b
    return a == b and repr(a) == repr(b)


def _tpc_table(directory, table, columns):
    te = sys.modules["tests.test_executor"]
    kind = "h" if directory == te.DIR_TPCH else "ds"
    if TPCREF:
        try:
            with open(os.path.join(HERE, "tpc", "%s.%s.m" % (kind, table)), "rb") as fh:
                return te.Table(columns=columns, rows=marshal.loads(fh.read()))
        except OSError:
            pass
    file_name = f"{directory}{table}.csv.gz"
    reader = te.csv.reader(te.open_file(file_name), delimiter="|")
    rows = []
    ctypes = []
    next(reader)
    for row in reader:
        if not ctypes:
            for i, v in enumerate(row):
                try:
                    ctypes.append(type(te.ast.literal_eval(v)))
                except (ValueError, SyntaxError):
                    ctypes.append(str)
        rows.append(tuple(None if (t is not str and v == "") else t(v) for t, v in zip(ctypes, row)))
    return te.Table(columns=columns, rows=rows)


class RefConn:
    def __init__(self, kind, directory, schema):
        self.kind, self.directory, self.schema = kind, directory, schema
        self.conn = None

    def execute(self, sql, *a):
        if TPCREF and not a:
            blob = _tpc_ref().get(self.kind, {}).get(sql)
            if blob is not None:
                return RefResult(blob)
        if self.conn is None:
            te = sys.modules["tests.test_executor"]
            self.conn = te.duckdb.connect()
            for table, columns in self.schema.items():
                file_name = f"{self.directory}{table}.csv.gz"
                self.conn.execute(
                    f"""
                    CREATE VIEW {table} AS
                    SELECT *
                    FROM READ_CSV('{file_name}', delim='|', header=True, columns={columns})
                    """
                )
        return self.conn.execute(sql, *a)

    def close(self):
        if self.conn is not None:
            self.conn.close()


class RefResult:
    def __init__(self, blob):
        self.blob = blob

    def fetchdf(self):
        return pickle.loads(self.blob)


_REF = []


def _tpc_ref():
    if not _REF:
        try:
            with open(os.path.join(HERE, "tpc", "ref.pkl"), "rb") as fh:
                _REF.append(pickle.load(fh))
        except OSError:
            _REF.append({})
    return _REF[0]


def _lazy_tpc_setup(cls):
    te = sys.modules[cls.__module__]
    cls.tpch_conn = RefConn("h", te.DIR_TPCH, te.TPCH_SCHEMA)
    cls.tpcds_conn = RefConn("ds", te.DIR_TPCDS, te.TPCDS_SCHEMA)
    cls.tpch_tables = LazyTables("h", te.DIR_TPCH, te.TPCH_SCHEMA)
    cls.tpcds_tables = LazyTables("ds", te.DIR_TPCDS, te.TPCDS_SCHEMA)
    cls.cache = {}
    cls.tpch_sqls = list(te.load_sql_fixture_pairs("optimizer/tpc-h/tpc-h.sql"))
    cls.tpcds_sqls = list(te.load_sql_fixture_pairs("optimizer/tpc-ds/tpc-ds.sql"))


class DeferredParse:
    def __init__(self, real, args, kwargs):
        self.real, self.args, self.kwargs = real, args, kwargs

    def parse(self):
        return self.real(*self.args, **self.kwargs)


def resolve_parses(args):
    return tuple(a.parse() if type(a) is DeferredParse else a for a in args)


def defer_mp_parse(klass, ustate):
    real_mp = klass._mp_execute

    def mp_execute(self, *a, **kw):
        te = sys.modules[klass.__module__]
        real = te.parse_one
        if ustate["allowed"] is not None and "" not in ustate["allowed"]:
            te.parse_one = lambda *pa, **pk: DeferredParse(real, pa, pk)
        try:
            return real_mp(self, *a, **kw)
        finally:
            te.parse_one = real

    klass._mp_execute = mp_execute


def _lazy_class_setup(klass, names):
    real = _lazy_tpc_setup if LAZYTABLES else vars(klass)["setUpClass"].__func__
    real_down = vars(klass)["tearDownClass"].__func__ if "tearDownClass" in vars(klass) else None
    loaded = []

    class Attr:
        def __init__(self, name):
            self.name = name

        def __get__(self, obj, owner):
            if not loaded:
                loaded.append(1)
                for n in names:
                    if isinstance(vars(klass).get(n), Attr):
                        delattr(klass, n)
                real(klass)
            return getattr(klass, self.name)

    def setup(cls):
        for n in names:
            setattr(cls, n, Attr(n))

    def teardown(cls):
        if loaded and real_down:
            real_down(cls)

    klass.setUpClass = classmethod(setup)
    klass.tearDownClass = classmethod(teardown)


class QueryBudget(BaseException):
    pass


def _over_budget(signum, frame):
    raise QueryBudget()


def lean_run(order, stop, optcache, budgets, total):
    with open(os.path.join(HERE, "tpc", "lean.pkl"), "rb") as fh:
        ref = pickle.load(fh)
    queries, schema = ref["queries"], ref["schema"]
    from sqlglot import find_tables, parse_one
    import sqlglot.executor as X
    from sqlglot.executor.table import Table
    d = memo_data()
    blobs, keyed = d["memo"]["ds"], d["keyed"]["ds"]
    signal.signal(signal.SIGVTALRM, _over_budget)
    signal.signal(signal.SIGPROF, _over_budget)
    signal.setitimer(signal.ITIMER_PROF, total)
    tables = {}
    for kind, names in (("h", ref["hschema"]), ("ds", schema)):
        for table in names:
            with open(os.path.join(HERE, "tpc", "%s.%s.m" % (kind, table)), "rb") as fh:
                tables[kind, table] = Table(columns=names[table], rows=marshal.loads(fh.read()))
    tables = pickle.loads(pickle.dumps({t: v for (kind, t), v in tables.items() if kind == "ds"}))
    if optcache:
        real, opt = X.optimize, ref["opt"]

        def cached(*a, **kw):
            try:
                blob = opt.get(pickle.dumps((a, kw)))
            except BaseException:
                blob = None
            return real(*a, **kw) if blob is None else pickle.loads(blob)

        X.optimize = cached

    def run(expression):
        return pickle.loads(pickle.dumps(X.execute(expression, schema=schema, tables={t.name: tables[t.name] for t in find_tables(expression)})))

    bad = []
    for i in order:
        blob = blobs.get(keyed.get("f:%d" % i))
        if i not in queries or blob is None:
            return [i]
        signal.setitimer(signal.ITIMER_VIRTUAL, budgets.get(i, 0))
        got = _outcome(lambda: run(pickle.loads(pickle.dumps(parse_one(queries[i])))))
        signal.setitimer(signal.ITIMER_VIRTUAL, 0)
        if not _same(got, _outcome(lambda: pickle.loads(blob))):
            bad.append(i)
            if stop or got[0] == "err" and got[1] in ("Timeout", "QueryBudget", "MemoryError", "RecursionError"):
                break
    signal.setitimer(signal.ITIMER_PROF, 0)
    return bad


def child_run(root, test_ids, timeouts, wfd, sel, mode=None, lean=None):
    if DEBUG:
        import faulthandler
        faulthandler.enable()
    import unittest
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)
    if not DEBUG:
        os.dup2(devnull, 2)
    os.environ["SKIP_INTEGRATION"] = "0"
    install_futures()
    if mode is not None and mode[0] == "swap":
        import builtins
        import io
        import zygote
        zygote.apply_swaps(mode[1], mode[2])
        for m in list(sys.modules.values()):
            for v in list(vars(m).values()) if m is not None and getattr(m, "__name__", "").startswith("tests") else []:
                if isinstance(v, type) and vars(v).get("_prewarmed"):
                    v.setUpClass = classmethod(lambda cls: None)
                    v.tearDownClass = classmethod(lambda cls: None)
        redirect = {os.path.join(SRC, rel): os.path.join(root, rel) for rel in mode[3]}
        if redirect:
            real_open = builtins.open

            def ropen(file, *a, **k):
                try:
                    key = os.path.abspath(os.fspath(file))
                except TypeError:
                    return real_open(file, *a, **k)
                return real_open(redirect.get(key, file), *a, **k)

            builtins.open = ropen
            io.open = ropen
        os.chdir(SRC)
    else:
        fresh = None
        if mode is not None:
            if CLOSURE:
                gc.freeze()
            fresh = partial_purge(root) if PARTIAL else None
            if fresh is None:
                for m in [m for m in sys.modules if m == "sqlglot" or m.startswith(("sqlglot.", "tests"))]:
                    del sys.modules[m]
            if SRC in sys.path:
                sys.path.remove(SRC)
        os.chdir(root)
        sys.path.insert(0, root)
        for n in fresh or ():
            try:
                importlib.import_module(n)
            except BaseException:
                break
        if fresh:
            for n, m in list(sys.modules.items()):
                base, _, leaf = n.rpartition(".")
                if base in fresh and m is not None and base in sys.modules and not hasattr(sys.modules[base], leaf):
                    setattr(sys.modules[base], leaf, m)
    out = os.fdopen(wfd, "w", buffering=1)

    flagged = set()

    def emit(tag, tid):
        if tag in ("F", "X", "K"):
            flagged.add(tid)
        out.write(f"{tag} {tid}\n")

    class Timeout(BaseException):
        pass

    hung = []

    def on_alarm(signum, frame):
        hung.append(1)
        raise Timeout()

    signal.signal(signal.SIGALRM, on_alarm)
    if mode is not None and mode[0] == "reimport" and len(mode) > 2:
        for modname in mode[2]:
            try:
                signal.setitimer(signal.ITIMER_REAL, 20.0, 0.5)
                importlib.import_module(modname)
            except BaseException:
                emit("X", modname)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    if mode is not None and mode[0] == "reimport" and len(mode) > 1 and mode[1]:
        for modname, tids in mode[1].items():
            try:
                signal.setitimer(signal.ITIMER_REAL, 20.0, 0.5)
                importlib.import_module(modname)
            except BaseException:
                for tid in tids:
                    emit("F", tid)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
    case_to_id = {}
    failed = set()
    subfailed = set()
    recheck = []
    filtered = set()
    cases = []
    for tid in test_ids:
        path, cls, meth = tid.split("::")
        mod = path[:-3].replace("/", ".")
        try:
            m = __import__(mod, fromlist=["_"])
            c = getattr(m, cls)(meth)
        except BaseException:
            emit("F", tid)
            continue
        case_to_id[id(c)] = tid
        cases.append(c)

    class Result(unittest.TestResult):
        def startTest(self, test):
            super().startTest(test)
            tid = case_to_id.get(id(test))
            ustate.update(tid=tid, allowed=sel.get(tid), stack=[], seen={}, fut=0, guard=0, skipped=tid in filtered)
            if tid:
                emit("S", tid)
                self.t0 = time.process_time()
                signal.setitimer(signal.ITIMER_REAL, timeouts.get(tid, 10.0), 0.5)

        def stopTest(self, test):
            signal.setitimer(signal.ITIMER_REAL, 0)
            tid = case_to_id.get(id(test))
            if tid in failed and tid not in subfailed and ustate["skipped"] and not hung:
                failed.discard(tid)
                recheck.append(tid)
            elif tid:
                emit("F" if tid in failed else "P", tid)
                emit("C", "%s %.3f" % (tid, time.process_time() - getattr(self, "t0", time.process_time())))
                if hung:
                    out.flush()
                    os._exit(0)
            super().stopTest(test)

        def _fail(self, test):
            tid = case_to_id.get(id(test))
            if tid:
                failed.add(tid)
                return
            desc = str(test)
            m = re.match(r"setUpClass \(([\w.]+)\)", desc)
            if m:
                emit("K", m.group(1))
            for c in cases:
                ctid = case_to_id[id(c)]
                cname = type(c).__module__ + "." + type(c).__qualname__
                if cname in desc or type(c).__module__ in desc:
                    failed.add(ctid)
                    emit("F", ctid)

        def addError(self, test, err):
            self._dbg(test, err)
            self._fail(test)

        def addFailure(self, test, err):
            self._dbg(test, err)
            self._fail(test)

        def _dbg(self, test, err):
            if DEBUG and os.environ.get("BR_TB") == "1":
                import traceback
                sys.stderr.write("DBG %s\n%s\n" % (test, "".join(traceback.format_exception(*err))[-1500:]))

        def addSubTest(self, test, subtest, err):
            if err is not None:
                subfailed.add(case_to_id.get(id(test)))
                self._dbg(test, err)
                self._fail(test)

        def addUnexpectedSuccess(self, test):
            self._fail(test)

    orig_subtest = unittest.TestCase.subTest
    stop = {}
    ustate = {"tid": None, "allowed": None, "stack": [], "seen": {}, "fut": 0, "guard": 0}
    import unittest._log
    for ctx in (unittest.case._AssertRaisesContext, unittest.case._AssertWarnsContext, unittest._log._AssertLogsContext):
        def guard_enter(self, _enter=ctx.__enter__):
            ustate["guard"] += 1
            return _enter(self)

        def guard_exit(self, *a, _exit=ctx.__exit__):
            ustate["guard"] -= 1
            return _exit(self, *a)

        ctx.__enter__ = guard_enter
        ctx.__exit__ = guard_exit
    for tid, keys in sel.items():
        if keys is not None:
            closed = set()
            for k in keys:
                parts = k.split(">")
                for i in range(1, len(parts) + 1):
                    closed.add(">".join(parts[:i]))
            sel[tid] = closed

    class SkipBody(Exception):
        pass

    class UnitSub:
        def __init__(self, case, msg, params):
            base = repr((None if msg is unittest.case._subtest_msg_sentinel else msg, sorted(params.items())))
            fullk = ">".join(ustate["stack"] + [base])
            n = ustate["seen"].get(fullk, 0)
            ustate["seen"][fullk] = n + 1
            self.key = "s:" + base + ("#%d" % n if n else "")
            self.path = ">".join(ustate["stack"] + [self.key])
            self.skip = ustate["allowed"] is not None and self.path not in ustate["allowed"] and not ustate["guard"]
            if self.skip and not ustate["stack"]:
                q = _QKEY2.match(self.key)
                if q and "q:" + q.group(2) in ustate["allowed"]:
                    self.skip = False
            self.inner = None if self.skip else orig_subtest(case, msg, **params)
            if self.skip:
                ustate["skipped"] = True

        def __enter__(self):
            ustate["stack"].append(self.key)
            if self.skip:
                sys.settrace(lambda *a: None)
                frame = sys._getframe(1)

                def tracer(fr, ev, arg):
                    raise SkipBody()

                frame.f_trace = tracer
                return None
            return self.inner.__enter__()

        def __exit__(self, et, ev, tb):
            ustate["stack"].pop()
            if self.skip:
                sys.settrace(None)
                sys._getframe(1).f_trace = None
                return et is SkipBody
            return self.inner.__exit__(et, ev, tb)

    def unit_subtest(self, msg=unittest.case._subtest_msg_sentinel, **params):
        if stop.get(id(self)):
            raise StopTest()
        return UnitSub(self, msg, params)

    def lazy_submit(self, fn, *args, **kwargs):
        k = ustate["fut"]
        ustate["fut"] += 1
        skip = ustate["allowed"] is not None and ("f:%d" % k) not in ustate["allowed"]
        if not skip:
            args = resolve_parses(args)
        f = LazyFuture(fn, args, kwargs)
        f.skip_outer = skip
        if skip:
            ustate["skipped"] = True
        return f

    SyncExecutor.submit = lazy_submit
    orig_force = LazyFuture._force

    def force(self):
        if getattr(self, "skip_outer", False) and not ustate["stack"] and self.state is None:
            self.state = (True, None)
        if self.state is None:
            self.args = resolve_parses(self.args)
        return orig_force(self)

    LazyFuture._force = force

    class StopTest(Exception):
        pass

    def subtest(self, msg=unittest.case._subtest_msg_sentinel, **params):
        if stop.get(id(self)):
            raise StopTest()
        return orig_subtest(self, msg, **params)

    if UNITS:
        unittest.TestCase.subTest = unit_subtest
    elif FAILFAST:
        unittest.TestCase.subTest = subtest
    if FAILFAST:
        orig_add_subtest = Result.addSubTest

        def add_subtest(self, test, sub, err):
            if err is not None:
                stop[id(test)] = True
            orig_add_subtest(self, test, sub, err)

        Result.addSubTest = add_subtest
    if STMT_OF:
        patched_rel = set(CHILD_PATCHED)
        for c in cases:
            tid = case_to_id.get(id(c))
            if sel.get(tid):
                smap = STMT_OF.get(tid) or {}
                whole = {int(k[2:]) for k in sel[tid] if k.startswith("t:")}
                sel[tid].update(k for k, i in smap.items() if i in whole)
                try:
                    r = STMTSEL and stmt_filter(c, tid, sel[tid], patched_rel)
                    if r:
                        filtered.add(tid)
                    if DEBUG:
                        print("stmt", tid, r, file=sys.stderr)
                except Exception as e:
                    if DEBUG:
                        print("stmt err", tid, repr(e), file=sys.stderr)
    if CHILD_LAZY:
        for k in {type(c) for c in cases}:
            if k.__name__ == "TestExecutor" and k.__module__ == "tests.test_executor" and not vars(k).get("_prewarmed") and "setUpClass" in vars(k):
                _lazy_class_setup(k, ("tpch_conn", "tpcds_conn", "tpch_tables", "tpcds_tables", "cache", "tpch_sqls", "tpcds_sqls"))
                if UNITS and TPCPARSE:
                    defer_mp_parse(k, ustate)
    if CHILD_MEMO is not None:
        install_memo(*CHILD_MEMO, ustate)
    last = [c for c in cases if case_to_id[id(c)] == MEMO_TEST] if LIGHTFIRST == "skip" else []
    if last:
        mates = [c for c in cases if type(c) is type(last[0])]
        cases.remove(last[0])
        cases.insert(cases.index(mates[-1]) + (mates[-1] is not last[0]), last[0])

        def gate(result, _run=last[0].run):
            if flagged - {MEMO_TEST}:
                emit("S", MEMO_TEST)
                emit("F", MEMO_TEST)
                return None
            return _run(result)

        last[0].run = gate
    suite = unittest.TestSuite(cases)
    try:
        suite.run(Result())
    except BaseException:
        pass
    if recheck:
        again = []
        for tid in recheck:
            path, cls, meth = tid.split("::")
            c = getattr(sys.modules[path[:-3].replace("/", ".")], cls)(meth)
            case_to_id[id(c)] = tid
            sel[tid] = None
            filtered.discard(tid)
            again.append(c)
        try:
            unittest.TestSuite(again).run(Result())
        except BaseException:
            pass
    if lean is not None and LIGHTFIRST == "skip" and not LEANCAL and flagged - {MEMO_TEST}:
        emit("S", MEMO_TEST)
        emit("F", MEMO_TEST)
    elif lean is not None:
        order, optcache, budgets, total = lean
        emit("S", MEMO_TEST)
        t0 = time.process_time()
        try:
            import resource
            with open("/proc/self/status") as fh:
                vm = int(fh.read().split("VmSize:")[1].split()[0]) * 1024
            resource.setrlimit(resource.RLIMIT_AS, (vm + LEAN_MEM, vm + LEAN_MEM))
            signal.setitimer(signal.ITIMER_REAL, LEAN_WALL, 0.5)
            bad = lean_run(order, not LEANCAL, optcache, budgets, total)
            emit("Q", ",".join(map(str, bad)) or "-")
        except BaseException:
            bad = [-1]
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.setitimer(signal.ITIMER_PROF, 0)
        emit("F" if bad else "P", MEMO_TEST)
        emit("C", "%s %.3f" % (MEMO_TEST, time.process_time() - t0))
    emit("D", "-")
    out.flush()
    os._exit(0)


class Job:
    def __init__(self, cid, root, tests, timeouts, deadline, sel=None, mode=None, lean=None):
        self.cid = cid
        self.root = root
        self.tests = tests
        self.timeouts = timeouts
        self.deadline = deadline
        self.status = {}
        self.tcpu = {}
        self.current = None
        self.done = False
        self.buf = b""
        r, w = os.pipe()
        pid = os.fork()
        if pid == 0:
            os.close(r)
            try:
                child_run(root, tests, timeouts, w, sel or {}, mode, lean)
            except BaseException:
                if DEBUG:
                    import traceback
                    traceback.print_exc()
            finally:
                os._exit(1)
        os.close(w)
        self.pid = pid
        self.fd = r

    def feed(self):
        data = os.read(self.fd, 65536)
        if not data:
            self.finish()
            return
        self.buf += data
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            tag, tid = line.decode().split(" ", 1)
            if tag == "S":
                self.current = tid
            elif tag in ("P", "F"):
                self.status[tid] = tag
                self.current = None
            elif tag == "C":
                t, c = tid.rsplit(" ", 1)
                self.tcpu[t] = float(c)
            elif tag == "X":
                self.broken = True
            elif tag == "Q":
                self.lean = tid
            elif tag == "K":
                self.klass_fail = getattr(self, "klass_fail", set()) | {tid}
            elif tag == "D":
                pass

    def cpu_now(self):
        try:
            with open("/proc/%d/stat" % self.pid) as fh:
                f = fh.read().rsplit(")", 1)[1].split()
            return (int(f[11]) + int(f[12])) / os.sysconf("SC_CLK_TCK")
        except (OSError, IndexError, ValueError):
            return 0.0

    def kill(self):
        try:
            os.kill(self.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.finish()

    def finish(self):
        if self.done:
            return
        self.done = True
        try:
            os.close(self.fd)
        except OSError:
            pass
        self.cpu = 0.0
        try:
            _, st, ru = os.wait4(self.pid, 0)
            self.cpu = ru.ru_utime + ru.ru_stime
            self.exit = st
        except ChildProcessError:
            pass

    def unresolved(self):
        return [t for t in self.tests if t not in self.status]


def main():
    tests_doc = json.load(open(os.path.join(DATA, "tests.json")))
    tests = tests_doc["tests"]
    id_to_num = {t["id"]: t["number"] for t in tests}
    num_to_id = {t["number"]: t["id"] for t in tests}
    ms = {t["number"]: int(t["seconds"] * 1000 + 0.5) for t in tests}
    cov = CovMap(MAP_PATH, id_to_num)
    log("map loaded cpu=%.2f" % time.process_time())
    runcpu = json.load(open(os.path.join(HERE, "runcpu.json")))
    unitcpu = json.load(open(os.path.join(HERE, "unitcpu.json"))) if UNITCOST else {"units": {}}
    sys.path.insert(0, HERE)
    from split import split, cost as split_cost

    commits = sorted(p[:-6] for p in os.listdir(os.path.join(DATA, "commits")) if p.endswith(".patch"))
    plans = []
    memo_warm = None
    for cid in commits:
        text = open(os.path.join(DATA, "commits", cid + ".patch"), encoding="utf-8", errors="surrogateescape").read()
        FRACTION_OK.clear()
        FORCE_LIST.clear()
        notes = []
        cands = {}
        patched = {}
        hunks_by = {}
        old_by = {}
        ok = True
        try:
            files = parse_patch(text)
            for f in files:
                if f.get("binary"):
                    notes.append("binary:" + f["path"])
                    for q in {f["old"], f["path"]}:
                        r = candidates_for(dict(f, path=q, old=q, deleted=True, new_file=False, hunks=[]), None, None, cov, notes)
                        FORCE_LIST.update(r)
                        merge(cands, r)
                    continue
                src = os.path.join(SRC, f["old"])
                old_text = None
                if not f["new_file"] and os.path.exists(src):
                    with open(src, encoding="utf-8", newline="") as fh:
                        old_text = fh.read()
                new_text = None if f["deleted"] else apply_file(old_text or "", f["hunks"])
                patched[f["path"]] = new_text
                hunks_by[f["path"]] = f["hunks"]
                old_by[f["path"]] = old_text
                if f["old"] != f["path"]:
                    patched[f["old"]] = None
                    if PATHRULES and not f["old"].startswith("sqlglot/"):
                        merge(cands, candidates_for(dict(f, path=f["old"], deleted=True, hunks=[]), old_text, None, cov, notes))
                merge(cands, candidates_for(f, old_text, new_text, cov, notes))
        except Exception as e:
            ok = False
            notes.append(f"error:{type(e).__name__}:{e}")
            cands = full(num_to_id)
        if IMPORTT and "importtime" in notes:
            try:
                os.environ.setdefault("IMPORTTIME_SQLGLOT", SRC)
                os.environ.setdefault("IMPORTTIME_MAPS", os.path.join(HERE, "itmaps"))
                import importtime as itf
                if ITF_UNITS:
                    extra, info = itf.extra_candidates_units(text, root=SRC, with_info=True)
                    whole = "import-body" in notes
                    for n, keys in extra.items():
                        if n in num_to_id:
                            keys = None if whole else keys
                            if keys is not None:
                                FRACTION_OK.add(n)
                            merge(cands, {n: keys})
                else:
                    extra, info = itf.extra_candidates(text, root=SRC, with_info=True)
                    merge(cands, full(n for n in extra if n in num_to_id))
                if "import-body" in notes and "dynamic_paths" not in info:
                    dyn, dinfo = itf.dynamic_extra_candidates(text, root=SRC, items=True)
                    if dinfo.get("error"):
                        raise RuntimeError("dynamic")
                    notes.append("dynamic:%d" % len(dyn))
                    merge(cands, full(n for n in itf.items_to_units(dyn) if n in num_to_id))
                notes.append("itf:%d%s" % (len(extra), "" if info.get("confident", True) else ":unconfident"))
            except Exception as e:
                notes.append(f"itf-error:{type(e).__name__}")
                cands = full(num_to_id)
        for n, keys in cands.items():
            word = _MP_TESTS.get(num_to_id[n].rsplit("::", 1)[-1])
            if word and keys:
                for k in list(keys):
                    m = _QKEY.match(k)
                    if k.startswith("f:"):
                        keys.add("s:%r" % (("%s %d" % (word, int(k[2:]) + 1), []),))
                    elif m and m.group(1) == word:
                        keys.add("f:%d" % (int(m.group(2)) - 1))
        if DEBUG_N in cands:
            log(cid, "dbg", DEBUG_N, "keys", None if cands[DEBUG_N] is None else len(cands[DEBUG_N]), "fracok", DEBUG_N in FRACTION_OK, None if cands[DEBUG_N] is None else sorted(cands[DEBUG_N])[:5])
        cached = TPCREF and LAZYTABLES and tpc_lazy(patched)
        memo_n = id_to_num.get(MEMO_TEST)
        if MEMO and memo_n in cands:
            if memo_warm is None:
                memo_warm = {p: set(v) for p, v in json.load(open(os.path.join(HERE, "warmmap.json"))).items()}
            use_memo = memo_ok(patched, hunks_by, old_by, notes, memo_warm)
        else:
            use_memo = False
        touched = set()
        if use_memo:
            use_memo, touched = use_memo
            fx = "tests/fixtures/optimizer/tpc-ds/tpc-ds.sql"
            if fx in patched and all(r == fx or "noop:" + r in notes or not (r.startswith("sqlglot/") or "/tpc-" in r or r in ("tests/helpers.py", "tests/test_executor.py")) for r in patched):
                try:
                    known = {(q, tuple(sorted(m.items()))) for (q, m), _ in _pairs(old_by[fx])}
                    fresh = [i + 1 for i, ((q, m), _) in enumerate(_pairs(patched[fx])) if (q, tuple(sorted(m.items()))) not in known]
                except Exception:
                    fresh = None
                if fresh is not None:
                    keys = {"f:%d" % (i - 1) for i in fresh} | {"s:%r" % (("tpc-ds %d" % i, []),) for i in fresh}
                    if cands[memo_n] is None or keys < cands[memo_n]:
                        cands[memo_n] = keys
                    notes.append("memo-fresh:%d" % len(fresh))
            notes.append("memo:%s:%d" % (use_memo, len(touched)))

        def est(n, memo=True):
            c = runcpu.get(num_to_id[n], 0)
            if memo and use_memo and n == memo_n:
                pre, run = memo_data()["pre"]["ds"], memo_data()["run"]["ds"]
                keys = set(pre) if cands[n] is None else set(cands[n])
                return min(c, UNIT_K * sum(pre.get(k, 0) + (run.get(k, 0) if k in touched else 0) for k in keys) + FRAC_C)
            if not (UNITEST or n in FRACTION_OK) or cands[n] is None or not cov.nunits.get(n):
                return c
            u = cached and unitcpu["units"].get(num_to_id[n])
            if u:
                return min(c, UNIT_K * sum(u.get(k, 0) for k in cands[n]) + FRAC_C)
            return min(c, c * FRAC_K * len(cands[n]) / cov.nunits[n] + FRAC_C)

        def decide(price=None):
            def cost(n):
                return price if price is not None and n == memo_n else est(n)

            heavy = {n for n in cands if n in FORCE_LIST or ms[n] >= HEAVY_MS or (LISTRULE and cost(n) * 1000 > ms[n] + 2000)}
            light = sorted(set(cands) - heavy)
            whole = split_cost(sorted(cands), ms)
            cap = whole - split_cost(sorted(heavy), ms)
            over = RUN_O_RE if ("importtime" in notes or any(not r.endswith(".py") for r in patched)) else RUN_O
            if light and (RUN_K * sum(cost(n) for n in light) + over) * 1000 >= cap:
                return set(cands), [], cap, "blind"
            if price is None and light and memo_n in light and est(memo_n, False) * 1000 > ms[memo_n] + 2000 and (RUN_K * sum(est(n) for n in light if n != memo_n) + over) * 1000 >= whole - split_cost(sorted(heavy | {memo_n}), ms):
                spend = RUN_K * sum(est(n) * (1 if n == memo_n else MEMO_K) for n in light) + over
                if spend * 1000 >= cap:
                    return set(cands), [], cap, "blind:memo"
            return heavy, light, cap, None

        heavy, light, cap, blind = decide()
        lean = fallback = picks = None
        u = lean_cost() if LEAN and ok and cached and memo_n in heavy and memo_n not in FORCE_LIST and _lean_meta() else None
        if u and lean_gate(notes, patched, old_by, hunks_by):
            need = lean_need(cov, memo_n, patched, hunks_by, notes, u)
            optcache = not any(r in _lean_meta()["optfiles"] for r in patched if "noop:" + r not in notes)
            if CANARY_K:
                chosen = canary_pick(need, u, CANARY_K)
                order = lean_order(need, u, chosen)
                price = CANARY_SCALE * sum(u[q] for q in chosen) + FRAC_C
            else:
                order = lean_order(need, u)
                price = LEAN_OPT_COST if optcache else LEAN_COST
            if LEANCAL:
                picks = {k: [int(q[2:]) for q in canary_pick(need, u, k)] for k in (0, 2, 4, 8)}
            h2, l2, c2, b2 = decide(price)
            saving = (split_cost(sorted(h2 | {memo_n}), ms) - split_cost(sorted(h2), ms)) / 1000
            if memo_n in l2 and price < saving or LEANCAL:
                fallback = {"light": light, "heavy": heavy, "cap": cap / 1000, "notes": ([blind] if blind else []) + notes, "sel": {num_to_id[n]: (None if cands[n] is None else sorted(cands[n])) for n in light}, "lean": None, "fallback": None, "price": 0}
                heavy, light, cap, blind = (h2 - {memo_n}, sorted(set(l2) | {memo_n}), 1e9, b2) if LEANCAL else (h2, l2, c2, b2)
                if blind:
                    heavy, light, blind = heavy - {memo_n}, [memo_n], None
                notes = notes + ["lean%s%s:%.1f" % (":k%d" % CANARY_K if CANARY_K else "", ":opt" if optcache else "", saving)]
                lean = (order, optcache, {} if LEANCAL else {int(q[2:]): BUDGET_K * c + BUDGET_C for q, c in u.items()}, 1e6 if LEANCAL else saving / LEAN_SCALE)
        if blind:
            notes.insert(0, blind)
        sel = {num_to_id[n]: (None if cands[n] is None else sorted(cands[n])) for n in light if not (lean and n == memo_n)}
        runs_memo = memo_n in light and not lean
        plans.append({"cid": cid, "hunks": hunks_by, "old": old_by, "patched": patched, "light": light, "heavy": heavy, "notes": notes, "ok": ok, "sel": sel, "cap": cap / 1000, "memo": use_memo if runs_memo else False, "touched": touched, "strict": use_memo and runs_memo and est(memo_n, False) * 1000 > ms[memo_n] + 2000, "lean": lean, "fallback": fallback, "picks": picks, "price": price if lean else 0, "gain": saving - price if lean else 0})
        log(cid, "plancpu=%.2f" % time.process_time(), "cands", len(cands), "partial", sum(1 for n in light if cands[n] is not None), "heavy", sorted(heavy), "est_cpu %.2f" % sum(est(n) for n in light), notes[:4], "memo:%s:%d" % (use_memo, len(touched)) if use_memo else "")

    room = LEAN_ROOM * PARALLEL * BUDGET_FRAC * min(270.0, 180.0 * max(1.0, len(commits) / 40.0))
    spent = sum(p["price"] for p in plans)
    for p in sorted((p for p in plans if p["fallback"] and not LEANCAL), key=lambda p: p["gain"]):
        if spent <= room:
            break
        spent -= p["price"]
        p.update(p["fallback"])
        log(p["cid"], "lean dropped: wall budget")
    log("planned cpu=%.2f est=%.1f room=%.1f" % (time.process_time(), spent, room))
    if STATIC:
        for p in plans:
            sys.stdout.write(json.dumps({"commit": p["cid"], "workers": split(sorted(set(p["light"]) | set(p["heavy"])), ms)}) + "\n")
            WRITTEN.add(p["cid"])
        sys.stdout.flush()
        return
    if os.environ.get("BR_PLANONLY"):
        return
    imap = json.load(gzip.open(os.path.join(HERE, "importmap.json.gz"), "rt"))
    mod_tids = {}
    for n, tid in num_to_id.items():
        mod_tids.setdefault(tid.split("::")[0][:-3].replace("/", "."), []).append(tid)
    for p in plans:
        mask = 0
        for rel, content in p["patched"].items():
            if not rel.endswith(".py") or not rel.startswith(("sqlglot/", "tests/")) or "gone:" + rel in p["notes"]:
                continue
            if content is None or p["old"].get(rel) is None:
                mask = -1
                break
            if "noop:" + rel in p["notes"]:
                continue
            fm = imap["files"].get(rel, {})
            removed, anchors = changed_old_lines(p["hunks"][rel])
            for ln in removed | anchors:
                mask |= fm.get(str(ln), 0)
            if NEWTOP and "newtop:" + rel in p["notes"]:
                for v in fm.values():
                    mask |= v
        mods = imap["modules"]
        chosen = mods if mask == -1 else [m for i, m in enumerate(mods) if mask >> i & 1]
        p["collect"] = {m: mod_tids.get(m, []) for m in chosen} if COLLECT and chosen else None
        if p["collect"]:
            log(p["cid"], "collect", len(chosen))
    for p in plans:
        p["probe"] = p["collect"] is not None or (PROBE and "importtime" in p["notes"])
    for p in plans:
        p["runs"] = [n for n in p["light"] if not (p["lean"] and num_to_id[n] == MEMO_TEST)]
    heavy_libs = ("tests/test_executor.py", "tests/test_optimizer.py")
    needs_libs = any(num_to_id[n].startswith(heavy_libs) for p in plans for n in p["runs"]) or any(m in ("tests.test_executor", "tests.test_optimizer") for p in plans for m in (p["collect"] or ()))
    if LAZYPANDAS:
        needs_exec = any(num_to_id[n].startswith("tests/test_executor.py") for p in plans for n in p["runs"]) or any(m == "tests.test_executor" for p in plans for m in (p["collect"] or ()))
        if not needs_exec:
            sys.modules["pandas.testing"] = _LazyPandasTesting("pandas.testing")
            needs_libs = False
            try:
                import duckdb
            except Exception:
                pass
    if any(p["light"] or p.get("probe") for p in plans):
        preimport(needs_libs or not LEANIMP)
    log("preimported cpu=%.2f" % time.process_time())
    zyg = None
    if ZYGOTE and any(p["light"] or p.get("probe") for p in plans):
        import zygote
        install_futures()
        warm_ids = sorted({num_to_id[n] for p in plans for n in p["runs"]})
        table_attrs = {"tpch_conn", "tpcds_conn", "tpch_tables", "tpcds_tables", "cache", "tpch_sqls", "tpcds_sqls", "cached_execute", "subtestHelper", "_mp_execute"}
        reach = {}
        for _, _, classes in _setup_index(cov):
            for _, _, tattrs in classes:
                reach.update(tattrs)

        def needs_tables(n):
            if not num_to_id[n].startswith("tests/test_executor.py::TestExecutor::"):
                return False
            r = reach.get(n)
            return not LAZYEXEC or r is None or bool(r & table_attrs)

        exec_commits = sum(1 for p in plans if any(needs_tables(n) for n in p["runs"]))
        opt_commits = sum(1 for p in plans if any(num_to_id[n].startswith("tests/test_optimizer.py::TestOptimizer::") for n in p["light"]))
        zygote.warm(SRC, warm_ids, (TPCWARM or not (TPCREF and LAZYTABLES)) and exec_commits >= (3 if LAZYTABLES else 2 if LAZYEXEC or LEANIMP else 1), OPTWARM and opt_commits >= 2)
        if PARTIAL:
            load_edges()
        warm_lines = {p: set(v) for p, v in json.load(open(os.path.join(HERE, "warmmap.json"))).items()}
        code_idx = zygote.code_index({os.path.join(SRC, r) for p in plans for r in p["patched"] if r.endswith(".py")})
        zyg = (zygote, warm_lines, code_idx)
        if GCFREEZE:
            _PARSED.clear()
            gc.collect()
            gc.freeze()
        log("zygote warm done t=%.1f cpu=%.2f" % (time.monotonic() - T0, time.process_time()))
    if GCOFF:
        gc.freeze()
        gc.enable()
    results = {}
    pending = [p for p in plans if p["light"] or p["probe"]]
    for p in plans:
        if not p["light"] and not p["probe"]:
            results[p["cid"]] = set(p["heavy"])
    pending.sort(key=lambda p: -sum(ms[n] for n in p["light"]))
    running = []
    queue = list(pending)
    end = T0 + BUDGET_FRAC * min(270.0, 180.0 * max(1.0, len(commits) / 40.0))
    while queue or running:
        while queue and len(running) < PARALLEL:
            p = queue.pop(0)
            if time.monotonic() > end - 5:
                results[p["cid"]] = set(p["heavy"]) | set(p["light"])
                continue
            root = os.path.join(TMP, "ov", p["cid"])
            slot = False
            ids = [num_to_id[n] for n in p["runs"]]
            timeouts = {num_to_id[n]: max(3.0, ms[n] / 1000 * 10 + 2) for n in p["light"]}
            budget = sum(timeouts.values()) + 30
            mode = None
            if zyg is not None:
                mode = ("reimport", p["collect"], [modname_of(r) for r, c in p["patched"].items() if c is not None and p["old"].get(r) is not None and r.startswith("sqlglot/") and r.endswith(".py") and "gone:" + r not in p["notes"]])
                zmod, warm_lines, code_idx = zyg
                swaps, nonpy, ok = [], [], True
                for rel, content in p["patched"].items():
                    if content is None or p["old"].get(rel) is None:
                        ok = False
                    elif rel.endswith(".py"):
                        removed, anchors = changed_old_lines(p["hunks"][rel])
                        try:
                            plan = zmod.swap_plan(SRC, rel, p["old"][rel], content, removed | anchors, warm_lines, parse_cached(p["old"][rel]))
                        except SyntaxError:
                            plan = None
                        if plan is None:
                            ok = False
                        else:
                            swaps.append(plan)
                    else:
                        if rel in zmod.WARM_OPENED:
                            ok = False
                        nonpy.append(rel)
                if ok:
                    mode = ("swap", swaps, code_idx, nonpy)
                log(p["cid"], "mode", mode[0])
            try:
                rmtree(root)
                if THINOV and mode is not None and mode[0] == "swap":
                    for rel in mode[3]:
                        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
                        with open(os.path.join(root, rel), "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
                            fh.write(p["patched"][rel])
                else:
                    if REUSEOV:
                        slot = True
                        root = SLOTS.pop() if SLOTS else root
                    build_overlay(root, p["patched"])
            except Exception as e:
                log(p["cid"], "overlay failed", repr(e))
                results[p["cid"]] = set(num_to_id)
                continue
            global CHILD_LAZY, CHILD_PATCHED, CHILD_MEMO
            CHILD_PATCHED = list(p["patched"])
            CHILD_MEMO = (memo_blobs(p["touched"]), memo_data()["drop"], memo_state() if p["memo"] == "state" else None, p["strict"] and MEMO_MISS + 2 * sum(memo_data()["run"]["ds"].get(k, 0) for k in p["touched"])) if p["memo"] else None
            CHILD_LAZY = tpc_lazy(p["patched"])
            p["job"] = Job(p["cid"], root, ids, timeouts, time.monotonic() + budget, p["sel"], mode, p["lean"])
            p["root"] = root
            p["slot"] = slot
            running.append(p)
        fds = [p["job"].fd for p in running]
        r, _, _ = select.select(fds, [], [], 0.5)
        for p in list(running):
            job = p["job"]
            if job.fd in r:
                job.feed()
            if p["memo"] and not job.done and job.status.get(MEMO_TEST) == "F":
                fail = {id_to_num[t] for t, v in job.status.items() if v == "F"} | set(p["heavy"])
                if split_cost(sorted(fail | set(p["light"])), ms) <= split_cost(sorted(fail), ms):
                    log(p["cid"], "memo test failed, listing the rest")
                    job.kill()
                    p["listall"] = True
            if not job.done and (time.monotonic() > min(job.deadline, end) or job.cpu_now() > p["cap"] + 2.0):
                log(p["cid"], "killed cpu=%.2f cap=%.2f" % (job.cpu_now(), p["cap"]))
                job.kill()
                if p["probe"]:
                    job.broken = True
            if job.done:
                running.remove(p)
                fail = {id_to_num[t] for t, s in job.status.items() if s == "F"}
                for kq in getattr(job, "klass_fail", ()):
                    mod, _, cname = kq.rpartition(".")
                    pre = "%s.py::%s::" % (mod.replace(".", "/"), cname)
                    fail |= {n for n, t in num_to_id.items() if t.startswith(pre)}
                if getattr(job, "broken", False):
                    log(p["cid"], "patched module does not import")
                    fail = set(num_to_id)
                unresolved = job.unresolved()
                if unresolved:
                    log(p["cid"], "unresolved", len(unresolved), "current", job.current, "exit", getattr(job, "exit", None))
                    fail |= {id_to_num[t] for t in unresolved}
                if p["lean"] and job.status.get(MEMO_TEST) != "P":
                    fail.add(id_to_num[MEMO_TEST])
                if p["lean"] and CANARY_K and fail - {id_to_num[MEMO_TEST]}:
                    fail.add(id_to_num[MEMO_TEST])
                if p["lean"] and LEANCAL:
                    log(p["cid"], "leancal", json.dumps({"full": getattr(job, "lean", None), "picks": p["picks"], "other": sorted(fail - {id_to_num[MEMO_TEST]}), "status": job.status.get(MEMO_TEST), "cpu": job.tcpu.get(MEMO_TEST)}))
                results[p["cid"]] = fail | set(p["heavy"]) | (set(p["light"]) if p.get("listall") else set())
                if p["slot"]:
                    release_slot(p["root"], p["patched"])
                else:
                    rmtree(p["root"])
                top = sorted(job.tcpu.items(), key=lambda kv: -kv[1])[:4]
                log(p["cid"], "testcpu=%.2f" % sum(job.tcpu.values()), "top", " ".join("%s:%.2f" % (t.split("::")[-1], c) for t, c in top))
                log(p["cid"], "fail", sorted(fail), "heavy", sorted(p["heavy"]), "cpu=%.2f" % job.cpu, "t=%.1f" % (time.monotonic() - T0))
    log("loop done cpu=%.2f" % time.process_time())
    for cid in commits:
        workers = split(sorted(results.get(cid, set())), ms)
        sys.stdout.write(json.dumps({"commit": cid, "workers": workers}) + "\n")
        WRITTEN.add(cid)
    sys.stdout.flush()
    import resource
    log("end self=%.2f children=%.2f" % (time.process_time(), sum(resource.getrusage(resource.RUSAGE_CHILDREN)[:2])))


WRITTEN = set()


def fallback():
    tests = json.load(open(os.path.join(DATA, "tests.json")))["tests"]
    nums = [t["number"] for t in tests]
    for p in sorted(os.listdir(os.path.join(DATA, "commits"))):
        if p.endswith(".patch") and p[:-6] not in WRITTEN:
            sys.stdout.write(json.dumps({"commit": p[:-6], "workers": [nums[i::8] for i in range(8)]}) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:
        log("main failed", repr(e))
        fallback()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)
