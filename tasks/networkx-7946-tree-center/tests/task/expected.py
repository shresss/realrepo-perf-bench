"""Independent stdlib oracle; no NetworkX import or production implementation."""
from collections import deque
import heapq

# Embedded deterministic stdlib fixtures.
"""Deterministic stdlib fixtures; no dependency on NetworkX generators."""
import hashlib
import json
import random


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def graph(edges=(), nodes=None, **options):
    edges = [list(edge) for edge in edges]
    if nodes is None:
        nodes = list(dict.fromkeys(v for edge in edges for v in edge[:2]))
    return {"nodes": list(nodes), "edges": edges, "directed": False,
            "multigraph": False, **options}


def schema_pairs(size, seed):
    if size < 20:
        raise ValueError("schema_pairs requires at least 20 nodes")
    rng = random.Random(seed)
    pairs = []
    for i in range(6):
        spine = size // 10 + i
        first = [(v, v + 1) for v in range(spine - 1)]
        first.extend((rng.randrange(v), v) for v in range(spine, size))
        second = first
        if i >= 4:
            degree = [0] * size
            for u, v in first:
                degree[u] += 1
                degree[v] += 1
            leaves = [v for v in range(size) if degree[v] == 1 and v > 0]
            leaf = leaves[rng.randrange(len(leaves))]
            second = [(u, v) for u, v in first if leaf not in (u, v)]
            hubs = sorted(range(size), key=lambda v: -degree[v])
            second.append((hubs[0] if hubs[0] != leaf else hubs[1], leaf))
        permutation = list(range(size))
        rng.shuffle(permutation)
        second = [(permutation[u], permutation[v]) for u, v in second]
        rng.shuffle(second)
        pairs.append([graph(first), graph(second)])
    return pairs


def edge_pairs():
    path = lambda n: graph([(v, v + 1) for v in range(n - 1)], list(range(n)))
    star = lambda n: graph([(0, v) for v in range(1, n)], list(range(n)))
    binary = graph([(v, 2 * v + k) for v in range(7) for k in (1, 2)])
    # Equal node counts and degree sequences, but different unrooted shapes.
    a = graph([(0, 1), (0, 2), (0, 3), (1, 4), (4, 5), (5, 6)])
    b = graph([(0, 1), (0, 2), (0, 3), (1, 4), (2, 5), (5, 6)])
    return [[graph(nodes=[0]), graph(nodes=["q"])],
            [graph([(0, 1)]), graph([("a", "b")])],
            [path(2), path(3)], [path(6), path(6)], [star(6), star(6)],
            [binary, binary], [path(7), star(7)], [a, b]]


def invalid_pairs():
    tree = graph([(0, 1), (1, 2)])
    cycle = graph([(0, 1), (1, 2), (2, 0)])
    return [[cycle, tree], [tree, cycle],
            [graph([(0, 1)], directed=True), graph([(0, 1)], directed=True)],
            [graph([(0, 1)], multigraph=True), graph([(0, 1)], multigraph=True)]]


def center_guards():
    path = lambda n, **kw: graph([(v, v + 1) for v in range(n - 1)],
                                list(range(n)), **kw)
    return [graph(nodes=["only"]), path(5),
            graph([(0, 1), (1, 2), (2, 3)], [3, 2, 1, 0]),
            graph([(0, v) for v in range(1, 7)]),
            graph([(v, (v + 1) % 5) for v in range(5)]),
            graph([(u, v) for u in range(4) for v in range(u + 1, 4)]
                  + [(3, 4), (4, 5), (5, 6)]),
            graph([(0, 1, 5), (1, 2, 1), (2, 3, 1)], weight="w"),
            graph([(0, 1, 5), (1, 2, 1), (2, 3, 1)], weight="callable"),
            path(4, eccentricities=[[2, 1], [1, 1], [0, 9], [3, 9]]),
            path(7, usebounds=True),
            graph([(0, 1), (1, 2), (2, 0)], directed=True),
            graph([(0, 1), (2, 3)]),
            graph([(0, 1), (1, 2)], directed=True),
            graph([(0, 1), (0, 1), (1, 2)], multigraph=True),
            graph([(0, 0)], nodes=[0])]


def fixtures(case, size, seed):
    if case == "schema_pairs":
        return schema_pairs(size, seed)
    if case == "edge_pairs":
        return edge_pairs()
    if case == "invalid_pairs":
        return invalid_pairs()
    if case == "center_guards":
        return center_guards()
    raise ValueError(f"unknown case {case!r}")


def observable(case, results, unchanged):
    value = {"case": case, "count": len(results), "sha256": digest(results),
             "results": results, "input_unchanged": unchanged}
    return value



def adjacency(spec):
    result = {node: {} for node in spec["nodes"]}
    weighted = bool(spec.get("weight"))
    for edge in spec["edges"]:
        u, v = edge[:2]
        distance = edge[2] if weighted and len(edge) == 3 else 1
        result[u][v] = distance
        if not spec["directed"]:
            result[v][u] = distance
    return result


def bfs(adj, root):
    distances, parent = {root: 0}, {root: None}
    todo = deque([root])
    while todo:
        node = todo.popleft()
        for neighbor in adj[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                parent[neighbor] = node
                todo.append(neighbor)
    return distances, parent


def center_oracle(spec):
    if "eccentricities" in spec:
        eccentricities = spec["eccentricities"]
    else:
        adj = adjacency(spec)
        eccentricities = []
        for root in spec["nodes"]:
            distances = {root: 0}
            queue = [(0, 0, root)]
            serial = 0
            while queue:
                distance, _, node = heapq.heappop(queue)
                if distance != distances[node]:
                    continue
                for neighbor, weight in adj[node].items():
                    candidate = distance + weight
                    if candidate < distances.get(neighbor, float("inf")):
                        distances[neighbor] = candidate
                        serial += 1
                        heapq.heappush(queue, (candidate, serial, neighbor))
            if len(distances) != len(adj):
                return {"error": "NetworkXError"}
            eccentricities.append([root, max(distances.values())])
    radius = min(value for _, value in eccentricities)
    return {"center": [node for node, value in eccentricities if value == radius]}


def rooted_signature(adj, root):
    parent = {root: None}
    order = [root]
    for node in order:
        for neighbor in adj[node]:
            if neighbor != parent[node]:
                parent[neighbor] = node
                order.append(neighbor)
    signatures = {}
    for node in reversed(order):
        children = [signatures[v] for v in adj[node] if parent.get(v) == node]
        signatures[node] = "(" + "".join(sorted(children)) + ")"
    return signatures[root]


def canonical_tree(spec):
    adj = adjacency(spec)
    distances, _ = bfs(adj, spec["nodes"][0])
    endpoint = max(distances, key=distances.get)
    distances, parent = bfs(adj, endpoint)
    farthest = max(distances, key=distances.get)
    path = []
    while farthest is not None:
        path.append(farthest)
        farthest = parent[farthest]
    roots = [path[(len(path) - 1) // 2], path[len(path) // 2]]
    return min(rooted_signature(adj, root) for root in set(roots))


def is_tree(spec):
    if len(spec["edges"]) != len(spec["nodes"]) - 1:
        return False
    return len(bfs(adjacency(spec), spec["nodes"][0])[0]) == len(spec["nodes"])


def expected(case: str, size: int, seed: int) -> dict:
    results = []
    values = fixtures(case, size, seed)
    if case == "center_guards":
        results = [center_oracle(spec) for spec in values]
    else:
        for first, second in values:
            if first["directed"] or first["multigraph"]:
                results.append({"error": "NetworkXNotImplemented"})
            elif not is_tree(first) or not is_tree(second):
                results.append({"error": "NetworkXError"})
            else:
                equal = (len(first["nodes"]) == len(second["nodes"])
                         and canonical_tree(first) == canonical_tree(second))
                results.append({"isomorphic": equal,
                                "mapping_count": len(first["nodes"]) if equal else 0,
                                "mapping_valid": True})
    return observable(case, results, True)
