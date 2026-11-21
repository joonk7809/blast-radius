import glob, gzip, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import importtime as IT
ROOT = '/tmp/claude-0/mut/base'
IT.SQLGLOT_ROOT = ROOT
DUR = [0.0] * 1620
for _t in json.load(open('/home/user/blast-radius/sample/tests.json'))['tests']:
    DUR[_t['number']] = _t['seconds']
CP = os.path.join(HERE, '..', 'dyn_paths_cache.json')
cache = json.load(open(CP)) if os.path.exists(CP) else {}
pats = sorted(glob.glob(os.path.join(HERE, '..', 'mutants', '*.patch'))) + sorted(glob.glob('/home/user/blast-radius/sample/commits/*.patch'))
pats += sorted(glob.glob(os.environ.get('EXTRA_MUT', '/tmp/claude-0/mut2') + '/*.patch'))
if len(sys.argv) > 1:
    pats = [p for p in pats if any((a in p for a in sys.argv[1:]))]
IT.get_readmap()
IT._load('spans.json.gz')
IT._load('fp.json.gz')
bad = 0
for p in pats:
    n = os.path.basename(p)[:-6]
    text = open(p).read()
    if n not in cache:
        ps, err = IT.dynamic_changed_paths(text, ROOT)
        cache[n] = sorted(ps) if ps is not None else None
    dp = set(cache[n] or [])
    dt, _ = IT.tests_for_paths(dp)
    t = time.process_time()
    st, info = IT.static_candidates(text, ROOT, with_info=True)
    el = time.process_time() - t
    miss = dt - st
    flag = 'MISS' if miss else ''
    if miss:
        bad += 1
    print(f'{n:16s} dyn={len(dt):4d} {sum((DUR[i] for i in dt)):6.2f}s  stat={len(st):4d} {sum((DUR[i] for i in st)):6.2f}s t={el:.3f} {flag} {len(miss)}')
    if miss or '-v' in os.environ.get('V', ''):
        print('   dyn:', sorted(dp)[:6])
        print('   sta:', info['paths'][:8], info['notes'][:3])
json.dump(cache, open(CP, 'w'))
print('static misses vs dynamic:', bad, '/', len(pats))
