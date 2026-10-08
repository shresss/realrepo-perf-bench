import hashlib, json, random
def expected(case,size,seed):
    if case=="comments":
        tokens=[["/**/"],["/* a ** / b */"],["// keep \\\n going"],["// eof"]]
        return {"cpp":tokens,"java":tokens}
    rng=random.Random(seed)
    values=[f"symbol_{i}_{rng.randrange(100000)}" for i in range(size)]
    return {"count":len(values),"sha256":hashlib.sha256(json.dumps(values,separators=(",",":")).encode()).hexdigest(),"raw":values if size<=8 else []}
