"""Independent stdlib-only oracle for the markdown-1621 documentation-rendering workload.

Never imports markdown or workload.py. For the generated cases (tag_index, symbol_index, adjacent,
mixed) it rebuilds the same pages from the same seed and constructs the HTML every page must render
to directly from the Markdown rules those pages exercise:

  * "# title" -> <h1>title</h1>; each paragraph -> <p>...</p>; blocks joined by a newline;
  * [text](url) -> <a href="url">text</a>; ![alt](src) -> <img alt="alt" src="src" />;
  * `code` -> <code>code</code> (contents literal, link syntax inside is not a link);
  * *w* -> <em>w</em>; **w** -> <strong>w</strong>; <https://h/p> -> <a href="https://h/p">https://h/p</a>;
  * named entities (&copy;) and the middle dot (U+00B7) pass through unchanged.

For edge_core / edge_ext (hand-written inputs: nested brackets, escapes, reference links, emphasis
around links, code spans holding link syntax, raw HTML, comments, titles, extension syntax) the expected
HTML is the RECORDED output of the untouched checkout (base 7be0cff, 2026-10-01), which is also the
output of the public reference fix and of an independent alternative fix: behavior must not change.
"""
import hashlib
import random

PAGES = 10
RAW_LIMIT = 20_000
SYL = ("ka", "lo", "mi", "ne", "ra", "to", "su", "vi", "de", "po", "xa", "qu")
KINDS = ("function", "class", "method", "attribute", "module", "exception")

EDGE_CORE_HTML = (
    '',
    '<p><a href="b">a</a></p>',
    '<p><a href="b">a</a><a href="d">c</a></p>',
    '<p><a href="b">a</a> <a href="d">c</a> <a href="f">e</a></p>',
    '<p><em><a href="b">a</a></em> <strong><a href="d">c</a></strong></p>',
    '<p><a href="y"><img alt="img" src="x.png" /></a></p>',
    '<p><a href="/v">foo [bar](/u)</a></p>',
    '<p><a href="c">[a](b)</a></p>',
    '<p><code>[a](b)</code> <a href="d">c</a></p>',
    '<p><a href="https://x.org">https://x.org</a> <a href="b">a</a> <a href="https://y.org">https://y.org</a></p>',
    '<p><a href="/one">a</a> <a href="/two">b</a> <a href="d">c</a></p>',
    '<p><a href="b" title="title">a</a> <a href="d e">c</a></p>',
    '<p><img alt="i" src="a" /> <img alt="j" src="b" /> <a href="c">k</a></p>',
    '<p><a href="b">a</a><em>x</em><a href="d">c</a><em>y</em></p>',
    '<p>[a](b) <a href="d">c</a></p>',
    '<p><a href="b)c">a</a> <a href="e">d</a></p>',
    '<p><em><a href="b">a</a></em> <strong><a href="d">c</a></strong> <strong><em><a href="f">e</a></em></strong></p>',
    '<p><a href="b">a</a>&amp;<a href="d">c</a>&copy;</p>',
    '<p><span><a href="b">a</a></span> <a href="d">c</a></p>',
    '<p>[a]  (b) <a href="d">c</a></p>',
    '<p><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a></p>',
    '<p><a href="b"><em>a</em></a> <a href="d"><code>c</code></a> <a href="f"><strong>e</strong></a></p>',
    '<p><a href="b">a</a>\n<a href="d">c</a></p>',
    '<p>text <a href="b">a</a> more <em>em <a href="d">c</a> em</em> end</p>',
    '<p><a href="b">a</a><a href="d">c</a><a href="f">e</a><a href="h">g</a></p>',
    '<p><b><a href="b">a</a></b></p>',
    '<p><a href="http://x.org/?q=[1]">a</a> <a href="c">b</a></p>',
    '<p><strong>bold <a href="b">a</a> and <a href="d">c</a></strong></p>',
    '<p><a href="b">a</a> <code>code</code> <a href="d">c</a> <code>code2</code> <a href="f">e</a></p>',
    '<p><a href="https://example.org/a/very/long/path/to/a/page">first link with long text</a><a href="c">b</a><a href="e">d</a></p>',
    '<p><code>a</code> <code>b</code> <code>c</code> <em>d</em> <em>e</em> <strong>f</strong> <strong>g</strong> <em>h</em> <em>i</em></p>',
    '<p><code>x``y</code> <code>a ` b</code> <code>c</code></p>',
    '<p><em>a</em> <em>b</em> <a href="d">c</a> <em>e</em> <a href="g">f</a> <em>h</em></p>',
    '<p>a<br />\nb <a href="d">c</a><br />\ne</p>',
    '<p><a href="b">a</a> <!-- comment <a href="y">x</a> --> <a href="d">c</a></p>',
    '<p><a href="&#109;&#97;&#105;&#108;&#116;&#111;&#58;&#97;&#64;&#98;&#46;&#111;&#114;&#103;">&#97;&#64;&#98;&#46;&#111;&#114;&#103;</a> <a href="d">c</a> <a href="&#109;&#97;&#105;&#108;&#116;&#111;&#58;&#101;&#64;&#102;&#46;&#111;&#114;&#103;">&#101;&#64;&#102;&#46;&#111;&#114;&#103;</a></p>',
    '<p><a href="b" title="t1">a</a><a href="d" title="t2">c</a><a href="f (t3)">e</a></p>',
    '<p>[unclosed](a <a href="c">b</a> [d](e</p>',
    '<p><a href="/x">a</a></p>\n<p><a href="/x">a</a><a href="/x"></a></p>',
    '<p>--- "quotes" \'single\' ... -- <a href="b">a</a> &lt;<x>&gt;</p>',
    '<p><em>Term</em> <a href="b">a</a>\n:   Definition with <a href="d">c</a> and <code>e</code></p>',
    '<p>| h1 | h2 |\n|----|----|\n| <a href="b">a</a> | <code>c</code> <a href="e">d</a> |</p>',
    '<p>Text with HTML abbr and a footnote[^1] <a href="b">a</a>.</p>\n<p>*[HTML]: Hyper Text\n[^1]: Note <a href="d">c</a>.</p>',
    '<p><a href="b">a</a>{: .cls } and <a href="d">c</a>{: #id }</p>',
    '<p><code>[not](a link) `x`</code></p>\n<p><a href="b">a</a></p>',
)
EDGE_EXT_HTML = (
    '',
    '<p><a href="b">a</a></p>',
    '<p><a href="b">a</a><a href="d">c</a></p>',
    '<p><a href="b">a</a> <a href="d">c</a> <a href="f">e</a></p>',
    '<p><em><a href="b">a</a></em> <strong><a href="d">c</a></strong></p>',
    '<p><a href="y"><img alt="img" src="x.png" /></a></p>',
    '<p><a href="/v">foo [bar](/u)</a></p>',
    '<p><a href="c">[a](b)</a></p>',
    '<p><code>[a](b)</code> <a href="d">c</a></p>',
    '<p><a href="https://x.org">https://x.org</a> <a href="b">a</a> <a href="https://y.org">https://y.org</a></p>',
    '<p><a href="/one">a</a> <a href="/two">b</a> <a href="d">c</a></p>',
    '<p><a href="b" title="title">a</a> <a href="d e">c</a></p>',
    '<p><img alt="i" src="a" /> <img alt="j" src="b" /> <a href="c">k</a></p>',
    '<p><a href="b">a</a><em>x</em><a href="d">c</a><em>y</em></p>',
    '<p>[a](b) <a href="d">c</a></p>',
    '<p><a href="b)c">a</a> <a href="e">d</a></p>',
    '<p><em><a href="b">a</a></em> <strong><a href="d">c</a></strong> <strong><em><a href="f">e</a></em></strong></p>',
    '<p><a href="b">a</a>&amp;<a href="d">c</a>&copy;</p>',
    '<p><span><a href="b">a</a></span> <a href="d">c</a></p>',
    '<p>[a]  (b) <a href="d">c</a></p>',
    '<p><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a><a href="y">x</a></p>',
    '<p><a href="b"><em>a</em></a> <a href="d"><code>c</code></a> <a href="f"><strong>e</strong></a></p>',
    '<p><a href="b">a</a>\n<a href="d">c</a></p>',
    '<p>text <a href="b">a</a> more <em>em <a href="d">c</a> em</em> end</p>',
    '<p><a href="b">a</a><a href="d">c</a><a href="f">e</a><a href="h">g</a></p>',
    '<p><b><a href="b">a</a></b></p>',
    '<p><a href="http://x.org/?q=[1]">a</a> <a href="c">b</a></p>',
    '<p><strong>bold <a href="b">a</a> and <a href="d">c</a></strong></p>',
    '<p><a href="b">a</a> <code>code</code> <a href="d">c</a> <code>code2</code> <a href="f">e</a></p>',
    '<p><a href="https://example.org/a/very/long/path/to/a/page">first link with long text</a><a href="c">b</a><a href="e">d</a></p>',
    '<p><code>a</code> <code>b</code> <code>c</code> <em>d</em> <em>e</em> <strong>f</strong> <strong>g</strong> <em>h</em> <em>i</em></p>',
    '<p><code>x``y</code> <code>a ` b</code> <code>c</code></p>',
    '<p><em>a</em> <em>b</em> <a href="d">c</a> <em>e</em> <a href="g">f</a> <em>h</em></p>',
    '<p>a<br />\nb <a href="d">c</a><br />\ne</p>',
    '<p><a href="b">a</a> <!-- comment <a href="y">x</a> --> <a href="d">c</a></p>',
    '<p><a href="&#109;&#97;&#105;&#108;&#116;&#111;&#58;&#97;&#64;&#98;&#46;&#111;&#114;&#103;">&#97;&#64;&#98;&#46;&#111;&#114;&#103;</a> <a href="d">c</a> <a href="&#109;&#97;&#105;&#108;&#116;&#111;&#58;&#101;&#64;&#102;&#46;&#111;&#114;&#103;">&#101;&#64;&#102;&#46;&#111;&#114;&#103;</a></p>',
    '<p><a href="b" title="t1">a</a><a href="d" title="t2">c</a><a href="f (t3)">e</a></p>',
    '<p>[unclosed](a <a href="c">b</a> [d](e</p>',
    '<p><a href="/x">a</a></p>\n<p><a href="/x">a</a><a href="/x"></a></p>',
    '<p>&mdash; &ldquo;quotes&rdquo; &lsquo;single&rsquo; &hellip; &ndash; <a href="b">a</a> &lt;<x>&gt;</p>',
    '<dl>\n<dt><em>Term</em> <a href="b">a</a></dt>\n<dd>Definition with <a href="d">c</a> and <code>e</code></dd>\n</dl>',
    '<table>\n<thead>\n<tr>\n<th>h1</th>\n<th>h2</th>\n</tr>\n</thead>\n<tbody>\n<tr>\n<td><a href="b">a</a></td>\n<td><code>c</code> <a href="e">d</a></td>\n</tr>\n</tbody>\n</table>',
    '<p>Text with <abbr title="Hyper Text">HTML</abbr> abbr and a footnote<sup id="fnref:1"><a class="footnote-ref" href="#fn:1">1</a></sup> <a href="b">a</a>.</p>\n<div class="footnote">\n<hr />\n<ol>\n<li id="fn:1">\n<p>Note <a href="d">c</a>.&#160;<a class="footnote-backref" href="#fnref:1" title="Jump back to footnote 1 in the text">&#8617;</a></p>\n</li>\n</ol>\n</div>',
    '<p><a class="cls" href="b">a</a> and <a href="d" id="id">c</a></p>',
    '<pre><code>[not](a link) `x`\n</code></pre>\n<p><a href="b">a</a></p>',
)


def _word(rng):
    return "".join(rng.choices(SYL, k=rng.randint(2, 4)))


def _a(href, text):
    return f'<a href="{href}">{text}</a>'


def _pages_html(case, size, seed):
    if type(size) is not int or not 0 <= size <= 20_000:
        raise ValueError("size must be an integer in 0..20000")
    if type(seed) is not int or not 0 <= seed < 1_000_000:
        raise ValueError("seed must be an integer in 0..999999")
    rng = random.Random(seed)
    out = []
    if case == "tag_index":
        for p in range(PAGES):
            tags = [f"{_word(rng)}-{_word(rng)}" for _ in range(size)]
            body = " · ".join(_a(f"/tags/{t}/", t) for t in tags)
            out.append(f"<h1>Tag index {p}</h1>\n<p>This page lists <em>every</em> tag used on the site, "
                       f"generated nightly. See {_a('/guide/', 'the guide')}.</p>" + (f"\n<p>{body}</p>" if size else ""))
        return out
    if case == "symbol_index":
        for p in range(PAGES):
            entries = []
            for _ in range(size):
                symbol = f"{_word(rng)}.{_word(rng)}_{_word(rng)}()"
                entries.append(f"<code>{symbol}</code> <em>{rng.choice(KINDS)}</em>")
            out.append(f"<h1>API index {p}</h1>\n<p>Every public symbol, generated from the docstrings. "
                       f"See {_a('/reference/', 'the reference guide')}.</p>" + (f"\n<p>{'; '.join(entries)}</p>" if size else ""))
        return out
    if case == "adjacent":
        links = []
        for i in range(size):
            w = _word(rng)
            links.append(_a(f"https://example.org/{w}/{'segment/' * rng.randint(1, 4)}{i}", f"{w} {i}"))
        return ["<p>" + "".join(links) + "</p>"] if size else [""]
    if case == "mixed":
        tokens = []
        for i in range(size):
            w = _word(rng)
            kind = rng.randrange(9)
            if kind == 0:
                tokens.append(_a(f"/p/{w}/{i}", w))
            elif kind == 1:
                tokens.append(f'<img alt="{w}" src="/img/{w}.png" />')
            elif kind == 2:
                tokens.append(f"<code>{w}[{i}]({w})</code>")
            elif kind == 3:
                tokens.append(f"<em>{w}</em>")
            elif kind == 4:
                tokens.append(f"<strong>{w}</strong>")
            elif kind == 5:
                url = f"https://{w}.example.org/{i}"
                tokens.append(_a(url, url))
            elif kind == 6:
                tokens.append("&copy;")
            elif kind == 7:
                tokens.append(_a(f"/a/{i}", w) + _a(f"/b/{i}", w))
            else:
                tokens.append(w)
        return ["<p>Intro line.</p>" + ("\n<p>" + " ".join(tokens) + "</p>" if size else "")]
    if case == "edge_core":
        return list(EDGE_CORE_HTML)
    if case == "edge_ext":
        return list(EDGE_EXT_HTML)
    raise ValueError(f"unsupported case {case!r}")


def expected(case, size, seed):
    htmls = _pages_html(case, size, seed)
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
