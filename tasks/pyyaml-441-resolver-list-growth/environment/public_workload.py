import argparse
import hashlib
import json
import sys
from pathlib import Path
import re

def _load_package():
    # The upstream Python 3 package lives in lib3, including in verifier snapshots.
    for item in list(sys.path):
        candidate=Path(item or '.').resolve() / 'lib3'
        if (candidate / 'yaml' / '__init__.py').is_file():
            sys.path.insert(0,str(candidate))
            break
    import yaml
    return yaml

def _normalize(value):
    if isinstance(value,dict):return {str(k):_normalize(v) for k,v in value.items()}
    if isinstance(value,list):return [_normalize(v) for v in value]
    if hasattr(value,'isoformat'):return value.isoformat()
    return value

def run(case,size,seed):
    yaml=_load_package()
    class RecordLoader(yaml.SafeLoader):pass
    RecordLoader.add_implicit_resolver('!ticket',re.compile(r'^ticket-[0-9]+$'),None)
    RecordLoader.add_constructor('!ticket',lambda loader,node: 'T:'+loader.construct_scalar(node))
    if case=='records':
        text=''.join(f'- name: file-{seed}-{i}\n  flag: false\n  ticket: ticket-{(i*17+seed)%997}\n' for i in range(size))
        value=yaml.load(text,Loader=RecordLoader)
    elif case=='semantics':
        text="""plain: ticket-17
quoted: 'ticket-17'
flow: [true, false, null, 12, 1.5, 'false', ticket-9, ordinary]
date: 2020-01-02
block: |
  ticket-6
unicode: café
empty: ''
"""
        value=yaml.load(text,Loader=RecordLoader)
    else:raise ValueError(case)
    value=_normalize(value)
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)
    return {'count':len(value or []),'sha256':hashlib.sha256(raw.encode()).hexdigest(),'sample':value[:3] if isinstance(value,list) else value}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='records');ap.add_argument('--size',type=int,default=2000);ap.add_argument('--seed',type=int,default=71);a=ap.parse_args()
    sys.path.insert(0,'/app')
    print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True))
