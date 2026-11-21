import ast
import bisect
import enum
import gzip
import importlib
import json
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
GCFREEZE = os.environ.get("BR_GCFREEZE", "0") == "1"
LAZYEXEC = os.environ.get("BR_LAZYEXEC", "1") == "1"
LAZYUNITS = os.environ.get("BR_LAZYUNITS", "1") == "1"
DEBUG_N = int(os.environ.get("BR_DEBUG_N", "-1"))
UNITS = os.environ.get("BR_UNITS", "1") == "1"
CANON = os.environ.get("BR_CANON", "1") == "1"
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
PROBE = os.environ.get("BR_PROBE", "1") == "1"
COLLECT = os.environ.get("BR_COLLECT", "1") == "1"
IMPORTT = os.environ.get("BR_IMPORTT", "1") == "1"
BUDGET_FRAC = float(os.environ.get("BR_BUDGET_FRAC", "0.75"))
T0 = time.monotonic()


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def parse_patch(text):
    files = []
    cur = None
    hunk = None
    for line in text.splitlines(keepends=True):
        if line.startswith("diff --git "):
            m = re.match(r"diff --git a/(\S+) b/(\S+)", line)
            cur = {"old": m.group(1), "path": m.group(2), "hunks": [], "new_file": False, "deleted": False}
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
            self.undo.append((node, node.ops))
            node.ops = [ast.Eq() if isinstance(node.ops[0], ast.Is) else ast.NotEq()]
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
        t = _PARSED[text] = ast.parse(text)
    return t


def _canon_dump(node, resolve):
    if not CANON:
        return ast.dump(node, annotate_fields=False, include_attributes=False)
    canon = _Canon(resolve)
    try:
        canon.visit(node)
        return ast.dump(node, annotate_fields=False, include_attributes=False)
    finally:
        for n, ops in reversed(canon.undo):
            n.ops = ops


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


def ast_noop(old_text, new_text, hunks, resolve):
    try:
        a, b = parse_cached(old_text), parse_cached(new_text)
    except SyntaxError:
        return False
    removed, anchors = changed_old_lines(hunks)
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


def _candidates_for(f, old_text, new_text, cov, notes):
    path = f["path"]
    if path.startswith("sqlglot/") and path.endswith(".py"):
        if f["deleted"] or (f["old"] and f["old"] != path):
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
                gone = set(top_names(parse_cached(old_text))) - set(top_names(parse_cached(new_text)))
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
            if FASTNOOP:
                same = ast_noop(old_text, new_text, f["hunks"], res)
            else:
                a, b = strip_ast(old_text, res), strip_ast(new_text, res)
                same = a is not None and a == b
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
        try:
            new_units = Units(new_text, added_new_lines(f["hunks"]))
        except SyntaxError:
            new_units = None
        lam = LAMBDAS and new_units is not None and lambda_only(path, units, new_units, f["hunks"])
        if lam:
            notes.append("lambda-only")
        for h in f["hunks"]:
            hr, ha = changed_old_lines([h])
            found = {ln: units.unit_for(ln) for ln in sorted(hr | ha)}
            gap = GAPS and not any(found.values())
            for ln, u in found.items():
                for _, first, last, runtime, node in [u] if u else units.gap_units(ln) if gap else ():
                    merge(out, cov.tests_for_lines(path, range(first, last + 1)))
                    if not runtime and not (lam and isinstance(node, ast.Lambda)):
                        importtime = True
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
        if importtime:
            notes.append("importtime")
            if not IMPORTT:
                merge(out, cov.tests_touching_file(path))
                merge(out, full(module_test_files(path, cov)))
        return merge(out, extra)
    if path.startswith("tests/") and path.endswith(".py"):
        if os.path.basename(path).startswith("test_"):
            notes.append("testfile")
            out = set(cov.by_file.get(path, []))
            if any(tag == "+" and "xfail" in line for h in f["hunks"] for tag, line in h["lines"]):
                notes.append("xfail")
                FORCE_LIST.update(out)
            hit = test_dependents(path, f, old_text, new_text)
            if hit:
                notes.append("test-dependents:%d" % len(hit))
                out.update(n for tf in hit for n in cov.by_file.get(tf, []))
            return out
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
    return set()


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
STMT_OF = {}
_STMT_TREES = {}


def _stmt_tree(path):
    t = _STMT_TREES.get(path)
    if t is None:
        with open(path, encoding="utf-8") as fh:
            t = _STMT_TREES[path] = ast.parse(fh.read())
    return t


def _skippable(st, local):
    if not isinstance(st, ast.Expr) or not isinstance(st.value, ast.Call):
        return False
    f = st.value.func
    if not (isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "self"):
        return False
    return not any(isinstance(n, ast.Name) and n.id in local for n in ast.walk(st))


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
    tree = _stmt_tree(os.path.join(SRC, path))
    node = None
    for c in tree.body:
        if isinstance(c, ast.ClassDef) and c.name == cls:
            for f in c.body:
                if isinstance(f, ast.FunctionDef) and f.name == meth and not f.decorator_list and f.lineno == code.co_firstlineno:
                    node = f
    if node is None:
        return False
    need = {int(k[2:]) for k in allowed if k.startswith("t:")} | {smap[k] for k in allowed if k in smap}
    local = {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del))} | {a.arg for a in ast.walk(node.args) if isinstance(a, ast.arg) and a.arg != "self"}
    body = []
    for i, st in enumerate(node.body):
        if i in need or not _skippable(st, local):
            body.append(st)
        else:
            body.append(ast.copy_location(ast.Pass(), st))
    new = ast.FunctionDef(name=node.name, args=node.args, body=body, decorator_list=[], returns=node.returns, type_comment=None, type_params=[])
    ast.copy_location(new, node)
    mod = ast.Module(body=[new], type_ignores=[])
    ast.fix_missing_locations(mod)
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
    with open(os.path.join(path, "ref.pkl"), "wb") as fh:
        pickle.dump(ref, fh)


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


def child_run(root, test_ids, timeouts, wfd, sel, mode=None):
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
        if mode is not None:
            for m in [m for m in sys.modules if m == "sqlglot" or m.startswith(("sqlglot.", "tests"))]:
                del sys.modules[m]
            if SRC in sys.path:
                sys.path.remove(SRC)
        os.chdir(root)
        sys.path.insert(0, root)
    out = os.fdopen(wfd, "w", buffering=1)

    def emit(tag, tid):
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
    emit("D", "-")
    out.flush()
    os._exit(0)


class Job:
    def __init__(self, cid, root, tests, timeouts, deadline, sel=None, mode=None):
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
                child_run(root, tests, timeouts, w, sel or {}, mode)
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
    unitcpu = json.load(open(os.path.join(HERE, "unitcpu.json"))) if UNITCOST else {"full": {}, "units": {}}
    sys.path.insert(0, HERE)
    from split import split, cost as split_cost

    commits = sorted(p[:-6] for p in os.listdir(os.path.join(DATA, "commits")) if p.endswith(".patch"))
    plans = []
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
                    for n, keys in extra.items():
                        if n in num_to_id:
                            if keys is not None:
                                FRACTION_OK.add(n)
                            merge(cands, {n: keys})
                else:
                    extra, info = itf.extra_candidates(text, root=SRC, with_info=True)
                    merge(cands, full(n for n in extra if n in num_to_id))
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

        def est(n):
            c = unitcpu["full"].get(num_to_id[n], runcpu.get(num_to_id[n], 0)) if cached else runcpu.get(num_to_id[n], 0)
            if not (UNITEST or n in FRACTION_OK) or cands[n] is None or not cov.nunits.get(n):
                return c
            u = cached and unitcpu["units"].get(num_to_id[n])
            if u:
                return min(c, FRAC_K * sum(u.get(k, 0) for k in cands[n]) + FRAC_C)
            return min(c, c * FRAC_K * len(cands[n]) / cov.nunits[n] + FRAC_C)

        heavy = {n for n in cands if n in FORCE_LIST or ms[n] >= HEAVY_MS or (LISTRULE and est(n) * 1000 > ms[n] + 2000)}
        light = sorted(set(cands) - heavy)
        blind = split_cost(sorted(cands), ms)
        cap = blind - split_cost(sorted(heavy), ms)
        over = RUN_O_RE if ("importtime" in notes or any(not r.endswith(".py") for r in patched)) else RUN_O
        if light and (RUN_K * sum(est(n) for n in light) + over) * 1000 >= cap:
            notes.insert(0, "blind")
            heavy, light = set(cands), []
        sel = {num_to_id[n]: (None if cands[n] is None else sorted(cands[n])) for n in light}
        plans.append({"cid": cid, "hunks": hunks_by, "old": old_by, "patched": patched, "light": light, "heavy": heavy, "notes": notes, "ok": ok, "sel": sel, "cap": cap / 1000})
        log(cid, "plancpu=%.2f" % time.process_time(), "cands", len(cands), "partial", sum(1 for n in light if cands[n] is not None), "heavy", sorted(heavy), "est_cpu %.2f" % sum(est(n) for n in light), notes[:4])

    log("planned cpu=%.2f" % time.process_time())
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
            if not rel.endswith(".py") or not rel.startswith(("sqlglot/", "tests/")):
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
    heavy_libs = ("tests/test_executor.py", "tests/test_optimizer.py")
    needs_libs = any(num_to_id[n].startswith(heavy_libs) for p in plans for n in p["light"]) or any(m in ("tests.test_executor", "tests.test_optimizer") for p in plans for m in (p["collect"] or ()))
    if LAZYPANDAS:
        needs_exec = any(num_to_id[n].startswith("tests/test_executor.py") for p in plans for n in p["light"]) or any(m == "tests.test_executor" for p in plans for m in (p["collect"] or ()))
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
        warm_ids = sorted({num_to_id[n] for p in plans for n in p["light"]})
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

        exec_commits = sum(1 for p in plans if any(needs_tables(n) for n in p["light"]))
        zygote.warm(SRC, warm_ids, (TPCWARM or not (TPCREF and LAZYTABLES)) and exec_commits >= (3 if LAZYTABLES else 2 if LAZYEXEC or LEANIMP else 1))
        warm_lines = {p: set(v) for p, v in json.load(open(os.path.join(HERE, "warmmap.json"))).items()}
        code_idx = zygote.code_index({os.path.join(SRC, r) for p in plans for r in p["patched"] if r.endswith(".py")})
        zyg = (zygote, warm_lines, code_idx)
        if GCFREEZE:
            import gc
            _PARSED.clear()
            gc.collect()
            gc.freeze()
        log("zygote warm done t=%.1f cpu=%.2f" % (time.monotonic() - T0, time.process_time()))
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
            try:
                rmtree(root)
                build_overlay(root, p["patched"])
            except Exception as e:
                log(p["cid"], "overlay failed", repr(e))
                results[p["cid"]] = set(num_to_id)
                continue
            ids = [num_to_id[n] for n in p["light"]]
            timeouts = {num_to_id[n]: max(3.0, ms[n] / 1000 * 10 + 2) for n in p["light"]}
            budget = sum(timeouts.values()) + 30
            mode = None
            if zyg is not None:
                mode = ("reimport", p["collect"], [modname_of(r) for r, c in p["patched"].items() if c is not None and p["old"].get(r) is not None and r.startswith("sqlglot/") and r.endswith(".py")])
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
            global CHILD_LAZY, CHILD_PATCHED
            CHILD_PATCHED = list(p["patched"])
            CHILD_LAZY = tpc_lazy(p["patched"])
            p["job"] = Job(p["cid"], root, ids, timeouts, time.monotonic() + budget, p["sel"], mode)
            p["root"] = root
            running.append(p)
        fds = [p["job"].fd for p in running]
        r, _, _ = select.select(fds, [], [], 0.5)
        for p in list(running):
            job = p["job"]
            if job.fd in r:
                job.feed()
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
                results[p["cid"]] = fail | set(p["heavy"])
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
