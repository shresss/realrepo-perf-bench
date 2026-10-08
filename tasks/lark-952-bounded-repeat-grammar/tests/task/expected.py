import hashlib,json,random
def expected(case,size,seed):
    rng=random.Random(seed)
    minimum=0 if case=="compile" else (size if case=="exact" else size//2)
    lengths=sorted(set([minimum,(minimum+size)//2,size]))
    inputs=["".join(rng.choice("AB") for _ in range(n)) for n in lengths]
    values=[[["LETTER",char] for char in text] for text in inputs]
    return {"lengths":lengths,"sha256":hashlib.sha256(json.dumps(values,separators=(",",":")).encode()).hexdigest(),"raw":values if size<=8 else [],"rejected":[size+1]+([minimum-1] if minimum else [])}
