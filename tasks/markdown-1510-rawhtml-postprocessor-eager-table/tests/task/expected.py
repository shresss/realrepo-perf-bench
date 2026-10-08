import hashlib,json
EXT=["md_in_html","fenced_code","tables","attr_list","toc"]
def build_page(size,seed):
    parts = ['# API reference\n']
    for i in range(seed % 37, seed % 37 + size):
        parts.append(f'\n<div class="doc doc-object" markdown="1">\n## `pkg.module.func_{i}` <span class="badge">v1.{i % 9}</span>\n\n<div class="doc-contents" markdown="1">\nReturns the <b>{i}</b>-th record &mdash; see <a href="#func_{i + 1}">next</a> &amp; <em>notes</em>.\n\n| Name | Type | Description |\n|------|------|-------------|\n| `x` | <code>int</code> | value <span class="unit">ms</span> |\n\n```python\ndef func_{i}(x: int) -> int:\n    return x * {i}\n```\n</div>\n</div>\n')
    return ''.join(parts)

EDGES={'empty': ('', ''), 'raw': ("<div class='x'>raw <b>html</b></div>\n", "<div class='x'>raw <b>html</b></div>"), 'inline': ('<span>start</span> middle <em>end</em>\n\n<b>only</b>\n', '<p><span>start</span> middle <em>end</em></p>\n<p><b>only</b></p>'), 'entities': ('Text &copy; &amp; &#169;\n', '<p>Text &copy; &amp; &#169;</p>'), 'comment': ('before\n\n<!-- raw comment -->\n\nafter\n', '<p>before</p>\n<!-- raw comment -->\n\n<p>after</p>')}
def fixture(case,size,seed):
    return build_page(size,seed) if case == 'api' else EDGES[case][0]
def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()
def observable(html,toc):
    return {"html_sha256":digest(html),"html_length":len(html),"toc_sha256":digest(json.dumps(toc,sort_keys=True,ensure_ascii=False,separators=(',',':')))}

ENTRY='<div class="doc doc-object">\n<h2 id="pkgmodulefunc_{i}-v1{v}"><code>pkg.module.func_{i}</code> <span class="badge">v1.{v}</span></h2>\n<div class="doc-contents">\n<p>Returns the <b>{i}</b>-th record &mdash; see <a href="#func_{nxt}">next</a> &amp; <em>notes</em>.</p>\n<table>\n<thead>\n<tr>\n<th>Name</th>\n<th>Type</th>\n<th>Description</th>\n</tr>\n</thead>\n<tbody>\n<tr>\n<td><code>x</code></td>\n<td><code>int</code></td>\n<td>value <span class="unit">ms</span></td>\n</tr>\n</tbody>\n</table>\n<pre><code class="language-python">def func_{i}(x: int) -&gt; int:\n    return x * {i}\n</code></pre>\n</div>\n</div>'
def expected(case,size,seed):
    toc=[]
    if case=='api':
        parts=['<h1 id="api-reference">API reference</h1>'];children=[]
        for i in range(seed % 37,seed % 37+size):
            parts.append(ENTRY.format(i=i,v=i%9,nxt=i+1))
            children.append({"level":2,"id":f"pkgmodulefunc_{i}-v1{i%9}","name":f"pkg.module.func_{i} v1.{i%9}","html":f'<code>pkg.module.func_{i}</code> <span class="badge">v1.{i%9}</span>',"data-toc-label":"","children":[]})
        html='\n'.join(parts)
        toc=[{"level":1,"id":"api-reference","name":"API reference","html":"API reference","data-toc-label":"","children":children}]
    else: html=EDGES[case][1]
    result=observable(html,toc)
    if size<=4:result.update(html=html,reset_equal=True)
    return result
