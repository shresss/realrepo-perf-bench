"""Exhaustive hyperparameter sweeps through Optuna's public API with BruteForceSampler.

run(case, size, seed) creates a study with BruteForceSampler(seed=seed), drives it through the
public API (create_study, optimize, enqueue_trial, ask/tell) and returns every trial's number,
state, params and value. No timing, expected answers or reward logic live here.

Adapted from the mining screen workload (workload_bruteforce.py, sha256 0b887e8c...) to the
template signature run(case, size, seed); objectives, search spaces and seeds are unchanged.
Cases and the meaning of `size`:
  grid              size = number of grid configurations, a multiple of 132
                    (n_estimators_k 1..size/132, 4 optimizers, 11 dropout steps, 3 activations)
  conditional       size must be 96 (conditional space: 22 linear + 64 tree + 10 knn configs)
  conditional-aps   same space with avoid_premature_stop=True
  nan               size must be 180 (inf/-inf/nan/None/str/int categorical choices)
  failures          size must be 36 (pruned, raised and NaN-valued trials, catch=(ValueError,))
  enqueue           size = n_trials passed to optimize (enqueued duplicate and partial trials)
  ask-tell-running  size = number of ask() calls (trials left RUNNING, finished out of order)
"""
import argparse
import json
import math

GRID_BLOCK = 132  # 4 optimizers x 11 dropout values x 3 activations


def run(case, size, seed):
    import optuna
    from optuna.samplers import BruteForceSampler
    from optuna.trial import TrialState

    if type(size) is not int or type(seed) is not int or size < 1:
        raise ValueError("size and seed must be positive integers")
    optuna.logging.set_verbosity(optuna.logging.ERROR)
    aps = case == "conditional-aps"
    study = optuna.create_study(sampler=BruteForceSampler(seed=seed, avoid_premature_stop=aps))

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
    elif case in ("conditional", "conditional-aps"):
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
    elif case == "nan":
        if size != 180:
            raise ValueError("nan size must be 180")
        weird = [float("inf"), -float("inf"), float("nan"), None, "s", 3]

        def objective(t):
            a = t.suggest_categorical("a", weird)
            b = t.suggest_categorical("b", weird)
            c = t.suggest_float("c", -1.0, 1.0, step=0.5)
            return 0.0 if a is None else float(len(repr(a)) + len(repr(b))) + c
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
    elif case == "enqueue":
        study.enqueue_trial({"x": 2, "y": "b"})
        study.enqueue_trial({"x": 6, "y": "a"})
        study.enqueue_trial({"x": 2, "y": "b"})      # duplicate
        study.enqueue_trial({"x": 4})                # partial

        def objective(t):
            x = t.suggest_int("x", 0, 6, step=2)
            y = t.suggest_categorical("y", ["a", "b", "c"])
            return x + ord(y)
        study.optimize(objective, n_trials=size)
    elif case == "ask-tell-running":
        # Interleaved ask/tell with trials left running, then finished out of order.
        held = []
        for i in range(size):
            t = study.ask()
            x = t.suggest_int("x", 0, 3)
            z = t.suggest_float("z", 0.0, 0.4, step=0.1)
            if i % 4 == 0:
                held.append((t, x + z))
            else:
                study.tell(t, x + z)
            if i % 6 == 5:
                for ht, v in reversed(held):
                    study.tell(ht, v)
                held.clear()
        for ht, v in held:
            study.tell(ht, v)
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
    parser.add_argument("--case", required=True)
    parser.add_argument("--size", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.case, args.size, args.seed), allow_nan=False, sort_keys=True))
