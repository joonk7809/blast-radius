import glob, gzip, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import importtime as IT
ROOT = '/tmp/claude-0/mut/base'
IT.SQLGLOT_ROOT = ROOT
_T = json.load(open('/home/user/blast-radius/sample/tests.json'))['tests']
DUR = [0.0] * 1620
for _t in _T:
    DUR[_t['number']] = _t['seconds']
CACHE = os.path.join(HERE, '..', 'eval_cache.json')
cache = json.load(open(CACHE)) if os.path.exists(CACHE) and '--refresh' not in sys.argv else {}

def cases():
    out = []
    for p in sorted(glob.glob(os.path.join(HERE, '..', 'mutants', '*.patch'))):
        n = os.path.basename(p)[:-6]
        lp = os.path.join(HERE, '..', 'labels', n + '.json')
        if os.path.exists(lp):
            lab = json.load(open(lp))
            if 'failing' in lab:
                out.append((n, open(p).read(), set(lab['failing'])))
    A = json.load(open('/home/user/blast-radius/sample/answers.json'))['commits']
    for p in sorted(glob.glob('/home/user/blast-radius/sample/commits/*.patch')):
        n = os.path.basename(p)[:-6]
        out.append(('s_' + n, open(p).read(), set(A[n]['failing'])))
    return out
_TIDALL = {}

def coarse_tests(paths):
    rm = IT.get_readmap()
    if not _TIDALL:
        for k, v in rm.key.items():
            tid = k.split('\x00')[0]
            _TIDALL.setdefault(tid, set()).update(rm.T(v))
    out = set()
    for p in paths:
        parts = p.split('|')
        if parts[0] == 'K':
            tid = f'{parts[1]}|{parts[2]}'
            out |= _TIDALL.get(tid, set()) | set(rm.T(rm.star.get(tid)))
            out |= IT._attr_tests(rm, parts[1], parts[2])
            if parts[2] == 'TRANSFORMS':
                for d in rm.subclasses(parts[1]):
                    out |= set(rm.T(rm.star.get('D|' + d)))
        elif parts[0] == 'MK':
            tid = f'M|{parts[1]}|{parts[2]}'
            out |= _TIDALL.get(tid, set()) | set(rm.T(rm.star.get(tid)))
        else:
            out |= IT.tests_for_paths({p})[0]
    return out

def fallback_tests(text):
    out = set()
    for f in IT.parse_patch(text):
        rel = f['new'] or f['old']
        if rel and rel.endswith('.py') and rel.startswith('sqlglot/'):
            out |= IT.module_fallback(rel)
    return out

def main():
    rows = []
    for n, text, fail in cases():
        if n not in cache:
            t = time.time()
            paths, err = IT.dynamic_changed_paths(text, ROOT)
            cache[n] = {'paths': sorted(paths) if paths is not None else None, 'err': err, 'wall': time.time() - t}
        dyn, _ = IT.tests_for_paths(set(cache[n]['paths'] or []))
        t = time.process_time()
        st, info = IT.static_candidates(text, ROOT, with_info=True)
        stt = time.process_time() - t
        best = st | dyn if info['needs_dynamic'] or not info['confident'] else st
        it = info['import_time'] or bool(cache[n]['paths'])
        coarse = coarse_tests(set(cache[n]['paths'] or [])) if '--ablate' in sys.argv else set()
        fb = fallback_tests(text) if '--ablate' in sys.argv and it else set()
        rows.append(dict(n=n, fail=fail, dyn=dyn, st=st, best=best, coarse=coarse, fallback=fb, stt=stt, conf=info['confident'], esc=info['needs_dynamic'] or not info['confident'], it=info['import_time'] or bool(cache[n]['paths'])))
    json.dump(cache, open(CACHE, 'w'))

    def sec(c):
        return sum((DUR[i] for i in c))
    for r in rows:
        md, ms = (r['fail'] - r['dyn'], r['fail'] - r['st'])
        print('%-18s fail=%3d | dyn %4d %7.2fs %-10s| static %4d %7.2fs %-10s t=%.3f%s' % (r['n'], len(r['fail']), len(r['dyn']), sec(r['dyn']), 'MISS%d' % len(md) if md else '', len(r['st']), sec(r['st']), 'MISS%d' % len(ms) if ms else '', r['stt'], ' (escalate->dynamic)' if r['esc'] else ''))
    for label, sel in (('mutants', [r for r in rows if not r['n'].startswith('s_')]), ('sample import-time', [r for r in rows if r['n'].startswith('s_') and r['it']])):
        if not sel:
            continue
        for tier in ('dyn', 'st', 'best') + (('coarse', 'fallback') if '--ablate' in sys.argv else ()):
            ok = sum((1 for r in sel if r['fail'] <= r[tier]))
            wf = [r for r in sel if r['fail']]
            okf = sum((1 for r in wf if r['fail'] <= r[tier]))
            tot = sum((sec(r[tier]) for r in sel))
            print(f"{label:20s} {tier:4s} n={len(sel)} recall={ok}/{len(sel)} (patches with failures {okf}/{len(wf)}) sum_sec={tot:.1f} mean_sec={tot / len(sel):.2f} max_static_t={max((r['stt'] for r in sel)):.3f}" + (f" escalations={sum((1 for r in sel if r['esc']))}" if tier == 'best' else ''))
if __name__ == '__main__':
    main()
