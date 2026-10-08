import asyncio, hashlib, json, sys
from pathlib import Path

def build(case, size, seed):
    roots = [Path(item) for item in sys.path if item] + [Path.cwd()]
    root = next(item for item in roots if (item / "src/datasets/__init__.py").is_file())
    sys.path.insert(0, str(root / "src"))
    import datasets
    assert Path(datasets.__file__).resolve().is_relative_to(root.resolve()), datasets.__file__
    import tqdm
    tqdm.tqdm.monitor_interval = 0
    from datasets import Dataset, Features, Value
    datasets.disable_progress_bars()
    data={"id":list(range(size)),"x":[(i*37+seed)%997 for i in range(size)],"text":["r"+str((i+seed)%71) for i in range(size)],"nullable":[None if i%11==0 else i%23 for i in range(size)]}
    ds=Dataset.from_dict(data,features=Features({"id":Value("int64"),"x":Value("int32"),"text":Value("string"),"nullable":Value("int32")}))
    if case=="indexed": ds=ds.select(list(range(size-1,-1,-1)))
    return ds,data

def observe(ds,data,case,seed):
    before=ds.to_dict()
    def predicate(row,index,modulus): return (row["x"]+index+seed)%modulus < 3 and row["nullable"] is not None
    async def asynchronous(row,index,modulus):
        await asyncio.sleep(0)
        return predicate(row,index,modulus)
    def batched(batch,indices,modulus):
        return [(x+i+seed)%modulus < 3 and n is not None for x,i,n in zip(batch["x"],indices,batch["nullable"])]
    kwargs={"with_indices":True,"fn_kwargs":{"modulus":7},"keep_in_memory":True,"load_from_cache_file":False,"batch_size":17 if case!="row_filter" else 1000}
    if case=="batched": out=ds.filter(batched,batched=True,**kwargs)
    elif case=="async": out=ds.filter(asynchronous,**kwargs)
    elif case=="input_columns":
        def columns(x,n,index,modulus): return (x+index+seed)%modulus<3 and n is not None
        out=ds.filter(columns,input_columns=["x","nullable"],**kwargs)
    else: out=ds.filter(predicate,**kwargs)
    got=out.to_dict()
    return {"count":len(out),"sha256":hashlib.sha256(json.dumps(got,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest(),"columns":out.column_names,"features":{k:v.dtype for k,v in out.features.items()},"small":got if len(ds)<100 else None,"input_unchanged":before==ds.to_dict()}

def run(case,size,seed):
    ds,data=build(case,size,seed)
    return observe(ds,data,case,seed)

if __name__ == "__main__":
    import argparse
    p=argparse.ArgumentParser();p.add_argument("--case",default="row_filter");p.add_argument("--size",type=int,default=10000);p.add_argument("--seed",type=int,default=71)
    a=p.parse_args();print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True))
