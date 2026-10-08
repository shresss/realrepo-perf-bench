import hashlib, json
EXT = ['md_in_html', 'fenced_code', 'tables', 'attr_list', 'toc']

def build_page(size, seed):
    parts = ['# API reference\n']
    for i in range(seed % 37, seed % 37 + size):
        parts.append(f'\n<div class="doc doc-object" markdown="1">\n## `pkg.module.func_{i}` <span class="badge">v1.{i % 9}</span>\n\n<div class="doc-contents" markdown="1">\nReturns the <b>{i}</b>-th record &mdash; see <a href="#func_{i + 1}">next</a> &amp; <em>notes</em>.\n\n| Name | Type | Description |\n|------|------|-------------|\n| `x` | <code>int</code> | value <span class="unit">ms</span> |\n\n```python\ndef func_{i}(x: int) -> int:\n    return x * {i}\n```\n</div>\n</div>\n')
    return ''.join(parts)
EDGES = {'empty': '', 'raw': "<div class='x'>raw <b>html</b></div>\n", 'inline': '<span>start</span> middle <em>end</em>\n\n<b>only</b>\n'}

def fixture(case, size, seed):
    return build_page(size, seed) if case == 'api' else EDGES[case]

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def observable(html, toc):
    return {'html_sha256': digest(html), 'html_length': len(html), 'toc_sha256': digest(json.dumps(toc, sort_keys=True, ensure_ascii=False, separators=(',', ':')))}

def run(case, size, seed):
    import markdown
    text = fixture(case, size, seed)
    md = markdown.Markdown(extensions=EXT)
    html = md.convert(text)
    result = observable(html, md.toc_tokens)
    if size <= 4:
        result['html'] = html
        md.reset()
        result['reset_equal'] = md.convert(text) == html
    return result
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--case', default='api')
    p.add_argument('--size', type=int, default=200)
    p.add_argument('--seed', type=int, default=0)
    a = p.parse_args()
    print(json.dumps(run(a.case, a.size, a.seed), ensure_ascii=False))
