import hashlib,json,random,sys

def run(case,size,seed):
    if case != "sequence":
        raise ValueError("Public aid supports only sequence")
    from lark import Lark
    sys.setrecursionlimit(20000)
    rng=random.Random(seed)
    text="".join(rng.choice("AB") for _ in range(size))
    grammar="start: sequence\nsequence: LETTER sequence |\nLETTER: /[AB]/"
    parser=Lark(grammar,parser="earley",lexer="dynamic",ambiguity="resolve")
    tree=parser.parse(text)
    rows=[];stack=[tree]
    while stack:
        node=stack.pop()
        if hasattr(node,"children"):
            rows.append(["node",str(node.data),len(node.children)])
            stack.extend(reversed(node.children))
        else:rows.append(["token",str(node.type),str(node)])
    return {"count":sum(row[0]=="token" for row in rows),"sha256":hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest(),"raw":rows if size<=8 else []}


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, "/app")
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["sequence"], required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
