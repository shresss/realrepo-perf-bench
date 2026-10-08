import hashlib,json

def expected(case,size,seed):
    ids=list(range(size))
    if case=="indexed":ids.reverse()
    keep=[i for position,i in enumerate(ids) if ((i*37+seed)%997+position+seed)%7<3 and i%11!=0]
    got={"id":keep,"x":[(i*37+seed)%997 for i in keep],"text":["r"+str((i+seed)%71) for i in keep],"nullable":[i%23 for i in keep]}
    return {"count":len(keep),"sha256":hashlib.sha256(json.dumps(got,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest(),"columns":["id","x","text","nullable"],"features":{"id":"int64","x":"int32","text":"string","nullable":"int32"},"small":got if size<100 else None,"input_unchanged":True}
