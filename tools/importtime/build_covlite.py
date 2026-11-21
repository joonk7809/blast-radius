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
cache, sets, sidx = ({}, [], {})

def conv(i):
    if i not in cache:
        ts = tuple(sorted({unit_t[u] for u in data[offs[i]:offs[i + 1]].tolist() if unit_t[u] is not None}))
        if ts not in sidx:
            sidx[ts] = len(sets)
            sets.append(list(ts))
        cache[i] = sidx[ts]
    return cache[i]
files = {rel: {'lines': {ln: conv(s) for ln, s in fm['lines'].items()}} for rel, fm in M['files'].items()}
with gzip.open(out_p, 'wt') as f:
    json.dump({'files': files, 'sets': sets}, f, separators=(',', ':'))
print(len(files), len(sets), file=sys.stderr)
