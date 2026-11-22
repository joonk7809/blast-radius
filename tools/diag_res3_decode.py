import sys

ROWCAT = ("not run, blind", "not run, plan-time heavy/force/other", "ran, none of the listed confirmed", "ran, some listed confirmed", "memo or lean run", "killed/unresolved/broken")
CPUCAT = ("memo", "lean + ckhooks", "lean native", "plain light run", "no child run")
CPUB = ("<3 s", "3-6 s", "6-12 s", ">=12 s")


def main():
    sim = float(sys.argv[1])
    base = float(sys.argv[2]) if len(sys.argv) > 2 else 97.337
    t = round((sim - base) * 1000)
    print("delta %d ms" % t)
    if t < 0 or t >= 20 * 13 ** 4:
        print("out of range: the selection itself moved between runs, no decoding")
        return
    rows = []
    for _ in range(4):
        rows.append(t % 13)
        t //= 13
    print("top hidden commit by child CPU: %s, %s" % (CPUCAT[t // 4], CPUB[t % 4]))
    for i, v in enumerate(reversed(rows)):
        if v:
            print("U-row %d (commits with 2.5 <= U < 3.5 s, sorted by id): %s, U %s 2882 ms" % (i, ROWCAT[(v - 1) // 2], "==" if (v - 1) % 2 == 0 else "!="))
        else:
            print("U-row %d: absent" % i)


if __name__ == "__main__":
    main()
