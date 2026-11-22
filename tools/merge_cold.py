import array, gzip, json, lzma, os, sys

meta_in, sets_in, cold_dir, meta_out, sets_out = sys.argv[1:6]
m = json.load(gzip.open(meta_in, "rt"))
raw = lzma.open(sets_in).read()
n = int.from_bytes(raw[:4], "little")
offs = memoryview(raw)[4:4 + 4 * n].cast("I")
data = memoryview(raw)[4 + 4 * n:].cast("H")
sets = [list(data[offs[i]:offs[i + 1]]) for i in range(n - 1)]
idx = {t: i for i, t in enumerate(m["tests"])}
units = m["units"]
whole = {t: u for u, (t, k) in enumerate(units) if not k}
cold = {}
for name in os.listdir(cold_dir):
    d = json.load(open(os.path.join(cold_dir, name)))
    t = idx.get(d["id"])
    if t is None:
        continue
    for f, lines in d["files"].items():
        fc = cold.setdefault(f, {})
        for ln in lines:
            fc.setdefault(str(ln), set()).add(t)
setidx = {tuple(s): i for i, s in enumerate(sets)}
added = lines_hit = new_lines = 0
for f, fc in cold.items():
    fm = m["files"].get(f)
    if fm is None:
        continue
    lm = fm["lines"]
    imp = set(map(str, fm["import"]))
    for ln, ts in fc.items():
        old = sets[lm[ln]] if ln in lm else []
        if ln not in lm and ln not in imp:
            continue
        have = {units[u][0] for u in old}
        delta = ts - have
        if not delta:
            continue
        for t in delta:
            if t not in whole:
                whole[t] = len(units)
                units.append([t, ""])
        key = tuple(sorted(set(old) | {whole[t] for t in delta}))
        if key not in setidx:
            setidx[key] = len(sets)
            sets.append(list(key))
        new_lines += ln not in lm
        lm[ln] = setidx[key]
        added += len(delta)
        lines_hit += 1
assert len(units) < 65536
out_offs = array.array("I", [0])
out_data = array.array("H")
for s in sets:
    out_data.extend(sorted(s))
    out_offs.append(len(out_data))
with lzma.open(sets_out, "wb", preset=9 | lzma.PRESET_EXTREME) as fh:
    fh.write(len(out_offs).to_bytes(4, "little"))
    out_offs.tofile(fh)
    out_data.tofile(fh)
with gzip.open(meta_out, "wt", compresslevel=9) as fh:
    json.dump(m, fh, separators=(",", ":"))
print("lines %d (new %d) credits %d units %d sets %d" % (lines_hit, new_lines, added, len(units), len(sets)), file=sys.stderr)
