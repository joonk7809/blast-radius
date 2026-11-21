import ast, difflib, os, random, sys
SRC = '/home/user/sqlglot'
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'mutants')
os.makedirs(OUT, exist_ok=True)
rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 1234)
PREFIX = sys.argv[2] if len(sys.argv) > 2 else 'm'

def pyfiles():
    for root, dirs, files in os.walk(os.path.join(SRC, 'sqlglot')):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in sorted(files):
            if f.endswith('.py'):
                yield os.path.relpath(os.path.join(root, f), SRC)

def read(p):
    return open(os.path.join(SRC, p)).read()

def mkpatch(path, old, new):
    a = old.splitlines(keepends=True)
    b = new.splitlines(keepends=True)
    d = ''.join(difflib.unified_diff(a, b, f'a/{path}', f'b/{path}', n=3))
    return f'diff --git a/{path} b/{path}\n' + d

def write(name, path, old, new):
    assert old != new
    compile(new, path, 'exec')
    with open(os.path.join(OUT, name + '.patch'), 'w') as f:
        f.write(mkpatch(path, old, new))

def replace_segment(src, node, newtext):
    lines = src.splitlines(keepends=True)
    off = [0]
    for l in lines:
        off.append(off[-1] + len(l))
    s = off[node.lineno - 1] + node.col_offset
    e = off[node.end_lineno - 1] + node.end_col_offset
    return src[:s] + newtext + src[e:]

def seg(src, node):
    return ast.get_source_segment(src, node)
made = []

def main():
    global made
    bool_flags, dict_entries, argtypes, set_members, mod_consts = ([], [], [], [], [])
    for p in pyfiles():
        src = read(p)
        tree = ast.parse(src)
        for top in tree.body:
            if isinstance(top, (ast.Assign, ast.AnnAssign)) and top.value is not None:
                tgt = top.targets[0] if isinstance(top, ast.Assign) else top.target
                if isinstance(tgt, ast.Name) and tgt.id.isupper():
                    mod_consts.append((p, top))
        for cls in ast.walk(tree):
            if not isinstance(cls, ast.ClassDef):
                continue
            for st in cls.body:
                if not isinstance(st, (ast.Assign, ast.AnnAssign)) or st.value is None:
                    continue
                tgt = st.targets[0] if isinstance(st, ast.Assign) else st.target
                if not isinstance(tgt, ast.Name):
                    continue
                v = st.value
                if isinstance(v, ast.Constant) and isinstance(v.value, bool):
                    bool_flags.append((p, cls.name, tgt.id, v))
                if tgt.id == 'arg_types' and isinstance(v, ast.Dict):
                    for k, val in zip(v.keys, v.values):
                        if isinstance(val, ast.Constant) and isinstance(val.value, bool):
                            argtypes.append((p, cls.name, val))
                elif isinstance(v, ast.Dict) and len(v.keys) >= 3:
                    real = [(k, val) for k, val in zip(v.keys, v.values) if k is not None]
                    if len(real) >= 3:
                        dict_entries.append((p, cls.name, tgt.id, v, real))
                elif isinstance(v, (ast.Set, ast.BinOp)):
                    elts = []
                    if isinstance(v, ast.Set):
                        elts = [e for e in v.elts if not isinstance(e, ast.Starred)]
                    elif isinstance(v.right, ast.Set):
                        elts = [e for e in v.right.elts if not isinstance(e, ast.Starred)]
                    if len(elts) >= 2:
                        set_members.append((p, cls.name, tgt.id, elts))

    def emit(kind, p, newsrc):
        name = f'{PREFIX}{len(made):02d}_{kind}'
        write(name, p, read(p), newsrc)
        made.append(name)
    N = dict(bool=12, dict_swap=6, dict_del=4, argt=6, setdel=6, modc=4)
    for p, c, n, v in rng.sample(bool_flags, N['bool']):
        src = read(p)
        emit('bool', p, replace_segment(src, v, str(not v.value)))
    for p, c, n, d, real in rng.sample(dict_entries, N['dict_swap']):
        src = read(p)
        (k1, v1), (k2, v2) = rng.sample(real, 2)
        if seg(src, v1) == seg(src, v2):
            continue
        emit('dswap', p, replace_segment(src, v1, seg(src, v2)))
    for p, c, n, d, real in rng.sample(dict_entries, N['dict_del']):
        src = read(p)
        k, v = rng.choice(real)
        lines = src.splitlines(keepends=True)
        if k.lineno != v.end_lineno or lines[k.lineno - 1].strip().count(':') < 1:
            emit('dnone', p, replace_segment(src, v, 'None'))
            continue
        line = lines[k.lineno - 1]
        if not line.rstrip().endswith(','):
            emit('dnone', p, replace_segment(src, v, 'None'))
            continue
        del lines[k.lineno - 1]
        emit('ddel', p, ''.join(lines))
    for p, c, v in rng.sample(argtypes, N['argt']):
        src = read(p)
        emit('argt', p, replace_segment(src, v, str(not v.value)))
    for p, c, n, elts in rng.sample(set_members, N['setdel']):
        src = read(p)
        e = rng.choice(elts)
        lines = src.splitlines(keepends=True)
        line = lines[e.lineno - 1]
        if e.lineno == e.end_lineno and line.strip() == seg(src, e) + ',':
            del lines[e.lineno - 1]
            emit('sdel', p, ''.join(lines))
        else:
            other = rng.choice([x for x in elts if x is not e])
            emit('ssub', p, replace_segment(src, e, seg(src, other)))
    cands = [x for x in mod_consts if isinstance(x[1].value, (ast.Dict, ast.Set, ast.Tuple, ast.Constant))]
    for p, st in rng.sample(cands, N['modc'] * 3):
        if sum((1 for m in made if m.endswith('modc'))) >= N['modc']:
            break
        src = read(p)
        v = st.value
        if isinstance(v, ast.Constant):
            if isinstance(v.value, str):
                new = replace_segment(src, v, repr(v.value + '_x'))
            elif isinstance(v.value, bool):
                new = replace_segment(src, v, str(not v.value))
            elif isinstance(v.value, int):
                new = replace_segment(src, v, str(v.value + 1))
            else:
                continue
        else:
            elts = v.values if isinstance(v, ast.Dict) else v.elts
            elts = [e for e in elts if e is not None and (not isinstance(e, ast.Starred))]
            if len(elts) < 2:
                continue
            e, o = rng.sample(elts, 2)
            if seg(src, e) == seg(src, o):
                continue
            new = replace_segment(src, e, seg(src, o))
        emit('modc', p, new)
    print('\n'.join(made))
if __name__ == '__main__':
    main()
