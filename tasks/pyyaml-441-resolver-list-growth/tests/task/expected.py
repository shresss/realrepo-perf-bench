import hashlib,json

def expected(case,size,seed):
    if case=='records':
        value=[{'name':f'file-{seed}-{i}','flag':False,'ticket':f'T:ticket-{(i*17+seed)%997}'} for i in range(size)] or None
    elif case=='semantics':
        value={'plain':'T:ticket-17','quoted':'ticket-17','flow':[True,False,None,12,1.5,'false','T:ticket-9','ordinary'],'date':'2020-01-02','block':'ticket-6\n','unicode':'café','empty':''}
    elif case=='documents':value=[['T:ticket-1',False],['T:ticket-2',23]]
    else:raise ValueError(case)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)
    return {'count':len(value or []),'sha256':hashlib.sha256(raw.encode()).hexdigest(),'sample':value[:3] if isinstance(value,list) else value}
