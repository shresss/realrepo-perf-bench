# optuna-bruteforce-series-6650-6649-6705-6646

Speed up exhaustive Optuna BruteForceSampler sweeps (study.optimize until the grid is exhausted) while preserving the exact seeded trial sequence and stop-on-exhaustion semantics.

- Upstream repository: https://github.com/optuna/optuna (MIT)
- Base commit: `bf732bdb855aa22010ac4a80063539d6faf37409`
- Expert reference: `62ac5ef59038da1932affdb61cb9f26c170bfe21` from https://github.com/optuna/optuna/pull/6650, https://github.com/optuna/optuna/pull/6649, https://github.com/optuna/optuna/pull/6705, https://github.com/optuna/optuna/pull/6646
- Reference provenance: `public-pr-series`

The agent receives `instruction.md` and the repository at the base commit. `solution/` holds the expert reference; `tests/` holds the verifier (protected tests, hidden cases, timing and scoring policy).

## Graded cases

| Case | Expert speedup R | Bar (candidate/baseline CPU at most) |
|---|---|---|
| `grid-1320` | 3.31 | 0.55 |

## Controls (run through the verifier before any model ran)

- `controls/alternative.patch`: a different correct fix; must pass
- `controls/naive.patch`: the obvious shallow fix; must fail (usually the speed bar)
- `controls/negative-flat-weights.patch`: a fast but incorrect fix; must fail correctness

## Results (first counted attempt per model)

| Model | Passed | Expert parity |
|---|---|---|
| Claude Opus 5.5 | True | False |
| Gemini 3.8 Flash | True | True |
| GPT-6 Astra | True | True |
