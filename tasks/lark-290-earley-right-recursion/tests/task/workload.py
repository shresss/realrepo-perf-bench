import hashlib,json,random,sys

def run(case,size,seed):
    from lark import Lark
    sys.setrecursionlimit(20000)
    rng=random.Random(seed)
    text="".join(rng.choice("AB") for _ in range(size))
    grammar="start: sequence\nsequence: LETTER sequence |\nLETTER: /[AB]/"
    if case=="branch":
        grammar=grammar.replace("start: sequence", 'start: sequence "!"')
        text+="!"
    elif case=="ignored":
        grammar+='\n%ignore " "'
        text=" ".join(text)
    parser=Lark(grammar,parser="earley",lexer="dynamic",ambiguity="resolve")
    if case=="malformed":
        from lark.exceptions import UnexpectedCharacters
        try:
            parser.parse(text+"?")
        except UnexpectedCharacters as exc:
            return {"error":type(exc).__name__,"position":exc.pos_in_stream}
        return {"error":None,"position":None}
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
    ap.add_argument("--case", required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
