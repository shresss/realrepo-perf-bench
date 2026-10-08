import hashlib

SEMANTIC_EXPECTED={'empty-ip': [['', '', ''], ['', '', ''], ['', '127.0.0.1', '']], 'wildcard': [['sub', 'www', 'example.ck'], ['', 'www', 'ck'], ['', '', 'nes.buskerud.no'], ['', 'buskerud', 'no']], 'unicode': [['www', 'example', 'com'], ['', 'xn--h1alffa9f', 'xn--p1ai']], 'private': [['', 'foo', 'blogspot.com'], ['', '', 's3.ap-south-1.amazonaws.com'], ['ap-south-1', 'amazonaws', 'com']], 'root': [['www', 'example', 'com'], ['', '', 'co.uk'], ['example', 'za', '']], 'extra': [['node', 'customer', 'example.internal'], ['', 'node', 'example.internal']]}

def expected(case,size,seed):
 if case in SEMANTIC_EXPECTED:return {"rows":SEMANTIC_EXPECTED[case]}
 suffixes=['com','co.uk','com.au','net','org'];counts={s:0 for s in suffixes};digest=hashlib.sha256()
 middle='edge.ingress.pool.shard.worker.region.zone.cell.rack.node.team.account.tenant.unit.cluster.service.endpoint.origin.branch.group.stack.stage'
 for serial in range(seed,seed+size):
  suffix=suffixes[serial%5];counts[suffix]+=1
  subdomain=('r'+str(serial)+'.'+middle) if case=='deep' else 'www'
  domain='customer'+str(serial%1000)
  digest.update((subdomain+'\t'+domain+'\t'+suffix+'\n').encode('utf8'))
 return {'count':size,'sha256':digest.hexdigest(),'suffix_counts':counts}
