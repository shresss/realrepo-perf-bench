"""Independent conditional-likelihood equations, using only the standard library.

Fixtures contain inputs and probe parameters only. No saved production answers.
Fitted outputs are checked against likelihood, score and observed-information
equations at the returned coefficients, including the optimizer stopping rule.
"""
from collections import Counter
from functools import lru_cache
import gzip
import hashlib
import itertools
import json
import math
from pathlib import Path

FIXTURE_SHA = '2424e76cb452244d69493f6a41d9270da1179aafb0b95874a11dc851f5ea4c37'

@lru_cache(maxsize=1)
def inputs():
    raw = Path(__file__).with_name('fixture-inputs.json.gz').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA
    return json.loads(gzip.decompress(raw))

@lru_cache(maxsize=32)
def expected(case, size, seed):
    data = inputs()[f'{case}:{size}:{seed}']
    q, c = len(data['x'][0]), max(data['y'])
    grouped = {}
    for y, x, group in zip(data['y'],data['x'],data['groups']):
        grouped.setdefault(group,[]).append((y,x))
    models=[]
    for rows in grouped.values():
        outcomes = tuple(y for y,x in rows)
        columns = [x for y,x in rows]
        def statistic(assignment):
            return [math.fsum(x[j] for x,label in zip(columns,assignment) if label==k)
                    for j in range(q) for k in range(1,c+1)]
        all_stats = [statistic(assignment) for assignment in sorted(set(itertools.permutations(outcomes)))]
        log_multiplicity = math.fsum(math.lgamma(count+1) for count in Counter(outcomes).values())
        models.append((statistic(outcomes),all_stats,log_multiplicity))
    probes=[evaluate(models, p, False)[:2] for p in data['probes']]
    return dict(models=models, probes=probes, fit=data['fit'], n=len(data['y']), d=q*c, q=q, c=c)

def evaluate(models, params, curvature):
    d=len(params); likelihood=0.; grad=[0.]*d; information=[[0.]*d for _ in params]
    for observed,stats,log_multiple in models:
        eta=[math.fsum(a*b for a,b in zip(row,params)) for row in stats]
        shift=max(eta); mass=[math.exp(v-shift) for v in eta]; total=math.fsum(mass)
        weights=[v/total for v in mass]
        means=[math.fsum(weight*row[j] for weight,row in zip(weights,stats)) for j in range(d)]
        likelihood += math.fsum(a*b for a,b in zip(observed,params))-shift-math.log(total)-log_multiple
        for j in range(d): grad[j] += observed[j]-means[j]
        if curvature:
            for j in range(d):
                for k in range(j+1):
                    value=math.fsum(weight*(row[j]-means[j])*(row[k]-means[k]) for weight,row in zip(weights,stats))
                    information[j][k]+=value
                    if j!=k: information[k][j]+=value
    return likelihood,grad,information

def invert(matrix):
    n=len(matrix); a=[list(row)+[float(i==j) for j in range(n)] for i,row in enumerate(matrix)]
    for j in range(n):
        pivot=max(range(j,n),key=lambda i:abs(a[i][j])); a[j],a[pivot]=a[pivot],a[j]
        scale=a[j][j]
        if abs(scale)<1e-14: raise ValueError('singular fitted information')
        a[j]=[v/scale for v in a[j]]
        for i in range(n):
            if i!=j:
                factor=a[i][j]; a[i]=[x-factor*y for x,y in zip(a[i],a[j])]
    return [row[n:] for row in a]

def close(a,b,rtol=1e-8,atol=1e-8):
    return (isinstance(a,list) and len(a)==len(b) and all(
        isinstance(x,(int,float)) and math.isfinite(x) and abs(x-y)<=atol+rtol*abs(y) for x,y in zip(a,b)))

def equivalent(actual,want):
    try:
        keys={f'{kind}{i}' for kind in ['loglike','score'] for i in range(3)}|{'input_unchanged'}
        if want['fit']: keys|={'params','bse','llf'}
        if not isinstance(actual,dict) or set(actual)!=keys or actual['input_unchanged'] is not True: return False
        for i,(ll,gradient) in enumerate(want['probes']):
            if not close(actual[f'loglike{i}'],[ll]) or not close(actual[f'score{i}'],gradient): return False
        if want['fit']:
            params=actual['params']
            if not close(params,params) or len(params)!=want['d']: return False
            ll,gradient,information=evaluate(want['models'],params,True)
            # statsmodels BFGS minimizes mean negative log likelihood, gtol=1e-5.
            if max(abs(v) for v in gradient)/want['n']>1.1e-5: return False
            if not close(actual['llf'],[ll]): return False
            covariance=invert(information)
            diagonal=[math.sqrt(covariance[j][j]) for j in range(len(params))]
            # Public MultinomialResults.bse reshapes its covariance diagonal in Fortran order.
            bse=[diagonal[j+k*want['q']] for j in range(want['q']) for k in range(want['c'])]
            if not close(actual['bse'],bse,rtol=1e-6,atol=1e-8): return False
        return True
    except (TypeError,ValueError,OverflowError,KeyError,ZeroDivisionError):
        return False
