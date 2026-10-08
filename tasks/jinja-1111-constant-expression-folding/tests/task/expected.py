"""Independent standard-library rendering oracle; imports no Jinja code."""
import hashlib


def expected(case, size, seed):
    if case == "catalog":
        parts = ("catalog-row", " layout-grid", " gap-small", " align-center", " color-primary",
                 " border-thin", " background-light", " padding-small", " margin-bottom",
                 " text-regular", " line-normal", " weight-normal", " display-block",
                 " width-full", " height-auto", " overflow-hidden")
        template = "{% for row in rows %}{% set css = " + " ~ ".join(map(repr, parts)) + " %}<li class=\"{{ css }}\">{{ row }}</li>\n{% endfor %}"
        output = ''.join('<li class="{}">{}</li>\n'.format(''.join(parts), row)
                         for row in range(size)).encode()
        return {"mode": "render", "rows": size,
                "template_sha256": hashlib.sha256(template.encode()).hexdigest(),
                "output_sha256": hashlib.sha256(output).hexdigest(), "bytes": len(output)}
    if case == "expressions":
        return {"outputs": ["&lt;&amp;&gt;", "<&>", "&lt;x&gt;|<x>", "[1, 2]:None",
                            "&amp;1;&amp;2;", "<&amp;", "&lt;x&gt;", "<x>"]}
    raise ValueError(case)
