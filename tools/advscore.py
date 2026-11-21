import glob, json, os, sys

S = sys.argv[1]
ADV = os.environ.get("ADV", "/mnt/project-files/blast-radius/challenger/adv")
t = json.load(open(os.path.join(S, "tests.json")))["tests"]
num = {x["id"]: x["number"] for x in t}
ms = {x["number"]: int(x["seconds"] * 1000 + 0.5) for x in t}
out = {json.loads(l)["commit"]: json.loads(l)["workers"] for l in open(os.path.join(S, "out.jsonl"))}
tot = 0
for f in sorted(glob.glob(ADV + "/*.patch")):
    b = os.path.basename(f)[:-6]
    w = out.get(b.split("_")[0]) or []
    sel = {n for x in w for n in x}
    c = (max(sum(ms[n] for n in x) for x in w) + 2000 * len(w)) / 1000 if w else 0
    g = f[:-6] + ".gt.json"
    gt = {num[i] for i in json.load(open(g))["failed"] if i in num} if os.path.exists(g) else None
    miss = sorted(gt - sel) if gt is not None else []
    c += 300 if miss else 0
    tot += c
    print(b, "nsel", len(sel), "cost %.1f" % c, "" if gt is None else ("MISS %s" % miss if miss else "ok"))
print("adv simulated %.1f" % tot, open(os.path.join(S, "out.stderr")).read().splitlines()[-1])
