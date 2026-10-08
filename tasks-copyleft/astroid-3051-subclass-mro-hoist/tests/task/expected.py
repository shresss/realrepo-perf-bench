import hashlib,json

def expected(case,size,seed):
    n=size
    lines=['class Base: pass']
    for level in range(12):lines.append('class Model%d(%s): pass'%(level,'Base' if level==0 else 'Model'+str(level-1)))
    lines += ['class Dispatch%d: pass'%i for i in range(24)]
    lines.append('leaf = Model11()')
    start=len(lines)
    for i in range(n):
     types=', '.join('Dispatch'+str(j) for j in range(24))
     if i%4:types+=', Base'
     lines.append(('issubclass(Model11, (%s))' if i%2==0 else 'isinstance(leaf, (%s))')%types)
    text='\n'.join(lines)+'\n'
    values=[bool(i%4) for i in range(n)]
    return {'mode':'infer','checks':n,'true':sum(values),'output_sha256':hashlib.sha256(json.dumps(values,separators=(',',':')).encode()).hexdigest(),'source_sha256':hashlib.sha256(text.encode()).hexdigest()}
