"""Independent stdlib oracle from authored document specifications.

Does not import the workload or markdown_it, call a parser, read candidate files,
or use public-reference outputs. Semantic HTML and maps are hand specifications.
The changelog oracle directly emits HTML/env from release records, without parsing.
"""
from __future__ import annotations

import hashlib
import html
import json
import random


def _sha(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _ref(href: str, start: int, stop: int, title: str = "") -> dict:
    return {"href": href, "title": title, "map": [start, stop]}


def _inline(content: str, start: int, stop: int) -> dict:
    return {"content": content, "map": [start, stop]}


def _semantics(case: str) -> tuple[str, dict, list, list]:
    if case == "empty":
        return "", {}, [], []
    if case == "duplicate":
        env = {"references": {"A": _ref("/first", 2, 3, "First"), "B": _ref("/bee", 4, 5)}, "duplicate_refs": [{**_ref("/later", 3, 4, "Later"), "label": "A"}]}
        return '<p><a href="/first" title="First">a</a> <a href="/bee">B</a></p>\n', env, [_inline("[a] [B]", 0, 1)], []
    if case == "multiline-title":
        return '<p><a href="/target" title="First line\n  second line">ref</a></p>\n', {"references": {"REF": _ref("/target", 2, 5, "First line\n  second line")}}, [_inline("[ref]", 0, 1)], []
    if case == "multiline-label":
        return '<p><a href="/target">two words</a></p>\n', {"references": {"TWO WORDS": _ref("/target", 2, 4)}}, [_inline("[two words]", 0, 1)], []
    if case == "rollback-title":
        return '<p><a href="/target">ref</a></p>\n<p>&quot;Title&quot; extra</p>\n', {"references": {"REF": _ref("/target", 2, 3)}}, [_inline("[ref]", 0, 1), _inline('"Title" extra', 3, 4)], []
    if case == "blank-title":
        return '<p>[ref]</p>\n<p>[ref]: /target &quot;First</p>\n<p>second&quot;</p>\n', {}, [_inline("[ref]", 0, 1), _inline('[ref]: /target "First', 2, 3), _inline('second"', 4, 5)], []
    if case == "heading-terminator":
        return '<h1>Heading</h1>\n<p><a href="/target">ref</a></p>\n', {"references": {"REF": _ref("/target", 0, 1)}}, [_inline("Heading", 1, 2), _inline("[ref]", 3, 4)], []
    if case == "paragraph-before":
        return '<p>paragraph\n[ref]: /target</p>\n<p>[ref]</p>\n', {}, [_inline("paragraph\n[ref]: /target", 0, 2), _inline("[ref]", 3, 4)], []
    if case == "angle-destination":
        return '<p><a href="https://example.com/a%20b" title="A &amp; B">escaped</a> <a href="/ligature">ﬀﬁﬂ</a></p>\n', {"references": {"ESCAPED": _ref("https://example.com/a%20b", 2, 3, "A & B"), "FFFIFL": _ref("/ligature", 3, 4)}}, [_inline("[escaped] [ﬀﬁﬂ]", 0, 1)], []
    if case == "no-end-newline":
        return '<p><a href="/target" title="Title">ref</a></p>\n', {"references": {"REF": _ref("/target", 2, 3, "Title")}}, [_inline("[ref]", 0, 1)], []
    if case == "container":
        return '<blockquote>\n<p><a href="/quote" title="Quoted">ref</a></p>\n</blockquote>\n<ul>\n<li>\n<p><a href="/item">item</a></p>\n</li>\n</ul>\n', {"references": {"REF": _ref("/quote", 0, 1, "Quoted"), "ITEM": _ref("/item", 4, 5)}}, [_inline("[ref]", 2, 3), _inline("[item]", 6, 7)], []
    if case == "indented-code":
        return '<pre><code>[ref]: /target\n</code></pre>\n<p>[ref]</p>\n', {}, [_inline("[ref]", 2, 3)], []
    if case == "inline-definitions":
        env = {"references": {"A": _ref("/one", 0, 1, "One")}, "duplicate_refs": [{**_ref("/two", 1, 2), "label": "A"}]}
        defs = [{"map": [0, 1], "meta": {"id": "A", "title": "One", "url": "/one", "label": "a"}}, {"map": [1, 2], "meta": {"id": "A", "title": "", "url": "/two", "label": "a"}}]
        return '< />\n< />\n<p><a href="/one" title="One">a</a></p>\n', env, [_inline("[a]", 3, 4)], defs
    if case == "existing-env":
        env = {"references": {"A": _ref("/seed", 20, 21, "Seed"), "B": _ref("/bee", 2, 3)}, "duplicate_refs": [{**_ref("/later", 3, 4), "label": "A"}]}
        return '<p><a href="/seed" title="Seed">a</a> <a href="/bee">b</a></p>\n', env, [_inline("[a] [b]", 0, 1)], []
    if case == "title-escaped-newline":
        title = "\nhello\n\\\nworld\n"
        return '<p><a href="/target" title="\nhello\n\\\nworld\n">ref</a></p>\n', {"references": {"REF": _ref("/target", 0, 5, title)}}, [_inline("[ref]", 6, 7)], []
    raise ValueError(case)


def _changelog(size: int, seed: int) -> dict:
    if not 0 <= size <= 600:
        raise ValueError("size outside frozen declared range")
    rng = random.Random(seed)
    actions = ("Fix", "Add", "Remove", "Improve", "Deprecate", "Document")
    subjects = ("parser", "cache", "CLI flag", "schema loader", "retry policy", "S3 backend", "type hints", "logging")
    raw_docs, rendered_docs, reference_envs = [], [], []
    for project in range(6):
        versions = ["%d.%d.%d" % (1 + n // 100, (n // 10) % 10, n % 10) for n in reversed(range(size))]
        sections = []
        for version in versions:
            date = "2026-%02d-%02d" % (rng.randint(1, 12), rng.randint(1, 28))
            bullets = []
            for _ in range(rng.randint(3, 6)):
                bullets.append("%s %s (#%d)" % (rng.choice(actions), rng.choice(subjects), rng.randint(1, 9999)))
            sections.append((version, date, bullets))
        urls = {v: f"https://github.com/org/proj-{project}/compare/v{versions[i + 1] if i + 1 < size else '0.0.1'}...v{v}" for i, v in enumerate(versions)}
        pieces = [f"# Changelog of proj-{project}\n", "All notable changes to this project are documented in this file.\n"]
        output = [f"<h1>Changelog of proj-{project}</h1>\n", "<p>All notable changes to this project are documented in this file.</p>\n"]
        for version, date, bullets in sections:
            pieces.extend([f"## [{version}] - {date}\n", "\n".join("- " + b for b in bullets) + "\n"])
            output.extend([f'<h2><a href="{urls[version]}">{version}</a> - {date}</h2>\n', "<ul>\n", *("<li>" + html.escape(b, quote=False) + "</li>\n" for b in bullets), "</ul>\n"])
        pieces.append("\n".join(f"[{v}]: {urls[v]}" for v in versions) + "\n")
        document = "\n".join(pieces)
        # The fixture places one blank line after each header and bullet group.
        footer_start = 4 + sum(3 + len(bullets) for _, _, bullets in sections)
        env = {"references": {v.upper(): _ref(urls[v], footer_start + i, footer_start + i + 1) for i, v in enumerate(versions)}} if size else {}
        raw_docs.append(document)
        rendered_docs.append("".join(output))
        reference_envs.append(env)
    return {"pages": 6, "input_sha256": _sha(raw_docs), "html_sha256": _sha(rendered_docs), "html_chars": sum(map(len, rendered_docs)), "references_sha256": _sha(reference_envs), "reference_count": 6 * size, "input_unchanged": True}


def expected(case: str, size: int, seed: int) -> dict:
    if case == "changelog":
        return _changelog(size, seed)
    text, env, inlines, definitions = _semantics(case)
    return {"html": text, "html_sha256": hashlib.sha256(text.encode()).hexdigest(), "render_env": env, "parse_env": env, "inlines": inlines, "definitions": definitions, "input_unchanged": True}
