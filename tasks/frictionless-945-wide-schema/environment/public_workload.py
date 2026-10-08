import hashlib,json

def run(case,size,seed):
    if case != "records":raise ValueError(case)
    from frictionless import Resource,Layout
    header=['feature_'+str(seed)+'_'+str(i) for i in range(size)]
    rows=[]
    for r in range(8):
        row=[]
        for c in range(size):
            value=[str(seed+r+c),'naïve_'+str(seed)+'_'+str(r),['true','false'][r%2],'2021-11-%02d'%(r+1)][c%4]
            row.append('' if r==0 and c%7==0 else value)
        rows.append(row)
    data=[header]+rows
    original=json.dumps(data,ensure_ascii=False)
    resource=Resource(data,layout=Layout(header=True))
    resource.infer()
    fields=resource.schema['fields']
    normalized=[[f['name'],f['type'],f.get('format','default')] for f in fields]
    encoded=json.dumps(normalized,ensure_ascii=False,separators=(',',':')).encode()
    return {'columns':len(fields),'schema_sha256':hashlib.sha256(encoded).hexdigest(),'types':{t:sum(f['type']==t for f in fields) for t in sorted({f['type'] for f in fields})},'head':normalized[:4],'tail':normalized[-4:],'input_unchanged':json.dumps(data,ensure_ascii=False)==original}

if __name__=='__main__':
    import sys,argparse
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='records');ap.add_argument('--size',type=int,default=256);ap.add_argument('--seed',type=int,default=71);a=ap.parse_args();sys.path.insert(0,'/app');print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True))
