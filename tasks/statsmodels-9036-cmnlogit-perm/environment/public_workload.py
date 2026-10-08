"""Source-bound conditional multinomial model fitting for declared customer panels."""
import json
from pathlib import Path
import sys
CASES = {'sem-eval-g5-k3': dict(ngroups=12, gsize=5, k=3, q=2, seed=1, fit=False), 'sem-fit-g4-k3': dict(ngroups=40, gsize=4, k=3, q=2, seed=5, fit=True), 'panel_fit': dict(ngroups=400, gsize=5, k=3, q=3, seed=11, fit=True)}

def fixture(c):
    import numpy as np
    rng = np.random.default_rng(c['seed'])
    sizes = [c['gsize'][g % len(c['gsize'])] if isinstance(c['gsize'], tuple) else c['gsize'] for g in range(c['ngroups'])]
    groups = np.repeat(np.arange(c['ngroups']), sizes)
    n = len(groups)
    x = rng.standard_normal((n, c['q']))
    coef = rng.uniform(-1.0, 1.0, size=(c['q'], c['k']))
    coef[:, 0] = 0
    fe = rng.standard_normal((c['ngroups'], c['k']))
    fe[:, 0] = 0
    lp = x @ coef + fe[groups]
    pr = np.exp(lp)
    pr /= pr.sum(1)[:, None]
    u = rng.uniform(size=n)
    y = (u[:, None] > pr.cumsum(1)).sum(1)
    y = np.minimum(y, c['k'] - 1)
    y[0] = c['k'] - 1
    return (y, x, groups)

def run(case, size, seed):
    import numpy as np
    from statsmodels.discrete.conditional_models import ConditionalMNLogit
    import statsmodels.discrete.conditional_models as target
    c = dict(CASES[case])
    c['ngroups'] = size
    c['seed'] = seed
    y, x, groups = fixture(c)
    originals = [array.copy() for array in [y, x, groups]]
    model = ConditionalMNLogit(y, x, groups=groups)
    obs = {}
    rng = np.random.default_rng(seed + 100)
    for i in range(3):
        p = rng.standard_normal(model.exog.shape[1] * (model.k_cat - 1))
        obs[f'loglike{i}'] = [model.loglike(p)]
        obs[f'score{i}'] = model.score(p)
    if c['fit']:
        result = model.fit(method='BFGS', maxiter=200, generator=np.random.RandomState(seed))
        obs.update(params=result.params, bse=result.bse, llf=[result.llf])
    values = {k: np.asarray(v, dtype=float).ravel().tolist() for k, v in obs.items()}
    values['input_unchanged'] = all((np.array_equal(before, after) for before, after in zip(originals, [y, x, groups])))
    root = Path(target.__file__).resolve().parents[2]
    modules = {name: Path(module.__file__).resolve() for name, module in sys.modules.items() if name.startswith('statsmodels') and getattr(module, '__file__', None)}
    assert all((path.is_relative_to(root) and path.suffix not in {'.so', '.pyd', '.dylib'} for path in modules.values()))
    return values
if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--case', required=True)
    p.add_argument('--size', type=int, required=True)
    p.add_argument('--seed', type=int, required=True)
    a = p.parse_args()
    print(json.dumps(run(a.case, a.size, a.seed), allow_nan=False))
