import gzip
import json
import os
import sys
root, ie_p, out_p = sys.argv[1:4]
root = os.path.abspath(root)
sys.path.insert(0, root)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..'))
os.environ.setdefault('IDS', '/home/user/ids.txt')
import importtime as IT
import attrtrace as AT
IE = json.load(gzip.open(ie_p, 'rt'))['files']
cnt = {}
for f, ls in IE.items():
    if f in ('sqlglot/parser.py', 'sqlglot/tokenizer_core.py', 'sqlglot/generator.py'):
        for l, ms in ls.items():
            for m in ms:
                cnt[m] = cnt.get(m, 0) + 1
heavy = sorted((m for m, c in cnt.items() if c >= 20 and m not in ('sqlglot.dialects.dialect', 'sqlglot.tokens', 'sqlglot.parser')))
print('heavy importers:', heavy, file=sys.stderr)
core = ['sqlglot', 'sqlglot.expressions', 'sqlglot.tokens', 'sqlglot.parser', 'sqlglot.generator', 'sqlglot.dialects.dialect', 'sqlglot.optimizer.annotate_types', 'sqlglot.typing']
IT.import_all(core)
loaded = sorted((n for n in sys.modules if n.startswith('sqlglot')))
reg, classes = IT.build_registry(loaded)
AT.REG.update(reg)
for name, cls in classes:
    import enum
    import types
    if issubclass(cls, enum.Enum):
        continue
    for k, v in list(cls.__dict__.items()):
        if k in IT.SKIP_CLASS_KEYS or (k.startswith('__') and k.endswith('__')):
            continue
        if isinstance(v, (type, types.ModuleType)) or callable(v) or hasattr(type(v), '__get__'):
            continue
        try:
            setattr(cls, k, AT.Desc(name, k, AT.wrap_value(v, f'{name}|{k}')))
        except Exception:
            pass
byid = {}
for n in loaded:
    m = sys.modules.get(n)
    for k, v in list(vars(m).items()):
        if k.startswith('__') or type(v) not in (dict, set, frozenset) or 'CACHE' in k.upper():
            continue
        byid.setdefault(id(v), (v, []))[1].append((n, k))
for _, (v, binds) in byid.items():
    w = AT.wrap_value(v, f'M|{binds[0][0]}|{binds[0][1]}')
    for n, k in binds:
        setattr(sys.modules[n], k, w)
out = {}
import importlib
PREF = os.path.join(root, 'sqlglot') + os.sep

class _Rec:

    def __init__(self):
        self.items = []

    def add(self, item):
        f = sys._getframe(1)
        while f is not None:
            co = f.f_code
            if co.co_name == '<module>' and co.co_filename.startswith(PREF):
                self.items.append((item, f.f_globals.get('__name__')))
                return
            f = f.f_back

    def clear(self):
        self.items = []
REC = _Rec()
AT.CUR = REC
for h in heavy:
    if h in sys.modules:
        print('already imported (skipped):', h, file=sys.stderr)
        continue
    REC.clear()
    AT.ON[0] = True
    try:
        importlib.import_module(h)
    except Exception as e:
        print('import failed', h, e, file=sys.stderr)
    AT.ON[0] = False
    for raw, owner in REC.items:
        e = next(iter(AT._translate([raw])), None)
        if e is None or owner is None:
            continue
        if e[0] == 'A':
            key = 'A\x00' + e[1] + '\x00' + e[2]
        else:
            if e[2] == AT.STAR:
                continue
            key = 'K\x00' + e[1] + '\x00' + e[2]
        out.setdefault(key, set()).add(owner)
with gzip.open(out_p, 'wt') as f:
    json.dump({'entries': {k: sorted(v) for k, v in out.items()}, 'heavy': heavy}, f, separators=(',', ':'))
print('entries', len(out), file=sys.stderr)
