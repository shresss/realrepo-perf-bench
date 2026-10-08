"""Offline batch domain normalization for a DNS analytics export."""
import hashlib,json
SEMANTIC_INPUTS={'empty-ip': ['', 'http://', 'https://127.0.0.1/x'], 'wildcard': ['sub.www.example.ck', 'www.ck', 'nes.buskerud.no', 'buskerud.no'], 'unicode': ['https://www。example．com', 'http://xn--h1alffa9f.xn--p1ai']}
SUFFIXES=('com','co.uk','com.au','net','org')
PREFIX=('edge','ingress','pool','shard','worker','region','zone','cell','rack','node','team','account','tenant','unit','cluster','service','endpoint','origin','branch','group','stack','stage')
def fixture(size,seed,deep=True):
 urls=[]
 for i in range(size):
  n=i+seed
  labels=([f'r{n}',*PREFIX] if deep else ['www'])+[f'customer{n%1000}',SUFFIXES[n%5]]
  host='.'.join(labels)
  assert len(host.encode('ascii'))<=253 and all(0<len(x)<=63 and x.isalnum() for x in host.split('.'))
  urls.append('https://'+host+'/events/'+str(n)+'?source=dns')
 return urls

def run(case,size,seed):
 if case not in ('deep', 'empty-ip', 'short', 'unicode', 'wildcard'): raise ValueError(case)
 import tldextract
 if case not in ('deep','short'):
  options={'cache_dir':None,'suffix_list_urls':()}
  extract=tldextract.TLDExtract(**options)
  return {'rows':[list(extract(url)) for url in SEMANTIC_INPUTS[case]]}
 urls=fixture(size,seed,case=='deep')
 extract=tldextract.TLDExtract(cache_dir=None,suffix_list_urls=())
 extract('warmup.example.com')
 digest=hashlib.sha256();counts={s:0 for s in SUFFIXES}
 for url in urls:
  r=extract(url)
  digest.update(('\t'.join(r)+'\n').encode('utf8'))
  counts[r.suffix]=counts.get(r.suffix,0)+1
 return {'count':len(urls),'sha256':digest.hexdigest(),'suffix_counts':counts}
if __name__=='__main__':
 import argparse,sys
 a=argparse.ArgumentParser();a.add_argument('--source');a.add_argument('--case',default='deep');a.add_argument('--size',type=int,default=200000);a.add_argument('--seed',type=int,default=1729);args=a.parse_args()
 if args.source:sys.path.insert(0,args.source)
 import tldextract
 if args.source:assert tldextract.__file__.startswith(args.source)
 print(json.dumps(run(args.case,args.size,args.seed),sort_keys=True))
