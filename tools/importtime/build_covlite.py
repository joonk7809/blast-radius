import gzip, json, lzma, sys
meta_p, sets_p, ids_p, out_p = sys.argv[1:5]
M = json.load(gzip.open(meta_p, 'rt'))
raw = lzma.open(sets_p).read() if sets_p.endswith('.xz') else open(sets_p, 'rb').read()
n = int.from_bytes(raw[:4], 'little')
offs = memoryview(raw)[4:4 + 4 * n].cast('I')
data = memoryview(raw)[4 + 4 * n:].cast('H')
num = {t.strip(): i for i, t in enumerate(open(ids_p))}
tnum = [num.get(t) for t in M['tests']]
unit_t = [tnum[t] for t, k in M['units']]
unit_k = [k for t, k in M['units']]
names, nidx = ([], {})
usets, uidx = ([], {})

def uset(keys):
    ids = []
    for k in keys:
        if k not in nidx:
            nidx[k] = len(names)
            names.append(k)
        ids.append(nidx[k])
    s = ','.join(map(str, sorted(ids)))
    if s not in uidx:
        uidx[s] = len(usets)
        usets.append(s)
    return uidx[s]
cache, sets, sidx = ({}, [], {})

def conv(i):
    if i not in cache:
        d = {}
        for u in data[offs[i]:offs[i + 1]].tolist():
            t = unit_t[u]
            if t is None:
                continue
            k = unit_k[u]
            if k == '':
                d[t] = None
            elif d.get(t, 0) is not None:
                d.setdefault(t, set()).add(k)
        s = ','.join((str(t) if d[t] is None else '%d:%d' % (t, uset(d[t])) for t in sorted(d)))
        if s not in sidx:
            sidx[s] = len(sets)
            sets.append(s)
        cache[i] = sidx[s]
    return cache[i]
tunits = {}
for (t, k), tn in zip(M['units'], unit_t):
    if k and tn is not None:
        if k not in nidx:
            nidx[k] = len(names)
            names.append(k)
        tunits.setdefault(tn, []).append(nidx[k])
files = {rel: {'lines': {ln: conv(s) for ln, s in fm['lines'].items()}} for rel, fm in M['files'].items()}
with gzip.open(out_p, 'wt') as f:
    json.dump({'files': files, 'sets': sets, 'usets': usets, 'units': names, 'tunits': {str(t): ','.join(map(str, v)) for t, v in tunits.items()}}, f, separators=(',', ':'))
print(len(files), len(sets), len(usets), len(names), file=sys.stderr)
