"""Independent sorted-record simulator; does not use a heap or Mesa."""


def expected(case, size, seed):
    if case not in {"reschedule", "repeat-cancel", "clear-reuse", "cancel-popped", "compact", "priority"} or size < 1:
        raise ValueError("unsupported case")
    priorities = (1, 5, 10)
    serial = 0
    active = {}

    def add(identity, generation):
        nonlocal serial
        active[identity] = ((17 * identity + seed) % 19 + 32 * generation,
                            priorities[(identity + generation) % 3], serial,
                            identity, generation)
        serial += 1

    def ordered():
        return [[r[3], r[4]] for r in sorted(active.values())]

    for i in range(size):
        add(i, 0)
    counts, peeks, executed = [size], [], []
    generations = 8 if case in {"reschedule", "repeat-cancel", "compact"} else 0
    for generation in range(1, generations + 1):
        for i in range(size):
            active.pop(i)
            if i % 32 == 0:
                counts.append(len(active))
            add(i, generation)
            if i % 32 == 0:
                counts.append(len(active))
        peeks.append(ordered()[:3])
    if case == "clear-reuse":
        active.clear()
        counts.append(0)
        for i in range(size):
            add(i, 1)
        # The retained old event is no longer a member of this queue.
        counts.append(size)
    elif case == "cancel-popped":
        first = ordered()[0]
        active.pop(first[0])
        executed.append(first)
        counts.append(size - 1)
    elif case == "priority":
        peeks.append(ordered()[:min(5, size)])
    executed.extend(ordered())
    counts.append(0)
    return {"executed": executed, "counts": counts, "peeks": peeks,
            "empty_pop_exception": "IndexError"}
