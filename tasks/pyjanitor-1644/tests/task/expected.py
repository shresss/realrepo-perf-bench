"""Independent stdlib sorted-query heap oracle; imports no candidate code."""
import hashlib
import heapq
import json
import random


def expected(case, size, seed):
    op, keep, layout = case.split(":")
    rng = random.Random(seed)
    values = [[rng.randrange(-max(size, 1), max(size, 1)) for _ in range(size)] for _ in range(2)]
    left, right = values
    if layout == "sorted":
        right.sort()
    elif layout == "reverse":
        right.sort(reverse=True)
    elif layout == "ties":
        left, right = [[x % 7 for x in vector] for vector in (left, right)]
    elif layout == "nulls":
        left = [None if i % 11 == 0 else x for i, x in enumerate(left)]
        right = [None if i % 7 == 0 else x for i, x in enumerate(right)]
    elif layout not in {"unsorted", "datetime"}:
        raise ValueError(layout)
    descending = op.startswith("<")
    queries = sorted(((x, i) for i, x in enumerate(left) if x is not None), reverse=descending)
    targets = sorted(((x, i) for i, x in enumerate(right) if x is not None), reverse=descending)
    selected = {}
    heap = []
    cursor = 0
    for value, left_id in queries:
        while cursor < len(targets):
            other, position = targets[cursor]
            eligible = other > value if descending else other < value
            eligible = eligible or ("=" in op and other == value)
            if not eligible:
                break
            heapq.heappush(heap, position if keep == "first" else -position)
            cursor += 1
        if heap:
            selected[left_id] = heap[0] if keep == "first" else -heap[0]
    pairs = [[i, selected[i]] for i in sorted(selected)]
    return {
        "count": len(pairs),
        "pairs_sha256": hashlib.sha256(json.dumps(pairs, separators=(",", ":")).encode()).hexdigest(),
        "pairs": pairs if size <= 64 else None,
        "input_unchanged": True,
        "index_names": ["left_original", "right_original"],
    }
