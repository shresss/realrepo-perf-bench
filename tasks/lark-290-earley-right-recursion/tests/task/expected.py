import hashlib,json,random
def expected(case,size,seed):
    if case=="malformed":return {"error":"UnexpectedCharacters","position":size}
    rng=random.Random(seed)
    rows=[["node","start",1]]
    for _ in range(size):rows.extend([["node","sequence",2],["token","LETTER",rng.choice("AB")]])
    rows.append(["node","sequence",0])
    return {"count":size,"sha256":hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest(),"raw":rows if size<=8 else []}
