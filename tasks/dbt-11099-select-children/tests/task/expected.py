"""Stdlib reachability oracle; imports no package, candidate, or workload."""
from collections import deque
import hashlib
import json
import random


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def warehouse(count, seed):
    rng = random.Random(seed)
    source_ids = [f"source.warehouse.raw.raw_{j}" for j in range(6)]
    names = [f"model.warehouse.layer{min(3, 4 * j // count)}_{j:05d}" for j in range(count)]
    partitions = [[names[j] for j in range(count) if min(3, 4 * j // count) == level] for level in range(4)]
    node_ids = source_ids + names
    edges = []
    descendants = {}
    for level in range(4):
        choices = source_ids if level == 0 else partitions[level - 1]
        for target in partitions[level]:
            for origin in rng.sample(choices, min(3, len(choices))):
                edges.append((origin, target, None))
                descendants.setdefault(origin, []).append(target)
    for j, model_id in enumerate(names):
        test_id = f"test.warehouse.unique_{j:05d}"
        node_ids.append(test_id)
        edges.append((model_id, test_id, None))
        for target in descendants.get(model_id, []):
            if rng.random() < 0.3:
                edges.append((test_id, target, "parent_test"))
    queries = []
    for team in range(6):
        for operation, level in (("children", 0), ("parents", 3), ("at", 1)):
            selection = [names[j] for j in range(count) if j % 6 == team and min(3, 4 * j // count) == level]
            queries.append((f"team{team}-{operation}", operation, selection, None))
    return node_ids, edges, queries, []


def small(case, seed):
    vertices = list("abcdt")
    connections = [("a", "b", None), ("a", "c", None), ("b", "d", None), ("c", "d", "other")]
    requests = [("children", "children", ["a"], None), ("parents", "parents", ["d"], None),
                ("at", "at", ["b"], None)]
    changes = []
    if case == "empty":
        return [], [], [("empty-children", "children", [], None), ("empty-parents", "parents", [], None),
                        ("empty-at", "at", [], None)], []
    if case == "singleton":
        return ["a"], [], [("singleton-children", "children", ["a"], None),
                           ("singleton-parents", "parents", ["a"], 1), ("singleton-at", "at", ["a"], None)], []
    if case == "chain":
        connections = [("a", "b", None), ("b", "c", None), ("c", "d", None)]
    elif case == "diamond":
        pass
    elif case == "overlap":
        requests = [("overlap-children", "children", ["a", "b"], None),
                    ("overlap-parents", "parents", ["b", "d"], None), ("overlap-at", "at", ["b", "c"], None)]
    elif case.startswith("depth-"):
        bound = int(case[6:])
        requests = [(f"depth{bound}-children", "children", ["a"], bound),
                    (f"depth{bound}-parents", "parents", ["d"], bound)]
    elif case in ("parent-test", "selected-test"):
        connections = [("a", "t", None), ("t", "b", "parent_test"), ("b", "c", None)]
        if case == "parent-test":
            requests = [("parent-test-children", "children", ["a"], None),
                        ("parent-test-parents", "parents", ["b"], None), ("parent-test-at", "at", ["a"], None)]
        else:
            requests = [("test-children", "children", ["t"], None), ("test-parents", "parents", ["t"], None),
                        ("test-at", "at", ["t"], None)]
    elif case == "mutation":
        connections = [("a", "b", None), ("b", "c", None)]
        requests = [("before", "children", ["a"], None), ("after", "children", ["a"], None),
                    ("after-parents", "parents", ["c"], None)]
        changes = [(1, "remove", "a", "b", None), (1, "add", "a", "d", None)]
    elif case == "random-small":
        rng = random.Random(seed)
        vertices = [f"m{j}" for j in range(18)] + [f"t{j}" for j in range(18)]
        connections = [(f"m{j}", f"t{j}", None) for j in range(18)]
        for target in range(1, 18):
            for origin in rng.sample(range(target), min(2, target)):
                connections.extend([(f"m{origin}", f"m{target}", None),
                                    (f"t{origin}", f"m{target}", "parent_test")])
        requests = [("random-children", "children", ["m0", "m1"], 3),
                    ("random-parents", "parents", ["m17", "m12"], None),
                    ("random-at", "at", ["m8", "t2"], None)]
    else:
        raise ValueError(case)
    return vertices, connections, requests, changes


def reachable(links, selected, maximum):
    # Separate per-seed shortest-path searches define reachability independently
    # of dbt's layer-based implementation. DAG inputs have no return-to-seed path.
    result = set()
    for seed in selected:
        visited = {seed}
        queue = deque([(seed, 0)])
        while queue:
            current, distance = queue.popleft()
            if maximum is not None and distance >= maximum:
                continue
            for target in links.get(current, ()):
                if target not in visited:
                    visited.add(target)
                    result.add(target)
                    queue.append((target, distance + 1))
    return result


def expected(case, size, seed):
    vertices, edges, queries, mutations = warehouse(size, seed) if case == "lineage" else small(case, seed)
    values = []
    for index, (label, operation, selected, depth) in enumerate(queries):
        for at, action, origin, target, kind in mutations:
            if at == index:
                if action == "remove":
                    edges = [edge for edge in edges if edge[:2] != (origin, target)]
                else:
                    edges.append((origin, target, kind))
        forward, reverse = {}, {}
        for origin, target, kind in edges:
            if kind != "parent_test":
                forward.setdefault(origin, []).append(target)
                reverse.setdefault(target, []).append(origin)
        if operation == "children":
            result = reachable(forward, selected, depth)
        elif operation == "parents":
            result = reachable(reverse, selected, depth)
        else:
            included = reachable(forward, selected, None) | set(selected)
            result = included | reachable(reverse, included, None)
        # NodeSelector's public caller includes explicitly tag-matched nodes in
        # addition to the specified neighbors, even for a depth-zero modifier.
        result |= set(selected)
        values.append({"label": label, "nodes": sorted(result)})
    value = {"queries": len(values), "node_count": len(vertices), "edge_count": len(edges),
             "output_sha256": digest(values), "output_counts": [len(item["nodes"]) for item in values],
             "input_unchanged": True}
    if case != "lineage" or size <= 20:
        value["outputs"] = values
    return value
