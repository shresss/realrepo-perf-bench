import hashlib,json

def expected(case,size,seed):
    if case!='records':raise ValueError(case)
    types=('integer','string','boolean','date')
    descriptors=[['feature_%d_%d'%(seed,index),types[index%4],'default'] for index in range(size)]
    counts={kind:sum(row[1]==kind for row in descriptors) for kind in sorted(set(row[1] for row in descriptors))}
    encoded=json.dumps(descriptors,ensure_ascii=False,separators=(',',':')).encode()
    return {'columns':size,'schema_sha256':hashlib.sha256(encoded).hexdigest(),'types':counts,'head':descriptors[:4],'tail':descriptors[-4:],'input_unchanged':True}
