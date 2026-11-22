import ast, json, os, sys

root, out = sys.argv[1:3]


def containers(tree):
    mod = set()
    for node in tree.body:
        for t in node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) and node.value is not None else []:
            if isinstance(t, ast.Name) and isinstance(node.value, (ast.Dict, ast.Set, ast.List, ast.DictComp)) or isinstance(t, ast.Name) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id in ("dict", "set", "list", "defaultdict", "OrderedDict"):
                mod.add(t.id)
    cls = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for st in node.body:
                for t in st.targets if isinstance(st, ast.Assign) else [st.target] if isinstance(st, ast.AnnAssign) and st.value is not None else []:
                    if isinstance(t, ast.Name) and isinstance(st.value, (ast.Dict, ast.Set, ast.List)):
                        cls.setdefault(node.name, set()).add(t.id)
    return mod, cls


def shared(expr, mod, cls, owner):
    if isinstance(expr, ast.Name):
        return expr.id in mod
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        if expr.value.id == "cls" and owner is not None:
            return expr.attr in cls.get(owner, ())
        return expr.attr in cls.get(expr.value.id, ())
    return False


def memo_reads(fn, mod, cls, owner):
    got = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == "get" and shared(node.value.func.value, mod, cls, owner):
            got[node.targets[0].id] = node.lineno
    return got


def guards(fn, mod, cls, owner):
    loaded = memo_reads(fn, mod, cls, owner)
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        t = node.test
        if isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.NotIn) and shared(t.comparators[0], mod, cls, owner):
            yield node, [node.lineno]
        elif isinstance(t, ast.Compare) and len(t.ops) == 1 and isinstance(t.ops[0], ast.Is) and isinstance(t.left, ast.Name) and t.left.id in loaded and isinstance(t.comparators[0], ast.Constant) and t.comparators[0].value is None:
            yield node, [loaded[t.left.id], node.lineno]


def scan(path):
    tree = ast.parse(open(os.path.join(root, path)).read())
    mod, cls = containers(tree)
    funcs, methods = {}, {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = node
        if isinstance(node, ast.ClassDef):
            for st in node.body:
                if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[(node.name, st.name)] = st
    memo, lazy = [], []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "__getattr__" and any(isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name) and n.value.func.id == "globals" for n in ast.walk(node)):
            lazy.append([node.lineno, node.end_lineno])
    for (owner, _), fn in [((None, None), f) for f in funcs.values()] + list(methods.items()):
        for g, readers in guards(fn, mod, cls, owner):
            fill, todo, seen, writes = [[g.body[0].lineno, g.body[-1].end_lineno]], list(g.body), set(), False
            while todo:
                for n in ast.walk(todo.pop()):
                    if isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store) and shared(n.value, mod, cls, owner):
                        writes = True
                    if not isinstance(n, ast.Call):
                        continue
                    f = n.func
                    tgt = funcs.get(f.id) if isinstance(f, ast.Name) else methods.get((owner, f.attr)) if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in ("cls", "self") else None
                    if tgt is not None and id(tgt) not in seen:
                        seen.add(id(tgt))
                        fill.append([tgt.body[0].lineno, tgt.end_lineno])
                        todo.extend(tgt.body)
            if writes:
                memo.append([fill, readers])
    return memo, lazy


sites = {}
for dirpath, dirs, files in os.walk(os.path.join(root, "sqlglot")):
    dirs[:] = sorted(d for d in dirs if d != "__pycache__")
    for f in sorted(files):
        if f.endswith(".py"):
            rel = os.path.relpath(os.path.join(dirpath, f), root)
            memo, lazy = scan(rel)
            if memo or lazy:
                sites[rel] = {"memo": memo, "lazy": lazy}
json.dump(sites, open(out, "w"), indent=1)
for p, s in sites.items():
    print(p, s, file=sys.stderr)
