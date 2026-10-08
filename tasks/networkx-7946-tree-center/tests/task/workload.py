"""Real public API workload: unrooted tree isomorphism and center regressions."""
import json

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



def build(nx, spec):
    constructor = nx.MultiGraph if spec["multigraph"] else nx.Graph
    if spec["directed"]:
        constructor = nx.DiGraph
    value = constructor()
    value.add_nodes_from(spec["nodes"])
    for edge in spec["edges"]:
        if len(edge) == 3:
            value.add_edge(edge[0], edge[1], w=edge[2])
        else:
            value.add_edge(*edge)
    return value


def snapshot(value):
    # Include node order, edge data and graph kind, so the oracle catches mutation.
    return digest([list(value.nodes(data=True)), list(value.edges(data=True)),
                   value.is_directed(), value.is_multigraph()])


def mapping_valid(first, second, mapping):
    if not mapping:
        return True
    if len(mapping) != len(first["nodes"]) or len(mapping) != len(second["nodes"]):
        return False
    translated = dict(mapping)
    if (len(translated) != len(mapping) or set(translated) != set(first["nodes"])
            or set(translated.values()) != set(second["nodes"])):
        return False
    edges = {frozenset(edge[:2]) for edge in second["edges"]}
    mapped = {frozenset((translated[edge[0]], translated[edge[1]]))
              for edge in first["edges"]}
    return mapped == edges


def run(case: str, size: int, seed: int) -> dict:
    import networkx as nx

    values = fixtures(case, size, seed)
    results, unchanged = [], True
    if case == "center_guards":
        for spec in values:
            value = build(nx, spec)
            before = snapshot(value)
            options = {}
            if spec.get("weight") == "callable":
                options["weight"] = lambda u, v, data: data.get("w", 1)
            elif spec.get("weight"):
                options["weight"] = spec["weight"]
            if "eccentricities" in spec:
                options["e"] = dict(spec["eccentricities"])
            if "usebounds" in spec:
                options["usebounds"] = spec["usebounds"]
            try:
                results.append({"center": list(nx.center(value, **options))})
            except Exception as error:
                results.append({"error": type(error).__name__})
            unchanged &= before == snapshot(value)
    else:
        for first, second in values:
            left, right = build(nx, first), build(nx, second)
            before = [snapshot(left), snapshot(right)]
            try:
                mapping = nx.isomorphism.tree_isomorphism(left, right)
                results.append({"isomorphic": bool(mapping), "mapping_count": len(mapping),
                                "mapping_valid": mapping_valid(first, second, mapping)})
            except Exception as error:
                results.append({"error": type(error).__name__})
            unchanged &= before == [snapshot(left), snapshot(right)]
    return observable(case, results, bool(unchanged))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", default="schema_pairs")
    parser.add_argument("--size", type=int, default=40)
    parser.add_argument("--seed", type=int, default=0)
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.case, arguments.size, arguments.seed),
                     sort_keys=True, allow_nan=False))
