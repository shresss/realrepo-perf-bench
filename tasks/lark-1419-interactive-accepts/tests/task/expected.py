import hashlib, json, random
def expected(case,size,seed):
    if case=="context":
        return {"trace":[["A","B"],["C"],["X" if seed%2==0 else "Y"],["$END"]],"tree":"start\n  inner\n"}
    if case=="copy":
        return {"isolated":True,"values":[["first",1],["second",-2]]}
    if case=="callbacks":
        return {"callbacks_suppressed":True,"calls":[["first",1],["second",-2]],"values":[["first",1],["second",-2]]}
    rng=random.Random(seed)
    values=[["item_"+str(i),rng.randrange(-10000,10001)] for i in range(size)]
    allowed=[["$END","NAME"],["EQUAL"],["SIGNED_INT"],["SEMICOLON"]]*size+[["$END","NAME"]]
    payload={"values":values,"allowed":allowed}
    return {"count":len(values),"sha256":hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest(),"raw":payload if size<=8 else {}}
