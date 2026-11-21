import gzip, json, re, sys
M = json.load(gzip.open("maps/covmap.json.gz", "rt"))
def parse_patch(text):
    """-> list of (path, old_changed_lines, old_adjacent_lines_for_inserts, added_texts, removed_texts)"""
    out = []; cur = None
    for line in text.splitlines():
        if line.startswith("diff --git"):
            cur = {"path": line.split(" b/")[-1], "removed": [], "anchors": [], "added": [], "rtext": []}; out.append(cur); continue
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)", line)
        if m: old = int(m.group(1)); continue
        if cur is None or line.startswith(("---", "+++", "index ")): continue
        if line.startswith("-"): cur["removed"].append(old); cur["rtext"].append(line[1:]); old += 1
        elif line.startswith("+"): cur["anchors"] += [old - 1, old]; cur["added"].append(line[1:])
        else: old += 1
    return out
def candidates(text):
    c = set(); notes = []
    for f in parse_patch(text):
        p = f["path"]
        if p in M["fixtures"]:
            c |= set(M["fixtures"][p]); notes.append("fixture"); continue
        fm = M["files"].get(p)
        if fm is None: notes.append("nomap:" + p); continue
        lines = set(f["removed"]) | set(f["anchors"])
        imp = set(fm["import"]); hit = False
        for ln in lines:
            s = fm["lines"].get(str(ln))
            if s is not None: c |= set(M["sets"][s]); hit = True
            if ln in imp: notes.append(f"import:{p}:{ln}")
        if not hit: notes.append("nohit:" + p)
    return c, notes
if __name__ == "__main__":
    import glob, os
    A = json.load(open("sample/answers.json"))["commits"]
    dur = M["dur"]
    for pf in sorted(glob.glob("sample/commits/*.patch")):
        cid = os.path.basename(pf)[:-6]
        c, notes = candidates(open(pf).read())
        fail = set(A[cid]["failing"]); miss = fail - c
        print(cid, A[cid]["kind"], "fail", len(fail), "cand", len(c), "candsec %.1f" % sum(dur[i] for i in c), "MISS" if miss else "", sorted(miss)[:5], notes[:3])
