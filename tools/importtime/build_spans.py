import ast
import gzip
import json
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import importtime as IT
root, fp_p, out_p = sys.argv[1:4]
FP = json.load(gzip.open(fp_p, 'rt'))
classnames = {}
for name in FP['mro']:
    simple = name.rsplit('.', 1)[-1]
    prev = classnames.get(simple)
    if prev is None or (name.startswith('sqlglot.expressions') and (not prev.startswith('sqlglot.expressions'))):
        classnames[simple] = name
enum_names = set()
for p in FP['fp']:
    if p.startswith('A|') and p.endswith('|__members__'):
        enum_names.add(p.split('|')[1].rsplit('.', 1)[-1])
enum_alias = {n: n for n in enum_names}
enum_alias.setdefault('Type', 'DType') if 'DType' in enum_names else None
ctx = {'classnames': classnames, 'enum_alias': enum_alias}

def stored_names(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, (ast.Subscript, ast.Attribute)) and isinstance(n.ctx, ast.Store):
            b = n.value
            while isinstance(b, (ast.Subscript, ast.Attribute)):
                b = b.value
            if isinstance(b, ast.Name):
                out.add(b.id)
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name):
            if n.func.attr in ('update', 'pop', 'add', 'discard', 'remove', 'append', 'extend', 'setdefault', 'clear', 'insert'):
                out.add(n.func.value.id)
    return sorted(out)

def nodes_of(body):
    out = []
    for st in body:
        start = min([st.lineno] + [d.lineno for d in getattr(st, 'decorator_list', [])])
        if isinstance(st, ast.ClassDef):
            out.append(['C', [st.name], start, st.end_lineno, st.body[0].lineno - 1, nodes_of(st.body)])
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(['D', [st.name], start, st.end_lineno, st.body[0].lineno - 1, []])
        elif isinstance(st, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            tg = st.targets if isinstance(st, ast.Assign) else [st.target]
            names = sorted({n.id for t in tg for n in ast.walk(t) if isinstance(n, ast.Name)})
            out.append(['A' if not isinstance(st, ast.AugAssign) else 'O', names, start, st.end_lineno, None, []])
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            out.append(['I', sorted((a.asname or a.name.split('.')[0] for a in st.names)), start, st.end_lineno, None, []])
        else:
            out.append(['O', stored_names(st), start, st.end_lineno, None, []])
    return out

def ref_names(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add((n.id, None))
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
            v = n.value
            q = v.id if isinstance(v, ast.Name) else v.attr if isinstance(v, ast.Attribute) else '?'
            out.add((n.attr, q))
    return out
KP_FUNCS = {'set', 'frozenset', 'dict', 'list', 'tuple', 'sorted'}

def kp_names(v):
    out = set()
    par = {}
    for n in ast.walk(v):
        for c in ast.iter_child_nodes(n):
            par[id(c)] = n
    for n in ast.walk(v):
        if not isinstance(n, (ast.Name, ast.Attribute)) or not isinstance(n.ctx, ast.Load):
            continue
        key = (n.id, None) if isinstance(n, ast.Name) else (n.attr, n.value.id if isinstance(n.value, ast.Name) else n.value.attr if isinstance(n.value, ast.Attribute) else '?')
        p = par.get(id(n))
        if n is v:
            out.add(key)
        elif isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and (p.func.id in KP_FUNCS) and (n in p.args):
            out.add(key)
        elif isinstance(p, ast.Starred) or (isinstance(p, ast.BinOp) and isinstance(p.op, (ast.BitOr, ast.Sub, ast.BitAnd))):
            out.add(key)
        elif isinstance(p, ast.Attribute) and p.attr in ('copy', 'keys'):
            out.add(key)
    return out
SKIP_REF = {'exp', 't', 'TokenType', 'self', 'e', 'args', 'seq_get', 'True', 'False', 'None', 'DType', 'kwargs', 'expression', 'dialect', 'this', 'sql', 'isinstance', 'len', 'str', 'dict', 'set', 'list', 'tuple', 'k', 'v', 'x'}
refs = {}

def add_ref(nq, rec):
    name, q = nq
    if name in SKIP_REF or (q is None and (name in classnames or name in enum_alias)):
        return
    refs.setdefault(name, []).append(rec + [q])

def file_aliases(tree, mod, rel):
    al = {}
    pkg = mod.split('.') if rel.endswith('__init__.py') else mod.split('.')[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                pk = pkg[:len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                base = '.'.join(pk + ([node.module] if node.module else []))
            for a in node.names:
                al[a.asname or a.name] = base + '.' + a.name
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    al[a.asname] = a.name
                else:
                    al[a.name.split('.')[0]] = a.name.split('.')[0]
    for st in tree.body:
        if isinstance(st, ast.ClassDef):
            al[st.name] = mod + '.' + st.name
    return al
MRO = FP['mro']

def resolve_qual(dotted, al, mod, owner):
    if not dotted or dotted == '?':
        return None
    parts = dotted.split('.')
    if parts[0] in ('self', 'cls', 'klass'):
        return None
    base = al.get(parts[0])
    if base is None:
        if owner and parts[0] == owner.split('.')[-1]:
            base = mod + '.' + owner
        else:
            return None
    full = '.'.join([base] + parts[1:])
    if full in MRO:
        return full
    c = classnames.get(parts[-1])
    if c and c.startswith(base.rsplit('.', 1)[0] if base.count('.') > 1 else base):
        return c
    return None

def ref_names_q(node):
    out = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            out.add((n.id, None))
        elif isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Load):
            d = IT._dotted(n.value)
            out.add((n.attr, '.'.join(d) if d else '?'))
    return out

def index_refs(rel, body, owner, al, mod):

    def add(nq, rec):
        name, q = nq
        if name in SKIP_REF or (q is None and (name in classnames or name in enum_alias)):
            return
        refs.setdefault(name, []).append(rec + [q, resolve_qual(q, al, mod, owner) if q else None])
    for st in body:
        if isinstance(st, ast.ClassDef):
            q = owner + '.' + st.name if owner else st.name
            for b in st.bases + st.keywords + st.decorator_list:
                for n in ref_names_q(b):
                    add(n, [rel, q, '<bases>', None])
            index_refs(rel, st.body, q, al, mod)
            continue
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = st.args
            for d in a.defaults + [x for x in a.kw_defaults if x is not None] + st.decorator_list:
                for n in ref_names_q(d):
                    add(n, [rel, owner, st.name, '<def>'])
            continue
        if isinstance(st, (ast.Assign, ast.AnnAssign)) and st.value is not None:
            tg = st.targets if isinstance(st, ast.Assign) else [st.target]
            names = [t.id for t in tg if isinstance(t, ast.Name)]
            v = IT.unwrap_filter_comp(st.value)
            for attr in names:
                if isinstance(v, ast.Dict):
                    for k, val in zip(v.keys, v.values):
                        if k is None:
                            fk = IT.fromkeys_entries(val, ctx)
                            if fk is not None:
                                for kn2 in fk:
                                    for n in ref_names_q(val):
                                        add(n, [rel, owner, attr, kn2])
                                continue
                        kn = IT.ast_kname(k, ctx) if k is not None else '<spread>' if isinstance(IT.unwrap_filter_comp(val), (ast.Name, ast.Attribute)) else None
                        for n in ref_names_q(val) | (ref_names_q(k) if k is not None else set()):
                            add(n, [rel, owner, attr, kn])
                elif isinstance(v, ast.Set):
                    for e in v.elts:
                        kn = IT.ast_kname(e, ctx) if not isinstance(e, ast.Starred) else '<spread>'
                        for n in ref_names_q(e):
                            add(n, [rel, owner, attr, kn])
                else:
                    kp = {x[0] for x in kp_names(v)}
                    for n in ref_names_q(v):
                        add(n, [rel, owner, attr, '<kp>' if n[0] in kp else None])
            continue
        if isinstance(st, (ast.Import, ast.ImportFrom)):
            continue
        is_mut = isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute) and (st.value.func.attr in ('pop', 'discard', 'remove', 'add')) and all((isinstance(x, ast.Constant) for x in st.value.args))
        for attr in stored_names(st):
            for n in ref_names_q(st):
                add(n, [rel, owner, attr, '<kp>' if is_mut else None])
importers = {}

def index_importers(tree, m, rel):
    al = file_aliases(tree, m, rel)
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                full = al.get(a.asname or a.name)
                if full and '.' in full:
                    src_mod, nm = full.rsplit('.', 1)
                    importers.setdefault(src_mod + '|' + nm, []).append(m + '|' + (a.asname or a.name))
spans = {}
for m in FP['modules']:
    p = m.replace('.', '/')
    rel = p + '.py' if os.path.exists(os.path.join(root, p + '.py')) else p + '/__init__.py'
    tree = ast.parse(open(os.path.join(root, rel)).read())
    spans[rel] = nodes_of(tree.body)
    index_refs(rel, tree.body, '', file_aliases(tree, m, rel), m)
    index_importers(tree, m, rel)
refs = {k: v for k, v in refs.items() if len(v) <= 5000}
with gzip.open(out_p, 'wt') as f:
    json.dump({'spans': spans, 'refs': refs, 'classnames': classnames, 'enum_alias': enum_alias, 'lines': FP['lines'], 'expr_classes': FP['expr_classes'], 'importers': importers}, f, separators=(',', ':'))
print('files', len(spans), 'refnames', len(refs), file=sys.stderr)
