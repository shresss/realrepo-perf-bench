import hashlib
import json
import random

GRAMMAR = r'''
start: record*
record: NAME "=" SIGNED_INT ";"
%import common.CNAME -> NAME
%import common.SIGNED_INT
%import common.WS
%ignore WS
'''


def run(case: str, size: int, seed: int) -> dict:
    from lark import Lark
    if case != "records":
        raise ValueError("The public profiling aid supports only records")
    rng = random.Random(seed)
    pairs = [("item_" + str(i), rng.randrange(-10000, 10001)) for i in range(size)]
    text = "\n".join(f"{name} = {value};" for name, value in pairs)
    parser = Lark(GRAMMAR, parser="lalr")
    cursor = parser.parse_interactive(text)
    trace = []
    for token in cursor.iter_parse():
        trace.append(sorted(cursor.accepts()))
    trace.append(sorted(cursor.accepts()))
    tree = cursor.feed_eof()
    values = [[str(record.children[0]), int(record.children[1])] for record in tree.children]
    payload = {"values": values, "allowed": trace}
    return {"count": len(values), "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest(), "raw": payload if size <= 8 else {}}


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, "/app")
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["records"], required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
