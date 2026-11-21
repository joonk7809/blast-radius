import array, gzip, json, lzma, sys

src, meta_out, sets_out = sys.argv[1:4]
m = json.load(gzip.open(src, "rt"))
assert len(m["units"]) < 65536
offs = array.array("I", [0])
data = array.array("H")
for s in m.pop("sets"):
    data.extend(sorted(s))
    offs.append(len(data))
with lzma.open(sets_out, "wb", preset=9 | lzma.PRESET_EXTREME) as fh:
    fh.write(len(offs).to_bytes(4, "little"))
    offs.tofile(fh)
    data.tofile(fh)
with gzip.open(meta_out, "wt", compresslevel=9) as fh:
    json.dump(m, fh, separators=(",", ":"))
