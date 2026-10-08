import hashlib, json, random
def expected(case,size,seed):
    rng=random.Random(seed)
    groups={}
    for i in range(size):
        region="r"+str(rng.randrange(8));sensor="s"+str(rng.randrange(3));rng.randrange(101)
        if case=="defaults" and i%2==0:sensor="unknown"
        groups.setdefault(region,{}).setdefault(sensor,[]).append("scene_"+str(i))
    rows=[[[],[]]]
    for region,sensors in groups.items():
        rows.append([[region],[]])
        for sensor,items in sensors.items():rows.append([[region,sensor],items])
    return {"count":size,"created":len(rows)-1,"idempotent":True,"parents":True,"unchanged":True,"sha256":hashlib.sha256(json.dumps(rows,separators=(",",":")).encode()).hexdigest(),"raw":rows if size<=8 else []}
