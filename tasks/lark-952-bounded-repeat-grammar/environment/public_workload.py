import hashlib,json,random

def run(case,size,seed):
    if case != "compile":
        raise ValueError("Public aid supports only compile")
    from lark import Lark, UnexpectedInput
    rng=random.Random(seed)
    minimum=0
    grammar="start: LETTER~"+str(minimum)+".."+str(size)+"\nLETTER: /[AB]/"
    lengths=sorted(set([minimum,(minimum+size)//2,size]))
    inputs=["".join(rng.choice("AB") for _ in range(n)) for n in lengths]
    invalid=["A"*(size+1)] + (["A"*(minimum-1)] if minimum else [])
    parser=Lark(grammar,parser="lalr")
    values=[]
    for text in inputs:
        tree=parser.parse(text)
        values.append([[str(t.type),str(t)] for t in tree.children])
    rejected=[]
    for text in invalid:
        try:parser.parse(text)
        except UnexpectedInput:rejected.append(len(text))
    return {"lengths":[len(v) for v in values],"sha256":hashlib.sha256(json.dumps(values,separators=(",",":")).encode()).hexdigest(),"raw":values if size<=8 else [],"rejected":rejected}


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, "/app")
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["compile"], required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
