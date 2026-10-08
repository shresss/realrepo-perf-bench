import sys,hashlib,json,pickle,copy
from pathlib import Path

def build(case,size,seed):
    roots=[Path(p) for p in sys.path if p]+[Path.cwd()]
    root=next(p for p in roots if(p/'pydicom/__init__.py').is_file());sys.path.insert(0,str(root))
    import pydicom
    assert Path(pydicom.__file__).resolve().is_relative_to(root.resolve())
    from pydicom.dataset import Dataset
    from pydicom.sequence import Sequence
    ds=Dataset();frames=Sequence();ds.PerFrameFunctionalGroupsSequence=frames
    for i in range(size):
        plane=Dataset();plane.XOffsetInSlideCoordinateSystem='0.0';plane.YOffsetInSlideCoordinateSystem='0.0';plane.ZOffsetInSlideCoordinateSystem='0.0'
        plane.ColumnPositionInTotalImagePixelMatrix=(i*31+seed)%10009
        plane.RowPositionInTotalImagePixelMatrix=(i*17+seed)%10007
        group=Dataset();group.PlanePositionSequence=Sequence([plane]);frames.append(group)
    return ds,case,size,seed

def values(ds):
    result=[]
    for i in range(len(ds.PerFrameFunctionalGroupsSequence)):
        group=ds.PerFrameFunctionalGroupsSequence[i];plane=group.PlanePositionSequence[0]
        result.append([int(plane.RowPositionInTotalImagePixelMatrix),int(plane.ColumnPositionInTotalImagePixelMatrix)])
    return result

def run(case,size,seed):
    ds,case,size,seed=build(case,size,seed)
    before=values(ds)
    if case=='copy':ds=copy.deepcopy(ds)
    elif case=='pickle':ds=pickle.loads(pickle.dumps(ds))
    elif case=='mutate' and size:
        seq=ds.PerFrameFunctionalGroupsSequence;item=copy.deepcopy(seq[0]);seq.insert(0,item);seq[-1]=copy.deepcopy(item);seq.pop(1)
    pixels=None
    if case in ('signed_write','copy_signed_write','pickle_signed_write'):
        from io import BytesIO
        import pydicom
        ds.PixelRepresentation=0
        for group in ds.PerFrameFunctionalGroupsSequence:
            group.PlanePositionSequence[0].SmallestImagePixelValue=b'\xff\xff'
        if case=='copy_signed_write':ds=copy.deepcopy(ds)
        elif case=='pickle_signed_write':ds=pickle.loads(pickle.dumps(ds))
        ds.PixelRepresentation=1
        ds.is_little_endian=True;ds.is_implicit_VR=False
        buffer=BytesIO();pydicom.dcmwrite(buffer,ds,write_like_original=True)
        ds=pydicom.dcmread(BytesIO(buffer.getvalue()),force=True)
        pixels=[[int(g.PlanePositionSequence[0].SmallestImagePixelValue),g.PlanePositionSequence[0][0x00280106].VR] for g in ds.PerFrameFunctionalGroupsSequence]
    after=before if case=="indexed" else values(ds)
    result={'count':len(after),'sha256':hashlib.sha256(json.dumps(after,separators=(',',':')).encode()).hexdigest(),'small':after if size<30 else None,'before_hash':hashlib.sha256(json.dumps(before,separators=(',',':')).encode()).hexdigest()}
    if pixels is not None:result['pixels']=pixels
    return result

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--case',default='indexed');p.add_argument('--size',type=int,default=500);p.add_argument('--seed',type=int,default=71)
    a=p.parse_args();print(json.dumps(run(a.case,a.size,a.seed),sort_keys=True))
