import hashlib
import json
import random


def run(case: str, size: int, seed: int) -> dict:
    import pyparsing as pp
    if case == "comments":
        texts = ["/**/", "/* a ** / b */", "// keep \\\n going\n", "// eof"]
        return {"cpp": [pp.cpp_style_comment.parse_string(text, parse_all=True).as_list() for text in texts],
                "java": [pp.java_style_comment.parse_string(text, parse_all=True).as_list() for text in texts]}
    rng = random.Random(seed)
    symbols = [f"symbol_{i}_{rng.randrange(100000)}" for i in range(size)]
    pieces = []
    for i, symbol in enumerate(symbols):
        pieces.append(symbol)
        if i % 3 == 0:
            pieces.append(" /* ordinary annotation ** / across\n two lines */ ")
        elif i % 3 == 1:
            pieces.append(" // line annotation \\\ncontinued comment\n")
        else:
            pieces.append("/**/ \n")
    text = " ".join(pieces)
    grammar = pp.ZeroOrMore(pp.Word(pp.alphas + "_", pp.alphanums + "_")).ignore(pp.cpp_style_comment)
    values = grammar.parse_string(text, parse_all=True).as_list()
    return {"count": len(values), "sha256": hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest(), "raw": values if size <= 8 else []}


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, "/app")
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
