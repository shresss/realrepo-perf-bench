"""Real NodeSelector tag criteria on compiled Manifest/Graph; no direct hotspot calls."""
import hashlib
import json
from pathlib import Path
import random
import sys
import threading


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def fixture(case, size, seed):
    if case == "lineage":
        if not 0 <= size <= 1800:
            raise ValueError("outside predeclared model-size ladder")
        rng = random.Random(seed)
        nodes = [(f"source.warehouse.raw.raw_{i}", {"kind": "source", "team": i}) for i in range(6)]
        layers = [[] for _ in range(4)]
        model_names = []
        for i in range(size):
            layer = min(3, 4 * i // size)
            name = f"model.warehouse.layer{layer}_{i:05d}"
            layers[layer].append(name)
            model_names.append(name)
            nodes.append((name, {"kind": "model", "team": i % 6, "layer": layer}))
        edges = []
        for layer, names in enumerate(layers):
            previous = [name for name, attrs in nodes if attrs["kind"] == "source"] if layer == 0 else layers[layer - 1]
            for name in names:
                for parent in rng.sample(previous, min(3, len(previous))):
                    edges.append((parent, name, None))
        outgoing = {}
        for parent, child, kind in edges:
            outgoing.setdefault(parent, []).append(child)
        for i, name in enumerate(model_names):
            test = f"test.warehouse.unique_{i:05d}"
            nodes.append((test, {"kind": "test", "team": i % 6}))
            edges.append((name, test, None))
            for child in outgoing.get(name, []):
                if child.startswith("model.") and rng.random() < 0.3:
                    edges.append((test, child, "parent_test"))
        queries = []
        for team in range(6):
            for op, layer in (("children", 0), ("parents", 3), ("at", 1)):
                selected = [name for name, attrs in nodes if attrs["kind"] == "model"
                            and attrs["team"] == team and attrs["layer"] == layer]
                queries.append((f"team{team}-{op}", op, selected, None))
        return nodes, edges, queries, []
    names = ["a", "b", "c", "d", "t"]
    nodes = [(name, {}) for name in names]
    edges = [("a", "b", None), ("a", "c", None), ("b", "d", None), ("c", "d", "other")]
    queries = [("children", "children", ["a"], None), ("parents", "parents", ["d"], None),
               ("at", "at", ["b"], None)]
    mutations = []
    if case == "empty":
        nodes, edges = [], []
        queries = [("empty-children", "children", [], None), ("empty-parents", "parents", [], None),
                   ("empty-at", "at", [], None)]
    elif case == "singleton":
        nodes, edges = [("a", {})], []
        queries = [("singleton-children", "children", ["a"], None),
                   ("singleton-parents", "parents", ["a"], 1), ("singleton-at", "at", ["a"], None)]
    elif case == "chain":
        edges = [("a", "b", None), ("b", "c", None), ("c", "d", None)]
    elif case == "diamond":
        pass
    elif case == "overlap":
        queries = [("overlap-children", "children", ["a", "b"], None),
                   ("overlap-parents", "parents", ["b", "d"], None), ("overlap-at", "at", ["b", "c"], None)]
    elif case.startswith("depth-"):
        depth = int(case.removeprefix("depth-"))
        queries = [(f"depth{depth}-children", "children", ["a"], depth),
                   (f"depth{depth}-parents", "parents", ["d"], depth)]
    elif case == "parent-test":
        edges = [("a", "t", None), ("t", "b", "parent_test"), ("b", "c", None)]
        queries = [("parent-test-children", "children", ["a"], None),
                   ("parent-test-parents", "parents", ["b"], None), ("parent-test-at", "at", ["a"], None)]
    elif case == "selected-test":
        edges = [("a", "t", None), ("t", "b", "parent_test"), ("b", "c", None)]
        queries = [("test-children", "children", ["t"], None), ("test-parents", "parents", ["t"], None),
                   ("test-at", "at", ["t"], None)]
    elif case == "mutation":
        edges = [("a", "b", None), ("b", "c", None)]
        queries = [("before", "children", ["a"], None), ("after", "children", ["a"], None),
                   ("after-parents", "parents", ["c"], None)]
        mutations = [(1, "remove", "a", "b", None), (1, "add", "a", "d", None)]
    elif case == "random-small":
        rng = random.Random(seed)
        nodes = [(f"m{i}", {}) for i in range(18)] + [(f"t{i}", {}) for i in range(18)]
        edges = [(f"m{i}", f"t{i}", None) for i in range(18)]
        for i in range(1, 18):
            for parent in rng.sample(range(i), min(2, i)):
                edges.append((f"m{parent}", f"m{i}", None))
                edges.append((f"t{parent}", f"m{i}", "parent_test"))
        queries = [("random-children", "children", ["m0", "m1"], 3),
                   ("random-parents", "parents", ["m17", "m12"], None),
                   ("random-at", "at", ["m8", "t2"], None)]
    else:
        raise ValueError(case)
    return nodes, edges, queries, mutations


def package():
    roots = [Path(item).resolve() for item in sys.path if item]
    root = next(item for item in roots if (item / "core/dbt/graph/graph.py").is_file())
    sys.path.insert(0, str(root / "core"))
    import networkx as nx
    import dbt.graph.graph as module
    assert Path(module.__file__).resolve().is_relative_to(root / "core")
    return nx, module.Graph


def compiled_manifest(nodes, edges, queries):
    from dbt.contracts.graph.manifest import Manifest
    from dbt.contracts.graph.nodes import ModelNode, SingularTestNode, SourceDefinition, NodeConfig, DependsOn
    from dbt.contracts.files import FileHash
    from dbt.artifacts.resources import TestConfig
    from dbt.node_types import NodeType
    tags = {name: [] for name, attrs in nodes}
    incoming = {}
    for parent, child, kind in edges:
        if kind != "parent_test":
            incoming.setdefault(child, []).append(parent)
    for index, (_, _, selected, _) in enumerate(queries):
        for name in selected:
            tags[name].append(f"query{index}")
    # Coordinator09:44: real compiled Manifest with a process-local fixture lock.
    # The unchanged selection API never touches this lock; no worker may spawn.
    manifest = Manifest(_lock=threading.Lock())
    for name, attrs in nodes:
        short = name.rsplit(".",1)[-1]
        parents = list(incoming.get(name, ()))
        common = dict(name=short, unique_id=name, package_name="warehouse", path=short+".sql",
            original_file_path="models/"+short+".sql", fqn=["warehouse", short],
            database="warehouse", schema="analytics", tags=tags[name])
        if attrs.get("kind") == "source":
            common.update(path="schema.yml",original_file_path="models/schema.yml",
                          fqn=["warehouse","raw",short])
            manifest.sources[name] = SourceDefinition(**common, source_name="raw", identifier=short,
                loader="warehouse", resource_type=NodeType.Source, source_description="")
        else:
            is_test = attrs.get("kind") == "test" or name == "t" or name.startswith("t")
            klass = SingularTestNode if is_test else ModelNode
            manifest.nodes[name] = klass(**common, alias=short, raw_code="select 1", language="sql",
                resource_type=NodeType.Test if is_test else NodeType.Model,
                config=TestConfig() if is_test else NodeConfig(),
                depends_on=DependsOn(nodes=parents), checksum=FileHash.from_contents("select 1"))
    return manifest


def public_selection(selector, spec):
    # The real caller resolves a tag, expands modifiers, and combines direct and
    # related membership. Graph selection internals are not called by this aid.
    return selector.get_nodes_from_criteria(spec)


def run(case, size, seed):
    nx, Graph = package()
    from dbt.graph.selector import NodeSelector
    from dbt.graph.selector_methods import MethodName
    from dbt.graph.selector_spec import SelectionCriteria, IndirectSelection
    assert Path(sys.modules["dbt.graph.selector"].__file__).resolve().parent == Path(sys.modules["dbt.graph.graph"].__file__).resolve().parent
    nodes, edges, queries, mutations = fixture(case, size, seed)
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    for parent, child, kind in edges:
        graph.add_edge(parent, child, **({} if kind is None else {"edge_type": kind}))
    manifest = compiled_manifest(nodes, edges, queries)
    manifest_before = sha(manifest.to_dict())
    values = []
    unchanged = True
    for index, (label, op, selected, depth) in enumerate(queries):
        for at, action, parent, child, kind in mutations:
            if at == index:
                if action == "remove":
                    graph.remove_edge(parent, child)
                else:
                    graph.add_edge(parent, child, **({} if kind is None else {"edge_type": kind}))
        before = sha([sorted(graph.nodes(data=True)), sorted(graph.edges(data=True))])
        selected_argument = set(selected)
        # A fresh production selector observes the caller's current graph after
        # intervening mutations; constructor eligibility/subgraph logic runs too.
        selector = NodeSelector(Graph(graph), manifest)
        spec = SelectionCriteria(raw=label, method=MethodName.Tag, method_arguments=[],
            value=f"query{index}", childrens_parents=op == "at", parents=op == "parents",
            parents_depth=depth, children=op == "children", children_depth=depth,
            indirect_selection=IndirectSelection.Empty)
        criteria_before = sha(vars(spec))
        answer, indirect = public_selection(selector, spec)
        unchanged = (unchanged and selected_argument == set(selected)
                     and criteria_before == sha(vars(spec))
                     and not indirect
                     and before == sha([sorted(graph.nodes(data=True)), sorted(graph.edges(data=True))]))
        values.append({"label": label, "nodes": sorted(answer)})
    value = {"queries": len(values), "node_count": graph.number_of_nodes(),
             "edge_count": graph.number_of_edges(), "output_sha256": sha(values),
             "output_counts": [len(item["nodes"]) for item in values],
             "input_unchanged": unchanged and manifest_before == sha(manifest.to_dict())}
    if case != "lineage" or size <= 20:
        value["outputs"] = values
    return value


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path.cwd()))
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True, allow_nan=False))
