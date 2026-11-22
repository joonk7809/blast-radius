import ast
import gzip
import json
import os
import sys
reads_p, fp_p, cov_p, root, out_p = sys.argv[1:6]
R = json.load(gzip.open(reads_p, 'rt'))
FP = json.load(gzip.open(fp_p, 'rt'))
COV = json.load(gzip.open(cov_p, 'rt'))
STAR = '\x01*'
entries, per = (R['entries'], R['per'])
ent_tests = [set() for _ in entries]
for t, lst in enumerate(per):
    for j in lst:
        ent_tests[j].add(t)
attr, recv, key, star = ({}, {}, {}, {})

def add(d, k, ts):
    d.setdefault(k, set()).update(ts)
aliases = R.get('tids', {})
for e, ts in zip(entries, ent_tests):
    if not ts:
        continue
    if e[0] == 'A':
        _, holder, a, receiver = e
        add(attr, holder + '\x00' + a, ts)
        add(recv, receiver + '\x00' + a, ts)
        add(recv, receiver + '\x00*', ts)
    else:
        _, tid, k = e
        tids = aliases.get(tid, [tid])
        for t2 in tids:
            if k == STAR:
                add(star, t2, ts)
            else:
                add(key, t2 + '\x00' + k, ts)
                if t2.startswith('D|'):
                    add(star, t2, ts)
modules = FP['modules']
mod_file = {}
for m in modules:
    p = m.replace('.', '/')
    f = p + '.py' if os.path.exists(os.path.join(root, p + '.py')) else p + '/__init__.py'
    mod_file[m] = f
file_mod = {f: m for m, f in mod_file.items()}

def cov_lines(rel, lines):
    fm = COV['files'].get(rel)
    out = set()
    if not fm:
        return out
    for ln in lines:
        s = fm['lines'].get(str(ln))
        if s is not None:
            out.update(COV['sets'][s])
    return out
globals_by_mod = {}
for p in FP['fp']:
    if p.startswith('G|') or p.startswith('F|'):
        _, m, name = p.split('|', 2)
        if m in mod_file:
            globals_by_mod.setdefault(m, set()).add(name)
refs = {}
for m, rel in mod_file.items():
    try:
        tree = ast.parse(open(os.path.join(root, rel)).read())
    except Exception:
        continue
    name_src = {}
    mod_alias = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module
            if node.level:
                pk = m.split('.')
                if not rel.endswith('__init__.py'):
                    pk = pk[:-1]
                pk = pk[:len(pk) - (node.level - 1)] if node.level > 1 else pk
                base = '.'.join(pk + ([node.module] if node.module else []))
            for a in node.names:
                full = base + '.' + a.name
                if full in mod_file:
                    mod_alias[a.asname or a.name] = full
                else:
                    name_src[a.asname or a.name] = (base, a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name in mod_file:
                    mod_alias[a.asname or a.name.split('.')[0]] = a.name if a.asname else a.name.split('.')[0]
    stmt_of = {}
    for st in ast.walk(tree):
        if isinstance(st, ast.stmt):
            for ch in ast.walk(st):
                if isinstance(ch, (ast.Name, ast.Attribute)):
                    prev = stmt_of.get(id(ch))
                    if prev is None or st.lineno >= prev.lineno:
                        stmt_of[id(ch)] = st
    own = globals_by_mod.get(m, set())
    for node in ast.walk(tree):
        tgt = None
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            if node.id in own:
                tgt = (m, node.id)
            elif node.id in name_src:
                src = name_src[node.id]
                tgt = src
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            mm = mod_alias.get(node.value.id)
            if mm:
                tgt = (mm, node.attr)
        if tgt is None:
            continue
        st = stmt_of.get(id(node))
        lines = {node.lineno}
        if st is not None:
            lines.add(st.lineno)
        refs.setdefault(tgt, set()).update(((rel, ln) for ln in lines))
        if isinstance(node, ast.Name) and node.id in name_src:
            refs.setdefault((m, node.id), set()).update(((rel, ln) for ln in lines))
modglob = {}
for (m, name), locs in refs.items():
    byfile = {}
    for rel, ln in locs:
        byfile.setdefault(rel, set()).add(ln)
    ts = set()
    for rel, lns in byfile.items():
        ts |= cov_lines(rel, lns)
    if ts:
        modglob[f'{m}|{name}'] = ts
sets, idx = ([], {})

def intern(ts):
    k = tuple(sorted(ts))
    if k not in idx:
        idx[k] = len(sets)
        sets.append(list(k))
    return idx[k]
out = {'attr': {k: intern(v) for k, v in attr.items()}, 'recv': {k: intern(v) for k, v in recv.items()}, 'key': {k: intern(v) for k, v in key.items()}, 'star': {k: intern(v) for k, v in star.items()}, 'modglob': {k: intern(v) for k, v in modglob.items()}, 'mro': FP['mro'], 'owns': FP['owns']}
out['sets'] = [','.join(map(str, x)) for x in sets]
with gzip.open(out_p, 'wt') as f:
    json.dump(out, f, separators=(',', ':'))
print('attr', len(attr), 'recv', len(recv), 'key', len(key), 'star', len(star), 'modglob', len(modglob), 'sets', len(sets), file=sys.stderr)
