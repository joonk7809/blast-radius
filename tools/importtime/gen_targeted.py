import ast, os, random, sys
sys.argv, args = (sys.argv[:1], sys.argv[1:])
import gen_mutants as G
rng = random.Random(int(args[0]))
N = int(args[1])
G.OUT = args[2]
os.makedirs(G.OUT, exist_ok=True)
FILES = ['sqlglot/generator.py', 'sqlglot/parser.py', 'sqlglot/tokens.py', 'sqlglot/dialects/duckdb.py', 'sqlglot/dialects/dialect.py', 'sqlglot/executor/python.py', 'sqlglot/executor/env.py', 'sqlglot/optimizer/simplify.py', 'sqlglot/optimizer/annotate_types.py', 'sqlglot/optimizer/qualify_columns.py', 'sqlglot/expressions.py', 'sqlglot/typing/__init__.py']
FILES = [f for f in FILES if os.path.exists(os.path.join(G.SRC, f))]
pool = []
for p in FILES:
    src = G.read(p)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            real = [(k, v) for k, v in zip(node.keys, node.values) if k is not None]
            if len(real) >= 2:
                for k, v in real:
                    pool.append(('d', p, node, real, k, v))
        elif isinstance(node, ast.Set) and len(node.elts) >= 2:
            for e in node.elts:
                if not isinstance(e, ast.Starred):
                    pool.append(('s', p, node, node.elts, e, None))
rng.shuffle(pool)
made, seen = ([], set())
for kind, p, node, real, k, v in pool:
    if len(made) >= N:
        break
    src = G.read(p)
    try:
        if kind == 'd':
            if isinstance(v, ast.Constant) and isinstance(v.value, bool):
                new, tag = (G.replace_segment(src, v, str(not v.value)), 'flip')
            elif rng.random() < 0.5:
                k2, v2 = rng.choice([x for x in real if x[1] is not v])
                if G.seg(src, v2) == G.seg(src, v):
                    continue
                new, tag = (G.replace_segment(src, v, G.seg(src, v2)), 'dswap')
            else:
                lines = src.splitlines(keepends=True)
                if k.lineno == v.end_lineno and lines[k.lineno - 1].rstrip().endswith(',') and lines[k.lineno - 1].strip().startswith(G.seg(src, k)):
                    del lines[k.lineno - 1]
                    new, tag = (''.join(lines), 'ddel')
                else:
                    continue
        else:
            lines = src.splitlines(keepends=True)
            if k.lineno == k.end_lineno and lines[k.lineno - 1].strip() == G.seg(src, k) + ',':
                del lines[k.lineno - 1]
                new, tag = (''.join(lines), 'sdel')
            else:
                continue
        if new in seen or new == src:
            continue
        compile(new, p, 'exec')
    except Exception:
        continue
    seen.add(new)
    name = 'u%03d_%s' % (len(made), tag)
    G.write(name, p, src, new)
    made.append(name)
print(len(made))
