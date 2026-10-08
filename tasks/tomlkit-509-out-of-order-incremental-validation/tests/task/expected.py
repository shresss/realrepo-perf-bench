import hashlib,json,tomllib
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

def expected(case,size,seed):
 text=build_doc(size,seed) if case=='logging' else DOCUMENTS[case]
 if case in ('duplicate','conflict','header_collision'):return {'error':'ParseError'}
 data=tomllib.loads(text)
 result={'roundtrip':True,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),'data_sha256':hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest(),'top_keys':list(data.keys())}
 if case!='logging':result.update(data=data,copy_roundtrip=True,pickle_roundtrip=True)
 if case=='mutation':
  changed={'a':{'x':7,'w':9},'b':{'y':2},'new':{'nested':seed+1}}
  result['edited']=[{'data':changed,'reparsed':changed,'comment':True,'contains':[False,True]} for _ in range(3)]
 return result
