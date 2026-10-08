import json,hashlib

def expected(case,size,seed):
    before=[[(i*17+seed)%10007,(i*31+seed)%10009] for i in range(size)]
    after=list(before)
    if case=='mutate' and size:
        after.insert(0,before[0]);after[-1]=before[0];after.pop(1)
    h=lambda v:hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest()
    result={'count':len(after),'sha256':h(after),'small':after if size<30 else None,'before_hash':h(before)}
    if case in ('signed_write','copy_signed_write','pickle_signed_write'):result['pixels']=[[-1,'SS'] for i in range(size)]
    return result
