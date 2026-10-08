"""Real source-bound public VECM fits; original screening fixtures unchanged."""
import json
from pathlib import Path
import sys

CASES = {
    "sem-nc-r1": dict(T=120,K=3,k_ar_diff=1,rank=1,det="n",seasons=0,exog=0,exog_coint=0,seed=1),
    "sem-co-r2": dict(T=200,K=4,k_ar_diff=2,rank=2,det="co",seasons=0,exog=0,exog_coint=0,seed=2),
    "sem-ci-lag0": dict(T=150,K=3,k_ar_diff=0,rank=1,det="ci",seasons=0,exog=0,exog_coint=0,seed=3),
    "sem-colo-seas": dict(T=240,K=3,k_ar_diff=2,rank=1,det="colo",seasons=4,exog=0,exog_coint=0,seed=4),
    "sem-cili-exog": dict(T=300,K=4,k_ar_diff=1,rank=3,det="cili",seasons=0,exog=2,exog_coint=1,seed=5),
    "sem-li-rankmax": dict(T=180,K=2,k_ar_diff=3,rank=1,det="li",seasons=12,exog=1,exog_coint=0,seed=6),
    "perf-hourly-8760": dict(T=8760,K=4,k_ar_diff=2,rank=1,det="ci",seasons=24,exog=0,exog_coint=0,seed=11),
    "perf-hourly-8760x12": dict(T=8760,K=4,k_ar_diff=2,rank=1,det="ci",seasons=24,exog=0,exog_coint=0,seed=11,groups=12),
}


def fixture(case, size, seed):
    import numpy as np
    c = dict(CASES[case])
    assert c["T"] == size and c["seed"] == seed
    groups = []
    for group in range(c.get("groups",1)):
        rng = np.random.default_rng(seed + group)
        total, k, rank = size + 1, c["K"], c["rank"]
        trends = np.cumsum(rng.standard_normal((total,k-rank)),axis=0)
        load = rng.uniform(.5,1.5,size=(k-rank,k))
        noise = np.zeros((total,k)); innovations = rng.standard_normal((total,k))
        for t in range(1,total):
            noise[t] = .6 * noise[t-1] + innovations[t]
        endog = 50 + trends @ load + noise
        exog = rng.standard_normal((total,c["exog"])) if c["exog"] else None
        exog_coint = np.cumsum(rng.standard_normal((total,c["exog_coint"])),axis=0) if c["exog_coint"] else None
        groups.append((endog,exog,exog_coint))
    return c,groups


def build(spec):
    from statsmodels.tsa.vector_ar.vecm import VECM
    import statsmodels.tsa.vector_ar.vecm as target
    file = Path(target.__file__).resolve()
    root = file.parents[3]
    assert file == root / "statsmodels/tsa/vector_ar/vecm.py"
    assert str(root) in [str(Path(value).resolve()) for value in sys.path if value], "source root not explicitly active"
    c,groups = spec
    return [(VECM(y,exog=exog,exog_coint=exog_coint,k_ar_diff=c["k_ar_diff"],coint_rank=c["rank"],
                  deterministic=c["det"],seasons=c["seasons"]), (y,exog,exog_coint)) for y,exog,exog_coint in groups]


def source_closure(root):
    modules = {name: Path(module.__file__).resolve() for name,module in sys.modules.items()
               if name.startswith("statsmodels") and getattr(module,"__file__",None)}
    assert all(path.is_relative_to(root) for path in modules.values()), modules
    assert not any(path.suffix in {".so",".pyd",".dylib"} for path in modules.values()), modules


def run(case,size,seed):
    import numpy as np
    models = build(fixture(case,size,seed))
    observed = []
    for model,inputs in models:
        originals = [None if array is None else array.copy() for array in inputs]
        result = model.fit()
        values = {}
        for key in ("alpha","beta","gamma","sigma_u","llf","stderr_alpha","stderr_beta",
                    "pvalues_gamma","det_coef","det_coef_coint"):
            array = np.asarray(getattr(result,key))
            # Real-domain numerical eigensystems can retain roundoff imaginary
            # components. Reject substantial complex output, not silently drop it.
            if np.iscomplexobj(array):
                assert np.max(np.abs(array.imag),initial=0.0) <= 1e-9, key
                array = array.real
            values[key] = np.asarray(array,dtype=float).ravel().tolist()
        if inputs[1] is None:
            values["predict"] = result.predict(steps=24).ravel().tolist()
        assert all(np.isfinite(value).all() for value in values.values())
        assert all(before is None or np.array_equal(before,array) for before,array in zip(originals,inputs))
        observed.append(values)
    import statsmodels.tsa.vector_ar.vecm as target
    source_closure(Path(target.__file__).resolve().parents[3])
    return {"fits": observed}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--case",required=True)
    parser.add_argument("--size",type=int,required=True)
    parser.add_argument("--seed",type=int,required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case,args.size,args.seed),allow_nan=False))
