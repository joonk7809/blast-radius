import glob, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import importtime as IT
ROOT = '/tmp/claude-0/mut/base'
IT.SQLGLOT_ROOT = ROOT
DC = os.path.join(HERE, '..', 'dyn_units_cache.json')
dcache = json.load(open(DC)) if os.path.exists(DC) else {}

def cases():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, '..', 'mutants', '*.patch'))):
        n = os.path.basename(p)[:-6]
        lp = os.path.join(HERE, '..', 'labels', n + '.json')
        if os.path.exists(lp):
            lab = json.load(open(lp))
            if 'failing' in lab:
                out.append((n, open(p).read(), sorted(lab['failing'])))
    A = json.load(open('/tmp/val/answers.json'))['commits']
    for p in sorted(glob.glob('/tmp/val/commits/*.patch')):
        n = os.path.basename(p)[:-6]
        out.append(('v_' + n, open(p).read(), sorted(A[n]['failing'])))
    return out
_orig = IT.dynamic_changed_paths

def cached_dyn(text, root=None, timeout=60):
    import hashlib
    h = hashlib.sha1(text.encode()).hexdigest()
    if h not in dcache:
        p, e = _orig(text, root, timeout)
        dcache[h] = [sorted(p) if p is not None else None, e]
    p, e = dcache[h]
    return (set(p) if p is not None else None, e)
IT.dynamic_changed_paths = cached_dyn
res = {}
for n, text, fail in cases():
    t = time.process_time()
    items, info = IT.best_candidates(text, ROOT, items=True)
    el = time.process_time() - t
    u = IT.items_to_units(items)
    res[n] = {'fail': fail, 'units': {str(k): None if v is None else sorted(v) for k, v in u.items()}, 't': el}
json.dump(dcache, open(DC, 'w'))
json.dump(res, open(sys.argv[1], 'w'))
print(len(res), 'cases', file=sys.stderr)
