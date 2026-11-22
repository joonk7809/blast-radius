import sys

CAT = ("other", "blind", "plan-time heavy listed", "memo:plain", "memo:state", "lean native", "lean ckhooks", "killed/unresolved/broken")
SUB = {
    1: ("blind", "blind:memo", "-", "-"),
    3: ("touched 0", "touched 1-5", "touched 6-20", "touched >20"),
    4: ("touched 0", "touched 1-5", "touched 6-20", "touched >20"),
    5: ("plain", "opt", "wide", "opt+wide"),
    6: ("clean", "nogo", "fallbacks", "nogo+fallbacks"),
    7: ("unresolved, not killed", "killed over CPU cap", "killed at deadline", "module does not import"),
}
CPU = ("<1 s", "1-3 s", "3-6 s", "6-12 s", "12-25 s", ">=25 s")
HEAVY = ("no unconfirmed heavy", "1106", "other heavy (>=2 s)", "1106 + other heavy")
UB = ("2.5-3.5 s", "3.5-8 s", "8-20 s", ">=20 s")


def main():
    sim = float(sys.argv[1])
    base = float(sys.argv[2]) if len(sys.argv) > 2 else 97.337
    t = round((sim - base) * 1000)
    print("delta %d ms" % t)
    if t < 0 or t >= 4 * 3072 * 48:
        print("out of range: the selection itself moved between runs, no decoding")
        return
    n, c = t % 4, t // 4
    c0, c1 = c % 3072, c // 3072
    print("hidden commits with U >= 2.5 s: %s" % ("3 or more" if n == 3 else n))
    if n == 0:
        if c:
            print("inconsistent: no commits but nonzero codes")
        return
    cat, sub, cpu, hv, ub = c0 % 8, c0 // 8 % 4, c0 // 32 % 6, c0 // 192 % 4, c0 // 768
    print("largest-U commit: U %s, %s (%s), child CPU %s, %s" % (UB[ub], CAT[cat], SUB.get(cat, ("-",) * 4)[sub], CPU[cpu], HEAVY[hv]))
    if n >= 2:
        if c1 >= 48:
            print("inconsistent second code %d" % c1)
            return
        print("second-largest: %s, child CPU %s" % (CAT[c1 % 8], CPU[c1 // 8]))
    elif c1:
        print("inconsistent: second code without a second commit")


if __name__ == "__main__":
    main()
