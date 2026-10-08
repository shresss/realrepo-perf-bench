"""Render deterministic catalog and expression examples through Jinja's public API."""
import argparse
import hashlib
import json


def run(case, size, seed):
    from jinja2 import Environment

    if case == "catalog":
        fragments = ["catalog-row", " layout-grid", " gap-small", " align-center", " color-primary",
                     " border-thin", " background-light", " padding-small", " margin-bottom",
                     " text-regular", " line-normal", " weight-normal", " display-block",
                     " width-full", " height-auto", " overflow-hidden"]
        literal = "".join(fragments)
        expression = " ~ ".join(repr(x) for x in fragments)
        template_text = "{% for row in rows %}{% set css = " + expression + " %}<li class=\"{{ css }}\">{{ row }}</li>\n{% endfor %}"
        rows = range(size)
        env = Environment(autoescape=True)
        input_digest = hashlib.sha256(template_text.encode()).hexdigest()
        template = env.from_string(template_text)
        rendered = template.render(rows=rows)
        expected = "".join('<li class="' + literal + '">' + str(i) + '</li>\n' for i in rows)
        assert rendered == expected
        return {"mode": "render", "rows": size, "template_sha256": input_digest,
                "output_sha256": hashlib.sha256(rendered.encode()).hexdigest(),
                "bytes": len(rendered.encode())}
    if case == "expressions":
        examples = [
            ("{% set v = '<' ~ text ~ '>' %}{{ v }}", {"text": "&"}, True),
            ("{% set v = '<' ~ text ~ '>' %}{{ v }}", {"text": "&"}, False),
            ("{% autoescape true %}{% set v = '<' ~ 'x' ~ '>' %}{{ v }}{% endautoescape %}|{% autoescape false %}{% set v = '<' ~ 'x' ~ '>' %}{{ v }}{% endautoescape %}", {}, False),
            ("{% set v = [1, 2] ~ ':' ~ none %}{{ v }}", {}, False),
            ("{% for n in ns %}{% set v = '&' ~ n %}{{ v }};{% endfor %}", {"ns": [1, 2]}, True),
            ("{% set v = ('<'|safe) ~ text %}{{ v }}", {"text": "&"}, True),
            ("{% autoescape enabled %}{% set v = '<' ~ 'x' ~ '>' %}{{ v }}{% endautoescape %}", {"enabled": True}, False),
            ("{% autoescape enabled %}{% set v = '<' ~ 'x' ~ '>' %}{{ v }}{% endautoescape %}", {"enabled": False}, True),
        ]
        return {"outputs": [Environment(autoescape=escape).from_string(text).render(**context)
                            for text, context, escape in examples]}
    raise ValueError(case)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True, allow_nan=False))
