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
    if case == "context":
        parser = Lark('start: "a" inner "x" | "b" inner "y"\ninner: "c"', parser="lalr")
        text = "acx" if seed % 2 == 0 else "bcy"
        cursor = parser.parse_interactive(text)
        trace = []
        for token in cursor.iter_parse():
            trace.append(sorted(cursor.accepts()))
        trace.append(sorted(cursor.accepts()))
        tree = cursor.feed_eof()
        return {"trace": trace, "tree": tree.pretty()}
    if case == "copy":
        parser = Lark(GRAMMAR, parser="lalr")
        cursor = parser.parse_interactive("first=1; second=-2;")
        cursor.exhaust_lexer()
        before = repr(cursor.parser_state.value_stack)
        clone = cursor.copy()
        clone.parser_state.value_stack[0].children.append("clone-only")
        return {"isolated": repr(cursor.parser_state.value_stack) == before,
                "values": [[str(row.children[0]), int(row.children[1])] for row in cursor.feed_eof().children]}
    if case == "callbacks":
        from lark import Transformer
        calls = []
        class Callbacks(Transformer):
            def record(self, children):
                calls.append([str(children[0]), int(children[1])])
                return children
        parser = Lark(GRAMMAR, parser="lalr", transformer=Callbacks())
        cursor = parser.parse_interactive("first=1; second=-2;")
        for token in cursor.iter_parse():
            before = len(calls)
            cursor.accepts()
            if len(calls) != before:
                return {"callbacks_suppressed": False}
        cursor.accepts()
        tree = cursor.feed_eof()
        return {"callbacks_suppressed": True, "calls": calls,
                "values": [[str(row[0]), int(row[1])] for row in tree.children]}
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
    ap.add_argument("--case", required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
