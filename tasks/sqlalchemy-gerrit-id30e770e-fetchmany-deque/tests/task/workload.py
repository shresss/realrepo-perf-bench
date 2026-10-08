import hashlib,json,os,sys
from pathlib import Path

def run(case,size,seed):
    if source:=os.environ.get('AQ_SOURCE'):
        sys.path.insert(0,source)
    else:
        for entry in [*sys.path, str(Path.cwd())]:
            candidate = Path(entry or '.') / 'lib'
            if (candidate / 'sqlalchemy/__init__.py').is_file():
                sys.path.insert(0,str(candidate)); break
        else:
            raise RuntimeError('SQLAlchemy source lib directory not present in the worker snapshot')
    from sqlalchemy import create_engine,MetaData,Table,Column,Integer,String,insert
    from sqlalchemy.util import has_compiled_ext
    assert not has_compiled_ext(), 'The declared scenario uses pure-Python SQLAlchemy'
    engine=create_engine('sqlite:///:memory:')
    meta=MetaData()
    orders=Table('orders',meta,Column('id',Integer,primary_key=True),Column('customer',String),Column('sku',String),Column('qty',Integer),Column('amount_cents',Integer),Column('status',String))
    meta.create_all(engine)
    rows=[{'id':i,'customer':f'cust-{(i*37+seed)%5000:05d}','sku':f'SKU-{(i*11+seed)%900:04d}','qty':1+(i+seed)%8,'amount_cents':100+(i*97+seed)%99900,'status':('new','paid','shipped','refunded')[(i+seed)%4]} for i in range(size)]
    if os.environ.get('AQ_FLOOR')=='1':
        engine.dispose();return {'floor':True,'rows':size}
    if case in ('fetch-sequence','zero-size','empty-select'):
        from sqlalchemy import select
        with engine.begin() as conn:
            result = conn.execute(select(orders)) if case=='empty-select' else conn.execute(insert(orders).returning(*orders.c),rows)
            keys=list(result.keys())
            if case=='fetch-sequence':
                first=result.fetchone()
                value={'keys':keys,'first':list(first) if first is not None else None,
                       'many':[list(row) for row in result.fetchmany(3)],
                       'default':[list(row) for row in result.fetchmany()],
                       'rest':[list(row) for row in result.fetchall()]}
            elif case=='zero-size':
                value={'keys':keys,'zero':[list(row) for row in result.fetchmany(0)],'rest':[list(row) for row in result.fetchall()],'first':result.fetchone()}
            else:
                value={'keys':keys,'many':[list(row) for row in result.fetchmany(50)],'first':result.fetchone(),'batches':list(result.partitions(50))}
        engine.dispose();return value
    lengths=[];digest=hashlib.sha256();count=0;id_sum=0
    with engine.begin() as conn:
        result=conn.execute(insert(orders).returning(*orders.c),rows)
        for partition in result.partitions(50):
            values=[tuple(row) for row in partition]
            lengths.append(len(values));count+=len(values);id_sum+=sum(row[0] for row in values)
            digest.update(repr(values).encode())
        terminal=[result.fetchone(),result.fetchmany(50),result.fetchall()]
    engine.dispose()
    return {'count':count,'id_sum':id_sum,'batch_lengths':lengths,'sha256':digest.hexdigest(),'terminal':terminal}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);parser.add_argument('--size',type=int,required=True);parser.add_argument('--seed',type=int,required=True)
    args=parser.parse_args();print(json.dumps(run(args.case,args.size,args.seed),sort_keys=True))
