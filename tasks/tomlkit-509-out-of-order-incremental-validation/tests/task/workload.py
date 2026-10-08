import hashlib,json,copy,pickle
def build_doc(size,seed):
    lines=["# service config", 'server.host = "0.0.0.0"', "server.port = 8080", "server.workers = 4", 'server.tls.cert = "/etc/ssl/svc.pem"']
    for i in range(size):
        name=["app","db","http","cache","auth","jobs","mail","audit"][i%8]+f"_{i+seed}"
        lines += [f'logging.loggers.{name}.level = "{["INFO","DEBUG","WARNING"][(i+seed)%3]}"',f'logging.loggers.{name}.handler = "{["console","file"][(i+seed)%2]}"',f"logging.loggers.{name}.propagate = {'true' if (i+seed)%2 else 'false'}"]
    lines += ['server.tls.key = "/etc/ssl/svc.key"',"server.timeout_s = 30",'server.log_level = "info"',"server.debug = false",""]
    return "\n".join(lines)

DOCUMENTS={
 'empty':'',
 'duplicate':'a.b.c = 1\na.b.c = 2\n',
 'conflict':'a.b = 1\na.b.c = 2\n',
 'header_collision':'[a]\nb.c = 1\n[q]\nx = 1\n[a]\nb.c = 2\n',
 'unicode':'"日本".x = 1\n"日本".y = "été"\nz = 0\n"日本".w = 3\n',
 'interleaved':'a.x = 1\nb.y = 2\na.z = 3\nb.w = 4\na.q.r = 5\n',
 'headers':'[a.x]\nk = 1\n[b]\nm = 2\n[a.y]\nn = 3\n[a.x.deep]\no = 4\n',
 'aot':"[[jobs]]\nname = 'a'\nopts.retries = 1\nopts.backoff = 2\n[[jobs]]\nname = 'b'\nopts.retries = 3\n",
 'mutation':'# preserve me\na.x = 1\nb.y = 2\na.z = 3\n',
}

def run(case,size,seed):
    import tomlkit
    text=build_doc(size,seed) if case in ('logging','floor') else DOCUMENTS[case]
    if case=='floor':return {'bytes':len(text)}
    try:doc=tomlkit.parse(text)
    except Exception as e:return {'error':type(e).__name__}
    out=tomlkit.dumps(doc);data=doc.unwrap()
    result={'roundtrip':out==text,'text_sha256':hashlib.sha256(out.encode()).hexdigest(),'data_sha256':hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'top_keys':list(doc.keys())}
    if case!='logging':
        result['data']=data
        result['copy_roundtrip']=tomlkit.dumps(copy.copy(doc))==text
        result['pickle_roundtrip']=tomlkit.dumps(pickle.loads(pickle.dumps(doc)))==text
    if case=='mutation':
        edited=[]
        for changed in (doc,copy.copy(tomlkit.parse(text)),pickle.loads(pickle.dumps(tomlkit.parse(text)))):
            changed['a']['x']=7
            del changed['a']['z']
            changed['a']['w']=9
            changed['new']={'nested':seed+1}
            changed['temporary']=1
            del changed['temporary']
            serialized=tomlkit.dumps(changed)
            edited.append({'data':changed.unwrap(),'reparsed':tomlkit.parse(serialized).unwrap(),'comment':'# preserve me' in serialized,'contains':('z' in changed['a'],'w' in changed['a'])})
        result['edited']=edited
    return result

if __name__=='__main__':
 import argparse
 a=argparse.ArgumentParser();a.add_argument('--case',default='logging');a.add_argument('--size',type=int,default=16);a.add_argument('--seed',type=int,default=0);v=a.parse_args();print(json.dumps(run(v.case,v.size,v.seed),sort_keys=True,ensure_ascii=False))
