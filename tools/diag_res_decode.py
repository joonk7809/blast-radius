import sys

DIGITS = (
    "sample commits whose listing cost differs from the offline 8fbb263 run",
    "hidden commits with unconfirmed listing cost U >= 20 s",
    "hidden commits with U in [8, 20) s",
    "hidden commits with U in [3.5, 8) s",
    "hidden commits with U in [2.5, 3.5) s",
    "hidden commits with U in (0, 2.5) s",
)


def main():
    sim = float(sys.argv[1])
    base = float(sys.argv[2]) if len(sys.argv) > 2 else 97.337
    delta = round((sim - base) * 1000)
    print("delta %d ms" % delta)
    if delta < 0 or delta >= 8 ** len(DIGITS):
        print("out of range: the selection itself moved between runs, no decoding")
        return
    for d, text in enumerate(DIGITS):
        print("  %d  %s" % (delta // 8 ** d % 8, text))


if __name__ == "__main__":
    main()
