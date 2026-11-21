import json, re, sys

sys.path.insert(0, "src")
from split import cost

d = sys.argv[1]
out_path = sys.argv[2] if len(sys.argv) > 2 else d + "/o.jsonl"
t = json.load(open(d + "/tests.json"))["tests"]
ms = {x["number"]: int(x["seconds"] * 1000 + 0.5) for x in t}
ans = json.load(open(d + "/answers.json"))["commits"]
out = {json.loads(l)["commit"]: json.loads(l)["workers"] for l in open(out_path)}
cpu, notes = {}, {}
for l in open(out_path + ".stderr"):
    m = re.match(r"(\w+) fail .* cpu=([\d.]+)", l)
    if m:
        cpu[m[1]] = float(m[2])
    m = re.match(r"(\w+) cands (\d+) .*est_cpu [\d.]+ (.*)", l)
    if m:
        notes[m[1]] = m[3][:80]
rows = []
for c, a in ans.items():
    f = set(a["failing"])
    w = out.get(c, [])
    sel = {n for x in w for n in x}
    sim = (max(sum(ms[n] for n in x) for x in w) + 2000 * len(w)) / 1000 if w else 0
    o = cost(sorted(f), ms) / 1000
    rows.append((sim - o, c, sim, o, cpu.get(c, 0), len(sel - f), sorted(f - sel)[:3], notes.get(c, ""), a.get("kind")))
rows.sort(reverse=True)
print("waste %.1f oracle %.1f cpu %.1f" % (sum(r[0] for r in rows), sum(r[3] for r in rows), sum(r[4] for r in rows)))
for r in rows[:15]:
    print("%-8s waste %6.1f sim %6.1f oracle %6.1f cpu %5.1f extra %4d miss %s %s %s" % (r[1], r[0], r[2], r[3], r[4], r[5], r[6], r[8], r[7]))
