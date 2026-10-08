import hashlib, json, random
from datetime import datetime, timezone

def run(case, size, seed):
    if case != "catalog":
        raise ValueError("Public aid supports only catalog")
    from pystac import Catalog, Item
    rng=random.Random(seed)
    root=Catalog(id="inventory",description="Regional imagery inventory")
    items=[]
    for i in range(size):
        props={"region":"r"+str(rng.randrange(8)),"sensor":"s"+str(rng.randrange(3)),"quality":rng.randrange(101)}
        item=Item(id="scene_"+str(i),geometry={"type":"Point","coordinates":[float(i%180),float(i%80)]},bbox=[float(i%180),float(i%80),float(i%180),float(i%80)],datetime=datetime(2020,1,1,tzinfo=timezone.utc),properties=props)
        items.append(item)
        root.add_item(item)
    before=[json.dumps([i.properties,i.geometry,i.bbox],sort_keys=True) for i in items]
    created=root.generate_subcatalogs('${region}/${sensor}',defaults={"sensor":"unknown"})
    again=root.generate_subcatalogs('${region}/${sensor}',defaults={"sensor":"unknown"})
    observed=[]
    parents=True
    def walk(cat,path):
        nonlocal parents
        direct=list(cat.get_items())
        observed.append([path,[i.id for i in direct]])
        for item in direct:
            parents=parents and item.get_parent() is cat and item.get_root() is root
        for child in cat.get_children():
            parents=parents and child.get_parent() is cat and child.get_root() is root
            walk(child,path+[child.id])
    walk(root,[])
    unchanged=before==[json.dumps([i.properties,i.geometry,i.bbox],sort_keys=True) for i in items]
    return {"count":sum(len(row[1]) for row in observed),"created":len(created),"idempotent":len(again)==0,"parents":parents,"unchanged":unchanged,"sha256":hashlib.sha256(json.dumps(observed,separators=(",",":")).encode()).hexdigest(),"raw":observed if size<=8 else []}


if __name__ == "__main__":
    import argparse, sys
    sys.path.insert(0, "/app")
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", choices=["catalog"], required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), sort_keys=True))
