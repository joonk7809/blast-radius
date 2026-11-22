from __future__ import annotations
import ast
import enum
import gzip
import hashlib
import json
import os
import re
import sys
import types
HERE = os.path.dirname(os.path.abspath(__file__))
MAPDIR = os.environ.get('IMPORTTIME_MAPS', os.path.join(HERE, 'maps'))
SQLGLOT_ROOT = os.environ.get('IMPORTTIME_SQLGLOT', '/sqlglot')
SKIP_CLASS_KEYS = {'__dict__', '__weakref__', '__module__', '__qualname__', '__doc__', '__annotations__', '__firstlineno__', '__static_attributes__', '__orig_bases__', '__parameters__', '_abc_impl', '__slots__', '__annotate__', '__annotate_func__', '__annotations_cache__', '__match_args__'}

def module_names(root):
    out = []
    base = os.path.join(root, 'sqlglot')
    for r, dirs, files in os.walk(base):
        dirs[:] = sorted((d for d in dirs if d != '__pycache__'))
        for f in sorted(files):
            if not f.endswith('.py') or f == '__main__.py':
                continue
            rel = os.path.relpath(os.path.join(r, f), root)[:-3].replace(os.sep, '.')
            if rel.endswith('.__init__'):
                rel = rel[:-len('.__init__')]
            out.append(rel)
    return sorted(out)

def import_all(names):
    import importlib
    mods = {}
    for n in names:
        try:
            mods[n] = importlib.import_module(n)
        except Exception as e:
            mods[n] = None
    return mods

def _resolve(modname, qual):
    m = sys.modules.get(modname)
    obj = m
    for part in qual.split('.'):
        obj = getattr(obj, part, None) if obj is not None else None
        if obj is None:
            return None
    return obj

def build_registry(modnames):
    reg, classes = ({}, [])

    def add(cls, name):
        if id(cls) in reg:
            return False
        reg[id(cls)] = name
        classes.append((name, cls))
        return True
    mods = [(n, sys.modules[n]) for n in modnames if sys.modules.get(n) is not None]
    for n, m in mods:
        for k in sorted(vars(m)):
            v = vars(m)[k]
            if isinstance(v, type) and getattr(v, '__module__', '').startswith('sqlglot'):
                q = getattr(v, '__qualname__', '')
                if '<' not in q and _resolve(v.__module__, q) is v:
                    add(v, f'{v.__module__}.{q}')
    i = 0
    while i < len(classes):
        name, cls = classes[i]
        i += 1
        d = cls.__dict__
        for k in sorted(d):
            v = d[k]
            if isinstance(v, type) and getattr(v, '__module__', '').startswith('sqlglot'):
                q = getattr(v, '__qualname__', '')
                if '<' not in q and _resolve(v.__module__, q) is v:
                    add(v, f'{v.__module__}.{q}')
                else:
                    add(v, f'{name}.{k}')
    for n, m in mods:
        for k in sorted(vars(m)):
            v = vars(m)[k]
            if isinstance(v, type) and getattr(v, '__module__', '').startswith('sqlglot'):
                add(v, f'{n}.{k}')
    return (reg, classes)

def kname(k, reg):
    if isinstance(k, str):
        return k
    if isinstance(k, enum.Enum):
        return f'E:{type(k).__name__}.{k.name}'
    if isinstance(k, type):
        n = reg.get(id(k))
        return 'C:' + (n or f"{getattr(k, '__module__', '?')}.{getattr(k, '__qualname__', '?')}")
    if isinstance(k, tuple):
        return 'T:(' + ','.join((kname(x, reg) for x in k)) + ')'
    if isinstance(k, (int, float, bool)) or k is None:
        return 'V:' + repr(k)
    r = repr(k)
    if ' at 0x' in r:
        r = type(k).__qualname__
    return 'R:' + r[:200]

class Fingerprinter:

    def __init__(self, reg, unordered=False):
        self.reg = reg
        self.memo = {}
        self.unordered = unordered

    def code(self, co, depth=0):
        parts = [co.co_qualname, co.co_code.hex(), repr(co.co_names), repr(co.co_varnames), repr(co.co_freevars), str(co.co_argcount), str(co.co_kwonlyargcount), str(co.co_flags)]
        for c in co.co_consts:
            if isinstance(c, types.CodeType):
                parts.append(self.code(c, depth + 1) if depth < 6 else c.co_qualname)
            else:
                parts.append(self.fp(c, 4))
        return '|'.join(parts)

    def func(self, f, depth, with_code):
        parts = ['fn', getattr(f, '__module__', '') or '', f.__qualname__]
        co = f.__code__
        if with_code or '<' in f.__qualname__:
            parts.append(self.code(co))
        else:
            parts += [str(co.co_argcount), str(co.co_kwonlyargcount), repr(co.co_varnames[:co.co_argcount + co.co_kwonlyargcount]), str(co.co_flags & 12)]
        if f.__defaults__:
            parts.append(self.fp(f.__defaults__, depth - 1))
        if f.__kwdefaults__:
            parts.append(self.fp(f.__kwdefaults__, depth - 1))
        if f.__closure__:
            for c in f.__closure__:
                try:
                    parts.append(self.fp(c.cell_contents, depth - 1))
                except ValueError:
                    parts.append('<empty>')
        return '(' + ';'.join(parts) + ')'

    def fp(self, v, depth=6):
        if v is None or isinstance(v, (bool, int, float, complex, str, bytes)):
            if isinstance(v, enum.Enum):
                return f'E:{type(v).__name__}.{v.name}'
            return repr(v) if not isinstance(v, str) or len(v) < 300 else 's' + hashlib.md5(v.encode()).hexdigest()
        if isinstance(v, enum.Enum):
            return f'E:{type(v).__name__}.{v.name}'
        if isinstance(v, type):
            n = self.reg.get(id(v))
            return 'C:' + (n or f"{getattr(v, '__module__', '?')}.{getattr(v, '__qualname__', '?')}")
        if depth <= 0:
            return '~' + type(v).__name__
        key = id(v)
        r = self.memo.get(key)
        if r is not None and r[0] is v:
            return r[1]
        out = self._fp(v, depth)
        self.memo[key] = (v, out)
        return out

    def _fp(self, v, depth):
        if isinstance(v, types.FunctionType):
            return self.func(v, depth, with_code=False)
        if isinstance(v, types.MethodType):
            return 'm(' + self.fp(v.__func__, depth) + '@' + self.fp(v.__self__ if isinstance(v.__self__, type) else type(v.__self__), depth) + ')'
        if isinstance(v, (types.BuiltinFunctionType, types.BuiltinMethodType)):
            s = getattr(v, '__self__', None)
            own = '' if s is None or isinstance(s, types.ModuleType) else self.fp(s if isinstance(s, type) else type(s), 2)
            return f"b:{getattr(v, '__module__', '')}.{v.__qualname__}{own}"
        if isinstance(v, (classmethod, staticmethod)):
            return type(v).__name__ + '(' + self.fp(v.__func__, depth) + ')'
        if isinstance(v, property):
            return 'prop(' + ','.join((self.fp(x, depth) for x in (v.fget, v.fset, v.fdel))) + ')'
        if isinstance(v, dict):
            items = sorted(((kname(k, self.reg), self.fp(x, depth - 1)) for k, x in v.items()))
            return '{' + ','.join((f'{a}:{b}' for a, b in items)) + '}'
        if isinstance(v, (set, frozenset)):
            return type(v).__name__ + '{' + ','.join(sorted((self.fp(x, depth - 1) for x in v))) + '}'
        if isinstance(v, (list, tuple)):
            el = [self.fp(x, depth - 1) for x in v]
            if self.unordered or (el and all((isinstance(x, type) for x in v))):
                el.sort()
            return type(v).__name__ + '[' + ','.join(el) + ']'
        if isinstance(v, types.ModuleType):
            return 'mod:' + v.__name__
        if isinstance(v, re.Pattern):
            return f're:{v.pattern!r}:{v.flags}'
        if isinstance(v, types.CodeType):
            return self.code(v)
        try:
            import functools
            if isinstance(v, functools.partial):
                return 'partial(' + self.fp(v.func, depth) + self.fp(v.args, depth) + self.fp(v.keywords, depth) + ')'
        except Exception:
            pass
        if callable(v) and hasattr(v, '__wrapped__'):
            return 'wrap(' + self.fp(v.__wrapped__, depth) + ')'
        d = getattr(v, '__dict__', None)
        tn = self.fp(type(v), 2)
        if isinstance(d, dict):
            return 'o:' + tn + self.fp(d, depth - 1)
        slots = []
        for c in type(v).__mro__:
            for s in getattr(c, '__slots__', ()) or ():
                if isinstance(s, str) and hasattr(v, s):
                    slots.append((s, getattr(v, s)))
        if slots:
            return 'o:' + tn + '{' + ','.join((f'{s}:{self.fp(x, depth - 1)}' for s, x in slots)) + '}'
        r = repr(v)
        if ' at 0x' in r:
            return 'o:' + tn
        return 'r:' + tn + r[:300]

def _h(s):
    return hashlib.blake2b(s.encode('utf-8', 'surrogatepass'), digest_size=6).hexdigest()

def snapshot(modnames, reg, classes, want_lines=False, unordered=()):
    fpr0 = Fingerprinter(reg)
    fpr1 = Fingerprinter(reg, unordered=True)
    unordered = set(unordered)
    out = {}
    lines = {}
    fpr = fpr0

    def dictlike(prefix, v):
        if isinstance(v, dict):
            out[prefix.replace('K|', 'A|', 1) if prefix.startswith('K|') else prefix] = 'dict'
            for k, x in v.items():
                out[prefix + '|' + kname(k, reg)] = _h(fpr.fp(x, 5))
            return True
        if isinstance(v, (set, frozenset)):
            for k in v:
                out[prefix + '|' + kname(k, reg)] = '1'
            return True
        return False

    def func_entry(path, f):
        raw = f
        while isinstance(raw, (classmethod, staticmethod)):
            raw = raw.__func__
        if isinstance(raw, property):
            raw = raw.fget
        out[path] = _h(fpr.fp(f, 6))
        if want_lines:
            inner = raw
            seen = 0
            while hasattr(inner, '__wrapped__') and seen < 5:
                inner = inner.__wrapped__
                seen += 1
            co = getattr(inner, '__code__', None)
            if co is not None and co.co_filename:
                ls = [l for _, _, l in co.co_lines() if l]
                if ls:
                    lines[path] = (co.co_filename, min(ls), max(ls))
    for name, cls in classes:
        try:
            mro = cls.__mro__
        except Exception:
            mro = ()
        out[f'B|{name}'] = _h(','.join((fpr.fp(b, 1) for b in mro)))
        if issubclass(cls, enum.Enum):
            out[f'A|{name}|__members__'] = _h(','.join((f'{m}={v.value!r}' for m, v in cls.__members__.items())))
            continue
        for k, v in list(cls.__dict__.items()):
            if k in SKIP_CLASS_KEYS:
                continue
            p = f'{name}|{k}'
            if isinstance(v, (types.FunctionType, classmethod, staticmethod, property)) or (callable(v) and hasattr(v, '__wrapped__') and (not isinstance(v, type))):
                func_entry('F|' + p, v)
            elif isinstance(v, (dict, set, frozenset)):
                out['A|' + p] = type(v).__name__ + ':' + ('1' if v else '0')
                dictlike('K|' + p, v)
            else:
                out['A|' + p] = _h((fpr1 if 'A|' + p in unordered else fpr0).fp(v, 6))
    for n in modnames:
        m = sys.modules.get(n)
        if m is None:
            out[f'G|{n}|<import-error>'] = '1'
            continue
        for k, v in list(vars(m).items()):
            if k.startswith('__') and k not in ('__all__',):
                continue
            p = f'{n}|{k}'
            if isinstance(v, types.FunctionType):
                if v.__module__ == n:
                    func_entry('F|' + p, v)
                else:
                    out['G|' + p] = 'ref:' + f'{v.__module__}.{v.__qualname__}'
            elif isinstance(v, type):
                out['G|' + p] = fpr.fp(v, 1)
            elif isinstance(v, types.ModuleType):
                out['G|' + p] = 'mod:' + v.__name__
            elif isinstance(v, (dict, set, frozenset)):
                out['G|' + p] = type(v).__name__ + ':' + ('1' if v else '0')
                dictlike('MK|' + p, v)
            else:
                out['G|' + p] = _h((fpr1 if 'G|' + p in unordered else fpr0).fp(v, 6))
    return (out, lines)

def diff_snapshots(old, new):
    ch = set()
    for p, h in new.items():
        o = old.get(p)
        if o != h and o != '?':
            ch.add(p)
    for p in old:
        if p not in new:
            ch.add(p)
    return ch
_MAPS = {}

def _load(name):
    if name not in _MAPS:
        p = os.path.join(MAPDIR, name)
        try:
            with gzip.open(p, 'rt') as f:
                _MAPS[name] = json.load(f)
        except FileNotFoundError:
            _MAPS[name] = None
    return _MAPS[name]

class ReadMap:

    def __init__(self, d):
        self.sets = d['sets']
        self.attr = d['attr']
        self.recv = d['recv']
        self.key = d['key']
        self.star = d['star']
        self.mro = d['mro']
        self.subs = {}
        for c, bases in self.mro.items():
            for b in bases:
                self.subs.setdefault(b, []).append(c)
        self.owns = _LazySets(d.get('owns', {}))
        self.modglob = d.get('modglob', {})

    def T(self, idx):
        if idx is None:
            return ()
        v = self.sets[idx]
        if isinstance(v, str):
            v = self.sets[idx] = [int(x) for x in v.split(',')] if v else []
        return v

    def subclasses(self, c):
        return [c] + self.subs.get(c, [])

class _LazySets(dict):

    def get(self, k, default=()):
        v = dict.get(self, k)
        if v is None:
            return default
        if not isinstance(v, set):
            v = set(v)
            self[k] = v
        return v

def get_readmap():
    if '_rm' not in _MAPS:
        d = _load('readmap.json.gz')
        _MAPS['_rm'] = ReadMap(d) if d else None
    return _MAPS['_rm']

def get_cov():
    return _load('covmap.json.gz') or _load_cov_fallback()

def _load_cov_fallback():
    if '_cov' not in _MAPS:
        p = os.environ.get('IMPORTTIME_COVMAP', '/home/user/blast-radius/maps/covmap.json.gz')
        try:
            with gzip.open(p, 'rt') as f:
                _MAPS['_cov'] = json.load(f)
        except Exception:
            _MAPS['_cov'] = None
    return _MAPS['_cov']

def cov_tests(relpath, lo, hi):
    M = get_cov()
    out = set()
    if not M:
        return out
    fm = M['files'].get(relpath)
    if not fm:
        return out
    L = fm['lines']
    for ln in range(lo, hi + 1):
        s = L.get(str(ln))
        if s is not None:
            out.update(M['sets'][s])
    return out

def tests_for_paths(paths, info=None):
    rm = get_readmap()
    res = set()
    unresolved = []
    if rm is None:
        return (res, ['no readmap'])
    flines = (_load('spans.json.gz') or {}).get('lines', {})
    for p in sorted(paths):
        parts = p.split('|')
        kind = parts[0]
        if kind == 'A' and len(parts) >= 3:
            cls, attr = (parts[1], '|'.join(parts[2:]))
            res |= _attr_tests(rm, cls, attr)
        elif kind == 'K' and len(parts) >= 4:
            cls, attr, key = (parts[1], parts[2], '|'.join(parts[3:]))
            res |= _key_tests(rm, cls, attr, key)
        elif kind == 'MK' and len(parts) >= 4:
            mod, name, key = (parts[1], parts[2], '|'.join(parts[3:]))
            tid = f'M|{mod}|{name}'
            res |= set(rm.T(rm.key.get(tid + '\x00' + key)))
            res |= set(rm.T(rm.star.get(tid)))
            res |= set(rm.T(rm.modglob.get(f'{mod}|{name}')))
        elif kind == 'G' and len(parts) >= 3:
            mod, name = (parts[1], parts[2])
            if name == '<import-error>':
                rel = mod.replace('.', '/') + '.py'
                if not os.path.exists(os.path.join(SQLGLOT_ROOT, rel)):
                    rel = mod.replace('.', '/') + '/__init__.py'
                res |= module_fallback(rel)
                unresolved.append(p)
                continue
            tid = f'M|{mod}|{name}'
            res |= set(rm.T(rm.star.get(tid))) | set(rm.T(rm.modglob.get(f'{mod}|{name}')))
        elif kind == 'F' and len(parts) >= 3:
            owner, name = (parts[1], parts[2])
            li = flines.get(p)
            if li:
                res |= cov_tests(li[0], li[1], li[2])
            if owner in rm.mro or owner in rm.owns:
                res |= _attr_tests(rm, owner, name)
                if name.endswith('_sql') and (not name.startswith('_')):
                    ek = 'C:' + _expr_class_for(name[:-4])
                    for d in rm.subclasses(owner):
                        res |= set(rm.T(rm.key.get(f'D|{d}\x00{ek}')))
            else:
                res |= set(rm.T(rm.modglob.get(f'{owner}|{name}')))
        elif kind == 'B':
            cls = parts[1]
            for d in rm.subclasses(cls):
                res |= set(rm.T(rm.recv.get(d + '\x00*')))
        else:
            unresolved.append(p)
    return (res, unresolved)
_EXPR_CLASSES = None

def _expr_class_for(key):
    global _EXPR_CLASSES
    if _EXPR_CLASSES is None:
        _EXPR_CLASSES = (_load('spans.json.gz') or {}).get('expr_classes', {})
    return _EXPR_CLASSES.get(key, '?' + key)

def _attr_tests(rm, cls, attr):
    res = set(rm.T(rm.attr.get(cls + '\x00' + attr)))
    if attr == 'TRANSFORMS':
        for d in rm.subclasses(cls):
            res |= set(rm.T(rm.star.get('D|' + d)))
    for d in rm.subclasses(cls):
        if d != cls:
            shadowed = False
            for b in [d] + rm.mro.get(d, []):
                if b == cls:
                    break
                if attr in rm.owns.get(b, ()):
                    shadowed = True
                    break
            if shadowed:
                continue
        res |= set(rm.T(rm.recv.get(d + '\x00' + attr)))
    return res

def _key_tests(rm, cls, attr, key):
    tid = f'{cls}|{attr}'
    res = set(rm.T(rm.key.get(tid + '\x00' + key)))
    res |= set(rm.T(rm.star.get(tid)))
    if attr == 'TRANSFORMS':
        for d in rm.subclasses(cls):
            res |= set(rm.T(rm.key.get(f'D|{d}\x00{key}')))
    for d in rm.subclasses(cls)[1:]:
        if attr in rm.owns.get(d, ()):
            t2 = f'{d}|{attr}'
            res |= set(rm.T(rm.key.get(t2 + '\x00' + key)))
            res |= set(rm.T(rm.star.get(t2)))
    return res

def parse_patch(text):
    files = []
    cur = None
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith('diff --git'):
            cur = {'old': None, 'new': None, 'hunks': []}
            files.append(cur)
            m = re.match('diff --git a/(\\S+) b/(\\S+)', ln)
            if m:
                cur['old'], cur['new'] = (m.group(1), m.group(2))
        elif ln.startswith('--- ') and cur is not None and (not cur['hunks']):
            p = ln[4:].strip().split('\t')[0]
            cur['old'] = None if p == '/dev/null' else p[2:] if p.startswith('a/') else p
        elif ln.startswith('+++ ') and cur is not None and (not cur['hunks']):
            p = ln[4:].strip().split('\t')[0]
            cur['new'] = None if p == '/dev/null' else p[2:] if p.startswith('b/') else p
        elif ln.startswith('@@') and cur is not None:
            m = re.match('@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@', ln)
            ostart = int(m.group(1))
            ocount = int(m.group(2)) if m.group(2) is not None else 1
            ncount = int(m.group(4)) if m.group(4) is not None else 1
            old, new = ([], [])
            i += 1
            while i < len(lines) and (ocount > 0 or ncount > 0):
                l = lines[i]
                if l.startswith('\\'):
                    i += 1
                    continue
                tag, body = (l[:1], l[1:])
                if tag == ' ' or l in ('\n', '\r\n'):
                    body = body if tag == ' ' else '\n'
                    old.append(body)
                    new.append(body)
                    ocount -= 1
                    ncount -= 1
                elif tag == '-':
                    old.append(body)
                    ocount -= 1
                elif tag == '+':
                    new.append(body)
                    ncount -= 1
                else:
                    break
                i += 1
                if i < len(lines) and lines[i].startswith('\\'):
                    if tag in ('-', ' '):
                        old[-1] = old[-1].rstrip('\n')
                    if tag in ('+', ' '):
                        new[-1] = new[-1].rstrip('\n')
            cur['hunks'].append((ostart, old, new))
            continue
        i += 1
    return files

def apply_hunks(src, hunks):
    a = src.splitlines(keepends=True)
    out, pos = ([], 0)
    for ostart, old, new in hunks:
        start = max(ostart - 1, 0) if old else ostart
        cand = None
        for delta in range(0, 200):
            for s in (start + delta, start - delta):
                if 0 <= s <= len(a) and s >= pos and ([x.rstrip('\r\n') for x in a[s:s + len(old)]] == [x.rstrip('\r\n') for x in old]):
                    cand = s
                    break
            if cand is not None:
                break
        if cand is None:
            raise ValueError('hunk does not apply at %d' % ostart)
        out += a[pos:cand]
        out += new
        pos = cand + len(old)
    out += a[pos:]
    return ''.join(out)

def patched_sources(patch_text, root=None):
    root = root or SQLGLOT_ROOT
    res = {}
    for f in parse_patch(patch_text):
        if f['new'] is None:
            res[f['old']] = None
            continue
        old = ''
        if f['old']:
            try:
                with open(os.path.join(root, f['old']), encoding='utf-8') as fh:
                    old = fh.read()
            except FileNotFoundError:
                old = ''
        res[f['new']] = apply_hunks(old, f['hunks'])
        if f['old'] and f['old'] != f['new']:
            res[f['old']] = None
    return res

class _OverlayFinder:

    def __init__(self, root, overlay):
        self.root = root
        self.overlay = overlay

    def find_spec(self, name, path=None, target=None):
        if not name.startswith('sqlglot'):
            return None
        import importlib.util
        rel = name.replace('.', '/')
        for cand, is_pkg in ((rel + '.py', False), (rel + '/__init__.py', True)):
            if cand in self.overlay:
                if self.overlay[cand] is None:
                    return None
                full = os.path.join(self.root, cand)
                loader = _OverlayLoader(self.overlay[cand], full)
                spec = importlib.util.spec_from_file_location(name, full, loader=loader, submodule_search_locations=[os.path.dirname(full)] if is_pkg else None)
                return spec
        return None

class _OverlayLoader:

    def __init__(self, src, path):
        self.src, self.path = (src, path)

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        code = compile(self.src, self.path, 'exec', dont_inherit=True)
        exec(code, module.__dict__)

def _snapshot_current(root, extra_modules=()):
    names = sorted(set(module_names(root)) | set(extra_modules))
    import_all(names)
    reg, classes = build_registry(names)
    unordered = (_load('fp.json.gz') or {}).get('unordered', ())
    snap, lines = snapshot(names, reg, classes, want_lines=False, unordered=unordered)
    return snap

def changed_paths_inprocess(root=None, extra_modules=()):
    root = root or SQLGLOT_ROOT
    old = (_load('fp.json.gz') or {}).get('fp')
    if old is None:
        raise RuntimeError('fp.json.gz missing')
    new = _snapshot_current(root, extra_modules)
    return diff_snapshots(old, new)

def _dynamic_main(patch_text, root):
    overlay = patched_sources(patch_text, root)
    added = [p[:-3].replace('/', '.').replace('.__init__', '') for p, s in overlay.items() if s is not None and p.startswith('sqlglot/') and p.endswith('.py') and (not os.path.exists(os.path.join(root, p)))]
    sys.path.insert(0, root)
    sys.meta_path.insert(0, _OverlayFinder(root, {k: v for k, v in overlay.items() if k.endswith('.py')}))
    return changed_paths_inprocess(root, added)

def dynamic_changed_paths(patch_text, root=None, timeout=60):
    import subprocess
    root = root or SQLGLOT_ROOT
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', IMPORTTIME_SQLGLOT=root)
    env.pop('PYTHONPATH', None)
    p = subprocess.run([sys.executable, '-I', os.path.abspath(__file__), '--dynamic', root, MAPDIR], input=patch_text, capture_output=True, text=True, timeout=timeout, env=env)
    if p.returncode != 0:
        if os.environ.get('BR_HARDEN', '1') == '1':
            return (None, 'rc=%d %s' % (p.returncode, p.stderr[-2000:]))
        return (None, p.stderr[-2000:])
    return (set(json.loads(p.stdout.strip().splitlines()[-1])), None)

def dynamic_extra_candidates(patch_text, root=None):
    paths, err = dynamic_changed_paths(patch_text, root)
    if paths is None:
        return (set(), {'confident': False, 'error': err})
    tests, unresolved = tests_for_paths(paths)
    return (tests, {'confident': not unresolved, 'paths': sorted(paths), 'unresolved': unresolved})

def _dotted(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return parts[::-1]
    return None

def ast_kname(node, ctx):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            return node.value
        return 'V:' + repr(node.value)
    if isinstance(node, ast.Tuple):
        el = [ast_kname(e, ctx) for e in node.elts]
        return None if None in el else 'T:(' + ','.join(el) + ')'
    parts = _dotted(node)
    if not parts:
        return None
    last = parts[-1]
    if len(parts) >= 2 and parts[-2] in ctx['enum_alias']:
        return f"E:{ctx['enum_alias'][parts[-2]]}.{last}"
    c = ctx['classnames'].get(last)
    if c is not None:
        return 'C:' + c
    return None

def _modname(rel):
    m = rel[:-3].replace('/', '.')
    return m[:-len('.__init__')] if m.endswith('.__init__') else m

def _alignment(old_lines_n, hunks_ops):
    amap = {}
    o = n = 1
    for ostart, nstart, ops in hunks_ops:
        while o < ostart:
            amap[o] = n
            o += 1
            n += 1
        n = nstart if nstart > 0 else n
        for tag in ops:
            if tag == ' ':
                amap[o] = n
                o += 1
                n += 1
            elif tag == '-':
                amap[o] = None
                o += 1
            else:
                n += 1
    while o <= old_lines_n + 1:
        amap[o] = n
        o += 1
        n += 1
    return amap

def _hunk_ops(text):
    res = {}
    cur = None
    for line in text.splitlines():
        if line.startswith('diff --git'):
            m = re.match('diff --git a/(\\S+) b/(\\S+)', line)
            cur = res.setdefault(m.group(1) if m else line, {'hunks': [], 'removed': set(), 'ins': set()})
            continue
        if cur is None or line.startswith(('--- ', '+++ ', 'index ', 'new file', 'deleted file', 'similarity', 'rename ', 'old mode', 'new mode')):
            continue
        m = re.match('@@ -(\\d+)(?:,(\\d+))? \\+(\\d+)(?:,(\\d+))? @@', line)
        if m:
            o = int(m.group(1))
            if m.group(2) == '0':
                o += 1
            cur['hunks'].append([o, int(m.group(3)) if m.group(4) != '0' else int(m.group(3)) + 1, []])
            pos = o
            continue
        if not cur['hunks'] or line.startswith('\\'):
            continue
        tag = line[:1] or ' '
        ops = cur['hunks'][-1][2]
        if tag == '-':
            cur['removed'].add(pos)
            pos += 1
        elif tag == '+':
            cur['ins'].add(pos)
        else:
            pos += 1
            tag = ' '
        ops.append(tag)
    return res

def _find(nodes, line):
    for nd in nodes:
        if nd[2] <= line <= nd[3]:
            return nd
    return None

def _wrap_parse(lines, indent):
    txt = ''.join(lines)
    if not any((l.strip() and (not l.lstrip().startswith('#')) for l in lines)):
        return []
    if indent:
        txt = 'if 1:\n' + txt
    try:
        tree = ast.parse(txt)
    except SyntaxError:
        return None
    return tree.body[0].body if indent else tree.body

def _indent_of(line):
    return len(line) - len(line.lstrip(' \t'))

class _StaticCtx:

    def __init__(self):
        sp = _load('spans.json.gz') or {}
        self.spans = sp.get('spans', {})
        self.refs = sp.get('refs', {})
        self.ctx = {'classnames': sp.get('classnames', {}), 'enum_alias': sp.get('enum_alias', {})}
        self.importers = sp.get('importers', {})
        self.kvals = {}
        self.ldiff = {}

def _stmt_map(body):
    out = {}
    for st in body or []:
        if isinstance(st, ast.ClassDef):
            out['class:' + st.name] = st
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out['def:' + st.name] = st
        elif isinstance(st, (ast.Assign, ast.AnnAssign)):
            tg = st.targets if isinstance(st, ast.Assign) else [st.target]
            for t in tg:
                if isinstance(t, ast.Name):
                    out['var:' + t.id] = st
                else:
                    for n in ast.walk(t):
                        if isinstance(n, ast.Name):
                            out['other:' + n.id] = st
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            for a in st.names:
                out['imp:' + (a.asname or a.name.split('.')[0])] = (st, a)
        else:
            d = ast.dump(st)
            for n in _stored_names(st) or ['?' + str(hash(d))]:
                out.setdefault('other:' + n, [])
                if isinstance(out['other:' + n], list):
                    out['other:' + n].append(st)
    return out

def _stored_names(node):
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

def _dump(x):
    if isinstance(x, list):
        return '|'.join((ast.dump(y) for y in x))
    if isinstance(x, tuple):
        return ast.dump(x[0].__class__(module=getattr(x[0], 'module', None), names=[x[1]], level=getattr(x[0], 'level', 0))) if isinstance(x[0], ast.ImportFrom) else ast.dump(x[1])
    return ast.dump(x)

def unwrap_filter_comp(v):
    if isinstance(v, ast.DictComp) and len(v.generators) == 1:
        g = v.generators[0]
        it = g.iter
        if isinstance(it, ast.Call) and isinstance(it.func, ast.Attribute) and (it.func.attr == 'items') and (not it.args) and isinstance(g.target, ast.Tuple) and (len(g.target.elts) == 2) and isinstance(g.target.elts[0], ast.Name) and isinstance(v.key, ast.Name) and (v.key.id == g.target.elts[0].id) and isinstance(v.value, ast.Name) and isinstance(g.target.elts[1], ast.Name) and (v.value.id == g.target.elts[1].id):
            return it.func.value
    return v

def fromkeys_entries(val, ctx):
    if isinstance(val, ast.Call) and isinstance(val.func, ast.Attribute) and (val.func.attr == 'fromkeys') and isinstance(val.func.value, ast.Name) and (val.func.value.id == 'dict') and val.args and isinstance(val.args[0], (ast.Tuple, ast.List, ast.Set)):
        ks = [ast_kname(e, ctx) for e in val.args[0].elts]
        if None not in ks:
            return ks
    return None

def _const(node):
    return node.value if isinstance(node, ast.Constant) else None

def _entries(v, ctx):
    if isinstance(v, ast.DictComp):
        inner = unwrap_filter_comp(v)
        if inner is not v:
            r = _entries(inner, ctx) if isinstance(inner, ast.Dict) else None
            if r is not None:
                return (r[0], r[1] + ['filter:' + ast.dump(v.generators[0].ifs[0]) if v.generators[0].ifs else 'filter'])
            return None
    if isinstance(v, ast.Dict):
        out, other = ({}, [])
        for k, val in zip(v.keys, v.values):
            if k is None:
                fk = fromkeys_entries(val, ctx)
                if fk is not None:
                    vd = ast.dump(val.args[1]) if len(val.args) > 1 else 'None'
                    for kn in fk:
                        out[kn] = (vd, val.args[1] if len(val.args) > 1 else None)
                    continue
                if isinstance(val, ast.DictComp) and len(val.generators) == 1:
                    g = val.generators[0]
                    if isinstance(g.iter, (ast.Set, ast.List, ast.Tuple)) and (not g.ifs) and isinstance(g.target, ast.Name) and isinstance(val.key, ast.Name) and (val.key.id == g.target.id):
                        vd = ast.dump(val.value)
                        for e in g.iter.elts:
                            kn = ast_kname(e, ctx) or '?' + ast.dump(e)
                            out[kn] = (vd, None)
                        continue
                other.append(ast.dump(val))
                continue
            kn = ast_kname(k, ctx)
            if kn is None:
                kn = '?' + ast.dump(k)
            out[kn] = (ast.dump(val), val)
        return (out, other)
    if isinstance(v, ast.Set):
        out, other = ({}, [])
        for e in v.elts:
            if isinstance(e, ast.Starred):
                other.append(ast.dump(e))
                continue
            kn = ast_kname(e, ctx) or '?' + ast.dump(e)
            out[kn] = ('1', None)
        return (out, other)
    if isinstance(v, ast.BinOp) and isinstance(v.op, ast.BitOr) and isinstance(v.right, (ast.Set, ast.Dict)):
        r = _entries(v.right, ctx)
        if r:
            return (r[0], r[1] + [ast.dump(v.left)])
    return None

def _list_elems(v):
    if not isinstance(v, (ast.List, ast.Tuple)):
        return None
    out = []
    for e in v.elts:
        if isinstance(e, ast.Constant) and isinstance(e.value, str):
            out.append(e.value)
        elif isinstance(e, ast.Tuple) and e.elts and isinstance(e.elts[0], ast.Constant):
            out.append(str(e.elts[0].value))
        else:
            return None
    return out

def _diff_bodies(mod, owner, ob, nb, sc, paths, names_changed, notes):
    om, nm = (_stmt_map(ob), _stmt_map(nb))
    for key in set(om) | set(nm):
        o, n = (om.get(key), nm.get(key))
        if o is not None and n is not None and (_dump(o) == _dump(n)):
            continue
        kind, name = key.split(':', 1)
        if kind == 'class':
            q = f'{owner}.{name}' if owner else name
            cname = f'{mod}.{q}'
            if o is None or n is None:
                paths.add(f'A|{mod}.{owner}|{name}' if owner else f'G|{mod}|{name}')
                notes.append('class added/removed: ' + cname)
                if mod.startswith('sqlglot.expressions'):
                    c = n if n is not None else o
                    fnames = []
                    for st in c.body:
                        if isinstance(st, ast.Assign) and any((isinstance(t, ast.Name) and t.id == '_sql_names' for t in st.targets)):
                            if isinstance(st.value, (ast.List, ast.Tuple)):
                                fnames += [e.value for e in st.value.elts if isinstance(e, ast.Constant)]
                    if not fnames:
                        fnames = [re.sub('(?<!^)(?=[A-Z])', '_', name).upper()]
                    for fn in fnames:
                        paths.add(f'K|sqlglot.parser.Parser|FUNCTIONS|{fn}')
                        paths.add(f'MK|sqlglot.expressions|FUNCTION_BY_NAME|{fn}')
                if o is not None:
                    paths.add(f'B|{cname}')
                names_changed.add((mod, owner, name))
                continue
            hdr = lambda c: ast.dump(ast.Module(body=[], type_ignores=[])) + '|'.join((ast.dump(x) for x in c.bases + c.keywords + c.decorator_list))
            if hdr(o) != hdr(n):
                paths.add(f'B|{cname}')
            _diff_bodies(mod, q, o.body, n.body, sc, paths, names_changed, notes)
            continue
        if kind == 'def':

            def sig(f):
                if f is None:
                    return None
                return ast.dump(f.args) + '|'.join((ast.dump(d) for d in f.decorator_list)) + type(f).__name__ + (ast.dump(f.returns) if f.returns else '')
            if sig(o) != sig(n):
                paths.add(f'F|{mod}.{owner}|{name}' if owner else f'F|{mod}|{name}')
                names_changed.add((mod, owner, name))
            continue
        if kind == 'imp':
            paths.add(f'G|{mod}|{name}')
            names_changed.add((mod, owner, name))
            continue
        cls = f'{mod}.{owner}' if owner else None
        if kind == 'var':
            ov = getattr(o, 'value', None) if o is not None else None
            nv = getattr(n, 'value', None) if n is not None else None
            eo = _entries(ov, sc.ctx) if ov is not None else None
            en = _entries(nv, sc.ctx) if nv is not None else None
            if eo is not None and en is not None and (eo[1] == en[1]):
                oe, ne = (eo[0], en[0])
                for k in set(oe) | set(ne):
                    a1, b1 = (oe.get(k), ne.get(k))
                    if (a1 and a1[0]) != (b1 and b1[0]):
                        if k.startswith('?'):
                            paths.add(f'A|{cls}|{name}' if cls else f'G|{mod}|{name}')
                        else:
                            pth = f'K|{cls}|{name}|{k}' if cls else f'MK|{mod}|{name}|{k}'
                            paths.add(pth)
                            sc.kvals[pth] = (a1 is not None, b1 is not None, _const(a1[1]) if a1 and a1[1] is not None else None, _const(b1[1]) if b1 and b1[1] is not None else None)
                            names_changed.add((mod, owner, name + '\x00' + k))
                if bool(oe) != bool(ne):
                    paths.add(f'A|{cls}|{name}' if cls else f'G|{mod}|{name}')
                continue
        pth = f'A|{cls}|{name}' if cls else f'G|{mod}|{name}'
        paths.add(pth)
        if kind == 'var' and o is not None and (n is not None):
            lo_, ln_ = (_list_elems(getattr(o, 'value', None)), _list_elems(getattr(n, 'value', None)))
            if lo_ is not None and ln_ is not None:
                sc.ldiff[pth] = set(lo_) ^ set(ln_) or set(lo_) | set(ln_)
        names_changed.add((mod, owner, name))
_IMPORT_EXEC = [set()]

def static_paths(patch_text, root=None):
    root = root or SQLGLOT_ROOT
    _IMPORT_EXEC[0] = set()
    sc = _StaticCtx()
    paths, notes = (set(), [])
    ok = True
    names_changed = set()
    hp = _hunk_ops(patch_text)
    files = parse_patch(patch_text)
    for f in files:
        rel_old, rel_new = (f['old'], f['new'])
        rel = rel_new or rel_old
        if not rel or not rel.endswith('.py') or (not rel.startswith('sqlglot/')):
            continue
        mod = _modname(rel)
        if rel_old is None or rel_new is None or rel_old != rel_new:
            notes.append('file added/removed/renamed: ' + rel)
            paths.add(f'G|{mod}|<import-error>')
            ok = False
            continue
        nodes = sc.spans.get(rel)
        try:
            with open(os.path.join(root, rel), encoding='utf-8') as fh:
                old_src = fh.read()
        except OSError:
            notes.append('no source: ' + rel)
            ok = False
            continue
        if nodes is None:
            notes.append('no spans: ' + rel)
            ok = False
            continue
        info = hp.get(rel) or {'hunks': [], 'removed': set(), 'ins': set()}
        old_lines = old_src.splitlines(keepends=True)
        touched = []
        locs = [(ln, 'rm') for ln in sorted(info['removed'])] + [(ln, 'ins') for ln in sorted(info['ins'])]
        need = []
        for ln, why in locs:
            chain = []
            nodes_ = nodes
            hit = None
            while True:
                nd = _find(nodes_, ln)
                if why == 'ins' and nd is not None and (nd[2] == ln):
                    nd = None
                if nd is None:
                    break
                if nd[0] == 'C':
                    if ln <= nd[4]:
                        hit = ('hdr', nd)
                        break
                    chain.append(nd)
                    nodes_ = nd[5]
                    continue
                if nd[0] == 'D':
                    hit = ('sig', nd) if ln <= nd[4] else ('body', nd)
                    break
                hit = ('stmt', nd)
                break
            if hit is not None and hit[0] == 'body':
                ie = (_load('importexec.json.gz') or {}).get('files', {}).get(rel)
                if ie:
                    for l2 in (ln,) if why == 'rm' else (ln - 1, ln):
                        for m2 in ie.get(str(l2), ()):
                            _IMPORT_EXEC[0].add(m2)
                continue
            need.append((tuple((id(c) for c in chain)), chain, hit, ln, why))
        if not need:
            continue
        new_src = apply_hunks(old_src, f['hunks'])
        amap = _alignment(len(old_lines), info['hunks'])
        new_lines = new_src.splitlines(keepends=True)
        scopes = {}
        for key, chain, hit, ln, why in need:
            scopes.setdefault(key, (chain, []))[1].append((hit, ln, why))
        for key, (chain, hits) in scopes.items():
            owner = '.'.join((c[1][0] for c in chain))
            if chain:
                top = chain[-1]
                lo, hi = (top[4] + 1, top[3])
            else:
                lo, hi = (1, len(old_lines))
            sub = chain[-1][5] if chain else nodes
            wl, wh = (None, None)
            for hit, ln, why in hits:
                a, b = (ln, ln)
                if hit is not None:
                    a, b = (hit[1][2], hit[1][3])
                    if hit[0] == 'hdr':
                        a, b = (hit[1][2], hit[1][4])
                wl = a if wl is None else min(wl, a)
                wh = b if wh is None else max(wh, b)
            changed = True
            while changed:
                changed = False
                for nd in sub:
                    if nd[2] <= wh and nd[3] >= wl and (nd[2] < wl or nd[3] > wh):
                        if nd[0] == 'C' and (nd[2] < wl and nd[3] > wh):
                            continue
                        wl, wh = (min(wl, nd[2]), max(wh, nd[3]))
                        changed = True
                while wl > lo and amap.get(wl - 1) is None:
                    wl -= 1
                    changed = True
                while wh < hi and amap.get(wh + 1) is None:
                    wh += 1
                    changed = True
            pl = wl - 1
            while pl >= 1 and amap.get(pl) is None:
                pl -= 1
            nl = (amap.get(pl) or 0) + 1 if pl >= 1 else 1
            if amap.get(wl) is not None and wl not in info['ins']:
                nl = amap[wl]
            qh = wh + 1
            while qh <= len(old_lines) and amap.get(qh) is None:
                qh += 1
            nh = (amap.get(qh) or len(new_lines) + 1) - 1
            old_seg = old_lines[wl - 1:wh]
            new_seg = new_lines[nl - 1:nh]
            indent = 1 if chain else 0
            ob = _wrap_parse(old_seg, indent)
            nb = _wrap_parse(new_seg, indent)
            if ob is None or nb is None:
                notes.append(f'unparsable region {rel}:{wl}-{wh}')
                ok = False
                cls = f'{mod}.{owner}' if owner else None
                for nd in sub:
                    if nd[2] <= wh and nd[3] >= wl:
                        for nm in nd[1]:
                            paths.add(f'A|{cls}|{nm}' if cls else f'G|{mod}|{nm}')
                continue
            _diff_bodies(mod, owner, ob, nb, sc, paths, names_changed, notes)
    for mod, owner, name in list(names_changed):
        if owner:
            continue
        base, _, key = name.partition('\x00')
        for imp in sc.importers.get(f'{mod}|{base}', ()):
            mod2, alias = imp.split('|', 1)
            paths.add(f'MK|{mod2}|{alias}|{key}' if key else f'G|{mod2}|{alias}')
            names_changed.add((mod2, '', alias + ('\x00' + key if key else '')))
    seen = set()
    frontier = set(names_changed)
    for _ in range(3):
        nxt = set()
        for mod, owner, name in frontier:
            base, _, key = name.partition('\x00')
            if (mod, owner, base, key) in seen:
                continue
            seen.add((mod, owner, base, key))
            simple = owner.rsplit('.', 1)[-1] if owner else None
            modlast = mod.rsplit('.', 1)[-1]
            cname = f'{mod}.{owner}' if owner else None
            for rel2, owner2, attr2, entry, qual, qcls in sc.refs.get(base, ()):
                mod2 = _modname(rel2)
                if owner:
                    if qcls is not None:
                        if qcls != cname:
                            continue
                    elif not (qual is None and mod2 == mod and (owner2 == owner) or (qual is not None and qual not in ('?',) and cname.endswith('.' + qual) and qual.split('.')[0][:1].isupper())):
                        continue
                elif not (qual is None or qual == modlast):
                    continue
                if attr2 == '<bases>':
                    paths.add(f'B|{mod2}.{owner2}')
                    continue
                if entry == '<def>':
                    paths.add(f'F|{mod2}.{owner2}|{attr2}' if owner2 else f'F|{mod2}|{attr2}')
                    continue
                cls2 = f'{mod2}.{owner2}' if owner2 else None
                if entry in ('<spread>', '<kp>') and key:
                    paths.add(f'K|{cls2}|{attr2}|{key}' if cls2 else f'MK|{mod2}|{attr2}|{key}')
                    nxt.add((mod2, owner2, attr2 + '\x00' + key))
                    continue
                if entry and entry not in ('<spread>', '<kp>'):
                    paths.add(f'K|{cls2}|{attr2}|{entry}' if cls2 else f'MK|{mod2}|{attr2}|{entry}')
                    nxt.add((mod2, owner2, attr2 + '\x00' + entry))
                    continue
                paths.add(f'A|{cls2}|{attr2}' if cls2 else f'G|{mod2}|{attr2}')
                nxt.add((mod2, owner2, attr2))
        frontier = nxt
    _LAST_SC[0] = sc
    return (paths, notes, ok)
_LAST_SC = [None]
_TOK_DERIVED = {'QUOTES': ['_QUOTES', '_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'IDENTIFIERS': ['_IDENTIFIERS'], 'BIT_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'BYTE_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'HEX_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'NATIONAL_RAW_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'RAW_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'HEREDOC_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'UNICODE_STRINGS': ['_FORMAT_STRINGS', '_KEYWORD_TRIE'], 'STRING_ESCAPES': ['_STRING_ESCAPES', 'BYTE_STRING_ESCAPES', '_BYTE_STRING_ESCAPES'], 'BYTE_STRING_ESCAPES': ['_BYTE_STRING_ESCAPES'], 'IDENTIFIER_ESCAPES': ['_IDENTIFIER_ESCAPES'], 'COMMENTS': ['_COMMENTS', '_KEYWORD_TRIE'], 'HINT_START': ['_COMMENTS', '_KEYWORD_TRIE'], 'KEYWORDS': ['_COMMENTS', '_KEYWORD_TRIE'], 'SINGLE_TOKENS': ['_KEYWORD_TRIE']}
_TOK_TO_DIALECT = {'QUOTES': ['QUOTE_START', 'QUOTE_END', 'BIT_START', 'BIT_END', 'HEX_START', 'HEX_END', 'BYTE_START', 'BYTE_END', 'UNICODE_START', 'UNICODE_END'], 'IDENTIFIERS': ['IDENTIFIER_START', 'IDENTIFIER_END'], 'BIT_STRINGS': ['BIT_START', 'BIT_END'], 'HEX_STRINGS': ['HEX_START', 'HEX_END'], 'BYTE_STRINGS': ['BYTE_START', 'BYTE_END'], 'UNICODE_STRINGS': ['UNICODE_START', 'UNICODE_END'], 'STRING_ESCAPES': ['STRINGS_SUPPORT_ESCAPED_SEQUENCES', 'BYTE_STRINGS_SUPPORT_ESCAPED_SEQUENCES', 'UNESCAPED_SEQUENCES', 'ESCAPED_SEQUENCES', 'IDENTIFIER_ESCAPED_SEQUENCES'], 'BYTE_STRING_ESCAPES': ['BYTE_STRINGS_SUPPORT_ESCAPED_SEQUENCES', 'UNESCAPED_SEQUENCES', 'ESCAPED_SEQUENCES', 'IDENTIFIER_ESCAPED_SEQUENCES'], 'IDENTIFIER_ESCAPES': ['IDENTIFIER_ESCAPED_SEQUENCES'], 'NUMERIC_ESCAPES': ['ESCAPED_SEQUENCES'], 'KEYWORDS': ['SUPPORTS_COLUMN_JOIN_MARKS']}
_DIALECT_DERIVED = {'TIME_MAPPING': ['TIME_TRIE', 'FORMAT_TRIE', 'INVERSE_TIME_MAPPING', 'INVERSE_TIME_TRIE'], 'FORMAT_MAPPING': ['FORMAT_TRIE', 'INVERSE_FORMAT_MAPPING', 'INVERSE_FORMAT_TRIE'], 'INVERSE_TIME_MAPPING': ['INVERSE_TIME_TRIE'], 'CREATABLE_KIND_MAPPING': ['INVERSE_CREATABLE_KIND_MAPPING'], 'UNESCAPED_SEQUENCES': ['ESCAPED_SEQUENCES', 'IDENTIFIER_ESCAPED_SEQUENCES'], 'DATE_PART_MAPPING': ['VALID_INTERVAL_UNITS'], 'tokenizer_class': ['*'], 'parser_class': [], 'generator_class': []}

def _is_sub(rm, c, base_suffix):
    return any((b.endswith(base_suffix) for b in rm.mro.get(c, [])))
_TOK_LISTS = {'QUOTES', 'IDENTIFIERS', 'BIT_STRINGS', 'BYTE_STRINGS', 'HEX_STRINGS', 'NATIONAL_RAW_STRINGS', 'RAW_STRINGS', 'HEREDOC_STRINGS', 'UNICODE_STRINGS', 'COMMENTS'}

def _trie_key_affects(k):
    return ' ' in k or not k.replace('_', '').isalnum()

def expand_derived(paths, rm, sc=None):
    kvals = sc.kvals if sc else {}
    ldiff = sc.ldiff if sc else {}
    out = set(paths)

    def addk(d, attr, keys):
        for k in keys:
            if isinstance(k, str):
                out.add(f'K|{d}|{attr}|{k}')
    for p in paths:
        parts = p.split('|')
        if parts[0] not in ('A', 'K') or len(parts) < 3:
            continue
        cls, attr = (parts[1], parts[2])
        key = '|'.join(parts[3:]) if len(parts) > 3 else None
        kv = kvals.get(p)
        vals = [x for x in (kv[2], kv[3]) if isinstance(x, str)] if kv else []
        subs = rm.subclasses(cls)
        is_tok = cls == 'sqlglot.tokens.Tokenizer' or _is_sub(rm, cls, 'sqlglot.tokens._TokenizerBase')
        if is_tok:
            elems = ldiff.get(p)
            for d in subs:
                if key is not None and attr in ('KEYWORDS', 'SINGLE_TOKENS'):
                    if _trie_key_affects(key):
                        addk(d, '_KEYWORD_TRIE', [key[:1].upper()])
                        out.add(f'A|{d}|_COMMENTS')
                    continue
                if elems is not None and attr in _TOK_LISTS:
                    starts = set(elems)
                    if attr == 'QUOTES':
                        starts |= {pre + e for e in elems for pre in ('n', 'N')}
                    der = {'QUOTES': '_QUOTES', 'IDENTIFIERS': '_IDENTIFIERS', 'COMMENTS': '_COMMENTS'}.get(attr)
                    if der:
                        addk(d, der, elems)
                    if attr != 'IDENTIFIERS':
                        addk(d, '_FORMAT_STRINGS', starts)
                        addk(d, '_KEYWORD_TRIE', {x[:1].upper() for x in starts if x})
                    continue
                for der in _TOK_DERIVED.get(attr, ()):
                    out.add(f'A|{d}|{der}')
                    if key is not None and der != '_KEYWORD_TRIE':
                        out.add(f'K|{d}|{der}|{key}')
            dialects = set()
            for d in subs:
                parent = d.rsplit('.', 1)[0]
                if parent in rm.mro and (parent == 'sqlglot.dialects.dialect.Dialect' or _is_sub(rm, parent, 'sqlglot.dialects.dialect.Dialect')):
                    dialects.add(parent)
            for dl in list(dialects):
                dialects.update(rm.subclasses(dl))
            if cls == 'sqlglot.tokens.Tokenizer':
                dialects = {c for c in rm.mro if _is_sub(rm, c, 'sqlglot.dialects.dialect.Dialect')} | {'sqlglot.dialects.dialect.Dialect'}
            ders = _TOK_TO_DIALECT.get(attr, ())
            if attr == 'KEYWORDS':
                ders = ders if key in (None, '(+)') else ()
            if attr == 'NUMERIC_ESCAPES' and kv is not None and kv[0] and kv[1]:
                ders = ()
            for dl in dialects:
                for der in ders:
                    out.add(f'A|{dl}|{der}')
        if cls == 'sqlglot.dialects.dialect.Dialect' or _is_sub(rm, cls, 'sqlglot.dialects.dialect.Dialect'):
            for d in subs:
                if key is not None and kv is not None and (vals is not None):
                    if attr == 'TIME_MAPPING':
                        addk(d, 'TIME_TRIE', [key[:1]])
                        addk(d, 'FORMAT_TRIE', [key[:1]])
                        inv = set(vals) | {v + 'strict' for v in vals} | {v.replace('strict', '') for v in vals}
                        addk(d, 'INVERSE_TIME_MAPPING', inv)
                        addk(d, 'INVERSE_TIME_TRIE', {v[:1] for v in vals if v})
                        if not vals:
                            out.add(f'A|{d}|INVERSE_TIME_MAPPING')
                        continue
                    if attr == 'FORMAT_MAPPING':
                        addk(d, 'FORMAT_TRIE', [key[:1]])
                        addk(d, 'INVERSE_FORMAT_MAPPING', set(vals) | {v + 'strict' for v in vals})
                        addk(d, 'INVERSE_FORMAT_TRIE', {v[:1] for v in vals if v})
                        continue
                    if attr == 'INVERSE_TIME_MAPPING':
                        addk(d, 'INVERSE_TIME_TRIE', [key[:1]])
                        continue
                    if attr == 'DATE_PART_MAPPING':
                        addk(d, 'VALID_INTERVAL_UNITS', [key] + vals)
                        if kv and (kv[0] and kv[2] is None or (kv[1] and kv[3] is None)):
                            out.add(f'A|{d}|VALID_INTERVAL_UNITS')
                        continue
                    if attr in ('UNESCAPED_SEQUENCES', 'CREATABLE_KIND_MAPPING'):
                        ders = ['ESCAPED_SEQUENCES', 'IDENTIFIER_ESCAPED_SEQUENCES'] if attr == 'UNESCAPED_SEQUENCES' else ['INVERSE_CREATABLE_KIND_MAPPING']
                        if attr == 'UNESCAPED_SEQUENCES':
                            esc = [v for v in vals if v == '\\' or not v.isprintable()]
                            addk(d, 'IDENTIFIER_ESCAPED_SEQUENCES', vals)
                            addk(d, 'ESCAPED_SEQUENCES', esc)
                            if len(vals) < 2:
                                out.add(f'A|{d}|ESCAPED_SEQUENCES')
                            continue
                        for der in ders:
                            addk(d, der, vals)
                            if len(vals) < 2:
                                out.add(f'A|{d}|{der}')
                        continue
                for der in _DIALECT_DERIVED.get(attr, ()):
                    if der == '*':
                        continue
                    out.add(f'A|{d}|{der}')
                    if key is not None:
                        out.add(f'K|{d}|{der}|{key}')
        if attr == 'arg_types':
            for d in subs:
                out.add(f'A|{d}|required_args')
                if key is not None:
                    out.add(f'K|{d}|required_args|{key}')
        if attr == 'SUPPORTED_JSON_PATH_PARTS':
            for d in subs:
                out.add(f'K|{d}|TRANSFORMS|{key}' if key else f'A|{d}|TRANSFORMS')
    return out

def module_fallback(rel):
    rm = get_readmap()
    mod = _modname(rel)
    res = set()
    if rm is not None:
        for c in rm.mro:
            if c.startswith(mod + '.'):
                for d in rm.subclasses(c):
                    res.update(rm.T(rm.recv.get(d + '\x00*')))
        for k, v in rm.modglob.items():
            if k.startswith(mod + '|'):
                res.update(rm.T(v))
    M = get_cov()
    if M:
        fm = M['files'].get(rel)
        if fm:
            for s in set(fm['lines'].values()):
                res.update(M['sets'][s])
    return res

def static_candidates(patch_text: str, root=None, with_info=False):
    rm = get_readmap()
    paths, notes, ok = static_paths(patch_text, root)
    if rm is not None:
        paths = expand_derived(paths, rm, _LAST_SC[0])
    tests, unresolved = tests_for_paths(paths) if paths else (set(), [])
    fb = sorted({m for n in notes if n.startswith(('unparsable region', 'no spans', 'file added')) for m in re.findall('(sqlglot/\\S+?\\.py)', n)})
    for rel in fb:
        tests |= module_fallback(rel)
    ir = (_load('importreaders.json.gz') or {}).get('entries', {})
    for p in paths:
        parts = p.split('|')
        k = None
        if parts[0] == 'K' and len(parts) >= 4:
            k = f"K\x00{parts[1]}|{parts[2]}\x00{'|'.join(parts[3:])}"
        elif parts[0] == 'MK' and len(parts) >= 4:
            k = f"K\x00M|{parts[1]}|{parts[2]}\x00{'|'.join(parts[3:])}"
        elif parts[0] == 'A' and len(parts) >= 3:
            k = f"A\x00{parts[1]}\x00{'|'.join(parts[2:])}"
        if k is not None and k in ir:
            _IMPORT_EXEC[0].update(ir[k])
    ie = sorted(_IMPORT_EXEC[0])
    info = {'confident': ok and (not unresolved) and (rm is not None), 'paths': sorted(paths), 'notes': notes, 'unresolved': unresolved, 'import_time': bool(paths), 'import_exec_modules': ie, 'needs_dynamic': bool(ie) or not (ok and (not unresolved))}
    return (tests, info) if with_info else tests

def import_exec_fallback(modules):
    out = set()
    for m in modules:
        rel = m.replace('.', '/') + '.py'
        if not os.path.exists(os.path.join(SQLGLOT_ROOT, rel)):
            rel = m.replace('.', '/') + '/__init__.py'
        out |= module_fallback(rel)
    return out

def best_candidates(patch_text, root=None, allow_dynamic=True):
    tests, info = static_candidates(patch_text, root, with_info=True)
    if info['needs_dynamic'] or info['import_time']:
        if allow_dynamic and (info['needs_dynamic'] or not info['confident']):
            dt, dinfo = dynamic_extra_candidates(patch_text, root)
            if dinfo.get('error'):
                info['dynamic_error'] = dinfo['error']
                tests |= import_exec_fallback(info['import_exec_modules'])
            else:
                tests |= dt
                info['dynamic_paths'] = dinfo['paths']
        elif info['import_exec_modules']:
            tests |= import_exec_fallback(info['import_exec_modules'])
    return (tests, info)

def _raw_snapshot_subprocess(root, seed, unordered):
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as tf:
        json.dump(sorted(unordered), tf)
    env = dict(os.environ, PYTHONHASHSEED=str(seed), PYTHONDONTWRITEBYTECODE='1')
    p = subprocess.run([sys.executable, '-I', os.path.abspath(__file__), '--snapshot-raw', root, tf.name], capture_output=True, text=True, env=env, check=True)
    return json.loads(p.stdout.strip().splitlines()[-1])

def build_snapshot(root, out_path):
    a = _raw_snapshot_subprocess(root, 1, ())
    b = _raw_snapshot_subprocess(root, 2, ())
    c = _raw_snapshot_subprocess(root, 3, ())
    unstable = {p for p in set(a) | set(b) | set(c) if not a.get(p) == b.get(p) == c.get(p)}
    a2 = _raw_snapshot_subprocess(root, 1, unstable)
    b2 = _raw_snapshot_subprocess(root, 2, unstable)
    c2 = _raw_snapshot_subprocess(root, 3, unstable)
    unordered = {p for p in unstable if a2.get(p) == b2.get(p) == c2.get(p)}
    ignore = unstable - unordered
    print('unstable', sorted(unstable), 'ignored', sorted(ignore), file=sys.stderr)
    names = module_names(root)
    import_all(names)
    reg, classes = build_registry(names)
    snap, lines = snapshot(names, reg, classes, want_lines=True, unordered=unordered)
    for p in ignore:
        snap[p] = '?'
    for p in snap:
        if snap[p] != a2.get(p) and snap[p] != '?':
            print('in-process disagrees, ignoring', p, file=sys.stderr)
            snap[p] = '?'
    rootabs = os.path.abspath(root)
    lines = {p: (os.path.relpath(f, rootabs), a, b) for p, (f, a, b) in lines.items() if f.startswith(rootabs)}
    mro, owns = ({}, {})
    for name, cls in classes:
        try:
            mro[name] = [reg[id(b)] for b in cls.__mro__[1:] if id(b) in reg]
        except Exception:
            mro[name] = []
        owns[name] = sorted((k for k in cls.__dict__ if k not in SKIP_CLASS_KEYS))
    expr_classes = {}
    try:
        from sqlglot import exp
        for k, c in exp.EXPR_CLASSES.items():
            if id(c) in reg:
                expr_classes[k] = reg[id(c)]
    except Exception:
        pass
    files = {}
    for name, cls in classes:
        m = sys.modules.get(cls.__module__)
        f = getattr(m, '__file__', None)
        if f and os.path.abspath(f).startswith(rootabs):
            files[name] = os.path.relpath(f, rootabs)
    data = {'fp': snap, 'lines': lines, 'mro': mro, 'owns': owns, 'expr_classes': expr_classes, 'class_files': files, 'modules': names, 'unordered': sorted(unordered)}
    with gzip.open(out_path, 'wt') as f:
        json.dump(data, f, separators=(',', ':'))
    print(len(snap), 'paths', len(classes), 'classes', file=sys.stderr)
if __name__ == '__main__':
    if sys.argv[1] == '--dynamic':
        root, MAPDIR = (sys.argv[2], sys.argv[3])
        ch = _dynamic_main(sys.stdin.read(), root)
        sys.stdout.write('\n' + json.dumps(sorted(ch)) + '\n')
    elif sys.argv[1] == '--snapshot-raw':
        root = sys.argv[2]
        sys.path.insert(0, root)
        uo = json.load(open(sys.argv[3]))
        names = module_names(root)
        import_all(names)
        reg, classes = build_registry(names)
        snap, _ = snapshot(names, reg, classes, unordered=uo)
        sys.stdout.write('\n' + json.dumps(snap) + '\n')
    elif sys.argv[1] == '--snapshot':
        root = sys.argv[2]
        sys.path.insert(0, root)
        build_snapshot(root, sys.argv[3])

def extra_candidates(patch_text: str, root=None, with_info=False, allow_dynamic=True):
    tests, info = best_candidates(patch_text, root, allow_dynamic=allow_dynamic)
    return (tests, info) if with_info else tests
