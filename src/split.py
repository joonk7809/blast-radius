def split(nums, ms):
    if not nums:
        return []
    order = sorted(nums, key=lambda n: -ms[n])
    best = None
    for k in range(1, min(8, len(order)) + 1):
        loads = [0] * k
        bins = [[] for _ in range(k)]
        for n in order:
            i = loads.index(min(loads))
            loads[i] += ms[n]
            bins[i].append(n)
        cost = max(loads) + 2000 * k
        if best is None or cost < best[0]:
            best = (cost, bins)
    return best[1]
