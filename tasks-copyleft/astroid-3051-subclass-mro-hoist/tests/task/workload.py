import hashlib,json

def run(case,size,seed):
    n=size
    import astroid
    lines=['class Base: pass']
    for level in range(12):lines.append('class Model%d(%s): pass'%(level,'Base' if level==0 else 'Model'+str(level-1)))
    lines += ['class Dispatch%d: pass'%i for i in range(24)]
    lines.append('leaf = Model11()')
    start=len(lines)
    for i in range(n):
     types=', '.join('Dispatch'+str(j) for j in range(24))
     if i%4:types+=', Base'
     lines.append(('issubclass(Model11, (%s))' if i%2==0 else 'isinstance(leaf, (%s))')%types)
    text='\n'.join(lines)+'\n';module=astroid.parse(text,module_name='generated_models');queries=module.body[start:];assert len(queries)==n
    source_hash=hashlib.sha256(text.encode()).hexdigest()
    if case=='floor':result={'mode':'floor','checks':n,'source_sha256':source_hash}
    else:
     values=[]
     for expression in queries:
      inferred=list(expression.value.infer());assert len(inferred)==1 and isinstance(inferred[0],astroid.nodes.Const)
      values.append(inferred[0].value)
     assert values==[bool(i%4) for i in range(n)]
     result={'mode':'infer','checks':n,'true':sum(values),'output_sha256':hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest(),'source_sha256':source_hash}
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--case',required=True);p.add_argument('--size',type=int,required=True);p.add_argument('--seed',type=int,required=True);a=p.parse_args();print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True))
