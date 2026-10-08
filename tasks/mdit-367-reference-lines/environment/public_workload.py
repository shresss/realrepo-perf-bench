"""Real MarkdownIt render/parse workload; fixture construction is deterministic."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random


SEMANTICS = {
    "empty": ("", {}, False),
    "duplicate": ('[a] [B]\n\n[a]: /first "First"\n[A]: /later "Later"\n[b]: /bee\n', {}, False),
    "multiline-title": ('[ref]\n\n[ref]: /target\n  "First line\n  second line"\n', {}, False),
    "heading-terminator": ('[ref]: /target\n# Heading\n\n[ref]\n', {}, False),
    "container": ('> [ref]: /quote "Quoted"\n>\n> [ref]\n\n- [item]: /item\n\n  [item]\n', {}, False),
    "inline-definitions": ('[a]: /one "One"\n[a]: /two\n\n[a]\n', {}, True),
}


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def changelogs(size: int, seed: int) -> list[str]:
    if not 0 <= size <= 600:
        raise ValueError("changelog size is releases per project, in [0, 600]")
    rng = random.Random(seed)
    verbs = ["Fix", "Add", "Remove", "Improve", "Deprecate", "Document"]
    nouns = ["parser", "cache", "CLI flag", "schema loader", "retry policy", "S3 backend", "type hints", "logging"]
    pages = []
    for project in range(6):
        versions = [f"{1 + i // 100}.{(i // 10) % 10}.{i % 10}" for i in range(size)][::-1]
        parts = [f"# Changelog of proj-{project}\n", "All notable changes to this project are documented in this file.\n"]
        for version in versions:
            parts.append(f"## [{version}] - 2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}\n")
            parts.append("\n".join(f"- {rng.choice(verbs)} {rng.choice(nouns)} (#{rng.randint(1, 9999)})" for _ in range(rng.randint(3, 6))) + "\n")
        definitions = []
        for index, version in enumerate(versions):
            previous = versions[index + 1] if index + 1 < size else "0.0.1"
            definitions.append(f"[{version}]: https://github.com/org/proj-{project}/compare/v{previous}...v{version}")
        parts.append("\n".join(definitions) + "\n")
        pages.append("\n".join(parts))
    return pages


def run(case: str, size: int, seed: int) -> dict:
    from markdown_it import MarkdownIt

    if case == "changelog":
        pages = changelogs(size, seed)
        before = digest(pages)
        outputs, environments = [], []
        md = MarkdownIt("commonmark")
        for page in pages:
            env = {}
            outputs.append(md.render(page, env))
            environments.append(env)
        return {"pages": 6, "input_sha256": before, "html_sha256": digest(outputs), "html_chars": sum(map(len, outputs)), "references_sha256": digest(environments), "reference_count": sum(len(e.get("references", {})) for e in environments), "input_unchanged": before == digest(pages)}
    source, initial, definitions = SEMANTICS[case]
    initial = copy.deepcopy(initial)
    before = digest([source, initial])
    md = MarkdownIt("commonmark", {"inline_definitions": definitions})
    render_env, parse_env = copy.deepcopy(initial), copy.deepcopy(initial)
    html = md.render(source, render_env)
    tokens = md.parse(source, parse_env)
    inlines = [{"content": t.content, "map": t.map} for t in tokens if t.type == "inline"]
    defined = [{"map": t.map, "meta": t.meta} for t in tokens if t.type == "definition"]
    return {"html": html, "html_sha256": hashlib.sha256(html.encode()).hexdigest(), "render_env": render_env, "parse_env": parse_env, "inlines": inlines, "definitions": defined, "input_unchanged": before == digest([source, initial])}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=("changelog", *SEMANTICS))
    parser.add_argument("--size", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True, ensure_ascii=False, allow_nan=False))
