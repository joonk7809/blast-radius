import gzip, json, os, sys, zlib
m = json.load(gzip.open(sys.argv[1], "rt"))
out = sys.argv[2]
os.makedirs(os.path.join(out, "files"), exist_ok=True)
units = [[t, "%08x" % zlib.crc32(k.encode()) if k else ""] for t, k in m["units"]]
meta = {"tests": m["tests"], "units": units, "nunits": m["nunits"], "fixtures": m["fixtures"], "files": sorted(m["files"])}
json.dump(meta, open(os.path.join(out, "meta.json"), "w"), separators=(",", ":"))
sets = m["sets"]
for path, fm in m["files"].items():
    d = {"l": {ln: sets[s] for ln, s in fm["lines"].items()}, "i": fm["import"]}
    json.dump(d, open(os.path.join(out, "files", path.replace("/", "__") + ".json"), "w"), separators=(",", ":"))
