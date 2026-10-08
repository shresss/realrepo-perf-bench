"""Public profiling aid: render generated documentation pages with Python-Markdown.

run(case, size, seed) builds deterministic Markdown pages from `seed` and renders every page with the
REAL public API, one markdown.Markdown instance per run: md.reset().convert(page). No timers live here.

Cases (sizes are entries per page; generated cases render PAGES pages):
  tag_index     docs-site tag index pages: a heading, an intro paragraph and ONE paragraph listing `size`
                inline links "[tag](/tags/tag/)" separated by " · ".
  symbol_index  API reference symbol index pages: a heading, an intro paragraph and ONE paragraph listing
                `size` entries "`module.symbol()` *kind*" separated by "; ".
  adjacent      one paragraph of `size` links written back to back with no separator, long URLs.
  mixed         one paragraph of `size` tokens mixing links, images, code spans, emphasis, strong,
                autolinks, entities and plain words.
  edge_core     a fixed list of hand-written inputs, default configuration (size, seed ignored).
  edge_ext      the same inputs with the built-in tables, attr_list, footnotes, abbr, def_list, smarty
                and fenced_code extensions enabled (size, seed ignored).

Observables: page count, total HTML characters, number of "<a " anchors, number of "<code>" spans, sha256
of the pages' HTML joined by NUL, and the raw HTML when the total is small.
"""
import argparse
import hashlib
import json
import random

PAGES = 10
RAW_LIMIT = 20_000
SYL = ("ka", "lo", "mi", "ne", "ra", "to", "su", "vi", "de", "po", "xa", "qu")
KINDS = ("function", "class", "method", "attribute", "module", "exception")
EXTENSIONS = tuple("markdown.extensions." + name for name in
                   ("tables", "attr_list", "footnotes", "abbr", "def_list", "smarty", "fenced_code"))

EDGE_INPUTS = (
    "",
    "[a](b)",
    "[a](b)[c](d)",
    "[a](b) [c](d) [e](f)",
    "*[a](b)* **[c](d)**",
    "[![img](x.png)](y)",
    "[foo [bar](/u)](/v)",
    "[[a](b)](c)",
    "`[a](b)` [c](d)",
    "<https://x.org> [a](b) <https://y.org>",
    "[a][r1] [b][r2] [c](d)\n\n[r1]: /one\n[r2]: /two",
    "[a](b \"title\") [c](<d e>)",
    "![i](a) ![j](b) [k](c)",
    "[a](b)*x*[c](d)*y*",
    "\\[a](b) [c](d)",
    "[a](b\\)c) [d](e)",
    "_[a](b)_ __[c](d)__ ***[e](f)***",
    "[a](b)&amp;[c](d)&copy;",
    "<span>[a](b)</span> [c](d)",
    "[a]  (b) [c](d)",
    "[x](y)" * 50,
    "[*a*](b) [`c`](d) [**e**](f)",
    "[a](b)\n[c](d)\n",
    "text [a](b) more *em [c](d) em* end",
    "[a](b)[c](d)[e](f)[g](h)",
    "<b>[a](b)</b>",
    "[a](http://x.org/?q=[1]) [b](c)",
    "**bold [a](b) and [c](d)**",
    "[a](b) `code` [c](d) `code2` [e](f)",
    "[first link with long text](https://example.org/a/very/long/path/to/a/page)[b](c)[d](e)",
    "`a` `b` `c` *d* *e* **f** **g** _h_ _i_",
    "`x``y` ``a ` b`` `c`",
    "*a* *b* [c](d) *e* [f](g) *h*",
    "a  \nb [c](d)  \ne",
    "[a](b) <!-- comment [x](y) --> [c](d)",
    "<a@b.org> [c](d) <mailto:e@f.org>",
    "[a](b \"t1\")[c](d 't2')[e](f (t3))",
    "[unclosed](a [b](c) [d](e",
    "[a]\n\n[a]: /x\n\n[a] [a][] [A]",
    "--- \"quotes\" 'single' ... -- [a](b) <<x>>",
    "*Term* [a](b)\n:   Definition with [c](d) and `e`",
    "| h1 | h2 |\n|----|----|\n| [a](b) | `c` [d](e) |",
    "Text with HTML abbr and a footnote[^1] [a](b).\n\n*[HTML]: Hyper Text\n[^1]: Note [c](d).",
    "[a](b){: .cls } and [c](d){: #id }",
    "```\n[not](a link) `x`\n```\n\n[a](b)",
)


def _rng_word(rng):
    return "".join(rng.choices(SYL, k=rng.randint(2, 4)))


def make_pages(case, size, seed):
    """Return (list of Markdown pages, extensions tuple)."""
    if type(size) is not int or not 0 <= size <= 20_000:
        raise ValueError("size must be an integer in 0..20000")
    if type(seed) is not int or not 0 <= seed < 1_000_000:
        raise ValueError("seed must be an integer in 0..999999")
    rng = random.Random(seed)
    pages = []
    if case == "tag_index":
        for p in range(PAGES):
            tags = [f"{_rng_word(rng)}-{_rng_word(rng)}" for _ in range(size)]
            links = " · ".join(f"[{t}](/tags/{t}/)" for t in tags)
            pages.append(f"# Tag index {p}\n\nThis page lists *every* tag used on the site, generated nightly. "
                         f"See [the guide](/guide/).\n\n{links}\n")
        return pages, ()
    if case == "symbol_index":
        for p in range(PAGES):
            entries = []
            for _ in range(size):
                symbol = f"{_rng_word(rng)}.{_rng_word(rng)}_{_rng_word(rng)}()"
                entries.append(f"`{symbol}` *{rng.choice(KINDS)}*")
            pages.append(f"# API index {p}\n\nEvery public symbol, generated from the docstrings. "
                         f"See [the reference guide](/reference/).\n\n{'; '.join(entries)}\n")
        return pages, ()
    if case == "adjacent":
        links = []
        for i in range(size):
            w = _rng_word(rng)
            links.append(f"[{w} {i}](https://example.org/{w}/{'segment/' * rng.randint(1, 4)}{i})")
        return ["".join(links) + "\n"], ()
    if case == "mixed":
        tokens = []
        for i in range(size):
            w = _rng_word(rng)
            kind = rng.randrange(9)
            if kind == 0:
                tokens.append(f"[{w}](/p/{w}/{i})")
            elif kind == 1:
                tokens.append(f"![{w}](/img/{w}.png)")
            elif kind == 2:
                tokens.append(f"`{w}[{i}]({w})`")
            elif kind == 3:
                tokens.append(f"*{w}*")
            elif kind == 4:
                tokens.append(f"**{w}**")
            elif kind == 5:
                tokens.append(f"<https://{w}.example.org/{i}>")
            elif kind == 6:
                tokens.append("&copy;")
            elif kind == 7:
                tokens.append(f"[{w}](/a/{i})[{w}](/b/{i})")
            else:
                tokens.append(w)
        return ["Intro line.\n\n" + " ".join(tokens) + "\n"], ()
    if case == "edge_core":
        return list(EDGE_INPUTS), ()
    if case == "edge_ext":
        return list(EDGE_INPUTS), EXTENSIONS
    raise ValueError(f"unsupported case {case!r}")


def summarize(htmls):
    h = hashlib.sha256()
    for html in htmls:
        h.update(html.encode("utf-8"))
        h.update(b"\0")
    total = sum(len(x) for x in htmls)
    return {
        "pages": len(htmls),
        "chars": total,
        "anchors": sum(x.count("<a ") for x in htmls),
        "code_spans": sum(x.count("<code>") for x in htmls),
        "digest": h.hexdigest(),
        "raw": list(htmls) if total <= RAW_LIMIT else None,
    }


def run(case, size, seed):
    pages, extensions = make_pages(case, size, seed)

    import markdown

    md = markdown.Markdown(extensions=list(extensions))
    htmls = [md.reset().convert(page) for page in pages]
    return summarize(htmls)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
