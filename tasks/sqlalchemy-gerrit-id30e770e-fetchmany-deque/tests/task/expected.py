import hashlib

def expected(case,size,seed):
    if case in ('fetch-sequence','zero-size','empty-select'):
        keys=['id','customer','sku','qty','amount_cents','status']
        values=[[i,f'cust-{(i*37+seed)%5000:05d}',f'SKU-{(i*11+seed)%900:04d}',1+(i+seed)%8,100+(i*97+seed)%99900,('new','paid','shipped','refunded')[(i+seed)%4]] for i in range(size)]
        if case=='fetch-sequence':return {'keys':keys,'first':values[0] if values else None,'many':values[1:4],'default':values[4:],'rest':[]}
        if case=='zero-size':return {'keys':keys,'zero':[],'rest':[],'first':None}
        return {'keys':keys,'many':[],'first':None,'batches':[]}
    digest=hashlib.sha256();lengths=[]
    for start in range(0,size,50):
        values=[(i,f'cust-{(i*37+seed)%5000:05d}',f'SKU-{(i*11+seed)%900:04d}',1+(i+seed)%8,100+(i*97+seed)%99900,('new','paid','shipped','refunded')[(i+seed)%4]) for i in range(start,min(start+50,size))]
        digest.update(repr(values).encode());lengths.append(len(values))
    return {'count':size,'id_sum':size*(size-1)//2,'batch_lengths':lengths,'sha256':digest.hexdigest(),'terminal':[None,[],[]]}
