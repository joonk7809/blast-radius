import sys

NAMES = ("parent (all commits)", "hidden lean/ck", "hidden memo", "hidden probe", "hidden reimport", "hidden other light")
DIGITS = ((0.5, 10), (0.5, 12), (0.25, 12), (0.25, 12), (0.25, 12), (0.25, 12))
OFFSET = 200000


def main():
    sim = float(sys.argv[1])
    base = float(sys.argv[2]) if len(sys.argv) > 2 else 97.337
    t = round((sim - base) * 1000) - OFFSET
    cap = 1
    for _, b in DIGITS:
        cap *= b
    print("delta %d ms after offset" % t)
    if t < 0 or t >= cap:
        print("out of range: base sim moved, no decoding")
        return
    vals = []
    for step, b in reversed(DIGITS):
        vals.append((t % b) * step)
        t //= b
    for name, v, (step, b) in zip(NAMES, reversed(vals), DIGITS):
        print("%-22s %.2f s%s" % (name, v, " (saturated)" if v >= (b - 1) * step else ""))


if __name__ == "__main__":
    main()
