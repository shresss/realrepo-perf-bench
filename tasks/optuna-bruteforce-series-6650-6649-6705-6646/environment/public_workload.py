"""Public Optuna profiling cases: grid, conditional and failures.

run(case, size, seed) creates a seeded BruteForceSampler study, invokes study.optimize,
and returns the complete ordered trial records. Grid sizes are multiples of132;
conditional uses96 configurations and failures uses36. Published sizes and seeds
are listed in public-cases.json. No expected answers or scoring logic are included.
"""
import argparse
import json
import math

GRID_BLOCK = 132  # 4 optimizers x 11 dropout values x 3 activations


PUBLIC_CASES = ("grid", "conditional", "failures")

def run(case, size, seed):
    if case not in PUBLIC_CASES:
        raise ValueError("unsupported public case")
    import optuna
    from optuna.samplers import BruteForceSampler
    from optuna.trial import TrialState

    if type(size) is not int or type(seed) is not int or size < 1:
        raise ValueError("size and seed must be positive integers")
    optuna.logging.set_verbosity(optuna.logging.ERROR)
    study = optuna.create_study(sampler=BruteForceSampler(seed=seed, avoid_premature_stop=False))

    if case == "grid":
        if size % GRID_BLOCK:
            raise ValueError("grid size must be a multiple of 132")
        xs = size // GRID_BLOCK

        def objective(t):
            x = t.suggest_int("n_estimators_k", 1, xs)
            opt = t.suggest_categorical("optimizer", ["sgd", "adam", "rmsprop", "adagrad"])
            lr = t.suggest_float("dropout", 0.0, 1.0, step=0.1)
            act = t.suggest_categorical("activation", ["relu", "tanh", "gelu"])
            return x * 0.37 + len(opt) * 1.1 - lr * 2.3 + len(act)
        study.optimize(objective)
    elif case == "conditional":
        if size != 96:
            raise ValueError("conditional size must be 96")

        def objective(t):
            model = t.suggest_categorical("model", ["linear", "tree", "knn"])
            if model == "linear":
                a = t.suggest_float("alpha", 0.0, 0.5, step=0.05)
                pen = t.suggest_categorical("penalty", ["l1", "l2"])
                return a + (pen == "l1")
            if model == "tree":
                d = t.suggest_int("depth", 1, 8)
                lv = t.suggest_int("leaves", 2, 16, step=2)
                return d * 0.1 + lv * 0.01
            k = t.suggest_int("k", 1, 9, step=2)
            w = t.suggest_categorical("weights", ["uniform", "distance"])
            return k + (w == "uniform")
        study.optimize(objective)
    elif case == "failures":
        if size != 36:
            raise ValueError("failures size must be 36")

        def objective(t):
            x = t.suggest_int("x", 0, 5)
            y = t.suggest_float("y", 0.25, 1.5, step=0.25)
            if (x + int(y * 4)) % 5 == 0:
                raise optuna.TrialPruned()
            if (x * 3 + int(y * 4)) % 7 == 0:
                raise ValueError("synthetic failure")
            if x == 4 and y == 0.5:
                return float("nan")
            return x - y
        study.optimize(objective, catch=(ValueError,))
    else:
        raise ValueError("unsupported case")

    def norm(v):
        if isinstance(v, float) and math.isnan(v):
            return "nan"
        return v
    trials = [[t.number, t.state.name, sorted((k, repr(norm(v))) for k, v in t.params.items()),
               None if t.values is None else [norm(v) for v in t.values]] for t in study.trials]
    return {"n_trials": len(trials), "trials": trials,
            "n_complete": sum(t.state == TrialState.COMPLETE for t in study.trials)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, choices=PUBLIC_CASES)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
